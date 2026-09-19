"""Directory iteration caches must not supply intake's file-identity evidence."""
from contextlib import contextmanager
from types import SimpleNamespace

from flcopilot import render_intake
from flcopilot.render_intake import FileStamp


def cached_scandir(monkeypatch, path, cached):
    """Model the documented Windows DirEntry zeros or an out-of-date entry."""
    calls = []

    def entry_stat(*, follow_symlinks=True):
        calls.append(follow_symlinks)
        return cached

    entry = SimpleNamespace(name=path.name, path=str(path), stat=entry_stat)

    @contextmanager
    def scan(_):
        yield iter([entry])

    monkeypatch.setattr(render_intake.os, 'scandir', scan)
    return calls


def test_scan_uses_real_identity_when_direntry_metadata_is_zero(tmp_path, monkeypatch):
    path = tmp_path / 'ordinary.wav'
    path.write_bytes(b'ordinary export')
    actual = path.lstat()
    cached = SimpleNamespace(st_mode=actual.st_mode, st_nlink=0,
                             st_dev=0, st_ino=0, st_file_attributes=0)
    calls = cached_scandir(monkeypatch, path, cached)
    found = render_intake._scan(tmp_path)
    assert found == {path.name: FileStamp.read(actual)}
    assert not calls, 'Cached DirEntry.stat is not file-identity evidence on Windows'


def test_scan_refreshes_metadata_when_entry_cache_is_stale(tmp_path, monkeypatch):
    path = tmp_path / 'growing.wav'
    path.write_bytes(b'old')
    cached = path.lstat()
    path.write_bytes(b'a longer new export')
    actual = path.lstat()
    calls = cached_scandir(monkeypatch, path, cached)
    assert render_intake._scan(tmp_path) == {path.name: FileStamp.read(actual)}
    assert not calls
