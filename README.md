# FL Studio AI Copilot — v0.4.0

**Windows-first local companion, development source release.** The code runs a local
browser interface, a single guarded executor, an audio-finishing workspace, and an
optional MCP relay. It is not a compiled VST3, not a signed Windows application,
and not a claim of better artistic mastering than Ozone.

**Read the evidence boundary:** this development pass ran the core, HTTP, audio,
contract-double and real simulator-process checks on Linux. The previous repository
CI passed its core suite on Windows and Linux; the updated workflow also runs
simulator process checks. Neither is live FL Studio, virtual MIDI, native plugin-menu
or local-model qualification. The record is in [BUILD_REPORT.md](BUILD_REPORT.md).
Screenshots are explicitly simulated; audio fixtures are synthetic.

**New in v0.4:** [Before/after audio review](docs/AUDIO_REVIEW.md). Pair two imported
exports, check matching format and timing evidence, render measured level-matched
A/B WAVs, inspect same-position measurement windows, and save your own listening
preference. No automatic FL render, recording, correction, or artistic winner is
claimed. See [upgrade instructions](docs/UPGRADE_v0.4.0.md).

**Added in v0.3:** a [Plugin workbench](docs/PLUGIN_WORKBENCH.md) for bounded,
read-only parameter discovery and observation-bound changes in displayed units.
The [v0.3 upgrade notes](docs/UPGRADE_v0.3.0.md) remain available for historical context.

## Current unreleased v0.5 additions

**Audio review now has [waveform navigation and section looping](docs/WAVEFORM_REVIEW.md).**
Open a ready review and load verified waveforms, seek the same passage on either
side, or repeat a numeric range or measured time window. A/B uses the original
level-matched files with separate stereo lanes and a shared scale. Loops are
approximate browser playback, not edits to your audio or FL project.

**Ready reviews also have a [server-randomized blind A/B/X check](docs/BLIND_ABX_REVIEW.md).**
The browser sees only blinded Reference A/B/X audio until you submit which reference
X matches (or choose unsure). The reveal is stored as a separate human
discrimination attempt; it does not change your saved preference, score quality, or
authorize a DAW action.

The merged [manual export intake](docs/FL_RENDER_INTAKE.md),
[persistent bounce library](docs/BOUNCE_LIBRARY.md), and
[native export test checklist](docs/ACCEPTANCE_WORKBENCH.md) remain available.
Package metadata is still 0.4.0; this is development source, not a qualified v0.5
Windows release. See [waveform validation](docs/WAVEFORM_VALIDATION.md).

## Start on Windows

Extract the whole ZIP. Install **64-bit Python 3.13**, including the `py` launcher.
Run `SETUP_WINDOWS.cmd`; select the live adapter when asked, or use core-only mode
with `powershell -NoProfile -File scripts/Setup-Windows.ps1 -CoreOnly`.
The first installation needs internet access. Once installed, demo, direct controls,
MIDI generation, and audio processing do not need a cloud account.

Run **`START_DEMO.cmd`** first. No connection to FL is attempted. Demo has a separate
workspace from live mode, so its action journal is not mixed with real sessions.

For FL: configure a trusted bidirectional virtual MIDI endpoint, close FL and other
PostFader clients, then run **`CONNECT_FL.cmd`**. It invokes upstream's guided setup
and stores only the exact endpoint name in `local-settings.json`. FL's input and
matching output need the same MIDI port number, the input must use **Universal
Bridge**, and the script must be reloaded. Upstream does not install a MIDI driver.
Use **`START_LIVE.cmd`**, open a disposable FL project, and inspect before changing
anything. See [Windows acceptance](docs/WINDOWS_ACCEPTANCE.md).

The pinned upstream compatibility gate requires **FL Studio 2026, build
26.1.3.5336 or newer, MIDI scripting API 44 or newer**. This is an upstream
requirement observed in its source, not an assumption about your installation.
Older versions fail the live compatibility gate; the audio workspace still works.

## What is implemented

### Session controls

Inspection reports project/mixer data through PostFader V10. The implemented live
adapter exposes scoped fader-dB changes, pan, renaming, explicit mute/unmute,
stereo separation, normalized parameter changes, and guarded displayed-unit
changes for already loaded effect slots. Every approved plan binds a session,
exact before-state, target/control, current protection locks, five-minute expiry,
and SHA-256 digest. Master is locked by default; tempo, notes, and arrangement
cannot be unlocked in this release. The maximum individual fader movement is 12 dB.

**Inspect** blocks project writes. **Assist** executes an explicitly approved plan.
**Finish** also authorizes only the displayed pass: it is not an unlimited autonomous
loop. The conservative gain-staging workflow observes user-selected non-master
tracks and proposes attenuation only. It neither listens to FL's audio nor performs
EQ, masking correction, compression, routing, or a complete artistic mix.

Receipts are committed to SQLite. If a reply is lost after dispatch, no automatic
retry occurs; subsequent writes remain blocked until a fresh inspection and explicit
acknowledgment. Acknowledgment is not rollback. No project is automatically saved.

### New in v0.4: before / after audio review

Use **Audio lab** to import matching before/after exports, then open **Audio review**.
Confirm that the song range and export settings match. The companion checks sample
rate, channels, exact frame count, finite loudness, and conservative timing evidence.
It does not shift, trim or resample mismatches. Ambiguous or offset pairs receive a
report with blockers, not audition files or a fabricated alignment guarantee.

For a ready pair, it creates `A_Baseline_Matched.wav`, `B_Candidate_Matched.wav`, and
`Review_Report.json`. Both float WAVs are attenuation-only, reread after writing,
and checked within **0.1 LU** of their common measured loudness and under a -1 dB
oversampled-peak estimate. No EQ or limiter is inserted. The standard player switches A/B at approximately the same position and is not
gapless or sample-synchronous. The separate blind A/B/X check hides the baseline /
candidate mapping until the human answers; one trial is a discrimination attempt,
not statistical proof, a preference, or a quality score. Global and 10–60 second
window deltas are measurements, not improvements or scores.

Reviews persist in a separate local SQLite store. Your preference and notes are
revision-checked human decisions; neither they nor the optional association with a
verified journal run authorize DAW changes. The immutable exported report excludes
local paths, source filenames, raw session tokens and private plan contents, but
contains your supplied review title and audio hashes. Decisions are kept separately
in local history; the original report file is not silently rewritten.

Three additional MCP tools (`copilot_review_audio`, `copilot_reviews`, and
`copilot_review_get`) use the same running app, bringing the relay to **17 tools**.
No MCP tool chooses a listening preference for you. Numeric `1` is now refused as
approval or export-range confirmation; only explicit boolean `true` is accepted.
The complete [review guide](docs/AUDIO_REVIEW.md) describes timing heuristics,
uncertainty, publication/crash boundaries, and the pending live-render workflow.

### Added in v0.3: plugin workbench

Select an actually loaded mixer effect, search its observed parameter names and
displays, and continue through bounded raw-index windows instead of stopping at
128 parameters. Padding and unnamed controls are excluded. Every result states
its coverage, next index, and whether more of the map remains unread.

Select a returned control and prepare an exact normalized value or an explicit
`dB`, `Hz`, `ms`, or `percent` target with tolerance. Observed kHz and seconds are
converted into Hz and ms; labels and ambiguous units are not guessed. Previews
bind the scan's session, track/plugin state and parameter values, expire after
five minutes, and still require separate Session approval.

**Displayed-unit searches require stopped playback and recording** because they
move intermediate settings. They run one at a time through the existing executor,
then receive independent displayed-value verification. A fully verified change can
receive a new, separately approved display-value restore. This does not restore
hidden plugin state or promise artistic improvement.

Demo insert 6 contains a deliberately fictional test effect with controls at indices
129, 2,049 and 4,097. These are not stock-plugin mappings. The two new MCP tools,
`copilot_plugin_scan` and `copilot_plugin_preview`, bring the relay to 14 tools.
No dependency, MIDI client, automatic model download or new execution authority
was added. See [Plugin workbench](docs/PLUGIN_WORKBENCH.md).

### New in v0.2: readiness and verified-control recovery

In **Connection & setup**, run **Check connection**. Fourteen checks separate Python,
audio dependencies, the installed bridge, exact MIDI endpoint matching, live FL
compatibility, source provenance, session protection, write-mode ownership, Stop,
and unresolved outcomes. Diagnostics use the existing app-owned bridge, never a
second independent controller. **Export privacy-filtered report** creates a JSON
file without local paths, MIDI device names, project contents, or session identifiers.
A simulator always remains unqualified, even when its control tests pass.

For a first live test on a saved project copy, select a non-master insert and click
**Preview 1 dB test**. Approve that exact reduction in Assist, check FL, then open
**Run journal → Preview restore** and approve the return separately. Diagnostics
can report an observed control round trip from application receipts. This is not
plugin-loading, sound-quality, audio-latency, or full Windows acceptance evidence.

**Preview restore** also works for ordinary fully verified control runs. It prepares
new inverse operations for captured fader, pan, name, mute, stereo, and parameter
values. The captured final state and session must still match. A changed target,
locked control, lost reply, incomplete run, or plugin insertion blocks recovery.
It never blindly resends the old operation, presses Ctrl+Z, reloads a project, or
removes a plugin. Older v0.1 receipts lacking v0.2 snapshots remain viewable but
are not eligible for the new restoration path.

A safety fix also ensures that a failed getter **after** dispatch means
`unknown_outcome`, not a safe-to-retry pre-dispatch refusal. Non-finite readbacks,
wrong-session receipts and unrelated changes to captured target controls now
block the next operation. Relative commands are rejected when their observed
session changes while the command is being interpreted.

See [Upgrade](docs/UPGRADE_v0.2.0.md), [Recovery](docs/RECOVERY.md), and
[Diagnostics](docs/DIAGNOSTICS.md).

### Audio lab

Import WAV, FLAC, AIFF, OGG, MP3, M4A, or AAC files. Decoder support depends on the
installed libsndfile/FFmpeg build; malformed or unsupported audio is rejected.
The source is copied into the app workspace; its original path is not exposed as an
arbitrary API read. Uploads are limited to 300 MiB; analysis accepts mono/stereo,
8–192 kHz, at least one second, at most ten minutes, and at most 24 million channel
samples. The sample-count bound may be reached before ten minutes at higher rates.

Measurements include gated integrated LUFS, sample peak, a **4× oversampled peak
estimate** (not a certified true-peak meter), RMS, crest factor, DC offset, stereo
correlation, clipping indicators, and broad-band energy fractions.

The finishing command creates four actual files:

- `Master.wav`: 24-bit output with measured readback and preserved sample rate,
  frame count, and channel count.
- `A_Original_Level_Matched.wav` and `B_Master_Level_Matched.wav`: float WAV files
  adjusted to a common measured loudness for auditioning.
- `Master_Report.json`: requested/achieved values, source/output hashes and warnings.

With **Preserve dynamics** on, the operation is peak-constrained gain only. It will
leave a loudness target unmet rather than crush peaks to reach it. With the switch
off, FFmpeg two-pass `loudnorm` may use dynamic limiting. Neither path adds automatic
tonal EQ or evaluates artistic quality. A clipped source cannot be repaired by
normalization. Reference comparison is a global measurement comparison, not proof
that the songs align or that one sounds better.

### MIDI sketch

Create a deterministic Type-1 MIDI file with a tempo track, GM-channel drum notes,
and a minor-key bass sketch. Defaults: 88 BPM, eight bars, E minor, seed 17, moderate
swing. Choose your own samples/instruments in FL. This is file generation, not
automatic Playlist placement, sample chopping, or audio-stem production.

### AI options

Supported offline forms include `Lower Drums by 2 dB`, `Set track 2 to -8 dB`,
`Rename track 3 to Bass`, `Mute Drums`, `Unmute track 1`, and
`Set track 3 stereo separation to 0.5`. Targets must be exact; no fuzzy guessing.
The optional model's own allowlist remains narrower: volume, pan and renaming only.
Use explicit commands or the direct controls for mute and stereo separation.

For broader instructions, use a local llama.cpp-compatible endpoint with alias
`local`. Add `"local_endpoint": "http://127.0.0.1:8081/v1"` to your local settings.
Alternatively, add `llama_exe`, `model` (a licensed compatible GGUF path), and
`gpu_layers` to let the app own and close a llama-server process. Example:

```json
{
  "midi_port": "Your exact endpoint",
  "llama_exe": "D:\\LocalAI\\llama-server.exe",
  "model": "D:\\LocalAI\\your-model.gguf",
  "gpu_layers": 0
}
```

Use normal JSON escaping: each Windows path separator is `\\` in JSON. Start with
CPU inference or conservatively assigned GPU layers. No particular model fit,
latency, VRAM headroom, or FL underrun performance was benchmarked on the RTX 3060.
Weights and a llama.cpp executable are not bundled or downloaded automatically.
The managed option avoids a separately maintained Ollama service, but is not a
self-contained preinstalled ML distribution.

An existing MCP-capable coding/assistant client can use the twenty-tool stdio relay:

```powershell
.\.venv\Scripts\python.exe scripts\write_mcp_config.py
```

This prints, rather than edits, a client configuration. Start the live app first.
The relay talks to that same executor, not another competing PostFader server.
It cannot change modes or unlock protected targets. Model output is a suggestion,
never Python, PowerShell, an executable script, or a raw bridge command.

## Experimental Windows plugin insertion

`windows_menu.py` implements a PostFader-compatible backend for **named native Win32
Add-menu entries**. It checks the FL process, foreground window, geometry, popup
state, user input timestamp, fresh menu path, and an empty selected destination.
It never falls back to screen coordinates, blind keystrokes, or plugin-manager scans.

The UI provides a five-second focus handoff. Bring FL's main window forward yourself,
then leave input alone during the operation. Custom-drawn or localized menus which
are not exposed in the expected native structure produce a manual handoff.

This is **not proof that PostFader's Windows limitations are solved**. Live testing
may show the native menu adapter is unavailable on your FL build. Loading effects
manually and then controlling exposed parameters remains the intended fallback.
Plugin removal/reordering, generator loading, and instrument note editing are not
added by this release. Upstream's own capability scope is broader than the subset
intentionally exposed by this app.

## Safety, workspaces, and recovery

Live data defaults to `%LOCALAPPDATA%\FLStudioAICopilot`; demo uses its `demo`
subdirectory. Inputs and exports are local and persist after closing the app. No
telemetry is included. Local account owners/admins can access their own workspace;
the token file is not a defense against malicious software running as that user.
Keep the private launcher URL, `server.json`, logs and project files out of Git.

Use the red **Stop** button. On Windows, the app attempts to register
**Ctrl+Alt+Shift+F12**; Setup reports whether registration succeeded. An in-flight
command may still complete, and Stop does not undo it. Wait for jobs to settle,
inspect FL, and reset Stop in Setup. Reconcile unknown outcomes only after checking
the project yourself.

Save a new FL project version manually before live use. The optional CLI checkpoint
copies only an already-saved FLP file; it cannot capture unsaved edits or bundle
external samples:

```powershell
.\.venv\Scripts\python.exe -m flcopilot --checkpoint "D:\Beats\Saved_Copy.flp"
```

See [security](docs/SECURITY.md), [architecture](docs/ARCHITECTURE.md), and
[known limitations](docs/KNOWN_LIMITATIONS.md).

## Developer validation

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q tests
.\.venv\Scripts\python.exe scripts\doctor.py
```

Keep the app **running** before invoking `doctor.py` or `CHECK_CONNECTION.cmd`.
The doctor relays to that app rather than opening its own MIDI connection.
Exit 0 means live bridge write preconditions are ready, not that authorization was
granted. Exit 2 means not ready, simulator, or no running app. `--demo --diagnose`
targets the demo workspace; an explicit `--workspace` also works.

Run `python scripts/verify_runtime.py` for a temporary simulator-process/doctor/MCP
smoke test. `python scripts/browser_dom_smoke.py` additionally needs Playwright and
Chromium; its transport is a direct-Service harness, not ordinary browser launch
acceptance. Both scripts are optional developer checks. The included
GitHub Actions workflow runs core and simulator-process checks on Windows and
Linux. Consult the actual run for this commit; CI success does not establish live
FL Studio acceptance. Direct versions are recorded, but all transitive
packages are not hash-locked. Review installation output and run `pip check`.

## Foundations and attribution

PostFader is an external **Apache-2.0** dependency pinned to revision
`480bedd1cde98fe272c5e02f66efd7aa83315d0b` (version 10.0.0). Its source, bridge and
licenses are installed by pip; they are not copied into this source tree. The other
two discussed repositories are design references, not blindly merged code. The
application-specific code is MIT licensed. No third-party model, plugin, sample,
font, proprietary Image-Line asset, or MIDI driver is redistributed.

Source references: [PostFader](https://github.com/synopsys0/postfader-fl-studio-mcp),
[Bees-D](https://github.com/Bees-D/Fl-Studio-Ai-Producer),
[IzzoSol](https://github.com/IzzoSol/FL-STUDIO-AI).

This project is unofficial and is not affiliated with Image-Line.
