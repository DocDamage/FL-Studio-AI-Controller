# FL Studio AI Copilot v0.3.0 — build and validation report

Date: September 19, 2026. Cumulative development source release.

## Delivered milestone

Plugin Workbench adds bounded, read-only exploration of effects that are already
loaded in mixer slots, followed by separately approved normalized or engineering-unit
parameter adjustments. It does not load an instrument, create a Playlist clip, listen
to FL output, save the project, or supply an adaptive mastering model.

The initial local source was reconstructed from the v0.2.0 archive and the repository
import additions. Its Git tree matched remote `main` exactly:
`bcf0f713d9aeaeba7da99b747e5c88d779f999c2`, at commit
`c9c1c982845641463491bf2aac05942e7561c953`. The baseline suite was independently
rerun: 214 passed. This release builds on that verified baseline, not a replacement
scaffold. The v0.2.0 build report is preserved under `docs/history/`.

## Added functionality

- Parameter discovery reads pages of at most 128 raw indices, within an explicit
  window of at most 2,048 indices. The address ceiling is 65,536. Counts, coverage,
  excluded padding, search scope, and the next window are reported separately.
  An empty search result never establishes that the whole plugin was searched.
- Search matches observed names and displayed text. Preview selection is bound to
  an in-memory observation token, the session, captured mixer state, plugin name,
  raw parameter index, and its prior readback. Tokens expire after five minutes;
  only the latest 16 scans are retained. A token is not approval.
- Targets support normalized values or explicit dB, Hz, ms, and percent. Observed
  kHz and seconds are converted to base units. Ambiguous/unitless displays, ratios,
  labels, unsupported locales, and non-finite values are rejected rather than guessed.
- Engineering-unit search uses the pinned PostFader display setter and its live
  display-unit capability. It requires playback and recording to be explicitly
  stopped and is isolated to one operation per approved plan. The solver can move
  through intermediate settings. The emergency stop cannot interrupt a native call
  already in progress.
- Verification independently rereads the displayed result and compares it with
  the approved target and tolerance. A contradictory or missing result after dispatch
  is an unknown outcome, not a safe retry or a claim that nothing happened.
- Restore prepares a new, separately approved display-unit operation from the
  captured value. It is not automatic rollback or a guarantee of FL Undo.
- Existing parameter, track, and master locks still apply. Discovery creates no
  control plan. Two typed MCP tools use the existing authenticated companion and
  serialized executor, bringing the exposed relay to 14 tools.
- The simulator includes one clearly fictional high-index test effect. No stock
  plugin mapping, real plugin behavior, or live-host success is implied.

## Evidence from this build

| Check | Observed result | Boundary |
| --- | --- | --- |
| Baseline source identity | Exact match with remote v0.2.0 Git tree | Source identity, not host execution |
| Baseline core suite | 214 passed on Linux Python 3.13 | Simulator, contract, HTTP and audio tests |
| Expanded core suite | **311 passed in 17.38 seconds** | 97 additional tests; no running FL Studio |
| Real companion subprocess | Passed in simulator mode | Authenticated localhost HTTP, not MIDI |
| Diagnostic subprocess | Passed; simulator correctly returns not-ready exit 2 | No live-readiness claim |
| MCP stdio subprocess | Passed, 14 tools; high index 2049 scanned without creating plans | Relay-to-companion integration in simulation |
| Browser DOM workflows | **35 checks, no page errors** | In-memory harness with real Service methods |
| Wheel | Built; isolated import and new static/package members verified | Linux, dependencies already installed |
| Prior GitHub CI | v0.2.0 core tests passed on Ubuntu and Windows | Does not qualify native FL or this revision |
| New GitHub CI | Workflow includes both OS core suites and simulator-process checks | Consult the actual run for the published commit |

The 311-test suite includes parameter-page bounds, high indices, duplicate/missing
rows, stale sessions and observations, unit conversion, type/range validation,
transport and capability checks, locks, exact target identity, contradictory receipts,
independent display verification, failed-readback quarantine, display restores,
HTTP authentication and endpoints, MCP schemas and forwarding, and the existing
real offline audio and MIDI tests. No audio processing algorithm or dependency pin
was changed for this milestone.

### Browser evidence limitation

Ordinary localhost navigation in the supplied browser was blocked by the environment
with `ERR_BLOCKED_BY_ADMINISTRATOR`. No browser policy was changed. The existing
in-memory DOM harness served static assets in memory and forwarded its fetch calls
to real Service methods. HTTP authentication, routing, and process integration were
checked separately. This is not a successful ordinary browser-launch or Windows
installation test.

The DOM run exercises the existing workflow plus partial scans, high-index windows,
end-of-range navigation, numeric display conversion, display preview/approval/restore,
a normalized alternate preview, escaped plugin text, and 390-pixel layout. The
screenshot `Plugin_Workbench_v030.png` depicts the simulator only and is distributed
separately from Git source.

## Evidence files

- `evidence/pytest_v030.txt`
- `evidence/browser_dom_report_v030.json`
- `evidence/browser_navigation_v030.json`
- `evidence/runtime_process_v030.json`
- `evidence/wheel_validation_v030.json`

The source `MANIFEST.sha256` covers tracked payload files except itself. Downloadable
package integrity and a fresh-extraction rerun are recorded in the separate package
receipt. Generated screenshots, local settings, authorization tokens, workspaces,
private logs, audio, databases, virtual environments, model weights, and FL projects
are not staged for GitHub.

## Still unqualified or not implemented

Actual FL Studio operation, Windows setup on a user's machine, MIDI exchange,
native plugin-menu automation, real plugin search curves, emergency hotkey behavior,
and local-model/GPU performance remain unqualified. Slot/name checks cannot establish
persistent plugin instance identity or detect all hidden state changes. A failed
native display search can leave an intermediate setting; do not retry it automatically.

This is a companion development source release, not an EXE installer, a VST3, a
replacement DAW, or a finished Ozone alternative. Automatic Playlist editing, plugin
removal/reordering, live audio capture, and full adaptive AI mastering remain outside
this milestone. The existing normalized parameter compatibility and v0.2.0 journal
shape are retained. No project is saved automatically.

Use a saved project copy for live qualification. Stop playback and recording before
testing one small display-unit change, check the actual control manually, then
approve any restore separately. See `docs/PLUGIN_WORKBENCH.md`,
`docs/UPGRADE_v0.3.0.md`, and `docs/WINDOWS_ACCEPTANCE.md`.
