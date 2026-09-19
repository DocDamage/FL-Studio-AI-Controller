# FL Studio AI Copilot v0.4.0 — build report

September 19, 2026. Cumulative source milestone: imported before/after audio review.

## Baseline and scope

Started from the supplied v0.3.0 source ZIP, whose reconstructed Git tree matched
remote main exactly: `b6d8a105c3cdcba4ca1a99ab66c1d67aa9d6260b`, commit
`d323ff0508eaa9a8f9d2a52dfd1bf5a5e3fb5084`. Re-ran 311 baseline tests successfully.
The prior Windows/Linux CI run was confirmed successful. Those are baseline checks,
not evidence that this new revision or a running FL instance was already tested.

New code adds strict review requests, conservative timing evidence, an actual
attenuation-only A/B renderer with reread measurements, persistent review/decision
storage, UI audition controls, HTTP routes and three MCP tools (17 total). Optional
verified-run associations deliberately do not claim export provenance or causation.
Existing control ownership, protection locks, bridge pins, master rendering and MIDI
workflows are preserved. No direct capture, render trigger or DAW mutation was added.

Also fixed numeric 1 satisfying a boolean confirmation and error-response sockets
left open by the HTTP test helper. Confirmation now requires actual boolean true.
Batch output registration changes the asset manifest only after the group validates.
Normal failed-publication cleanup removes only newly created review output records.

## Local checks actually executed

| Check | Result | Evidence boundary |
|---|---|---|
| Baseline tests | 311 passed | Existing source on Linux Python 3.13 |
| Full revised suite | **363 passed**, warnings treated as errors | 52 additional cases; synthetic audio, real HTTP, contract doubles |
| Existing browser regression | **35 checks**, no page errors | Direct-Service DOM harness, current app code |
| New review UI | **16 checks**, no page errors | Real service/render/storage; DOM transport fallback |
| Companion/MCP/audio process | Passed | Real separate simulator app, authenticated HTTP imports, actual WAV outputs, 17-tool stdio relay |
| JavaScript / Python syntax | Passed | Local syntax/compile checks |
| Native FL control/capture | Not run | No FL Studio instance or MIDI endpoint in this environment |

The full suite includes gain-only matching, shifted/uncertain/flat/antiphase content,
format mismatches, silence and silent windows, short-tail coverage, peak-constrained
attenuation, remeasured output rejection, source hashes and concurrent mutations,
cancellation, disk/publication failures, decision revisions and concurrent choices,
persistence across restart, untrusted paths and malformed confirmations, associated
run boundaries, authenticated routes and MCP forwarding. Audio review was tested
with every DAW adapter entry point replaced by a failure, establishing that the
review path does not need or call those adapter methods in that test.

The first stricter warnings-as-errors run exposed unclosed HTTP error responses in
the test helper. After closing those responses explicitly, all 363 tests passed under
that stricter run. No warnings were suppressed to obtain the result.

## Browser scope

Ordinary localhost navigation was attempted and rejected with
`ERR_BLOCKED_BY_ADMINISTRATOR`. No policy was modified. The new UI script permits
fallback only for that explicit environment condition. Static UI and real Service
calls then ran in a blank-page DOM harness; actual HTTP/authentication was checked
separately. UI playback tests verify browser media state and approximate switching,
not physical listening quality, Windows sound drivers or gapless playback.

Reviewed desktop and 390px screenshots. They show a synthetic before/after pair and
a simulator banner; no user audio, secrets, real project names or live FL evidence
is represented. Generated PNG files remain download artifacts, excluded from Git.

## Packaging and CI

Wheel build and isolated import checks, exact ZIP integrity/hash checks, and a
fresh-extraction test rerun are recorded in the separate package receipt produced
after this report. Source files are indexed by the regenerated `MANIFEST.sha256`.
GitHub CI runs the core suite and the enhanced real simulator-process checks on
Windows and Linux; inspect the actual published-commit run, not this document, for
its result. No new dependency or workflow permission was introduced.

Evidence: `evidence/pytest_v040.txt`, `evidence/runtime_process_v040.json`,
`evidence/browser_dom_report_v040.json`, `evidence/review_ui_v040.json`.
The old build report is retained under `docs/history/v0.3.0_BUILD_REPORT.md`.

## Remaining boundaries

The timing thresholds are heuristic and can refuse valid periodic/heavily processed
music. Readiness does not establish sample/phase alignment, content identity, origin,
causality or audible improvement. A review decision is a human annotation, not a DAW
operation. Hard crashes during the narrow filesystem/database publication interval
can leave orphan output records; they cannot trigger replay or automatic DAW writes.

Windows end-user setup, virtual MIDI, native effect menus, actual plugin behavior,
local models, GPU latency and physical monitoring remain unqualified. This is not a
signed EXE or VST3. Automatic Playlist editing, plugin removal/reordering, live capture,
automatic FL rendering, project autosave/rollback and adaptive AI mastering are not
implemented. See `docs/AUDIO_REVIEW.md` and `docs/UPGRADE_v0.4.0.md`.
