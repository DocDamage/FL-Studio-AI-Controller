"""Bounded intake for FL-produced renders.

FL Studio does not expose a qualified render command through the current bridge.
This module therefore watches an explicitly chosen user folder and imports only a
new, stable audio file that appears after the watch starts. It never clicks FL,
types a path, overwrites the source, or treats the file as causal proof.
"""
from __future__ import annotations
import os
import time
from dataclasses import dataclass
from pathlib import Path
from .assets import AUDIO_SUFFIXES, MAX_UPLOAD
from .contracts import PlanError, Stopped

MAX_WATCH_SECONDS=600
STABLE_SECONDS=1.0

@dataclass(frozen=True)
class FileStamp:
    size:int
    mtime_ns:int

def snapshot_folder(folder: str | Path) -> dict[str,FileStamp]:
    root=Path(folder).expanduser().resolve()
    if not root.is_dir(): raise PlanError("Render watch folder does not exist")
    out={}
    try:
        for p in root.iterdir():
            if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES:
                s=p.stat()
                out[p.name]=FileStamp(s.st_size,s.st_mtime_ns)
    except OSError as exc:
        raise PlanError("Cannot inspect render watch folder") from exc
    return out

def _safe_candidate(root:Path,name:str,baseline:dict[str,FileStamp]):
    path=(root/name).resolve()
    if path.parent != root or not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
        return None
    stat=path.stat(); stamp=FileStamp(stat.st_size,stat.st_mtime_ns)
    if stat.st_size < 1 or stat.st_size > MAX_UPLOAD or baseline.get(name)==stamp:
        return None
    return path,stamp

def wait_for_render(folder,baseline,stop,timeout=120,stable_seconds=STABLE_SECONDS):
    if type(timeout) not in (int,float) or isinstance(timeout,bool) or not 1<=timeout<=MAX_WATCH_SECONDS:
        raise PlanError("Render watch timeout must be 1 to 600 seconds")
    root=Path(folder).expanduser().resolve()
    if not root.is_dir(): raise PlanError("Render watch folder does not exist")
    if not isinstance(baseline,dict): raise PlanError("Render watch baseline is required")
    deadline=time.monotonic()+float(timeout); observed={}
    while time.monotonic()<deadline:
        if stop.is_set(): raise Stopped("Render watch cancelled")
        candidates=[]
        try:names=[p.name for p in root.iterdir()]
        except OSError as exc:raise PlanError("Cannot inspect render watch folder") from exc
        for name in names:
            item=_safe_candidate(root,name,baseline)
            if not item:continue
            path,stamp=item; now=time.monotonic()
            previous=observed.get(name)
            if previous and previous[0]==stamp and now-previous[1]>=stable_seconds:
                candidates.append((stamp.mtime_ns,name,path,stamp))
            elif not previous or previous[0]!=stamp:
                observed[name]=(stamp,now)
        if len(candidates)>1:
            raise PlanError("Multiple new render files appeared; choose a clean export folder and try again")
        if candidates:
            _,name,path,stamp=candidates[0]
            return path,stamp
        stop.wait(.1)
    raise PlanError("No stable new audio render appeared before the timeout")

def import_render(assets,path,expected:FileStamp):
    path=Path(path).resolve(); before=path.stat()
    if FileStamp(before.st_size,before.st_mtime_ns)!=expected:
        raise PlanError("Render changed before import")
    with path.open("rb") as src:
        record=assets.import_stream(src,before.st_size,path.name)
    after=path.stat()
    if FileStamp(after.st_size,after.st_mtime_ns)!=expected:
        raise PlanError("Render changed during import; imported copy is not promoted as verified")
    return {**record,"source":"watched_fl_export","source_file_unchanged":True,
            "render_triggered_by_app":False,"causal_provenance_verified":False}
