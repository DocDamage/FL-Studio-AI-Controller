"""Optional Windows global emergency stop. No keyboard recording or injection."""
import os
import threading
class StopHotkey:
    def __init__(self,callback):
        self.callback=callback; self.thread=None; self.thread_id=None; self.ready=threading.Event()
        self.status="Unavailable on this platform; use the red Stop button"
    def start(self):
        if os.name!="nt": return
        self.thread=threading.Thread(target=self._run,daemon=True,name="flcopilot-stop-hotkey")
        self.thread.start(); self.ready.wait(2)
    def _run(self):
        import ctypes
        from ctypes import wintypes
        u=ctypes.windll.user32
        self.thread_id=ctypes.windll.kernel32.GetCurrentThreadId()
        # Ctrl + Alt + Shift + F12; MOD_NOREPEAT prevents repeated callbacks.
        registered=False
        try:
            registered=bool(u.RegisterHotKey(None,0x4346,0x4000|1|2|4,0x7b))
            self.status="Ctrl+Alt+Shift+F12 registered" if registered else "Hotkey unavailable; use the red Stop button"
            self.ready.set()
            if not registered: return
            msg=wintypes.MSG()
            while u.GetMessageW(ctypes.byref(msg),None,0,0)>0:
                if msg.message==0x0312:
                    try: self.callback()
                    except Exception: pass
        finally:
            if registered: u.UnregisterHotKey(None,0x4346)
            self.ready.set()
    def close(self):
        if self.thread_id and self.thread and self.thread.is_alive():
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self.thread_id,0x0012,0,0)
            self.thread.join(timeout=2)
