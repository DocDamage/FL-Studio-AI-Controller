"""Capture actual codec-written files, not only Python-written byte fixtures."""
from dataclasses import asdict
import os
from pathlib import Path
import tempfile
import threading

import numpy as np
import pytest
import soundfile as sf
from flcopilot.assets import AssetStore
from flcopilot.render_intake import FileStamp, snapshot_folder, wait_for_render, import_render


@pytest.mark.parametrize('subtype', ['FLOAT', 'PCM_24'])
def test_native_codec_export_preserves_intake_identity(subtype):
    with tempfile.TemporaryDirectory(prefix='flcopilot-codec-roundtrip-') as tmp:
        workspace = Path(tmp)
        folder = workspace / 'manual-exports'; folder.mkdir()
        baseline = snapshot_folder(folder)
        path = folder / 'new-export.wav'
        samples = np.random.default_rng(91).normal(size=(24000, 2)) * .02
        sf.write(path, samples, 8000, subtype=subtype)
        selected, expected = wait_for_render(folder, baseline, threading.Event(), timeout=5)
        path_stat = selected.lstat()
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0)
        with os.fdopen(os.open(selected, flags), 'rb') as stream:
            descriptor_stat = os.fstat(stream.fileno())
            evidence = dict(expected=asdict(expected), path=asdict(FileStamp.read(path_stat)),
                            descriptor=asdict(FileStamp.read(descriptor_stat)),
                            path_links=path_stat.st_nlink, descriptor_links=descriptor_stat.st_nlink)
            assert expected.matches(path_stat), evidence
            assert expected.matches(descriptor_stat), evidence
        assets = AssetStore(workspace / 'workspace')
        record = import_render(assets, selected, expected)
        copied = assets.resolve(record['id'])
        assert copied.read_bytes() == path.read_bytes()
        assert sf.info(copied).subtype == subtype
