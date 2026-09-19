# Before / after audio review — v0.4.0

This milestone evaluates explicitly imported exports. It does not record FL,
trigger a render, apply an EQ, save a project, or decide which version sounds better.
The previous general Reference comparison remains available for different songs.

## Workflow

Export the baseline and candidate from the same song, range, and export settings.
Import both in Audio lab, then open Audio review. Choose the files and confirm that
the export range/settings match. Optionally associate a fully verified journal run;
that association does **not** establish that either file came from that FL session
or that the linked operation caused the measured changes.

Choose 10–60 second measurement windows and a review title. Analyze the pair. If
sample rate, channels, frame count or finite loudness do not match the requirements,
the result includes each file's measurements and explicit blockers, but no A/B audio.
A timing offset, ambiguous evidence or inconsistent window delays also withholds A/B.
Re-export an aligned pair rather than overriding the timing checks. A deliberately
different arrangement belongs in the ordinary global comparison, not this workflow.

A ready result produces three new files:

- `A_Baseline_Matched.wav` and `B_Candidate_Matched.wav`: float32 WAVs at the original
  rate, channel count and exact frame count, using only nonpositive gain adjustments.
- `Review_Report.json`: immutable measurements, source/output hashes, timing evidence,
  blockers, per-window deltas and any explicit journal association.

Both audition files are reread and measured. Each must be within 0.1 LU of the common
target, the pair must be within 0.1 LU of each other, and their 4x oversampled peak
estimates must not exceed -1 dB. A 0.2 dB construction margin is included. If input
headroom is limited, both files are attenuated further rather than clipped or limited.
This can make audition files quiet. No EQ, compressor, limiter, stretching, offset
correction, cropping or automatic loudness boost is applied.

Use Play / switch A and B, or the exported WAVs in your own player/DAW. Browser
switching preserves approximate playback time only: it is not sample-synchronous,
gapless or a blind ABX test. Physical monitoring and listening quality were not tested
in the build environment. A global Stop also pauses the review player. The existing
Audio lab players are independent; avoid playing multiple audition streams together.

Save a preference and listening note explicitly. This creates a new decision
revision and cannot overwrite a newer choice made in another tab without a reload.
The original report and WAVs do not change. Choices remain separate from measured
results and never authorize a plan, save FL, or mark a candidate technically superior.
Blocked pairs permit only undecided or needs-revision choices. Local history lists
the most recent 50 reviews; known IDs remain retrievable through the read tool.

## Timing evidence and its limits

For exactly proportional decoded samples, the check reports samplewise consistency,
including a flag for polarity inversion. Otherwise it examines up to three windows
of multichannel RMS energy at approximately 10 ms resolution. Both channel energies
are included, so an antiphase mono fold does not erase the probe signal.

Each window searches +/-500 ms. A usable peak needs normalized correlation >=0.85
and a >=0.03 margin above alternatives more than two envelope bins away. Windows
must contain varying energy. At least two usable probes are required when two or
more distinct windows are available. A median offset exceeding about 10 ms blocks
A/B; disagreement above 20 ms also blocks it. These values are **conservative product
heuristics, not calibrated confidence probabilities**. Flat, periodic, short or
heavily altered music can be refused even when the user exported it correctly.

A positive estimated delay means the candidate arrives later. No estimated delay
is used to move audio. Consistency is not sample/phase alignment, proof of song
identity, export provenance, or detection of every possible timing change. The
report deliberately keeps `content_alignment_verified=false` even for ready pairs.

Measurements use the existing pyloudnorm integrated-loudness and SciPy-based
oversampled-peak implementation. The peak meter is an estimate, not certified
true-peak conformance. Source documentation:
[pyloudnorm](https://github.com/csteinmetz1/pyloudnorm),
[SciPy correlation conventions](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.correlation_lags.html).
No dependency or core mastering algorithm was changed.

## Persistence, privacy and interruption

Review inputs use opaque asset IDs and the existing input hashes and bounds: no
arbitrary paths, remote links or multichannel downmixing. Up to 10 minutes and
24 million channel samples per file are accepted, subject to the existing rate,
duration and decoder rules. Inputs are rehashed before publication.

`reviews.sqlite3` stores immutable report snapshots and the append-only history of
human decision revisions. Existing control-journal tables are unchanged. Outputs
are grouped in a unique export directory; the asset manifest registers the whole
group atomically. If normal execution fails or is stopped before publication, its
unpublished output directory is removed. A failure to store the review after asset
registration attempts to remove only those new output records and files.

This is not a distributed transaction across SQLite and the filesystem. A hard
process crash or disk failure in the narrow publication interval can leave orphan
outputs/asset records, without a published review. They do not trigger retries or
DAW commands; no automatic crash-time deletion of user files is attempted.

Report files contain your title, opaque IDs and audio hashes, but no local paths,
source filenames, raw session IDs or complete private plans. Titles, notes, hashes
and the review database can still be private. Review exports before sharing and
never commit the workspace or database. The report's historical measurements are
not recomputed when reopened; playback/download verifies stored output hashes.

## MCP

The relay now has 17 tools. `copilot_review_audio` accepts the two asset IDs, a
literal boolean `confirm_same_range=true`, optional title/section duration/verified
run ID, and returns an asynchronous job. Poll `copilot_job` and inspect the report's
status/blockers instead of assuming an accepted pair. The user must supply the
matching-export confirmation; do not manufacture it.

`copilot_reviews` lists the latest 50 review summaries. `copilot_review_get` reads
one by ID. None can record a human listening choice or change the executor's locks,
mode, or authorization. The UI's decision endpoint requires current revision and
never applies a DAW operation. HTTP routes all require the existing bearer token
and same-origin/Host checks.
