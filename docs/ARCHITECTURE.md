# Architecture and trust boundaries

## One mutation owner

`cli.py` acquires a process-lifetime workspace lock and constructs one `Service`.
The stdlib HTTP server binds only to 127.0.0.1. UI requests and MCP requests converge
on the same service. The MCP relay opens no MIDI device and owns no executor.

The audio job pool has two workers and a bounded submission queue. Audio analysis
and rendering also share an audio lock. DAW reads/writes use the executor mutex
and the PostFader adapter's I/O lock. A long peak observation prevents another
DAW command from interleaving. It does not disable manual edits in FL.

## Plan state machine

`prepare -> ready -> running -> verified | blocked | stopped | unknown_outcome`.
Ready plans expire after five minutes and cannot survive an app restart. A plan
cannot be claimed twice. A running plan discovered at startup becomes unknown,
blocking later writes. Intent is committed to SQLite before crossing the target
command boundary; acknowledged/independent readback is committed afterward.

Preparation binds the observed before-state, session fingerprint, backend, target,
operation, locks, and expiry to a canonical SHA-256 digest. Approval must carry
that digest. Pre-dispatch state is compared to the preview, not substituted with
a fresher unapproved state. After one verified change, its readback becomes the
baseline only for later operations in that same approved plan.

The five control types are volume, pan, rename, effect parameter, and isolated
experimental effect loading. Master/track/parameter locks are enforced centrally.
Tempo, notes, and arrangement are not writable. Fader moves are capped at 12 dB;
maximum plan length is 32; insertion must be the only operation in its plan.

`NotDispatched` is reserved for failures known to precede the target write.
Exceptions after a dispatch attempt are unknown; never infer a safe retry. Menu
loading may have selected the destination as a prerequisite even if insertion
itself was not dispatched. Selection is not the same as plugin insertion.

## PostFader adapter

V10's read-only inspector and verified writer supply the live bridge surface.
The app additionally demands a matching packaged bridge source digest and a
project-load epoch capability for writes. It refuses to acquire a write gate
that is already enabled by another client/startup configuration. Cleanup only
closes a gate this run attempted to acquire, and only for the same session.

The adapter uses actual source-reviewed method/guard schemas. Parameter guards
support normalized value or display text, not plugin identity. Therefore plugin
and control names are checked before dispatch and in the receipt/readback. This
is not atomic unique-instance identity: replacing an effect with an indistinguishable
instance between observations remains a known limitation. Do not manipulate FL
concurrently with an approved operation.

## Optional planner and runtime

A narrow deterministic parser handles exact fader, rename, mute/unmute and stereo-separation command forms. Other requests
may go to one explicit loopback llama.cpp-compatible HTTP endpoint. Remote hosts,
credentials in URLs, redirects, and proxy environment use are rejected. The prompt
contains a bounded mixer summary, not audio or arbitrary local files. Model output
must parse as strict JSON into a narrower volume/pan/rename allowlist. Empty or
unsupported requests fail closed. No model output is evaluated as code.

The optional `ManagedLlama` launches only the explicitly configured executable and
GGUF with a bounded context, four CPU threads, a configurable GPU layer count,
loopback host, and alias `local`. It owns only that child process. Model readiness,
quality, GPU fit, and underrun behavior still need host qualification.

## Audio and MIDI

Assets are explicit imports with random IDs and SHA-256 digests. The API resolves
IDs only within the workspace and rechecks bytes. Audio decoders, LUFS analysis,
4x peak estimation, and FFmpeg finishing operate independently of FL. Output is
accepted only if technical checks pass; incomplete render folders are removed.
Real A/B files are gain-matched to a common measured loudness; listening remains
human review, not an automatic quality score.

MIDI is a deterministic Standard MIDI File encoder. It writes musical events to
a new file only; it neither edits an FLP binary nor imports/places that file in FL.

## Module map

- `contracts`, `executor`, `journal`: authorization and receipts.
- `postfader`, `windows_menu`, `demo`, `unavailable`: DAW capability boundary.
- `audio`, `process`, `assets`, `mix`, `creative`, `checkpoints`: bounded tools.
- `planner`, `runtime`, `mcp_relay`: optional AI interfaces.
- `service`, `jobs`, `server`, `cli`, `instance`, `hotkey`, `web/`: application shell.


## v0.2 execution changes

`controls.py` defines captured-control semantics and rejects unrelated changes to
those fields after a write. A post-dispatch getter failure is always uncertain,
even if the getter raised a pre-dispatch-style exception. Numeric verification
requires finite non-boolean values. Receipt session and subsequent session must
both match the approved plan.

`Executor.prepare` accepts internal expected-session/before-state anchors. These
are not arbitrary client approvals. Relative prompt planning, control-test
previews and recovery use them to reject drift before a ready plan is persisted.
A source snapshot is not atomic; these guards cannot freeze all of FL or prove
identity for an indistinguishable replacement plugin.

`recovery.py` inverts only a complete verified run, using original captured values
and the final per-track/parameter readbacks. It produces a normal expiring plan
with purpose `restore` and a source plan ID. No automatic compensation happens on
error. The ordinary locks, user approval, stop, write gate and readback rules all
apply to recovery. Readable legacy receipts are retained but not upgraded into
new evidence. Plugin insertion is deliberately non-reversible here.

`diagnostics.py` separates environmental checks from the existing adapter's live
handshake and bounded current-session journal evidence. Environment enumeration
never opens a MIDI port. The live handshake may establish the app-owned connection;
no second controller or write transition is created. Diagnostic exports use an
allowlist omitting local-only data. `doctor_client.py` and `scripts/doctor.py` relay
to the already-running authenticated app, avoiding another MIDI owner.
