# Verified-control restoration

The Run journal's **Preview restore** is a new proposed adjustment. It is not FL
Undo, an FLP backup restore, an automatic rollback, or an action performed after a
failure without asking.

## Successful path

A source run must have completed with status `verified`, one verified receipt per
operation, the same adapter/session, and expanded v0.2 after-state snapshots. Only
fader, pan, rename, mute, stereo separation and captured loaded-effect parameters
are eligible. Plugin insertion is not automatically reversible.

The service reconstructs the final captured state per track and parameter, then
builds inverse operations using the original captured values. An internal anchor
is checked during new-plan preparation; a drifted target does not create a ready
restore plan. The normal executor checks again when the user approves. Current
master/track/parameter locks, five-minute expiry, Stop, uncertain-outcome block,
write-gate ownership and independent readback all remain active.

Open Run journal → Preview restore, review the exact old/current values, then
approve in Assist/Finish. Nothing moves merely by opening the preview. A result
can still be uncertain: the app stops and preserves evidence rather than making
another guess. A completed restore itself has a journal record.

## Refusals

Changed session, changed captured controls or parameter identity/value, protected
targets, unverified/partial/interrupted source runs, legacy incomplete snapshots,
and plugin insertion all refuse. A reconciliation acknowledgment clears the write
block, but does not make an uncertain source run verified or restorable.

## Evidence boundary

Snapshots are non-atomic. Readable names/indices are not persistent unique IDs.
An indistinguishable plugin replacement can defeat that identity check; hidden
state, automation, MIDI, routing, arrangements and audio are not restored. Save
project versions manually and avoid simultaneous edits/other controllers. Even a
technically verified inverse write does not establish that the music sounds right.
