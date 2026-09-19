"""Bounded owned subprocesses; no shell interpolation or global process killing."""
from __future__ import annotations
import os
import subprocess
import tempfile
import time
from pathlib import Path
from .contracts import Stopped

def run_owned(args,*,stop=None,timeout=600.,cwd=None):
    with tempfile.TemporaryDirectory(prefix="flcopilot-process-") as temp:
        out=Path(temp)/"stdout"; err=Path(temp)/"stderr"
        with out.open("wb") as outf,err.open("wb") as errf:
            process=subprocess.Popen([str(a) for a in args],stdin=subprocess.DEVNULL,
                stdout=outf,stderr=errf,cwd=cwd,shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            started=time.monotonic()
            try:
                while process.poll() is None:
                    if stop is not None and stop.is_set(): raise Stopped("Audio job cancelled")
                    if time.monotonic()-started>timeout: raise TimeoutError("Audio subprocess timed out")
                    if err.stat().st_size>2_000_000 or out.stat().st_size>2_000_000:
                        raise RuntimeError("Subprocess diagnostic output exceeded its bound")
                    time.sleep(.08)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=3.)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3.)
        stdout=out.read_text(errors="replace")[-128000:]
        stderr=err.read_text(errors="replace")[-128000:]
        if process.returncode: raise RuntimeError(f"Audio process exited {process.returncode}: {stderr[-4000:]}")
        return stdout,stderr

def ffmpeg_path():
    import shutil
    configured=os.environ.get("FLCOPILOT_FFMPEG")
    if configured:
        path=Path(configured).expanduser().resolve(strict=True)
        if not path.is_file(): raise RuntimeError("Configured FFmpeg is not a file")
        return str(path)
    system=shutil.which("ffmpeg")
    if system: return system
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError("Install imageio-ffmpeg or configure an existing FFmpeg executable") from exc
