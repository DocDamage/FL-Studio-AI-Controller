import json
import pytest
from flcopilot.acceptance import (
    AcceptanceError, OPTIONAL_TESTS, PRIVATE_FIELDS, REQUIRED_TESTS,
    hash_evidence, load_record, public_record, validate_record, write_public_record,
)

def record(status="not_run"):
    tests={name:"not_run" for name in REQUIRED_TESTS + OPTIONAL_TESTS}
    return {
        "schema_version":"1.0","status":status,"date":None,"windows_build":None,
        "fl_studio_build":None,"python_version":None,"postfader_version":None,
        "midi_provider":"private provider","midi_endpoint":"private endpoint",
        "interface_and_driver":"private interface","display_scaling":150,
        "tests":tests,"notes":[],"evidence_sha256":{},
    }

def test_not_run_record_validates():
    assert validate_record(record())["status"]=="not_run"

def test_pass_requires_host_metadata_and_all_required_results():
    data=record("pass")
    data.update(date="2026-09-19",windows_build="26100",fl_studio_build="26.1.3.5336",
                python_version="3.13.7",postfader_version="10.0.0")
    for name in REQUIRED_TESTS: data["tests"][name]="pass"
    assert validate_record(data)["status"]=="pass"
    data["tests"]["live_readonly_handshake"]="blocked"
    with pytest.raises(AcceptanceError,match="every required"): validate_record(data)

def test_missing_and_unknown_tests_refused():
    data=record(); del data["tests"]["stop_hotkey"]
    with pytest.raises(AcceptanceError,match="missing tests"): validate_record(data)
    data=record(); data["tests"]["invented"]="pass"
    with pytest.raises(AcceptanceError,match="unknown tests"): validate_record(data)

def test_bad_result_and_scaling_refused():
    data=record(); data["tests"]["fresh_install"]="yes"
    with pytest.raises(AcceptanceError,match="invalid test result"): validate_record(data)
    data=record(); data["display_scaling"]=501
    with pytest.raises(AcceptanceError,match="display_scaling"): validate_record(data)

def test_public_record_removes_host_private_fields():
    shared=public_record(record())
    assert not (PRIVATE_FIELDS & set(shared))
    assert "privacy" in shared
    assert shared["tests"]["fresh_install"]=="not_run"

def test_hash_and_public_write(tmp_path):
    evidence=tmp_path/"receipt.json"; evidence.write_bytes(b'{"verified":true}')
    digest=hash_evidence(evidence)
    data=record(); data["evidence_sha256"]["receipt.json"]=digest
    output=write_public_record(data,tmp_path/"public"/"acceptance.json")
    saved=json.loads(output.read_text())
    assert saved["evidence_sha256"]["receipt.json"]==digest
    assert "midi_endpoint" not in saved

def test_load_rejects_invalid_json_and_accepts_bom(tmp_path):
    bad=tmp_path/"bad.json"; bad.write_text("{")
    with pytest.raises(AcceptanceError,match="valid JSON"): load_record(bad)
    good=tmp_path/"good.json"
    good.write_text("\ufeff"+json.dumps(record()),encoding="utf-8")
    assert load_record(good)["schema_version"]=="1.0"

def test_evidence_hash_format_is_strict():
    data=record(); data["evidence_sha256"]["x"]="A"*64
    with pytest.raises(AcceptanceError,match="evidence hash"): validate_record(data)
