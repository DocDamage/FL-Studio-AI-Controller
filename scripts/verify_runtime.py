"""Exercise a real app process, diagnostics client, and MCP stdio in simulation.

No FL/MIDI device is used. Workspace and private launcher output are temporary.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from flcopilot.mcp_relay import http_call


def main():
    with tempfile.TemporaryDirectory(prefix="flcopilot-runtime-") as tmp:
        workspace = Path(tmp)
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        args = [sys.executable, "-m", "flcopilot", "--demo", "--no-browser", "--port", "0", "--workspace", tmp]
        flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        process = subprocess.Popen(args, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **flags)
        try:
            for _ in range(100):
                if (workspace/"server.json").exists():
                    break
                if process.poll() is not None:
                    raise RuntimeError("App process exited before writing its descriptor")
                time.sleep(.1)
            status = http_call(workspace, "/api/status")
            assert status["demo"] and status["version"] == "0.2.0"
            doctor = subprocess.run([sys.executable, "-m", "flcopilot", "--diagnose", "--workspace", tmp],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=40)
            assert doctor.returncode == 2, "Simulator must never pass live qualification"
            report = json.loads(doctor.stdout)
            assert report["demo"] and not report["live_write_preconditions_ready"] and "local_details" not in report
            assert not http_call(workspace, "/api/history"), "Diagnostics may not create a control plan"
            messages = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "copilot_status", "arguments": {}}},
            ]
            relay = subprocess.run([sys.executable, "-m", "flcopilot", "--mcp", "--workspace", tmp], cwd=ROOT,
                                   env=env, input="\n".join(json.dumps(m) for m in messages)+"\n",
                                   capture_output=True, text=True, timeout=20)
            assert relay.returncode == 0
            replies = [json.loads(line) for line in relay.stdout.splitlines()]
            assert len(replies) == 3 and len(replies[1]["result"]["tools"]) == 12
            assert json.loads(replies[2]["result"]["content"][0]["text"])["demo"]
            summary = {"app_version": status["version"], "app_process": "passed_simulator",
                       "diagnostics_process": "passed; simulator correctly returned not-ready exit 2",
                       "mcp_stdio": "passed; 12 tools; JSON-RPC-only stdout", "diagnostics_control_plans_created": 0,
                       "live_fl_tested": False, "windows_process_tested": os.name == "nt"}
            print(json.dumps(summary, indent=2))
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.send_signal(signal.SIGINT)
                try:
                    process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
