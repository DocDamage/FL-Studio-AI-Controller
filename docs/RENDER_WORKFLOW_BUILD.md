# Render workflow development receipt

Date: 2026-09-19. Source: `DocDamage/FL-Studio-AI-Controller`, following merged PR #2.
Branch: `dev/v0.5-render-workflow`. No automatic merge into main.

Implemented: one-shot user-authorized folder intake, shared service/HTTP integration,
Audio lab controls and analysis/review handoff, two pathless MCP tools, persisted
provenance, staged publication, and overwrite/link/ambiguity/cancellation hardening.
CI now retains its exact source-under-test ZIP for seven days to make results
reproducible. The archive contains tracked source, not the user's workspace or audio.

Validation in this Linux environment:

- Original source baseline: 380 pytest tests passed.
- Final suite: 435 pytest tests passed (55 new cases).
- Real app/diagnostics/MCP subprocess validation passed, including watched WAV
  capture, persisted provenance, cancellation and measured review outputs.
- New export-workflow browser harness: 15 checks passed, zero page errors.
- Existing audio-review browser and general DOM regressions also passed.
- Desktop and 390-pixel mobile screenshots were inspected for layout issues.

Ordinary localhost browser navigation was blocked by environment administrator
policy. Browser checks used an explicitly recorded direct-service DOM fallback.
Authenticated HTTP was separately exercised by pytest and a real app subprocess.
This is not Windows desktop launch, live FL, physical audition, or signed-installer
validation. Native Windows/FL acceptance is still outstanding.

Machine-readable evidence is in `evidence/render_ui_validation.json`,
`evidence/render_workflow_runtime.json`, and `evidence/render_workflow_tests.txt`.
Historical release manifests/build reports are unchanged; they do not describe
this unreleased development increment. Fresh distribution packages must generate
their own current manifest, not claim the old release manifest validates new files.
