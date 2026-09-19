"""Compensating-control previews, never a promise to roll back the whole project."""
from __future__ import annotations
import json
from .contracts import DisplayTarget, Operation, Plan, PlanError, PrepareRequest, digest
from .controls import CONTROL_FIELD
from .executor import stable_track


def prepare_restore(executor, plan_id: str):
    """Invert one fully verified run only while its captured final state still holds."""
    with executor.mutex:
        if executor.journal.blocked():
            raise PlanError("Resolve the uncertain outcome before preparing a restore")
        row = executor.journal.get(plan_id)
        source = Plan.model_validate_json(row["body"])
        result = json.loads(row["result"]) if row["result"] else {}
        receipts = result.get("receipts", [])
        if row["status"] != "verified" or result.get("status") != "verified":
            raise PlanError("Only fully verified runs can receive a restore preview")
        if len(receipts) != len(source.operations):
            raise PlanError("Complete per-operation receipts are required")
        if source.backend != executor.adapter.name:
            raise PlanError("Restore belongs to a different backend")
        if any(op.kind == "load_effect" for op in source.operations):
            raise PlanError("Plugin insertion cannot be restored automatically; use FL manually")
        final_tracks = {}
        final_parameters = {}
        for op, receipt in zip(source.operations, receipts):
            if (digest(receipt.get("operation")) != digest(op.model_dump(mode="json"))
                    or receipt.get("receipt", {}).get("verified") is not True
                    or receipt["receipt"].get("session_fingerprint") != source.session):
                raise PlanError("Source receipts do not match the original plan")
            after = receipt["after"]
            if "stereo_separation" not in after["track"]:
                raise PlanError("This older run lacks v0.2 control snapshots; prepare a new inspected adjustment instead")
            final_tracks[op.track] = after["track"]
            if op.kind in ("parameter", "parameter_display"):
                final_parameters[(op.track, op.slot, op.parameter)] = after["parameter"]
        operations, anchors = [], []
        for op, before in reversed(tuple(zip(source.operations, source.before))):
            if op.kind == "parameter_display":
                from .units import display_in_unit
                value = DisplayTarget(amount=display_in_unit(before["parameter"].get("display"),op.value.unit),
                    unit=op.value.unit,tolerance=op.value.tolerance)
            else:
                value = (before["parameter"]["value"] if op.kind == "parameter"
                         else before["track"].get(CONTROL_FIELD[op.kind]))
            if value is None:
                raise PlanError("Original control value was not captured; restore is unavailable")
            inverse = Operation(kind=op.kind, track=op.track, value=value, slot=op.slot,
                                parameter=op.parameter, reason="Restore a captured value from verified run " + source.id)
            anchor = {"track": final_tracks[op.track]}
            if op.kind in ("parameter", "parameter_display"):
                anchor["parameter"] = final_parameters[(op.track, op.slot, op.parameter)]
            operations.append(inverse)
            anchors.append(anchor)
        # The executor checks every anchor while building the plan, before storing
        # it. A changed track/session/parameter never creates an executable plan.
        prepared = executor.prepare(
            PrepareRequest(title="Restore controls · " + source.title[:110], operations=tuple(operations)),
            expected_session=source.session, expected_before=tuple(anchors),
            purpose="restore", source_plan_id=source.id,
        )
        return {"plan": prepared, "source_plan_id": source.id,
                "project_rollback": False,
                "warning": "This restores only listed captured controls. It is a new approved write, not FL Undo or a project restore."}


def prepare_control_test(executor, track: int):
    """Prepare exactly a 1 dB reduction; a separate restore approval completes it."""
    if type(track) is not int or not 1 <= track <= 999:
        raise PlanError("Choose a non-master mixer insert (1–999)")
    with executor.mutex:
        snapshot = executor.adapter.snapshot()
        tracks = [t for t in snapshot["tracks"] if t["index"] == track]
        if len(tracks) != 1:
            raise PlanError("Control-test insert is absent or ambiguous")
        current = tracks[0].get("volume_db")
        if type(current) not in (int, float) or not -59 <= current <= 6:
            raise PlanError("Control test needs a readable fader at -59 to +6 dB")
        return executor.prepare(
            PrepareRequest(title="1 dB control test · insert " + str(track),
                           operations=(Operation(kind="volume", track=track, value=float(current)-1.,
                                                 reason="Explicit Windows control qualification test"),)),
            expected_session=snapshot["session"], expected_before=({"track": stable_track(tracks[0])},),
            purpose="control_test",
        )
