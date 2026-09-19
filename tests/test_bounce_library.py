"""Durable bounce metadata, current-byte verification, and HTTP/MCP regressions."""
import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error

import pytest
from pydantic import ValidationError
from flcopilot.assets import atomic_json
from flcopilot.bounce_library import BounceEdit, BounceQuery
from flcopilot.contracts import PlanError, Stopped
from flcopilot.demo import DemoAdapter
from flcopilot.mcp_relay import TOOLS, tool_call
from flcopilot.service import Service
from test_service_http import app, call, poll


@pytest.fixture
def service(tmp_path):
    s = Service(tmp_path / 'workspace', DemoAdapter())
    yield s
    s.close()


def add(s, name='Bounce.wav', watched=False):
    metadata = {'source': 'watched_fl_export', 'watch_id': 'a'*32,
                'causal_provenance_verified': False, 'render_triggered_by_app': False} if watched else None
    return s.assets.import_stream(io.BytesIO(b'input bytes'), 11, name, metadata=metadata)


def edit_data(record, **kw):
    return {'asset': record['id'], 'expected_revision': 1, 'label': 'Drums - before',
            'note': 'Keep the transients.\nCheck low end.', **kw}


def test_import_records_real_time_and_size(service):
    before = time.time(); record = add(service)
    assert before <= record['imported_at'] <= time.time()
    assert record['bytes'] == 11


def test_restart_preserves_labels_notes_and_capture_identity(service):
    record = add(service, watched=True)
    result = service.bounces.edit(edit_data(record))
    assert result['revision'] == 2 and result['name'] == 'Bounce.wav'
    again = Service(service.assets.root, DemoAdapter())
    try:
        assert again.bounces.get({'asset': record['id']}) == result
        assert again.bounces.list({})['items'] == [result]
        assert again.render_watch_status()['watch'] is None  # No silent rearming.
        assert not again.adapter.calls
    finally:
        again.close()
    assert service.assets.resolve(record['id']).read_bytes() == b'input bytes'
    assert result['watch_id'] == 'a'*32 and not result['causal_provenance_verified']
    assert not service.adapter.calls and not service.journal.history()


def test_listing_is_pathless_detached_and_never_rehashes(service, monkeypatch):
    record = add(service)
    monkeypatch.setattr(service.assets, 'resolve', lambda *_: pytest.fail('listing must not read audio'))
    result = service.bounces.list({})
    assert 'path' not in result['items'][0]
    assert str(service.assets.root) not in json.dumps(result)
    assert 'Not rechecked' in result['integrity']
    result['items'][0]['label'] = 'mutated response'
    assert service.bounces.get({'asset': record['id']})['label'] == ''


def test_legacy_imports_have_unknown_dates_without_inventing_timestamps(service):
    record = add(service)
    service.assets.data[record['id']].pop('bytes')
    service.assets.data[record['id']].pop('imported_at')
    atomic_json(service.assets.manifest, service.assets.data)
    row = service.bounces.list({})['items'][0]
    assert row['imported_at'] is None and row['bytes'] is None and row['revision'] == 1
    service.bounces.edit(edit_data(record))
    assert service.bounces.get({'asset': record['id']})['imported_at'] is None


def test_library_excludes_outputs_and_rejects_them_for_all_actions(service):
    f = service.assets.exports / 'master.wav'; f.write_bytes(b'output')
    output = service.assets.add_output(f)
    assert service.bounces.list({})['total'] == 0
    for method, data in [(service.bounces.get, {'asset': output['id']}),
                         (service.bounces.verify, {'asset': output['id']}),
                         (service.bounces.edit, edit_data(output))]:
        with pytest.raises(PlanError, match='input bounce'): method(data)


def test_search_source_and_pagination_preserve_import_order(service):
    rows = [add(service, f'Bounce {i}.wav', watched=i%2 == 0) for i in range(5)]
    service.bounces.edit(edit_data(rows[0], label='First take', note='Straße bass'))
    first = service.bounces.list({'limit': 2})
    assert [r['id'] for r in first['items']] == [rows[4]['id'], rows[3]['id']]
    assert first['next_offset'] == 2 and first['total'] == 5
    assert service.bounces.list({'offset': 4, 'limit': 2})['next_offset'] is None
    assert service.bounces.list({'offset': 5})['items'] == []
    assert service.bounces.list({'source': 'watched'})['total'] == 3
    assert service.bounces.list({'source': 'manual'})['total'] == 2
    for query in ['strasse', ' FIRST ', 'bounce 0']:
        assert [r['id'] for r in service.bounces.list({'query': query})['items']] == [rows[0]['id']]


def test_revision_conflict_cannot_overwrite_another_edit(service):
    record = add(service); data = edit_data(record)
    service.bounces.edit(data)
    with pytest.raises(PlanError, match='another view'):
        service.bounces.edit({**data, 'note': 'Stale write'})
    assert service.bounces.get({'asset': record['id']})['note'] == data['note']


def test_concurrent_edits_publish_one_revision(service):
    record = add(service); barrier = threading.Barrier(2)
    def save(label):
        barrier.wait()
        try:
            return service.bounces.edit(edit_data(record, label=label))['revision']
        except PlanError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ['First', 'Second']))
    assert sorted(map(str, results)) == ['2', 'conflict']
    assert json.loads(service.assets.manifest.read_text())[record['id']]['annotation']['revision'] == 2


def test_failed_manifest_save_keeps_memory_and_audio_unchanged(service, monkeypatch):
    record = add(service); before = service.assets.manifest.read_bytes()
    def fail(*_): raise OSError('fixture disk full')
    monkeypatch.setattr('flcopilot.bounce_library.atomic_json', fail)
    with pytest.raises(OSError): service.bounces.edit(edit_data(record))
    assert service.assets.manifest.read_bytes() == before
    assert service.bounces.get({'asset': record['id']})['revision'] == 1
    assert service.assets.resolve(record['id']).read_bytes() == b'input bytes'


def test_verify_checks_current_bytes_without_upgrading_provenance(service):
    record = add(service, watched=True)
    verified = service.bounces.verify({'asset': record['id']})
    assert verified['copied_bytes_verified'] and verified['sha256'] == record['sha256']
    assert verified['bytes'] == 11 and verified['verified_at'] <= time.time()
    assert not verified['causal_provenance_verified'] and not verified['render_triggered_by_app']
    assert 'copied_bytes_verified' not in service.bounces.get({'asset': record['id']})
    assert not service.adapter.calls


@pytest.mark.parametrize('change', ['mutated', 'deleted'])
def test_changed_or_missing_copy_does_not_verify_or_leak_paths(service, change):
    record = add(service); path = service.assets.resolve(record['id'])
    path.write_bytes(b'changed!!!') if change == 'mutated' else path.unlink()
    with pytest.raises(PlanError) as exc: service.bounces.verify({'asset': record['id']})
    assert 'fresh copy' in str(exc.value) and str(path) not in str(exc.value)
    assert service.bounces.list({})['total'] == 1  # Metadata still recoverable.


def test_stop_blocks_verification_but_not_note_editing(service):
    record = add(service); service.executor.stop()
    with pytest.raises(Stopped): service.bounces.verify({'asset': record['id']})
    assert service.bounces.edit(edit_data(record))['revision'] == 2


@pytest.mark.parametrize('values', [dict(limit=True), dict(limit=51), dict(limit=0), dict(offset=-1),
                                  dict(offset='1'), dict(source='arbitrary'), dict(query='x'*121), dict(path='/tmp')])
def test_query_validation(values):
    with pytest.raises(ValidationError): BounceQuery.model_validate_json(json.dumps(values))


@pytest.mark.parametrize('values', [dict(asset='../private'), dict(expected_revision=True), dict(expected_revision=0),
                                  dict(label='x'*101), dict(note='x'*2001), dict(label='bad\nlabel'),
                                  dict(note='nul\x00'), dict(sha256='forged')])
def test_edit_validation(values):
    with pytest.raises(ValidationError):
        BounceEdit.model_validate_json(json.dumps(edit_data({'id': 'a'*32}, **values)))


@pytest.mark.parametrize('key', ['imported_at', 'bytes', 'annotation'])
def test_import_metadata_cannot_forge_library_fields(service, key):
    with pytest.raises(PlanError, match='identity'):
        service.assets.import_stream(io.BytesIO(b'x'), 1, 'x.wav', metadata={key: 'forged'})


def test_api_and_mcp_share_persistent_library(app):
    s, srv, workspace = app; record = add(s, watched=True)
    assert len(TOOLS) == 20
    response = tool_call(workspace, 'copilot_bounces', {'source': 'watched'})
    assert response['items'][0]['id'] == record['id']
    saved = json.load(call(srv, '/api/bounce-edit', edit_data(record)))
    assert saved['revision'] == 2
    assert json.load(call(srv, '/api/bounce-get', {'asset': record['id']})) == saved
    verified = poll(srv, json.load(call(srv, '/api/bounce-verify', {'asset': record['id']})))
    assert verified['copied_bytes_verified'] and not s.adapter.calls
    with pytest.raises(ValueError): tool_call(workspace, 'copilot_bounce_edit', edit_data(record))


@pytest.mark.parametrize('route', ['bounces', 'bounce-get', 'bounce-edit', 'bounce-verify'])
def test_library_routes_auth_and_origin_protected(app, route):
    _, srv, _ = app
    for headers in [dict(token=False), dict(origin='https://evil.test')]:
        with pytest.raises(urllib.error.HTTPError) as error:
            call(srv, '/api/'+route, {}, **headers)
        assert error.value.code == 403


def test_library_script_csp_and_input_escaping_contract(app):
    _, srv, _ = app
    with call(srv, '/bounces.js', token=False) as response:
        assert "script-src 'self'" in response.headers['Content-Security-Policy']
        source = response.read().decode()
        assert 'textContent=item.label' in source and 'innerHTML' not in source
