"""Imported-bounce review: measurements, timing checks and attenuation-only A/B.

This module never calls a DAW adapter, executes a plan, or claims artistic quality.
"""
import json
import shutil
import tempfile
import time
import uuid
from pathlib import Path
import numpy as np
import soundfile as sf
from .assets import atomic_json, file_hash
from .audio import _load, decode_supported, measure_array
from .contracts import Plan, PlanError, digest
from .review_alignment import check_stop, timing_evidence

FIELDS = ("integrated_lufs", "oversampled_peak_dbtp_estimate", "crest_db", "stereo_correlation")


def differences(a, b):
    return {key: b[key]-a[key] if a[key] is not None and b[key] is not None else None for key in FIELDS}


def link_evidence(journal, ident):
    if ident is None:
        return None
    row = journal.get(ident)
    plan = Plan.model_validate_json(row["body"])
    result = json.loads(row["result"]) if row["result"] else {}
    receipts = result.get("receipts", [])
    if row["status"] != "verified" or result.get("status") != "verified" or len(receipts) != len(plan.operations):
        raise PlanError("Only a fully verified run can be associated with a review")
    for op, receipt in zip(plan.operations, receipts):
        if (receipt.get("receipt", {}).get("verified") is not True
                or receipt["receipt"].get("session_fingerprint") != plan.session
                or digest(receipt.get("operation")) != digest(op.model_dump(mode="json"))):
            raise PlanError("Associated run receipts do not match the verified plan")
    return {"plan_id": ident, "plan_digest": plan.digest, "backend": plan.backend,
            "operation_count": len(plan.operations), "status": "verified",
            "association": "user_selected_journal_record_only", "audio_provenance_verified": False,
            "causal_effect_verified": False, "current_fl_session_checked": False}


def sections(a, b, sr, seconds, stop):
    width = seconds*sr
    starts = list(range(0, len(a), width))
    if len(starts) > 1 and len(a)-starts[-1] < sr:
        starts.pop()  # Fold a subsecond tail into the preceding measured window.
    result = []
    for i, start in enumerate(starts):
        check_stop(stop)
        end = starts[i+1] if i+1 < len(starts) else len(a)
        left, right = measure_array(a[start:end], sr, stop), measure_array(b[start:end], sr, stop)
        result.append({"start_seconds": start/sr, "end_seconds": end/sr,
                       "baseline": {k: left[k] for k in FIELDS},
                       "candidate": {k: right[k] for k in FIELDS},
                       "candidate_minus_baseline": differences(left, right)})
    return result


def render_pair(a, b, sr, before, after, folder, stop):
    # Never boost either file. Leave 0.2 dB margin under a -1 dB estimated ceiling.
    common = min(before["integrated_lufs"], after["integrated_lufs"],
                 -1.2-max(m["oversampled_peak_dbtp_estimate"]-m["integrated_lufs"] for m in (before, after)))
    rows, paths = [], []
    for label, signal, observed in (("A_Baseline_Matched", a, before), ("B_Candidate_Matched", b, after)):
        check_stop(stop)
        gain = common-observed["integrated_lufs"]
        path = folder/(label+".wav")
        with sf.SoundFile(path, mode="x", samplerate=sr, channels=signal.shape[1], subtype="FLOAT", format="WAV") as output:
            for start in range(0, len(signal), 131072):
                check_stop(stop)
                output.write(signal[start:start+131072] * 10**(gain/20.))
        reread, rate = _load(path)
        if rate != sr or reread.shape != signal.shape:
            raise PlanError("A/B export changed rate, channels or frame count")
        measured = measure_array(reread, rate, stop)
        loud, peak = measured["integrated_lufs"], measured["oversampled_peak_dbtp_estimate"]
        if loud is None or abs(loud-common) > .1 or peak is None or peak > -1.0:
            raise PlanError("Rendered A/B did not pass measured loudness/peak checks; no pair published")
        rows.append({"name": path.name, "sha256": file_hash(path), "gain_db": gain,
                     "measurement": measured})
        paths.append(path)
    if abs(rows[0]["measurement"]["integrated_lufs"]-rows[1]["measurement"]["integrated_lufs"]) > .1:
        raise PlanError("A/B loudness difference exceeds 0.1 LU; no pair published")
    return {"target_lufs": common, "measured_tolerance_lu": .1, "peak_ceiling_dbtp_estimate": -1.,
            "processing": "attenuation_only", "eq_applied": False, "limiting_applied": False,
            "files": rows}, paths


def build_review(assets, request, exports, stop, linked=None):
    """Produce files privately; callers register them only after all checks pass."""
    paths = []
    for ident in (request.baseline, request.candidate):
        records = [a for a in assets.list() if a["id"] == ident and a["kind"] in ("input", "audio")]
        if len(records) != 1:
            raise PlanError("Review inputs must be imported or generated audio assets")
        paths.append(assets.resolve(ident))
    check_stop(stop)
    ident = uuid.uuid4().hex
    folder = Path(exports)/("review_"+ident)
    folder.mkdir()
    try:
        with tempfile.TemporaryDirectory(prefix="flcopilot-review-") as scratch:
            hashes = [file_hash(path) for path in paths]
            signals = [_load(decode_supported(path, scratch, stop)) for path in paths]
            a, sr = signals[0]; b, br = signals[1]
            check_stop(stop)
            before, after = measure_array(a, sr, stop), measure_array(b, br, stop)
            reasons = []
            if sr != br: reasons.append("sample_rate_mismatch")
            if a.shape[1] != b.shape[1]: reasons.append("channel_count_mismatch")
            if len(a) != len(b): reasons.append("frame_count_mismatch")
            if before["integrated_lufs"] is None or after["integrated_lufs"] is None:
                reasons.append("unmeasurable_loudness")
            timing = {"status": "not_checked", "note": "Matching export format and measurable loudness are required."}
            if not reasons:
                timing = timing_evidence(a, b, sr, stop)
                if timing["status"] != "consistent": reasons.append("timing_"+timing["status"])
            report = {"schema_version": "1.0", "app_version": "0.4.0", "review_id": ident,
                      "created": time.time(), "title": request.title, "status": "blocked" if reasons else "ready",
                      "blocked_reasons": reasons, "same_export_range_user_confirmed": True,
                      "baseline_asset": request.baseline, "candidate_asset": request.candidate,
                      "baseline_sha256": hashes[0], "candidate_sha256": hashes[1],
                      "identical_file_bytes": hashes[0] == hashes[1], "baseline": before, "candidate": after,
                      "candidate_minus_baseline": differences(before, after), "timing": timing,
                      "content_alignment_verified": False, "linked_run": linked, "sections": [],
                      "level_matched_ab": None, "source_overwritten": False, "project_changed": False,
                      "subjective_quality_evaluated": False, "automatic_correction_performed": False,
                      "warnings": ["Imported exports only; export provenance and causal effect of a linked run are not verified.",
                                   "Readiness is a technical gate, not proof that either version sounds better.",
                                   "Timing probes are not phase alignment. No input is trimmed, shifted, resampled or time-stretched."]}
            if hashes[0] == hashes[1]:
                report["warnings"].append("Both imported file hashes are identical; this pair contains no byte-level change.")
            output_paths = []
            if not reasons:
                report["sections"] = sections(a, b, sr, request.section_seconds, stop)
                report["level_matched_ab"], output_paths = render_pair(a, b, sr, before, after, folder, stop)
                if timing.get("polarity_inverted"):
                    report["warnings"].append("The candidate is samplewise polarity-inverted relative to the baseline; audition mono compatibility.")
            for path, original in zip(paths, hashes):
                if file_hash(path) != original:
                    raise PlanError("Review source bytes changed during analysis; no result published")
            check_stop(stop)
            report_path = folder/"Review_Report.json"
            atomic_json(report_path, report)
            return report, [*output_paths, report_path], folder
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
