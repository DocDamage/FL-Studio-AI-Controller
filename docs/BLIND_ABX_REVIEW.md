# Blind A/B/X listening — unreleased v0.5

Open a technically ready **Audio review**, then use **Blind A/B/X listening**. The
companion now supports both one quick blind trial and a precommitted multi-trial
session over the already-rendered, level-matched audition WAVs. Neither mode renders
FL Studio, changes the project, chooses a preferred version, or decides whether a
mix is better.

## Distraction-free blind mode

Starting unanswered blind work automatically hides the labeled A/B player,
measurements, waveform/loop controls, section deltas, full report details, listening
preference controls, and review-export file list. Those labeled views return after a
single trial is answered or after the entire precommitted session is completed.

This matters because the earlier single-trial increment hid the server mapping but
left labeled evidence visible elsewhere on the page. The new focus state removes
those obvious identity cues from the active review workspace. It still cannot control
what the listener saw or heard before starting the blind work, other applications,
external notes, or operating-system audio processing.

## One blind trial

Starting a single trial re-verifies the saved review report and both matched WAV
outputs. The server uses a cryptographic random choice to assign the baseline and
candidate to **Reference A** and **Reference B**, then independently makes **X** equal
to A or B. While the trial is open, the browser receives only the trial ID, creation
time and blinded A/B/X audio routes.

Play A, B and X as often as needed, then submit **X matches A**, **X matches B**, or
**Unsure / no guess**. The mapping and correctness are revealed only after that
submission. A completed single trial cannot be answered again.

## Precommitted blind sessions

Choose an even session length from 4 through 20 trials. Before the first answer, the
server creates the whole trial set in one transaction:

- Reference A is baseline for exactly half of the planned trials and candidate for
  the other half.
- X equals A for exactly half and B for the other half.
- Both balanced lists are independently shuffled with the operating system's
  cryptographic random source.
- Every hidden trial receives its ID and ordinal up front.

Only one unanswered blind work item is allowed per saved review. A session therefore
cannot be silently restarted after seeing intermediate feedback, and a session-owned
trial cannot be submitted through the single-trial endpoint.

Answers are recorded sequentially. While any planned trial remains, the API returns
only the session ID, progress, and next blinded trial ID. It does **not** return prior
mappings, correctness, aggregate accuracy, or hidden assignments. Open sessions
survive an application restart with those answers still sealed.

After the final planned answer, the session reveals every trial and a descriptive
summary: correct, incorrect, unsure, scored-trial count, scored accuracy, and an exact
50/50 upper-tail chance probability. Unsure answers are excluded from scored
accuracy.

The chance-tail value is deliberately labeled **descriptive**. Its calculation
assumes independent 50/50 trials, but this app does not establish listener
independence, controlled listening conditions, preregistration outside the local
record, absence of learning/fatigue, or any other requirement of a formal study.
It is not presented as a statistical-significance verdict.

## Persistence and evidence

Blind trials and sessions live in the local review SQLite database, separate from the
normal listening preference and its revision. Starting, playing or answering blind
work never changes the saved baseline/candidate preference, needs-revision state, or
any FL Studio control.

Existing databases from the first single-trial blind increment are migrated in place:
the trial table gains nullable session/ordinal fields and existing rows are retained.

The server rechecks the saved output identities and SHA-256 bytes before creating
blind work, serving each A/B/X file, and accepting an answer. If the report or an
audition WAV changes, disappears, escapes the workspace, or no longer matches the
measured review evidence, the operation is refused. Stop also blocks new
verification work. The original imported before/after bounces are not reverified by
this feature, and matched review outputs still do not prove which FL session produced
them.

## API boundary

Authenticated loopback routes for single trials:

- POST /api/review-blind-start with review_id.
- POST /api/review-blind-history with review_id.
- GET /api/review-blind-file/<trial_id>/a|b|x.
- POST /api/review-blind-submit with trial_id and guess (a, b, or unsure).

Authenticated loopback routes for sealed sessions:

- POST /api/review-blind-session-start with review_id and an even trials value from
  4 through 20.
- POST /api/review-blind-session-history with review_id.
- POST /api/review-blind-session-submit with session_id and guess.
- The same blinded-file route serves the current precommitted trial.

Start and submit operations run through the existing job queue and audio lock. Audio
routes use static blinded filenames such as Blind_X.wav; they do not expose the real
review asset ID in the route. There is intentionally no MCP tool for answering blind
work: the answer is a human listening action in the desktop interface, not an AI
task.

## What this does not prove

A correct answer means only that the submitted response matched that hidden
assignment. A completed session gives more structured evidence than repeatedly
starting ad-hoc trials, but it still does not establish audible superiority, mix
quality, causation, a preference, population-level repeatability, or formal
double-blind laboratory validity.

Browser media playback is approximate. A/B/X switches are not sample-synchronous or
gapless, and device/driver latency is not measured. The blind player keeps the
current audition position when blind work starts or the seek position changes. The
labeled waveform itself is hidden while an answer is outstanding.

The feature adds no dependency, no automatic FL export, no new DAW authority, no AI
listener, and no artistic scoring model.
