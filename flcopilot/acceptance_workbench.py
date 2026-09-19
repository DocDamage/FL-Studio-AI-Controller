"""Desktop-only native export checklist; human observations never authorize DAW writes."""
from __future__ import annotations

import copy
import importlib.metadata
import json
import platform
import threading
import uuid
import weakref
from datetime import date
from typing import Any

from pydantic import Field
from .assets import atomic_json
from .contracts import PlanError, Stopped, Strict
from .render_acceptance import REQUIRED_TESTS, public_record, validate_record

EDITABLE = {
    "date", "windows_build", "fl_studio_build", "saved_project_copy_confirmed",
    "project_label", "interface_and_driver", "private_notes", "notes", "tests",
}
CHECKS = dict(zip(REQUIRED_TESTS, (
    "Arm a folder, then manually export one new filename in FL.",
    "Check that the first export appears in the Bounce library.",
    "Analyze the first captured copy successfully.",
    "Arm a different watch and capture a second export with matching settings.",
    "Create a technically ready Audio review of these two captures.",
    "Check that overwriting an existing filename is refused.",
    "Check that two new audio filenames are refused as ambiguous.",
    "Cancel an armed watch and check that intake stops.",
    "Use global Stop during a watch; check it stays latched until reset.",
    "Restart the app; check that the folder is not automatically re-armed.",
    "Verify both stored copies against their saved SHA-256 hashes.",
)))


class DraftEdit(Strict):
    expected_revision: int = Field(ge=1)
    fields: dict[str, Any]
    assets: list[str] = Field(max_length=2)
    review_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class ExportRequest(Strict):
    expected_revision: int = Field(ge=1)
    completed: bool = False
    confirm: bool = False


def runtime(service):
    try:
        version = importlib.metadata.version("postfader-fl-studio-mcp")
    except importlib.metadata.PackageNotFoundError:
        version = None
    return {"app_mode": "demo" if service.adapter.name == "demo" else "live",
            "python_version": platform.python_version(), "postfader_version": version,
            "native_host_eligible": platform.system() == "Windows" and service.adapter.name == "postfader"}


def initial_record():
    return {"schema_version": "1.0", "status": "not_run", "date": date.today().isoformat(),
            "windows_build": None, "fl_studio_build": None, "python_version": None,
            "postfader_version": None, "app_mode": None, "saved_project_copy_confirmed": False,
            "project_label": None, "export_folder": None, "interface_and_driver": None,
            "private_notes": [], "notes": [], "tests": dict.fromkeys(REQUIRED_TESTS, "not_run"),
            "captures": [], "evidence_sha256": {}}


class AcceptanceWorkbench:
    def __init__(self, service):
        self.service = weakref.proxy(service)
        self.path = service.assets.root / "render-acceptance-draft.json"
        self.lock = threading.RLock()
        self.state = {"revision": 1, "record": initial_record(), "assets": [], "review_id": None}
        self.load_error = False
        if self.path.exists():
            try:
                if self.path.stat().st_size > 256 * 1024:
                    raise ValueError("oversized draft")
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if set(loaded) != set(self.state) or type(loaded["revision"]) is not int or loaded["revision"] < 1:
                    raise ValueError("invalid draft")
                validate_record(loaded["record"])
                if loaded["record"]["status"] == "pass" or loaded["record"].get("captures") or loaded["record"].get("evidence_sha256"):
                    raise ValueError("draft cannot contain a completed receipt")
                self._selection(loaded["assets"], loaded["review_id"])
                self.state = loaded
            except (OSError, ValueError, TypeError, KeyError, PlanError):
                # Keep corrupt bytes intact, and keep the rest of the app usable.
                self.load_error = True

    @staticmethod
    def _selection(assets, review_id):
        if (not isinstance(assets, list) or len(assets) > 2 or
                any(not isinstance(a, str) or len(a) != 32 or any(c not in "0123456789abcdef" for c in a) for a in assets) or
                len(set(assets)) != len(assets)):
            raise PlanError("Choose up to two distinct input bounce IDs")
        if review_id is not None and (not isinstance(review_id, str) or len(review_id) != 32 or
                                      any(c not in "0123456789abcdef" for c in review_id)):
            raise PlanError("Invalid review ID")

    def _writable(self, revision):
        if self.load_error:
            raise PlanError("Saved checklist is unreadable. Preserve render-acceptance-draft.json, then move it aside and restart.")
        if revision != self.state["revision"]:
            raise PlanError("Checklist changed in another view. Reload before saving or exporting.")

    def get(self):
        with self.lock:
            out = copy.deepcopy(self.state)
            out.update(runtime=runtime(self.service), checks=copy.deepcopy(CHECKS), load_error=self.load_error)
            return out

    def save(self, data):
        req = DraftEdit.model_validate_json(json.dumps(data))
        if set(req.fields) - EDITABLE:
            raise PlanError("Only checklist observations and private notes are editable")
        self._selection(req.assets, req.review_id)
        with self.lock:
            self._writable(req.expected_revision)
            record = {**copy.deepcopy(self.state["record"]), **copy.deepcopy(req.fields)}
            record.update({k: v for k, v in runtime(self.service).items() if k != "native_host_eligible"})
            record.update(status="not_run", captures=[], evidence_sha256={})
            validate_record(record)
            if "fail" in record["tests"].values():
                record["status"] = "fail"
            elif "blocked" in record["tests"].values():
                record["status"] = "blocked"
            updated = {"revision": self.state["revision"] + 1, "record": record,
                       "assets": req.assets, "review_id": req.review_id}
            if len(json.dumps(updated, indent=2).encode("utf-8")) > 256 * 1024:
                raise PlanError("Checklist is too large; shorten the notes")
            atomic_json(self.path, updated)
            self.state = updated
            return self.get()

    def _stop(self):
        if self.service.executor.stop_event.is_set():
            raise Stopped("Reset Stop before exporting acceptance evidence")

    def _live_session(self):
        s = self.service
        if not runtime(s)["native_host_eligible"]:
            raise PlanError("Completed acceptance requires native Windows and the live PostFader adapter, not demo")
        self._stop()
        with s.executor.mutex:
            if s.executor.running or s.journal.blocked():
                raise PlanError("Settle and reconcile controller work before exporting acceptance")
            connection = s.adapter.connection()
        token = connection.get("session_fingerprint")
        if connection.get("connected") is not True or connection.get("compatible") is not True or not isinstance(token, str) or not token:
            raise PlanError("A connected, compatible live FL session is required")
        return token

    def _evidence(self, state):
        s = self.service
        if len(state["assets"]) != 2 or state["review_id"] is None:
            raise PlanError("Select two separately captured bounces and their ready Audio review")
        captures = []
        for asset in state["assets"]:
            row = s.bounces.get({"asset": asset})
            if row["source"] != "watched" or not row.get("watch_id"):
                raise PlanError("Acceptance requires watched FL exports, not manual imports")
            proof = s.bounces.verify({"asset": asset})
            captures.append({key: proof[key] for key in (
                "asset", "sha256", "bytes", "copied_bytes_verified",
                "render_triggered_by_app", "causal_provenance_verified")})
            captures[-1]["watch_id"] = row["watch_id"]
        review = s.reviews.get(state["review_id"])
        report = review["report"]
        if report["status"] != "ready" or report.get("same_export_range_user_confirmed") is not True:
            raise PlanError("Selected Audio review did not pass same-range technical readiness")
        expected = {c["asset"]: c["sha256"] for c in captures}
        observed = {report["baseline_asset"]: report["baseline_sha256"],
                    report["candidate_asset"]: report["candidate_sha256"]}
        if observed != expected:
            raise PlanError("Audio review does not match the selected capture IDs and hashes")
        files = review["files"]
        reports = [f for f in files if f["kind"] == "report" and f["name"] == "Review_Report.json"]
        if len(reports) != 1:
            raise PlanError("Audio review report is missing or ambiguous")
        expected_files = {f["name"]: f["sha256"] for f in report["level_matched_ab"]["files"]}
        if (len(files) != 3 or len({f["id"] for f in files}) != 3 or
                {f["name"]: f["sha256"] for f in files if f["kind"] == "audio"} != expected_files):
            raise PlanError("Audio review is missing its original level-matched outputs")
        for output in files:
            self._stop()
            s.assets.resolve(output["id"])
            with s.assets.lock:
                stored = s.assets.data[output["id"]]
                if any(stored[k] != output[k] for k in ("kind", "name", "sha256")):
                    raise PlanError("Audio review output identity changed")
        # Bind the stored report to the review database, not just to a filename.
        report_path = s.assets.resolve(reports[0]["id"])
        if json.loads(report_path.read_text(encoding="utf-8")) != report:
            raise PlanError("Audio review report does not match the saved review")
        # Detect a source change while checking the other evidence. This is still
        # point-in-time hashing, not an atomic filesystem snapshot or FL handshake.
        for capture in captures:
            checked = s.bounces.verify({"asset": capture["asset"]})
            if any(checked[k] != capture[k] for k in ("sha256", "bytes")):
                raise PlanError("Captured source changed during acceptance verification")
        return captures, {"Review_Report.json": reports[0]["sha256"]}

    def export(self, data):
        req = ExportRequest.model_validate_json(json.dumps(data))
        if req.confirm is not True:
            raise PlanError("Explicit confirmation is required to export the saved checklist")
        with self.lock:
            self._writable(req.expected_revision)
            self._stop()
            state = copy.deepcopy(self.state)
            record = state["record"]
            record.update({k: v for k, v in runtime(self.service).items() if k != "native_host_eligible"})
            if req.completed:
                session = self._live_session()
                with self.service.audio_lock:
                    record["captures"], record["evidence_sha256"] = self._evidence(state)
                record["status"] = "pass"
                validate_record(record)
                if self._live_session() != session:
                    raise PlanError("FL session changed during evidence export; no acceptance published")
            shared = public_record(record)
            self._stop()
            path = self.service.assets.exports / ("Render_Acceptance_" + uuid.uuid4().hex + ".json")
            try:
                atomic_json(path, shared)
                self._stop()
                output = self.service.assets.add_output(path, kind="report")
            except Exception:
                path.unlink(missing_ok=True)
                path.with_suffix(".json.tmp").unlink(missing_ok=True)
                raise
            # No persisted pass badge: exporting once is not ongoing qualification.
            return {"record": shared, "file": {k: output[k] for k in ("id", "name", "sha256", "kind")},
                    "revision": state["revision"], "project_changed": False,
                    "note": "Human-recorded observations; hashes checked at export, not an independent FL test or rendering authorization."}
