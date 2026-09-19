"""Known control semantics; unrelated observed changes are not silently adopted."""
from __future__ import annotations
import math
from .contracts import digest

CONTROL_FIELD = {
    "volume": "volume_db", "pan": "pan", "rename": "name",
    "mute": "muted", "stereo": "stereo_separation",
}


def finite_control(value):
    return type(value) in (float, int) and math.isfinite(value)


def verify_unchanged(operation, before, after):
    """Check other captured fields, not all possible state inside FL or a plugin."""
    changed = {
        "volume": {"volume_db", "volume_normalized"},
        "pan": {"pan"}, "rename": {"name"}, "mute": {"muted"},
        "stereo": {"stereo_separation"}, "parameter": set(),
        "load_effect": {"plugins"},
    }[operation.kind]
    old = {key: value for key, value in before.items() if key not in changed}
    new = {key: value for key, value in after.items() if key not in changed}
    if digest(old) != digest(new):
        raise RuntimeError("Other captured track controls changed during the write; inspect before continuing")
