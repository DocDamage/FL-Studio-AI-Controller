"""Conservative display-unit parsing; never infer units from a parameter name."""
from __future__ import annotations
import math
import re
from .contracts import NotDispatched

# Canonical targets use base units. Prefix conversion happens only on observed text.
UNITS = {"db": ("dB", 1.), "hz": ("Hz", 1.), "khz": ("Hz", 1000.),
         "ms": ("ms", 1.), "s": ("ms", 1000.), "sec": ("ms", 1000.),
         "second": ("ms", 1000.), "seconds": ("ms", 1000.),
         "%": ("percent", 1.), "percent": ("percent", 1.)}
DISPLAY_PATTERN = re.compile(r"\s*([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))\s*([A-Za-z%]+)\s*")


def parse_display(text):
    """Return (amount, canonical unit), refusing labels, ratios and ambiguous locales."""
    if not isinstance(text, str) or len(text) > 256:
        raise NotDispatched("A bounded numeric display with explicit units is required")
    match = DISPLAY_PATTERN.fullmatch(text)
    if not match or match[2].lower() not in UNITS:
        raise NotDispatched("Display is not an unambiguous dB, Hz/kHz, ms/seconds or percent value")
    unit, scale = UNITS[match[2].lower()]
    value = float(match[1]) * scale
    if not math.isfinite(value):
        raise NotDispatched("Display value must be finite")
    return value, unit


def display_in_unit(text, unit):
    value, observed_unit = parse_display(text)
    if observed_unit != unit:
        raise NotDispatched("Displayed units do not match the requested target")
    return value


def require_display_ready(adapter):
    """A solver moves intermediate values. Do not start it during playback/recording."""
    if adapter.connection().get("plugin_display_units") is not True:
        raise NotDispatched("The bridge has not advertised display-unit control")
    transport = adapter.transport_state()
    if not isinstance(transport, dict) or transport.get("playing") is not False or transport.get("recording") is not False:
        raise NotDispatched("Stop playback and recording in FL before a display-value search; unknown transport is refused")
