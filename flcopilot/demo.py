"""Deterministic simulator. Never represented as a live FL session."""
from __future__ import annotations
import copy
import math
import time
from .contracts import NotDispatched, digest

class DemoAdapter:
    name="demo"
    def __init__(self):
        self.session="d"*32
        self.writes=False
        self.calls=[]
        self.tracks=[dict(index=i,name=n,volume_db=v,volume_normalized=.7,pan=p,
            muted=False,soloed=False,plugins=[],stereo_separation=0.) for i,n,v,p in
            [(0,"Master",0.,0.),(1,"Drums",-2.,0.),(2,"Sample chops",-5.,0.),
             (3,"Bass / 808",-3.,0.),(4,"Choir & bells",-10.,.12),(5,"Transitions",-12.,-.1)]]
        self.tracks[1]["plugins"]=[dict(slot_index=0,name="Fruity Parametric EQ 2")]
        self.params={(1,0,0):dict(plugin="Fruity Parametric EQ 2",name="Demo parameter",value=.5)}
    def connection(self):
        return dict(connected=True,compatible=True,session_fingerprint=self.session,
            fl_app_version="SIMULATED — no FL Studio connection",backend=self.name,
            bridge_provenance_verified=False,verified_writes_enabled=self.writes)
    def snapshot(self):
        return dict(connection=self.connection(),session=self.session,backend=self.name,
            project={"name":"Demo • Underground session","tempo":88.,"demo":True},
            tracks=copy.deepcopy(self.tracks),observed=time.time(),
            evidence="simulated",observation_atomic=False)
    def track(self,index):
        rows=[t for t in self.tracks if t["index"] == index]
        if len(rows)!=1: raise NotDispatched("Track not found")
        return copy.deepcopy(rows[0])
    def parameter(self,track,slot,index):
        row=self.params.get((track,slot,index))
        if not row: raise NotDispatched("Parameter not found")
        return copy.deepcopy(row)
    def parameters(self,track,slot):
        return [{"index":i,"reported_name":v["name"],"normalized_value":v["value"],"display_text":str(v["value"])}
            for (t,s,i),v in self.params.items() if (t,s)==(track,slot)]
    def begin(self,session):
        if session != self.session: raise NotDispatched("Session changed")
        self.writes=True
    def end(self,session): self.writes=False
    def execute(self,op,before,session):
        if not self.writes or session != self.session: raise NotDispatched("Write gate closed")
        from .executor import stable_track
        if stable_track(self.track(op.track)) != before["track"]: raise NotDispatched("Track changed")
        self.calls.append(op.model_dump())
        target=next(t for t in self.tracks if t["index"]==op.track)
        if op.kind in ("volume","pan","rename","mute","stereo"):
            target[{"volume":"volume_db","pan":"pan","rename":"name","mute":"muted","stereo":"stereo_separation"}[op.kind]]=op.value
        elif op.kind=="parameter": self.params[(op.track,op.slot,op.parameter)]["value"]=op.value
        else: target["plugins"].append(dict(slot_index=0,name=op.value))
        return {"verified":True,"status":"loaded" if op.kind=="load_effect" else "verified",
            "session_fingerprint":session,"demo":True,"project_saved":False,
            "undo_point_created":None,"verification_summary":"Simulator state changed; not a live-host test."}
    def menu_inventory(self):
        return {"supported":True,"demo":True,"entries":[dict(name="Fruity Limiter",kind="effect",menu_path=["Add","Effect","Fruity Limiter"])]}
    def observe_peaks(self,tracks,seconds,stop):
        start=self.snapshot()
        for _ in range(4):
            if stop.wait(.05): raise NotDispatched("Observation stopped")
        return {"session":self.session,"before":start,"duration":seconds,"samples":4,"demo":True,
            "peaks":{str(i):10**({0:-1.,1:-2.,2:-8.,3:-4.,4:-14.,5:-12.}.get(i,-12.)/20) for i in tracks}}
