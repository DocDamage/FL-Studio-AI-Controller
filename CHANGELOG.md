# Changelog

## 0.3.0 — September 19, 2026

Added the plugin workbench: read-only padded-parameter search, bounded pagination,
expiring observation tokens, and normalized or explicit dB/Hz/ms/percent previews.
Displayed-unit writes require stopped transport, remain isolated and approved, and
receive independent displayed-value readback plus separately approved restores.

Added two MCP tools (14 total), a fictional high-index demo effect, authenticated
routes, UI coverage indicators, and unit/pagination/staleness/adapter/HTTP tests.
The legacy parameter endpoint now shares executor serialization. The Windows/Linux
CI matrix also exercises actual simulator and MCP processes. Dependency pins and
PostFader revision are unchanged. This is not live FL Studio qualification.

## 0.2.0 — September 17, 2026

Cumulative development source. Not a live-qualified Windows or FL Studio release.

Added explicit mute/unmute and stereo-separation controls, exact offline command
forms, before/after verification and protection locks. Added 14 connection checks,
privacy-filtered exports, an explicit 1 dB test preview, verified-control restore
previews, journal buttons, and three MCP tools (12 total). Standalone diagnostics
now relay to the running companion rather than creating another bridge client.

Fixed post-dispatch getter failures being eligible for pre-dispatch classification;
wrong-session receipts, non-finite readbacks and unrelated changes to captured target
controls now stop execution. Relative prompts and restores use preparation anchors
to reject changes during planning. Existing uncertain outcomes still require review.

Added upgrade, diagnostics, recovery and expanded Windows acceptance documentation.
Preserved the original audio/MIDI engines, master protection, musical-content locks,
local model option, application workspace, journal and unchanged pinned PostFader.

Validation: 214 Python tests; 23 browser DOM/direct-Service checks with no page errors;
actual simulator app/doctor/MCP process smoke. Ordinary browser HTTP launch remains
blocked by environment policy. Windows/FL, actual upstream runtime and GPU inference
were not exercised. See BUILD_REPORT.md and evidence for exact scope.

## 0.1.0

Initial guarded companion, PostFader adapter, experimental Windows menu backend,
audio analysis/finishing, deterministic MIDI sketches, optional local planner,
authenticated UI, MCP relay and durable execution journal. Historical validation
record retained under docs/history/v0.1.0_BUILD_REPORT.md.
