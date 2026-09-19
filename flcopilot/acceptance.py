"""Strict local recorder/validator for native Windows + FL acceptance evidence.

This module never performs DAW control. It validates observations a human made on
an actual Windows/FL host and can emit a privacy-filtered shareable record.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
RESULTS = {"not_run", "pass", "fail", "blocked"}
REQUIRED_TESTS = (
    "fresh_install", "live_readonly_handshake", "small_fader_pan_rename",
    "loaded_plugin_parameter", "master_track_locks", "stale_project_rejection",
    "native_menu_probe", "empty_track_effect_insertion", "focus_popup_input_refusal",
    "stop_hotkey", "interrupted_write_recovery", "audio_ab_audition",
    "readiness_report", "approved_1db_roundtrip", "mute_stereo_controls",
    "stale_restore_refusal", "privacy_filtered_export", "plugin_workbench_scan",
    "plugin_display_unit_change_restore", "audio_review_level_match",
    "audio_review_decision_persistence",
)
OPTIONAL_TESTS = ("model_vram_latency_underruns",)
PRIVATE_FIELDS = {"midi_endpoint", "interface_and_driver", "midi_provider"}
MAX_RECORD_BYTES = 256 * 1024


class AcceptanceError(ValueError):
    pass


def _text(value: Any, field: str, *, required: bool = False, limit: int = 1000) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise AcceptanceError(f"invalid {field}")
    return value


def validate_record(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AcceptanceError("record must be an object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise AcceptanceError("unsupported schema_version")
    if data.get("status") not in RESULTS:
        raise AcceptanceError("invalid status")
    for field in ("date", "windows_build", "fl_studio_build", "python_version", "postfader_version"):
        _text(data.get(field), field, required=data.get("status") == "pass")
    for field in PRIVATE_FIELDS:
        _text(data.get(field), field)
    scaling = data.get("display_scaling")
    if scaling is not None and (type(scaling) not in (int, float) or not 50 <= scaling <= 500):
        raise AcceptanceError("invalid display_scaling")
    tests = data.get("tests")
    if not isinstance(tests, dict):
        raise AcceptanceError("tests must be an object")
    expected = set(REQUIRED_TESTS) | set(OPTIONAL_TESTS)
    missing = set(REQUIRED_TESTS) - set(tests)
    unknown = set(tests) - expected
    if missing:
        raise AcceptanceError("missing tests: " + ", ".join(sorted(missing)))
    if unknown:
        raise AcceptanceError("unknown tests: " + ", ".join(sorted(unknown)))
    for name, result in tests.items():
        if result not in RESULTS:
            raise AcceptanceError(f"invalid test result: {name}")
    if data["status"] == "pass" and any(tests[name] != "pass" for name in REQUIRED_TESTS):
        raise AcceptanceError("overall pass requires every required test to pass")
    notes = data.get("notes", [])
    if not isinstance(notes, list) or len(notes) > 100:
        raise AcceptanceError("invalid notes")
    for note in notes:
        _text(note, "note", required=True, limit=2000)
    hashes = data.get("evidence_sha256", {})
    if not isinstance(hashes, dict) or len(hashes) > 100:
        raise AcceptanceError("invalid evidence_sha256")
    for name, digest in hashes.items():
        _text(name, "evidence name", required=True, limit=160)
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise AcceptanceError(f"invalid evidence hash: {name}")
    return data


def load_record(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_RECORD_BYTES:
        raise AcceptanceError("record missing or too large")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError("record is not valid JSON") from exc
    return validate_record(data)


def hash_evidence(path: str | Path) -> str:
    path = Path(path)
    if not path.is_file():
        raise AcceptanceError("evidence file missing")
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def public_record(data: Any) -> dict[str, Any]:
    valid = validate_record(data)
    out = {k: v for k, v in valid.items() if k not in PRIVATE_FIELDS}
    out["privacy"] = (
        "MIDI endpoint/provider and audio-interface/driver details omitted. "
        "No project names, local paths, auth tokens, prompts or audio are included by this formatter."
    )
    return out


def write_public_record(data: Any, destination: str | Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(public_record(data), indent=2, sort_keys=True) + "\n"
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(destination)
    return destination
