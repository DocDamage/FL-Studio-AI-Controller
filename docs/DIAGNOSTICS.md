# Connection diagnostics and first control proof

In the running companion, open **Connection & setup → Check connection**. This
checks environment and live preconditions without saving, recording, moving a
project control, clicking a menu, or enabling the write gate.

The environment checks enumerate MIDI names without opening ports. The live
handshake uses the app's existing adapter; it may establish that app-owned bridge
connection. No second controller is started. `CHECK_CONNECTION.cmd`,
`python -m flcopilot --diagnose`, and `scripts/doctor.py` reuse the running app.
For the demo workspace, add `--demo`; an explicit `--workspace` is supported.

## Reading the result

Fourteen rows distinguish Python architecture/range, local FFmpeg, pinned
PostFader, the real FL user-data Hardware folder, bridge-file presence, MIDI
enumeration, exact input/output endpoint matching, process MIDI enablement,
compatible live handshake, live source provenance, project-load epoch protection,
closed write gate, Stop state and unresolved journal outcomes.

An environmental failure and a live bridge observation are separate evidence.
For example, a bridge already loaded in FL may respond even when its on-disk file
has disappeared. The write-precondition summary follows the current live handshake,
source/epoch/gate evidence and app stop/journal state; it is not a blanket pass for
all installation rows. Review failed rows before using the tool.

A simulator cannot qualify FL. An older/mismatched bridge is not silently accepted.
A native-menu probe, plugin load, audio-loop test, or subjective listening verdict
is not inferred from a successful handshake.

## Deliberate 1 dB round trip

Save a new project copy. Leave Master protected. Select one non-master insert and
click **Preview 1 dB test**. In Assist, approve that displayed reduction and check
FL. Then use its journal entry's **Preview restore**; inspect and approve the new
return-to-original plan separately. Review actual receipts, not only the banner.

The report can distinguish no test, prepared/not-completed, verified reduction,
and verified reduction plus restore for the current bridge session. It looks at
the last 50 journal plans. Those are application control receipts, not full Windows,
plugin-menu, audio-capture, latency or musical-quality qualification.

## Sharing evidence

**Export privacy-filtered report** creates `Connection_Diagnostics.json` in a new
workspace export folder. It omits local paths, device/endpoint names, raw errors,
project contents, model addresses, auth tokens and session fingerprints. Local-only
details remain available in the application. Review every file before sharing.
CLI exit 0 means live write preconditions ready, not authorization; exit 2 means
not ready, a simulator, no running app, or a diagnostic error.

## Primary source references

The adapter contracts are pinned to PostFader 10.0.0 revision
`480bedd1cde98fe272c5e02f66efd7aa83315d0b`, specifically `readonly_inspector.py`,
`verified_writer.py`, `host_config.py` and `docs/setup.md`.

- https://github.com/synopsys0/postfader-fl-studio-mcp/tree/480bedd1cde98fe272c5e02f66efd7aa83315d0b
- https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm
- https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/mixer.htm

Sources were reviewed for this September 17, 2026 development increment. Source
review and fixture coverage are not native-host acceptance.
