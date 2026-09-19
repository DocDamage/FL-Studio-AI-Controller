"""Saved-file backup only. An on-disk FLP is not the unsaved live project."""
from __future__ import annotations
import shutil
import uuid
from pathlib import Path
from .assets import atomic_json,file_hash
from .contracts import PlanError

def checkpoint(saved_flp,exports):
    source=Path(saved_flp).expanduser().resolve(strict=True)
    if source.suffix.lower()!=".flp" or not source.is_file(): raise PlanError("Choose an existing saved .flp")
    with source.open("rb") as f:
        if f.read(4)!=b"FLhd": raise PlanError("Not an FLP header")
    if source.stat().st_size>300*1024*1024: raise PlanError("FLP exceeds the 300 MiB backup bound")
    folder=Path(exports)/("checkpoint_"+uuid.uuid4().hex[:12]); folder.mkdir(parents=True)
    output=folder/"Saved_Project_Backup.flp"
    try:
        original=file_hash(source); shutil.copyfile(source,output)
        if original!=file_hash(source) or original!=file_hash(output): raise PlanError("Saved project changed during copying")
        report={"sha256":original,"output":str(output),"source_overwritten":False,
            "unsaved_live_edits_included":False,"external_samples_bundled":False,
            "note":"Byte-verified backup of the saved file only; no automatic FL save or guaranteed rollback."}
        atomic_json(folder/"Checkpoint_Report.json",report)
        return report
    except Exception:
        shutil.rmtree(folder,ignore_errors=True); raise
