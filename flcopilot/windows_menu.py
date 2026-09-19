"""Experimental Win32 named-menu backend for PostFader's MenuBackend protocol.

No coordinates, fuzzy matches, blind shortcuts, focus stealing, or scan dialogs.
An FL build with custom-drawn/unexposed menus returns a manual handoff.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from .contracts import NotDispatched

DENIED={"more plugins...","more plugins…","plugin picker","view plugin picker",
    "plugin database","browse plugin database","browse all installed plugins",
    "browse presets","refresh plugin list (fast scan)","manage plugins",
    "manage fl cloud plugins...","categories","simple","tree","pattern",
    "automation for last tweaked parameter"}

def clean_label(text):
    return text.replace("&&","\0").replace("&","").replace("\0","&").split("\t",1)[0].strip()

@dataclass(frozen=True)
class Entry:
    name: str
    kind: str
    menu_path: tuple[str,...]

class Win32Surface:
    def __init__(self):
        if os.name!="nt": raise NotDispatched("The Windows menu adapter requires Windows.")
        import ctypes
        from ctypes import wintypes as W
        from pywinauto import Desktop
        import psutil
        self.ctypes=ctypes; self.W=W; self.psutil=psutil
        self.user=ctypes.WinDLL("user32",use_last_error=True)
        self.user.GetForegroundWindow.restype=W.HWND
        self.user.GetLastActivePopup.argtypes=[W.HWND]; self.user.GetLastActivePopup.restype=W.HWND
        self.user.IsWindowEnabled.argtypes=[W.HWND]; self.user.IsWindowEnabled.restype=W.BOOL
        self.user.IsIconic.argtypes=[W.HWND]; self.user.IsIconic.restype=W.BOOL
        self.user.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
        windows=[]
        for w in Desktop(backend="win32").windows(visible_only=True):
            try:
                proc=psutil.Process(w.process_id())
                if proc.name().lower() in {"fl64.exe","fl.exe","flengine_x64.exe"} and not w.owner():
                    windows.append(w)
            except (psutil.Error,RuntimeError): continue
        if len(windows)!=1: raise NotDispatched("Exactly one visible FL Studio window is required.")
        self.window=windows[0]; self.pid=self.window.process_id()
        self.started=self.psutil.Process(self.pid).create_time()
        self.initial=self.fingerprint()
    def _input_tick(self):
        class LASTINPUTINFO(self.ctypes.Structure):
            _fields_=[("cbSize",self.W.UINT),("dwTime",self.W.DWORD)]
        info=LASTINPUTINFO(); info.cbSize=self.ctypes.sizeof(info)
        if not self.user.GetLastInputInfo(self.ctypes.byref(info)): raise NotDispatched("Cannot inspect user input state")
        return info.dwTime
    def fingerprint(self):
        hwnd=self.window.handle
        if self.psutil.Process(self.pid).create_time()!=self.started: raise NotDispatched("FL process was replaced")
        if int(self.user.GetForegroundWindow() or 0)!=hwnd:
            raise NotDispatched("Bring FL Studio's main window to the foreground; the copilot will not steal focus.")
        if self.user.IsIconic(hwnd) or not self.user.IsWindowEnabled(hwnd):
            raise NotDispatched("FL is minimized, disabled, or has a modal dialog")
        if int(self.user.GetLastActivePopup(hwnd) or 0)!=hwnd:
            raise NotDispatched("Close FL's popup/plugin/modal window before named-menu loading")
        rect=self.window.rectangle()
        return (self.pid,self.started,hwnd,rect.left,rect.top,rect.right,rect.bottom,self._input_tick())
    def guard(self):
        if self.fingerprint()!=self.initial:
            raise NotDispatched("Window geometry, focus, or user input changed; prepare a fresh action.")
    def _root(self):
        self.guard()
        menu=self.window.menu()
        if menu is None: raise NotDispatched("FL exposes no native Win32 menu on this setup; load the effect manually.")
        matches=[i for i in menu.items() if clean_label(i.text())=="Add"]
        if len(matches)!=1: raise NotDispatched("No unique native Add menu; custom-drawn/localized menus are not qualified.")
        sub=matches[0].sub_menu()
        if sub is None: raise NotDispatched("The Add submenu is not available without unqualified UI input.")
        return sub
    def entries(self):
        rows=[]
        def walk(menu,path,kind):
            if len(path)>11: raise NotDispatched("Menu is too deeply nested")
            for item in menu.items():
                name=clean_label(item.text())
                if not name or name.casefold() in DENIED or not item.is_enabled(): continue
                sub=item.sub_menu()
                current="effect" if len(path)==1 and name=="Effect" else kind
                route=path+(name,)
                if sub is not None: walk(sub,route,current)
                else: rows.append(Entry(name,current,route))
                if len(rows)>512: raise NotDispatched("Menu inventory exceeds the 512-entry bound")
        walk(self._root(),("Add",),"instrument")
        self.guard()
        return tuple(rows)
    def resolve(self,path):
        if not path or path[0]!="Add": raise NotDispatched("Only an observed Add menu path may be used")
        menu=self._root(); leaf=None
        for n,name in enumerate(path[1:]):
            matches=[i for i in menu.items() if clean_label(i.text())==name and i.is_enabled()]
            if len(matches)!=1: raise NotDispatched("Menu entry disappeared, is disabled, or is ambiguous")
            leaf=matches[0]
            if n<len(path)-2:
                menu=leaf.sub_menu()
                if menu is None: raise NotDispatched("Menu structure changed")
        if leaf is None or leaf.sub_menu() is not None or clean_label(leaf.text()).casefold() in DENIED:
            raise NotDispatched("Not a loadable plugin leaf")
        self.guard()
        return leaf
    def invoke(self,leaf):
        # select() addresses the named Win32 menu item, not a remembered pixel.
        self.guard()
        leaf.select()

class WindowsPluginMenu:
    def __init__(self,destination_guard=None,surface_factory=Win32Surface):
        self.destination_guard=destination_guard
        self.surface_factory=surface_factory
        self._last=()
    def entries(self):
        if os.environ.get("FL_BRIDGE_SANDBOXED")=="1":
            raise NotDispatched("Desktop actions disabled in sandbox")
        from fl_studio_mcp.plugin_loading import PluginMenuEntry
        rows=self.surface_factory().entries()
        self._last=tuple(PluginMenuEntry(name=r.name,kind=r.kind,menu_path=r.menu_path) for r in rows)
        return self._last
    def load(self,entry):
        from fl_studio_mcp.plugin_loading import MenuDispatch
        attempted=False
        try:
            if os.environ.get("FL_BRIDGE_SANDBOXED")=="1": raise NotDispatched("Sandbox blocks desktop input")
            if not self._last or entry not in self._last: raise NotDispatched("Only this backend's observed inventory is loadable")
            if entry.kind!="effect": raise NotDispatched("v0.1 Windows execution qualifies effect insertion only")
            surface=self.surface_factory()
            rows=surface.entries()
            matches=[r for r in rows if r.menu_path==entry.menu_path and r.name==entry.name and r.kind==entry.kind]
            if len(matches)!=1: raise NotDispatched("Menu changed or contains duplicate targets")
            if self.destination_guard is None or self.destination_guard() is not True:
                raise NotDispatched("An empty, selected mixer destination was not verified")
            leaf=surface.resolve(entry.menu_path)
            surface.guard()
            attempted=True
            surface.invoke(leaf)
            return MenuDispatch(status="dispatched")
        except Exception as exc:
            return MenuDispatch(status="unknown_outcome" if attempted else "not_dispatched",error=str(exc)[:1024])
