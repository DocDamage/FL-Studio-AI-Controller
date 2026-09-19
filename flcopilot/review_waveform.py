"""Bounded, read-only peak envelopes of the original level-matched review WAVs."""
from __future__ import annotations

import copy
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from pydantic import Field

from .assets import MAX_UPLOAD
from .audio import MAX_SAMPLES, MAX_SECONDS
from .contracts import PlanError, Stopped
from .review_contracts import ReviewID

MAX_READ_FRAMES = 65_536
NAMES = ("A_Baseline_Matched.wav", "B_Candidate_Matched.wav", "Review_Report.json")


class WaveformRequest(ReviewID):
    bins: int = Field(default=800, ge=64, le=2048)


def _stop(stop):
    if stop is not None and stop.is_set():
        raise Stopped("Waveform preview cancelled")


def _hash(path: Path, stop, limit: int) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            _stop(stop)
            total += len(block)
            if total > limit:
                raise PlanError("Review output grew beyond the preview size bound")
            digest.update(block)
    _stop(stop)
    return digest.hexdigest()


def _verified_path(assets, row, stop):
    """Bind saved review identity to both the current manifest and current bytes."""
    _stop(stop)
    with assets.lock:
        stored = copy.deepcopy(assets.data.get(row["id"]))
    if not stored or any(stored.get(k) != row.get(k) for k in ("id", "name", "kind", "sha256", "path")):
        raise PlanError("Review output identity changed; reopen or rebuild the review")
    path = assets.resolve(row["id"], verify=False)
    limit = 2 * 1024 * 1024 if row["kind"] == "report" else MAX_UPLOAD
    if not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise PlanError("Review output is missing or exceeds the preview size bound")
    if _hash(path, stop, limit) != row["sha256"]:
        raise PlanError("Review output bytes changed; no waveform published")
    return path


def _envelope(path, expected, bins, stop):
    """Cover every frame once, preserving independent mono/stereo extrema."""
    with sf.SoundFile(str(path), mode="r") as source:
        frames, channels, rate = source.frames, source.channels, source.samplerate
        if (channels not in (1, 2) or not 8000 <= rate <= 192000 or frames < rate or
                frames > rate * MAX_SECONDS or frames * channels > MAX_SAMPLES):
            raise PlanError("Waveform exceeds the mono/stereo, duration or sample-count bound")
        if source.format != "WAV" or source.subtype != "FLOAT":
            raise PlanError("Waveform requires the original float WAV audition outputs")
        actual = {"frames": frames, "channels": channels, "sample_rate": rate}
        if any(type(expected.get(k)) is not int or expected[k] != v for k, v in actual.items()):
            raise PlanError("Review output format no longer matches its measured report")
        edges = [i * frames // bins for i in range(bins + 1)]
        rows = [{"min": [], "max": [], "rms": []} for _ in range(channels)]
        for start, end in zip(edges, edges[1:]):
            minimum, maximum = np.full(channels, np.inf), np.full(channels, -np.inf)
            energy = np.zeros(channels, dtype=np.float64)
            remaining = end - start
            while remaining:
                _stop(stop)
                count = min(remaining, MAX_READ_FRAMES)
                block = source.read(count, dtype="float32", always_2d=True)
                if len(block) != count:
                    raise PlanError("Review output ended during waveform reading")
                if not np.isfinite(block).all():
                    raise PlanError("Review output contains non-finite audio")
                minimum = np.minimum(minimum, block.min(axis=0))
                maximum = np.maximum(maximum, block.max(axis=0))
                energy += np.square(block, dtype=np.float64).sum(axis=0)
                remaining -= count
            rms = np.sqrt(energy / (end - start))
            for channel, row in enumerate(rows):
                for key, values in (("min", minimum), ("max", maximum), ("rms", rms)):
                    row[key].append(float(values[channel]))
        _stop(stop)
        return actual, edges, rows


def build_waveforms(assets, review, bins, stop=None):
    """No cache, file publication, DAW calls, remeasurement or preference changes."""
    _stop(stop)
    # Keep this callable strict even outside the HTTP/service entrypoint.
    request = WaveformRequest(review_id=review["review_id"], bins=bins)
    report = review["report"]
    if report.get("status") != "ready" or report.get("review_id") != request.review_id:
        raise PlanError("Open a technically ready Audio review before requesting waveforms")
    files = review["files"]
    if (len(files) != 3 or len({f["id"] for f in files}) != 3 or
            {f["name"] for f in files} != set(NAMES)):
        raise PlanError("Review is missing its original three output files")
    by_name = {f["name"]: copy.deepcopy(f) for f in files}
    measured = report.get("level_matched_ab") or {}
    measurements = measured.get("files", [])
    if len(measurements) != 2 or {r["name"] for r in measurements} != set(NAMES[:2]):
        raise PlanError("Review is missing its measured audition output identities")
    paths = {}
    for name in NAMES:
        row = by_name[name]
        if row["kind"] != ("report" if name == NAMES[2] else "audio"):
            raise PlanError("Invalid review output kind")
        paths[name] = _verified_path(assets, row, stop)
    if json.loads(paths[NAMES[2]].read_text(encoding="utf-8")) != report:
        raise PlanError("Stored report does not match the saved review")
    sides, metadata, frame_edges = {}, None, None
    for side, name in zip(("a", "b"), NAMES[:2]):
        measurement = next(r for r in measurements if r["name"] == name)
        row = by_name[name]
        if row["sha256"] != measurement["sha256"]:
            raise PlanError("Audition output hash does not match its measured report")
        current, edges, channels = _envelope(paths[name], measurement["measurement"], request.bins, stop)
        if metadata is not None and current != metadata:
            raise PlanError("A/B waveform formats differ")
        metadata, frame_edges = current, edges
        sides[side] = {"asset": row["id"], "sha256": row["sha256"], "channels": channels}
    # A change while processing the other side invalidates the entire preview.
    for name in NAMES:
        if _verified_path(assets, by_name[name], stop) != paths[name]:
            raise PlanError("Review output location changed during waveform processing")
    _stop(stop)
    return {"schema_version": "1.0", "review_id": request.review_id, **metadata,
            "duration_seconds": metadata["frames"] / metadata["sample_rate"],
            "bin_count": request.bins, "frame_edges": frame_edges, "sides": sides,
            "amplitude_units": "linear_digital_full_scale", "independent_normalization": False,
            "basis": "original_level_matched_review_outputs", "checked_at": time.time(),
            "project_changed": False, "source_inputs_reverified": False,
            "note": "Per-channel min/max and RMS summaries, not sample-level alignment or a quality score. "
                    "Output bytes checked now; original input bounces were not reverified."}
