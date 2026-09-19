# Waveform navigation and section looping — unreleased v0.5

Open a technically ready review in **Audio review**, then click **Load verified
waveforms**. The companion reads the original level-matched A/B WAVs, not the raw
before/after bounces. Existing reviews work without rebuilding them, provided the
original report and both audition files are still present and unchanged.

## Navigate and compare

Click either waveform or use the keyboard-accessible **Audition position** slider.
Seeking before the first file loads is preserved. Seeking does not start playback;
use **Play / switch A** or **Play / switch B**. Switching sides retains the approximate
position. A seek made while a file is loading takes precedence over its old position,
and Pause or Stop prevents a pending switch from starting playback later.

Enter **Loop start** and **Loop end**, then **Apply loop range**. The range must lie
inside the file and last at least 0.25 seconds. Alternatively, select a measured
elapsed-time window and click **Use window as loop**. Applying a range seeks to its
start without automatically playing. Both A and B share the same range. The repeat
checkbox disables looping without discarding the selection; **Clear range** removes
it. Editing either bound disables the previous range until the new one is applied.

Stereo channels are drawn separately: L/R are not averaged and cannot cancel each
other visually. Both sides use one shared amplitude scale of at least +/-1 digital
full scale; larger finite peaks expand that common scale. Min/max peaks and RMS
summaries cover every frame, including the final partial bin. A louder-looking
waveform is not an artistic verdict. No visual per-side normalization is applied.

## Evidence and limits

The authenticated `POST /api/review-waveform` endpoint accepts only a saved
`review_id` and an optional integer `bins` from 64 to 2048 (default 800). It runs
through the existing bounded job queue and audio lock. It checks the saved report,
asset identities and file hashes before and after reading the WAVs. Its pathless
result identifies the two audition outputs and their hashes. It does **not** reverify
the original input bounces or establish which FL session produced them.

Reading is bounded to the existing mono/stereo, 8–192 kHz, one-second-to-ten-minute,
24-million-channel-sample limits, at most 65,536 frames per decoder read, and a
300 MiB audio-file bound. Hashing checks Stop and enforces its byte bound while
reading. Non-finite audio, mismatched report identities, changed bytes, missing
outputs, and unsupported formats refuse the entire preview. There is no disk cache,
new audio output, preference update, DAW operation, or additional MCP tool.

Reloading waveforms first clears previous envelopes, loops and cached browser audio
URLs, even when verification fails. Opening another review also clears them. A late
response for an old review cannot populate the new one. Loop settings are temporary,
not saved as decisions or exported in the immutable report. Global Stop pauses this
player, disables repeat, and invalidates an in-flight waveform response.

Playback uses the browser's media element. Loop boundaries and side switches are
**approximate, not gapless or sample-synchronous**; browser scheduling/background
throttling can delay them. There is no crossfade, click-removal, automatic
alignment, beat detection or tempo/key edit. Waveform controls themselves are not
blind; the separate [blind A/B/X check](BLIND_ABX_REVIEW.md) hides audio identity
server-side until the human answers. Canvas repainting is limited to roughly
15 fps during foreground playback; the separate loop check runs on animation and
media time updates. No audio-driver latency or physical listening test is claimed.

## Implementation references

[SoundFile 0.13.1 documentation](https://python-soundfile.readthedocs.io/en/0.13.1/)
describes block reads and explicit dtypes/channels.
[MDN currentTime](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/currentTime)
describes seeking;
[MDN timeupdate](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/timeupdate_event)
documents that update frequency depends on system load. These references explain
implementation constraints, not native FL qualification.
