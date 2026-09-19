"""Adapter to PostFader V10. Upstream code is installed separately, not copied."""
from __future__ import annotations
import importlib.metadata
import os
import math
import threading
import time
from .contracts import NotDispatched, Stopped

class PostFaderAdapter:
    name="postfader"
    def __init__(self,windows_menu_enabled=False):
        try:
            version=importlib.metadata.version("postfader-fl-studio-mcp")
            if version != "10.0.0": raise NotDispatched("This build qualifies only PostFader 10.0.0; found "+version)
            from fl_studio_mcp.readonly_inspector import ReadOnlyInspector
            from fl_studio_mcp.verified_writer import VerifiedWriter, WriteModeManager
            from fl_studio_mcp.bridge_client import get_client
        except ImportError as exc:
            raise NotDispatched("PostFader is not installed. Run Setup-Windows.ps1 or install the pinned bridge dependency.") from exc
        self.inspector=ReadOnlyInspector(); self.writer=VerifiedWriter(); self.mode=WriteModeManager()
        self.client=get_client(); self.windows_menu_enabled=windows_menu_enabled
        self.io=threading.RLock()
        self._selected_destination=None
        self._gate_owned=False
    def connection(self):
        with self.io:
            return self.inspector.connection_info().model_dump(mode="json")
    def _ready(self):
        c=self.connection()
        if not c["connected"] or not c["compatible"]:
            raise NotDispatched(c.get("error") or c.get("compatibility_reason") or "Bridge unavailable")
        if not c.get("session_fingerprint"): raise NotDispatched("Missing project session fingerprint")
        return c
    def snapshot(self):
        with self.io:
            c=self._ready()
            project=self.inspector.project_summary().model_dump(mode="json")
            scan=self.inspector.list_mixer_tracks(only_used=False,include_peaks=False).model_dump(mode="json")
            if scan.get("partial"): raise NotDispatched("A complete mixer scan is required")
            if self.connection().get("session_fingerprint")!=c["session_fingerprint"]:
                raise NotDispatched("Project changed during inspection")
            return {"connection":c,"session":c["session_fingerprint"],"backend":self.name,
                "project":project,"tracks":scan["tracks"],"observed":time.time(),
                "evidence":"live_readback","observation_atomic":False,"warnings":scan.get("warnings",[])}
    def track(self,index):
        with self.io:
            return self.inspector.inspect_mixer_track(index).track.model_dump(mode="json")
    def parameters(self,track,slot):
        with self.io:
            return self.inspector.plugin_parameters(track_index=track,slot_index=slot,limit=128).model_dump(mode="json")
    def parameter(self,track,slot,index):
        with self.io:
            page=self.inspector.plugin_parameters(track_index=track,slot_index=slot,offset=index,limit=1)
            rows=[p for p in page.parameters if p.index==index and p.classification!="padding_candidate"]
            if len(rows)!=1 or rows[0].normalized_value is None: raise NotDispatched("No named parameter readback at that index")
            return {"plugin":page.plugin.name,"name":rows[0].reported_name,"value":rows[0].normalized_value}
    def begin(self,session):
        with self.io:
            self._gate_owned=False
            c=self._ready()
            if c["session_fingerprint"] != session: raise NotDispatched("Session changed")
            if not c.get("bridge_provenance_verified"):
                raise NotDispatched("Bridge source hash is not the packaged V10 source. Install and reload the matching bridge.")
            if not c.get("project_load_epoch"):
                raise NotDispatched("The bridge does not report project-load epoch protection.")
            if c.get("verified_writes_enabled"):
                raise NotDispatched("Another client or startup configuration already enabled writes. Disable it first.")
            self._gate_owned=True  # Set before dispatch: closure is needed even if its reply is lost.
            self.mode.set_write_mode(enabled=True,confirm_user_present=True,session_fingerprint=session)
    def end(self,session):
        with self.io:
            if not self._gate_owned: return
            # Closing a changed/new session is not inferred safe from the old token.
            if self.connection().get("session_fingerprint") != session:
                raise RuntimeError("Bridge session changed; inspect the new session's write gate manually")
            self.mode.set_write_mode(enabled=False,session_fingerprint=session)
            self._gate_owned=False
    def execute(self,op,before,session):
        with self.io:
            common=dict(track_index=op.track,allow_master=op.track==0,session_fingerprint=session)
            if op.kind=="volume":
                from fl_studio_mcp.contracts import ExpectedMixerVolumeState
                expected=ExpectedMixerVolumeState(volume_db=before["track"]["volume_db"],
                    volume_normalized=before["track"]["volume_normalized"])
                result=self.writer.set_mixer_volume_db(**common,volume_db=op.value,expected_before=expected)
            elif op.kind=="pan":
                result=self.writer.set_mixer_pan(**common,pan=op.value,expected_before=before["track"]["pan"])
            elif op.kind=="mute":
                result=self.writer.set_mixer_mute(**common,muted=op.value,expected_before=before["track"]["muted"])
            elif op.kind=="stereo":
                result=self.writer.set_mixer_stereo_separation(**common,stereo_separation=op.value,
                    expected_before=before["track"]["stereo_separation"])
            elif op.kind=="rename":
                result=self.writer.set_mixer_name(**common,name=op.value,expected_before=before["track"]["name"])
            elif op.kind=="parameter":
                from fl_studio_mcp.contracts import ExpectedPluginParameterState
                observed=self.parameter(op.track,op.slot,op.parameter)
                if observed != before["parameter"]:
                    raise NotDispatched("Parameter identity or value changed before dispatch")
                expected=ExpectedPluginParameterState(normalized_value=observed["value"])
                result=self.writer.set_plugin_parameter(**common,slot_index=op.slot,
                    parameter_index=op.parameter,normalized_value=op.value,expected_before=expected)
                if result.plugin_name != observed["plugin"] or result.parameter_name != observed["name"]:
                    raise RuntimeError("Parameter receipt identifies a different plugin/control; outcome unknown")
            elif op.kind=="load_effect":
                if not self.windows_menu_enabled: raise NotDispatched("Enable the experimental Windows menu adapter in Setup first.")
                if os.name != "nt": raise NotDispatched("Windows menu adapter requires Windows")
                from fl_studio_mcp.plugin_loading import PluginLoadRequest, load_plugin
                from .windows_menu import WindowsPluginMenu
                self._selected_destination=op.track
                request=PluginLoadRequest(name=op.value,kind="effect",track_index=op.track,
                    allow_master=op.track==0,session_fingerprint=session)
                backend=WindowsPluginMenu(destination_guard=lambda:self._destination_ok(op.track,session))
                result=load_plugin(request,backend=backend)
            else: raise NotDispatched("Operation not allowlisted")
            return result.model_dump(mode="json")
    def _destination_ok(self,track,session):
        return (self.connection().get("session_fingerprint")==session
            and self.track(track).get("selected") is True and not self.track(track).get("plugins"))
    def menu_inventory(self):
        if not self.windows_menu_enabled:
            return {"supported":False,"error":"Experimental Windows menus are disabled; enable them in Setup."}
        from fl_studio_mcp.plugin_loading import list_available_plugins
        from .windows_menu import WindowsPluginMenu
        return list_available_plugins(backend=WindowsPluginMenu()).model_dump(mode="json")
    def observe_peaks(self,tracks,seconds,stop):
        start=self.snapshot(); maxima={str(i):0. for i in tracks}; count=0
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if stop.is_set(): raise Stopped("Peak observation cancelled")
            with self.io:
                self._ready()
                raw=self.client.call("mixer.list",only_used=False,peaks=True)
            seen=set()
            for row in raw.get("tracks",[]):
                key=str(row.get("index"))
                if key in maxima:
                    l,r=row.get("peak_l"),row.get("peak_r")
                    seen.add(key)
                    if (type(l) not in (int,float) or type(r) not in (int,float)
                        or not math.isfinite(l) or not math.isfinite(r) or min(l,r)<0):
                        raise NotDispatched("Bridge did not return numeric sample meters")
                    maxima[key]=max(maxima[key],float(l),float(r))
            if seen != set(maxima): raise NotDispatched("Meter pass omitted a requested track")
            count+=1
            stop.wait(.15)
        if self.connection().get("session_fingerprint")!=start["session"]:
            raise NotDispatched("Project changed during metering")
        return {"session":start["session"],"before":start,"duration":seconds,
            "samples":count,"peaks":maxima,"demo":False}
