# Persistent bounce library — v0.5 development

Open **Audio lab → Bounce library**. Both manual imports and watched exports are
listed newest-first. Search filename, library label, or notes; filter by source;
use Previous/Next to page through 20 inputs at a time. Generated masters and review
outputs remain in their existing output views, not the input library.

Open an input to edit its label and notes. These are stored in the existing local
`assets.json` manifest. The original filename, copied bytes, source export, SHA-256,
and watch provenance do not change. No new database or migration is required.
Older imports still appear; their unknown import date/size is not invented.
Editing does not change import order. Labels are limited to 100 characters and
notes to 2,000. The library survives restarting the app; folder watches do not
restart or regain access without new consent.

Unsaved notes remain in the editor during list refresh. Saving from an outdated
view is refused rather than overwriting a newer revision. Use **Reload saved notes**
to explicitly discard a draft and reopen the stored version. Browser-close warnings
are best-effort; save important notes before leaving.

**Analyze** measures the actual stored copy with the existing analyzer. **Verify
copy** rechecks its SHA-256 and reports when that check occurred. Listing only reads
metadata; it is not an integrity check, codec validation, or proof that FL finished
rendering. Failed verification clears the prior success message. Missing or changed
copies remain in history so their notes can be recovered, but verification refuses
them. Re-import an intact file to create a new input.

**Use as before / Use as after** select the saved input in Audio review. Either
handoff clears the matching-export confirmation. Changing either regular A/B
selector now clears that confirmation too. Confirm the two exports use the same
range/settings before creating measured A/B; no musical preference or DAW change
is automatically approved.

## API and MCP

All routes use the existing loopback authentication and Host/Origin protections:

- `POST /api/bounces`: optional `query`, `source` (`all`, `manual`, `watched`),
  `offset`, and `limit` (1–50). Returns items, total, and next_offset.
- `POST /api/bounce-get`: exact input `asset` ID.
- `POST /api/bounce-edit`: `asset`, `expected_revision`, `label`, and `note`.
- `POST /api/bounce-verify`: `asset`; returns a normal asynchronous job.

`copilot_bounces` adds read-only search/pagination to the existing MCP relay (20
tools total). It does not expose label/notes writes, folder selection, approval,
or render commands. Model clients must treat notes as user data, not instructions.
The library omits automatic source/workspace path fields. User-entered labels,
filenames, and notes remain visible to authorized clients, so do not put secrets
in them. Verification flags never establish FL-session or causal provenance.

## Validation of this increment

Base: PR #3 commit `3ce7908ec3290c161f61f5c8c30dc79b37e8fc79`.

Executed locally on Linux/Python 3.13: **485 tests passed with warnings treated as
errors**, including 38 new library cases. Real companion/diagnostics/MCP subprocess
checks passed, including library edits through HTTP and search through MCP stdio.
The new browser harness passed 15 checks, including service restart, notes conflict,
real audio analysis/A-B generation, current-byte verification, and 390px layout.
The existing export-workflow browser harness also passed its 15 checks.

Ordinary localhost browser navigation was blocked by administrator policy here.
The browser harnesses reported their direct-Service DOM fallback; no browser policy
was changed. Actual HTTP was tested separately. This is not live FL Studio testing,
physical audio audition, a signed installer, or an automatic-render implementation.
Exact Windows/Ubuntu CI outcomes belong to the published commit's Actions checks.

Evidence: `evidence/bounce_library_tests.txt`, `evidence/bounce_library_runtime.json`,
and `evidence/bounce_library_ui.json`. Historical manifests/reports describe their
own older snapshots, not this increment. Package version remains 0.4.0 during v0.5
development. Distributions must use a freshly generated manifest.
