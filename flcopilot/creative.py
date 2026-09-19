"""Original deterministic boom-bap MIDI sketch. Export only; never changes an FLP."""
from __future__ import annotations
import random
import struct
import uuid
from pathlib import Path
from .contracts import PlanError

PITCH={"C":0,"C#":1,"D":2,"D#":3,"E":4,"F":5,"F#":6,"G":7,"G#":8,"A":9,"A#":10,"B":11}

def vlq(value):
    if not 0<=value<=0x0fffffff: raise ValueError("Invalid MIDI delta")
    out=[value&127]
    while value>>7:
        value>>=7; out.insert(0,(value&127)|128)
    return bytes(out)

def track_chunk(events,end_tick):
    data=bytearray(); previous=0
    for tick,message in sorted(events,key=lambda x:(x[0],x[1][0]&0xf0!=0x80)):
        data+=vlq(tick-previous)+message; previous=tick
    data+=vlq(max(0,end_tick-previous))+b"\xff\x2f\x00"
    return b"MTrk"+struct.pack(">I",len(data))+data

def export_sketch(exports,bpm=88.,key="E",bars=8,seed=17,swing=.08):
    if not isinstance(bpm,(float,int)) or isinstance(bpm,bool) or not 50<=bpm<=180: raise PlanError("BPM must be 50–180")
    if key not in PITCH or type(bars)!=int or not 1<=bars<=32 or type(seed)!=int or not 0<=seed<=2147483647:
        raise PlanError("Invalid key, bars, or seed")
    if not isinstance(swing,(float,int)) or isinstance(swing,bool) or not 0<=swing<=.25: raise PlanError("Swing must be 0–0.25")
    rng=random.Random(seed); ppq=480; end=bars*4*ppq
    tempo=round(60000000/bpm)
    conductor=[(0,b"\xff\x51\x03"+tempo.to_bytes(3,"big")),(0,b"\xff\x58\x04\x04\x02\x18\x08")]
    drums=[]; bass=[]
    def note(events,ch,pitch,start,length,velocity):
        events.extend([(start,bytes([0x90|ch,pitch,velocity])),(min(end,start+length),bytes([0x80|ch,pitch,0]))])
    for bar in range(bars):
        base=bar*1920
        for tick in (0,720,1200)+( (1680,) if bar%4==3 else () ):
            note(drums,9,36,base+tick,90,rng.randint(100,121))
        for tick in (480,1440): note(drums,9,38,base+tick,100,rng.randint(104,122))
        if bar%2: note(drums,9,38,base+1320,50,rng.randint(35,53))
        for step in range(8):
            tick=base+step*240+(round(240*swing) if step%2 else 0)
            note(drums,9,42,tick,60,rng.randint(63,85) if step%2 else rng.randint(85,101))
        root=36+PITCH[key]+([0,0,3,5][bar%4])
        note(bass,0,root,base,630,98)
        note(bass,0,root,base+960,420,91)
        note(bass,0,root-12,base+1560,300,96)
    midi=b"MThd"+struct.pack(">IHHH",6,1,3,ppq)+track_chunk(conductor,end)+track_chunk(drums,end)+track_chunk(bass,end)
    folder=Path(exports); folder.mkdir(parents=True,exist_ok=True)
    path=folder/("Boom_Bap_"+str(seed)+"_"+uuid.uuid4().hex[:8]+".mid")
    path.write_bytes(midi)
    return path,{"bpm":bpm,"key":key+" minor","bars":bars,"seed":seed,"swing":swing,
        "tracks":3,"ppq":ppq,"fl_playlist_modified":False,"note":"Import this MIDI in FL Studio and assign your own drums and bass sounds."}
