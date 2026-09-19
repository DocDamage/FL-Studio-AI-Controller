import sys
import types
import pytest
from pydantic import BaseModel
from flcopilot.windows_menu import WindowsPluginMenu,Entry,clean_label

class MenuEntry(BaseModel):
    name:str
    kind:str
    menu_path:tuple[str,...]
class Dispatch(BaseModel):
    status:str
    error:str|None=None

@pytest.fixture
def upstream(monkeypatch):
    m=types.ModuleType("fl_studio_mcp.plugin_loading");m.PluginMenuEntry=MenuEntry;m.MenuDispatch=Dispatch
    monkeypatch.setitem(sys.modules,"fl_studio_mcp",types.ModuleType("fl_studio_mcp"))
    monkeypatch.setitem(sys.modules,"fl_studio_mcp.plugin_loading",m)
    monkeypatch.delenv("FL_BRIDGE_SANDBOXED",raising=False)

class Surface:
    rows=(Entry("Fruity Limiter","effect",("Add","Effect","Fruity Limiter")),)
    invoked=0
    fail=None
    def entries(self):return self.rows
    def resolve(self,path):return path
    def guard(self):
        if self.fail=="guard":raise RuntimeError("User input changed")
    def invoke(self,leaf):
        self.invoked+=1
        if self.fail=="timeout":raise TimeoutError("Reply lost after dispatch")

def test_menu_dispatch_once_with_guards(upstream):
    s=Surface();b=WindowsPluginMenu(destination_guard=lambda:True,surface_factory=lambda:s)
    e=b.entries()[0];r=b.load(e);assert r.status=="dispatched" and s.invoked==1

def test_unknown_never_retried(upstream):
    s=Surface();s.fail="timeout";b=WindowsPluginMenu(destination_guard=lambda:True,surface_factory=lambda:s)
    e=b.entries()[0];r=b.load(e);assert r.status=="unknown_outcome" and s.invoked==1

@pytest.mark.parametrize("guard",[None,lambda:False,lambda:1])
def test_destination_missing_never_inputs(upstream,guard):
    s=Surface();b=WindowsPluginMenu(destination_guard=guard,surface_factory=lambda:s)
    assert b.load(b.entries()[0]).status=="not_dispatched" and s.invoked==0

def test_empty_hint_or_name_not_a_target(upstream):
    s=Surface();b=WindowsPluginMenu(destination_guard=lambda:True,surface_factory=lambda:s);b.entries()
    assert b.load(MenuEntry(name="",kind="effect",menu_path=("Add","Effect",""))).status=="not_dispatched"
    assert s.invoked==0

def test_stale_menu_refused(upstream):
    s=Surface();b=WindowsPluginMenu(destination_guard=lambda:True,surface_factory=lambda:s);e=b.entries()[0];s.rows=()
    assert b.load(e).status=="not_dispatched" and s.invoked==0

def test_ambiguous_menu_refused(upstream):
    s=Surface();b=WindowsPluginMenu(destination_guard=lambda:True,surface_factory=lambda:s);e=b.entries()[0];s.rows=s.rows*2
    assert b.load(e).status=="not_dispatched" and s.invoked==0

def test_focus_or_input_change_refused(upstream):
    s=Surface();s.fail="guard";b=WindowsPluginMenu(destination_guard=lambda:True,surface_factory=lambda:s)
    assert b.load(b.entries()[0]).status=="not_dispatched" and s.invoked==0

def test_no_prior_inventory_no_dispatch(upstream):
    s=Surface();b=WindowsPluginMenu(destination_guard=lambda:True,surface_factory=lambda:s)
    e=MenuEntry(name="Fruity Limiter",kind="effect",menu_path=("Add","Effect","Fruity Limiter"))
    assert b.load(e).status=="not_dispatched" and s.invoked==0

def test_sandbox_disables_desktop(upstream,monkeypatch):
    monkeypatch.setenv("FL_BRIDGE_SANDBOXED","1")
    with pytest.raises(RuntimeError):WindowsPluginMenu().entries()

def test_menu_labels():assert clean_label("&Fruity && Co\tCtrl+N")=="Fruity & Co"
