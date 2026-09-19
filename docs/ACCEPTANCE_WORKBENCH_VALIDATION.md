# Acceptance workbench development evidence — September 19, 2026

Base: merged `main` commit `93b4648bb17497b3b54a2a20102990fb3bea0323`.
The source artifact matched Git tree `6889b82e9aa276bdcd71c750b9a5cc4509a65890`.
This is an unreleased v0.5 development increment; package metadata remains 0.4.0.

## Actually run locally

Environment: Linux, Python 3.13.5. Baseline: 495 tests passed. Final suite: **566
passed in 42.25 seconds**, exit 0, using warnings as errors and disabling unrelated
preinstalled third-party pytest plugins. See
[`acceptance_workbench_tests.txt`](../evidence/acceptance_workbench_tests.txt).

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -W error -m pytest -q tests
python scripts/verify_runtime.py
python scripts/verify_acceptance_ui.py
python -m pip wheel --no-deps --no-build-isolation -w /tmp/fl-wheels .
```

The added 71 cases cover persistent drafts, stale revisions, schema/privacy
boundaries, explicit confirmation, Stop, malformed/corrupt storage, failed writes,
real HTTP auth/save/export, real synthetic A/B report/output hashes, source/report
mutation, removed outputs, mismatched reviews, disconnection/session changes, and
unchanged DAW/MCP authority. Native Windows and bridge eligibility in these tests
are explicit contract doubles, never evidence of a real FL session.

The independent companion/doctor/MCP process smoke passed. It exercised the 20-tool
stdio relay, high-index plugin inspection, actual synthetic WAV import/review,
manually created folder export intake, and persistent bounce metadata. Its simulator
correctly reported not-ready rather than qualifying a host. See
[`acceptance_workbench_runtime.json`](../evidence/acceptance_workbench_runtime.json).

Nine browser checks passed, with no JavaScript page errors. Chromium's ordinary
localhost navigation was blocked by the execution environment, so these checks
used the explicitly reported direct-Service DOM fallback. Separate Python HTTP
tests exercised the actual authenticated routes. Desktop and 390px layouts were
captured; the mobile layout has no horizontal overflow. See
[`acceptance_workbench_ui.json`](../evidence/acceptance_workbench_ui.json).

The wheel built successfully, and all 49 packaged `flcopilot` source/static files
matched the working source bytes, including acceptance Python, CSS and JavaScript.
Python compilation and JavaScript syntax checks also passed. The wheel is not a
signed Windows installer or VST3.

## Not established by this pass

No actual Windows/FL Studio export session, virtual MIDI loopback, native plugin
insertion, audio-driver latency, or local-model performance was tested here. A
completed desktop record still requires the user's native observations and the
runtime evidence checks. This pass adds no automatic FL render mechanism.

Repository CI is a separate run after publication. Do not infer its outcome from
this local report; inspect the Actions run for the actual commit. Historical
release manifests and previous build reports are not claims about this increment.
