"""Shared application service used by both the UI and the MCP relay."""
from __future__ import annotations
import threading
import time
from . import __version__
from .assets import AssetStore
from .contracts import Approval, Locks, MasterRequest, MixRequest, PrepareRequest, PlanError, digest
from .executor import Executor
from .jobs import Jobs
from .journal import Journal
from .planner import LocalPlanner

class Service:
    def __init__(self,workspace,adapter,endpoint=None):
        self.assets=AssetStore(workspace)
        self.adapter=adapter
        self.journal=Journal(self.assets.root/"journal.sqlite3")
        self.executor=Executor(adapter,self.journal)
        from .plugin_workbench import PluginWorkbench
        self.workbench=PluginWorkbench(self.executor)
        from .review_store import ReviewStore
        self.reviews=ReviewStore(self.assets.root/"reviews.sqlite3")
        self.jobs=Jobs(); self.audio_lock=threading.Lock()
        from .render_workflow import RenderWorkflow
        self.render_workflow=RenderWorkflow(self.assets,self.jobs,self.executor.stop_event)
        self.planner=LocalPlanner(endpoint)
        self.last_snapshot=None
    def status(self):
        return {"version":__version__,"backend":self.adapter.name,"demo":self.adapter.name=="demo",
            "mode":self.executor.mode,"locks":self.executor.locks.model_dump(mode="json"),
            "stopped":self.executor.stop_event.is_set(),"blocked":self.journal.blocked(),
            "running":self.executor.running,"planner":self.planner.status,
            "windows_menu_enabled":getattr(self.adapter,"windows_menu_enabled",False),
            "workspace":str(self.assets.root),"hotkey":getattr(self,"hotkey_status","Not registered")}
    def inspect(self):
        with self.executor.mutex:
            snapshot=self.adapter.snapshot()
            self.last_snapshot={"session":snapshot["session"],"at":time.time(),
                "digest":digest({"session":snapshot["session"],"tracks":snapshot["tracks"]})}
            return {**snapshot,"reconcile_digest":self.last_snapshot["digest"]}
    def capabilities(self):
        return {"live_qualification":"No Windows/FL live-host acceptance was performed for this release.",
            "features":[
                {"name":"Session inspection + mixer writes","status":"demo" if self.adapter.name=="demo" else "runtime checked","detail":"PostFader V10: fader, pan, name, mute, stereo separation and loaded effect parameters; approval plus independent readback."},
                {"name":"Plugin workbench","status":"implemented","detail":"Bounded read-only parameter search with high-index pagination; observation-bound normalized or explicit dB/Hz/ms/percent previews. Display searches require stopped transport and separate approval."},
                {"name":"Windows effect insertion","status":"experimental","detail":"Native Win32 Add menu only; isolated empty destination; manual fallback when not exposed."},
                {"name":"Manual FL export intake","status":"implemented","detail":"One-shot, desktop-authorized local folder watch with verified copy, cancellation and before/after handoff. Does not trigger FL rendering or prove export provenance."},
                {"name":"Before / after audio review","status":"implemented","detail":"Imported paired exports, conservative timing checks, measured attenuation-only A/B, section deltas and saved human preferences. No live capture or causal-quality claim."},
                {"name":"Audio analysis + WAV finishing","status":"implemented","detail":"Local exported audio; gated LUFS, oversampled-peak estimate, real A/B files."},
                {"name":"MIDI sketches","status":"implemented","detail":"Deterministic file export; manual FL import."},
                {"name":"AI planning","status":"optional","detail":"Local llama.cpp-compatible endpoint or MCP relay; no bundled weights."},
                {"name":"Plugin removal / reordering","status":"unsupported","detail":"No state-preserving live implementation yet."},
                {"name":"Automatic Playlist editing","status":"unsupported","detail":"No pixel-based or binary-FLP editing."},
                {"name":"Live audio capture / VST3 sensor","status":"unsupported","detail":"This release measures explicitly imported renders."},
                {"name":"Connection diagnostics","status":"implemented","detail":"Read-only environment and bridge checks, plus privacy-filtered JSON export. Simulator never qualifies the host."},
                {"name":"Verified-run restore previews","status":"implemented","detail":"New approved inverse writes for captured controls only; stale, ambiguous, or insertion runs are refused."},
                {"name":"Live project auto-save / rollback","status":"manual handoff","detail":"Save a new project version in FL; CLI can copy a saved FLP only."}]}
    def settings(self,data):
        if set(data)-{"mode","locks","windows_menu_enabled"}: raise PlanError("Unknown setting")
        if "windows_menu_enabled" in data and type(data["windows_menu_enabled"])!=bool: raise PlanError("Boolean required")
        mode=data.get("mode",self.executor.mode)
        locks=Locks.model_validate_json(__import__('json').dumps(data.get("locks",self.executor.locks.model_dump(mode="json"))))
        self.executor.configure(mode,locks)
        if "windows_menu_enabled" in data:
            if type(data["windows_menu_enabled"])!=bool: raise PlanError("Boolean required")
            if hasattr(self.adapter,"windows_menu_enabled"): self.adapter.windows_menu_enabled=data["windows_menu_enabled"]
        return self.status()
    def prompt(self,text):
        from .executor import stable_track
        with self.executor.mutex:
            snapshot=self.adapter.snapshot()
            locks=self.executor.locks
        request,source=self.planner.plan(text,snapshot,locks)
        with self.executor.mutex:
            if locks != self.executor.locks:
                raise PlanError("Protection locks changed while planning")
            current=self.adapter.snapshot()
            expected=digest({"session":snapshot["session"],"tracks":[stable_track(t) for t in snapshot["tracks"]]})
            observed=digest({"session":current["session"],"tracks":[stable_track(t) for t in current["tracks"]]})
            if expected != observed:
                raise PlanError("Session changed while interpreting the prompt; prepare it again")
            anchors=[]
            for op in request.operations:
                rows=[t for t in snapshot["tracks"] if t["index"]==op.track]
                if len(rows)!=1: raise PlanError("Planner target was not uniquely observed")
                anchors.append({"track":stable_track(rows[0])})
            return {"plan":self.executor.prepare(request,expected_session=snapshot["session"],
                expected_before=tuple(anchors)),"planner":source}
    def prepare(self,data):
        return self.executor.prepare(PrepareRequest.model_validate_json(__import__('json').dumps(data)))
    def execute(self,data,delay=0.):
        approval=Approval.model_validate_json(__import__('json').dumps(data))
        if delay and self.executor.stop_event.wait(delay): raise PlanError("Cancelled during focus handoff")
        return self.executor.run(approval)
    def mix(self,data):
        from .mix import propose_gain_staging
        request=MixRequest.model_validate_json(__import__('json').dumps(data))
        with self.executor.mutex: return propose_gain_staging(self.executor,request)
    def analyze(self,asset):
        from .audio import analyze
        with self.audio_lock: return analyze(self.assets.resolve(asset),self.executor.stop_event)
    def master(self,data):
        from .audio import master
        request=MasterRequest.model_validate_json(__import__('json').dumps(data))
        with self.audio_lock:
            report,files=master(self.assets.resolve(request.asset),self.assets.exports,request,self.executor.stop_event)
            output=[self.assets.add_output(f,kind="report" if f.suffix==".json" else "audio") for f in files]
            return {"report":report,"files":output}
    def compare(self,a,b):
        from .audio import compare
        with self.audio_lock: return compare(self.assets.resolve(a),self.assets.resolve(b),self.executor.stop_event)
    def create_midi(self,data):
        from .creative import export_sketch
        if set(data)-{"bpm","key","bars","seed","swing"}: raise PlanError("Unknown MIDI setting")
        path,report=export_sketch(self.assets.exports,**data)
        return {"file":self.assets.add_output(path,kind="midi"),"report":report}
    def reconcile(self,data):
        with self.executor.mutex:
            return self._reconcile_locked(data)
    def _reconcile_locked(self,data):
        if set(data)!={"digest","acknowledge"} or data["acknowledge"] is not True:
            raise PlanError("Explicit acknowledgment and fresh inspection digest required")
        if self.executor.running: raise PlanError("Cannot reconcile a running operation")
        if not self.last_snapshot or time.time()-self.last_snapshot["at"]>60:
            raise PlanError("Inspect the current session first")
        if data["digest"]!=self.last_snapshot["digest"]: raise PlanError("Inspection does not match")
        snapshot=self.adapter.snapshot()
        current=digest({"session":snapshot["session"],"tracks":snapshot["tracks"]})
        if current!=data["digest"]: raise PlanError("State changed since reconciliation inspection")
        self.journal.reconcile({"snapshot":current,"session":snapshot["session"],"user_acknowledged":True})
        return {"reconciled":True,"rollback_performed":False}
    def restore_preview(self,data):
        from .recovery import prepare_restore
        if set(data)!={"plan_id"} or not isinstance(data["plan_id"],str):
            raise PlanError("Expected the source plan_id only")
        return prepare_restore(self.executor,data["plan_id"])
    def control_test_preview(self,data):
        if set(data)!={"track"}: raise PlanError("Expected a non-master track only")
        return self._control_test_result(data["track"])
    def _control_test_result(self,track):
        from .recovery import prepare_control_test
        return {"plan":prepare_control_test(self.executor,track)}
    def diagnostics(self,export=False):
        from .diagnostics import diagnose,export_report
        report=diagnose(self)
        return export_report(self,report) if export else report
    def plugin_scan(self,data):
        from .plugin_workbench import ScanRequest
        return self.workbench.scan(ScanRequest.model_validate_json(__import__('json').dumps(data)))
    def plugin_preview(self,data):
        from .plugin_workbench import ParameterPreview
        return self.workbench.preview(ParameterPreview.model_validate_json(__import__('json').dumps(data)))
    def parameters(self,track,slot):
        from .plugin_workbench import ScanRequest
        request=ScanRequest(track=track,slot=slot)
        with self.executor.mutex:
            return self.adapter.parameters(request.track,request.slot)
    def review_audio(self,data):
        import json
        import shutil
        from .review_contracts import ReviewRequest
        from .review import build_review,link_evidence
        request=ReviewRequest.model_validate_json(json.dumps(data))
        linked=link_evidence(self.journal,request.linked_plan_id)
        with self.audio_lock:
            report,paths,folder=build_review(self.assets,request,self.assets.exports,self.executor.stop_event,linked)
            records=[]
            try:
                records=self.assets.add_outputs([(p,None,"report" if p.suffix==".json" else "audio") for p in paths])
                return self.reviews.add(report,records)
            except Exception:
                if records:
                    self.assets.discard_outputs({r["id"] for r in records})
                shutil.rmtree(folder,ignore_errors=True)
                raise
    def review_decision(self,data):
        import json
        from .review_contracts import ReviewDecision
        return self.reviews.decide(ReviewDecision.model_validate_json(json.dumps(data)))
    def review_get(self,data):
        import json
        from .review_contracts import ReviewID
        request=ReviewID.model_validate_json(json.dumps(data))
        return self.reviews.get(request.review_id)
    def render_watch(self,data):
        return self.render_workflow.start(data)
    def render_watch_status(self):
        return self.render_workflow.status()
    def render_watch_cancel(self,data):
        return self.render_workflow.cancel(data)
    def close(self):
        self.executor.stop_event.set(); self.jobs.close(); self.reviews.close(); self.journal.close()
