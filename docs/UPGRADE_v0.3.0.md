# Upgrade to v0.3.0

Close the companion and its MCP clients before updating. Save your FL project
manually. This version does not upgrade PostFader or replace its controller script.

For a Git checkout, pull the new `main` commit and rerun `SETUP_WINDOWS.cmd` to
refresh installed package metadata. Do not commit `local-settings.json` or your
workspace. For a ZIP installation, extract into a new folder, copy only your
existing `local-settings.json`, and run setup. Do not copy `.venv`, `server.json`,
process locks, or tokens from the old installation.

The dependency pins and default workspace locations are unchanged. Existing
imports, exports and journal history remain in those workspaces. Demo and live
journals remain separate. No database migration is required. Old numeric-operation
JSON retains its shape; verified v0.2 control records remain eligible for their
existing captured-control restore checks. Ready plans are expired on app restart.

Start `START_DEMO.cmd`. Open Plugin workbench and use demo insert 6 to test a
read-only scan, then a displayed-value preview and separately approved change and
restore. These controls are explicitly fictional, not real stock-plugin profiles.

For live use, launch `START_LIVE.cmd` and run Connection & setup → Check connection.
Begin with the earlier 1 dB fader test on a saved project copy. Load effects in FL
manually when the experimental menu adapter is unavailable. In Plugin workbench,
scan the actually loaded effect, stop playback/recording, and make one small,
explicit displayed-unit change. Check the FL control and journal receipt yourself.

Existing MCP launch configurations are unchanged. Reconnect the MCP client to
refresh its tool list from 12 to 14 tools. Broad local-model prompts still use the
narrow mixer-control allowlist; they do not invent plugin indices. Use the
workbench or the new MCP scan/preview tools for observed effect parameters.

Read [Plugin workbench](PLUGIN_WORKBENCH.md) and
[Windows acceptance](WINDOWS_ACCEPTANCE.md). Passing core/simulator tests on
Windows is not live FL qualification or proof of audible improvement.
