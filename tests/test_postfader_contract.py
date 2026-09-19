"""Contract doubles based on source-reviewed V10. NOT a live/upstream integration suite."""
import sys
import threading
import types
import pytest
from pydantic import BaseModel,ConfigDict
from flcopilot.postfader import PostFaderAdapter
from flcopilot.contracts import Operation,NotDispatched

class ExpectedVolume(BaseModel):
    model_config=ConfigDict(extra='forbid')
    volume_normalized:float|None=None
    volume_db:float|None=None
class ExpectedParameter(BaseModel):
    model_config=ConfigDict(extra='forbid')
    normalized_value:float|None=None
    display_text:str|None=None
class Receipt(BaseModel):
    verified:bool=True
    plugin_name:str='Effect'
    parameter_name:str='Drive'
class Writer:
    def __init__(self):self.calls=[]
    def set_plugin_parameter(self,*,track_index,slot_index,parameter_index,normalized_value,allow_master,session_fingerprint,expected_before):
        self.calls.append(locals());return Receipt()
    def set_mixer_volume_db(self,*,track_index,volume_db,allow_master,session_fingerprint,expected_before):
        self.calls.append(locals());return Receipt()
class Mode:
    def __init__(self):self.calls=[];self.fail=False
    def set_write_mode(self,**kwargs):
        self.calls.append(kwargs)
        if self.fail and kwargs['enabled']:raise TimeoutError('lost gate acknowledgment')
@pytest.fixture
def adapter(monkeypatch):
    m=types.ModuleType('fl_studio_mcp.contracts');m.ExpectedMixerVolumeState=ExpectedVolume;m.ExpectedPluginParameterState=ExpectedParameter
    monkeypatch.setitem(sys.modules,'fl_studio_mcp',types.ModuleType('fl_studio_mcp'))
    monkeypatch.setitem(sys.modules,'fl_studio_mcp.contracts',m)
    a=PostFaderAdapter.__new__(PostFaderAdapter);a.io=threading.RLock();a.writer=Writer();a.mode=Mode();a._gate_owned=False
    c=dict(connected=True,compatible=True,session_fingerprint='s'*32,bridge_provenance_verified=True,project_load_epoch=True,verified_writes_enabled=False)
    a.connection=lambda:c.copy();a.parameter=lambda *args:dict(plugin='Effect',name='Drive',value=.5)
    return a,c

def test_real_v10_parameter_before_schema(adapter):
    a,c=adapter;r=a.execute(Operation(kind='parameter',track=1,slot=0,parameter=12,value=.3),{'parameter':dict(plugin='Effect',name='Drive',value=.5)},c['session_fingerprint'])
    assert r['verified'] and len(a.writer.calls)==1
    assert a.writer.calls[0]['expected_before'].model_dump()=={'normalized_value':.5,'display_text':None}

def test_parameter_identity_mismatch_predispatch(adapter):
    a,c=adapter
    with pytest.raises(NotDispatched):a.execute(Operation(kind='parameter',track=1,slot=0,parameter=12,value=.3),{'parameter':dict(plugin='Other',name='Drive',value=.5)},c['session_fingerprint'])
    assert not a.writer.calls

def test_parameter_receipt_mismatch_unknown_not_predispatch(adapter):
    a,c=adapter;a.writer.set_plugin_parameter=lambda **kwargs:Receipt(plugin_name='Wrong effect')
    with pytest.raises(RuntimeError,match='outcome unknown'):a.execute(Operation(kind='parameter',track=1,slot=0,parameter=12,value=.3),{'parameter':dict(plugin='Effect',name='Drive',value=.5)},c['session_fingerprint'])

def test_exact_volume_contract(adapter):
    a,c=adapter;a.execute(Operation(kind='volume',track=1,value=-6.),{'track':dict(volume_db=-4.,volume_normalized=.6)},c['session_fingerprint'])
    assert a.writer.calls[0]['expected_before'].volume_db==-4

@pytest.mark.parametrize('field',['bridge_provenance_verified','project_load_epoch'])
def test_missing_protection_blocks_gate(adapter,field):
    a,c=adapter;c[field]=False
    with pytest.raises(NotDispatched):a.begin(c['session_fingerprint'])
    a.end(c['session_fingerprint']);assert not a.mode.calls

def test_another_clients_gate_is_not_closed(adapter):
    a,c=adapter;c['verified_writes_enabled']=True
    with pytest.raises(NotDispatched):a.begin(c['session_fingerprint'])
    a.end(c['session_fingerprint']);assert not a.mode.calls

def test_own_gate_closed_after_lost_enable_ack(adapter):
    a,c=adapter;a.mode.fail=True
    with pytest.raises(TimeoutError):a.begin(c['session_fingerprint'])
    a.end(c['session_fingerprint']);assert [x['enabled'] for x in a.mode.calls]==[True,False]
    assert a._gate_owned is False

def test_new_session_gate_not_touched(adapter):
    a,c=adapter;session=c['session_fingerprint'];a.begin(session);c['session_fingerprint']='t'*32
    with pytest.raises(RuntimeError):a.end(session)
    assert len(a.mode.calls)==1


def test_stale_gate_ownership_not_reused_on_next_run(adapter):
    a,c=adapter;a._gate_owned=True;c['verified_writes_enabled']=True
    with pytest.raises(NotDispatched):a.begin(c['session_fingerprint'])
    a.end(c['session_fingerprint']);assert not a.mode.calls


def test_mute_v10_explicit_state_contract(adapter):
    a,c=adapter
    def setter(*,track_index,muted,allow_master,session_fingerprint,expected_before):
        assert track_index==1 and muted is True and expected_before is False
        assert not allow_master and session_fingerprint==c['session_fingerprint']
        return Receipt()
    a.writer.set_mixer_mute=setter
    result=a.execute(Operation(kind='mute',track=1,value=True),{'track':{'muted':False}},c['session_fingerprint'])
    assert result['verified']


def test_stereo_v10_explicit_state_contract(adapter):
    a,c=adapter
    def setter(*,track_index,stereo_separation,allow_master,session_fingerprint,expected_before):
        assert track_index==1 and stereo_separation==.5 and expected_before==.1
        assert not allow_master and session_fingerprint==c['session_fingerprint']
        return Receipt()
    a.writer.set_mixer_stereo_separation=setter
    result=a.execute(Operation(kind='stereo',track=1,value=.5),{'track':{'stereo_separation':.1}},c['session_fingerprint'])
    assert result['verified']
