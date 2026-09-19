import io
import json
import threading
import time
import urllib.request
import urllib.error
import pytest
from flcopilot.server import LocalServer
from flcopilot.service import Service
from flcopilot.demo import DemoAdapter
from flcopilot.contracts import PlanError
from flcopilot.assets import atomic_json
from flcopilot.mcp_relay import handle,tool_call

@pytest.fixture
def app(tmp_path):
    s=Service(tmp_path,DemoAdapter());server=LocalServer(s,0)
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    atomic_json(tmp_path/"server.json",{"origin":server.origin,"token":server.token})
    yield s,server,tmp_path
    server.shutdown();t.join(timeout=2);server.server_close();s.close()

def call(server,path,data=None,token=True,origin=None,host=None):
    headers={"Content-Type":"application/json"}
    if token:headers["Authorization"]="Bearer "+server.token
    if origin:headers["Origin"]=origin
    if host:headers["Host"]=host
    r=urllib.request.Request(server.origin+path,headers=headers,data=json.dumps(data).encode() if data is not None else None)
    return urllib.request.urlopen(r,timeout=10)

def poll(server,result):
    for _ in range(100):
        row=json.load(call(server,"/api/jobs/"+result["job"]))
        if row["status"]=="error":raise RuntimeError(row["error"])
        if row["status"]=="complete":return row["result"]
        time.sleep(.02)
    raise TimeoutError()

def test_status_requires_auth(app):
    _,srv,_=app
    with pytest.raises(urllib.error.HTTPError) as e:call(srv,"/api/status",token=False)
    assert e.value.code==403

@pytest.mark.parametrize("origin",["http://evil.test","null","http://127.0.0.1:1"])
def test_reject_cross_origin(app,origin):
    _,srv,_=app
    with pytest.raises(urllib.error.HTTPError) as e:call(srv,"/api/status",origin=origin)
    assert e.value.code==403

def test_reject_rebound_host(app):
    _,srv,_=app
    with pytest.raises(urllib.error.HTTPError) as e:call(srv,"/api/status",host="evil.test")
    assert e.value.code==403

def test_static_has_csp_and_no_token(app):
    _,srv,_=app
    with call(srv,"/",token=False) as r:
        data=r.read().decode();assert "script-src 'self'" in r.headers["Content-Security-Policy"]
        assert srv.token not in data and "Change preview" in data

@pytest.mark.parametrize("path",["/../local-settings.json","/api/file/../../secrets","/server.json","/api/nonexistent"])
def test_no_arbitrary_file_read(app,path):
    _,srv,_=app
    with pytest.raises(urllib.error.HTTPError):call(srv,path)

def test_http_plan_execute_lifecycle(app):
    s,srv,_=app
    observed=poll(srv,json.load(call(srv,"/api/inspect",{})));assert observed["backend"]=="demo"
    json.load(call(srv,"/api/settings",{"mode":"assist"}))
    prepared=poll(srv,json.load(call(srv,"/api/prompt",{"prompt":"Lower Drums by 2 dB"})))
    p=prepared["plan"];r=poll(srv,json.load(call(srv,"/api/execute",{"plan_id":p["id"],"digest":p["digest"],"confirm":True})))
    assert r["status"]=="verified" and r["demo"]
    assert json.load(call(srv,"/api/history"))[0]["result"]["status"]=="verified"
    assert s.adapter.track(1)["volume_db"]==-4

def test_http_mix_preview_is_no_write(app):
    s,srv,_=app;r=poll(srv,json.load(call(srv,"/api/mix",{"tracks":[1,2,3],"seconds":2.})))
    assert r["plan"] and not s.adapter.calls and r["observation"]["demo"]

def test_reconciliation_needs_fresh_evidence(app):
    s,srv,_=app;s.journal.block("test unknown")
    with pytest.raises(PlanError):s.reconcile({"digest":"guess","acknowledge":True})
    snap=s.inspect();s.adapter.tracks[1]["pan"]=-.1
    with pytest.raises(PlanError):s.reconcile({"digest":snap["reconcile_digest"],"acknowledge":True})
    snap=s.inspect();assert s.reconcile({"digest":snap["reconcile_digest"],"acknowledge":True})["rollback_performed"] is False
    assert not s.journal.blocked()

def test_mcp_initialize_and_tools(app):
    s,srv,path=app
    r=handle(path,{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}})
    assert r["result"]["serverInfo"]["name"]=="fl-studio-ai-copilot"
    assert len(handle(path,{"jsonrpc":"2.0","id":2,"method":"tools/list"})["result"]["tools"])==14
    assert handle(path,{"jsonrpc":"2.0","method":"notifications/initialized"}) is None

def test_mcp_uses_same_app_executor(app):
    s,srv,path=app;assert tool_call(path,"copilot_status",{})["demo"]
    p=tool_call(path,"copilot_prepare",{"operations":[{"kind":"pan","track":1,"value":.1}]})
    # MCP cannot switch the app out of read-only or weaken locks.
    r=poll(srv,tool_call(path,"copilot_inspect",{}));assert r["backend"]=="demo"
    result=handle(path,{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"copilot_settings","arguments":{"mode":"assist"}}})
    assert result["result"]["isError"] and not s.adapter.calls

def test_mcp_path_injection_rejected(app):
    _,_,path=app
    with pytest.raises(ValueError):tool_call(path,"copilot_job",{"id":"../../server.json"})

def test_settings_invalid_flag_does_not_partially_apply(app):
    s,_,_=app
    with pytest.raises(PlanError):s.settings({"mode":"assist","windows_menu_enabled":"yes"})
    assert s.executor.mode=="inspect"


def test_http_control_test_restore_requires_explicit_approvals(app):
    s,srv,_=app
    p=poll(srv,json.load(call(srv,"/api/control-test-preview",{"track":1})))["plan"]
    assert not s.adapter.calls
    json.load(call(srv,"/api/settings",{"mode":"assist"}))
    def apply(p):return poll(srv,json.load(call(srv,"/api/execute",{"plan_id":p["id"],"digest":p["digest"],"confirm":True})))
    assert apply(p)["status"]=="verified" and s.adapter.track(1)["volume_db"]==-3.
    inverse=poll(srv,json.load(call(srv,"/api/restore-preview",{"plan_id":p["id"]})))
    assert len(s.adapter.calls)==1
    assert apply(inverse["plan"])["status"]=="verified" and s.adapter.track(1)["volume_db"]==-2.


def test_http_diagnostics_export_safe(app):
    s,srv,_=app
    result=poll(srv,json.load(call(srv,"/api/diagnostics",{"export":True})))
    assert not result["report"]["live_read_ready"] and not s.adapter.calls
    assert "local_details" not in result["report"]
    asset=result["files"][0]
    raw=call(srv,"/api/file/"+asset["id"]).read()
    assert json.loads(raw)["demo"] and srv.token.encode() not in raw


@pytest.mark.parametrize("route,data",[("diagnostics",{}),("restore-preview",{"plan_id":"a"*32}),
                                      ("control-test-preview",{"track":1})])
def test_new_routes_require_auth(app,route,data):
    _,srv,_=app
    with pytest.raises(urllib.error.HTTPError) as e:call(srv,"/api/"+route,data,token=False)
    assert e.value.code==403


def test_mcp_new_tools_reuse_service(app):
    s,srv,path=app
    result=poll(srv,tool_call(path,"copilot_diagnostics",{}))
    assert result["report"]["demo"] and "local_details" not in result["report"]
    plan=poll(srv,tool_call(path,"copilot_control_test_preview",{"track":1}))["plan"]
    assert plan["purpose"]=="control_test" and not s.adapter.calls
    for name,args in [("copilot_diagnostics",{"execute":True}),
        ("copilot_control_test_preview",{"track":True}),("copilot_control_test_preview",{"track":0}),
        ("copilot_restore_preview",{"plan_id":"../../private"})]:
        with pytest.raises(ValueError):tool_call(path,name,args)


@pytest.mark.parametrize('route,data',[('plugin-scan',{'track':6,'slot':0}),
    ('plugin-preview',{'observation_id':'a'*32,'parameter':129,'value':.5})])
def test_workbench_routes_require_auth(app,route,data):
    _,srv,_=app
    with pytest.raises(urllib.error.HTTPError) as e:call(srv,'/api/'+route,data,token=False)
    assert e.value.code==403


def test_workbench_http_scan_preview_apply_restore(app):
    s,srv,_=app
    def post(route,data):return poll(srv,json.load(call(srv,'/api/'+route,data)))
    scan=post('plugin-scan',{'track':6,'slot':0})
    p=post('plugin-preview',{'observation_id':scan['observation_id'],'parameter':129,'mode':'display',
        'value':{'amount':-9.,'unit':'dB','tolerance':.1}})['plan']
    assert not s.adapter.calls
    with pytest.raises(RuntimeError,match='Inspect mode'):
        post('execute',{'plan_id':p['id'],'digest':p['digest'],'confirm':True})
    json.load(call(srv,'/api/settings',{'mode':'assist'}))
    assert post('execute',{'plan_id':p['id'],'digest':p['digest'],'confirm':True})['status']=='verified'
    assert s.adapter.display_parameter(6,0,129)['display']=='-9.000000 dB'
    inverse=post('restore-preview',{'plan_id':p['id']})['plan']
    assert post('execute',{'plan_id':inverse['id'],'digest':inverse['digest'],'confirm':True})['status']=='verified'
    assert s.adapter.params[(6,0,129)]['value']==.5


def test_workbench_mcp_uses_observations_and_never_self_approves(app):
    s,srv,path=app
    result=poll(srv,tool_call(path,'copilot_plugin_scan',{'track':6,'slot':0,'start':2048}))
    p=poll(srv,tool_call(path,'copilot_plugin_preview',{'observation_id':result['observation_id'],
        'parameter':2049,'mode':'display','value':{'amount':750.,'unit':'Hz','tolerance':1.}}))['plan']
    assert p['operations'][0]['parameter']==2049 and not s.adapter.calls
    for tool,args in [('copilot_plugin_scan',{'track':True,'slot':0}),
        ('copilot_plugin_preview',{'observation_id':result['observation_id'],'parameter':2049,'value':.5,'confirm':True})]:
        with pytest.raises(ValueError):tool_call(path,tool,args)


def test_workbench_script_has_csp_and_no_secret(app):
    _,srv,_=app
    with call(srv,'/workbench.js',token=False) as response:
        source=response.read().decode()
        assert 'plugin-scan' in source and srv.token not in source
        assert "script-src 'self'" in response.headers['Content-Security-Policy']


def test_legacy_parameter_endpoint_rejects_bad_slot(app):
    _,srv,_=app
    with pytest.raises(urllib.error.HTTPError):call(srv,'/api/parameters?track=1&slot=10')
