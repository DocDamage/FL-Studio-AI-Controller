# Plugin workbench — v0.3.0

This workspace controls **already loaded mixer effects** through the single
PostFader-backed executor. It is not a plugin host, stock-effect preset library,
automatic EQ advisor, or evidence that Windows/FL live operation has passed.

## Use it

Inspect the session, open **Plugin workbench**, and select a listed insert/effect.
The UI shows effect slots as 1–10; API requests use zero-based slots 0–9. Parameter
indices are always the raw zero-based indices reported by FL.

Scan a window of 512 or 2,048 indices. Search matches observed names and display
strings within that window only. Use **Next window** while more indices remain.
Padding and unnamed controls are excluded; the UI does not confuse an empty
search window with an empty plugin. It also never calls a partial scan a full map.
The app supports addresses 0–65,535. A reported space beyond that range remains
explicitly incomplete; it is not silently truncated into a complete result.

Select one observed control. Choose a known normalized value (0–1), or displayed
units when an explicit readable unit is available. Supported target units are
`dB`, `Hz`, `ms`, and `percent`. Observations such as `1 kHz`, `0.02 seconds`, and
`50 %` are converted to 1,000 Hz, 20 ms, and 50 percent. Unitless numbers, ratios,
beat divisions, ambiguous decimal-comma displays, and free-form labels are not
interpreted as engineering units.

For displayed units, enter both the target and its maximum readback tolerance.
The companion does not infer a knob curve from its position. PostFader performs
a bounded search, and the executor separately reads the control afterward and
checks its displayed value in the requested units.

**Stop playback and recording in FL before preparing or applying a displayed-unit
change.** The search moves intermediate values. The app checks stopped transport
before planning, again before dispatch, and inside the adapter. It cannot freeze
FL or cancel a command already in flight. Keep hands and other controllers off the
session during the operation. Reachability and successful restoration are not
guaranteed; a failed or ambiguous dispatched search is never automatically retried.

**Prepare change preview** does not apply it. Review the insert, slot, raw index,
plugin/control names, current value, target, tolerance and warning in Session.
Assist/Finish plus explicit approval are still required. Display searches are
isolated to one operation per plan. Master, track and parameter locks still apply.

## Observation and execution boundaries

Each scan issues an observation token with a five-minute lifetime. It binds the
session, captured track/plugin state and returned parameter values. The service
keeps at most 16 observations; expired, evicted and pre-restart tokens are refused.
A preview cannot address a parameter absent from its observation's returned results.
State drift, changed plugin names/counts, malformed or missing raw indices, and
cancellation refuse rather than produce a misleading ready plan.

These observations are **not atomic** or persistent plugin-instance IDs. Same-name
replacement, linked parameters, hidden state, automation and preset internals
cannot be certified unchanged. Ordinary normalized writes keep their existing
numeric-readback contract; display writes verify the displayed destination and do
not claim that a lagging normalized getter has already caught up.

A fully verified display change can receive a separately approved **Preview
restore** in the Run journal. The inverse targets the original displayed value,
in the same unit and tolerance, with fresh before-state checks. It is not FL Undo,
a preset restore, or whole-project rollback.

## MCP / local API

The relay now exposes 14 tools. The new tools are:

- `copilot_plugin_scan`: read-only discovery; returns an asynchronous job. Poll
  `copilot_job`, inspect `has_more` and `next_start`, and retain `observation_id`.
- `copilot_plugin_preview`: binds a proposal to a returned parameter and creates
  another job containing a plan. It cannot change modes, unlock controls or approve.

Example scan arguments (the insert and slot must actually contain a loaded effect):

```json
{"track":6,"slot":0,"start":2048,"max_indices":512,"query":"frequency"}
```

Example preview arguments using the token and index returned by that scan:

```json
{
  "observation_id":"TOKEN_FROM_COMPLETED_SCAN",
  "parameter":2049,
  "mode":"display",
  "value":{"amount":750.0,"unit":"Hz","tolerance":1.0}
}
```

The matching authenticated routes are `POST /api/plugin-scan` and
`POST /api/plugin-preview`. All reads and writes serialize through the existing
executor. The legacy first-page `GET /api/parameters` route remains available,
now with target validation and the same executor lock. No additional MIDI client,
shell surface, public network listener, model weights or dependency was added.

## Simulator and sources

Demo insert 6 contains **Copilot Test Effect (simulated)** with controls at indices
129, 2,049 and 4,097. These deliberately exercise padding, pagination and prefix
conversion. Its linear mappings are fictional test data, not profiles or parameter
indices for Fruity EQ, a real compressor, or any third-party plugin.

The adapter follows the existing pinned PostFader 10.0.0 API, reviewed at commit
`480bedd1cde98fe272c5e02f66efd7aa83315d0b`:
[parameter inspection](https://github.com/synopsys0/postfader-fl-studio-mcp/blob/480bedd1cde98fe272c5e02f66efd7aa83315d0b/fl_studio_mcp/readonly_inspector.py),
[display writer](https://github.com/synopsys0/postfader-fl-studio-mcp/blob/480bedd1cde98fe272c5e02f66efd7aa83315d0b/fl_studio_mcp/verified_writer.py),
and [Image-Line MIDI scripting](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm).
Source-reviewed contract doubles are not an installed-upstream or live-FL test.
