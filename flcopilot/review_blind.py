"""Server-side blind A/B/X listening trials over verified review outputs only."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .assets import MAX_UPLOAD
from .contracts import PlanError, Stopped

NAMES = ("A_Baseline_Matched.wav", "B_Candidate_Matched.wav", "Review_Report.json")


def _stop(stop):
    if stop is not None and stop.is_set():
        raise Stopped("Blind listening review cancelled")


def _hash(path: Path, stop, limit: int) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            _stop(stop)
            total += len(block)
            if total > limit:
                raise PlanError("Review output grew beyond the blind-listening size bound")
            digest.update(block)
    _stop(stop)
    return digest.hexdigest()


def _verified_path(assets, row, stop):
    _stop(stop)
    with assets.lock:
        stored = copy.deepcopy(assets.data.get(row["id"]))
    if not stored or any(stored.get(k) != row.get(k) for k in ("id", "name", "kind", "sha256", "path")):
        raise PlanError("Review output identity changed; rebuild the review before a blind trial")
    path = assets.resolve(row["id"], verify=False)
    limit = 2 * 1024 * 1024 if row["kind"] == "report" else MAX_UPLOAD
    if not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise PlanError("Review output is missing or exceeds the blind-listening size bound")
    if _hash(path, stop, limit) != row["sha256"]:
        raise PlanError("Review output bytes changed; blind listening was refused")
    return path


def verified_paths(assets, review, stop=None):
    """Verify the saved ready review and return paths without exposing them publicly."""
    _stop(stop)
    report = review["report"]
    if report.get("status") != "ready" or report.get("review_id") != review.get("review_id"):
        raise PlanError("Open a technically ready Audio review before starting blind listening")
    files = review["files"]
    if (len(files) != 3 or len({f["id"] for f in files}) != 3 or
            {f["name"] for f in files} != set(NAMES)):
        raise PlanError("Review is missing its original three output files")
    by_name = {f["name"]: copy.deepcopy(f) for f in files}
    measured = report.get("level_matched_ab") or {}
    measurements = measured.get("files", [])
    if len(measurements) != 2 or {row["name"] for row in measurements} != set(NAMES[:2]):
        raise PlanError("Review is missing measured audition output identities")
    paths = {}
    for name in NAMES:
        row = by_name[name]
        expected_kind = "report" if name == NAMES[2] else "audio"
        if row["kind"] != expected_kind:
            raise PlanError("Invalid review output kind")
        paths[name] = _verified_path(assets, row, stop)
    if json.loads(paths[NAMES[2]].read_text(encoding="utf-8")) != report:
        raise PlanError("Stored report does not match the saved review")
    for name in NAMES[:2]:
        measurement = next(row for row in measurements if row["name"] == name)
        if by_name[name]["sha256"] != measurement["sha256"]:
            raise PlanError("Audition output hash does not match its measured report")
    return {"baseline": paths[NAMES[0]], "candidate": paths[NAMES[1]]}


def blind_file(assets, reviews, trial_id, sample, stop=None):
    if sample not in ("a", "b", "x"):
        raise PlanError("Blind sample must be a, b or x")
    trial = reviews.blind_internal(trial_id)
    review = reviews.get(trial["review_id"])
    paths = verified_paths(assets, review, stop)
    a_side = trial["a_side"]
    b_side = "candidate" if a_side == "baseline" else "baseline"
    side = a_side if sample == "a" else b_side if sample == "b" else (
        a_side if trial["x_sample"] == "a" else b_side)
    return paths[side]
