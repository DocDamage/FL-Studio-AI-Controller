"""Process-lifetime workspace lock. Prevent two app executors owning one workspace."""
import os
from pathlib import Path
class InstanceLock:
    def __init__(self,path): self.path=Path(path); self.file=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file=self.path.open("a+b"); self.file.seek(0)
        if self.path.stat().st_size==0: self.file.write(b"0"); self.file.flush()
        self.file.seek(0)
        try:
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close(); self.file=None
            raise RuntimeError("An app is already using this workspace. Close that app first.") from exc
        return self
    def __exit__(self,*args):
        if self.file is not None: self.file.close(); self.file=None
