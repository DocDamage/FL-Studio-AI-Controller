# Upgrade v0.1.0 → v0.2.0

This is a cumulative source package. The old ZIP is not needed for a new install.
Actual Windows setup/FL acceptance remains untested in the build environment.

1. Close the old companion and its MCP clients. Save your FL project manually.
2. Extract v0.2.0 into a new normal folder. Keep the old folder until validation.
3. Copy only your existing `local-settings.json` into the new folder. Do not copy
   its `.venv`, `server.json`, launcher token or cached client settings. An editable
   Python install in the old environment still points at the old source.
4. Run `SETUP_WINDOWS.cmd` in the new folder, selecting the live adapter as needed.
5. Test `START_DEMO.cmd`. Then close demo and use `START_LIVE.cmd` with a project copy.
6. In Connection & setup, click Check connection. The pinned PostFader revision is
   unchanged; redeploy through `CONNECT_FL.cmd` only when not configured or when
   diagnostics require a matching bridge deployment/reload.
7. For MCP, rerun `scripts/write_mcp_config.py` using the new `.venv` and replace the
   old client entry yourself after reviewing it. Do not run both versions at once.

The default live workspace is still `%LOCALAPPDATA%\FLStudioAICopilot`; simulator
uses its `demo` subfolder. Existing imports, exports and journal records remain
there. No audio/project migration or deletion is performed. Unused old previews
expire on restart. Interrupted runs stay blocked until inspected and reconciled.

New restoration needs v0.2 captured snapshots. Old v0.1 execution records remain
readable but cannot be upgraded retrospectively into new recovery evidence.

`CHECK_CONNECTION.cmd` now requires the companion to be running and reuses it.
Unlike the old standalone doctor, it does not open another PostFader controller.
No Windows driver, Python runtime, model weights, FL license or VST3 is bundled.
