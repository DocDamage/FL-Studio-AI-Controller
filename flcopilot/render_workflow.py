"""Single-flight export intake. Folder consent belongs to the desktop UI, not MCP."""
from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Literal

from pydantic import Field, field_validator
from .contracts import PlanError, Stopped, Strict
from .render_intake import import_render, snapshot_folder, verify_folder, wait_for_render


class WatchRequest(Strict):
    folder: str = Field(min_length=1, max_length=4096)
    timeout: int = Field(default=120, ge=5, le=600)
    confirm_folder: Literal[True]

    @field_validator("confirm_folder", mode="before")
    @classmethod
    def confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit folder consent requires boolean true")
        return value

    @field_validator("folder")
    @classmethod
    def clean_folder(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Choose a nonblank local folder path without control characters")
        return value


class WatchID(Strict):
    watch_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class WatchStop:
    """A local cancellation must not stop unrelated work; global Stop stops both."""
    def __init__(self, global_stop):
        self.local = threading.Event()
        self.global_stop = global_stop

    def is_set(self):
        return self.local.is_set() or self.global_stop.is_set()

    def wait(self, seconds):
        until = time.monotonic() + seconds
        while not self.is_set():
            remaining = until - time.monotonic()
            if remaining <= 0:
                return False
            self.local.wait(min(remaining, .05))
        return True


class RenderWorkflow:
    ACTIVE = {"queued", "watching", "importing"}

    def __init__(self, assets, jobs, global_stop):
        self.assets = assets
        self.jobs = jobs
        self.global_stop = global_stop
        self.lock = threading.RLock()
        self.row = None
        self.stop = None

    def status(self):
        with self.lock:
            # Serialized copy: callers cannot mutate current state or provenance.
            return {"watch": json.loads(json.dumps(self.row)),
                    "render_triggered_by_app": False, "folder_selection": "desktop_only"}

    def start(self, data):
        request = WatchRequest.model_validate_json(json.dumps(data))
        with self.lock:
            if self.global_stop.is_set():
                raise Stopped("Reset the latched Stop before arming a render watch")
            if self.row and self.row["status"] in self.ACTIVE:
                raise PlanError("A render watch is already active; cancel it or let it finish")
            # Synchronous baseline: files exported after the response cannot be
            # swallowed by a queued worker taking its initial snapshot too late.
            baseline = snapshot_folder(request.folder)
            if self.global_stop.is_set():
                raise Stopped("Render watch cancelled")
            deadline = time.monotonic() + request.timeout
            previous = self.row
            stop = WatchStop(self.global_stop)
            self.stop = stop
            self.row = {"watch_id": uuid.uuid4().hex, "job": None, "status": "queued",
                        "created": time.time(), "timeout": request.timeout,
                        "result": None, "error": None, "cancel_requested": False}
            try:
                job = self.jobs.submit("Waiting for one new manual FL export",
                    lambda: self._run(request, baseline, stop, deadline))
            except Exception:
                self.row = previous
                raise
            self.row["job"] = job["job"]
            return {**job, "watch_id": self.row["watch_id"], "render_triggered_by_app": False}

    def _run(self, request, baseline, stop, deadline):
        try:
            with self.lock:
                self.row["status"] = "watching"
                watch_id = self.row["watch_id"]
            remaining = deadline - time.monotonic()
            if remaining < 1:
                raise PlanError("Render watch expired while queued; arm it again")
            path, stamp = wait_for_render(request.folder, baseline, stop, timeout=remaining)
            with self.lock:
                self.row["status"] = "importing"
            record = import_render(self.assets, path, stamp, stop=stop,
                                   metadata={"watch_id": watch_id},
                                   folder_guard=lambda: verify_folder(request.folder, baseline, path.name, stamp))
            with self.lock:
                self.row.update(status="complete", result=record, finished=time.time())
            return record
        except Exception as exc:
            cancelled = isinstance(exc, Stopped) or stop.is_set()
            # No unexpected exception can expose a local path through MCP status.
            message = ("Render watch cancelled" if cancelled else str(exc)
                       if isinstance(exc, PlanError) else "Render intake failed; no result was promoted")
            with self.lock:
                self.row.update(status="cancelled" if cancelled else "error",
                                error=message, finished=time.time())
            raise PlanError(message) from exc

    def cancel(self, data):
        request = WatchID.model_validate_json(json.dumps(data))
        with self.lock:
            if not self.row or request.watch_id != self.row["watch_id"]:
                raise PlanError("That render watch is no longer current")
            if self.row["status"] in self.ACTIVE:
                self.row["cancel_requested"] = True
                self.stop.local.set()
            return self.status()
