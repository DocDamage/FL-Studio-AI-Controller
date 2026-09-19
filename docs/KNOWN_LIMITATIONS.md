# Known limitations — v0.4.0

This release implements a useful guarded foundation, not the entire proposed DAW
agent. The distinction is intentional and visible in the capability ledger.

- No live FL Studio run was possible in the Linux build environment. GitHub CI
  core/simulator runs are not Windows FL, MIDI or plugin-insertion acceptance.
  The pinned external PostFader package was not installed/exercised here; source-reviewed
  API contract doubles are not equivalent to running its complete test suite.
- The native Windows Add-menu adapter is experimental. FL custom-drawn menus may
  expose nothing usable, in which case automatic loading remains unavailable.
  There is no coordinate/OCR/vision fallback that pretends this limitation is fixed.
- The exposed controls are fader dB, pan, rename, mute/unmute, stereo separation, loaded
  effect normalized/displayed-unit parameters, and isolated experimental effect insertion. Routing,
  solo, plugin removal/
  reorder, generator insertion, note editing, Playlist editing and arrangement
  manipulation are not exposed by this app, even where upstream has broader tools.
- "Finish" is a task-scoped approved pass, not autonomous repeated audition/revision.
  Peak gain staging is not full mixing. Master export is gain/normalization with
  optional dynamics limiting, not adaptive tonal EQ, compressor optimization,
  restoration, or an artistic-quality score. No Ozone-superiority claim is made.
- No live audio capture, automatic FL render, VST3 sensor/control plugin, stem
  separation model, sample chopping engine, or automatic stem export is included.
  Import actual renders manually. MIDI sketches are MIDI files, not finished beats.
- No guaranteed Undo or automatic rollback/save. A saved-FLP backup excludes
  unsaved edits and external samples. Keep your own versioned projects.
- Master is protectable rather than physically immutable: the user can explicitly
  unlock it in the UI. Musical content locks are not unlockable in v0.2.
- Readbacks are non-atomic snapshots. Indistinguishable plugin instances cannot
  be distinguished by name/index alone. Other clients or manual edits can race;
  validation reduces risk but cannot freeze the entire FL process.
- Optional local model binaries/weights are not bundled, inferred from your GPU,
  downloaded automatically, or benchmarked. External local endpoints must use
  the alias `local`. Model context and output bounds may be too small for huge
  projects; reject rather than pretend the omitted context was analyzed.
- No Windows signed EXE, self-updater, uninstall wizard, or fully hash-locked
  transitive dependency archive is provided. PowerShell launch/setup source is
  included and statically reviewed, not executed on Windows.
- Browser DOM flows were exercised with a direct-service test harness because
  ordinary localhost navigation was blocked by the environment's admin policy.
  HTTP/authentication was tested independently. Actual end-to-end browser startup
  and Windows media playback/download integration remain host acceptance items.

- Recovery previews are compensating writes for captured controls, not project
  rollback, Undo, plugin-preset restoration or automatic error recovery. They need
  a fully verified source run, the same session and matching captured state.
  v0.1 receipts without the expanded snapshots are not eligible. Data not captured
  by these controls (automation curves, hidden plugin state, audio, routing and
  arrangements) is neither restored nor certified unchanged.
- Diagnostics do not install drivers, configure FL MIDI ports, elevate permissions,
  or fix arbitrary device/host failures. A compatible handshake and fader round trip
  do not establish audio capture, plugin insertion, latency or artistic quality.
  The control-evidence lookup covers the most recent 50 journal plans for the current
  bridge session; historical evidence beyond that bound is not promoted implicitly.

- Plugin workbench scans are bounded windows, not persistent complete inventories.
  A search only covers the examined window. Nameless controls, unsupported/ambiguous
  display units, indices beyond 65,535 and missing readbacks are not promoted into
  editable engineering-unit controls. Observations expire after five minutes and
  are evicted after 16 retained scans.
- Display searches move intermediate values and cannot be interrupted inside an
  in-flight bridge call. Stopped-transport checks reduce risk but cannot prevent
  concurrent manual playback or hidden plugin changes. Reachability, normalized
  getter freshness, whole-preset restoration and audible improvement are not promised.

- Audio review analyzes imported exports, not live FL output. Equal-format and
  timing checks can refuse valid periodic or heavily changed audio. A ready pair
  is not sample/phase alignment, source provenance, causal proof or a quality score.
  Standard A/B and blind A/B/X playback are approximate, not gapless or
  sample-synchronous. Sealed sessions precommit balanced local assignments and hide
  intermediate feedback, but they still do not establish independent trials,
  controlled listening conditions, population repeatability, formal statistical
  significance, preference or an artistic verdict. Human decisions remain separate
  annotations.
  Crash-time orphan exports can remain during a narrow publication interval; no DAW
  replay or automatic user-file deletion occurs. See AUDIO_REVIEW.md and
  BLIND_ABX_REVIEW.md for the exact heuristics and persistence boundaries.
