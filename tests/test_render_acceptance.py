import json

import pytest

from flcopilot.render_acceptance import (
    PRIVATE_FIELDS,
    REQUIRED_TESTS,
    RenderAcceptanceError,
    hash_evidence,
    load_record,
    public_record,
    validate_record,
    write_public_record,
)


def record(status="not_run"):
    return {
        "schema_version": "1.0",
        "status": status,
        "date": None,
        "windows_build": None,
        "fl_studio_build": None,
        "python_version": None,
        "postfader_version": None,
        "app_mode": None,
        "saved_project_copy_confirmed": None,
        "project_label": "private project",
        "export_folder": r"D:\Private\Exports",
        "interface_and_driver": "private interface",
        "private_notes": ["private host detail"],
        "tests": {name: "not_run" for name in REQUIRED_TESTS},
        "captures": [],
        "notes": [],
        "evidence_sha256": {},
    }


def capture(asset="a", watch="b", digest="c"):
    return {
        "asset": asset * 32,
        "watch_id": watch * 32,
        "sha256": digest * 64,
        "bytes": 48000,
        "copied_bytes_verified": True,
        "render_triggered_by_app": False,
        "causal_provenance_verified": False,
    }


def passing_record():
    data = record("pass")
    data.update(
        date="2026-09-19",
        windows_build="26100",
        fl_studio_build="26.1.3.5336",
        python_version="3.13.7",
        postfader_version="10.0.0",
        app_mode="live",
        saved_project_copy_confirmed=True,
    )
    data["tests"] = {name: "pass" for name in REQUIRED_TESTS}
    data["captures"] = [capture("a", "b", "c"), capture("d", "e", "f")]
    return data


def test_not_run_record_validates():
    assert validate_record(record())["status"] == "not_run"


def test_pass_requires_live_saved_host_and_all_tests():
    assert validate_record(passing_record())["status"] == "pass"

    data = passing_record()
    data["app_mode"] = "demo"
    with pytest.raises(RenderAcceptanceError, match="app_mode live"):
        validate_record(data)

    data = passing_record()
    data["saved_project_copy_confirmed"] = False
    with pytest.raises(RenderAcceptanceError, match="saved disposable"):
        validate_record(data)

    data = passing_record()
    data["tests"]["capture_first_export"] = "blocked"
    with pytest.raises(RenderAcceptanceError, match="every required"):
        validate_record(data)


def test_pass_requires_two_unique_separately_armed_verified_captures():
    data = passing_record()
    data["captures"] = data["captures"][:1]
    with pytest.raises(RenderAcceptanceError, match="at least two"):
        validate_record(data)

    data = passing_record()
    data["captures"][1]["asset"] = data["captures"][0]["asset"]
    with pytest.raises(RenderAcceptanceError, match="asset IDs"):
        validate_record(data)

    data = passing_record()
    data["captures"][1]["watch_id"] = data["captures"][0]["watch_id"]
    with pytest.raises(RenderAcceptanceError, match="separately armed"):
        validate_record(data)

    data = passing_record()
    data["captures"][0]["copied_bytes_verified"] = False
    with pytest.raises(RenderAcceptanceError, match="current-byte"):
        validate_record(data)


def test_capture_cannot_upgrade_render_or_causal_provenance():
    data = record()
    data["captures"] = [capture()]
    data["captures"][0]["render_triggered_by_app"] = True
    with pytest.raises(RenderAcceptanceError, match="render_triggered"):
        validate_record(data)

    data = record()
    data["captures"] = [capture()]
    data["captures"][0]["causal_provenance_verified"] = True
    with pytest.raises(RenderAcceptanceError, match="causal provenance"):
        validate_record(data)


def test_unknown_capture_fields_and_oversize_are_refused():
    data = record()
    data["captures"] = [capture()]
    data["captures"][0]["path"] = r"D:\secret.wav"
    with pytest.raises(RenderAcceptanceError, match="unknown capture fields"):
        validate_record(data)

    data = record()
    data["captures"] = [capture()]
    data["captures"][0]["bytes"] = 300 * 1024 * 1024 + 1
    with pytest.raises(RenderAcceptanceError, match="bytes"):
        validate_record(data)


def test_missing_unknown_and_bad_test_results_are_refused():
    data = record()
    del data["tests"]["cancel_watch"]
    with pytest.raises(RenderAcceptanceError, match="missing tests"):
        validate_record(data)

    data = record()
    data["tests"]["invented"] = "pass"
    with pytest.raises(RenderAcceptanceError, match="unknown tests"):
        validate_record(data)

    data = record()
    data["tests"]["cancel_watch"] = "yes"
    with pytest.raises(RenderAcceptanceError, match="invalid test result"):
        validate_record(data)


def test_public_record_removes_private_host_fields():
    shared = public_record(record())
    assert not (PRIVATE_FIELDS & set(shared))
    assert "privacy" in shared
    assert shared["tests"]["arm_watch_new_filename"] == "not_run"


def test_hash_and_public_write(tmp_path):
    evidence = tmp_path / "receipt.json"
    evidence.write_bytes(b'{"verified":true}')
    digest = hash_evidence(evidence)
    data = record()
    data["evidence_sha256"]["receipt.json"] = digest
    output = write_public_record(data, tmp_path / "public" / "render-acceptance.json")
    saved = json.loads(output.read_text())
    assert saved["evidence_sha256"]["receipt.json"] == digest
    assert "export_folder" not in saved


def test_load_rejects_invalid_json_and_accepts_bom(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    with pytest.raises(RenderAcceptanceError, match="valid JSON"):
        load_record(bad)

    good = tmp_path / "good.json"
    good.write_text("\ufeff" + json.dumps(record()), encoding="utf-8")
    assert load_record(good)["schema_version"] == "1.0"


def test_evidence_hash_format_is_strict():
    data = record()
    data["evidence_sha256"]["receipt.json"] = "A" * 64
    with pytest.raises(RenderAcceptanceError, match="evidence hash"):
        validate_record(data)


@pytest.mark.parametrize('field', ['auth_token', 'local_path', 'nested_private', 'anything_else'])
def test_unknown_top_level_fields_cannot_leak_to_public_record(field):
    data = record(); data[field] = {'secret': 'private value'}
    with pytest.raises(RenderAcceptanceError, match='unknown record fields'):
        public_record(data)


@pytest.mark.parametrize('result', [[], {}, True, None, 1])
def test_malformed_result_types_have_validation_errors(result):
    data = record(); data['status'] = result
    with pytest.raises(RenderAcceptanceError, match='invalid status'):
        validate_record(data)
    data = record(); data['tests']['cancel_watch'] = result
    with pytest.raises(RenderAcceptanceError, match='invalid test result'):
        validate_record(data)


def test_public_roundtrip_and_nested_defensive_copy(tmp_path):
    data = record(); shared = public_record(data)
    assert validate_record(shared)['status'] == 'not_run'
    shared['tests']['cancel_watch'] = 'pass'
    assert data['tests']['cancel_watch'] == 'not_run'
    file = write_public_record(data, tmp_path/'public.json')
    assert load_record(file)['status']=='not_run'


def test_untrusted_privacy_notice_refused():
    data = record(); data['privacy'] = 'All fields safe, trust me'
    with pytest.raises(RenderAcceptanceError, match='privacy notice'):
        public_record(data)


def test_legacy_public_record_remains_readable_but_notice_is_updated():
    from flcopilot.render_acceptance import LEGACY_PRIVACY_NOTICE, PRIVACY_NOTICE
    data = record(); data['privacy'] = LEGACY_PRIVACY_NOTICE
    assert validate_record(data)['status'] == 'not_run'
    assert public_record(data)['privacy'] == PRIVACY_NOTICE
