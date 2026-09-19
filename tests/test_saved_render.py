import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from pydantic import ValidationError

from flcopilot.assets import AssetStore, atomic_json
from flcopilot.contracts import PlanError
from flcopilot.demo import DemoAdapter
from flcopilot.mcp_relay import tool_call
from flcopilot.saved_render import RenderStartRequest, SavedRenderController
from flcopilot.server import LocalServer
from flcopilot.service import Service


class FakeRenderManager:
    def __init__(self):
        self.jobs = {}
        self.last_request = None
        self.closed = False

    def start(self, request):
        self.last_request = request
        ident = "render-" + f"{len(self.jobs)+1:020x}"
        output = Path(request["output_directory"]) / ("private-project-" + ident) / "private-name.wav"
        output.parent.mkdir(parents=True, exist_ok=False)
        row = {
            "job_id": ident,
            "status": "queued",
            "project_path": request["project_path"],
            "output_directory": request["output_directory"],
            "output_path": str(output),
            "platform": "windows",
            "launch_method": "windows_executable",
            "command": ["FL64.exe", "/Rprivate"],
            "created_at": "2026-09-19T12:00:00Z",
            "started_at": None,
            "finished_at": None,
            "cancel_requested": False,
            "application_exit_observed": False,
            "process_return_code": None,
            "renderer_may_be_running": False,
            "result": None,
            "error": None,
            "warnings": ["Saved-state fixture"],
            "includes_unsaved_changes": False,
        }
        self.jobs[ident] = row
        return dict(row)

    def status(self, ident):
        if ident not in self.jobs:
            raise RuntimeError("Unknown render job")
        return dict(self.jobs[ident])

    def list(self):
        return [dict(row) for row in self.jobs.values()]

    def cancel(self, ident):
        row = self.jobs[ident]
        row.update(
            status="cancelled",
            cancel_requested=True,
            finished_at="2026-09-19T12:01:00Z",
            renderer_may_be_running=False,
        )
        return dict(row)

    def complete(self, ident, *, outside=None):
        row = self.jobs[ident]
        output = Path(outside) if outside is not None else Path(row["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        y = np.random.default_rng(55).normal(size=(8000, 2)).astype("float32") * 0.01
        sf.write(output, y, 8000, subtype="FLOAT")
        row.update(
            status="completed",
            started_at="2026-09-19T12:00:01Z",
            finished_at="2026-09-19T12:00:04Z",
            application_exit_observed=True,
            process_return_code=0,
            renderer_may_be_running=False,
            result={
                "path": str(output),
                "size_bytes": output.stat().st_size,
                "modified_ns": output.stat().st_mtime_ns,
                "sample_rate": 8000,
                "channels": 2,
                "frames": 8000,
                "duration_seconds": 1.0,
                "subtype": "FLOAT",
                "fully_decoded": True,
            },
        )

    def shutdown(self, wait=True):
        self.closed = True


def make_flp(path):
    path.write_bytes(b"FLhd" + bytes(range(64)))
    return path


def controller(tmp_path):
    assets = AssetStore(tmp_path / "workspace")
    manager = FakeRenderManager()
    render = SavedRenderController(assets, manager=manager, request_factory=lambda **kwargs: kwargs)
    return assets, manager, render


def test_saved_render_requires_literal_true_and_printable_paths():
    base = dict(project_path="/tmp/beat.flp", confirm_saved_state_only=True)
    assert RenderStartRequest(**base).confirm_saved_state_only is True
    for value in (1, 0, False, "true", None):
        with pytest.raises(ValidationError):
            RenderStartRequest(project_path="/tmp/beat.flp", confirm_saved_state_only=value)
    with pytest.raises(ValidationError):
        RenderStartRequest(project_path="/tmp/bad\nname.flp", confirm_saved_state_only=True)


def test_render_start_hides_paths_and_forces_private_output_root(tmp_path):
    assets, manager, render = controller(tmp_path)
    source = make_flp(tmp_path / "Very Private Beat.flp").resolve()
    started = render.start({"project_path": str(source), "confirm_saved_state_only": True, "timeout_seconds": 90.0})
    assert started["status"] == "queued" and not started["published"]
    assert started["source_sha256"] and not started["includes_unsaved_changes"]
    payload = json.dumps(started)
    assert str(source) not in payload and "FL64.exe" not in payload and "private-project" not in payload
    assert manager.last_request["project_path"] == str(source)
    assert manager.last_request["output_directory"] == str(render.root)
    assert manager.last_request["timeout_seconds"] == 90.0
    assert manager.last_request["fl_studio_path"] is None
    render.close()
    assert manager.closed


def test_completed_render_is_registered_once_with_generic_public_path(tmp_path):
    assets, manager, render = controller(tmp_path)
    source = make_flp(tmp_path / "Secret Song Name.flp").resolve()
    started = render.start({"project_path": str(source), "confirm_saved_state_only": True})
    manager.complete(started["job_id"])
    completed = render.get({"job_id": started["job_id"]})
    assert completed["status"] == "completed" and completed["published"]
    assert completed["asset"]["kind"] == "audio"
    assert completed["audio"]["fully_decoded"] is True
    again = render.get({"job_id": started["job_id"]})
    assert again["asset"] == completed["asset"]
    outputs = [row for row in assets.list() if row["kind"] == "audio"]
    assert len(outputs) == 1
    assert "Secret Song Name" not in outputs[0]["path"]
    assert "private-project" not in outputs[0]["path"]
    assert assets.resolve(outputs[0]["id"]).name.startswith("Saved_Project_Render_")


def test_output_ready_is_not_published_and_source_mutation_blocks_completion(tmp_path):
    assets, manager, render = controller(tmp_path)
    source = make_flp(tmp_path / "beat.flp").resolve()
    started = render.start({"project_path": str(source), "confirm_saved_state_only": True})
    manager.jobs[started["job_id"]]["status"] = "output_ready"
    assert not render.get({"job_id": started["job_id"]})["published"]
    manager.complete(started["job_id"])
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(PlanError, match="project bytes changed"):
        render.get({"job_id": started["job_id"]})
    assert not [row for row in assets.list() if row["kind"] == "audio"]


def test_renderer_output_escape_and_bad_local_path_are_refused(tmp_path):
    assets, manager, render = controller(tmp_path)
    with pytest.raises(PlanError, match="absolute path"):
        render.start({"project_path": "relative.flp", "confirm_saved_state_only": True})
    source = make_flp(tmp_path / "beat.flp").resolve()
    started = render.start({"project_path": str(source), "confirm_saved_state_only": True})
    manager.complete(started["job_id"], outside=tmp_path / "outside.wav")
    with pytest.raises(PlanError, match="escaped"):
        render.get({"job_id": started["job_id"]})


@pytest.fixture
def http_app(tmp_path):
    service = Service(tmp_path / "workspace", DemoAdapter())
    manager = FakeRenderManager()
    service.saved_renders._manager_instance = manager
    service.saved_renders._request_factory = lambda **kwargs: kwargs
    server = LocalServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    atomic_json(tmp_path / "workspace" / "server.json", {"origin": server.origin, "token": server.token})
    yield service, manager, server, tmp_path / "workspace"
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()
    service.close()


def call(server, path, data=None, *, token=True):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + server.token
    request = urllib.request.Request(
        server.origin + path,
        headers=headers,
        data=json.dumps(data).encode() if data is not None else None,
    )
    try:
        return urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as error:
        error.close()
        raise


def test_saved_render_http_and_mcp_monitoring_are_path_free(http_app):
    service, manager, server, workspace = http_app
    source = make_flp(workspace.parent / "My Private Project.flp").resolve()
    with pytest.raises(urllib.error.HTTPError) as error:
        call(server, "/api/render-start", {"project_path": str(source), "confirm_saved_state_only": True}, token=False)
    assert error.value.code == 403

    with call(server, "/api/render-start", {"project_path": str(source), "confirm_saved_state_only": True}) as response:
        started = json.load(response)
    assert started["status"] == "queued"
    listed = tool_call(workspace, "copilot_renders", {})
    assert len(listed) == 1 and listed[0]["job_id"] == started["job_id"]
    observed = tool_call(workspace, "copilot_render_get", {"job_id": started["job_id"]})
    assert observed["job_id"] == started["job_id"]
    assert str(source) not in json.dumps(listed) and str(source) not in json.dumps(observed)
    with pytest.raises(ValueError, match="Unknown tool"):
        tool_call(workspace, "copilot_render_start", {"project_path": str(source)})
    manager.complete(started["job_id"])
    completed = tool_call(workspace, "copilot_render_get", {"job_id": started["job_id"]})
    assert completed["published"] and completed["asset"]["kind"] == "audio"
    assert not service.adapter.calls


def test_stop_requests_render_cancellation(http_app):
    service, manager, server, workspace = http_app
    source = make_flp(workspace.parent / "beat.flp").resolve()
    started = service.render_start({"project_path": str(source), "confirm_saved_state_only": True})
    result = service.stop()
    assert result["stopped"] and len(result["saved_render_cancellations"]) == 1
    assert manager.jobs[started["job_id"]]["status"] == "cancelled"
