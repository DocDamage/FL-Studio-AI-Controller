# Blind A/B/X listening — unreleased v0.5

Open a technically ready **Audio review**, then use **Blind A/B/X check**. This is a
human discrimination aid for the already-rendered level-matched audition WAVs. It
does not render FL Studio, change the project, pick a preferred version, or decide
whether a mix is better.

## What is hidden

Starting a trial re-verifies the saved review report and both matched WAV outputs.
The server then uses a cryptographic random choice to assign the baseline and
candidate to **Reference A** and **Reference B**. It independently chooses whether
**X** is A or B. While the trial is open, the browser receives only the trial ID,
creation time and blinded A/B/X audio routes. The mapping, X answer, asset IDs,
source filenames and local paths are not returned.

Play Reference A, Reference B and X as often as needed, then submit **X matches A**,
**X matches B**, or **Unsure / no guess**. Only after that submission does the
server return the mapping and whether a non-unsure guess was correct. A completed
trial cannot be answered again.

## Persistence and evidence

Blind trials are stored in the existing local review database but are separate from
the normal listening preference and its revision. Starting, playing or answering a
blind trial never changes the saved baseline/candidate preference, needs-revision
state, or any FL Studio control. Open trials survive an application restart without
revealing their mapping. The latest 20 trials for a review are shown locally.

The server rechecks the saved output identities and SHA-256 bytes before creating a
trial, serving each A/B/X file, and accepting an answer. If the report or an audition
WAV changes, disappears, escapes the workspace, or no longer matches the measured
review evidence, the operation is refused. Stop also blocks new verification work.
The original imported before/after bounces are not reverified by this feature, and
matching review outputs still do not prove which FL session produced them.

## API boundary

Authenticated loopback routes are:

- POST /api/review-blind-start with the saved review_id.
- POST /api/review-blind-history with the saved review_id.
- GET /api/review-blind-file/<trial_id>/a|b|x for the blinded WAV.
- POST /api/review-blind-submit with trial_id and guess (a, b, or unsure).

Start and submit run through the existing job queue and audio lock. Audio routes use
static blinded filenames such as Blind_X.wav; they do not expose the real review
asset ID in the route. There is intentionally no MCP tool for answering a trial:
the answer is a human listening action in the desktop interface, not an AI task.

## What this does not prove

A correct answer means only that one submitted trial matched the server's hidden
assignment. It does not establish statistical significance, repeatability, audible
superiority, mix quality, causation, or a preference. Repeating self-selected trials
does not automatically turn the history into a controlled listening study. The test
is single-listener and computer-assisted; it is not a formal double-blind laboratory
protocol.

Browser media playback is approximate. A/B/X switches are not sample-synchronous or
gapless, and device/driver latency is not measured. The blind player shares the
current audition position when a trial starts or the waveform seek control moves,
but the waveform itself remains the ordinary labeled review display. Do not use the
visible labeled waveforms as an identity clue during a blind judgment.

The feature adds no dependency, no automatic FL export, no new DAW authority, and no
artistic scoring model.
