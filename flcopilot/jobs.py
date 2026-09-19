"""Bounded application jobs. The DAW executor remains the only mutation owner."""
from __future__ import annotations
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from .contracts import PlanError

class Jobs:
    def __init__(self):
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix="flcopilot")
        self.lock=threading.RLock(); self.rows={}
    def submit(self,label,func):
        with self.lock:
            if sum(r["status"] in ("queued","running") for r in self.rows.values())>=4:
                raise PlanError("Too many pending jobs; finish or stop the current work.")
            if len(self.rows)>100:
                for key in list(self.rows):
                    if self.rows[key]["status"] in ("complete","error"):
                        del self.rows[key]
                        if len(self.rows)<=80: break
            key=uuid.uuid4().hex
            self.rows[key]={"id":key,"label":label,"status":"queued","created":time.time(),"result":None,"error":None}
        def worker():
            with self.lock: self.rows[key]["status"]="running"
            try:
                result=func()
                with self.lock: self.rows[key].update(status="complete",result=result)
            except Exception as exc:
                with self.lock: self.rows[key].update(status="error",error=str(exc))
        self.pool.submit(worker)
        return {"job":key}
    def get(self,key):
        with self.lock:
            if key not in self.rows: raise PlanError("Unknown job")
            return dict(self.rows[key])
    def close(self): self.pool.shutdown(wait=True,cancel_futures=True)
