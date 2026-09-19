# Guarded FL render intake — v0.5 development

The current PostFader bridge does not provide a qualified FL Studio render/export
command. v0.5 therefore adds a deliberately bounded handoff instead of pretending
that screen automation is reliable.

The companion snapshots an **explicit folder selected by the user before export**,
waits for exactly one new or changed supported audio file, requires its size and
timestamp to remain stable, and copies it into the normal immutable import
workspace. The source export is never deleted, renamed or modified.

## Intended workflow

1. Choose or create a clean export folder.
2. Start a render watch before exporting from FL Studio.
3. Export one WAV/FLAC/AIFF/OGG/MP3/M4A/AAC file from FL into that folder.
4. The watcher refuses multiple simultaneous candidates and files above the normal
   300 MiB import limit.
5. Once stable, the file is copied through the same asset store used by manual
   imports and receives a SHA-256 hash.
6. Use the resulting asset in Audio Lab or Before/After Review.

A watched export records `source=watched_fl_export`,
`render_triggered_by_app=false`, and `causal_provenance_verified=false`.
Those distinctions are intentional: observing a file after a user export does not
prove which FL state produced it or that a preceding controller action caused an
audible difference.

## Safety boundaries

The watcher does not click FL, press render shortcuts, type filenames, scan the
whole filesystem, overwrite audio, or enable bridge writes. Timeout is bounded to
ten minutes. Cancellation uses the existing Stop event. An export that changes
before/during import is refused rather than silently promoted.

This is the safe bridge toward automatic render review. A future direct render
implementation should only replace this handoff after the exact FL/PostFader
render API can provide destination, range, format, completion and session evidence
without coordinate automation.
