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
            assert status["demo"] and status["version"] == "0.5.0"
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
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "copilot_plugin_scan", "arguments": {"track":6,"slot":0,"start":2048}}},
            ]
            relay = subprocess.run([sys.executable, "-m", "flcopilot", "--mcp", "--workspace", tmp], cwd=ROOT,
                                   env=env, input="\n".join(json.dumps(m) for m in messages)+"\n",
                                   capture_output=True, text=True, timeout=20)
            assert relay.returncode == 0
            replies = [json.loads(line) for line in relay.stdout.splitlines()]
            assert len(replies) == 4 and len(replies[1]["result"]["tools"]) == 19
            assert json.loads(replies[2]["result"]["content"][0]["text"])["demo"]
            scan_job = json.loads(replies[3]["result"]["content"][0]["text"])
            for _ in range(100):
                scan = http_call(workspace, "/api/jobs/"+scan_job["job"])
                if scan["status"] == "complete": break
                if scan["status"] == "error": raise RuntimeError(scan["error"])
                time.sleep(.05)
            assert scan["status"] == "complete" and scan["result"]["parameters"][0]["index"] == 2049
            assert not http_call(workspace, "/api/history")
            # Import two synthetic exports through the real authenticated HTTP app.
            import io
            import urllib.request
            import numpy as np
            import soundfile as sf
            from flcopilot.planner import NoRedirect
            info = json.loads((workspace/"server.json").read_text())
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            fixture = np.random.default_rng(91).normal(size=(24000, 2))*.04
            inputs = []
            for samples in (fixture, fixture*.5):
                stream = io.BytesIO()
                sf.write(stream, samples, 8000, format="WAV", subtype="FLOAT")
                request = urllib.request.Request(info["origin"]+"/api/import", data=stream.getvalue(),
                    headers={"Authorization":"Bearer "+info["token"], "Content-Type":"application/octet-stream",
                             "X-Filename":"Synthetic_Bounce.wav"})
                with opener.open(request, timeout=10) as response:
                    inputs.append(json.load(response)["id"])
            review_job = http_call(workspace, "/api/review-audio", {
                "baseline":inputs[0], "candidate":inputs[1], "confirm_same_range":True})
            for _ in range(400):
                result = http_call(workspace, "/api/jobs/"+review_job["job"])
                if result["status"] == "complete": break
                if result["status"] == "error": raise RuntimeError(result["error"])
                time.sleep(.05)
            assert result["status"] == "complete"
            review = result["result"]
            assert review["report"]["status"] == "ready" and len(review["files"]) == 3
            assert review["decision"] == "undecided"
            decision = http_call(workspace, "/api/review-decision", {
                "review_id":review["review_id"], "expected_revision":1,
                "decision":"needs_revision", "note":"Synthetic process test; not an artistic judgment"})
            assert decision["revision"] == 2 and not http_call(workspace, "/api/history")
            summary = {"app_version": status["version"], "app_process": "passed_simulator",
                       "diagnostics_process": "passed; simulator correctly returned not-ready exit 2",
                       "mcp_stdio": "passed; 19 tools; JSON-RPC-only stdout", "diagnostics_control_plans_created": 0,
                       "plugin_scan_via_mcp_process": "passed; observed high index 2049, no control plans created",
                       "audio_review_process": "passed; real WAV imports, 3 outputs and persisted decision; zero DAW plans",
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
