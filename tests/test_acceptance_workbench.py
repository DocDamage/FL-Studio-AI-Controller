"""Contract doubles and actual synthetic review files, never native FL acceptance."""
import io
import json
import threading
import time
import urllib.error
import urllib.request

import numpy as np
import pytest
import soundfile as sf

from flcopilot.acceptance_workbench import AcceptanceWorkbench
from flcopilot.assets import atomic_json
from flcopilot.contracts import PlanError, Stopped
from flcopilot.demo import DemoAdapter
from flcopilot.render_acceptance import REQUIRED_TESTS, load_record, validate_record
from flcopilot.server import LocalServer
from flcopilot.service import Service


@pytest.fixture
def service(tmp_path):
    s = Service(tmp_path / 'workspace', DemoAdapter())
    yield s
    s.close()


def save(s, fields=None, assets=None, review_id=None, revision=None):
    return s.acceptance.save({'expected_revision': revision or s.acceptance.get()['revision'],
        'fields': fields or {}, 'assets': assets or [], 'review_id': review_id})


def export(s, completed=False, revision=None):
    return s.acceptance.export({'expected_revision': revision or s.acceptance.get()['revision'],
                               'completed': completed, 'confirm': True})


def native_double(s, monkeypatch):
    """Explicitly synthetic native-platform/bridge eligibility, not a live test."""
    monkeypatch.setattr(s.adapter, 'name', 'postfader')
    monkeypatch.setattr(s.adapter, 'connection', lambda: {
        'connected': True, 'compatible': True, 'session_fingerprint': 'synthetic-session'})
    monkeypatch.setattr('flcopilot.acceptance_workbench.runtime', lambda service: {
        'app_mode': 'live', 'python_version': '3.13.5', 'postfader_version': '10.0.0',
        'native_host_eligible': True})


def evidence(s, same_watch=False, manual=False):
    samples = np.random.default_rng(84).normal(0, .04, (24000, 2))
    ids = []
    for n, gain in enumerate((1, .7)):
        stream = io.BytesIO()
        sf.write(stream, samples * gain, 8000, format='WAV', subtype='FLOAT')
        raw = stream.getvalue()
        ids.append(s.assets.import_stream(io.BytesIO(raw), len(raw), f'Private-source-{n}.wav',
            metadata=None if manual else {'source': 'watched_fl_export',
            'watch_id': ('a' if same_watch else 'ab'[n]) * 32})['id'])
    review = s.review_audio({'baseline': ids[0], 'candidate': ids[1],
        'confirm_same_range': True, 'title': 'Synthetic acceptance pair'})
    assert review['report']['status'] == 'ready'
    return ids, review


def completed_draft(s, ids, review):
    return save(s, {'windows_build': 'Test build', 'fl_studio_build': 'Test FL build',
        'saved_project_copy_confirmed': True, 'tests': dict.fromkeys(REQUIRED_TESTS, 'pass')},
        ids, review['review_id'])


def test_initial_state_no_invented_observations(service):
    state = service.acceptance.get()
    assert state['revision'] == 1 and not state['load_error']
    assert set(state['checks']) == set(REQUIRED_TESTS)
    assert set(state['record']['tests'].values()) == {'not_run'}
    assert state['record']['captures'] == []
    assert state['runtime']['app_mode'] == 'demo'
    assert state['runtime']['native_host_eligible'] is False


def test_get_is_defensive_copy(service):
    state = service.acceptance.get()
    state['record']['tests']['cancel_watch'] = 'pass'
    assert service.acceptance.get()['record']['tests']['cancel_watch'] == 'not_run'


def test_save_restart_roundtrip_without_folder_rearm(service):
    state = save(service, {'private_notes': ['Private test note'], 'project_label': 'Disposable'})
    assert state['revision'] == 2
    again = AcceptanceWorkbench(service).get()
    assert again['record']['private_notes'] == ['Private test note']
    assert again['revision'] == 2
    assert service.render_watch_status()['watch'] is None


def test_stale_save_and_export_refused(service):
    save(service)
    for action in (lambda: save(service, {'notes': ['overwrite']}, revision=1),
                   lambda: export(service, revision=1)):
        with pytest.raises(PlanError, match='another view'):
            action()
    assert service.acceptance.get()['record']['notes'] == []
    assert not service.assets.list()


@pytest.mark.parametrize('field,value', [('status','pass'), ('captures',[]), ('evidence_sha256',{}),
    ('app_mode','live'), ('python_version','invented'), ('postfader_version','invented'),
    ('folder',r'D:\secret'), ('privacy','safe'), ('unknown',True)])
def test_protected_or_unknown_fields_refused(service, field, value):
    with pytest.raises(PlanError):
        save(service, {field: value})


@pytest.mark.parametrize('changes', [
    {'expected_revision': True}, {'assets': ['x']}, {'assets': ['a'*32, 'a'*32]},
    {'assets': ['a'*32]*3}, {'assets': 'a'*32}, {'review_id': 'bad'},
    {'fields': {'tests': {'cancel_watch': 'pass'}}},
    {'fields': {'saved_project_copy_confirmed': 1}}, {'unexpected': True},
])
def test_invalid_drafts_refused_without_writes(service, changes):
    payload = {'expected_revision': 1, 'fields': {}, 'assets': []}
    payload.update(changes)
    with pytest.raises((ValueError, PlanError)):
        service.acceptance.save(payload)
    assert not service.acceptance.path.exists()


def test_save_failure_preserves_memory_and_disk(service, monkeypatch):
    save(service, {'project_label': 'Keep this'})
    original = service.acceptance.path.read_bytes()
    def fail(*args):
        raise OSError('disk unavailable')
    monkeypatch.setattr('flcopilot.acceptance_workbench.atomic_json', fail)
    with pytest.raises(OSError):
        save(service, {'project_label': 'Not saved'})
    assert service.acceptance.path.read_bytes() == original
    assert service.acceptance.get()['record']['project_label'] == 'Keep this'


@pytest.mark.parametrize('payload', ['{', 'null', '[]', '{"revision":0}',
    '{"revision":1,"record":{},"assets":[],"review_id":null}'])
def test_corrupt_draft_preserved_and_app_remains_usable(tmp_path, payload):
    path = tmp_path / 'render-acceptance-draft.json'
    path.write_text(payload)
    s = Service(tmp_path, DemoAdapter())
    try:
        assert s.acceptance.get()['load_error'] is True
        assert s.status()['demo'] is True
        with pytest.raises(PlanError, match='unreadable'):
            save(s)
        assert path.read_text() == payload
    finally:
        s.close()


def test_progress_export_is_private_field_filtered_and_cli_loadable(service):
    save(service, {'project_label':'PRIVATE PROJECT', 'private_notes':['SECRET'],
                   'notes':['Shared observation'], 'interface_and_driver':'PRIVATE DEVICE'})
    result = export(service)
    assert result['record']['status'] == 'not_run'
    assert result['record']['captures'] == []
    raw = service.assets.resolve(result['file']['id']).read_text()
    assert all(s not in raw for s in ['SECRET', 'PRIVATE PROJECT', 'PRIVATE DEVICE'])
    assert 'Shared observation' in raw
    assert 'path' not in result['file']
    assert load_record(service.assets.resolve(result['file']['id']))['status'] == 'not_run'
    assert result['project_changed'] is False


@pytest.mark.parametrize('result', ['fail', 'blocked'])
def test_progress_status_records_failed_or_blocked_observations(service, result):
    tests = dict.fromkeys(REQUIRED_TESTS, 'pass'); tests['cancel_watch'] = result
    save(service, {'tests': tests})
    assert export(service)['record']['status'] == result


def test_every_box_passed_is_not_an_automatic_pass(service):
    save(service, {'tests': dict.fromkeys(REQUIRED_TESTS, 'pass')})
    assert export(service)['record']['status'] == 'not_run'
    with pytest.raises(PlanError, match='native Windows'):
        export(service, completed=True)


@pytest.mark.parametrize('confirm', [False, 1, 'true', None])
def test_explicit_boolean_export_consent_required(service, confirm):
    with pytest.raises((ValueError, PlanError)):
        service.acceptance.export({'expected_revision': 1, 'confirm': confirm})
    assert not service.assets.list()


def test_stop_blocks_export_but_allows_checklist_save(service):
    service.executor.stop()
    assert save(service)['revision'] == 2
    with pytest.raises(Stopped):
        export(service)
    assert not service.assets.list()


def test_completed_export_requires_selected_evidence(service, monkeypatch):
    native_double(service, monkeypatch)
    with pytest.raises(PlanError, match='Select two'):
        export(service, completed=True)


def test_completed_export_binds_actual_capture_and_review_hashes(service, monkeypatch):
    native_double(service, monkeypatch)
    ids, review = evidence(service)
    completed_draft(service, ids, review)
    result = export(service, completed=True)
    validate_record(result['record'])
    assert result['record']['status'] == 'pass'
    assert {c['asset'] for c in result['record']['captures']} == set(ids)
    assert all(c['copied_bytes_verified'] and not c['causal_provenance_verified'] for c in result['record']['captures'])
    assert result['record']['evidence_sha256']['Review_Report.json'] == next(
        f['sha256'] for f in review['files'] if f['kind'] == 'report')
    assert 'Private-source' not in json.dumps(result)
    assert 'synthetic-session' not in json.dumps(result)
    assert service.acceptance.get()['record']['status'] == 'not_run'
    assert AcceptanceWorkbench(service).get()['record']['captures'] == []


@pytest.mark.parametrize('mode', ['same_watch', 'manual', 'tampered_source', 'tampered_review',
                                  'wrong_review', 'not_ready', 'missing_output', 'missing_pass', 'unsaved_project'])
def test_completed_evidence_failures_publish_no_report(service, monkeypatch, mode):
    native_double(service, monkeypatch)
    ids, review = evidence(service, same_watch=mode=='same_watch', manual=mode=='manual')
    completed_draft(service, ids, review)
    if mode == 'tampered_source':
        service.assets.resolve(ids[0]).write_bytes(b'tampered')
    if mode == 'tampered_review':
        f = next(f for f in review['files'] if f['kind']=='report')
        service.assets.resolve(f['id']).write_bytes(b'{}')
    if mode == 'missing_output':
        service.assets.resolve(review['files'][0]['id']).unlink()
    if mode in ('wrong_review', 'not_ready'):
        report = review['report'].copy()
        report['baseline_asset' if mode=='wrong_review' else 'status'] = 'c'*32 if mode=='wrong_review' else 'blocked'
        service.reviews.db.execute('UPDATE reviews SET report=? WHERE id=?', (json.dumps(report), review['review_id']))
        service.reviews.db.commit()
    if mode == 'missing_pass':
        tests = dict.fromkeys(REQUIRED_TESTS, 'pass'); tests['cancel_watch']='not_run'
        save(service, {'tests': tests}, ids, review['review_id'])
    if mode == 'unsaved_project':
        save(service, {'saved_project_copy_confirmed': False}, ids, review['review_id'])
    before = len(service.assets.list())
    with pytest.raises((ValueError, PlanError, OSError)):
        export(service, completed=True)
    assert len(service.assets.list()) == before
    assert not list(service.assets.exports.glob('Render_Acceptance_*'))


@pytest.mark.parametrize('connection', [
    {'connected':False,'compatible':True,'session_fingerprint':'x'},
    {'connected':True,'compatible':False,'session_fingerprint':'x'},
    {'connected':True,'compatible':True,'session_fingerprint':None},
])
def test_disconnected_or_incompatible_host_refused(service, monkeypatch, connection):
    native_double(service, monkeypatch)
    monkeypatch.setattr(service.adapter, 'connection', lambda: connection)
    with pytest.raises(PlanError, match='connected, compatible'):
        export(service, completed=True)


def test_changed_live_session_refuses_publication(service, monkeypatch):
    native_double(service, monkeypatch)
    ids, review = evidence(service); completed_draft(service, ids, review)
    sessions = iter(('old', 'new'))
    monkeypatch.setattr(service.adapter, 'connection', lambda: {
        'connected':True, 'compatible':True, 'session_fingerprint':next(sessions)})
    with pytest.raises(PlanError, match='session changed'):
        export(service, completed=True)
    assert not list(service.assets.exports.glob('Render_Acceptance_*'))


def test_failed_output_publication_cleans_up(service, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('manifest failure')
    monkeypatch.setattr(service.assets, 'add_output', fail)
    with pytest.raises(OSError):
        export(service)
    assert not list(service.assets.exports.glob('Render_Acceptance_*'))


def test_http_auth_save_export_and_script(service):
    server = LocalServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    def call(path, data=None, auth=True):
        headers={'Content-Type':'application/json'}
        if auth: headers['Authorization']='Bearer '+server.token
        request=urllib.request.Request(server.origin+path, headers=headers,
            data=json.dumps(data).encode() if data is not None else None)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            error.close(); raise
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            call('/api/render-acceptance', auth=False)
        assert exc.value.code == 403
        state=json.loads(call('/api/render-acceptance'))
        state=json.loads(call('/api/render-acceptance', {'expected_revision':state['revision'],
            'fields':{'notes':['HTTP checked']}, 'assets':[]}))
        job=json.loads(call('/api/render-acceptance-export', {
            'expected_revision':state['revision'], 'confirm':True}))
        for _ in range(100):
            result=json.loads(call('/api/jobs/'+job['job']))
            if result['status'] in ('complete','error'): break
            time.sleep(.02)
        assert result['status']=='complete'
        assert result['result']['record']['notes']==['HTTP checked']
        assert b'acceptanceState' in call('/acceptance.js', auth=False)
        assert b'Native export test checklist' in call('/', auth=False)
    finally:
        server.shutdown(); thread.join(timeout=2); server.server_close()


def test_checks_copy_cannot_modify_global_descriptions(service):
    state = service.acceptance.get()
    state['checks']['cancel_watch'] = 'untrusted'
    assert service.acceptance.get()['checks']['cancel_watch'] != 'untrusted'


def test_review_output_removed_from_database_is_refused(service, monkeypatch):
    native_double(service, monkeypatch)
    ids, review = evidence(service); completed_draft(service, ids, review)
    service.reviews.db.execute('UPDATE reviews SET files=? WHERE id=?',
        (json.dumps([f for f in review['files'] if f['kind']=='report']), review['review_id']))
    service.reviews.db.commit()
    with pytest.raises(PlanError, match='level-matched outputs'):
        export(service, completed=True)


def test_source_changed_during_review_verification_is_refused(service, monkeypatch):
    native_double(service, monkeypatch)
    ids, review = evidence(service); completed_draft(service, ids, review)
    path = service.assets.resolve(ids[0]); original_resolve = service.assets.resolve
    report_id = next(f['id'] for f in review['files'] if f['kind']=='report')
    def change_on_review(ident, **kwargs):
        if ident == report_id:
            path.write_bytes(b'changed after the first hash')
        return original_resolve(ident, **kwargs)
    monkeypatch.setattr(service.assets, 'resolve', change_on_review)
    with pytest.raises(PlanError, match='missing, changed, or unreadable'):
        export(service, completed=True)
    assert not list(service.assets.exports.glob('Render_Acceptance_*'))


def test_stopped_after_writing_report_cleans_up(service, monkeypatch):
    original = atomic_json
    def latch_stop(path, payload):
        original(path, payload)
        service.executor.stop()
    monkeypatch.setattr('flcopilot.acceptance_workbench.atomic_json', latch_stop)
    with pytest.raises(Stopped):
        export(service)
    assert not list(service.assets.exports.glob('Render_Acceptance_*'))
    assert not service.assets.list()


def test_completion_does_not_enable_executor_writes_or_add_mcp_tool(service, monkeypatch):
    from flcopilot.mcp_relay import TOOLS
    native_double(service, monkeypatch)
    ids, review = evidence(service); completed_draft(service, ids, review)
    before_mode = service.executor.mode
    export(service, completed=True)
    assert service.executor.mode == before_mode
    assert not service.journal.history()
    assert not any('acceptance' in t['name'] for t in TOOLS)
