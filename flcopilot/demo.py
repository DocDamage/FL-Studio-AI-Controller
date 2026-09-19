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
        self.tracks.append(dict(index=6,name="Workbench demo",volume_db=-12.,volume_normalized=.7,
            pan=0.,muted=False,soloed=False,stereo_separation=0.,
            plugins=[dict(slot_index=0,name="Copilot Test Effect (simulated)")]))
        for index,name in ((129,"Demo gain"),(2049,"Demo frequency"),(4097,"Demo attack")):
            self.params[(6,0,index)]=dict(plugin="Copilot Test Effect (simulated)",name=name,value=.5)
        self.transport={"playing":False,"recording":False}
    def connection(self):
        return dict(connected=True,compatible=True,session_fingerprint=self.session,
            fl_app_version="SIMULATED — no FL Studio connection",backend=self.name,
            bridge_provenance_verified=False,verified_writes_enabled=self.writes,plugin_display_units=True)
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
    def display_parameter(self,track,slot,index):
        row=self.parameter(track,slot,index)
        value=row["value"]
        if (track,slot,index)==(6,0,129): text=f"{value*36-24:.6f} dB"
        elif (track,slot,index)==(6,0,2049): text=f"{value*2:.6f} kHz"
        elif (track,slot,index)==(6,0,4097): text=f"{value*.04:.6f} seconds"
        else: text=str(value)
        return {**row,"display":text}
    def parameter_page(self,track,slot,offset,limit):
        plugins=[p for p in self.track(track)["plugins"] if p["slot_index"]==slot]
        if len(plugins)!=1: raise NotDispatched("No unique loaded effect at this slot")
        total=max((i+1 for (t,s,i) in self.params if (t,s)==(track,slot)),default=0)
        count=min(limit,max(0,total-offset))
        rows=[]
        for i in range(offset,offset+count):
            if (track,slot,i) in self.params:
                p=self.display_parameter(track,slot,i)
                rows.append(dict(index=i,reported_name=p["name"],normalized_value=p["value"],
                    display_text=p["display"],classification="reported"))
            else:
                rows.append(dict(index=i,reported_name="",normalized_value=0.,display_text="0",classification="padding_candidate"))
        return dict(plugin={"name":plugins[0]["name"],"track_index":track,"slot_index":slot},
            offset=offset,scanned_count=count,reported_parameter_count=total,parameters=rows)
    def transport_state(self): return self.transport.copy()
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
        elif op.kind=="parameter_display":
            from .units import require_display_ready
            require_display_ready(self)
            key=(op.track,op.slot,op.parameter)
            maps={(6,0,129):("dB",-24.,36.),(6,0,2049):("Hz",0.,2000.),(6,0,4097):("ms",0.,40.)}
            if key not in maps or op.value.unit!=maps[key][0]: raise NotDispatched("No simulated display mapping")
            _,low,width=maps[key]
            if not low <= op.value.amount <= low+width: raise NotDispatched("Outside simulated control range")
            self.params[key]["value"]=(op.value.amount-low)/width
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
