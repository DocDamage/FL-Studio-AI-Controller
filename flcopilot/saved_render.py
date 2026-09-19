"""Saved-project rendering through the pinned PostFader V10 process adapter.

Starting a render is deliberately a local desktop/API action because it accepts an
absolute project path. Public job state and MCP monitoring never expose filesystem
paths or the renderer command. Only a completed, fully decoded WAV is published.
"""
from __future__ import annotations

import importlib.metadata
import json
import threading
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from .assets import file_hash
from .contracts import PlanError, Strict

MAX_FLP_BYTES = 300 * 1024 * 1024
TERMINAL = {"completed", "failed", "cancelled", "timed_out"}


class RenderStartRequest(Strict):
    project_path: str = Field(min_length=1, max_length=4096)
    fl_studio_path: str | None = Field(default=None, min_length=1, max_length=4096)
    timeout_seconds: float = Field(default=600.0, ge=30.0, le=7200.0)
    confirm_saved_state_only: Literal[True]

    @field_validator("confirm_saved_state_only", mode="before")
    @classmethod
    def explicit_saved_state_confirmation(cls, value):
        if value is not True:
            raise ValueError("Saved-state rendering requires explicit boolean true")
        return value

    @field_validator("project_path", "fl_studio_path")
    @classmethod
    def printable_paths(cls, value):
        if value is not None and any(ord(char) < 32 for char in value):
            raise ValueError("Paths may not contain control characters")
        return value


class RenderJobID(Strict):
    job_id: str = Field(pattern=r"^render-[a-f0-9]{20}$")


class SavedRenderController:
    """Own one PostFader render manager and publish only sanitized completed jobs."""

    def __init__(self, assets, *, manager=None, request_factory=None):
        self.assets = assets
        self.root = (assets.exports / "saved-project-renders").resolve()
        self._manager_instance = manager
        self._request_factory = request_factory
        self._lock = threading.RLock()
        self._sources: dict[str, tuple[Path, str]] = {}
        self._published: dict[str, dict] = {}

    def _manager(self):
        if self._manager_instance is not None:
            return self._manager_instance
        try:
            version = importlib.metadata.version("postfader-fl-studio-mcp")
        except importlib.metadata.PackageNotFoundError as exc:
            raise PlanError(
                "Saved-project rendering requires the pinned PostFader V10 install. "
                "Run the Windows setup with the live adapter enabled."
            ) from exc
        if version != "10.0.0":
            raise PlanError(f"Saved-project rendering qualifies only PostFader 10.0.0; found {version}")
        try:
            from fl_studio_mcp.saved_project_render import SavedProjectRenderJobs
        except ImportError as exc:
            raise PlanError("The installed PostFader package has no saved-project renderer") from exc
        self._manager_instance = SavedProjectRenderJobs()
        return self._manager_instance

    def _build_upstream_request(self, **kwargs):
        if self._request_factory is not None:
            return self._request_factory(**kwargs)
        try:
            from fl_studio_mcp.saved_project_render import SavedProjectRenderRequest
        except ImportError as exc:
            raise PlanError("The installed PostFader package has no saved-project render contract") from exc
        return SavedProjectRenderRequest(**kwargs)

    @staticmethod
    def _raw(job):
        if hasattr(job, "model_dump"):
            return job.model_dump(mode="json")
        if isinstance(job, dict):
            return dict(job)
        raise PlanError("Renderer returned an unsupported job record")

    def _public(self, job):
        raw = self._raw(job)
        ident = raw.get("job_id")
        if not isinstance(ident, str):
            raise PlanError("Renderer returned a job without an ID")
        RenderJobID(job_id=ident)
        result = raw.get("result") if isinstance(raw.get("result"), dict) else None
        audio = None
        if result is not None:
            audio = {
                key: result.get(key)
                for key in (
                    "size_bytes",
                    "sample_rate",
                    "channels",
                    "frames",
                    "duration_seconds",
                    "subtype",
                    "fully_decoded",
                )
            }
        source = self._sources.get(ident)
        asset = self._published.get(ident)
        safe_asset = None
        if asset:
            safe_asset = {key: asset[key] for key in ("id", "name", "sha256", "kind")}
        return {
            "job_id": ident,
            "status": raw.get("status"),
            "platform": raw.get("platform"),
            "launch_method": raw.get("launch_method"),
            "created_at": raw.get("created_at"),
            "started_at": raw.get("started_at"),
            "finished_at": raw.get("finished_at"),
            "cancel_requested": raw.get("cancel_requested", False),
            "application_exit_observed": raw.get("application_exit_observed", False),
            "process_return_code": raw.get("process_return_code"),
            "renderer_may_be_running": raw.get("renderer_may_be_running", False),
            "error": raw.get("error"),
            "warnings": list(raw.get("warnings") or []),
            "includes_unsaved_changes": False,
            "source_sha256": source[1] if source else None,
            "audio": audio,
            "asset": safe_asset,
            "published": safe_asset is not None,
        }

    def _publish_if_complete(self, job):
        raw = self._raw(job)
        ident = raw.get("job_id")
        if raw.get("status") != "completed":
            return self._public(job)
        result = raw.get("result")
        if not isinstance(result, dict) or result.get("fully_decoded") is not True:
            raise PlanError("Renderer reported completion without a fully decoded WAV")
        with self._lock:
            if ident in self._published:
                return self._public(job)
            source_info = self._sources.get(ident)
            if source_info is None:
                raise PlanError("Render source evidence is unavailable in this process")
            source, expected_source_hash = source_info
            try:
                current_source_hash = file_hash(source)
            except OSError as exc:
                raise PlanError("Saved project could not be re-read after rendering; WAV was not published") from exc
            if current_source_hash != expected_source_hash:
                raise PlanError("Saved project bytes changed after rendering started; WAV was not published")
            try:
                source_wav = Path(result.get("path", "")).resolve(strict=True)
            except OSError as exc:
                raise PlanError("Verified render WAV is unavailable; no asset was published") from exc
            if not source_wav.is_relative_to(self.root):
                raise PlanError("Renderer output escaped the private render directory")
            suffix = ident.removeprefix("render-")
            destination = (self.assets.exports / f"Saved_Project_Render_{suffix}.wav").resolve()
            if destination.exists():
                raise PlanError("Render publication destination already exists; refusing overwrite")
            moved = False
            try:
                source_wav.replace(destination)
                moved = True
                record = self.assets.add_output(destination, name="Saved Project Render.wav", kind="audio")
            except Exception:
                if moved and destination.exists() and not source_wav.exists():
                    try:
                        destination.replace(source_wav)
                    except OSError:
                        pass
                raise
            self._published[ident] = record
            return self._public(job)

    def start(self, data):
        request = RenderStartRequest.model_validate_json(json.dumps(data))
        source = Path(request.project_path).expanduser()
        if not source.is_absolute():
            raise PlanError("Choose an absolute path to an existing saved .flp")
        try:
            source = source.resolve(strict=True)
        except OSError as exc:
            raise PlanError("Saved FLP does not exist or cannot be read") from exc
        if source.suffix.lower() != ".flp" or not source.is_file():
            raise PlanError("Choose an existing saved .flp")
        with source.open("rb") as stream:
            if stream.read(4) != b"FLhd":
                raise PlanError("Selected file does not have an FLP header")
        if source.stat().st_size > MAX_FLP_BYTES:
            raise PlanError("Saved FLP exceeds the 300 MiB safety bound")

        configured = None
        if request.fl_studio_path:
            candidate = Path(request.fl_studio_path).expanduser()
            if not candidate.is_absolute():
                raise PlanError("FL Studio executable path must be absolute")
            try:
                configured = str(candidate.resolve(strict=True))
            except OSError as exc:
                raise PlanError("Configured FL Studio application does not exist") from exc

        source_hash = file_hash(source)
        self.root.mkdir(parents=True, exist_ok=True)
        manager = self._manager()
        upstream = self._build_upstream_request(
            project_path=str(source),
            output_directory=str(self.root),
            fl_studio_path=configured,
            timeout_seconds=request.timeout_seconds,
        )
        try:
            job = manager.start(upstream)
        except Exception as exc:
            raise PlanError(str(exc)) from exc
        raw = self._raw(job)
        ident = raw.get("job_id")
        try:
            RenderJobID(job_id=ident)
        except Exception as exc:
            try:
                manager.cancel(ident)
            except Exception:
                pass
            raise PlanError("Renderer returned an invalid job ID") from exc
        with self._lock:
            self._sources[ident] = (source, source_hash)
        return self._publish_if_complete(job)

    def get(self, data):
        request = RenderJobID.model_validate_json(json.dumps(data))
        if self._manager_instance is None:
            raise PlanError("No saved-project render jobs exist in this process")
        try:
            job = self._manager_instance.status(request.job_id)
        except Exception as exc:
            raise PlanError(str(exc)) from exc
        return self._publish_if_complete(job)

    def list(self):
        if self._manager_instance is None:
            return []
        try:
            jobs = self._manager_instance.list()
        except Exception as exc:
            raise PlanError(str(exc)) from exc
        return [self._publish_if_complete(job) for job in jobs]

    def cancel(self, data):
        request = RenderJobID.model_validate_json(json.dumps(data))
        if self._manager_instance is None:
            raise PlanError("No saved-project render jobs exist in this process")
        try:
            job = self._manager_instance.cancel(request.job_id)
        except Exception as exc:
            raise PlanError(str(exc)) from exc
        return self._public(job)

    def active(self):
        if self._manager_instance is None:
            return False
        try:
            return any(self._raw(job).get("status") not in TERMINAL for job in self._manager_instance.list())
        except Exception:
            return True

    def cancel_all(self):
        if self._manager_instance is None:
            return []
        cancelled = []
        for job in self._manager_instance.list():
            raw = self._raw(job)
            if raw.get("status") not in TERMINAL:
                cancelled.append(self._public(self._manager_instance.cancel(raw["job_id"])))
        return cancelled

    def close(self):
        manager = self._manager_instance
        if manager is None:
            return
        try:
            self.cancel_all()
        finally:
            manager.shutdown(wait=True)
