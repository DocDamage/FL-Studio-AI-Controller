# Windows / FL Studio acceptance checklist

**Status: NOT RUN in this release environment.** Complete this on a disposable
project, with monitoring at a low volume. Record your exact OS/FL build, interface,
MIDI driver/provider and endpoint, display scaling, plugin versions and results.
Do not promote the Windows menu adapter to production-ready based on fixture tests.

## Installation and connection

1. Install with 64-bit Python 3.13 using `SETUP_WINDOWS.cmd`. Verify `pip check`.
   Do not proceed past a dependency error. Dependencies are downloaded separately.
2. Run the demo, confirm the amber simulator banner, inspect, prepare a pan/fader
   move, switch to Assist, approve and read the simulator receipt. No FL connection
   should be attempted in this mode.
3. Close the demo and any other PostFader/MCP process. Configure one bidirectional
   virtual MIDI endpoint. Run `CONNECT_FL.cmd` while FL is closed for deployment.
4. Start FL; set Universal Bridge on the enabled matching input and the same MIDI
   port number on matching output. Reload the script and confirm `ready: MIDI SysEx`.
5. Start live mode, click Inspect. Require correct version, actual project, complete
   track inventory, stable session and matching packaged bridge digest. A rejection
   must remain a rejection; do not disable the compatibility/provenance checks.

## Small control acceptance

Save a new FLP version first. Leave Master locked. In Connection & setup, run
Check connection and review every live precondition. The simulator does not count.
Choose an insert with Preview 1 dB test, inspect the exact preview, choose Assist
and approve. Confirm the actual
fader in FL, the later readback and the receipt. In Run journal choose Preview
restore for that exact test. Verify no movement before its separate approval;
then approve and confirm the original fader value in FL. Export diagnostics and
retain the actual application receipts. Repeat for pan, rename, explicit mute and
stereo separation on disposable inserts. Verify
Inspect cannot execute, a locked track cannot be changed, and an old preview is
rejected after you manually move the target or load another project.

For a loaded effect parameter, read its slot/index/name first. Make one small
normalized change, verify actual UI state and audible behavior, then restore it
through a newly approved plan. Quantized or delayed-readback plugins may produce
unknown outcomes; this is not evidence of failure to be blindly retried.

## Windows named-menu probe and insertion

Enable the experimental adapter. Click Probe; focus FL's main window during the
five-second handoff, and stop moving the mouse/typing. A missing native Add menu,
custom-drawn menu, localized mismatch, duplicate entry, popup or wrong focus must
produce manual handoff, not a blind click. Confirm the observed effect path is real.

Select an empty disposable destination insert and prepare one exact effect load.
Use the five-second execution handoff. Require one and only one matching new slot
in the receipt and actual FL UI. Test foreground change, a plugin modal, resize/DPI
change, and user input just before dispatch: each must refuse safely. An attempted
click with uncertain outcome must not be replayed. The executor must block further
writes until fresh inspection and explicit reconciliation.

Generator loading, replacing effects, reordering/removing slots, and custom-drawn
menu fallback are out of scope. Load those manually, then inspect their parameters.

## Stop, restart, and recovery

Check the registered-hotkey status. Test red Stop and, where registered,
Ctrl+Alt+Shift+F12 between two approved operations. At most the current in-flight
operation may complete; no later operation should start. Wait for jobs to finish
before resetting Stop. Test interruption only in a disposable project: restart must
mark the pending run unknown and block writes. Inspect before acknowledging it.

## Audio and model acceptance

Import a known exported bounce, analyze it, generate both finishing modes and
compare the reports against a trusted meter in your normal signal chain. Audition
level-matched A/B for transient damage, pumping, mono cancellation and clipping.
Peak estimation is not certification. Check source hashes remain unchanged.

With a local model, first test an unambiguous one-control request. Confirm no action
occurs without approval. Check invalid/ambiguous/model-injected output is refused.
Measure real inference latency, VRAM headroom and FL underruns before assigning
more GPU layers or running larger models. No model benchmark was supplied here.

## Record

Use `evidence/WINDOWS_ACCEPTANCE_TEMPLATE.json` to record actual observations.
Do not replace `not_run` with `passed` without a corresponding host result.


## v0.2 recovery refusal tests

On a disposable verified run, move a captured target control manually before
requesting restore. Restore must refuse; it must not overwrite the manual change.
Repeat after loading another project, locking the insert, locking a parameter, and
with a plugin-insertion source run. Only complete verified control runs in the same
session are eligible. A failed post-dispatch read must latch unknown outcome, not
be classified as an unexecuted command. Acknowledging an uncertain state never
retroactively makes the uncertain run restorable.

## v0.3 workbench acceptance (not yet performed against FL)

On a saved project copy with one manually loaded effect, inspect its actual names
and raw indices in Plugin workbench. Confirm that a small window is marked partial
and that Next window reaches controls outside the first 128 positions. Stop FL
playback and recording, select one explicitly unit-bearing control, and prepare a
small bounded change. Verify the preview without approving; the FL control must
not have moved. Start playback and confirm that applying the preview is refused.
Stop playback, prepare a fresh preview, approve, and compare both the real displayed
value and receipt. Then separately preview and approve restoration of that value.

Also test a plugin without supported display text: no unit should be guessed. Test
a changed plugin/parameter after scanning: the stale preview must refuse. Capture
evidence locally without including private project names, tokens, paths or audio
in public issues. Passing these steps qualifies only those observed controls on
that host, not other plugins, live audio capture or musical quality.
