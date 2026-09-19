"""Small stdio MCP relay. All DAW mutations run in the single desktop service.

This is not a proxy for all 134 upstream tools. It exposes only our bounded API.
No shell execution, arbitrary file paths, model-produced scripts, or auto-approval.
"""
from __future__ import annotations
import json
import re
import sys
import urllib.request
from urllib.parse import urlsplit
from .planner import NoRedirect
from .contracts import PrepareRequest,MasterRequest,Approval

def schema(props=None,required=()):
    return {"type":"object","properties":props or {},"required":list(required),"additionalProperties":False}
TOOLS=[
    {"name":"copilot_status","description":"Read mode and locks. Start the desktop app first.","inputSchema":schema()},
    {"name":"copilot_inspect","description":"Read actual project through the app. Returns a job ID; poll copilot_job.","inputSchema":schema()},
    {"name":"copilot_prepare","description":"Prepare bounded mixer operations for review, without changing FL. Use the returned digest for explicit approval.","inputSchema":PrepareRequest.model_json_schema()},
    {"name":"copilot_execute","description":"ONLY after explicit user authorization for this exact preview. Desktop must be in Assist/Finish. Never invent confirmation. Returns a job ID, never immediate success.","inputSchema":Approval.model_json_schema()},
    {"name":"copilot_job","description":"Read the result/evidence of one asynchronous application job.","inputSchema":schema({"id":{"type":"string","pattern":"^[a-f0-9]{32}$"}},("id",))},
    {"name":"copilot_assets","description":"List audio explicitly imported in the desktop UI and actual output assets.","inputSchema":schema()},
    {"name":"copilot_analyze","description":"Measure an imported asset. Returns a job ID.","inputSchema":schema({"asset":{"type":"string","pattern":"^[a-f0-9]{32}$"}},("asset",))},
    {"name":"copilot_master","description":"After a user request, render a separate loudness-finished WAV and A/B files. Does not alter the source or FL project; not an artistic-quality guarantee.","inputSchema":MasterRequest.model_json_schema()},
    {"name":"copilot_diagnostics","description":"Read-only connection checks through the running app. Returns a job for a privacy-filtered report. Does not enable writes or qualify the host by itself.","inputSchema":schema()},
    {"name":"copilot_restore_preview","description":"Prepare a compensating-control preview from one fully verified run. Does not execute. Requires unchanged captured state and a separate explicit approval; no whole-project rollback.","inputSchema":schema({"plan_id":{"type":"string","pattern":"^[a-f0-9]{32}$"}},("plan_id",))},
    {"name":"copilot_control_test_preview","description":"Prepare, never execute, exactly a 1 dB reduction on a non-master insert. Use a saved project copy. Restore is a separately approved plan.","inputSchema":schema({"track":{"type":"integer","minimum":1,"maximum":999}},("track",))},
    {"name":"copilot_stop","description":"Latch emergency stop; no later operation starts. In-flight writes are not undone.","inputSchema":schema()},
]

def http_call(workspace,route,data=None):
    path=workspace/"server.json"
    if not path.exists(): raise RuntimeError("Start FL Studio AI Copilot with the matching workspace first.")
    if path.stat().st_size>4096: raise RuntimeError("Invalid app descriptor")
    info=json.loads(path.read_text()); p=urlsplit(info["origin"])
    if p.scheme!="http" or p.hostname!="127.0.0.1" or not p.port or p.path or p.query or p.fragment or p.username:
        raise RuntimeError("App descriptor is not a literal loopback endpoint")
    req=urllib.request.Request(info["origin"]+route,
        data=None if data is None else json.dumps(data,allow_nan=False).encode(),
        headers={"Authorization":"Bearer "+info["token"],"Content-Type":"application/json"})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open(req,timeout=60) as resp: raw=resp.read(4*1024*1024+1)
    if len(raw)>4*1024*1024: raise RuntimeError("App response exceeded limit")
    return json.loads(raw)

def tool_call(workspace,name,args):
    if not isinstance(args,dict): raise ValueError("Tool arguments must be an object")
    empty={"copilot_status":("/api/status",False),"copilot_inspect":("/api/inspect",True),
        "copilot_assets":("/api/assets",False),"copilot_stop":("/api/stop",True)}
    if name in empty:
        if args: raise ValueError("This tool takes no arguments")
        route,post=empty[name]; return http_call(workspace,route,{} if post else None)
    if name=="copilot_job":
        if set(args)!={"id"} or not isinstance(args["id"],str) or not re.fullmatch("[a-f0-9]{32}",args["id"]): raise ValueError("Invalid job ID")
        return http_call(workspace,"/api/jobs/"+args["id"])
    if name=="copilot_analyze":
        if set(args)!={"asset"} or not isinstance(args["asset"],str) or not re.fullmatch("[a-f0-9]{32}",args["asset"]): raise ValueError("Invalid asset ID")
        return http_call(workspace,"/api/analyze",args)
    if name=="copilot_diagnostics":
        if args: raise ValueError("Diagnostics takes no arguments")
        return http_call(workspace,"/api/diagnostics",{"export":True})
    if name=="copilot_restore_preview":
        if set(args)!={"plan_id"} or not isinstance(args["plan_id"],str) or not re.fullmatch("[a-f0-9]{32}",args["plan_id"]):
            raise ValueError("Invalid source plan ID")
        return http_call(workspace,"/api/restore-preview",args)
    if name=="copilot_control_test_preview":
        if set(args)!={"track"} or type(args["track"]) is not int or not 1<=args["track"]<=999:
            raise ValueError("A non-master insert (1–999) is required")
        return http_call(workspace,"/api/control-test-preview",args)
    models={"copilot_prepare":(PrepareRequest,"/api/prepare"),"copilot_execute":(Approval,"/api/execute"),"copilot_master":(MasterRequest,"/api/master")}
    if name not in models: raise ValueError("Unknown tool")
    model,route=models[name]; parsed=model.model_validate_json(json.dumps(args))
    return http_call(workspace,route,parsed.model_dump(mode="json"))

def handle(workspace,msg):
    if not isinstance(msg,dict) or msg.get("jsonrpc")!="2.0": return {"jsonrpc":"2.0","id":None,"error":{"code":-32600,"message":"Invalid request"}}
    if "id" not in msg: return None
    ident=msg["id"]; method=msg.get("method"); params=msg.get("params") or {}
    try:
        if method=="initialize":
            result={"protocolVersion":"2025-06-18","capabilities":{"tools":{"listChanged":False}},
                "serverInfo":{"name":"fl-studio-ai-copilot","version":"0.2.0"},
                "instructions":"Use one running desktop app. Read-only by default. Never equate demo/technical readback with audible quality. Approval must come from the user."}
        elif method=="ping": result={}
        elif method=="tools/list": result={"tools":TOOLS}
        elif method=="tools/call":
            try:
                value=tool_call(workspace,params["name"],params.get("arguments",{}))
                result={"content":[{"type":"text","text":json.dumps(value,allow_nan=False)}],"isError":False}
            except Exception as exc: result={"content":[{"type":"text","text":str(exc)}],"isError":True}
        else: return {"jsonrpc":"2.0","id":ident,"error":{"code":-32601,"message":"Method not found"}}
        return {"jsonrpc":"2.0","id":ident,"result":result}
    except Exception as exc: return {"jsonrpc":"2.0","id":ident,"error":{"code":-32602,"message":str(exc)}}

def serve(workspace):
    while True:
        line=sys.stdin.buffer.readline(131073)
        if not line: return 0
        if len(line)>131072:
            # Do not interpret the tail of an oversized request as a fresh command.
            print("Oversized MCP request; closing relay",file=sys.stderr); return 2
        try: response=handle(workspace,json.loads(line))
        except Exception: response={"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":"Invalid JSON"}}
        if response is not None:
            sys.stdout.write(json.dumps(response,allow_nan=False)+"\n"); sys.stdout.flush()
