"""Explicit engineering units, isolated solver writes and honest verification."""
import json
import pytest
from pydantic import ValidationError
from flcopilot.contracts import DisplayTarget, Operation, PrepareRequest, Approval, PlanError, NotDispatched, Locks
from flcopilot.demo import DemoAdapter
from flcopilot.service import Service
from flcopilot.units import parse_display, display_in_unit

@pytest.fixture
def service(tmp_path):
    s=Service(tmp_path,DemoAdapter());s.settings({'mode':'assist'})
    yield s
    s.close()

def plan(s,index=129,amount=-9.,unit='dB',tolerance=.1):
    return s.prepare({'operations':[{'kind':'parameter_display','track':6,'slot':0,'parameter':index,
        'value':{'amount':amount,'unit':unit,'tolerance':tolerance}}]})

def execute(s,p):return s.execute({'plan_id':p['id'],'digest':p['digest'],'confirm':True})

@pytest.mark.parametrize('text,amount,unit',[
    ('1.2 kHz',1200.,'Hz'),(' 0.02 seconds ',20.,'ms'),('-9.00 dB',-9.,'dB'),
    ('.5 s',500.,'ms'),('12 %',12.,'percent'),('440 Hz',440.,'Hz')])
def test_only_explicit_units_convert(text,amount,unit):
    assert parse_display(text)==(amount,unit)

@pytest.mark.parametrize('text',['50','20 beats','1,25 kHz','-inf dB','NaN ms','3:1',
    '1e3 Hz','Attack 20 ms','+12 dB extra',None,False,'9'*400+' Hz'])
def test_ambiguous_displays_are_not_inferred(text):
    with pytest.raises(PlanError):parse_display(text)

def test_dimension_mismatch_rejected():
    with pytest.raises(PlanError):display_in_unit('20 ms','Hz')

@pytest.mark.parametrize('change',[{'amount':True},{'amount':float('nan')},{'unit':'kHz'},
    {'unit':'ratio'},{'tolerance':0.},{'tolerance':.00001},{'tolerance':2.},{'amount':25.},{'amount':-121.}])
def test_display_contract_bounds(change):
    values=dict(amount=-9.,unit='dB',tolerance=.1);values.update(change)
    with pytest.raises(ValidationError):DisplayTarget.model_validate(values)

@pytest.mark.parametrize('index,amount,unit',[(129,-9.,'dB'),(2049,750.,'Hz'),(4097,30.,'ms')])
def test_display_round_trip_and_restore(service,index,amount,unit):
    p=plan(service,index,amount,unit);assert not service.adapter.calls
    assert 'intermediate' in p['warning']
    result=execute(service,p)
    assert result['status']=='verified' and not service.adapter.writes
    after=result['receipts'][0]['after']['parameter']
    assert display_in_unit(after['display'],unit)==pytest.approx(amount)
    restore=service.restore_preview({'plan_id':p['id']})['plan']
    assert execute(service,restore)['status']=='verified'
    assert service.adapter.params[(6,0,index)]['value']==.5
    assert not result['project_saved'] and not result['audible_quality_evaluated']

@pytest.mark.parametrize('field,value',[('playing',True),('recording',True),('playing',None),('recording',0)])
def test_transport_must_be_explicitly_stopped_before_preview(service,field,value):
    service.adapter.transport[field]=value
    with pytest.raises(PlanError,match='playback'):plan(service)
    assert not service.adapter.calls and not service.journal.history()

def test_transport_rechecked_before_dispatch(service):
    p=plan(service);service.adapter.transport['playing']=True
    result=execute(service,p)
    assert result['status']=='blocked' and not service.adapter.calls and not service.adapter.writes

def test_capability_missing_refuses_preview(service):
    old=service.adapter.connection
    service.adapter.connection=lambda:{**old(),'plugin_display_units':False}
    with pytest.raises(PlanError,match='advertised'):plan(service)

def test_one_solver_operation_per_plan(service):
    a=Operation(kind='parameter_display',track=6,slot=0,parameter=129,
        value=DisplayTarget(amount=-9.,unit='dB',tolerance=.1))
    b=Operation(kind='pan',track=1,value=.1)
    with pytest.raises(ValidationError,match='isolated'):service.executor.prepare(PrepareRequest(operations=(a,b)))

def test_normalized_and_display_cannot_duplicate_a_control(service):
    a=Operation(kind='parameter_display',track=6,slot=0,parameter=129,
        value=DisplayTarget(amount=-9.,unit='dB',tolerance=.1))
    b=Operation(kind='parameter',track=6,slot=0,parameter=129,value=.4)
    with pytest.raises(ValidationError,match='One write'):service.executor.prepare(PrepareRequest(operations=(a,b)))

@pytest.mark.parametrize('failure',['lie','read_error','identity','unit','value','gate'])
def test_postdispatch_failures_latch_unknown_not_safe_to_retry(service,failure):
    p=plan(service);old=service.adapter.execute;read=service.adapter.display_parameter
    def bad(*args):
        result=old(*args)
        if failure=='lie':raise TimeoutError('lost response')
        if failure=='read_error':
            def unavailable(*a):raise NotDispatched('readback lost after dispatch')
            service.adapter.display_parameter=unavailable
        elif failure in ('identity','unit','value'):
            def changed(*a):
                row=read(*a)
                if failure=='identity':row['name']='Different control'
                if failure=='unit':row['display']='-9 ms'
                if failure=='value':row['display']='-3 dB'
                return row
            service.adapter.display_parameter=changed
        elif failure=='gate':
            def close(*a):raise RuntimeError('cannot close gate')
            service.adapter.end=close
        return result
    service.adapter.execute=bad
    result=execute(service,p)
    assert result['status']=='unknown_outcome' and service.journal.blocked()
    assert len(service.adapter.calls)==1
    with pytest.raises(PlanError):execute(service,p)
    assert len(service.adapter.calls)==1

def test_display_verified_without_claiming_fresh_normalized_value(service):
    p=plan(service);old=service.adapter.display_parameter
    def delayed(*args):
        row=old(*args);row['value']=.5
        return row
    service.adapter.display_parameter=delayed
    result=execute(service,p)
    assert result['status']=='verified'
    assert result['receipts'][0]['after']['parameter']['display']=='-9.000000 dB'

def test_old_numeric_operation_shape_is_unchanged():
    op=Operation(kind='parameter',track=1,slot=0,parameter=0,value=.3)
    assert op.model_dump()==dict(kind='parameter',track=1,slot=0,parameter=0,value=.3,reason='Explicit user adjustment')
