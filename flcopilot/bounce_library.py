"""Persistent input-bounce labels and history; never controls FL or renames audio."""
from __future__ import annotations

import json
import time
from typing import Literal

from pydantic import Field, field_validator
from .assets import atomic_json
from .contracts import PlanError, Strict, Stopped


class BounceQuery(Strict):
    query: str = Field(default="", max_length=120)
    source: Literal["all", "manual", "watched"] = "all"
    offset: int = Field(default=0, ge=0, le=1_000_000)
    limit: int = Field(default=20, ge=1, le=50)


class BounceID(Strict):
    asset: str = Field(pattern=r"^[a-f0-9]{32}$")


class BounceEdit(BounceID):
    expected_revision: int = Field(ge=1)
    label: str = Field(max_length=100)
    note: str = Field(max_length=2000)

    @field_validator("label", "note")
    @classmethod
    def printable(cls, value, info):
        allowed = "\n\t" if info.field_name == "note" else ""
        if any((ord(c) < 32 or ord(c) == 127) and c not in allowed for c in value):
            raise ValueError("Labels and notes must not contain control characters")
        return value.strip()


class BounceLibrary:
    def __init__(self, assets, stop):
        self.assets = assets
        self.stop = stop

    @staticmethod
    def _row(record):
        # Explicit allowlist: neither workspace nor watched folder paths are returned.
        annotation = record.get("annotation", {})
        return {"id": record["id"], "name": record["name"],
                "label": annotation.get("label", ""), "note": annotation.get("note", ""),
                "revision": annotation.get("revision", 1), "sha256": record["sha256"],
                "imported_at": record.get("imported_at"), "bytes": record.get("bytes"),
                "source": "watched" if record.get("source") == "watched_fl_export" else "manual",
                "watch_id": record.get("watch_id"),
                "render_triggered_by_app": False, "causal_provenance_verified": False}

    def _input(self, asset):
        record = self.assets.data.get(asset)
        if record is None or record.get("kind") != "input":
            raise PlanError("Choose an imported input bounce, not a generated output")
        return record

    def list(self, data):
        request = BounceQuery.model_validate_json(json.dumps(data))
        query = request.query.casefold().strip()
        with self.assets.lock:
            # Manifest insertion order records import order, even for old inputs
            # whose timestamps are unknown. Editing labels does not reorder them.
            rows = [self._row(r) for r in reversed(list(self.assets.data.values()))
                    if r.get("kind") == "input"]
        rows = [r for r in rows if (request.source == "all" or r["source"] == request.source)
                and (not query or query in "\n".join([r["name"], r["label"], r["note"]]).casefold())]
        end = request.offset + request.limit
        return {"items": rows[request.offset:end], "total": len(rows), "offset": request.offset,
                "next_offset": end if end < len(rows) else None,
                "integrity": "Not rechecked by listing. Verify or analyze a selected copy."}

    def get(self, data):
        request = BounceID.model_validate_json(json.dumps(data))
        with self.assets.lock:
            return self._row(self._input(request.asset))

    def edit(self, data):
        request = BounceEdit.model_validate_json(json.dumps(data))
        with self.assets.lock:
            original = self._input(request.asset)
            revision = original.get("annotation", {}).get("revision", 1)
            if revision != request.expected_revision:
                raise PlanError("Bounce notes changed in another view. Reopen the bounce before saving.")
            record = {**original, "annotation": {"label": request.label, "note": request.note,
                                                 "revision": revision + 1}}
            updated = {**self.assets.data, request.asset: record}
            # Only metadata is replaced atomically. Source and copied audio stay untouched.
            atomic_json(self.assets.manifest, updated)
            self.assets.data = updated
            return self._row(record)

    def verify(self, data):
        request = BounceID.model_validate_json(json.dumps(data))
        with self.assets.lock:
            row = self._row(self._input(request.asset))
        if self.stop.is_set():
            raise Stopped("Reset Stop before verifying a bounce")
        try:
            path = self.assets.resolve(request.asset)  # Rehash the actual stored copy.
            size = path.stat().st_size
        except (OSError, PlanError) as exc:
            raise PlanError("Stored bounce is missing, changed, or unreadable. Import a fresh copy.") from exc
        if self.stop.is_set():
            raise Stopped("Bounce verification cancelled")
        return {"asset": row["id"], "sha256": row["sha256"], "bytes": size,
                "verified_at": time.time(), "copied_bytes_verified": True,
                "render_triggered_by_app": False, "causal_provenance_verified": False}
