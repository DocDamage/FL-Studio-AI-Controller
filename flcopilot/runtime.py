"""Optional app-owned llama.cpp server. No Ollama service or cloud account required."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from .contracts import PlanError

class ManagedLlama:
    def __init__(self,exe,model,log_path,port=8081,gpu_layers=0):
        self.exe=Path(exe).expanduser().resolve(strict=True)
        self.model=Path(model).expanduser().resolve(strict=True)
        if not self.exe.is_file() or not self.model.is_file() or self.model.suffix.lower()!=".gguf":
            raise PlanError("Select an existing llama-server executable and a licensed compatible .gguf model")
        if not 1024<=port<=65535 or not 0<=gpu_layers<=256: raise PlanError("Invalid local runtime limits")
        self.log=Path(log_path).open("ab")
        self.process=subprocess.Popen([str(self.exe),"--model",str(self.model),"--host","127.0.0.1",
            "--port",str(port),"--alias","local","--ctx-size","4096","--threads","4","--n-gpu-layers",str(gpu_layers)],
            stdin=subprocess.DEVNULL,stdout=self.log,stderr=self.log,shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        self.endpoint=f"http://127.0.0.1:{port}/v1"
    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=5)
        self.log.close()
