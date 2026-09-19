"""Blind A/B/X review trials use verified matched WAVs and never touch FL."""
import io
import json

import numpy as np
import pytest
import soundfile as sf
from pydantic import ValidationError

from flcopilot.contracts import PlanError, Stopped
from flcopilot.demo import DemoAdapter
from flcopilot.review_contracts import BlindTrialID, BlindTrialSubmit
from flcopilot.service import Service


@pytest.fixture
def app(tmp_path):
    service = Service(tmp_path, DemoAdapter())
    yield service
    service.close()


def signal(seconds=4, sr=8000):
    t = np.arange(round(seconds * sr)) / sr
    base = np.sin(2 * np.pi * 173 * t) * .04
    detail = np.sin(2 * np.pi * 691 * t) * (.012 + .008 * np.sin(2 * np.pi * .7 * t))
    left = base + detail
    right = base * .83 - detail * .71
    return np.column_stack((left, right)).astype(np.float32)


def upload(app, y, name):
    stream = io.BytesIO()
    sf.write(stream, y, 8000, format="WAV", subtype="FLOAT")
    raw = stream.getvalue()
    return app.assets.import_stream(io.BytesIO(raw), len(raw), name)["id"]


def ready_review(app):
    a = signal()
    # Non-linear but timing-consistent processing stays measurably different after level match.
    b = np.tanh(a * 8) / 8
    return app.review_audio({
        "baseline": upload(app, a, "private-before.wav"),
        "candidate": upload(app, b, "private-after.wav"),
        "confirm_same_range": True,
        "title": "Blind fixture",
    })


def test_open_trial_hides_mapping_and_never_writes_daw(app):
    review = ready_review(app)
    before = app.review_get({"review_id": review["review_id"]})
    trial = app.review_blind_start({"review_id": review["review_id"]})
    assert trial["status"] == "open"
    assert trial["answer_revealed"] is False
    assert trial["project_changed"] is False
    for secret in ("mapping", "x_matches", "guess", "correct", "a_side", "x_sample"):
        assert secret not in trial
    assert app.review_get({"review_id": review["review_id"]}) == before
    assert not app.adapter.calls and not app.adapter.writes and not app.journal.history()


def test_server_mapping_controls_blinded_audio_routes(app, monkeypatch):
    review = ready_review(app)
    import flcopilot.review_store as store
    values = iter((0, 1))  # A=baseline; X=B=candidate.
    monkeypatch.setattr(store.secrets, "randbits", lambda _: next(values))
    trial = app.review_blind_start({"review_id": review["review_id"]})
    a_path = app.review_blind_file(trial["trial_id"], "a")
    b_path = app.review_blind_file(trial["trial_id"], "b")
    x_path = app.review_blind_file(trial["trial_id"], "x")
    assert a_path.name == "A_Baseline_Matched.wav"
    assert b_path.name == "B_Candidate_Matched.wav"
    assert x_path == b_path
    assert a_path != b_path


def test_submit_reveals_answer_once_without_changing_preference(app, monkeypatch):
    review = ready_review(app)
    import flcopilot.review_store as store
    values = iter((0, 1))
    monkeypatch.setattr(store.secrets, "randbits", lambda _: next(values))
    trial = app.review_blind_start({"review_id": review["review_id"]})
    result = app.review_blind_submit({"trial_id": trial["trial_id"], "guess": "b"})
    assert result["status"] == "completed" and result["answer_revealed"] is True
    assert result["correct"] is True and result["x_matches"] == "b"
    assert result["mapping"] == {"a": "baseline", "b": "candidate", "x": "candidate"}
    assert app.review_get({"review_id": review["review_id"]})["decision"] == "undecided"
    assert app.review_get({"review_id": review["review_id"]})["revision"] == 1
    with pytest.raises(PlanError, match="already completed"):
        app.review_blind_submit({"trial_id": trial["trial_id"], "guess": "a"})


def test_unsure_reveals_mapping_but_is_not_scored_correct_or_wrong(app):
    review = ready_review(app)
    trial = app.review_blind_start({"review_id": review["review_id"]})
    result = app.review_blind_submit({"trial_id": trial["trial_id"], "guess": "unsure"})
    assert result["status"] == "completed" and result["correct"] is None
    assert result["guess"] == "unsure" and result["x_matches"] in ("a", "b")
    assert set(result["mapping"]) == {"a", "b", "x"}


def test_blocked_review_cannot_start_blind_trial(app):
    a = signal()
    blocked = app.review_audio({
        "baseline": upload(app, a, "a.wav"),
        "candidate": upload(app, np.zeros_like(a), "b.wav"),
        "confirm_same_range": True,
    })
    assert blocked["report"]["status"] == "blocked"
    with pytest.raises(PlanError, match="ready"):
        app.review_blind_start({"review_id": blocked["review_id"]})
    assert app.review_blind_history({"review_id": blocked["review_id"]}) == []


def test_changed_output_refuses_start_without_persisting_trial(app):
    review = ready_review(app)
    audio = next(row for row in review["files"] if row["kind"] == "audio")
    app.assets.resolve(audio["id"]).write_bytes(b"changed")
    with pytest.raises(PlanError, match="bytes changed"):
        app.review_blind_start({"review_id": review["review_id"]})
    assert app.review_blind_history({"review_id": review["review_id"]}) == []


def test_changed_output_after_start_refuses_playback_and_answer(app):
    review = ready_review(app)
    trial = app.review_blind_start({"review_id": review["review_id"]})
    audio = next(row for row in review["files"] if row["kind"] == "audio")
    app.assets.resolve(audio["id"]).write_bytes(b"changed later")
    with pytest.raises(PlanError, match="bytes changed"):
        app.review_blind_file(trial["trial_id"], "x")
    with pytest.raises(PlanError, match="bytes changed"):
        app.review_blind_submit({"trial_id": trial["trial_id"], "guess": "a"})
    history = app.review_blind_history({"review_id": review["review_id"]})
    assert len(history) == 1 and history[0]["status"] == "open"
    assert "mapping" not in history[0]


@pytest.mark.parametrize("payload", [
    {"trial_id": "../private", "guess": "a"},
    {"trial_id": "a" * 32, "guess": "candidate"},
    {"trial_id": "a" * 32, "guess": True},
    {"trial_id": "a" * 32, "guess": "a", "extra": 1},
])
def test_blind_submit_contract_is_strict(payload):
    with pytest.raises(ValidationError):
        BlindTrialSubmit.model_validate(payload)


@pytest.mark.parametrize("ident", ["../private", "A" * 32, "a" * 31, True, None])
def test_blind_trial_id_contract_is_strict(ident):
    with pytest.raises(ValidationError):
        BlindTrialID(trial_id=ident)


def test_unknown_trial_and_invalid_sample_refused(app):
    review = ready_review(app)
    trial = app.review_blind_start({"review_id": review["review_id"]})
    with pytest.raises(PlanError, match="Unknown"):
        app.review_blind_file("f" * 32, "a")
    with pytest.raises(PlanError, match="must be"):
        app.review_blind_file(trial["trial_id"], "baseline")


def test_open_and_completed_trials_survive_restart_without_leaking_open_mapping(tmp_path):
    first = Service(tmp_path, DemoAdapter())
    review = ready_review(first)
    open_trial = first.review_blind_start({"review_id": review["review_id"]})
    completed = first.review_blind_start({"review_id": review["review_id"]})
    completed = first.review_blind_submit({"trial_id": completed["trial_id"], "guess": "unsure"})
    first.close()
    second = Service(tmp_path, DemoAdapter())
    try:
        history = second.review_blind_history({"review_id": review["review_id"]})
        open_row = next(row for row in history if row["trial_id"] == open_trial["trial_id"])
        done_row = next(row for row in history if row["trial_id"] == completed["trial_id"])
        assert open_row["status"] == "open" and "mapping" not in open_row
        assert done_row["status"] == "completed" and "mapping" in done_row
        assert second.review_get({"review_id": review["review_id"]})["decision"] == "undecided"
        assert not second.adapter.calls
    finally:
        second.close()


def test_stop_refuses_new_trial_and_answer(app):
    review = ready_review(app)
    app.executor.stop()
    with pytest.raises(Stopped):
        app.review_blind_start({"review_id": review["review_id"]})
    app.executor.reset_stop()
    trial = app.review_blind_start({"review_id": review["review_id"]})
    app.executor.stop()
    with pytest.raises(Stopped):
        app.review_blind_submit({"trial_id": trial["trial_id"], "guess": "a"})


def test_public_trial_json_has_no_paths_source_names_or_asset_ids(app):
    review = ready_review(app)
    trial = app.review_blind_start({"review_id": review["review_id"]})
    raw = json.dumps(trial)
    assert str(app.assets.root) not in raw
    assert "private-before" not in raw and "private-after" not in raw
    for row in review["files"]:
        assert row["id"] not in raw
