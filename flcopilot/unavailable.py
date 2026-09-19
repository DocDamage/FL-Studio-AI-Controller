"""Disconnected is not simulation: local audio tools remain available."""
from .contracts import NotDispatched
class UnavailableAdapter:
    name="postfader"
    windows_menu_enabled=False
    def __init__(self,reason): self.reason=str(reason)
    def connection(self): return {"connected":False,"compatible":False,"error":self.reason,"session_fingerprint":None}
    def snapshot(self): raise NotDispatched(self.reason)
    def track(self,*args): raise NotDispatched(self.reason)
    def parameters(self,*args): raise NotDispatched(self.reason)
    def menu_inventory(self): return {"supported":False,"error":self.reason}
