# Upgrade to v0.4.0

Close the companion and its MCP clients. In an existing checkout, pull `main` with
`git pull --ff-only`, then run `SETUP_WINDOWS.cmd`. For ZIP installations, extract
into a new folder, copy only `local-settings.json`, and run setup. Do not copy the
old virtual environment, authorization descriptor or process-lock files.

Python 3.13, dependency pins, PostFader 10.0.0, bridge revision, and default workspace
locations are unchanged. A bridge redeployment is not required by this milestone.
Existing inputs, exports, control journal and restorable plans retain their data.
Ready change plans still expire on restart. A new separate `reviews.sqlite3` is
created in each selected workspace; it does not migrate or overwrite the control
journal. Demo and live workspaces remain separate.

Start demo or live mode. Audio review works with imported files even when FL is
not connected. Import baseline and candidate bounces in Audio lab, open Audio
review, choose the files, and explicitly confirm matching export settings/range.
Read blockers before expecting audition files. Use the matched A/B files and save
your own preference; this does not alter FL or accept a mix automatically.

Reconnect MCP clients to refresh the tool count to 17. Existing launch commands
remain valid. Approval payloads that incorrectly use numeric `1` must now use the
literal JSON boolean `true`. This change does not convert old stored execution
receipts or change approved plan digests.

See [Audio review](AUDIO_REVIEW.md). Actual FL rendering/capture, native plugin
behavior and end-user Windows installation still require live-host tests.
