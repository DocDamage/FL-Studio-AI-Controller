"""Intake regression tests: real files and service/HTTP/MCP, no FL simulation claims."""
import io
import json
import os
import threading
import time
import urllib.error

import pytest
from pydantic import ValidationError
from flcopilot.assets import AssetStore
from flcopilot.contracts import PlanError, Stopped
from flcopilot.demo import DemoAdapter
from flcopilot.mcp_relay import TOOLS, tool_call
from flcopilot.render_intake import FileStamp, import_render, snapshot_folder, wait_for_render
from flcopilot.render_workflow import WatchRequest, WatchStop
from flcopilot.service import Service
from test_service_http import app, call, poll


@pytest.fixture
def service(tmp_path):
    s = Service(tmp_path / 'workspace', DemoAdapter())
    yield s
    s.close()


def export_dir(tmp_path):
    folder = tmp_path / 'renders'
    folder.mkdir(exist_ok=True)
    return folder


def arm(s, folder, **extra):
    return s.render_watch({'folder': str(folder), 'confirm_folder': True, **extra})


def settle(s, ticket):
    for _ in range(250):
        row = s.jobs.get(ticket['job'])
        if row['status'] in {'complete', 'error'}:
            return row
        time.sleep(.02)
    raise AssertionError('Watch did not settle')


def test_overwriting_existing_file_is_never_a_new_export(tmp_path):
    folder = export_dir(tmp_path)
    path = folder / 'old.wav'; path.write_bytes(b'old')
    baseline = snapshot_folder(folder)
    path.write_bytes(b'overwritten')
    with pytest.raises(PlanError, match='existing audio file changed'):
        wait_for_render(folder, baseline, threading.Event(), 1, .01)


def test_stable_plus_empty_unfinished_file_is_ambiguous(tmp_path):
    folder = export_dir(tmp_path); baseline = snapshot_folder(folder)
    (folder / 'mix.wav').write_bytes(b'new')
    (folder / 'stem.wav').touch()
    with pytest.raises(PlanError, match='Multiple'):
        wait_for_render(folder, baseline, threading.Event(), 1, .01)


def test_empty_export_times_out_without_import(tmp_path):
    folder = export_dir(tmp_path); baseline = snapshot_folder(folder)
    (folder / 'empty.wav').touch()
    with pytest.raises(PlanError, match='No stable'):
        wait_for_render(folder, baseline, threading.Event(), 1, .01)


def test_oversize_rejected_without_copy(tmp_path, monkeypatch):
    monkeypatch.setattr('flcopilot.render_intake.MAX_UPLOAD', 4)
    folder = export_dir(tmp_path); baseline = snapshot_folder(folder)
    (folder / 'big.wav').write_bytes(b'12345')
    with pytest.raises(PlanError, match='300 MiB'):
        wait_for_render(folder, baseline, threading.Event(), 1, .01)


def test_folder_entry_bound(tmp_path, monkeypatch):
    monkeypatch.setattr('flcopilot.render_intake.MAX_FOLDER_ENTRIES', 1)
    folder = export_dir(tmp_path)
    (folder / 'a.txt').touch(); (folder / 'b.txt').touch()
    with pytest.raises(PlanError, match='too many entries'):
        snapshot_folder(folder)


def test_directory_replacement_rejected(tmp_path):
    folder = export_dir(tmp_path); baseline = snapshot_folder(folder)
    folder.rename(tmp_path / 'moved'); folder.mkdir()
    (folder / 'new.wav').write_bytes(b'audio')
    with pytest.raises(PlanError, match='folder was replaced'):
        wait_for_render(folder, baseline, threading.Event(), 1, .01)


def symlink_or_skip(target, link, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError:
        pytest.skip('This host does not permit symlink creation')


@pytest.mark.parametrize('external', [True, False])
def test_audio_symlinks_rejected(tmp_path, external):
    folder = export_dir(tmp_path)
    target = (tmp_path if external else folder) / 'target.bin'; target.write_bytes(b'secret')
    symlink_or_skip(target, folder / 'unsafe.wav')
    with pytest.raises(PlanError, match='link'):
        snapshot_folder(folder)


def test_folder_symlink_rejected(tmp_path):
    folder = export_dir(tmp_path); link = tmp_path / 'alias'
    symlink_or_skip(folder, link, True)
    with pytest.raises(PlanError, match='links'):
        snapshot_folder(link)


def test_hardlinked_audio_rejected(tmp_path):
    folder = export_dir(tmp_path); source = tmp_path / 'source.wav'; source.write_bytes(b'audio')
    try:
        os.link(source, folder / 'linked.wav')
    except OSError:
        pytest.skip('Hard links unavailable on this host')
    with pytest.raises(PlanError, match='hard link'):
        snapshot_folder(folder)


@pytest.mark.parametrize('timeout', [float('nan'), float('inf'), -float('inf'), True, '20'])
def test_core_nonfinite_or_non_numeric_wait_rejected(tmp_path, timeout):
    with pytest.raises(PlanError, match='timeout'):
        wait_for_render(tmp_path, {}, threading.Event(), timeout)


@pytest.mark.parametrize('interval', [0, -1, float('nan'), float('inf'), True])
def test_invalid_stability_interval_rejected(tmp_path, interval):
    with pytest.raises(PlanError, match='stability'):
        wait_for_render(tmp_path, {}, threading.Event(), 1, interval)


@pytest.mark.parametrize('value', [1, 'true', False, None])
def test_consent_is_not_coerced(value):
    with pytest.raises(ValidationError):
        WatchRequest(folder='/renders', confirm_folder=value)


@pytest.mark.parametrize('value', [True, '120', 4, 601, 12.5])
def test_ui_timeout_is_strict_and_bounded(value):
    with pytest.raises(ValidationError):
        WatchRequest(folder='/renders', confirm_folder=True, timeout=value)


@pytest.mark.parametrize('value', [' ', '\0', '\n/renders'])
def test_invalid_folder_text(value):
    with pytest.raises(ValidationError):
        WatchRequest(folder=value, confirm_folder=True)


def test_relative_folder_rejected_before_any_job(service):
    with pytest.raises(PlanError, match='absolute local'):
        arm(service, 'relative')
    assert not service.jobs.rows


def test_local_and_global_cancellation_are_distinct():
    global_stop = threading.Event(); combined = WatchStop(global_stop)
    assert not combined.wait(.001)
    combined.local.set(); assert combined.wait(1) and not global_stop.is_set()
    combined = WatchStop(global_stop); global_stop.set(); assert combined.wait(1)


def test_capture_persists_provenance_and_never_writes_daw(service, tmp_path):
    folder = export_dir(tmp_path); ticket = arm(service, folder)
    source = folder / 'New.wav'; source.write_bytes(b'RIFF-test-bytes')
    row = settle(service, ticket)
    assert row['status'] == 'complete', row
    record = row['result']; saved = AssetStore(service.assets.root).list()[0]
    assert saved == record
    assert record['watch_id'] == ticket['watch_id']
    assert not record['causal_provenance_verified'] and not record['render_triggered_by_app']
    assert service.assets.resolve(record['id']).read_bytes() == source.read_bytes()
    assert not service.adapter.calls and not service.journal.history()
    status = service.render_watch_status()
    assert str(folder) not in json.dumps(status)
    status['watch']['result']['source'] = 'forged'
    assert service.render_watch_status()['watch']['result']['source'] == 'watched_fl_export'


def test_only_one_active_watch(service, tmp_path):
    folder = export_dir(tmp_path); ticket = arm(service, folder)
    with pytest.raises(PlanError, match='already active'):
        arm(service, folder)
    service.render_watch_cancel({'watch_id': ticket['watch_id']})
    assert settle(service, ticket)['status'] == 'error'
    assert service.render_watch_status()['watch']['status'] == 'cancelled'
    assert not service.executor.stop_event.is_set() and not service.assets.list()
    next_ticket = arm(service, folder)
    with pytest.raises(PlanError, match='no longer current'):
        service.render_watch_cancel({'watch_id': ticket['watch_id']})
    service.render_watch_cancel({'watch_id': next_ticket['watch_id']})
    settle(service, next_ticket)


def test_global_stop_blocks_new_watch(service, tmp_path):
    folder = export_dir(tmp_path); service.executor.stop()
    with pytest.raises(Stopped): arm(service, folder)
    assert not service.jobs.rows


def test_global_stop_cancels_running_watch(service, tmp_path):
    ticket = arm(service, export_dir(tmp_path)); service.executor.stop()
    assert settle(service, ticket)['status'] == 'error'
    assert service.render_watch_status()['watch']['status'] == 'cancelled'
    assert not service.assets.list()


def test_baseline_is_captured_before_queued_worker_starts(service, tmp_path):
    gate = threading.Event()
    try:
        service.jobs.submit('Block A', lambda: gate.wait(3))
        service.jobs.submit('Block B', lambda: gate.wait(3))
        folder = export_dir(tmp_path); ticket = arm(service, folder)
        (folder / 'not-lost.wav').write_bytes(b'new')
        gate.set()
        assert settle(service, ticket)['status'] == 'complete'
    finally:
        gate.set()


def test_job_capacity_failure_does_not_leave_armed_state(service, tmp_path):
    gate = threading.Event()
    try:
        for _ in range(4): service.jobs.submit('Busy', lambda: gate.wait(3))
        with pytest.raises(PlanError, match='pending jobs'):
            arm(service, export_dir(tmp_path))
        assert service.render_watch_status()['watch'] is None
    finally:
        gate.set()


def test_verification_failure_leaves_no_input_or_staged_file(tmp_path):
    assets = AssetStore(tmp_path)
    def reject(_): raise PlanError('changed while copying')
    with pytest.raises(PlanError, match='changed'):
        assets.import_stream(io.BytesIO(b'audio'), 5, 'x.wav', validate=reject)
    assert not assets.list() and not list(assets.imports.iterdir())
    assert not AssetStore(tmp_path).list()


def test_cancel_during_copy_never_publishes(tmp_path):
    assets = AssetStore(tmp_path); stop = threading.Event()
    class Cancelling(io.BytesIO):
        def read(self, size=-1):
            stop.set(); return super().read(size)
    with pytest.raises(Stopped):
        assets.import_stream(Cancelling(b'abc'), 3, 'x.wav', stop=stop)
    assert not assets.list() and not list(assets.imports.iterdir())


def test_manifest_failure_rolls_back_memory_and_copy(tmp_path, monkeypatch):
    assets = AssetStore(tmp_path)
    def fail(*args): raise OSError('disk full')
    monkeypatch.setattr('flcopilot.assets.atomic_json', fail)
    with pytest.raises(OSError):
        assets.import_stream(io.BytesIO(b'abc'), 3, 'x.wav')
    assert not assets.list() and not list(assets.imports.iterdir())


def test_reserved_metadata_cannot_override_asset_identity(tmp_path):
    assets = AssetStore(tmp_path)
    with pytest.raises(PlanError, match='identity'):
        assets.import_stream(io.BytesIO(b'x'), 1, 'x.wav', metadata={'id': 'forged'})
    assert not assets.list()


def test_same_size_replacement_before_import_refused(tmp_path):
    assets = AssetStore(tmp_path / 'w'); path = tmp_path / 'source.wav'; path.write_bytes(b'old')
    stamp = FileStamp.read(path.stat())
    path.unlink(); path.write_bytes(b'new')
    os.utime(path, ns=(stamp.mtime_ns, stamp.mtime_ns))
    with pytest.raises(PlanError, match='changed before'):
        import_render(assets, path, stamp)
    assert not assets.list()


def test_mutation_during_import_refused_before_registration(tmp_path, monkeypatch):
    assets = AssetStore(tmp_path / 'w'); path = tmp_path / 'source.wav'; path.write_bytes(b'old')
    stamp = FileStamp.read(path.stat()); real_import = assets.import_stream
    def mutate(source, length, name, **kwargs):
        old_validate = kwargs['validate']
        def validate(staged):
            path.write_bytes(b'new'); old_validate(staged)
        kwargs['validate'] = validate
        return real_import(source, length, name, **kwargs)
    monkeypatch.setattr(assets, 'import_stream', mutate)
    with pytest.raises(PlanError, match='changed during'):
        import_render(assets, path, stamp)
    assert not assets.list() and not list(assets.imports.iterdir())


def test_http_capture_and_mcp_status_share_same_state(app, tmp_path):
    service, server, workspace = app; folder = export_dir(tmp_path)
    ticket = json.load(call(server, '/api/render-watch', {'folder': str(folder), 'confirm_folder': True}))
    (folder / 'capture.wav').write_bytes(b'RIFF-test')
    record = poll(server, ticket)
    state = tool_call(workspace, 'copilot_render_status', {})
    assert state['watch']['result']['id'] == record['id']
    assert not record['render_triggered_by_app'] and not service.adapter.calls
    assert str(folder) not in json.dumps(state)
    assert json.load(call(server, '/api/assets'))[0]['watch_id'] == ticket['watch_id']


def test_mcp_can_cancel_but_cannot_arm_or_choose_paths(app, tmp_path):
    service, server, workspace = app; ticket = arm(service, export_dir(tmp_path))
    names = {t['name'] for t in TOOLS}
    assert {'copilot_render_status', 'copilot_render_cancel'} <= names
    assert 'copilot_render_watch' not in names and len(names) == len(TOOLS)
    with pytest.raises(ValueError):
        tool_call(workspace, 'copilot_render_watch', {'folder': str(tmp_path)})
    with pytest.raises(ValueError):
        tool_call(workspace, 'copilot_render_status', {'folder': str(tmp_path)})
    with pytest.raises(ValidationError):
        tool_call(workspace, 'copilot_render_cancel', {'watch_id': ticket['watch_id'], 'folder': str(tmp_path)})
    tool_call(workspace, 'copilot_render_cancel', {'watch_id': ticket['watch_id']})
    assert settle(service, ticket)['status'] == 'error'
    assert not service.executor.stop_event.is_set()


@pytest.mark.parametrize('route,data', [('/api/render-watch', None),
    ('/api/render-watch', {'folder': '/private', 'confirm_folder': True}),
    ('/api/render-watch-cancel', {'watch_id': 'a' * 32})])
def test_render_routes_require_auth(app, route, data):
    _, server, _ = app
    with pytest.raises(urllib.error.HTTPError) as error:
        call(server, route, data, token=False)
    assert error.value.code == 403


def test_render_routes_reject_cross_origin(app, tmp_path):
    service, server, _ = app
    with pytest.raises(urllib.error.HTTPError) as error:
        call(server, '/api/render-watch', {'folder': str(tmp_path), 'confirm_folder': True}, origin='http://evil.test')
    assert error.value.code == 403 and not service.jobs.rows


def test_new_script_is_served_with_csp(app):
    _, server, _ = app
    with call(server, '/render.js', token=False) as response:
        assert 'script-src' in response.headers['Content-Security-Policy']
        assert b'renderWatchRefresh' in response.read()


def test_second_export_appearing_during_copy_is_not_published(service, tmp_path, monkeypatch):
    folder = export_dir(tmp_path); real_import = service.assets.import_stream
    def import_with_second_file(source, length, name, **kwargs):
        verify = kwargs['validate']
        def validate(staged):
            (folder / 'second.wav').write_bytes(b'new second export')
            verify(staged)
        kwargs['validate'] = validate
        return real_import(source, length, name, **kwargs)
    monkeypatch.setattr(service.assets, 'import_stream', import_with_second_file)
    ticket = arm(service, folder); (folder / 'first.wav').write_bytes(b'first')
    row = settle(service, ticket)
    assert row['status'] == 'error' and 'Multiple' in row['error']
    assert not service.assets.list() and not list(service.assets.imports.iterdir())


def test_cancel_after_completion_preserves_captured_input(service, tmp_path):
    folder = export_dir(tmp_path); ticket = arm(service, folder)
    (folder / 'done.wav').write_bytes(b'finished')
    assert settle(service, ticket)['status'] == 'complete'
    state = service.render_watch_cancel({'watch_id': ticket['watch_id']})
    assert state['watch']['status'] == 'complete'
    assert not state['watch']['cancel_requested'] and len(service.assets.list()) == 1
