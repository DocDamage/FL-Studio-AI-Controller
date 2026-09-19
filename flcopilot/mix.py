"""A conservative, explicitly limited first mix workflow: peak-aware gain staging."""
from __future__ import annotations
import math
from .contracts import Operation, PrepareRequest, NotDispatched
from .executor import stable_track

def propose_gain_staging(executor,request):
    if executor.stop_event.is_set(): raise NotDispatched("Stop is latched")
    observation=executor.adapter.observe_peaks(request.tracks,request.seconds,executor.stop_event)
    changes=[]
    original={t["index"]:t for t in observation["before"]["tracks"]}
    for track in request.tracks:
        if track==0 or track in executor.locks.tracks: continue
        old=original.get(track)
        if old is None: raise NotDispatched(f"Track {track} was not observed")
        if stable_track(executor.adapter.track(track))!=stable_track(old):
            raise NotDispatched("A fader/target changed during measurement. No plan created.")
        peak=observation["peaks"].get(str(track),0.)
        if not math.isfinite(peak) or peak<0: raise NotDispatched("Invalid meter value")
        if peak<=1e-7 or old.get("muted") or old.get("volume_db") is None: continue
        measured=20*math.log10(peak)
        cut=min(0.,request.target_peak_db-measured)
        cut=max(-request.max_cut_db,cut)
        target=max(-60.,float(old["volume_db"])+cut)
        if cut<-.2:
            changes.append(Operation(kind="volume",track=track,value=round(target,2),
                reason=f"Sampled peak {measured:.1f} dBFS; conservative reduction {cut:.1f} dB."))
    if not changes:
        return {"plan":None,"observation":observation,"message":"No high-confidence attenuation needed. Play a representative loud section when measuring.",
                "scope":"Gain staging only; not a tonal, masking, or full artistic mix."}
    if executor.adapter.connection().get("session_fingerprint")!=observation["session"]:
        raise NotDispatched("Session changed during metering")
    plan=executor.prepare(PrepareRequest(operations=tuple(changes),title="Mix this beat • conservative gain staging"))
    return {"plan":plan,"observation":observation,"scope":"Only attenuates selected non-master faders; sampled meters can miss transients. No EQ, timing, notes, or routing changes."}
