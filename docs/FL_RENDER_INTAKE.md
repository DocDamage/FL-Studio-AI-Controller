# Manual FL export intake — connected workflow

This development increment connects the guarded intake core to the shared Service,
authenticated loopback HTTP API, Audio lab, and the MCP relay. It does **not** make
FL render automatically. Application/package version remains 0.4.0 until the next
release is qualified; this is the v0.5 development workflow, not a release build.

## Use it

Open **Audio lab → Catch your next FL export**. Enter an existing absolute local
folder path, choose a wait limit of 5–600 seconds, check the one-file consent, and
click **Arm export watch**. Wait for the armed state, then export manually from FL
with a **new filename**. Use one mix bounce, not split mixer-track stems.

The app snapshots the directory before the arm request returns. A queued worker
therefore does not accidentally treat your new export as a pre-existing file.
Only one watch can be active. The wait budget starts when the watch is armed;
copying and verification may take additional time. No folder is remembered as a
standing authorization; each new watch requires another checkbox confirmation.

When capture completes, the WAV/other supported audio appears in the existing
asset selectors. **Analyze captured bounce** runs the existing audio analyzer.
**Use as before** and **Use as after** assign that asset to Audio review. Selecting
a new source clears any earlier matching-range confirmation. Confirm that both
exports use the same range and settings before building measured A/B. A technical
A/B readiness result is not a musical-quality verdict.

**Cancel watch** cancels only intake. The global **Stop** cancels intake as well
as latching the existing executor stop. Cancellation is cooperative: a file already
published before cancellation is not retracted or deleted. Wait for in-flight jobs
to settle before resetting global Stop in Setup. Closing the app ends a watch;
completed imports persist in the normal asset manifest. Browser reload reconnects
to the current watch while that same app process remains running.

## Refusal and publication rules

- Pre-existing audio names must remain unchanged. Overwriting, deleting or
  recreating an old audio file fails the watch; it never becomes a new export.
- More than one observed new audio filename is ambiguous, including empty or
  still-writing files. The folder is checked again immediately before publication.
- The directory is nonrecursive and bounded to 4,096 entries. Audio files over
  300 MiB fail without being copied. Zero-byte files cannot become ready.
- UNC paths, symbolic links, Windows reparse points, hard-linked audio, and
  replaced directories are refused. Use genuinely local storage: this is not a
  network-filesystem watcher and does not qualify network-backed mounted drives.
- File size, modification time and available file identity/change-time evidence
  are checked before and during import. An independently read source SHA-256 must
  match the staged copy. A failed or cancelled import does not publish an input
  record or leave a staged input file. The original export is never changed.

The stable-size interval is one second. This is **not** a completion handshake
with FL: a producer can pause writing for longer, or resume after verification.
Do not export into a directory concurrently used by another application. Later
changes to the source do not change the already verified local copy. Supported
filename extensions do not prove codec validity; analysis/review performs the
existing decoder checks. An incomplete or invalid audio file can still fail there.
These guards are not a general hostile-filesystem security boundary.

## Shared API

All routes retain the existing authentication, Host and Origin protections.

| Route | Behavior |
| --- | --- |
| `POST /api/render-watch` | Desktop-only folder consent with `folder`, optional integer `timeout`, and literal boolean `confirm_folder: true`; returns `job` and `watch_id`. |
| `GET /api/render-watch` | Current watch state; does not include the selected source-folder path. |
| `POST /api/render-watch-cancel` | Exact current `watch_id`; stale IDs cannot cancel a newer watch. |
| `GET /api/jobs/{job}` | Existing job completion/error and captured asset receipt. |

The MCP relay adds **copilot_render_status** and **copilot_render_cancel** (19
tools total). It deliberately cannot select a folder or start a watch. A model
can observe a user-armed watch, read the resulting asset ID, and use the existing
analysis/review tools. It must not invent the user's export-range declaration.
The HTTP route is a trusted local-client boundary, not proof of a physical human:
protect the desktop bearer token as before.

## Evidence and boundaries

Imported records persist `watch_id`, `source: watched_fl_export`,
`source_file_unchanged: true` (at verification),
`render_triggered_by_app: false`, and `causal_provenance_verified: false`.
These flags must not be upgraded merely because files appeared in the selected
folder. No saved-project identity, time range, FL session, render settings, or
musical improvement is inferred. No transport, plugin, mixer or Playlist command
is issued by intake.

Run `python -m pytest -q tests`, `python scripts/verify_runtime.py`, and optionally
`python scripts/verify_render_ui.py` with Playwright and Chromium installed.
The runtime test exercises a real app process, authenticated HTTP, real synthetic
WAV copying and A/B output, and MCP stdio status/cancel. It does not run FL.
The UI harness reports whether ordinary HTTP navigation worked or a documented
DOM-to-service fallback was required; it never changes browser administrator policy.

Native Windows/FL validation remains required on a disposable saved project:
arm, manually export a new mix, analyze it, capture a second bounce, review the
pair, then test overwrite refusal, split-stem ambiguity, Cancel, Stop, and restart.
No live-host acceptance claim is made by simulator tests or Windows CI.

Next development: qualify native Windows/FL exports first, then investigate an
explicit controller-triggered render mechanism with verifiable session, range and
output evidence. Do not substitute blind key presses or assume an upstream render
command is safe without qualification.
