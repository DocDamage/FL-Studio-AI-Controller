"""Measured audio, conservative finishing, and real level-matched export files.

LUFS uses pyloudnorm's gated BS.1770 implementation. Oversampled peaks are an
estimate, NOT a certified true-peak meter. No RMS value is labeled LUFS.
"""
from __future__ import annotations
import json
import math
import re
import tempfile
import uuid
from pathlib import Path
import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy.signal import resample_poly, welch
from .assets import atomic_json, file_hash
from .contracts import PlanError, Stopped
from .process import ffmpeg_path, run_owned

MAX_SAMPLES=24_000_000
MAX_SECONDS=600

def db(value):
    return float(20.*math.log10(value)) if value>1e-15 else None

def _load(path):
    info=sf.info(str(path))
    if info.channels not in (1,2): raise PlanError("v0.1 accepts mono/stereo only; multichannel audio is not downmixed silently.")
    if not 8000<=info.samplerate<=192000: raise PlanError("Unsupported sample rate")
    if info.frames<info.samplerate: raise PlanError("At least one second is required for audio analysis")
    if info.duration>MAX_SECONDS or info.frames*info.channels>MAX_SAMPLES:
        raise PlanError("Audio exceeds the 10-minute / 24-million-sample analysis bound; select a shorter render.")
    y,sr=sf.read(str(path),dtype="float64",always_2d=True)
    if not np.isfinite(y).all(): raise PlanError("Audio contains NaN or infinity")
    return y,sr

def decode_supported(path,scratch,stop=None):
    path=Path(path)
    try: sf.info(str(path)); return path
    except (RuntimeError,sf.LibsndfileError): pass
    demux={".mp3":"mp3",".m4a":"mov",".aac":"aac"}.get(path.suffix.lower())
    if not demux: raise PlanError("Unsupported or malformed audio file")
    out=Path(scratch)/(uuid.uuid4().hex+".wav")
    run_owned([ffmpeg_path(),"-hide_banner","-nostdin","-v","error","-n",
        "-protocol_whitelist","file,pipe","-f",demux,"-i",str(path),
        "-map","0:a:0","-vn","-t",str(MAX_SECONDS+1),"-fs","100000000","-c:a","pcm_f32le",str(out)],stop=stop)
    if out.stat().st_size>=99_900_000: raise PlanError("Decoded audio exceeds its size bound; truncated output is not accepted")
    _load(out)
    return out

def peak4(y,stop=None):
    maximum=float(np.max(np.abs(y)))
    # Overlap prevents artificial chunk edges from dominating interpolation.
    for start in range(0,len(y),131072):
        if stop is not None and stop.is_set(): raise Stopped("Analysis cancelled")
        left=max(0,start-128); right=min(len(y),start+131072+128)
        oversampled=resample_poly(y[left:right],4,1,axis=0)
        a=(start-left)*4; b=min(len(y)-start,131072)*4+a
        maximum=max(maximum,float(np.max(np.abs(oversampled[a:b]))))
    return maximum

def measure_array(y,sr,stop=None):
    peak=float(np.max(np.abs(y))); rms=float(np.sqrt(np.mean(y*y)))
    loud=float(pyln.Meter(sr).integrated_loudness(y))
    lufs=loud if math.isfinite(loud) else None
    interp=peak4(y,stop)
    correlation=None
    if y.shape[1]==2 and np.std(y[:,0])>1e-12 and np.std(y[:,1])>1e-12:
        correlation=float(np.corrcoef(y[:,0],y[:,1])[0,1])
    # Sum channel spectra: a mono fold can hide antiphase energy.
    f,p=welch(y,fs=sr,nperseg=min(4096,len(y)),axis=0)
    p=np.sum(p,axis=1); total=float(p.sum())
    bands={}
    for name,lo,hi in [("sub",20,60),("bass",60,200),("low_mid",200,500),
                       ("mid",500,2000),("presence",2000,6000),("air",6000,20000)]:
        bands[name]=float(p[(f>=lo)&(f<hi)].sum()/total) if total>1e-30 else 0.
    warnings=[]
    clipped=int(np.count_nonzero(np.abs(y)>=1.))
    if clipped: warnings.append("Samples reach/exceed digital full scale; normalization cannot recover clipped source transients.")
    if correlation is not None and correlation<0: warnings.append("Negative stereo correlation: audition in mono before accepting the master.")
    if lufs is None: warnings.append("No finite gated loudness was measurable (silence or extremely low level).")
    return {"sample_rate":sr,"channels":y.shape[1],"frames":len(y),"duration_seconds":len(y)/sr,
        "integrated_lufs":lufs,"sample_peak_dbfs":db(peak),"oversampled_peak_dbtp_estimate":db(interp),
        "peak_method":"4x scipy resample_poly estimate; not standards-certified",
        "loudness_method":"pyloudnorm gated ITU-R BS.1770","rms_dbfs":db(rms),
        "crest_db":db(peak/rms) if rms>0 else None,"dc_offset":float(np.max(np.abs(y.mean(axis=0)))),
        "stereo_correlation":correlation,"clipped_sample_values":clipped,"band_energy_fractions":bands,
        "warnings":warnings}

def analyze(path,stop=None):
    with tempfile.TemporaryDirectory(prefix="flcopilot-analysis-") as scratch:
        original=file_hash(path)
        decoded=decode_supported(path,scratch,stop); y,sr=_load(decoded)
        result=measure_array(y,sr,stop)
        if original!=file_hash(path): raise PlanError("Input changed during analysis")
        return {**result,"source_sha256":original}

def _stats(stderr):
    for candidate in reversed(re.findall(r"\{[^{}]*\}",stderr,re.S)):
        try:
            row=json.loads(candidate)
            if "input_i" in row: return row
        except json.JSONDecodeError: continue
    raise RuntimeError("FFmpeg did not return loudness measurement JSON")

def master(path,exports,request,stop=None):
    exports=Path(exports); exports.mkdir(parents=True,exist_ok=True)
    folder=exports/("master_"+uuid.uuid4().hex[:12]); folder.mkdir()
    try:
        with tempfile.TemporaryDirectory(prefix="flcopilot-master-") as scratch:
            source_digest=file_hash(path)
            decoded=decode_supported(path,scratch,stop); y,sr=_load(decoded)
            before=measure_array(y,sr,stop)
            if before["integrated_lufs"] is None: raise PlanError("Cannot master silence")
            requested=request.target_lufs-before["integrated_lufs"]
            if requested>18: raise PlanError("Requested gain exceeds 18 dB; fix the source level first.")
            output=folder/"Master.wav"
            args=[ffmpeg_path(),"-hide_banner","-nostdin","-n","-i",str(decoded),"-map","0:a:0","-vn"]
            if request.preserve_dynamics:
                # A guard margin reduces reconstruction overshoot after 24-bit output.
                available=request.ceiling_dbtp-.2-before["oversampled_peak_dbtp_estimate"]
                gain=min(requested,available)
                filter_graph=f"volume={gain:.8f}dB,aresample=dither_method=triangular"
                method="Peak-constrained linear loudness adjustment; dynamics preserved, LUFS target may remain unmet."
                run_owned(args+["-af",filter_graph,"-ar",str(sr),"-c:a","pcm_s24le",str(output)],stop=stop)
            else:
                base=f"loudnorm=I={request.target_lufs}:TP={request.ceiling_dbtp-.2}:LRA=11"
                _,log=run_owned(args+["-af",base+":print_format=json","-f","null","-"],stop=stop)
                stats=_stats(log)
                values={k:float(stats[k]) for k in ("input_i","input_tp","input_lra","input_thresh","target_offset")}
                if not all(math.isfinite(v) for v in values.values()): raise PlanError("FFmpeg measured an invalid loudness input")
                chain=(base+f":measured_I={values['input_i']}:measured_TP={values['input_tp']}"
                    +f":measured_LRA={values['input_lra']}:measured_thresh={values['input_thresh']}"
                    +f":offset={values['target_offset']}:linear=true:print_format=json")
                _,log=run_owned(args+["-af",chain,"-ar",str(sr),"-c:a","pcm_s24le",str(output)],stop=stop)
                method="FFmpeg two-pass loudnorm; dynamic limiting may be used when linear targets are impossible."
            if stop is not None and stop.is_set(): raise Stopped("Master cancelled")
            candidate,cs=_load(output)
            if cs!=sr or candidate.shape!=y.shape: raise PlanError("Output rate, channel count, or frame count changed")
            after=measure_array(candidate,cs,stop)
            if after["oversampled_peak_dbtp_estimate"] is None: raise PlanError("Master output is silent")
            if after["oversampled_peak_dbtp_estimate"]>request.ceiling_dbtp+.05:
                raise PlanError("Output exceeds the requested oversampled-peak check; no master accepted.")
            common=min(before["integrated_lufs"],after["integrated_lufs"])
            ab=[]
            for label,signal,measurement in [("A_Original_Level_Matched",y,before),("B_Master_Level_Matched",candidate,after)]:
                target=folder/(label+".wav")
                sf.write(str(target),signal*(10**((common-measurement["integrated_lufs"])/20.)),sr,subtype="FLOAT")
                ab.append(str(target))
            if file_hash(path)!=source_digest: raise PlanError("Source changed while rendering")
            warnings=list(after["warnings"])
            if abs(after["integrated_lufs"]-request.target_lufs)>.5:
                warnings.append("LUFS target was not met; the achieved value is reported, not hidden.")
            if before["crest_db"]-after["crest_db"]>3.:
                warnings.append("Crest factor fell by more than 3 dB. Audition for lost punch.")
            report={"method":method,"requested_lufs":request.target_lufs,"requested_ceiling_dbtp":request.ceiling_dbtp,
                "before":before,"after":after,"warnings":warnings,"source_sha256":source_digest,
                "master_sha256":file_hash(output),"source_overwritten":False,"original_project_modified":False,
                "tonal_eq_applied":False,"subjective_quality_validated":False,
                "ab_target_lufs":common,"output":str(output),"ab_files":ab}
            report_path=folder/"Master_Report.json"; atomic_json(report_path,report)
            return report, [output,Path(ab[0]),Path(ab[1]),report_path]
    except Exception:
        import shutil
        shutil.rmtree(folder,ignore_errors=True)
        raise

def compare(a,b,stop=None):
    left=analyze(a,stop); right=analyze(b,stop)
    fields=("integrated_lufs","oversampled_peak_dbtp_estimate","crest_db","stereo_correlation")
    delta={k:(right[k]-left[k] if right[k] is not None and left[k] is not None else None) for k in fields}
    return {"baseline":left,"candidate":right,"candidate_minus_baseline":delta,
        "content_alignment_verified":False,"note":"Global technical comparison, not proof of artistic improvement or aligned song content."}
