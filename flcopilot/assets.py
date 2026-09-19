"""Explicitly imported local files; opaque IDs, no remote downloads or arbitrary file reads."""
from __future__ import annotations
import hashlib
import json
import os
import threading
import uuid
from pathlib import Path
from .contracts import PlanError, Stopped

AUDIO_SUFFIXES={".wav",".wave",".flac",".aif",".aiff",".ogg",".oga",".mp3",".m4a",".aac"}
MAX_UPLOAD=300*1024*1024

def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""): h.update(part)
    return h.hexdigest()

def atomic_json(path,data):
    path=Path(path); temp=path.with_suffix(path.suffix+".tmp")
    with temp.open("w",encoding="utf-8") as f:
        json.dump(data,f,indent=2,allow_nan=False); f.flush(); os.fsync(f.fileno())
    os.replace(temp,path)

class AssetStore:
    def __init__(self,workspace):
        self.root=Path(workspace).resolve(); self.root.mkdir(parents=True,exist_ok=True)
        self.imports=self.root/"imports"; self.exports=self.root/"exports"
        self.imports.mkdir(exist_ok=True); self.exports.mkdir(exist_ok=True)
        self.manifest=self.root/"assets.json"; self.lock=threading.RLock()
        self.data=json.loads(self.manifest.read_text()) if self.manifest.exists() else {}
    def import_stream(self,stream,length,name,*,validate=None,stop=None,metadata=None):
        # Internal validation hooks run before registration, never after publication.
        if metadata and set(metadata) & {"id","name","path","sha256","kind"}:
            raise PlanError("Input metadata cannot replace asset identity")
        def check_stop():
            if stop is not None and stop.is_set(): raise Stopped("Audio import cancelled")
        check_stop()
        suffix=Path(name.replace("\\","/")).suffix.lower()
        if suffix not in AUDIO_SUFFIXES: raise PlanError("Import WAV, FLAC, AIFF, OGG, MP3, M4A, or AAC audio.")
        if type(length)!=int or not 1<=length<=MAX_UPLOAD: raise PlanError("Audio upload must be 1 byte to 300 MiB")
        asset=uuid.uuid4().hex; path=self.imports/(asset+suffix)
        remaining=length
        try:
            with path.open("xb") as out:
                while remaining:
                    check_stop()
                    block=stream.read(min(1024*1024,remaining))
                    if not block: raise PlanError("Upload ended before the declared size")
                    out.write(block); remaining-=len(block)
            if validate is not None: validate(path)
            check_stop()
            record={**(metadata or {}),"id":asset,"name":Path(name.replace("\\","/")).name[:180],
                "path":str(path.relative_to(self.root)),"sha256":file_hash(path),"kind":"input"}
            with self.lock:
                check_stop()
                updated={**self.data,asset:record}
                atomic_json(self.manifest,updated)
                self.data=updated
            return record
        except Exception:
            path.unlink(missing_ok=True); raise
    def add_output(self,path,name=None,kind="audio"):
        return self.add_outputs([(path, name, kind)])[0]
    def add_outputs(self,items):
        """Register a completed group atomically; failure publishes no partial group."""
        records=[]
        for path,name,kind in items:
            path=Path(path).resolve()
            if not path.is_relative_to(self.exports) or not path.is_file():
                raise PlanError("Output must exist inside exports")
            asset=uuid.uuid4().hex
            records.append({"id":asset,"name":name or path.name,"path":str(path.relative_to(self.root)),
                            "sha256":file_hash(path),"kind":kind})
        with self.lock:
            updated={**self.data,**{r["id"]:r for r in records}}
            atomic_json(self.manifest,updated)
            self.data=updated
        return records
    def discard_outputs(self,ids):
        """Internal failed-publication cleanup; never an API to delete user inputs."""
        with self.lock:
            if any(self.data.get(i,{}).get("kind")=="input" for i in ids):
                raise PlanError("Imported sources cannot be discarded by output cleanup")
            updated={i:r for i,r in self.data.items() if i not in ids}
            atomic_json(self.manifest,updated)
            self.data=updated
    def resolve(self,asset,verify=True):
        with self.lock: record=self.data.get(asset)
        if not record: raise PlanError("Unknown imported asset")
        path=(self.root/record["path"]).resolve(strict=True)
        if not path.is_relative_to(self.root): raise PlanError("Asset escapes the local workspace")
        if verify and file_hash(path)!=record["sha256"]: raise PlanError("Asset bytes changed since import")
        return path
    def list(self):
        with self.lock: return list(self.data.values())
