"""Padded parameter discovery, stale observations and preview-only permissions."""
import copy
import time
import pytest
from pydantic import ValidationError
from flcopilot.contracts import Locks, PlanError, Stopped
from flcopilot.demo import DemoAdapter
from flcopilot.service import Service
from flcopilot.plugin_workbench import ScanRequest, ParameterPreview, MAX_OBSERVATIONS

@pytest.fixture
def service(tmp_path):
    s=Service(tmp_path,DemoAdapter())
    yield s
    s.close()

def scan(s,**kwargs):
    return s.plugin_scan(dict(track=6,slot=0,**kwargs))

def preview(s,r,**kwargs):
    return s.plugin_preview(dict(observation_id=r['observation_id'],parameter=129,value=.25,**kwargs))

def test_partial_scan_does_not_touch_host_or_enable_writes(service):
    r=scan(service)
    assert not r['complete'] and r['has_more'] and r['next_start']==512
    assert r['examined_count']==512 and r['excluded_unnamed_or_padding']==511
    assert [p['index'] for p in r['parameters']]==[129]
    assert not service.adapter.calls and not service.adapter.writes and not service.journal.history()
    assert r['demo'] and not r['project_changed']

def test_pagination_finds_high_indices_without_duplicates(service):
    seen=[];start=0
    while True:
        r=scan(service,start=start,max_indices=2048)
        seen.extend(p['index'] for p in r['parameters'])
        if r['next_start'] is None: break
        start=r['next_start']
    assert seen==[129,2049,4097]
    assert r['end_exclusive']==4098 and not r['complete'] and not r['has_more']

def test_explicit_search_window_and_units(service):
    r=scan(service,start=2048,query='FREQUENCY')
    assert r['parameters'][0]['amount']==1000 and r['parameters'][0]['unit']=='Hz'
    assert r['parameters'][0]['display']=='1.000000 kHz'
    assert not scan(service,query='frequency')['parameters']

def test_search_matches_observed_display_not_invented_names(service):
    r=scan(service,start=4096,query='seconds')
    assert [p['index'] for p in r['parameters']]==[4097]
    assert r['parameters'][0]['amount']==20 and r['parameters'][0]['unit']=='ms'

def test_empty_plugin_parameter_space(service):
    service.adapter.params={}
    r=scan(service)
    assert r['complete'] and not r['has_more'] and r['examined_count']==0

def test_preview_is_observation_bound_and_read_only(service):
    r=scan(service);p=preview(service,r)['plan']
    assert p['operations'][0]['parameter']==129 and p['operations'][0]['track']==6
    assert p['before'][0]['parameter']['plugin']=='Copilot Test Effect (simulated)'
    assert not service.adapter.calls and not service.adapter.writes
    assert len(service.journal.history())==1

@pytest.mark.parametrize('change',['session','name','fader','plugin','value'])
def test_stale_observation_cannot_prepare(service,change):
    r=scan(service)
    if change=='session':service.adapter.session='e'*32
    elif change=='name':service.adapter.tracks[6]['name']='Different'
    elif change=='fader':service.adapter.tracks[6]['volume_db']=-8.
    elif change=='plugin':service.adapter.tracks[6]['plugins'][0]['name']='Different'
    else:service.adapter.params[(6,0,129)]['value']=.6
    with pytest.raises(PlanError):preview(service,r)
    assert not service.journal.history() and not service.adapter.calls

def test_unknown_filtered_parameter_cannot_prepare(service):
    r=scan(service,query='missing')
    with pytest.raises(PlanError,match='not present'):preview(service,r)

def test_expired_token_and_bounded_cache(service):
    r=scan(service)
    service.workbench.observations[r['observation_id']]['deadline']=time.monotonic()-1
    with pytest.raises(PlanError,match='expired'):preview(service,r)
    first=scan(service)
    for _ in range(MAX_OBSERVATIONS):scan(service)
    assert len(service.workbench.observations)==MAX_OBSERVATIONS
    with pytest.raises(PlanError,match='evicted'):preview(service,first)

def test_tokens_do_not_cross_app_processes(service,tmp_path):
    r=scan(service);other=Service(tmp_path/'other',DemoAdapter())
    try:
        with pytest.raises(PlanError):preview(other,r)
    finally:other.close()

@pytest.mark.parametrize('data',[{'track':True},{'slot':10},{'start':-1},{'start':65536},
    {'max_indices':2049},{'max_indices':0},{'query':'a'*81},{'script':'malicious'}])
def test_scan_bounds_reject_untrusted_requests(data):
    with pytest.raises(ValidationError):ScanRequest.model_validate(dict({'track':1,'slot':0},**data))

@pytest.mark.parametrize('change',['missing','duplicate','count','offset','plugin','slot','nan','bool_index'])
def test_malformed_raw_pages_never_claim_complete(service,change):
    old=service.adapter.parameter_page
    def bad(*a):
        p=old(*a)
        if change=='missing':p['parameters'].pop()
        elif change=='duplicate':p['parameters'][-1]['index']=p['parameters'][0]['index']
        elif change=='count':p['scanned_count']+=1
        elif change=='offset':p['offset']+=1
        elif change=='plugin':p['plugin']['name']='Wrong'
        elif change=='slot':p['plugin']['slot_index']=9
        elif change=='nan':p['parameters'][0]['normalized_value']=float('nan')
        else:p['parameters'][0]['index']=True
        return p
    service.adapter.parameter_page=bad
    with pytest.raises(PlanError):scan(service)
    assert not service.workbench.observations and not service.adapter.calls

@pytest.mark.parametrize('change',['session','track','count','stop'])
def test_change_during_scan_discards_results(service,change):
    old=service.adapter.parameter_page;calls=[]
    def read(*a):
        calls.append(1);p=old(*a)
        if change=='session':service.adapter.session='e'*32
        elif change=='track':service.adapter.tracks[6]['pan']=.1
        elif change=='stop':service.executor.stop_event.set()
        elif len(calls)>1:p['reported_parameter_count']+=1
        return p
    service.adapter.parameter_page=read
    with pytest.raises(PlanError):scan(service)
    assert not service.workbench.observations

def test_parameter_locks_apply_after_browsing(service):
    r=scan(service);service.executor.configure('assist',Locks(parameters=True))
    with pytest.raises(PlanError,match='locked'):preview(service,r)
    assert not service.adapter.calls

def test_unitless_and_unreadable_controls_are_not_promoted(service):
    r=service.plugin_scan({'track':1,'slot':0})
    p=r['parameters'][0]
    assert p['can_normalized'] and not p['can_display'] and p['unit'] is None
    old=service.adapter.parameter_page
    def unavailable(*a):
        p=old(*a)
        for row in p['parameters']:row['normalized_value']=None
        return p
    service.adapter.parameter_page=unavailable
    r=scan(service)
    assert not r['parameters'][0]['can_normalized'] and not r['parameters'][0]['can_display']

def test_address_limit_is_not_full_coverage(service):
    service.adapter.params[(6,0,70000)]=dict(plugin='Copilot Test Effect (simulated)',name='Beyond app range',value=.5)
    r=scan(service,start=65024)
    assert r['has_more'] and r['next_start'] is None and r['address_limit_reached']
    assert not r['complete']
