"""Launch UI, relay MCP to that same executor, or copy a saved FLP."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import webbrowser
from .assets import atomic_json
from .instance import InstanceLock

def default_workspace():
    base=Path(os.environ.get("LOCALAPPDATA",Path.home()/".local"/"share"))
    return base/"FLStudioAICopilot"

def load_config(path):
    p=Path(path)
    if not p.exists(): return {}
    if p.stat().st_size>16384: raise ValueError("Settings file too large")
    data=json.loads(p.read_text(encoding="utf-8-sig"))
    allowed={"midi_port","fl_user_data","local_endpoint","llama_exe","model","gpu_layers"}
    if not isinstance(data,dict) or set(data)-allowed: raise ValueError("Unknown local setting")
    for key in allowed-{"gpu_layers"}:
        if key in data and (not isinstance(data[key],str) or len(data[key])>4096): raise ValueError("Invalid local setting: "+key)
    if "gpu_layers" in data and (type(data["gpu_layers"])!=int or not 0<=data["gpu_layers"]<=100): raise ValueError("Invalid GPU layer count")
    return data

def main(argv=None):
    p=argparse.ArgumentParser(description="FL Studio AI Copilot — local companion development build")
    p.add_argument("--demo",action="store_true",help="Explicit simulator; never connects to FL")
    p.add_argument("--diagnose",action="store_true",help="Read-only diagnostics through the already-running app; no second MIDI owner")
    p.add_argument("--mcp",action="store_true",help="Serve stdio MCP by relaying to the already-running app")
    p.add_argument("--workspace",type=Path,default=None)
    p.add_argument("--port",type=int,default=8766)
    p.add_argument("--no-browser",action="store_true")
    p.add_argument("--config",default="local-settings.json")
    p.add_argument("--midi-port")
    p.add_argument("--local-endpoint")
    p.add_argument("--checkpoint",type=Path,help="Copy this already-saved FLP into the workspace; no live save")
    a=p.parse_args(argv)
    workspace=(a.workspace or (default_workspace()/"demo" if a.demo else default_workspace())).expanduser().resolve()
    if sum(bool(x) for x in (a.mcp,a.diagnose,a.checkpoint))>1:
        p.error("Choose only one of --mcp, --diagnose or --checkpoint")
    if a.diagnose:
        from .doctor_client import check_running_app
        return check_running_app(workspace)
    if a.mcp:
        from .mcp_relay import serve
        return serve(workspace)
    if a.checkpoint:
        from .checkpoints import checkpoint
        print(json.dumps(checkpoint(a.checkpoint,workspace/"checkpoints"),indent=2)); return 0
    if not 0<=a.port<=65535: p.error("Port must be between 0 and 65535")
    config=load_config(a.config)
    midi=a.midi_port or config.get("midi_port")
    if midi:
        if not midi.strip() or len(midi)>160: raise ValueError("Invalid MIDI endpoint name")
        os.environ["FL_BRIDGE_MIDI_PORT"]=midi
        os.environ["FL_BRIDGE_ENABLE_MIDI"]="1"
    if config.get("fl_user_data"):
        path=Path(config["fl_user_data"])
        if not path.is_absolute(): raise ValueError("FL user-data directory must be absolute")
        os.environ["FL_STUDIO_USER_DATA_DIR"]=str(path)
    # Never expose TCP bridge traffic remotely or inherit automatic write authorization.
    os.environ["FL_BRIDGE_HOST"]="127.0.0.1"
    os.environ.pop("FL_BRIDGE_ENABLE_WRITES",None)
    from .demo import DemoAdapter
    from .service import Service
    from .server import LocalServer
    from .hotkey import StopHotkey
    from .runtime import ManagedLlama
    endpoint=a.local_endpoint or config.get("local_endpoint")
    runtime=None
    with InstanceLock(workspace/"instance.lock"):
        service=server=hotkey=None
        descriptor=workspace/"server.json"
        try:
            if config.get("llama_exe") or config.get("model"):
                if not config.get("llama_exe") or not config.get("model"): raise ValueError("Both llama_exe and model are required")
                runtime=ManagedLlama(config["llama_exe"],config["model"],workspace/"llama.log",gpu_layers=config.get("gpu_layers",0))
                endpoint=runtime.endpoint
            if a.demo: adapter=DemoAdapter()
            else:
                try:
                    from .postfader import PostFaderAdapter
                    adapter=PostFaderAdapter()
                except Exception as exc:
                    from .unavailable import UnavailableAdapter
                    adapter=UnavailableAdapter(exc)
                    print("FL connection unavailable. Audio lab remains usable:",exc,file=sys.stderr)
            service=Service(workspace,adapter,endpoint)
            server=LocalServer(service,a.port)
            hotkey=StopHotkey(service.executor.stop); hotkey.start()
            service.hotkey_status=hotkey.status
            descriptor.parent.mkdir(parents=True,exist_ok=True)
            atomic_json(descriptor,{"pid":os.getpid(),"origin":server.origin,"token":server.token})
            if os.name!="nt": descriptor.chmod(0o600)
            url=server.origin+"/#"+server.token
            print("FL Studio AI Copilot 0.2.0 | "+("SIMULATOR" if a.demo else "LIVE adapter / local audio"))
            print("Open this private local URL:",url)
            print("Keep this console open. Ctrl+C exits. "+hotkey.status)
            if not a.no_browser: webbrowser.open(url)
            server.serve_forever(poll_interval=.2)
        except KeyboardInterrupt:
            print("Stopping owned work and closing the app.")
        finally:
            if hotkey: hotkey.close()
            if service: service.close()
            if server: server.server_close()
            if runtime: runtime.close()
            descriptor.unlink(missing_ok=True)
    return 0
