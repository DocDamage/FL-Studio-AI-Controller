"""Strict validator for native Windows/FL manual-export acceptance evidence.

This module never controls FL Studio and never starts a render. It validates a
human-recorded native session and can emit a privacy-filtered shareable record.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
RESULTS = {"not_run", "pass", "fail", "blocked"}
REQUIRED_TESTS = (
    "arm_watch_new_filename",
    "capture_first_export",
    "analyze_first_capture",
    "capture_second_export",
    "same_range_review_ready",
    "overwrite_refusal",
    "multiple_new_files_refusal",
    "cancel_watch",
    "global_stop_watch",
    "restart_requires_rearm",
    "stored_copy_hash_recheck",
)
PRIVATE_FIELDS = {"project_label", "export_folder", "interface_and_driver", "private_notes"}
RECORD_FIELDS = {
    "schema_version", "status", "date", "windows_build", "fl_studio_build",
    "python_version", "postfader_version", "app_mode", "saved_project_copy_confirmed",
    "project_label", "export_folder", "interface_and_driver", "private_notes",
    "tests", "captures", "notes", "evidence_sha256", "privacy",
}
PRIVACY_NOTICE = (
    "Private host fields omitted. User-entered notes, version text and evidence names "
    "remain; review these before sharing. No audio or project contents are attached."
)
LEGACY_PRIVACY_NOTICE = (
    "Project label, export folder, interface/driver and private notes omitted. "
    "No local paths, auth tokens, project contents or audio are included by this formatter."
)
MAX_RECORD_BYTES = 256 * 1024
MAX_CAPTURE_BYTES = 300 * 1024 * 1024


class RenderAcceptanceError(ValueError):
    pass


def _text(value: Any, field: str, *, required: bool = False, limit: int = 2000) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise RenderAcceptanceError(f"invalid {field}")
    return value


def _hex(value: Any, field: str, length: int) -> str:
    if not isinstance(value, str) or len(value) != length or any(c not in "0123456789abcdef" for c in value):
        raise RenderAcceptanceError(f"invalid {field}")
    return value


def _capture(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RenderAcceptanceError(f"capture {index} must be an object")
    allowed = {
        "asset", "watch_id", "sha256", "bytes", "copied_bytes_verified",
        "render_triggered_by_app", "causal_provenance_verified",
    }
    unknown = set(value) - allowed
    if unknown:
        raise RenderAcceptanceError(
            f"unknown capture fields: {', '.join(sorted(unknown))}"
        )
    _hex(value.get("asset"), f"capture {index} asset", 32)
    _hex(value.get("watch_id"), f"capture {index} watch_id", 32)
    _hex(value.get("sha256"), f"capture {index} sha256", 64)
    size = value.get("bytes")
    if type(size) is not int or not 1 <= size <= MAX_CAPTURE_BYTES:
        raise RenderAcceptanceError(f"invalid capture {index} bytes")
    if type(value.get("copied_bytes_verified")) is not bool:
        raise RenderAcceptanceError(f"invalid capture {index} copied_bytes_verified")
    if value.get("render_triggered_by_app") is not False:
        raise RenderAcceptanceError(
            f"capture {index} must record render_triggered_by_app false"
        )
    if value.get("causal_provenance_verified") is not False:
        raise RenderAcceptanceError(
            f"capture {index} cannot claim causal provenance"
        )
    return value


def validate_record(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RenderAcceptanceError("record must be an object")
    if set(data) - RECORD_FIELDS:
        raise RenderAcceptanceError("unknown record fields")
    if "privacy" in data and data["privacy"] not in (PRIVACY_NOTICE, LEGACY_PRIVACY_NOTICE):
        raise RenderAcceptanceError("invalid privacy notice")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise RenderAcceptanceError("unsupported schema_version")
    if not isinstance(data.get("status"), str) or data["status"] not in RESULTS:
        raise RenderAcceptanceError("invalid status")

    passing = data["status"] == "pass"
    for field in ("date", "windows_build", "fl_studio_build", "python_version", "postfader_version"):
        _text(data.get(field), field, required=passing, limit=160)

    app_mode = data.get("app_mode")
    if app_mode not in (None, "live", "demo"):
        raise RenderAcceptanceError("invalid app_mode")
    if passing and app_mode != "live":
        raise RenderAcceptanceError("overall pass requires app_mode live")

    saved = data.get("saved_project_copy_confirmed")
    if saved is not None and type(saved) is not bool:
        raise RenderAcceptanceError("invalid saved_project_copy_confirmed")
    if passing and saved is not True:
        raise RenderAcceptanceError("overall pass requires a saved disposable project copy")

    for field in ("project_label", "export_folder", "interface_and_driver"):
        _text(data.get(field), field, limit=1000)
    private_notes = data.get("private_notes", [])
    if not isinstance(private_notes, list) or len(private_notes) > 100:
        raise RenderAcceptanceError("invalid private_notes")
    for note in private_notes:
        _text(note, "private note", required=True, limit=2000)

    tests = data.get("tests")
    if not isinstance(tests, dict):
        raise RenderAcceptanceError("tests must be an object")
    missing = set(REQUIRED_TESTS) - set(tests)
    unknown = set(tests) - set(REQUIRED_TESTS)
    if missing:
        raise RenderAcceptanceError("missing tests: " + ", ".join(sorted(missing)))
    if unknown:
        raise RenderAcceptanceError("unknown tests: " + ", ".join(sorted(unknown)))
    for name, result in tests.items():
        if not isinstance(result, str) or result not in RESULTS:
            raise RenderAcceptanceError(f"invalid test result: {name}")
    if passing and any(tests[name] != "pass" for name in REQUIRED_TESTS):
        raise RenderAcceptanceError("overall pass requires every required render test to pass")

    captures = data.get("captures", [])
    if not isinstance(captures, list) or len(captures) > 10:
        raise RenderAcceptanceError("invalid captures")
    for index, capture in enumerate(captures, start=1):
        _capture(capture, index)
    if passing:
        if len(captures) < 2:
            raise RenderAcceptanceError("overall pass requires at least two verified captures")
        if len({row["asset"] for row in captures}) != len(captures):
            raise RenderAcceptanceError("capture asset IDs must be unique")
        if len({row["watch_id"] for row in captures}) != len(captures):
            raise RenderAcceptanceError("each accepted export must come from a separately armed watch")
        if any(row["copied_bytes_verified"] is not True for row in captures):
            raise RenderAcceptanceError("overall pass requires current-byte verification for every capture")

    notes = data.get("notes", [])
    if not isinstance(notes, list) or len(notes) > 100:
        raise RenderAcceptanceError("invalid notes")
    for note in notes:
        _text(note, "note", required=True, limit=2000)

    hashes = data.get("evidence_sha256", {})
    if not isinstance(hashes, dict) or len(hashes) > 100:
        raise RenderAcceptanceError("invalid evidence_sha256")
    for name, digest in hashes.items():
        _text(name, "evidence name", required=True, limit=160)
        _hex(digest, f"evidence hash: {name}", 64)

    return data


def load_record(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_RECORD_BYTES:
        raise RenderAcceptanceError("record missing or too large")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RenderAcceptanceError("record is not valid JSON") from exc
    return validate_record(data)


def hash_evidence(path: str | Path) -> str:
    path = Path(path)
    if not path.is_file():
        raise RenderAcceptanceError("evidence file missing")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def public_record(data: Any) -> dict[str, Any]:
    valid = validate_record(data)
    out = {key: copy.deepcopy(value) for key, value in valid.items()
           if key in RECORD_FIELDS - PRIVATE_FIELDS}
    out["privacy"] = PRIVACY_NOTICE
    return out


def write_public_record(data: Any, destination: str | Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(public_record(data), indent=2, sort_keys=True) + "\n"
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(destination)
    return destination
