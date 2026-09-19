"""Real synthetic WAV envelopes and guarded HTTP; no live FL or listening claims."""
import copy
import io
import json
import threading
import time
import urllib.error
import urllib.request

import numpy as np
import pytest
import soundfile as sf

from flcopilot import review_waveform as wave
from flcopilot.assets import file_hash
from flcopilot.contracts import PlanError, Stopped
from flcopilot.demo import DemoAdapter
from flcopilot.server import LocalServer
from flcopilot.service import Service


@pytest.fixture
def paired(tmp_path):
    s = Service(tmp_path / 'workspace', DemoAdapter())
    samples = np.random.default_rng(713).normal(0, .07, (32003, 2))
    ids = []
    try:
        for n, gain in enumerate((1, .7)):
            stream = io.BytesIO()
            sf.write(stream, samples * gain, 8000, format='WAV', subtype='FLOAT')
            raw = stream.getvalue()
            ids.append(s.assets.import_stream(io.BytesIO(raw), len(raw), f'private-{n}.wav')['id'])
        review = s.review_audio({'baseline': ids[0], 'candidate': ids[1], 'confirm_same_range': True})
        assert review['report']['status'] == 'ready'
        yield s, review
    finally:
        s.close()


def preview(s, review, **kwargs):
    return s.review_waveform({'review_id': review['review_id'], **kwargs})


def test_real_matched_outputs_every_frame_and_exact_extrema(paired):
    s, review = paired
    result = preview(s, review, bins=97)
    assert result['frame_edges'] == [i * 32003 // 97 for i in range(98)]
    for side, name in zip(('a', 'b'), wave.NAMES[:2]):
        record = next(r for r in review['files'] if r['name'] == name)
        y, sr = sf.read(s.assets.resolve(record['id']), dtype='float32', always_2d=True)
        assert result['sides'][side]['sha256'] == record['sha256']
        assert result['sides'][side]['asset'] == record['id']
        for c, row in enumerate(result['sides'][side]['channels']):
            for n, (start, end) in enumerate(zip(result['frame_edges'], result['frame_edges'][1:])):
                part = y[start:end, c]
                assert row['min'][n] == float(part.min())
                assert row['max'][n] == float(part.max())
                assert row['rms'][n] == pytest.approx(np.sqrt(np.square(part, dtype=np.float64).mean()), rel=1e-12)
    assert result['frames'] == 32003 and result['sample_rate'] == 8000 and result['channels'] == 2
    assert result['duration_seconds'] == 32003 / 8000


@pytest.mark.parametrize('bins', [64, 800, 2048])
def test_resolution_bounds_response_size_and_no_shared_mutable_cache(paired, bins):
    s, review = paired
    result = preview(s, review, bins=bins)
    assert result['bin_count'] == bins
    assert len(json.dumps(result).encode()) < 600 * 1024
    result['sides']['a']['channels'][0]['max'][0] = -100
    assert preview(s, review, bins=bins)['sides']['a']['channels'][0]['max'][0] != -100


@pytest.mark.parametrize('bins', [True, False, '800', 800.0, None, 0, 63, 2049, [], {}, float('inf')])
def test_invalid_resolution_never_reads_audio(paired, monkeypatch, bins):
    s, review = paired
    monkeypatch.setattr(wave, '_hash', lambda *args: pytest.fail('invalid request reached filesystem'))
    with pytest.raises(ValueError):
        preview(s, review, bins=bins)


@pytest.mark.parametrize('data', [{'review_id': '../outside'}, {'review_id': 'a'*32, 'path': '/private'},
    {'review_id': 'a'*32, 'start': 0}, {}, {'review_id': True}])
def test_request_id_and_allowlist(paired, data):
    with pytest.raises(ValueError):
        paired[0].review_waveform(data)


def test_unknown_review(paired):
    with pytest.raises(PlanError):
        paired[0].review_waveform({'review_id': 'f'*32})


def test_read_only_and_privacy(paired):
    s, review = paired
    before = s.assets.manifest.read_bytes()
    hashes = {r['id']: file_hash(s.assets.resolve(r['id'])) for r in s.assets.list()}
    result = preview(s, review)
    assert before == s.assets.manifest.read_bytes()
    assert hashes == {r['id']: file_hash(s.assets.resolve(r['id'])) for r in s.assets.list()}
    assert s.reviews.get(review['review_id']) == review
    assert not s.adapter.calls and not s.journal.history()
    assert result['project_changed'] is False and result['source_inputs_reverified'] is False
    assert result['independent_normalization'] is False
    text = json.dumps(result)
    for private in (str(s.assets.root), 'private-0', 'private-1', 'baseline_asset', 'path', 'title'):
        assert private not in text


@pytest.mark.parametrize('part', ['audio', 'report'])
def test_changed_file_fails_on_each_fresh_request(paired, part):
    s, review = paired
    preview(s, review)
    row = next(r for r in review['files'] if r['kind'] == part)
    s.assets.resolve(row['id']).write_bytes(b'changed')
    with pytest.raises(PlanError, match='bytes changed'):
        preview(s, review)


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'renamed', 'wrong_kind', 'manifest_hash',
                                      'report_database', 'blocked', 'measured_hash', 'missing_measurement'])
def test_identity_and_report_failures(paired, mutation):
    s, review = paired
    r = copy.deepcopy(review)
    if mutation == 'missing': r['files'].pop()
    if mutation == 'duplicate': r['files'][1] = r['files'][0]
    if mutation == 'renamed': r['files'][0]['name'] = 'other.wav'
    if mutation == 'wrong_kind': r['files'][0]['kind'] = 'input'
    if mutation == 'manifest_hash': s.assets.data[r['files'][0]['id']]['sha256'] = 'a'*64
    if mutation == 'report_database': r['report']['title'] = 'database changed'
    if mutation == 'blocked': r['report']['status'] = 'blocked'
    if mutation == 'measured_hash': r['report']['level_matched_ab']['files'][0]['sha256'] = 'b'*64
    if mutation == 'missing_measurement': r['report']['level_matched_ab']['files'].pop()
    with pytest.raises(PlanError):
        wave.build_waveforms(s.assets, r, 64)


def test_missing_file_refused(paired):
    s, review = paired
    s.assets.resolve(review['files'][0]['id']).unlink()
    with pytest.raises((PlanError, FileNotFoundError)):
        preview(s, review)


def test_workspace_escape_refused(paired, tmp_path):
    s, review = paired
    outside = tmp_path / 'outside.wav'; outside.write_bytes(b'outside')
    row = review['files'][0]; row['path'] = str(outside)
    # The database row and manifest agree, but the workspace boundary still wins.
    s.assets.data[row['id']]['path'] = str(outside)
    with pytest.raises(PlanError, match='escapes'):
        wave.build_waveforms(s.assets, review, 64)


def test_changed_during_other_side_read_is_refused(paired, monkeypatch):
    s, review = paired
    first = s.assets.resolve(next(r['id'] for r in review['files'] if r['name'] == wave.NAMES[0]))
    original = wave._envelope
    def change(path, *args):
        result = original(path, *args)
        if path != first: first.write_bytes(b'changed while reading side B')
        return result
    monkeypatch.setattr(wave, '_envelope', change)
    with pytest.raises(PlanError, match='bytes changed'):
        preview(s, review)


def test_stop_before_read(paired):
    s, review = paired
    s.executor.stop()
    with pytest.raises(Stopped): preview(s, review)


def test_stop_mid_hash(paired, monkeypatch):
    s, review = paired
    original = wave._hash
    def stop(*args):
        result = original(*args); s.executor.stop(); return result
    monkeypatch.setattr(wave, '_hash', stop)
    with pytest.raises(Stopped): preview(s, review)


def test_file_size_and_growing_hash_bound(paired, monkeypatch):
    s, review = paired
    monkeypatch.setattr(wave, 'MAX_UPLOAD', 100)
    with pytest.raises(PlanError, match='size bound'): preview(s, review)
    with pytest.raises(PlanError, match='grew beyond'):
        wave._hash(s.assets.resolve(review['files'][0]['id']), None, 100)


def write_wave(tmp_path, y, rate=8000, subtype='FLOAT'):
    path = tmp_path/'envelope.wav';sf.write(path, y, rate, subtype=subtype)
    return path, {'frames':len(y), 'channels':1 if y.ndim == 1 else y.shape[1], 'sample_rate':rate}


@pytest.mark.parametrize('channels', [1, 2])
def test_silence_and_antiphase_are_not_downmixed(tmp_path, channels):
    t = np.arange(8001)/8000
    y = np.sin(t*2*np.pi*440).astype('float32')*.5
    y = np.column_stack((y, -y)) if channels == 2 else np.zeros_like(y)
    path, expected = write_wave(tmp_path, y)
    metadata, edges, rows = wave._envelope(path, expected, 64, None)
    assert len(rows) == channels and edges[-1] == len(y)
    if channels == 1: assert all(v == 0 for v in rows[0]['rms'])
    else:
        assert min(rows[0]['rms']) > .3
        assert rows[0]['rms'] == rows[1]['rms']
        assert rows[0]['min'] == [-v for v in rows[1]['max']]


@pytest.mark.parametrize('value', [np.nan, np.inf, -np.inf])
def test_nonfinite_audio(tmp_path, value):
    y = np.zeros(8000, dtype=np.float32);y[4000] = value
    path, expected = write_wave(tmp_path, y)
    with pytest.raises(PlanError, match='non-finite'): wave._envelope(path, expected, 64, None)


@pytest.mark.parametrize('field,value', [('frames', 1), ('channels', True), ('sample_rate', 44100)])
def test_report_format_mismatch(tmp_path, field, value):
    path, expected = write_wave(tmp_path, np.zeros(8000, dtype=np.float32))
    expected[field] = value
    with pytest.raises(PlanError, match='format no longer matches'): wave._envelope(path, expected, 64, None)


@pytest.mark.parametrize('rate,frames,channels,subtype', [(7999, 8000, 1, 'FLOAT'),
    (192001, 192001, 1, 'FLOAT'), (8000, 7999, 1, 'FLOAT'), (8000, 8000, 3, 'FLOAT'),
    (8000, 8000, 1, 'PCM_16')])
def test_format_and_duration_bounds(tmp_path, rate, frames, channels, subtype):
    path, expected = write_wave(tmp_path, np.zeros((frames, channels), dtype=np.float32), rate, subtype)
    with pytest.raises(PlanError): wave._envelope(path, expected, 64, None)


def test_duration_and_sample_cap(tmp_path, monkeypatch):
    path, expected = write_wave(tmp_path, np.zeros((8000, 2), dtype=np.float32))
    monkeypatch.setattr(wave, 'MAX_SECONDS', .5)
    with pytest.raises(PlanError, match='bound'): wave._envelope(path, expected, 64, None)
    monkeypatch.setattr(wave, 'MAX_SECONDS', 600); monkeypatch.setattr(wave, 'MAX_SAMPLES', 15000)
    with pytest.raises(PlanError, match='bound'): wave._envelope(path, expected, 64, None)


def test_read_blocks_bounded_and_cancellable(tmp_path, monkeypatch):
    path, expected = write_wave(tmp_path, np.ones(8000, dtype=np.float32)*.1)
    monkeypatch.setattr(wave, 'MAX_READ_FRAMES', 17)
    original = sf.SoundFile.read; counts=[]; stop=threading.Event()
    def read(handle, frames=-1, **kwargs):
        counts.append(frames)
        if len(counts) == 20: stop.set()
        return original(handle, frames, **kwargs)
    monkeypatch.setattr(sf.SoundFile, 'read', read)
    with pytest.raises(Stopped): wave._envelope(path, expected, 64, stop)
    assert max(counts) == 17 and len(counts) == 20


def test_http_auth_and_actual_job(paired):
    s, review = paired
    server = LocalServer(s, 0);thread=threading.Thread(target=server.serve_forever, daemon=True);thread.start()
    def request(path, data=None, auth=True, origin=None):
        headers={'Content-Type':'application/json'}
        if auth: headers['Authorization']='Bearer '+server.token
        if origin: headers['Origin']=origin
        req=urllib.request.Request(server.origin+path, headers=headers,
            data=json.dumps(data).encode() if data is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=10) as response: return response.read()
        except urllib.error.HTTPError as error: error.close(); raise
    data={'review_id':review['review_id'], 'bins':64}
    try:
        for options in ({'auth':False}, {'origin':'https://untrusted.example'}):
            with pytest.raises(urllib.error.HTTPError) as exc: request('/api/review-waveform', data, **options)
            assert exc.value.code == 403
        job=json.loads(request('/api/review-waveform',data))
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            result=json.loads(request('/api/jobs/'+job['job']))
            if result['status'] in ('complete','error'): break
            time.sleep(.01)
        assert result['status']=='complete' and result['result']['bin_count']==64
        assert b'waveformData' in request('/waveform.js', auth=False)
        assert b'waveform-panel' in request('/waveform.css', auth=False)
        assert b'Load verified waveforms' in request('/', auth=False)
    finally:
        server.shutdown();thread.join(timeout=2);server.server_close()
