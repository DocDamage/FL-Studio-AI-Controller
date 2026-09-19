# Repository import — v0.2.0

This repository contains the application source from the cumulative
`FL_Studio_AI_Copilot_v0.2.0_Windows_Source.zip` release. The initial generic
README remains available in Git history; the root README is the full project guide.

## Preserved source

All Python modules, web assets, Windows launchers, PowerShell setup scripts,
tests, dependency files, licenses, documentation and textual validation evidence
are included. Application and test contents are unchanged from the release.
No private local settings, virtual environment, database, imported audio, model
weights or FL project is included.

The five generated browser PNG screenshots remain in the original release ZIP
and are excluded from source control. The browser smoke script can regenerate
them. They depict a simulator and do not prove live FL Studio operation.

`docs/history/v0.2.0_RELEASE_MANIFEST.sha256` preserves the original archive
payload manifest, including those screenshots. The root `MANIFEST.sha256` is
regenerated for this repository import and covers its tracked payload except
itself. Original build reports describe the earlier release, not a new host test.

## Import validation

- Original archive SHA-256: `66be2d01058a77a4c0cc81a29a3b84cde2f66253f59c8cfe2fa087ad44131430`.
- Archive CRC passed; all 87 original manifest entries matched before import.
- Core suite rerun for import: **214 passed**, Linux Python 3.13, 14.96 seconds.
- Native Windows installation, FL Studio, MIDI and local-model qualification
  remain unverified. The included CI workflow is a fixture-test workflow only.

No application feature or dependency version changed for this import.
