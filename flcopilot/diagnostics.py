"""Read-only readiness with separate environment, bridge and control evidence.

Enumeration opens no MIDI ports. The live handshake uses the app-owned bridge;
no second controller, menu click, or write-mode enable is requested.
Local paths/device names stay in local_details, omitted from exported reports.
"""
from __future__ import annotations
import importlib.metadata as metadata
import os
import re
import struct
import sys
import time
import uuid
from pathlib import Path
from . import __version__
from .assets import atomic_json, file_hash

PACKAGES = ("numpy", "scipy", "soundfile", "pydantic", "pyloudnorm",
            "imageio-ffmpeg", "postfader-fl-studio-mcp", "python-rtmidi", "pywinauto", "psutil")


def match_endpoints(inputs, outputs, selected):
    """Never choose a partial match, an alias, or one of duplicate device names."""
    if not isinstance(selected, str) or not selected.strip():
        return {"status": "missing_selection", "input_matches": 0, "output_matches": 0}
    left = [n for n in inputs if n.casefold() == selected.casefold()]
    right = [n for n in outputs if n.casefold() == selected.casefold()]
    status = "matched" if len(left) == len(right) == 1 else (
        "ambiguous" if len(left) > 1 or len(right) > 1 else "missing_direction")
    return {"status": status, "input_matches": len(left), "output_matches": len(right)}


def midi_inventory():
    instances = []
    try:
        import rtmidi
        incoming = rtmidi.MidiIn()
        instances.append(incoming)
        outgoing = rtmidi.MidiOut()
        instances.append(outgoing)
        # Deliberately do not call open_port/open_virtual_port.
        return {"available": True, "inputs": incoming.get_ports(), "outputs": outgoing.get_ports()}
    except Exception as exc:
        return {"available": False, "inputs": [], "outputs": [], "error": str(exc)[:1000]}
    finally:
        for instance in instances:
            try:
                instance.delete()
            except Exception:
                pass


def collect_environment():
    packages = {}
    for name in PACKAGES:
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    details = {"packages": packages, "python": ".".join(map(str, sys.version_info[:3])),
               "python_bits": struct.calcsize("P") * 8, "platform": sys.platform}
    try:
        from .process import ffmpeg_path
        ffmpeg = Path(ffmpeg_path())
        details["ffmpeg_present"] = ffmpeg.is_file()
        details["ffmpeg_path"] = str(ffmpeg)
    except Exception as exc:
        details["ffmpeg_present"] = False
        details["ffmpeg_error"] = str(exc)[:1000]
    folder, source = None, "unresolved"
    try:
        from fl_studio_mcp.host_config import fl_studio_user_data_selection
        selection = fl_studio_user_data_selection()
        folder, source = selection.path, selection.source
    except Exception:
        explicit = os.environ.get("FL_STUDIO_USER_DATA_DIR")
        if explicit and Path(explicit).is_absolute():
            folder, source = Path(explicit), "environment"
    details["user_data_source"] = source
    details["user_data"] = str(folder) if folder else None
    details["hardware_directory_present"] = bool(folder and (folder/"Settings"/"Hardware").is_dir())
    bridge = folder/"Settings"/"Hardware"/"Universal Bridge"/"device_UniversalBridge.py" if folder else None
    details["bridge_file_present"] = bool(bridge and bridge.is_file())
    if details["bridge_file_present"]:
        try:
            details["bridge_sha256"] = file_hash(bridge)
        except OSError as exc:
            details["bridge_file_present"] = False
            details["bridge_error"] = str(exc)[:1000]
    details["midi"] = midi_inventory()
    details["selected_endpoint"] = os.environ.get("FL_BRIDGE_MIDI_PORT", "")
    details["midi_enabled"] = os.environ.get("FL_BRIDGE_ENABLE_MIDI") == "1"
    return details


def control_evidence(service, session):
    """Report actual receipts, never convert a simulator result into host evidence."""
    rows = service.journal.history(50)
    tests = [r for r in rows if r["plan"].get("purpose") == "control_test"
             and r["plan"].get("session") == session and r["plan"].get("backend") == "postfader"]
    if not tests:
        return {"status": "not_observed", "scope": "last 50 journal plans; current bridge session"}
    test = tests[0]
    restore = next((r for r in rows if r["plan"].get("purpose") == "restore"
                    and r["plan"].get("source_plan_id") == test["id"] and r["status"] == "verified"), None)
    return {"status": "verified_round_trip" if test["status"] == "verified" and restore else
            "verified_reduction_only" if test["status"] == "verified" else "not_completed",
            "test_plan_id": test["id"], "test_status": test["status"],
            "restore_plan_id": restore["id"] if restore else None,
            "scope": "Application readback receipts, not audio-quality, plugin-loading or latency qualification"}


def diagnose(service, environment=None):
    with service.executor.mutex:
        env = collect_environment() if environment is None else environment
        checks = []
        def add(ident, label, status, detail):
            checks.append({"id": ident, "label": label, "status": status, "detail": detail})
        def state(ok):
            return "pass" if ok else "fail"
        runtime_ok = env["python_bits"] == 64 and (3, 11) <= tuple(map(int, env["python"].split(".")[:2])) < (3, 15)
        add("runtime", "64-bit Python runtime", state(runtime_ok),
            "Windows setup targets Python 3.13 x64. Python package range is 3.11–3.14.")
        add("ffmpeg", "Local audio renderer", state(env.get("ffmpeg_present")),
            "A local FFmpeg binary must exist for audio decoding and finishing.")
        add("postfader", "Pinned PostFader distribution", state(env["packages"].get("postfader-fl-studio-mcp") == "10.0.0"),
            "This adapter targets PostFader 10.0.0; install the pinned live requirements with SETUP_WINDOWS.cmd.")
        add("hardware", "FL user-data Hardware directory", state(env.get("hardware_directory_present")),
            "Use the actual FL user-data location, not the FL program directory. Custom paths belong in fl_user_data.")
        add("bridge_file", "Installed Universal Bridge script", state(env.get("bridge_file_present")),
            "Close FL and run CONNECT_FL.cmd to deploy; file presence alone does not prove the script is running.")
        midi = env.get("midi", {})
        match = match_endpoints(midi.get("inputs", []), midi.get("outputs", []), env.get("selected_endpoint"))
        add("midi_inventory", "MIDI device enumeration", state(midi.get("available")),
            "Enumeration only. No device is opened and no MIDI message is sent by this check.")
        add("endpoint", "Exact bidirectional endpoint", state(match["status"] == "matched"),
            {"matched": "One exact input and output were found. FL port assignment still needs checking.",
             "missing_selection": "Select an existing bidirectional endpoint using CONNECT_FL.cmd.",
             "ambiguous": "Duplicate names are unsafe. Give the endpoint a unique name before connecting.",
             "missing_direction": "The configured name is absent from input, output, or both. Partial matches are not selected."}[match["status"]])
        add("midi_enabled", "MIDI bridge enabled in this process", state(env.get("midi_enabled")),
            "START_LIVE.cmd reads the endpoint from local-settings.json before importing PostFader.")
        try:
            connection = service.adapter.connection()
        except Exception as exc:
            connection = {"connected": False, "compatible": False, "error": str(exc)[:1500]}
        live = service.adapter.name == "postfader"
        session = connection.get("session_fingerprint")
        valid_session = isinstance(session, str) and re.fullmatch(r"[a-f0-9]{32}", session) is not None
        read_ready = bool(live and connection.get("connected") is True and connection.get("compatible") is True and valid_session)
        add("handshake", "Compatible live FL handshake", state(read_ready) if live else "not_checked",
            "FL Studio 2026 26.1.3.5336+ and MIDI API 44+ are required by the pinned adapter. Simulator data is not host evidence.")
        provenance = connection.get("bridge_provenance_verified") is True
        epoch = connection.get("project_load_epoch") is True
        gate_closed = connection.get("verified_writes_enabled") is False
        add("provenance", "Running bridge source matches package", state(provenance) if read_ready else "not_checked",
            "A matching live source hash is required before this app can enable writes.")
        add("session_epoch", "Project-load session protection", state(epoch) if read_ready else "not_checked",
            "Reload the matching Universal Bridge script in FL before reconnecting after upgrades.")
        add("write_gate", "Live write gate is closed", state(gate_closed) if read_ready else "not_checked",
            "Close other controllers and disable their write mode. This app will not take over another client's authorization.")
        stopped = service.executor.stop_event.is_set()
        blocked = bool(service.journal.blocked())
        add("stop", "Emergency stop is clear", state(not stopped), "Clear stop only after all in-flight work settles.")
        add("journal", "No unresolved execution outcome", state(not blocked),
            "Unknown outcomes require a fresh inspection and acknowledgment. Acknowledgment is not rollback.")
        ready = bool(read_ready and provenance and epoch and gate_closed and not stopped and not blocked)
        return {"schema_version": "1.0", "application_version": __version__, "observed_at": time.time(),
                "backend": service.adapter.name, "demo": service.adapter.name == "demo",
                "platform": env["platform"], "python": env["python"], "python_bits": env["python_bits"],
                "packages": env["packages"], "checks": checks, "endpoint_match": match,
                "live_read_ready": read_ready, "live_write_preconditions_ready": ready,
                "authorization_granted": False, "project_mutations_dispatched": 0,
                "control_evidence": control_evidence(service, session) if live and read_ready else {"status": "not_observed"},
                "summary": "SIMULATOR — no live-host qualification" if service.adapter.name == "demo" else
                    "Live bridge preconditions ready; exact plan approval still required" if ready else
                    "Live connection needs attention; imported-audio tools remain independent",
                "local_details": {"environment": env, "connection": connection},
                "limitations": ["Readiness is not a Windows end-to-end acceptance test.",
                    "A verified fader round trip does not qualify plugin menus, audio capture, latency, or musical quality.",
                    "No project save, recording, rendering, UI automation, or write-mode enable was requested by diagnostics."]}


def export_report(service, report):
    # Explicit allowlist: never export raw exceptions, paths, device names, project
    # names, prompts, model addresses, auth tokens, or bridge fingerprints.
    allowed = {"schema_version", "application_version", "observed_at", "backend", "demo", "platform",
               "python", "python_bits", "packages", "checks", "endpoint_match", "live_read_ready",
               "live_write_preconditions_ready", "authorization_granted", "project_mutations_dispatched",
               "control_evidence", "summary", "limitations"}
    safe = {key: report[key] for key in allowed}
    safe["privacy"] = "Local paths, endpoint/device names, raw errors, session identifiers and project content omitted. Review before sharing."
    folder = service.assets.exports / uuid.uuid4().hex
    folder.mkdir()
    path = folder / "Connection_Diagnostics.json"
    atomic_json(path, safe)
    return {"report": safe, "files": [service.assets.add_output(path, kind="report")]}
