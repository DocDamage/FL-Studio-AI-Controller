import threading,time
import pytest
from flcopilot.assets import AssetStore
from flcopilot.contracts import PlanError,Stopped
from flcopilot.render_intake import FileStamp,import_render,snapshot_folder,wait_for_render

def test_new_stable_render_is_detected_and_copied(tmp_path):
    folder=tmp_path/"renders";folder.mkdir();baseline=snapshot_folder(folder)
    path=folder/"mix.wav";path.write_bytes(b"RIFF"+b"x"*100)
    found,stamp=wait_for_render(folder,baseline,threading.Event(),timeout=2,stable_seconds=.01)
    store=AssetStore(tmp_path/"workspace");record=import_render(store,found,stamp)
    assert record["source"]=="watched_fl_export" and not record["render_triggered_by_app"]
    assert path.read_bytes()==b"RIFF"+b"x"*100 and store.resolve(record["id"]).read_bytes()==path.read_bytes()

def test_existing_unchanged_file_is_ignored(tmp_path):
    folder=tmp_path/"renders";folder.mkdir();(folder/"old.wav").write_bytes(b"x")
    baseline=snapshot_folder(folder)
    with pytest.raises(PlanError,match="No stable"):wait_for_render(folder,baseline,threading.Event(),timeout=1,stable_seconds=.01)

def test_multiple_new_files_are_ambiguous(tmp_path):
    folder=tmp_path/"renders";folder.mkdir();baseline=snapshot_folder(folder)
    (folder/"a.wav").write_bytes(b"a");(folder/"b.wav").write_bytes(b"b")
    with pytest.raises(PlanError,match="Multiple"):wait_for_render(folder,baseline,threading.Event(),timeout=2,stable_seconds=.01)

def test_cancelled_watch_stops(tmp_path):
    folder=tmp_path/"renders";folder.mkdir();stop=threading.Event();stop.set()
    with pytest.raises(Stopped):wait_for_render(folder,snapshot_folder(folder),stop,timeout=2)

@pytest.mark.parametrize("timeout",[0,601,True,"10"])
def test_timeout_is_bounded(tmp_path,timeout):
    folder=tmp_path/"renders";folder.mkdir()
    with pytest.raises(PlanError,match="timeout"):wait_for_render(folder,{},threading.Event(),timeout=timeout)

def test_changed_render_before_import_is_refused(tmp_path):
    folder=tmp_path/"renders";folder.mkdir();path=folder/"mix.wav";path.write_bytes(b"one")
    stat=path.stat();stamp=FileStamp(stat.st_size,stat.st_mtime_ns);time.sleep(.002);path.write_bytes(b"changed")
    with pytest.raises(PlanError,match="changed before"):import_render(AssetStore(tmp_path/"w"),path,stamp)
