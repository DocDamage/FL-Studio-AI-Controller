"""Conservative timing evidence, not content identity or sample-accurate alignment."""
import numpy as np
from .contracts import Stopped


def check_stop(stop):
    if stop is not None and stop.is_set():
        raise Stopped("Audio review cancelled; no DAW control was changed")


def timing_evidence(a, b, sr, stop=None):
    """Require equal shape. Positive delay means the candidate arrives later.

    Exact proportional samples provide direct evidence. Otherwise inspect up to
    three 10 ms multichannel energy-envelope windows. Thresholds are conservative
    product heuristics, not calibrated probabilities; no corrective shift is made.
    """
    if a.shape != b.shape:
        raise ValueError("Timing probes require matching channel and frame counts")
    check_stop(stop)
    base = {"content_identity_verified": False, "automatic_shift_applied": False,
            "sample_accurate_alignment_claimed": False, "probe_resolution_ms": 10,
            "max_searched_delay_ms": 500, "probes": []}
    # Chunked sums bound temporary memory. Include both channels to avoid mono
    # cancellation concealing antiphase energy. Negative gain is reported as such.
    aa = ab = bb = 0.
    for start in range(0, len(a), 131072):
        check_stop(stop)
        x, y = a[start:start+131072], b[start:start+131072]
        aa += float(np.sum(x*x)); ab += float(np.sum(x*y)); bb += float(np.sum(y*y))
    if aa > 1e-20 and bb > 1e-20:
        gain = ab/aa
        residual = max(0., bb - ab*ab/aa)/bb
        if residual < 1e-10 and abs(gain) > 1e-12:
            return {**base, "status": "consistent", "basis": "samplewise_proportional",
                    "estimated_delay_ms": 0., "polarity_inverted": gain < 0,
                    "note": "Samples are proportional at the existing positions. This does not prove export provenance."}
    hop = max(1, sr//100)
    count = len(a)//hop
    if count < 300:
        return {**base, "status": "uncertain", "estimated_delay_ms": None,
                "basis": "insufficient_probe_duration", "note": "Use at least three seconds of varying audio for envelope timing checks."}
    envelopes = []
    for signal in (a, b):
        check_stop(stop)
        frames = signal[:count*hop].reshape(count, hop, signal.shape[1])
        # Reduce in bounded groups instead of squaring both full audio arrays.
        energy = np.empty(count)
        for start in range(0, count, 1024):
            check_stop(stop)
            block = frames[start:start+1024]
            energy[start:start+1024] = np.sqrt(np.mean(block*block, axis=(1, 2)))
        envelopes.append(energy)
    x, y = envelopes
    margin, size = 50, min(600, count-100)
    starts = sorted(set(np.linspace(margin, count-margin-size, 3).astype(int).tolist()))
    probes = []
    for start in starts:
        check_stop(stop)
        anchor = x[start:start+size]
        centered = anchor-anchor.mean()
        norm = float(np.linalg.norm(centered))
        if norm < 1e-12 or float(np.std(anchor)) < max(1e-12, float(np.mean(anchor))*.015):
            continue
        scores = []
        for lag in range(-margin, margin+1):
            shifted = y[start+lag:start+lag+size]
            centered_y = shifted-shifted.mean()
            scale = norm*float(np.linalg.norm(centered_y))
            scores.append(float(np.dot(centered, centered_y)/scale) if scale > 1e-20 else -1.)
        best = int(np.argmax(scores)); lag = best-margin
        runner_up = max(score for i, score in enumerate(scores) if abs(i-best) > 2)
        reliable = scores[best] >= .85 and scores[best]-runner_up >= .03 and abs(lag) < margin
        probes.append({"start_seconds": start*hop/sr, "duration_seconds": size*hop/sr,
                       "delay_ms": lag*hop/sr*1000., "correlation": scores[best],
                       "peak_margin": scores[best]-runner_up, "usable": reliable})
    usable = [p for p in probes if p["usable"]]
    # A short render can have one unique window. It must still have a clear peak.
    required = min(2, len(starts))
    status, delay = "uncertain", None
    if len(usable) >= required:
        lags = [p["delay_ms"] for p in usable]
        delay = float(np.median(lags))
        if max(lags)-min(lags) > 20.0001:
            status = "timing_disagreement"
        elif abs(delay) > 10.0001:
            status = "offset_detected"
        elif all(abs(v) <= 10.0001 for v in lags):
            status = "consistent"
    return {**base, "status": status, "basis": "multi_window_energy_envelope",
            "estimated_delay_ms": delay, "probes": probes,
            "note": "Heuristic 10 ms energy probes; periodic, flat or heavily changed audio may be uncertain. No trimming, time shift or resampling is performed."}
