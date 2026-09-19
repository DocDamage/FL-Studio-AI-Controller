"""Strict plans. Models may suggest values, never supply executable code."""
from __future__ import annotations
import hashlib
import json
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)

class Operation(Strict):
    kind: Literal["volume", "pan", "rename", "parameter", "load_effect", "mute", "stereo"]
    track: int = Field(ge=0, le=999)
    value: float | str | bool
    slot: int | None = Field(default=None, ge=0, le=9)
    parameter: int | None = Field(default=None, ge=0, le=65535)
    reason: str = Field(default="Explicit user adjustment", max_length=400)

    @model_validator(mode="after")
    def check(self):
        if self.kind in ("rename", "load_effect"):
            if not isinstance(self.value, str) or not self.value.strip():
                raise ValueError("A nonempty exact name is required")
            if len(self.value) > (64 if self.kind == "rename" else 256):
                raise ValueError("Name is too long")
            if any(ord(c) < 32 for c in self.value):
                raise ValueError("Control characters are not allowed")
        elif self.kind == "mute":
            if type(self.value) is not bool:
                raise ValueError("Mute requires an explicit true/false state, not a toggle")
        else:
            if isinstance(self.value, str) or isinstance(self.value, bool):
                raise ValueError("Numeric value required")
            low, high = {"volume":(-60.,6.), "pan":(-1.,1.), "parameter":(0.,1.), "stereo":(-1.,1.)}[self.kind]
            if not low <= self.value <= high:
                raise ValueError(f"{self.kind} must be between {low} and {high}")
        if self.kind == "parameter":
            if self.slot is None or self.parameter is None:
                raise ValueError("Parameter operations require slot and parameter indices")
        elif self.slot is not None or self.parameter is not None:
            raise ValueError("slot and parameter only apply to parameter writes")
        return self

class Locks(Strict):
    master: bool = True
    tracks: tuple[int, ...] = ()
    parameters: bool = False
    # There is intentionally no API to unlock musical content in v0.2.
    tempo: Literal[True] = True
    notes: Literal[True] = True
    arrangement: Literal[True] = True

class Plan(Strict):
    id: str
    created: float
    expires: float
    session: str
    backend: Literal["demo", "postfader"]
    title: str
    operations: tuple[Operation, ...] = Field(min_length=1, max_length=32)
    before: tuple[dict, ...]
    locks: Locks
    purpose: Literal["adjustment", "control_test", "restore"] = "adjustment"
    source_plan_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    warning: str = "No automatic project save or guaranteed rollback."
    @model_validator(mode="after")
    def check(self):
        if len(self.operations) != len(self.before):
            raise ValueError("Every operation requires its own before-state")
        keys = [(o.track, o.kind, o.slot, o.parameter) for o in self.operations]
        if len(keys) != len(set(keys)):
            raise ValueError("One write per target/control per plan")
        if any(o.kind == "load_effect" for o in self.operations) and len(keys) != 1:
            raise ValueError("Plugin insertion must be an isolated plan")
        return self
    @property
    def digest(self):
        return digest(self.model_dump(mode="json"))

class PrepareRequest(Strict):
    operations: tuple[Operation, ...] = Field(min_length=1, max_length=32)
    title: str = Field(default="Review changes", max_length=150)

class Approval(Strict):
    plan_id: str
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm: Literal[True]

class MasterRequest(Strict):
    asset: str = Field(pattern=r"^[a-f0-9]{32}$")
    target_lufs: float = Field(default=-14., ge=-24., le=-9.)
    ceiling_dbtp: float = Field(default=-1., ge=-3., le=-0.5)
    preserve_dynamics: bool = True

class MixRequest(Strict):
    seconds: float = Field(default=10., ge=2., le=60.)
    tracks: tuple[int, ...] = Field(min_length=1, max_length=64)
    target_peak_db: float = Field(default=-9., ge=-18., le=-3.)
    max_cut_db: float = Field(default=6., ge=0.5, le=12.)

class PlanError(RuntimeError):
    pass

class NotDispatched(PlanError):
    """Use only when no project-changing command was attempted."""

class UnknownOutcome(PlanError):
    pass

class Stopped(PlanError):
    pass

def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def public_plan(plan):
    return {**plan.model_dump(mode="json"), "digest":plan.digest,
            "seconds_remaining":max(0,int(plan.expires-time.time()))}
