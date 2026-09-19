"""Read-only bounded discovery and observation-bound parameter previews."""
from __future__ import annotations
from collections import OrderedDict
import time
import uuid
from typing import Literal
from pydantic import Field
from .contracts import DisplayTarget, NotDispatched, Operation, PrepareRequest, Stopped, Strict, digest
from .controls import finite_control
from .executor import stable_track
from .units import parse_display

ADDRESS_LIMIT = 65536
OBSERVATION_SECONDS = 300
MAX_OBSERVATIONS = 16


class ScanRequest(Strict):
    track: int = Field(ge=0, le=999)
    slot: int = Field(ge=0, le=9)
    start: int = Field(default=0, ge=0, lt=ADDRESS_LIMIT)
    max_indices: int = Field(default=512, ge=1, le=2048)
    query: str = Field(default="", max_length=80)


class ParameterPreview(Strict):
    observation_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    parameter: int = Field(ge=0, lt=ADDRESS_LIMIT)
    mode: Literal["normalized", "display"] = "normalized"
    value: float | DisplayTarget


def _integer(value, label, low=0):
    if type(value) is not int or value < low:
        raise NotDispatched("Invalid parameter page " + label)
    return value


def _target(track, slot):
    plugins = [p for p in track.get("plugins", []) if p.get("slot_index") == slot]
    if len(plugins) != 1 or not isinstance(plugins[0].get("name"), str) or not plugins[0]["name"].strip():
        raise NotDispatched("Choose one uniquely observed loaded effect slot")
    return plugins[0]["name"]


def _rows(page, request, cursor, limit, plugin):
    """Do not treat a partial/malformed page as a complete parameter map."""
    identity = page.get("plugin", {})
    if (identity.get("name") != plugin or identity.get("track_index") != request.track
            or identity.get("slot_index") != request.slot):
        raise NotDispatched("Plugin page belongs to a different target")
    total = _integer(page.get("reported_parameter_count"), "count")
    count = min(limit, max(0, total-cursor))
    if _integer(page.get("offset"), "offset") != cursor or _integer(page.get("scanned_count"), "scanned count") != count:
        raise NotDispatched("Parameter page coverage contradicts the requested range")
    rows = page.get("parameters")
    if not isinstance(rows, list) or len(rows) != count:
        raise NotDispatched("Parameter page omitted raw indices; completeness cannot be established")
    if any(type(row) is not dict or type(row.get("index")) is not int for row in rows):
        raise NotDispatched("Malformed parameter indices")
    if sorted(row["index"] for row in rows) != list(range(cursor, cursor+count)):
        raise NotDispatched("Duplicate or out-of-range parameter indices")
    return total, count, rows


def _control(row):
    name, text, value = row.get("reported_name"), row.get("display_text"), row.get("normalized_value")
    if not isinstance(name, str) or len(name) > 512 or (text is not None and (not isinstance(text, str) or len(text) > 256)):
        raise NotDispatched("Malformed parameter name or display")
    if value is not None and (not finite_control(value) or not 0 <= value <= 1):
        raise NotDispatched("Invalid normalized parameter readback")
    if row.get("classification") == "padding_candidate" or not name.strip():
        return None
    try:
        amount, unit = parse_display(text)
    except NotDispatched:
        amount, unit = None, None
    return {"index": row["index"], "name": name, "normalized": value, "display": text,
            "amount": amount, "unit": unit, "can_normalized": value is not None,
            "can_display": value is not None and unit is not None}


class PluginWorkbench:
    def __init__(self, executor):
        self.executor = executor
        # Tokens contain observed state, not approval. No file paths or arbitrary code.
        self.observations = OrderedDict()

    def _prune(self):
        now = time.monotonic()
        for key in list(self.observations):
            if self.observations[key]["deadline"] <= now:
                del self.observations[key]

    def scan(self, request: ScanRequest):
        with self.executor.mutex:
            adapter = self.executor.adapter
            if self.executor.stop_event.is_set():
                raise Stopped("Parameter scan cancelled by the latched stop")
            connection = adapter.connection()
            session = connection.get("session_fingerprint")
            if not session or connection.get("connected") is not True or connection.get("compatible") is not True:
                raise NotDispatched("No compatible observed session")
            before = stable_track(adapter.track(request.track))
            plugin = _target(before, request.slot)
            cursor, total, controls, excluded = request.start, None, [], 0
            bound = min(request.start+request.max_indices, ADDRESS_LIMIT)
            while cursor < bound:
                if self.executor.stop_event.is_set():
                    raise Stopped("Parameter scan cancelled; no parameter was changed")
                if adapter.connection().get("session_fingerprint") != session:
                    raise NotDispatched("Session changed during the parameter scan")
                limit = min(128, bound-cursor)
                page = adapter.parameter_page(request.track, request.slot, cursor, limit)
                observed_total, count, rows = _rows(page, request, cursor, limit, plugin)
                if total is not None and total != observed_total:
                    raise NotDispatched("Parameter count changed during scan")
                total = observed_total
                if request.start > total:
                    raise NotDispatched("Start index is beyond this plugin's reported parameter range")
                for row in rows:
                    control = _control(row)
                    if control is None:
                        excluded += 1
                    elif request.query.casefold() in (control["name"]+" "+(control["display"] or "")).casefold():
                        control["can_display"] &= connection.get("plugin_display_units") is True
                        controls.append(control)
                cursor += count
                if not count or cursor >= total:
                    break
            if (adapter.connection().get("session_fingerprint") != session
                    or digest(stable_track(adapter.track(request.track))) != digest(before)):
                raise NotDispatched("Session or captured mixer/plugin state changed during scan")
            if self.executor.stop_event.is_set():
                raise Stopped("Parameter scan cancelled before publication")
            self._prune()
            token = uuid.uuid4().hex
            self.observations[token] = {"deadline": time.monotonic()+OBSERVATION_SECONDS,
                "session": session, "before": before, "track": request.track, "slot": request.slot,
                "plugin": plugin, "controls": {c["index"]: c for c in controls}}
            while len(self.observations) > MAX_OBSERVATIONS:
                self.observations.popitem(last=False)
            has_more = cursor < total
            return {"observation_id": token, "expires": time.time()+OBSERVATION_SECONDS,
                "session": session, "track": request.track, "slot": request.slot, "plugin": plugin,
                "query": request.query, "start": request.start, "end_exclusive": cursor,
                "reported_count": total, "examined_count": cursor-request.start,
                "excluded_unnamed_or_padding": excluded, "parameters": controls,
                "complete": request.start == 0 and cursor >= total,
                "has_more": has_more, "next_start": cursor if has_more and cursor < ADDRESS_LIMIT else None,
                "address_limit_reached": has_more and cursor >= ADDRESS_LIMIT,
                "demo": adapter.name == "demo", "project_changed": False,
                "observation_atomic": False,
                "warnings": ["Search covers only this explicit index window. Continue scanning when has_more is true.",
                    "Names and slot indices are not persistent plugin-instance IDs; hidden state is not inspected.",
                    "Display-value searches move intermediate settings and require stopped playback/recording."]}

    def preview(self, request: ParameterPreview):
        with self.executor.mutex:
            self._prune()
            observation = self.observations.get(request.observation_id)
            if observation is None:
                raise NotDispatched("Observation expired, was evicted, or belongs to an earlier app process; scan again")
            control = observation["controls"].get(request.parameter)
            if control is None:
                raise NotDispatched("Parameter was not present in this scan's returned results")
            display = request.mode == "display"
            if not control["can_display" if display else "can_normalized"]:
                raise NotDispatched("This parameter lacks the required numeric readback")
            if display and (not isinstance(request.value, DisplayTarget) or request.value.unit != control["unit"]):
                raise NotDispatched("Use the explicitly observed unit for this display target")
            if not display and not finite_control(request.value):
                raise NotDispatched("Normalized mode requires a numeric value")
            op = Operation(kind="parameter_display" if display else "parameter",
                track=observation["track"], slot=observation["slot"], parameter=request.parameter,
                value=request.value, reason="Explicit plugin-workbench adjustment: " + control["name"][:200])
            parameter = {"plugin": observation["plugin"], "name": control["name"], "value": control["normalized"]}
            if display:
                parameter["display"] = control["display"]
            plan = self.executor.prepare(PrepareRequest(title=("Adjust " + control["name"])[:150], operations=(op,)),
                expected_session=observation["session"],
                expected_before=({"track": observation["before"], "parameter": parameter},))
            return {"plan": plan, "observation_id": request.observation_id, "project_changed": False}
