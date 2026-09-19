# FL Studio AI Copilot 0.2.0 — build and validation report

**Release:** cumulative Windows-first development source, September 17, 2026.  
**Status:** application code and local regression checks exercised; native Windows/FL qualification still pending.

## What changed in this increment

The delivered v0.1.0 archive was extracted and retained as the baseline. This is a
cumulative application, not a patch that requires merging the old ZIP. Existing
session controls, audio finishing/A-B exports, MIDI sketches, protection gates,
local planner support and experimental native plugin-menu adapter are retained.

- **Explicit mixer mute and stereo separation:** new typed operations, simulator
  state, source-reviewed PostFader writer bindings, prompts, UI previews and
  readback checks. Mute accepts only a true boolean; stereo uses FL's -1 to +1
  control range. Solo, arm, routing and effect bypass were not added.
- **Fourteen connection/readiness checks:** runtime, audio renderer, pinned
  dependency, FL data directory, bridge file, MIDI enumeration, exact matching
  input/output endpoint, process MIDI setting, compatible live handshake,
  running source provenance, project epoch, closed write gate, stop and journal.
  Environment checks and live observations stay separate. Simulator results can
  never qualify a host.
- **Privacy-filtered diagnostic export:** excludes local paths, device names,
  project content, raw errors, model addresses, tokens and bridge fingerprints.
  Local details remain available in the running app. The new Windows check
  launcher and CLI reuse that app rather than opening another MIDI controller.
- **Restore previews for verified controls:** build a separate, expiring,
  approval-required compensation plan for captured fader, pan, name, mute,
  stereo and effect-parameter values. The original final state must still match.
  Plugin insertion, uncertain runs and older insufficient snapshots are refused.
  This is not FL Undo, automatic rollback or restoration of a complete project.
- **A deliberate 1 dB non-master control test:** exact preview and approval for
  reduction, followed by a separately approved restore. Diagnostic evidence
  distinguishes preparation, verified reduction and an observed return. Only
  current-session live-adapter journal evidence qualifies; the last 50 plans
  are inspected. None was obtained from a real FL instance in this build.
- **Safety fixes:** a getter failure after a dispatched write now latches an
  unknown outcome instead of being mislabeled as a pre-dispatch block. Receipt
  session contradictions, non-finite control readbacks and captured collateral
  changes stop execution. Relative prompt plans are anchored to their observed
  session and controls, preventing stale model/command context from being adopted.
- **Twelve MCP tools:** diagnostics, restore preview and the 1 dB test join the
  existing nine. They share the same running executor and grant no approvals.

## What was actually executed

| Validation | Observed result |
|---|---|
| Baseline regression | Original 132 tests passed before the new work. |
| Final Python suite | **214 tests passed** in **21.22 seconds** on the final working source. This is 82 additional tests. |
| New safety/recovery cases | Strict booleans/ranges/locks; stale context/session/parameters; six-control compensation; old and partial receipt refusal; collateral changes; lost post-dispatch getter; contradictory receipts; NaN/inf/bool numeric readback; independently approved test/restore. |
| Connection diagnostics | Endpoint missing/ambiguous/matched fixtures, enumeration without opening ports, source/epoch/gate distinctions, simulator non-qualification, filtered exports, journal proof states and authenticated HTTP routes exercised. |
| Audio/MIDI regression | Real generated-fixture analysis, WAV rendering, original-file preservation, level-matched A/B export and MIDI-file tests still pass. This is not listening or artistic validation. |
| Browser DOM workflows | **23 checks passed**, zero page errors. Actual HTML/CSS/JS uses a direct real-Service test harness. Desktop 1512px and mobile 390px layouts exercised and screenshots inspected. |
| Browser transport limitation | Ordinary localhost navigation failed with **ERR_BLOCKED_BY_ADMINISTRATOR**. No policy was changed. This is not normal-browser end-to-end launch acceptance; HTTP routes/authentication were tested independently. |
| Application process | Actual simulator app subprocess, real HTTP status and diagnostic job requests passed. Diagnostics created no control plans and correctly exited 2 (not live-ready). |
| MCP stdio process | Actual relay subprocess initialization, tools list and status call passed; **12 tools**; JSON-RPC-only stdout. Simulator backend only. |
| Wheel | Built a **79,364-byte** Python wheel; extracted outside the source and imported successfully. Version/metadata, new modules and all three HTML/JS/CSS resources verified. Not a Windows EXE. |
| Syntax | Python compileall and JavaScript node --check passed. |

A wheel attempt was interrupted by the combined command timeout. Its generated
build directory was removed, then a clean wheel build and extracted-wheel checks
passed. No generated build directory or environment is shipped as source.

The final ZIP's CRC, file hashes and fresh-extraction test results are recorded
in the **adjacent external package receipt**. That fresh extraction reuses the
existing Linux dependency environment; it is not a new Windows dependency install.

## What remains unverified

No Windows installation or PowerShell execution, actual FL handshake, real MIDI
SysEx exchange, native menu dispatch, live plugin insertion or parameter edit,
hotkey registration, audio-interface latency test, local-model inference, RTX 3060
benchmark or full upstream PostFader suite was executed. The pinned PostFader
runtime was not installed here. Its mute/stereo API signatures were read from the
pinned source and exercised through contract doubles, not the actual distribution.

The new readiness UI and qualification workflow make host testing observable;
they do not substitute for it. All native-host acceptance fields in
`evidence/WINDOWS_ACCEPTANCE_TEMPLATE.json` remain **not_run**.

Screenshots show a **simulated DAW**, not an FL Studio session. Audio screenshots
use generated sine mixtures, not user beats. No musical-quality result is inferred.
No signed EXE, VST3, model weights, virtual MIDI driver, FL license or paid plugin
is included. No GitHub repository was created, changed or pushed for this increment.

## Remaining functional boundaries

This is not yet a complete autonomous mix engineer or adaptive AI masterer.
Continuous live listening/capture, automatic FL rendering, stem separation,
sample-chop arrangement, Playlist/note editing, automatic tonal EQ/compression,
plugin removal/reorder, autosave and full project rollback are not implemented.
The Windows plugin loader remains experimental and may report unsupported menus.
The source does not establish that every PostFader Windows limitation is fixed.

Preserve-dynamics finishing remains peak-constrained gain. The other finishing
mode is two-pass loudness normalization with possible dynamic limiting. Existing
imported-audio operations produce real WAV and A/B files but do not change FL's
master chain automatically.

Restore protects and reinstates only captured controls, not hidden plugin state,
audio, routing, automation or unrelated actions. It refuses runs whose final
captured state or current session changed. New approval is mandatory; previous
approval is not reused. Old v0.1 records remain readable but cannot gain missing
recovery snapshots retrospectively.

## Setup and upgrade

See `START_HERE.txt` and `docs/UPGRADE_v0.2.0.md`. Use a separate new source folder
and fresh `.venv`; copy only the existing local-settings.json as applicable.
The default workspace remains unchanged, preserving existing imported audio,
exports and journal history. Old unused previews expire; uncertain writes remain
blocked. Keep the old source and save a new FL project copy before first live use.

Run `CHECK_CONNECTION.cmd` or `scripts/doctor.py` **only while the companion is
running**. This intentionally replaces the earlier standalone-doctor workflow.
The pinned PostFader revision is unchanged; redeploy/reload the bridge only when
setup or current diagnostics require it. Never run competing app/MCP controllers.

## Provenance and reproducibility

Application source is MIT; external dependencies retain their own licenses.
PostFader remains a separate pinned dependency: distribution **10.0.0**, revision
`480bedd1cde98fe272c5e02f66efd7aa83315d0b`. Its source-reviewed compatibility gate
requires FL Studio 2026 **26.1.3.5336+**, MIDI API **44+**. The two other discussed
repositories remain conceptual references; their controller/audio code was not
silently copied into this increment. See `THIRD_PARTY_NOTICES.md`.

Source references for the new bindings and diagnostics:

- https://github.com/synopsys0/postfader-fl-studio-mcp/blob/480bedd1cde98fe272c5e02f66efd7aa83315d0b/fl_studio_mcp/verified_writer.py
- https://github.com/synopsys0/postfader-fl-studio-mcp/blob/480bedd1cde98fe272c5e02f66efd7aa83315d0b/fl_studio_mcp/readonly_inspector.py
- https://github.com/synopsys0/postfader-fl-studio-mcp/blob/480bedd1cde98fe272c5e02f66efd7aa83315d0b/fl_studio_mcp/host_config.py
- https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm
- https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/mixer.htm

Environment: Linux. Runtime/package versions observed for this build:

```json
{
  "python": "3.13.5",
  "numpy": "2.3.5",
  "scipy": "1.17.0",
  "soundfile": "0.13.1",
  "pydantic": "2.13.4",
  "pyloudnorm": "0.2.0",
  "imageio-ffmpeg": "0.6.0",
  "pytest": "9.0.2",
  "playwright": "1.57.0"
}
```

Core direct dependencies are pinned, not their entire transitive closure. The
existing local Chromium installation was used for the DOM checks and system
FFmpeg for the audio tests. Windows dependency resolution remains unverified.

Run `python -m pytest -q tests` to reproduce the core suite;
`scripts/verify_runtime.py` exercises actual simulator app/doctor/MCP processes.
`scripts/browser_dom_smoke.py` needs Playwright and local Chromium, optionally
selected using FLCOPILOT_BROWSER. It intentionally reports its transport limitation.

The baseline archive SHA-256 is `4506d4a568a2070ff7090b2b0dab0caf9432a89157da6d2ed2908a6dc0588c09`.
The independently built v0.2.0 wheel SHA-256 is `d3b3b0a6b1248ad3b2cc14ce981da27f225b9b8d8c3be6ec866bba042866d245`.
`MANIFEST.sha256` covers every shipped payload file except itself. The ZIP sidecar
and external receipt cover the archive; private workspaces, caches, environments,
build intermediates and project/audio files are excluded.
