import copy
import json
import sys
import types
import pytest
from flcopilot.demo import DemoAdapter
from flcopilot.service import Service
from flcopilot.contracts import Locks
from flcopilot.diagnostics import diagnose, export_report, match_endpoints, midi_inventory


@pytest.fixture
def service(tmp_path):
    s=Service(tmp_path,DemoAdapter())
    yield s
    s.close()


@pytest.fixture
def environment():
    return {"packages":{"postfader-fl-studio-mcp":"10.0.0"},"python":"3.13.5","python_bits":64,
            "platform":"win32","ffmpeg_present":True,"hardware_directory_present":True,
            "bridge_file_present":True,"midi":{"available":True,"inputs":["PRIVATE DEVICE"],"outputs":["PRIVATE DEVICE"]},
            "selected_endpoint":"PRIVATE DEVICE","midi_enabled":True,"user_data":"C:/Users/PRIVATE USER/FL Data"}


def connect(service):
    # Deliberately synthetic handshake for contract tests, never packaged as live evidence.
    service.adapter.name="postfader"
    connection=dict(connected=True,compatible=True,session_fingerprint="d"*32,
        bridge_provenance_verified=True,project_load_epoch=True,verified_writes_enabled=False)
    service.adapter.connection=lambda:connection.copy()
    return connection


@pytest.mark.parametrize("inputs,outputs,selected,wanted",[
    (["Port"],["Port"],"Port","matched"),(["Port"],["PORT"],"port","matched"),
    (["Port 1"],["Port 1"],"Port","missing_direction"),
    (["Port","PORT"],["Port"],"Port","ambiguous"),
    (["Port"],[],"Port","missing_direction"),([],[],"","missing_selection"),
    (["Port"],["Port"],None,"missing_selection"),(["Port"],["Port","port"],"Port","ambiguous")])
def test_exact_endpoint_resolution(inputs,outputs,selected,wanted):
    assert match_endpoints(inputs,outputs,selected)["status"]==wanted


def test_demo_never_qualifies_host(service,environment):
    before=copy.deepcopy(service.adapter.tracks)
    report=diagnose(service,environment)
    assert not report["live_read_ready"] and not report["live_write_preconditions_ready"]
    assert report["control_evidence"]["status"]=="not_observed"
    assert report["authorization_granted"] is False and service.adapter.tracks==before
    assert not service.adapter.calls and not service.adapter.writes


@pytest.mark.parametrize("field,value,ready",[
    ("connected",False,False),("compatible",False,False),
    ("session_fingerprint",None,False),("session_fingerprint","BAD",False),
    ("bridge_provenance_verified",False,False),("project_load_epoch",False,False),
    ("verified_writes_enabled",True,False),("verified_writes_enabled",None,False),
    ("verified_writes_enabled",False,True)])
def test_live_handshake_checks(service,environment,field,value,ready):
    c=connect(service);c[field]=value
    report=diagnose(service,environment)
    assert report["live_write_preconditions_ready"] is ready
    assert not report["authorization_granted"] and not service.adapter.calls


def test_block_and_stop_override_readiness(service,environment):
    connect(service)
    service.executor.stop()
    assert not diagnose(service,environment)["live_write_preconditions_ready"]
    service.executor.reset_stop();service.journal.block("unknown")
    assert not diagnose(service,environment)["live_write_preconditions_ready"]


def test_export_omits_private_data(service,environment):
    c=connect(service);c["error"]="PRIVATE SESSION NAME and a secret-token"
    report=diagnose(service,environment)
    output=export_report(service,report)
    text=service.assets.resolve(output["files"][0]["id"]).read_text()
    for private in ("PRIVATE USER","PRIVATE DEVICE","PRIVATE SESSION NAME","secret-token","d"*32):
        assert private not in text
    assert "local_details" not in json.loads(text)
    assert not service.adapter.calls


def test_diagnostic_getter_error_is_not_success(service,environment):
    connect(service)
    service.adapter.connection=lambda:(_ for _ in ()).throw(RuntimeError("device missing"))
    report=diagnose(service,environment)
    assert not report["live_read_ready"] and "device missing" in report["local_details"]["connection"]["error"]


def test_inventory_does_not_open_endpoints(monkeypatch):
    instances=[]
    class Device:
        def __init__(self): self.deleted=False;instances.append(self)
        def get_ports(self): return ["Port"]
        def open_port(self,*args): raise AssertionError("Enumeration may not open MIDI ports")
        def delete(self): self.deleted=True
    monkeypatch.setitem(sys.modules,"rtmidi",types.SimpleNamespace(MidiIn=Device,MidiOut=Device))
    inventory=midi_inventory()
    assert inventory["available"] and all(i.deleted for i in instances)


def test_inventory_releases_first_object_when_second_fails(monkeypatch):
    deleted=[]
    class Incoming:
        def delete(self): deleted.append(True)
    def fail(): raise RuntimeError("driver unavailable")
    monkeypatch.setitem(sys.modules,"rtmidi",types.SimpleNamespace(MidiIn=Incoming,MidiOut=fail))
    assert not midi_inventory()["available"] and deleted==[True]


def test_control_evidence_only_after_approved_complete_roundtrip(service,environment):
    connect(service);service.executor.configure("assist",Locks())
    p=service.control_test_preview({"track":1})["plan"]
    assert diagnose(service,environment)["control_evidence"]["status"]=="not_completed"
    def apply(plan): return service.execute({"plan_id":plan["id"],"digest":plan["digest"],"confirm":True})
    assert apply(p)["status"]=="verified"
    assert diagnose(service,environment)["control_evidence"]["status"]=="verified_reduction_only"
    restore=service.restore_preview({"plan_id":p["id"]})["plan"]
    assert apply(restore)["status"]=="verified"
    evidence=diagnose(service,environment)["control_evidence"]
    assert evidence["status"]=="verified_round_trip" and evidence["restore_plan_id"]==restore["id"]
