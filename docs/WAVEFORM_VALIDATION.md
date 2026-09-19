# Waveform review validation — September 19, 2026

Base: merged main `80d9d9934f3d24091710dae8ff06b9d40c630fef`, tree
`bc41bf0d7293529684ff5c54162400a659ce7aaf`. The downloaded GitHub source artifact
matched this tree before editing. Package version remains 0.4.0; these are
unreleased v0.5 development changes.

## Executed locally

Linux / Python 3.13.5. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -W error -m pytest -q tests`
passed **621 tests in 45.71 seconds**. Baseline was 566; 55 new tests exercise exact
per-bin min/max/RMS against real decoded WAVs, full frame coverage, independent
stereo/antiphase channels, strict request bounds, bounded reads/hashes, Stop,
identity/report checks, missing/changed files, privacy, read-only behavior, and
real HTTP authentication/origin/job/static-file routes. Unrelated environment
pytest plugins were disabled; warnings were errors.

`python scripts/verify_waveform_ui.py` passed **16 browser checks**, with zero page
errors. Includes actual synthetic WAV playback/seeking, A/B range switching, full-file
end looping, Stop, pause-during-load, latest-seek behavior, stale response rejection,
failed reverification, blocked reviews, and a 390px layout. Desktop/mobile captures
were visually inspected. They are synthetic examples, not user project screenshots.

The existing Audio review harness passed **16 checks**, and the acceptance checklist
harness passed **9 checks**. The review harness now discovers all current scripts and
styles instead of silently omitting later modules. All 41 checks reported the direct-
Service DOM fallback because ordinary localhost navigation was administrator-blocked.
No browser policy was changed. Real authenticated HTTP was tested separately by pytest.

`python scripts/verify_runtime.py` passed the actual companion/diagnostics/MCP
subprocess smoke with 20 MCP tools, synthetic WAV imports/review, watched-file
intake, and persistent bounce metadata. It correctly leaves the simulator unqualified.

`python -m pip wheel --no-deps --no-build-isolation -w /mnt/data/fl-wheels .` built the
wheel; all **52 packaged source/static files** matched the working bytes. New
Python/JavaScript syntax checks and git whitespace checks passed.

Receipts: `evidence/waveform_tests.txt`, `waveform_ui.json`,
`waveform_regressions.json`, `waveform_runtime.json`, and `waveform_package.json`.
The build location above is a development-environment path, not a Windows install path.
Historical release manifests/build reports are not validation of these new files.

## Not established

No actual FL Studio session, physical audio audition, native MIDI loopback, driver
latency, plugin insertion, or local-model benchmark was performed. Browser looping
is approximate and may be delayed by scheduling/background throttling. Point-in-time
hash checks do not establish causal FL provenance or freeze the filesystem. GitHub
CI is separate: consult the run for the published commit, not this local report.
