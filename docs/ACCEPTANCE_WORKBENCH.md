# Native export acceptance workbench — unreleased v0.5 increment

The **Connection & setup → Native export test checklist** panel replaces manual JSON
editing for the existing Windows/FL export acceptance gate. It records what you
personally tested; it neither performs those tests nor controls FL Studio.

## Use it

Start with a **saved disposable project copy** in live mode. Follow the native
session procedure in [RENDER_ACCEPTANCE.md](RENDER_ACCEPTANCE.md). Mark each of the
11 observations as Not tested, Pass, Fail, or Blocked. Enter the exact Windows and
FL builds; Python, app mode, and the installed PostFader version are observed by
the app rather than accepted from an editable form.

Save the checklist. Its revision-checked draft survives restarting the companion,
without re-arming a folder or saving an FL project. Unsaved edits disable exports;
a stale save is refused instead of overwriting another view. Reload explicitly
discards unsaved edits. A corrupt draft is preserved and editing is blocked; the
rest of the app remains usable. Preserve `render-acceptance-draft.json` in your
workspace, move it aside, then restart to create a fresh draft.

**Export progress report** works in demo and live mode. It shares saved observations
without inventing a completed test or verified capture. Failed or blocked observations
remain failed or blocked. Even 11 manually selected passes are not a completed record.

For **Verify & export completed record**, select two separately watched captures and
their ready Audio review. The server requires:

- Native Windows, the live PostFader adapter, a connected compatible FL session,
  no unresolved controller result or running executor, and global Stop reset.
- Explicit export confirmation, every manual observation passed, the saved-project
  confirmation, and complete version/date fields.
- Two distinct captured inputs from distinct watches, current stored-byte hashes,
  a ready same-range review matching their IDs and hashes, the original review
  report, and both original level-matched outputs with matching file hashes.

The app rechecks both inputs and the FL session before publishing a new JSON file.
The exported report binds the captures and review-report hash; it does not
automatically attach audio or private host fields. Export does not change the saved draft
into an ongoing pass badge and never enables DAW writes. Each later completed
export must verify its evidence again. No new MCP tool can edit or complete the
checklist. The relay remains at 20 tools.

## Privacy and compatibility

The public formatter rejects unknown top-level fields instead of accidentally
copying them into a supposedly filtered export. It drops `project_label`,
`export_folder`, `interface_and_driver`, and `private_notes`, and returns an
independent copy. **Shared notes, manually entered version text, and evidence names
are not secret-scanned. Review them before sharing.** Existing schema 1.0 public
records with the previous exact privacy notice remain readable; newly formatted
records use a narrower, accurate notice.

The generated JSON remains compatible with `scripts/validate_render_acceptance.py`.
That standalone CLI validates the record's schema, not the current bytes or host.
The desktop completed-export path performs the additional runtime checks above.

## Boundaries

A recorded pass is a human attestation plus point-in-time evidence checks, not an
independent observation of the 11 tests, proof FL created those files, musical-quality
assessment, or an atomic filesystem snapshot. Files can change after verification.
Build fields are user-entered descriptions, not attestations about the exact installed
FL build. Watched provenance flags remain false. No automatic render, blind key
presses, project save, folder authorization, mode change, or hidden control is added.

Local development uses synthetic audio, demo processes, and explicit native-host
contract doubles. Browser evidence records whether ordinary HTTP navigation worked
or the direct-Service DOM fallback was needed. Neither browser testing, the
standalone CLI, nor Windows CI is a native FL Studio acceptance session.
