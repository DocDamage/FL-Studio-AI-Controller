"""Authenticated loopback UI. Explicit folder consent; no remote listeners or CORS wildcard."""
from __future__ import annotations
import hmac
import json
import mimetypes
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs,unquote,urlsplit
from .assets import MAX_UPLOAD
from .contracts import PlanError

class LocalServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,service,port=8766):
        self.service=service; self.token=secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1",port),Handler)
        self.port=self.server_address[1]
        self.origin=f"http://127.0.0.1:{self.port}"

class Handler(BaseHTTPRequestHandler):
    server_version="FLCopilot/0.4"
    protocol_version="HTTP/1.0"
    def setup(self):
        super().setup(); self.connection.settimeout(30)
    def log_message(self,*args): pass  # Never log tokens, user prompts or local paths.
    def _secure(self,auth=True):
        allowed={f"127.0.0.1:{self.server.port}",f"localhost:{self.server.port}"}
        if self.headers.get("Host") not in allowed: raise PermissionError("Invalid Host")
        origin=self.headers.get("Origin")
        if origin is not None and origin not in {self.server.origin,f"http://localhost:{self.server.port}"}:
            raise PermissionError("Cross-origin request rejected")
        if auth:
            supplied=self.headers.get("Authorization","")
            if not hmac.compare_digest(supplied,"Bearer "+self.server.token): raise PermissionError("Open the application through its launcher to authenticate.")
    def _headers(self,status,kind,length,extra=None):
        self.send_response(status)
        self.send_header("Content-Type",kind); self.send_header("Content-Length",str(length))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("X-Frame-Options","DENY")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        for key,value in (extra or {}).items(): self.send_header(key,value)
        self.end_headers()
    def _json(self,value,status=200):
        data=json.dumps(value,allow_nan=False).encode()
        self._headers(status,"application/json; charset=utf-8",len(data)); self.wfile.write(data)
    def _body(self):
        if self.headers.get("Transfer-Encoding"): raise PlanError("Chunked requests are not supported")
        if self.headers.get("Content-Type","").split(";")[0]!="application/json": raise PlanError("JSON content type required")
        n=int(self.headers.get("Content-Length","0"))
        if not 2<=n<=131072: raise PlanError("Invalid JSON request size")
        raw=self.rfile.read(n)
        if len(raw)!=n: raise PlanError("Incomplete request")
        def bad(value): raise PlanError("Non-finite JSON values are not permitted")
        obj=json.loads(raw,parse_constant=bad)
        if not isinstance(obj,dict): raise PlanError("JSON object required")
        return obj
    def _error(self,exc):
        self._json({"error":str(exc)},403 if isinstance(exc,PermissionError) else 400)
    def do_OPTIONS(self):
        self._json({"error":"Cross-origin requests are not supported"},403)
    def do_GET(self):
        try:
            path=urlsplit(self.path).path
            if path in ("/","/app.js","/workbench.js","/review.js","/render.js","/bounces.js","/acceptance.js","/acceptance.css","/style.css"):
                self._secure(auth=False)
                name={"/":"index.html","/app.js":"app.js","/workbench.js":"workbench.js","/review.js":"review.js","/render.js":"render.js","/bounces.js":"bounces.js","/acceptance.js":"acceptance.js","/acceptance.css":"acceptance.css","/style.css":"style.css"}[path]
                data=files("flcopilot").joinpath("web",name).read_bytes()
                kind={"index.html":"text/html; charset=utf-8","app.js":"text/javascript; charset=utf-8","workbench.js":"text/javascript; charset=utf-8","review.js":"text/javascript; charset=utf-8","render.js":"text/javascript; charset=utf-8","bounces.js":"text/javascript; charset=utf-8","acceptance.js":"text/javascript; charset=utf-8","acceptance.css":"text/css; charset=utf-8","style.css":"text/css; charset=utf-8"}[name]
                self._headers(200,kind,len(data)); self.wfile.write(data); return
            self._secure()
            s=self.server.service; q=parse_qs(urlsplit(self.path).query)
            if path=="/api/status": return self._json(s.status())
            if path=="/api/capabilities": return self._json(s.capabilities())
            if path=="/api/history": return self._json(s.journal.history())
            if path=="/api/reviews": return self._json(s.reviews.history())
            if path=="/api/render-acceptance": return self._json(s.acceptance.get())
            if path=="/api/render-watch": return self._json(s.render_watch_status())
            if path=="/api/assets": return self._json(s.assets.list())
            if path=="/api/parameters": return self._json(s.parameters(int(q["track"][0]),int(q["slot"][0])))
            if path.startswith("/api/jobs/"): return self._json(s.jobs.get(path.rsplit("/",1)[-1]))
            if path.startswith("/api/file/"):
                asset=path.rsplit("/",1)[-1]; target=s.assets.resolve(asset)
                kind=mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                self._headers(200,kind,target.stat().st_size,{"Content-Disposition":f'attachment; filename="{target.name}"'})
                with target.open("rb") as f:
                    while chunk:=f.read(1024*1024): self.wfile.write(chunk)
                return
            self._json({"error":"Not found"},404)
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception as exc: self._error(exc)
    def do_POST(self):
        try:
            self._secure(); s=self.server.service; path=urlsplit(self.path).path
            if path=="/api/import":
                if self.headers.get("Transfer-Encoding"): raise PlanError("Chunked uploads are not supported")
                if self.headers.get("Content-Type")!="application/octet-stream": raise PlanError("Binary audio upload required")
                n=int(self.headers.get("Content-Length","0"))
                name=unquote(self.headers.get("X-Filename","audio.wav"))
                return self._json(s.assets.import_stream(self.rfile,n,name))
            data=self._body()
            if path=="/api/inspect": result=s.jobs.submit("Inspecting FL session",s.inspect)
            elif path=="/api/render-acceptance": result=s.acceptance.save(data)
            elif path=="/api/render-acceptance-export": result=s.jobs.submit("Verifying export acceptance evidence",lambda:s.acceptance.export(data))
            elif path=="/api/bounces": result=s.bounces.list(data)
            elif path=="/api/bounce-get": result=s.bounces.get(data)
            elif path=="/api/bounce-edit": result=s.bounces.edit(data)
            elif path=="/api/bounce-verify": result=s.jobs.submit("Verifying stored bounce bytes",lambda:s.bounces.verify(data))
            elif path=="/api/render-watch": result=s.render_watch(data)
            elif path=="/api/render-watch-cancel": result=s.render_watch_cancel(data)
            elif path=="/api/settings": result=s.settings(data)
            elif path=="/api/prepare": result=s.prepare(data)
            elif path=="/api/prompt":
                if set(data)!={"prompt"}: raise PlanError("Expected prompt only")
                result=s.jobs.submit("Preparing a bounded plan",lambda:s.prompt(data["prompt"]))
            elif path=="/api/execute":
                delay=data.pop("focus_handoff",False)
                if type(delay)!=bool: raise PlanError("Boolean focus handoff required")
                result=s.jobs.submit("Applying and verifying approved changes",lambda:s.execute(data,5. if delay else 0.))
            elif path=="/api/plugin-scan": result=s.jobs.submit("Reading a bounded plugin parameter window",lambda:s.plugin_scan(data))
            elif path=="/api/plugin-preview": result=s.jobs.submit("Checking observed plugin control before preview",lambda:s.plugin_preview(data))
            elif path=="/api/restore-preview": result=s.jobs.submit("Checking verified state for a restore preview",lambda:s.restore_preview(data))
            elif path=="/api/control-test-preview": result=s.jobs.submit("Preparing a 1 dB control test",lambda:s.control_test_preview(data))
            elif path=="/api/mix": result=s.jobs.submit("Observing peaks and preparing gain staging",lambda:s.mix(data))
            elif path=="/api/analyze":
                if set(data)!={"asset"}: raise PlanError("Expected asset only")
                result=s.jobs.submit("Measuring imported audio",lambda:s.analyze(data["asset"]))
            elif path=="/api/master": result=s.jobs.submit("Rendering and verifying WAV master",lambda:s.master(data))
            elif path=="/api/compare":
                if set(data)!={"a","b"}: raise PlanError("Expected baseline a and candidate b")
                result=s.jobs.submit("Comparing audio measurements",lambda:s.compare(data["a"],data["b"]))
            elif path=="/api/review-audio": result=s.jobs.submit("Checking exports and rendering level-matched A/B",lambda:s.review_audio(data))
            elif path=="/api/review-get": result=s.review_get(data)
            elif path=="/api/review-decision": result=s.review_decision(data)
            elif path=="/api/midi": result=s.create_midi(data)
            elif path=="/api/stop": result=s.executor.stop()
            elif path=="/api/reset-stop":
                with s.jobs.lock:
                    if any(r["status"] in ("running","queued") for r in s.jobs.rows.values()):
                        raise PlanError("Wait until all in-flight work settles before resetting stop")
                s.executor.reset_stop(); result=s.status()
            elif path=="/api/reconcile": result=s.reconcile(data)
            elif path=="/api/diagnostics":
                if set(data)-{"export"} or type(data.get("export",False)) is not bool:
                    raise PlanError("Only an optional boolean export flag is supported")
                result=s.jobs.submit("Checking connection without changing FL",lambda:s.diagnostics(data.get("export",False)))
            elif path=="/api/menu-probe":
                def probe():
                    if s.executor.stop_event.wait(5.): raise PlanError("Probe cancelled")
                    return s.adapter.menu_inventory()
                result=s.jobs.submit("Focus FL Studio now • native menu probe",probe)
            else: return self._json({"error":"Not found"},404)
            self._json(result)
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception as exc: self._error(exc)
