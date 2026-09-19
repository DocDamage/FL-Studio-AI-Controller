"""Synthetic audio, real WAV readback, durable choices and no DAW writes."""
import io
import json
from pathlib import Path
import threading
import numpy as np
import pytest
import soundfile as sf
from pydantic import ValidationError
from flcopilot.assets import file_hash
from flcopilot.contracts import Approval, PlanError, Stopped
from flcopilot.demo import DemoAdapter
from flcopilot.service import Service
from flcopilot.review_alignment import timing_evidence
from flcopilot.review_contracts import ReviewRequest


@pytest.fixture
def app(tmp_path):
    service=Service(tmp_path,DemoAdapter())
    yield service
    service.close()


def signal(seconds=4,sr=8000):
    t=np.arange(round(seconds*sr))/sr
    envelope=.04+.12*np.sin(2*np.pi*.71*t)**2+.15*np.maximum(0,np.sin(2*np.pi*2.17*t))**12
    return np.random.default_rng(45).normal(size=(len(t),2))*envelope[:,None]*.2


def upload(app,y,sr=8000,name='private-source.wav'):
    data=io.BytesIO();sf.write(data,y,sr,format='WAV',subtype='FLOAT');raw=data.getvalue()
    return app.assets.import_stream(io.BytesIO(raw),len(raw),name)['id']


def pair(app,a=None,b=None,sr=8000,br=8000):
    a=signal() if a is None else a
    b=a*1.6 if b is None else b
    return dict(baseline=upload(app,a,sr),candidate=upload(app,b,br),confirm_same_range=True)


def test_gain_only_pair_preserves_sources_and_reports_measured_match(app):
    req=pair(app);before=[file_hash(app.assets.resolve(req[k])) for k in ('baseline','candidate')]
    result=app.review_audio(req);report=result['report']
    assert report['status']=='ready' and report['timing']['basis']=='samplewise_proportional'
    assert len(result['files'])==3 and result['decision']=='undecided' and result['revision']==1
    assert not app.adapter.calls and not app.adapter.writes and not app.journal.history()
    assert [file_hash(app.assets.resolve(req[k])) for k in ('baseline','candidate')]==before
    ab=report['level_matched_ab'];assert ab['processing']=='attenuation_only'
    assert all(r['gain_db']<=0 for r in ab['files'])
    assert abs(ab['files'][0]['measurement']['integrated_lufs']-ab['files'][1]['measurement']['integrated_lufs'])<=.1
    arrays=[sf.read(app.assets.resolve(f['id']))[0] for f in result['files'][:2]]
    assert np.max(np.abs(arrays[0]-arrays[1]))<1e-6
    assert not report['content_alignment_verified'] and not report['subjective_quality_evaluated']
    assert not report['project_changed'] and not report['source_overwritten']
    assert str(app.assets.root) not in json.dumps(report) and 'private-source' not in json.dumps(report)


@pytest.mark.parametrize('value',[False,1,0,'true',None])
def test_confirmation_must_be_actual_true(value):
    with pytest.raises(ValidationError):
        ReviewRequest(baseline='a'*32,candidate='b'*32,confirm_same_range=value)
    with pytest.raises(ValidationError):
        Approval(plan_id='a'*32,digest='b'*64,confirm=value)


@pytest.mark.parametrize('change',[{'baseline':'../../file'},{'candidate':'a'*32},
    {'section_seconds':True},{'section_seconds':9},{'section_seconds':61},{'title':' '},
    {'title':'x\ny'},{'title':'x'*101},{'unknown':'value'},{'linked_plan_id':'../secret'}])
def test_strict_request_bounds(change):
    data=dict(baseline='a'*32,candidate='b'*32,confirm_same_range=True);data.update(change)
    with pytest.raises(ValidationError):ReviewRequest.model_validate(data)


@pytest.mark.parametrize('mismatch',['rate','channels','frames','silence','unrelated'])
def test_incompatible_pairs_get_report_but_no_ab(app,mismatch):
    a=signal();b=a.copy();br=8000;reason=''
    if mismatch=='rate':br=16000;reason='sample_rate_mismatch'
    elif mismatch=='channels':b=b[:,:1];reason='channel_count_mismatch'
    elif mismatch=='frames':b=b[:-1];reason='frame_count_mismatch'
    elif mismatch=='silence':b*=0;reason='unmeasurable_loudness'
    else:b=np.random.default_rng(982).normal(size=a.shape)*.01;reason='timing_uncertain'
    result=app.review_audio(pair(app,a,b,br=br));report=result['report']
    assert report['status']=='blocked' and reason in report['blocked_reasons']
    assert len(result['files'])==1 and result['files'][0]['kind']=='report'
    assert not report['sections'] and report['level_matched_ab'] is None
    assert not app.adapter.calls


def test_offset_detected_and_never_silently_fixed(app):
    a=signal(8);processed=np.tanh(a*6)/6
    b=np.concatenate([np.zeros((800,2)),processed[:-800]])
    result=app.review_audio(pair(app,a,b))
    assert result['report']['blocked_reasons']==['timing_offset_detected']
    assert result['report']['timing']['estimated_delay_ms']==pytest.approx(100)
    assert not result['report']['timing']['automatic_shift_applied']
    assert len(result['files'])==1


def test_envelope_checks_processed_antiphase_stereo_without_mono_fold():
    a=signal(8);a[:,1]=-a[:,0];b=np.tanh(a*8)/8
    result=timing_evidence(a,b,8000)
    assert result['status']=='consistent' and result['basis']=='multi_window_energy_envelope'
    assert not result['sample_accurate_alignment_claimed']


def test_polarity_change_not_silently_hidden(app):
    a=signal();r=app.review_audio(pair(app,a,-a))['report']
    assert r['timing']['polarity_inverted'] and any('polarity' in w for w in r['warnings'])


def test_uncertain_short_or_flat_audio_is_not_certified():
    a=signal(2);assert timing_evidence(a,np.tanh(a*7)/7,8000)['status']=='uncertain'
    a=np.ones((32000,2))*.03;b=a.copy();b[2000:2200]+=.001
    assert timing_evidence(a,b,8000)['status']=='uncertain'


def test_section_windows_cover_short_tail_without_tiny_lufs_block(app):
    a=signal(20.5);result=app.review_audio(pair(app,a,a*.7));sections=result['report']['sections']
    assert [(s['start_seconds'],s['end_seconds']) for s in sections]==[(0,15),(15,20.5)]
    result=app.review_audio({**pair(app,a,a*.7),'section_seconds':10})
    assert [(s['start_seconds'],s['end_seconds']) for s in result['report']['sections']]==[(0,10),(10,20.5)]


def test_silent_section_has_unknown_not_invented_delta(app):
    a=signal(25);a[80000:160000]=0
    r=app.review_audio({**pair(app,a,a*.7),'section_seconds':10})['report']
    assert r['sections'][1]['baseline']['integrated_lufs'] is None
    assert r['sections'][1]['candidate_minus_baseline']['integrated_lufs'] is None


def test_peak_limited_matching_attenuates_both_without_limiting(app):
    a=signal();a[123,0]=1.3
    r=app.review_audio(pair(app,a,a*1.4))['report'];ab=r['level_matched_ab']
    assert all(f['gain_db']<0 for f in ab['files'])
    assert all(f['measurement']['oversampled_peak_dbtp_estimate']<=-1 for f in ab['files'])
    assert not ab['limiting_applied'] and r['baseline']['clipped_sample_values']>0


def test_changed_input_and_non_audio_assets_refused(app):
    req=pair(app);app.assets.resolve(req['candidate']).write_bytes(b'changed')
    with pytest.raises(PlanError,match='bytes changed'):app.review_audio(req)
    assert not app.reviews.history() and not list(app.assets.exports.iterdir())
    f=app.assets.exports/'report.json';f.write_text('{}');asset=app.assets.add_output(f,kind='report')
    with pytest.raises(PlanError,match='audio assets'):app.review_audio({**req,'candidate':asset['id']})


def test_cancel_before_and_during_render_cleans_unpublished_files(app,monkeypatch):
    req=pair(app);app.executor.stop_event.set()
    with pytest.raises(Stopped):app.review_audio(req)
    app.executor.stop_event.clear()
    import flcopilot.review as review
    original=review.render_pair
    def stop_after(*args,**kwargs):
        result=original(*args,**kwargs);app.executor.stop_event.set();return result
    monkeypatch.setattr(review,'render_pair',stop_after)
    with pytest.raises(Stopped):app.review_audio(req)
    assert not app.reviews.history() and len(app.assets.list())==2
    assert not list(app.assets.exports.iterdir())


def test_changed_source_during_render_is_not_published(app,monkeypatch):
    req=pair(app);import flcopilot.review as review
    original=review.render_pair;source=app.assets.resolve(req['baseline'])
    def mutate(*args,**kwargs):
        result=original(*args,**kwargs);source.write_bytes(b'concurrent mutation');return result
    monkeypatch.setattr(review,'render_pair',mutate)
    with pytest.raises(PlanError,match='changed during'):app.review_audio(req)
    assert not list(app.assets.exports.iterdir()) and not app.reviews.history()


def test_failed_registration_or_store_publish_has_no_partial_history(app,monkeypatch):
    req=pair(app)
    def fail(*args):raise OSError('synthetic disk failure')
    monkeypatch.setattr(app.reviews,'add',fail)
    with pytest.raises(OSError):app.review_audio(req)
    assert len(app.assets.list())==2 and not list(app.assets.exports.iterdir())


def test_batch_output_registration_does_not_mutate_memory_on_disk_failure(app,monkeypatch):
    import flcopilot.assets as assets
    path=app.assets.exports/'test.json';path.write_text('{}')
    before=app.assets.list()
    def fail(*args):raise OSError('manifest write failed')
    monkeypatch.setattr(assets,'atomic_json',fail)
    with pytest.raises(OSError):app.assets.add_outputs([(path,None,'report')])
    assert app.assets.list()==before


def test_decisions_are_human_only_revision_checked_and_preserve_report(app):
    review=app.review_audio(pair(app));report=review['report']
    req=dict(review_id=review['review_id'],expected_revision=1,decision='prefer_baseline',note='More punch')
    chosen=app.review_decision(req);assert chosen['revision']==2 and chosen['report']==report
    assert chosen['decision_source']=='human' and not app.adapter.calls
    with pytest.raises(PlanError,match='changed'):app.review_decision(req)
    assert app.review_get({'review_id':review['review_id']})['note']=='More punch'


def test_blocked_review_cannot_be_saved_as_an_accepted_ab(app):
    review=app.review_audio(pair(app,signal(),np.zeros((32000,2))))
    args=dict(review_id=review['review_id'],expected_revision=1,decision='prefer_candidate')
    with pytest.raises(PlanError,match='readiness'):app.review_decision(args)
    assert app.review_decision({**args,'decision':'needs_revision'})['revision']==2


def test_reviews_survive_restart_without_reapplying_controls(tmp_path):
    app=Service(tmp_path,DemoAdapter());r=app.review_audio(pair(app));app.close()
    other=Service(tmp_path,DemoAdapter())
    try:
        assert other.review_get({'review_id':r['review_id']})==r
        assert len(other.reviews.history())==1 and not other.adapter.calls
    finally:other.close()


def test_linked_verified_plan_is_association_not_audio_provenance(app):
    app.settings({'mode':'assist'})
    plan=app.prepare({'operations':[{'kind':'volume','track':1,'value':-3.}]})
    req={**pair(app),'linked_plan_id':plan['id']}
    with pytest.raises(PlanError,match='fully verified'):app.review_audio(req)
    app.execute({'plan_id':plan['id'],'digest':plan['digest'],'confirm':True})
    calls=len(app.adapter.calls);r=app.review_audio(req)['report']['linked_run']
    assert r['backend']=='demo' and r['plan_digest']==plan['digest']
    assert not r['audio_provenance_verified'] and not r['causal_effect_verified']
    assert len(app.adapter.calls)==calls and app.adapter.session not in json.dumps(r)


def test_imported_inputs_cannot_be_discarded_as_transient_outputs(app):
    req=pair(app)
    with pytest.raises(PlanError):app.assets.discard_outputs({req['baseline']})
    assert app.assets.resolve(req['baseline']).is_file()


@pytest.mark.parametrize('failure',['rate','frames','loudness'])
def test_export_readback_failure_does_not_publish_audio(app,monkeypatch,failure):
    req=pair(app)
    import flcopilot.review as review
    original=review._load
    def damaged(path):
        samples,rate=original(path)
        if Path(path).name=='B_Candidate_Matched.wav':
            if failure=='rate':rate*=2
            elif failure=='frames':samples=samples[:-1]
            else:samples*=.5
        return samples,rate
    monkeypatch.setattr(review,'_load',damaged)
    with pytest.raises(PlanError,match='export changed|loudness'):app.review_audio(req)
    assert not app.reviews.history() and not list(app.assets.exports.iterdir())
    assert len(app.assets.list())==2


def test_negative_time_offset_sign_and_processed_content():
    a=signal(8);b=np.tanh(a*8)/8;b=np.concatenate([b[800:],np.zeros((800,2))])
    evidence=timing_evidence(a,b,8000)
    assert evidence['status']=='offset_detected' and evidence['estimated_delay_ms']==pytest.approx(-100)


def test_identical_imports_are_disclosed_not_called_improvement(app):
    a=signal();r=app.review_audio(pair(app,a,a))['report']
    assert r['identical_file_bytes'] and r['candidate_minus_baseline']['integrated_lufs']==0
    assert not r['subjective_quality_evaluated']


def test_decision_revision_race_has_one_winner(app):
    r=app.review_audio(pair(app));results=[]
    def decide(choice):
        try:
            app.review_decision(dict(review_id=r['review_id'],expected_revision=1,decision=choice))
            results.append('saved')
        except PlanError:results.append('stale')
    threads=[threading.Thread(target=decide,args=(c,)) for c in ('prefer_candidate','prefer_baseline')]
    for t in threads:t.start()
    for t in threads:t.join(timeout=3)
    assert sorted(results)==['saved','stale'] and app.reviews.get(r['review_id'])['revision']==2


def test_review_runs_without_any_adapter_access(app):
    def forbidden(*args):raise AssertionError('Review must not call FL')
    app.adapter.snapshot=app.adapter.connection=app.adapter.begin=app.adapter.execute=forbidden
    assert app.review_audio(pair(app))['report']['status']=='ready'
