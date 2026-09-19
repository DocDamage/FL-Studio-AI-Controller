"""Blind A/B/X review trials use verified matched WAVs and never touch FL."""
import io
import json
import sqlite3

import numpy as np
import pytest
import soundfile as sf
from pydantic import ValidationError

from flcopilot.contracts import PlanError, Stopped
from flcopilot.demo import DemoAdapter
from flcopilot.review_contracts import (
    BlindSessionID, BlindSessionStart, BlindSessionSubmit, BlindTrialID, BlindTrialSubmit,
)
from flcopilot.review_store import ReviewStore
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
    completed = first.review_blind_start({"review_id": review["review_id"]})
    completed = first.review_blind_submit({"trial_id": completed["trial_id"], "guess": "unsure"})
    open_trial = first.review_blind_start({"review_id": review["review_id"]})
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


@pytest.mark.parametrize("trials", [4, 8, 12, 16, 20])
def test_precommitted_session_is_balanced_and_sealed(app, trials):
    review = ready_review(app)
    session = app.review_blind_session_start({"review_id": review["review_id"], "trials": trials})
    assert session["status"] == "open" and session["answers_sealed"] is True
    assert session["planned_trials"] == trials and session["answered_trials"] == 0
    assert session["current_trial"]["ordinal"] == 1
    raw = json.dumps(session)
    for secret in ("mapping", "x_matches", "correct", "a_side", "x_sample", "summary", "trials"):
        assert secret not in raw
    rows = app.reviews.db.execute(
        "SELECT a_side,x_sample FROM review_blind_trials WHERE session_id=? ORDER BY ordinal",
        (session["session_id"],)).fetchall()
    assert len(rows) == trials
    assert sum(row["a_side"] == "baseline" for row in rows) == trials // 2
    assert sum(row["a_side"] == "candidate" for row in rows) == trials // 2
    assert sum(row["x_sample"] == "a" for row in rows) == trials // 2
    assert sum(row["x_sample"] == "b" for row in rows) == trials // 2
    assert not app.adapter.calls and not app.journal.history()


def test_session_answers_stay_sealed_until_final_precommitted_trial(app):
    review = ready_review(app)
    session = app.review_blind_session_start({"review_id": review["review_id"], "trials": 4})
    stored = app.reviews.db.execute(
        "SELECT ordinal,x_sample FROM review_blind_trials WHERE session_id=? ORDER BY ordinal",
        (session["session_id"],)).fetchall()
    for index, row in enumerate(stored, start=1):
        result = app.review_blind_session_submit({
            "session_id": session["session_id"], "guess": row["x_sample"],
        })
        if index < 4:
            assert result["status"] == "open" and result["answers_sealed"] is True
            assert result["answered_trials"] == index and result["current_trial"]["ordinal"] == index + 1
            for secret in ("summary", "trials", "mapping", "correct", "x_matches"):
                assert secret not in result
        else:
            assert result["status"] == "completed" and result["answers_sealed"] is False
            assert result["summary"] == {
                "correct": 4, "incorrect": 0, "unsure": 0, "scored_trials": 4,
                "accuracy": 1.0, "chance_tail_probability": 0.0625,
            }
            assert len(result["trials"]) == 4
            assert all(trial["correct"] is True for trial in result["trials"])
            assert all(set(trial["mapping"]) == {"a", "b", "x"} for trial in result["trials"])
    saved = app.review_get({"review_id": review["review_id"]})
    assert saved["decision"] == "undecided" and saved["revision"] == 1
    assert not app.adapter.calls and not app.adapter.writes


def test_session_unsure_is_excluded_from_descriptive_accuracy(app):
    review = ready_review(app)
    session = app.review_blind_session_start({"review_id": review["review_id"], "trials": 4})
    rows = app.reviews.db.execute(
        "SELECT x_sample FROM review_blind_trials WHERE session_id=? ORDER BY ordinal",
        (session["session_id"],)).fetchall()
    guesses = ["unsure", rows[1]["x_sample"], "a" if rows[2]["x_sample"] == "b" else "b", "unsure"]
    for guess in guesses:
        result = app.review_blind_session_submit({"session_id": session["session_id"], "guess": guess})
    assert result["summary"]["correct"] == 1
    assert result["summary"]["incorrect"] == 1
    assert result["summary"]["unsure"] == 2
    assert result["summary"]["scored_trials"] == 2
    assert result["summary"]["accuracy"] == .5
    assert result["summary"]["chance_tail_probability"] == .75


def test_session_trial_cannot_be_revealed_through_single_trial_endpoint(app):
    review = ready_review(app)
    session = app.review_blind_session_start({"review_id": review["review_id"], "trials": 4})
    current = session["current_trial"]
    assert app.review_blind_file(current["trial_id"], "x").is_file()
    with pytest.raises(PlanError, match="sealed blind session"):
        app.review_blind_submit({"trial_id": current["trial_id"], "guess": "a"})
    still = app.review_blind_session_history({"review_id": review["review_id"]})[0]
    assert still["answered_trials"] == 0 and still["answers_sealed"] is True


def test_only_one_open_blind_work_item_per_review(app):
    review = ready_review(app)
    single = app.review_blind_start({"review_id": review["review_id"]})
    with pytest.raises(PlanError, match="existing blind"):
        app.review_blind_start({"review_id": review["review_id"]})
    with pytest.raises(PlanError, match="existing blind"):
        app.review_blind_session_start({"review_id": review["review_id"], "trials": 4})
    app.review_blind_submit({"trial_id": single["trial_id"], "guess": "unsure"})
    session = app.review_blind_session_start({"review_id": review["review_id"], "trials": 4})
    with pytest.raises(PlanError, match="existing blind"):
        app.review_blind_start({"review_id": review["review_id"]})
    with pytest.raises(PlanError, match="existing blind"):
        app.review_blind_session_start({"review_id": review["review_id"], "trials": 4})
    assert session["status"] == "open"


def test_session_survives_restart_and_keeps_partial_answers_sealed(tmp_path):
    first = Service(tmp_path, DemoAdapter())
    review = ready_review(first)
    session = first.review_blind_session_start({"review_id": review["review_id"], "trials": 4})
    first.review_blind_session_submit({"session_id": session["session_id"], "guess": "unsure"})
    first.close()
    second = Service(tmp_path, DemoAdapter())
    try:
        resumed = second.review_blind_session_history({"review_id": review["review_id"]})[0]
        assert resumed["status"] == "open" and resumed["answered_trials"] == 1
        assert resumed["current_trial"]["ordinal"] == 2 and "summary" not in resumed
        for _ in range(3):
            resumed = second.review_blind_session_submit({
                "session_id": resumed["session_id"], "guess": "unsure",
            })
        assert resumed["status"] == "completed" and resumed["summary"]["unsure"] == 4
        assert resumed["summary"]["scored_trials"] == 0
        assert resumed["summary"]["accuracy"] is None
        assert resumed["summary"]["chance_tail_probability"] is None
        assert second.review_get({"review_id": review["review_id"]})["decision"] == "undecided"
        assert not second.adapter.calls
    finally:
        second.close()


def test_changed_output_blocks_session_answer_without_revealing_anything(app):
    review = ready_review(app)
    session = app.review_blind_session_start({"review_id": review["review_id"], "trials": 4})
    audio = next(row for row in review["files"] if row["kind"] == "audio")
    app.assets.resolve(audio["id"]).write_bytes(b"changed after session start")
    with pytest.raises(PlanError, match="bytes changed"):
        app.review_blind_session_submit({"session_id": session["session_id"], "guess": "a"})
    resumed = app.review_blind_session_history({"review_id": review["review_id"]})[0]
    assert resumed["answered_trials"] == 0 and resumed["answers_sealed"] is True
    assert "summary" not in resumed and "trials" not in resumed


def test_stop_refuses_session_start_and_answer(app):
    review = ready_review(app)
    app.executor.stop()
    with pytest.raises(Stopped):
        app.review_blind_session_start({"review_id": review["review_id"], "trials": 4})
    app.executor.reset_stop()
    session = app.review_blind_session_start({"review_id": review["review_id"], "trials": 4})
    app.executor.stop()
    with pytest.raises(Stopped):
        app.review_blind_session_submit({"session_id": session["session_id"], "guess": "a"})


@pytest.mark.parametrize("payload", [
    {"review_id": "a" * 32, "trials": 3},
    {"review_id": "a" * 32, "trials": 5},
    {"review_id": "a" * 32, "trials": 22},
    {"review_id": "a" * 32, "trials": True},
    {"review_id": "a" * 32, "trials": 8, "extra": 1},
])
def test_blind_session_start_contract_is_strict(payload):
    with pytest.raises(ValidationError):
        BlindSessionStart.model_validate(payload)


@pytest.mark.parametrize("payload", [
    {"session_id": "../private", "guess": "a"},
    {"session_id": "a" * 32, "guess": "candidate"},
    {"session_id": "a" * 32, "guess": True},
    {"session_id": "a" * 32, "guess": "a", "extra": 1},
])
def test_blind_session_submit_contract_is_strict(payload):
    with pytest.raises(ValidationError):
        BlindSessionSubmit.model_validate(payload)


def test_session_public_json_has_no_paths_source_names_or_asset_ids(app):
    review = ready_review(app)
    session = app.review_blind_session_start({"review_id": review["review_id"], "trials": 4})
    raw = json.dumps(session)
    assert str(app.assets.root) not in raw
    assert "private-before" not in raw and "private-after" not in raw
    for row in review["files"]:
        assert row["id"] not in raw


def test_old_single_trial_schema_migrates_without_deleting_history(tmp_path):
    path = tmp_path / "old-reviews.sqlite3"
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE review_blind_trials(
        id TEXT PRIMARY KEY, review_id TEXT NOT NULL, created REAL NOT NULL,
        a_side TEXT NOT NULL, x_sample TEXT NOT NULL, answered REAL,
        guess TEXT, correct INTEGER)""")
    db.execute("INSERT INTO review_blind_trials VALUES(?,?,?,?,?,?,?,?)",
               ("a" * 32, "b" * 32, 1.0, "baseline", "a", 2.0, "a", 1))
    db.commit(); db.close()
    store = ReviewStore(path)
    try:
        columns = {row["name"] for row in store.db.execute("PRAGMA table_info(review_blind_trials)")}
        assert {"session_id", "ordinal"} <= columns
        row = store.db.execute("SELECT * FROM review_blind_trials WHERE id=?", ("a" * 32,)).fetchone()
        assert row["a_side"] == "baseline" and row["correct"] == 1
        assert row["session_id"] is None and row["ordinal"] is None
    finally:
        store.close()
