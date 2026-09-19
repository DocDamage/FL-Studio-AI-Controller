"""Bounded, one-shot intake of an explicitly user-selected local export folder.

Stability is a filesystem heuristic, not proof that FL produced a file or finished
rendering. No DAW commands are issued. Only newly named, non-linked regular files
are eligible, and publication follows byte/identity verification of a staged copy.
"""
from __future__ import annotations

import hashlib
import math
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from .assets import AUDIO_SUFFIXES, MAX_UPLOAD, file_hash
from .contracts import PlanError, Stopped

MAX_WATCH_SECONDS = 600
MAX_FOLDER_ENTRIES = 4096
STABLE_SECONDS = 1.0


@dataclass(frozen=True)
class FileStamp:
    size: int
    mtime_ns: int
    device: int = 0
    inode: int = 0
    ctime_ns: int = 0

    @classmethod
    def read(cls, value):
        return cls(value.st_size, value.st_mtime_ns, value.st_dev,
                   value.st_ino, value.st_ctime_ns)

    def matches(self, value):
        current = FileStamp.read(value)
        return (self.size == current.size and self.mtime_ns == current.mtime_ns
                and (not self.device or self.device == current.device)
                and (not self.inode or self.inode == current.inode)
                and (not self.ctime_ns or self.ctime_ns == current.ctime_ns))


class FolderSnapshot(dict):
    def __init__(self, entries, identity):
        super().__init__(entries)
        self.identity = identity


def _linked(value):
    return stat.S_ISLNK(value.st_mode) or bool(
        getattr(value, "st_file_attributes", 0) & 0x400)  # Windows reparse point


def _root(folder):
    path = Path(folder).expanduser()
    if not path.is_absolute() or str(path).startswith(("\\\\", "//")):
        raise PlanError("Choose an absolute local render folder, not a network path")
    try:
        for part in (*reversed(path.parents), path):
            if _linked(part.lstat()):
                raise PlanError("Render folder cannot use symbolic links or reparse points")
        if not path.is_dir():
            raise PlanError("Render watch folder does not exist")
        return path.resolve(strict=True)
    except OSError as exc:
        raise PlanError("Cannot inspect render watch folder") from exc


def _scan(root):
    out = {}
    try:
        with os.scandir(root) as entries:
            for count, entry in enumerate(entries, 1):
                if count > MAX_FOLDER_ENTRIES:
                    raise PlanError("Render folder has too many entries; choose a smaller export folder")
                if Path(entry.name).suffix.lower() not in AUDIO_SUFFIXES:
                    continue
                # Windows DirEntry.stat reports zero dev/inode/link counts.
                # Fetch fresh no-follow metadata; do not weaken the link guard.
                value = os.stat(root / entry.name, follow_symlinks=False)
                if _linked(value) or (stat.S_ISREG(value.st_mode) and value.st_nlink != 1):
                    raise PlanError("Render audio must not be a symbolic link, reparse point or hard link")
                if stat.S_ISREG(value.st_mode):
                    out[entry.name] = FileStamp.read(value)
    except OSError as exc:
        raise PlanError("Render folder changed or cannot be inspected; arm it again") from exc
    return out


def snapshot_folder(folder: str | Path) -> FolderSnapshot:
    root = _root(folder)
    value = root.stat()
    return FolderSnapshot(_scan(root), (value.st_dev, value.st_ino))


def _duration(value, low, high, name):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise PlanError(f"Render watch {name} must be {low:g} to {high:g} seconds")


def wait_for_render(folder, baseline, stop, timeout=120, stable_seconds=STABLE_SECONDS):
    _duration(timeout, 1, MAX_WATCH_SECONDS, "timeout")
    _duration(stable_seconds, .001, MAX_WATCH_SECONDS, "stability interval")
    if not isinstance(baseline, dict) or any(not isinstance(s, FileStamp) for s in baseline.values()):
        raise PlanError("Render watch baseline is required")
    root = _root(folder)
    deadline = time.monotonic() + float(timeout)
    observed = {}
    seen = set()
    while time.monotonic() < deadline:
        if stop.is_set():
            raise Stopped("Render watch cancelled")
        _root(root)
        value = root.stat()
        if getattr(baseline, "identity", (value.st_dev, value.st_ino)) != (value.st_dev, value.st_ino):
            raise PlanError("Render folder was replaced; arm it again")
        current = _scan(root)
        # A pre-existing name is never promoted, even after overwrite/recreation.
        for name, stamp in baseline.items():
            if current.get(name) != stamp:
                raise PlanError("An existing audio file changed or was removed; use a new export filename")
        new = set(current) - set(baseline)
        seen.update(new)
        # Include unfinished files: a stable A plus still-writing B is ambiguous.
        if len(seen) > 1:
            raise PlanError("Multiple new render files appeared; choose a clean export folder and try again")
        for name in new:
            stamp = current[name]
            if stamp.size > MAX_UPLOAD:
                raise PlanError("Render exceeds the 300 MiB intake limit")
            previous = observed.get(name)
            now = time.monotonic()
            if stamp.size and previous and previous[0] == stamp and now - previous[1] >= stable_seconds:
                if stop.is_set():
                    raise Stopped("Render watch cancelled")
                return root / name, stamp
            if not previous or previous[0] != stamp:
                observed[name] = (stamp, now)
        # A vanished file cannot accumulate stability time while absent.
        observed = {n: v for n, v in observed.items() if n in current}
        stop.wait(.05)
    raise PlanError("No stable new audio render appeared before the timeout")


def verify_folder(folder, baseline, name, expected):
    """Recheck ambiguity/root identity immediately before publishing a copy."""
    current = snapshot_folder(folder)
    if current.identity != baseline.identity:
        raise PlanError("Render folder was replaced; arm it again")
    if any(current.get(n) != stamp for n, stamp in baseline.items()):
        raise PlanError("An existing audio file changed or was removed; use a new export filename")
    if set(current) - set(baseline) != {name}:
        raise PlanError("Multiple or missing render files detected during import; no input was published")
    if current[name] != expected:
        raise PlanError("Render changed during import; no input was published")


def import_render(assets, path, expected: FileStamp, stop=None, metadata=None, folder_guard=None):
    path = Path(path)
    _root(path.parent)

    def cancelled():
        if stop is not None and stop.is_set():
            raise Stopped("Render watch cancelled")

    def check(value, when):
        if (_linked(value) or not stat.S_ISREG(value.st_mode) or value.st_nlink != 1
                or not expected.matches(value)):
            raise PlanError(f"Render changed {when} import; no input was published")

    cancelled()
    try:
        check(path.lstat(), "before")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as source:
            check(os.fstat(source.fileno()), "before")

            def verify(staged):
                cancelled()
                check(os.fstat(source.fileno()), "during")
                check(path.lstat(), "during")
                # Independent source read binds the copied bytes, not just size/mtime.
                source.seek(0)
                h = hashlib.sha256()
                remaining = expected.size
                while remaining:
                    cancelled()
                    block = source.read(min(1024 * 1024, remaining))
                    if not block:
                        raise PlanError("Render changed during import; no input was published")
                    h.update(block)
                    remaining -= len(block)
                if source.read(1) or h.hexdigest() != file_hash(staged):
                    raise PlanError("Render bytes changed during import; no input was published")
                check(os.fstat(source.fileno()), "during")
                check(path.lstat(), "during")
                if folder_guard is not None: folder_guard()
                cancelled()

            proof = {**(metadata or {}), "source": "watched_fl_export",
                     "source_file_unchanged": True, "render_triggered_by_app": False,
                     "causal_provenance_verified": False}
            return assets.import_stream(source, expected.size, path.name,
                                        validate=verify, stop=stop, metadata=proof)
    except OSError as exc:
        raise PlanError("Render cannot be read safely; no input was published") from exc
