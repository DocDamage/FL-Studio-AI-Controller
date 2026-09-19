"""Windows creation timestamps must agree across path and open-handle observations."""
from types import SimpleNamespace

import pytest
from flcopilot import render_intake as intake


def observation(**changes):
    fields = dict(st_size=192088, st_mtime_ns=200, st_dev=37, st_ino=918,
                  st_ctime_ns=100, st_birthtime_ns=100)
    return SimpleNamespace(**(fields | changes))


def test_windows_path_and_handle_use_same_creation_timestamp(monkeypatch):
    monkeypatch.setattr(intake, "WINDOWS_TIMESTAMPS", True)
    path = observation()
    handle = observation(st_ctime_ns=200)
    stamp = intake.FileStamp.read(path)
    assert stamp.ctime_ns == 100
    assert stamp.matches(handle)
    assert stamp == intake.FileStamp.read(handle)


@pytest.mark.parametrize("field", ["st_size", "st_mtime_ns", "st_dev", "st_ino", "st_birthtime_ns"])
def test_windows_real_identity_changes_are_still_rejected(monkeypatch, field):
    monkeypatch.setattr(intake, "WINDOWS_TIMESTAMPS", True)
    original = observation()
    changed = observation(**{field: getattr(original, field) + 1})
    assert not intake.FileStamp.read(original).matches(changed)


def test_posix_retains_metadata_change_detection_even_with_birthtime(monkeypatch):
    monkeypatch.setattr(intake, "WINDOWS_TIMESTAMPS", False)
    assert not intake.FileStamp.read(observation()).matches(observation(st_ctime_ns=201))


def test_older_windows_falls_back_to_creation_ctime(monkeypatch):
    monkeypatch.setattr(intake, "WINDOWS_TIMESTAMPS", True)
    value = observation()
    del value.st_birthtime_ns
    assert intake.FileStamp.read(value).ctime_ns == value.st_ctime_ns
    assert intake.FileStamp.read(value).matches(value)
