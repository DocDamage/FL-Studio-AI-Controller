"""One serialized executor, task-scoped authorization, no ambiguous replay."""
from __future__ import annotations
import json
import threading
import time
import uuid
from .controls import finite_control, verify_unchanged
from .contracts import Approval, Locks, NotDispatched, Plan, PlanError, Stopped, digest, public_plan

# Exclude meters/selection from change identity; they are observation, not target identity.
IDENTITY_FIELDS=("index","name","volume_db","volume_normalized","pan","muted","soloed","plugins","stereo_separation")
def stable_track(track):
    return {key:track.get(key) for key in IDENTITY_FIELDS}

class Executor:
    def __init__(self,adapter,journal):
        self.adapter=adapter
        self.journal=journal
        self.mutex=threading.RLock()
        self.stop_event=threading.Event()
        self.locks=Locks()
        self.mode="inspect"
        self.running=False
    def stop(self):
        self.stop_event.set()
        self.journal.event(None,"stop_requested",{"at":time.time()})
        return {"stopped":True,"note":"A command already in flight cannot be undone; no later command will start."}
    def reset_stop(self):
        if self.running: raise PlanError("Wait for the in-flight command to settle before reset.")
        self.stop_event.clear()
    def configure(self,mode,locks):
        if self.running: raise PlanError("Cannot change mode or locks during execution.")
        if mode not in ("inspect","assist","finish"): raise PlanError("Invalid mode")
        with self.mutex:
            if self.running: raise PlanError("Cannot change settings during execution")
            self.mode=mode; self.locks=locks
    def _guard(self,op):
        if op.track in self.locks.tracks: raise NotDispatched(f"Track {op.track} is locked")
        if op.track==0 and self.locks.master: raise NotDispatched("Master is locked")
        if op.kind=="parameter" and self.locks.parameters: raise NotDispatched("Plugin parameters are locked")
    def _before(self,op):
        row={"track":stable_track(self.adapter.track(op.track))}
        if op.kind=="parameter": row["parameter"]=self.adapter.parameter(op.track,op.slot,op.parameter)
        return row
    def prepare(self,request,*,expected_session=None,expected_before=None,purpose="adjustment",source_plan_id=None):
        with self.mutex:
            snapshot=self.adapter.snapshot()
            session=snapshot["session"]
            if not session: raise NotDispatched("No verifiable FL session")
            before=[]
            for op in request.operations:
                self._guard(op)
                state=self._before(op)
                if op.kind=="load_effect" and state["track"].get("plugins"):
                    raise NotDispatched("Experimental insertion requires a completely empty destination track.")
                if op.kind=="volume":
                    current=state["track"].get("volume_db")
                    if not finite_control(current): raise NotDispatched("FL did not report a finite fader value in dB")
                    if abs(op.value-current)>12.00001: raise NotDispatched("A single fader move is limited to 12 dB.")
                if op.kind == "mute" and type(state["track"].get("muted")) is not bool:
                    raise NotDispatched("No explicit mute-state readback")
                if op.kind == "stereo" and not finite_control(state["track"].get("stereo_separation")):
                    raise NotDispatched("No numeric stereo-separation readback")
                before.append(state)
            if self.adapter.connection().get("session_fingerprint") != session:
                raise NotDispatched("Session changed during planning")
            if expected_session is not None and expected_session != session:
                raise NotDispatched("Session changed since the source observation")
            if expected_before is not None and digest(before) != digest(expected_before):
                raise NotDispatched("Captured controls changed since the source observation; no restore/relative plan created")
            now=time.time()
            plan=Plan(id=uuid.uuid4().hex,created=now,expires=now+300.,session=session,
                backend=self.adapter.name,title=request.title,operations=request.operations,
                before=tuple(before),locks=self.locks,purpose=purpose,source_plan_id=source_plan_id)
            self.journal.add(plan)
            return public_plan(plan)
    def run(self,approval: Approval):
        with self.mutex:
            if self.mode=="inspect": raise NotDispatched("Inspect mode cannot execute changes. Select Assist or Finish first.")
            if self.stop_event.is_set(): raise Stopped("Emergency stop is latched. Reset it before a new run.")
            if self.journal.blocked(): raise NotDispatched(self.journal.blocked())
            row=self.journal.get(approval.plan_id)
            plan=Plan.model_validate_json(row["body"])
            if approval.digest != plan.digest: raise NotDispatched("Approval does not match the exact plan")
            if time.time()>plan.expires: raise NotDispatched("Plan expired; inspect and prepare a fresh one.")
            if plan.backend != self.adapter.name or plan.locks != self.locks:
                raise NotDispatched("Backend or protection locks changed")
            if self.adapter.connection().get("session_fingerprint") != plan.session:
                raise NotDispatched("Project/bridge session changed")
            for op,before in zip(plan.operations,plan.before):
                self._guard(op)
                if digest(self._before(op)) != digest(before): raise NotDispatched("Project target changed after preview")
            self.journal.claim(plan.id)
            self.running=True
            receipts=[]; status="verified"; error=None; gate_attempted=False
            try:
                gate_attempted=True
                self.adapter.begin(plan.session)
                # A fresh state after each verified change is the baseline for the next.
                expected={op.track:original["track"] for op,original in zip(plan.operations,plan.before)}
                for index,(op,original) in enumerate(zip(plan.operations,plan.before)):
                    if self.stop_event.is_set(): raise Stopped("Stopped before next operation")
                    if self.adapter.connection().get("session_fingerprint") != plan.session:
                        raise NotDispatched("Session changed before next operation")
                    self._guard(op)
                    before=self._before(op)
                    if digest(before["track"]) != digest(expected[op.track]):
                        raise NotDispatched("Target was changed outside the executor")
                    if op.kind=="parameter" and before["parameter"] != original["parameter"]:
                        raise NotDispatched("Plugin parameter identity/value changed")
                    self.journal.event(plan.id,"dispatch_intent",{"index":index,"operation":op.model_dump(),"before":before})
                    try:
                        receipt=self.adapter.execute(op,before,plan.session)
                    except NotDispatched:
                        # Only the adapter's pre-dispatch refusal can prove no write occurred.
                        raise
                    except Exception as exc:
                        raise RuntimeError(str(exc)) from exc
                    if receipt.get("verified") is not True:
                        if receipt.get("status")=="not_dispatched":
                            raise NotDispatched(str(receipt))
                        raise RuntimeError("FL did not verify the command: "+str(receipt))
                    try:
                        # Once dispatch returned, ANY missing readback means an unknown
                        # outcome, including a getter that raises NotDispatched.
                        if receipt.get("session_fingerprint") != plan.session:
                            raise RuntimeError("Receipt belongs to an unknown/different session")
                        if self.adapter.connection().get("session_fingerprint") != plan.session:
                            raise RuntimeError("Session changed after dispatch")
                        after=self._before(op)
                        self._verify_value(op,after)
                        verify_unchanged(op,before["track"],after["track"])
                        if op.kind=="parameter" and any(after["parameter"][k]!=original["parameter"][k] for k in ("plugin","name")):
                            raise RuntimeError("Plugin/control identity changed after dispatch")
                    except Exception as exc:
                        raise RuntimeError("Post-dispatch verification unavailable: "+str(exc)) from exc
                    self.journal.event(plan.id,"verified_readback",{"index":index,"receipt":receipt,"after":after})
                    receipts.append({"operation":op.model_dump(),"receipt":receipt,"after":after})
                    expected[op.track]=after["track"]
            except Stopped as exc:
                status="stopped"; error=str(exc)
            except NotDispatched as exc:
                status="blocked"; error=str(exc)
            except Exception as exc:
                status="unknown_outcome"; error=str(exc)
            finally:
                if gate_attempted:
                    try: self.adapter.end(plan.session)
                    except Exception as exc:
                        status="unknown_outcome"
                        error=(error or "")+"; write gate closure unverified: "+str(exc)
                self.running=False
            result={"status":status,"receipts":receipts,"error":error,"demo":self.adapter.name=="demo",
                "project_saved":False,"rollback_performed":False,"audible_quality_evaluated":False}
            self.journal.finish(plan.id,status,result)
            return result
    @staticmethod
    def _verify_value(op,after):
        t=after["track"]
        if op.kind=="volume" and (not finite_control(t.get("volume_db")) or abs(t["volume_db"]-op.value)>.11):
            raise RuntimeError("Independent fader readback mismatch")
        if op.kind=="pan" and (not finite_control(t.get("pan")) or abs(t["pan"]-op.value)>.01):
            raise RuntimeError("Independent pan readback mismatch")
        if op.kind=="mute" and (type(t.get("muted")) is not bool or t["muted"] != op.value):
            raise RuntimeError("Independent mute readback mismatch")
        if op.kind=="stereo" and (not finite_control(t.get("stereo_separation")) or abs(t["stereo_separation"]-op.value)>.01):
            raise RuntimeError("Independent stereo-separation readback mismatch")
        if op.kind=="rename" and t["name"]!=op.value: raise RuntimeError("Track name readback mismatch")
        if op.kind=="parameter" and (not finite_control(after["parameter"].get("value")) or abs(after["parameter"]["value"]-op.value)>.002):
            raise RuntimeError("Parameter readback mismatch")
        if op.kind=="load_effect":
            plugins=t.get("plugins",[])
            if len(plugins)!=1 or plugins[0]["name"].casefold().replace(" ","")!=op.value.casefold().replace(" ",""):
                raise RuntimeError("New plugin not unambiguously observed")
