"""Reuse the running app rather than starting a competing PostFader/MIDI owner."""
from __future__ import annotations
import json
import sys
import time
from .mcp_relay import http_call


def check_running_app(workspace):
    try:
        queued = http_call(workspace, "/api/diagnostics", {"export": True})
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            result = http_call(workspace, "/api/jobs/" + queued["job"])
            if result["status"] == "error":
                raise RuntimeError(result["error"])
            if result["status"] == "complete":
                report = result["result"]["report"]
                print(json.dumps(report, indent=2, allow_nan=False))
                print("A privacy-filtered JSON report is in this workspace's exports directory.", file=sys.stderr)
                return 0 if report["live_write_preconditions_ready"] else 2
            time.sleep(.2)
        raise TimeoutError("No diagnostic result before the deadline; inspect the running app. No write was requested.")
    except Exception as exc:
        print("Connection check failed: " + str(exc), file=sys.stderr)
        print("Start START_LIVE.cmd first. This command will not open another MIDI connection.", file=sys.stderr)
        return 2
