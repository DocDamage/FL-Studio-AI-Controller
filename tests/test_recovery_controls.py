import copy
import json
import pytest
from pydantic import ValidationError
from flcopilot.contracts import Approval, Locks, NotDispatched, Operation, PlanError, PrepareRequest
from flcopilot.demo import DemoAdapter
from flcopilot.service import Service


@pytest.fixture
def service(tmp_path):
    instance=Service(tmp_path,DemoAdapter())
    instance.executor.configure("assist",Locks())
    yield instance
    instance.close()


def run(service, operations):
    plan=service.prepare({"operations":operations})
    result=service.execute({"plan_id":plan["id"],"digest":plan["digest"],"confirm":True})
    return plan,result


def approve(service, plan):
    return service.execute({"plan_id":plan["id"],"digest":plan["digest"],"confirm":True})


@pytest.mark.parametrize("value",[0,1,"true","false",2.,None])
def test_mute_rejects_non_boolean(value):
    with pytest.raises(ValidationError): Operation(kind="mute",track=1,value=value)


@pytest.mark.parametrize("value",[True,False])
def test_mute_roundtrip(service,value):
    plan,result=run(service,[{"kind":"mute","track":1,"value":value}])
    assert result["status"]=="verified" and service.adapter.track(1)["muted"] is value


@pytest.mark.parametrize("value",[-1.,0.,1.])
def test_stereo_roundtrip(service,value):
    _,result=run(service,[{"kind":"stereo","track":1,"value":value}])
    assert result["status"]=="verified" and service.adapter.track(1)["stereo_separation"]==value


@pytest.mark.parametrize("value",[-1.01,1.01,float("nan"),float("inf"),True,"0"])
def test_stereo_invalid(value):
    with pytest.raises(ValidationError): Operation(kind="stereo",track=1,value=value)


@pytest.mark.parametrize("kind,value",[("mute",True),("stereo",.5)])
def test_new_control_locks(service,kind,value):
    for track in (0,1):
        service.executor.locks=Locks(tracks=(1,))
        with pytest.raises(NotDispatched): service.prepare({"operations":[{"kind":kind,"track":track,"value":value}]})
    assert not service.adapter.calls


def test_full_verified_control_restore(service):
    original=copy.deepcopy(service.adapter.tracks)
    operations=[{"kind":"volume","track":1,"value":-4.}, {"kind":"pan","track":1,"value":-.2},
        {"kind":"rename","track":1,"value":"New name"},{"kind":"mute","track":1,"value":True},
        {"kind":"stereo","track":1,"value":.6},{"kind":"parameter","track":1,"slot":0,"parameter":0,"value":.3}]
    source,result=run(service,operations)
    assert result["status"]=="verified"
    inverse=service.restore_preview({"plan_id":source["id"]})
    assert len(service.adapter.calls)==6 and inverse["project_rollback"] is False
    assert inverse["plan"]["purpose"]=="restore" and inverse["plan"]["source_plan_id"]==source["id"]
    restored=approve(service,inverse["plan"])
    assert restored["status"]=="verified" and service.adapter.tracks==original
    assert service.adapter.parameter(1,0,0)["value"]==.5
    with pytest.raises(PlanError): approve(service,inverse["plan"])


@pytest.mark.parametrize("mutation",["track","parameter","session","lock","unknown"])
def test_restore_stale_or_locked_refuses(service,mutation):
    source,result=run(service,[{"kind":"volume","track":1,"value":-4.},
        {"kind":"parameter","track":1,"slot":0,"parameter":0,"value":.3}])
    if mutation=="track": service.adapter.tracks[1]["pan"]=.2
    if mutation=="parameter": service.adapter.params[(1,0,0)]["value"]=.6
    if mutation=="session": service.adapter.session="e"*32
    if mutation=="lock": service.executor.locks=Locks(tracks=(1,))
    if mutation=="unknown": service.journal.block("lost reply")
    prior=len(service.journal.history())
    with pytest.raises(PlanError): service.restore_preview({"plan_id":source["id"]})
    assert len(service.adapter.calls)==2 and len(service.journal.history())==prior


def test_restore_plugin_insertion_unavailable(service):
    source,result=run(service,[{"kind":"load_effect","track":2,"value":"Fruity Limiter"}])
    assert result["status"]=="verified"
    with pytest.raises(PlanError,match="insertion"): service.restore_preview({"plan_id":source["id"]})


def test_restore_ready_plan_unavailable(service):
    p=service.prepare({"operations":[{"kind":"volume","track":1,"value":-4.}]})
    with pytest.raises(PlanError,match="fully verified"): service.restore_preview({"plan_id":p["id"]})


def test_control_test_requires_two_approvals(service):
    original=service.adapter.track(1)["volume_db"]
    source=service.control_test_preview({"track":1})["plan"]
    assert source["purpose"]=="control_test" and not service.adapter.calls
    assert approve(service,source)["status"]=="verified"
    assert service.adapter.track(1)["volume_db"]==original-1
    inverse=service.restore_preview({"plan_id":source["id"]})["plan"]
    assert len(service.adapter.calls)==1
    assert approve(service,inverse)["status"]=="verified"
    assert service.adapter.track(1)["volume_db"]==original


@pytest.mark.parametrize("track",[0,-1,True,"1",1000])
def test_control_test_master_or_bad_track(service,track):
    with pytest.raises(PlanError): service.control_test_preview({"track":track})
    assert not service.adapter.calls


def test_inspect_blocks_control_test_execution(service):
    service.executor.configure("inspect",Locks())
    p=service.control_test_preview({"track":1})["plan"]
    with pytest.raises(NotDispatched): approve(service,p)
    assert not service.adapter.calls


def test_failure_of_getter_after_dispatch_is_unknown(service):
    original=service.adapter.execute
    def gone(*args):
        receipt=original(*args)
        service.adapter.track=lambda _:(_ for _ in ()).throw(NotDispatched("Getter failed"))
        return receipt
    service.adapter.execute=gone
    _,result=run(service,[{"kind":"volume","track":1,"value":-4.}])
    assert result["status"]=="unknown_outcome" and service.journal.blocked()
    assert service.adapter.tracks[1]["volume_db"]==-4. and len(service.adapter.calls)==1


@pytest.mark.parametrize("corruption",["session","unrelated_control","nan","infinity","boolean"])
def test_bad_postdispatch_evidence_blocks_next_write(service,corruption):
    original=service.adapter.execute
    def corrupt(*args):
        receipt=original(*args)
        if corruption=="session": receipt["session_fingerprint"]="e"*32
        if corruption=="unrelated_control": service.adapter.tracks[1]["muted"]=True
        if corruption=="nan": service.adapter.tracks[1]["volume_db"]=float("nan")
        if corruption=="infinity": service.adapter.tracks[1]["volume_db"]=float("inf")
        if corruption=="boolean": service.adapter.tracks[1]["volume_db"]=True
        return receipt
    service.adapter.execute=corrupt
    _,result=run(service,[{"kind":"volume","track":1,"value":-4.},{"kind":"volume","track":2,"value":-6.}])
    assert result["status"]=="unknown_outcome" and len(service.adapter.calls)==1
    assert service.journal.blocked()


def test_relative_prompt_stale_context_is_refused(service):
    original=service.planner.plan
    def mutate(*args):
        result=original(*args)
        service.adapter.tracks[1]["volume_db"]=-8.
        return result
    service.planner.plan=mutate
    with pytest.raises(PlanError,match="changed"): service.prompt("Lower Drums by 2 dB")
    assert not service.journal.history() and not service.adapter.calls


@pytest.mark.parametrize("text,kind,value",[("Mute Drums","mute",True),("Unmute track 1","mute",False),
    ("Set track 1 stereo separation to 0.5","stereo",.5)])
def test_offline_parser_new_controls(service,text,kind,value):
    result=service.prompt(text)
    op=result["plan"]["operations"][0]
    assert (op["kind"],op["value"])==(kind,value) and not service.adapter.calls


def test_legacy_receipt_cannot_claim_new_restore_coverage(service):
    source,result=run(service,[{"kind":"volume","track":1,"value":-4.}])
    del result['receipts'][0]['after']['track']['stereo_separation']
    with service.journal.db:
        service.journal.db.execute('UPDATE plans SET result=? WHERE id=?',(json.dumps(result),source['id']))
    with pytest.raises(PlanError,match='older run'):service.restore_preview({'plan_id':source['id']})
    assert len(service.adapter.calls)==1


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),True,None])
def test_nonfinite_or_missing_source_fader_is_refused(service,bad):
    service.adapter.tracks[1]['volume_db']=bad
    with pytest.raises(PlanError):service.prepare({'operations':[{'kind':'volume','track':1,'value':-4.}]})
    assert not service.adapter.calls


def test_control_test_state_changes_during_preparation_are_refused(service):
    original=service.adapter.track
    def changed(index):
        service.adapter.tracks[1]['volume_db']=-5.
        return original(index)
    service.adapter.track=changed
    with pytest.raises(PlanError,match='Captured controls changed'):service.control_test_preview({'track':1})
    assert not service.journal.history() and not service.adapter.calls
