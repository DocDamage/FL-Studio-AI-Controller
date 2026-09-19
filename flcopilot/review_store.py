"""Durable review records and revision-checked human preferences, not DAW actions."""
import json
import math
import secrets
import sqlite3
import threading
import time
from .contracts import PlanError
from .review_contracts import ReviewDecision, ReviewID


class ReviewStore:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS reviews(
                id TEXT PRIMARY KEY, created REAL NOT NULL, report TEXT NOT NULL,
                files TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
                decision TEXT NOT NULL DEFAULT 'undecided', note TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS review_decisions(
                review_id TEXT NOT NULL, revision INTEGER NOT NULL, at REAL NOT NULL,
                decision TEXT NOT NULL, note TEXT NOT NULL,
                PRIMARY KEY(review_id, revision));
            CREATE TABLE IF NOT EXISTS review_blind_trials(
                id TEXT PRIMARY KEY, review_id TEXT NOT NULL, created REAL NOT NULL,
                a_side TEXT NOT NULL, x_sample TEXT NOT NULL, answered REAL,
                guess TEXT, correct INTEGER, session_id TEXT, ordinal INTEGER);
            CREATE TABLE IF NOT EXISTS review_blind_sessions(
                id TEXT PRIMARY KEY, review_id TEXT NOT NULL, created REAL NOT NULL,
                planned_trials INTEGER NOT NULL, completed_at REAL);
            CREATE INDEX IF NOT EXISTS review_blind_trials_review_created
                ON review_blind_trials(review_id, created DESC);
            CREATE INDEX IF NOT EXISTS review_blind_sessions_review_created
                ON review_blind_sessions(review_id, created DESC);
        """)
        # Migration for workspaces created by the first single-trial blind increment.
        columns={row["name"] for row in self.db.execute("PRAGMA table_info(review_blind_trials)")}
        with self.db:
            if "session_id" not in columns:
                self.db.execute("ALTER TABLE review_blind_trials ADD COLUMN session_id TEXT")
            if "ordinal" not in columns:
                self.db.execute("ALTER TABLE review_blind_trials ADD COLUMN ordinal INTEGER")
            self.db.execute("CREATE INDEX IF NOT EXISTS review_blind_trials_session_ordinal "
                            "ON review_blind_trials(session_id, ordinal)")

    def add(self, report, files):
        with self.lock, self.db:
            self.db.execute("INSERT INTO reviews(id,created,report,files) VALUES(?,?,?,?)",
                (report["review_id"], report["created"], json.dumps(report, allow_nan=False),
                 json.dumps(files, allow_nan=False)))
        return self.get(report["review_id"])

    def get(self, ident):
        ReviewID(review_id=ident)
        with self.lock:
            row = self.db.execute("SELECT * FROM reviews WHERE id=?", (ident,)).fetchone()
            if row is None:
                raise PlanError("Unknown audio review")
            return {"review_id": row["id"], "created": row["created"],
                    "report": json.loads(row["report"]), "files": json.loads(row["files"]),
                    "revision": row["revision"], "decision": row["decision"], "note": row["note"],
                    "decision_source": "human", "project_changed": False}

    def history(self):
        with self.lock:
            rows = self.db.execute("SELECT * FROM reviews ORDER BY created DESC LIMIT 50").fetchall()
            return [{"review_id": r["id"], "created": r["created"],
                     "title": json.loads(r["report"])["title"],
                     "status": json.loads(r["report"])["status"], "revision": r["revision"],
                     "decision": r["decision"]} for r in rows]

    def decide(self, request: ReviewDecision):
        with self.lock, self.db:
            current = self.get(request.review_id)
            if current["revision"] != request.expected_revision:
                raise PlanError("Review decision changed; reload it before saving your choice")
            if current["report"]["status"] != "ready" and request.decision in ("prefer_baseline", "prefer_candidate"):
                raise PlanError("This pair did not pass A/B readiness; use needs_revision or undecided")
            revision = current["revision"]+1
            self.db.execute("UPDATE reviews SET revision=?,decision=?,note=? WHERE id=?",
                (revision, request.decision, request.note, request.review_id))
            self.db.execute("INSERT INTO review_decisions VALUES(?,?,?,?,?)",
                (request.review_id, revision, time.time(), request.decision, request.note))
            return self.get(request.review_id)

    @staticmethod
    def _blind_mapping(row):
        b_side = "candidate" if row["a_side"] == "baseline" else "baseline"
        x_side = row["a_side"] if row["x_sample"] == "a" else b_side
        return {"a": row["a_side"], "b": b_side, "x": x_side}

    @staticmethod
    def _chance_tail_probability(correct, scored):
        if scored <= 0:
            return None
        return sum(math.comb(scored, k) for k in range(correct, scored + 1)) / (2 ** scored)

    @staticmethod
    def _blind_public(row):
        result = {"trial_id": row["id"], "review_id": row["review_id"],
                  "created": row["created"], "status": "open" if row["answered"] is None else "completed",
                  "answer_revealed": row["answered"] is not None, "project_changed": False}
        if row["answered"] is None:
            result["note"] = "Reference identities and X are hidden until you submit the trial."
            return result
        result.update({"answered": row["answered"], "guess": row["guess"],
                       "correct": None if row["correct"] is None else bool(row["correct"]),
                       "x_matches": row["x_sample"],
                       "mapping": ReviewStore._blind_mapping(row),
                       "note": "This records one human discrimination attempt, not a preference or quality verdict."})
        return result

    def blind_start(self, review_id):
        from .review_contracts import ReviewID
        ReviewID(review_id=review_id)
        with self.lock, self.db:
            self.get(review_id)
            open_session = self.db.execute(
                "SELECT id FROM review_blind_sessions WHERE review_id=? AND completed_at IS NULL LIMIT 1",
                (review_id,)).fetchone()
            open_trial = self.db.execute(
                "SELECT id FROM review_blind_trials WHERE review_id=? AND session_id IS NULL AND answered IS NULL LIMIT 1",
                (review_id,)).fetchone()
            if open_session is not None or open_trial is not None:
                raise PlanError("Finish the existing blind listening work before starting another trial")
            ident = secrets.token_hex(16)
            created = time.time()
            a_side = "baseline" if secrets.randbits(1) == 0 else "candidate"
            x_sample = "a" if secrets.randbits(1) == 0 else "b"
            self.db.execute(
                "INSERT INTO review_blind_trials(id,review_id,created,a_side,x_sample,session_id,ordinal) "
                "VALUES(?,?,?,?,?,?,?)",
                (ident, review_id, created, a_side, x_sample, None, None))
            row = self.db.execute("SELECT * FROM review_blind_trials WHERE id=?", (ident,)).fetchone()
            return self._blind_public(row)

    def blind_internal(self, trial_id):
        from .review_contracts import BlindTrialID
        BlindTrialID(trial_id=trial_id)
        with self.lock:
            row = self.db.execute("SELECT * FROM review_blind_trials WHERE id=?", (trial_id,)).fetchone()
            if row is None:
                raise PlanError("Unknown blind listening trial")
            return {"trial_id": row["id"], "review_id": row["review_id"], "created": row["created"],
                    "a_side": row["a_side"], "x_sample": row["x_sample"],
                    "answered": row["answered"], "guess": row["guess"],
                    "session_id": row["session_id"], "ordinal": row["ordinal"]}

    def blind_submit(self, request):
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM review_blind_trials WHERE id=?", (request.trial_id,)).fetchone()
            if row is None:
                raise PlanError("Unknown blind listening trial")
            if row["session_id"] is not None:
                raise PlanError("This trial belongs to a sealed blind session; answer through the session")
            if row["answered"] is not None:
                raise PlanError("Blind listening trial already completed")
            correct = None if request.guess == "unsure" else int(request.guess == row["x_sample"])
            self.db.execute(
                "UPDATE review_blind_trials SET answered=?,guess=?,correct=? WHERE id=?",
                (time.time(), request.guess, correct, request.trial_id))
            row = self.db.execute("SELECT * FROM review_blind_trials WHERE id=?", (request.trial_id,)).fetchone()
            return self._blind_public(row)

    def blind_history(self, review_id):
        from .review_contracts import ReviewID
        ReviewID(review_id=review_id)
        with self.lock:
            self.get(review_id)
            rows = self.db.execute(
                "SELECT * FROM review_blind_trials WHERE review_id=? AND session_id IS NULL "
                "ORDER BY created DESC LIMIT 20",
                (review_id,)).fetchall()
            return [self._blind_public(row) for row in rows]

    def _blind_session_public(self, session_id):
        row = self.db.execute("SELECT * FROM review_blind_sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise PlanError("Unknown blind listening session")
        trials = self.db.execute(
            "SELECT * FROM review_blind_trials WHERE session_id=? ORDER BY ordinal",
            (session_id,)).fetchall()
        if len(trials) != row["planned_trials"]:
            raise PlanError("Blind listening session record is incomplete")
        answered = [trial for trial in trials if trial["answered"] is not None]
        completed = len(answered) == row["planned_trials"]
        result = {"session_id": row["id"], "review_id": row["review_id"], "created": row["created"],
                  "planned_trials": row["planned_trials"], "answered_trials": len(answered),
                  "remaining_trials": row["planned_trials"] - len(answered),
                  "status": "completed" if completed else "open",
                  "answers_sealed": not completed, "project_changed": False}
        if not completed:
            current = next(trial for trial in trials if trial["answered"] is None)
            result["current_trial"] = {"trial_id": current["id"], "ordinal": current["ordinal"],
                                       "status": "open", "answer_revealed": False}
            result["note"] = ("All trial mappings and correctness stay sealed until the planned "
                              "session is completed.")
            return result
        correct = sum(trial["correct"] == 1 for trial in answered)
        incorrect = sum(trial["correct"] == 0 for trial in answered)
        unsure = sum(trial["correct"] is None for trial in answered)
        scored = correct + incorrect
        result.update({
            "completed_at": row["completed_at"],
            "summary": {
                "correct": correct, "incorrect": incorrect, "unsure": unsure,
                "scored_trials": scored,
                "accuracy": None if scored == 0 else correct / scored,
                "chance_tail_probability": self._chance_tail_probability(correct, scored),
            },
            "trials": [
                {"ordinal": trial["ordinal"], **self._blind_public(trial)}
                for trial in trials
            ],
            "note": ("Descriptive session result only. The chance-tail value assumes independent "
                     "50/50 trials and is not a claim of a controlled study or statistical significance.")
        })
        return result

    def blind_session_start(self, review_id, planned_trials):
        from .review_contracts import BlindSessionStart
        request = BlindSessionStart(review_id=review_id, trials=planned_trials)
        with self.lock, self.db:
            self.get(request.review_id)
            existing = self.db.execute(
                "SELECT id FROM review_blind_sessions WHERE review_id=? AND completed_at IS NULL "
                "ORDER BY created DESC LIMIT 1", (request.review_id,)).fetchone()
            single = self.db.execute(
                "SELECT id FROM review_blind_trials WHERE review_id=? AND session_id IS NULL "
                "AND answered IS NULL LIMIT 1", (request.review_id,)).fetchone()
            if existing is not None or single is not None:
                raise PlanError("Finish the existing blind listening work before starting another session")
            ident = secrets.token_hex(16)
            created = time.time()
            half = request.trials // 2
            a_sides = ["baseline"] * half + ["candidate"] * half
            x_samples = ["a"] * half + ["b"] * half
            randomizer = secrets.SystemRandom()
            randomizer.shuffle(a_sides)
            randomizer.shuffle(x_samples)
            self.db.execute(
                "INSERT INTO review_blind_sessions(id,review_id,created,planned_trials) VALUES(?,?,?,?)",
                (ident, request.review_id, created, request.trials))
            for ordinal, (a_side, x_sample) in enumerate(zip(a_sides, x_samples), start=1):
                self.db.execute(
                    "INSERT INTO review_blind_trials("
                    "id,review_id,created,a_side,x_sample,session_id,ordinal) VALUES(?,?,?,?,?,?,?)",
                    (secrets.token_hex(16), request.review_id, created, a_side, x_sample, ident, ordinal))
            return self._blind_session_public(ident)

    def blind_session_get(self, session_id):
        from .review_contracts import BlindSessionID
        BlindSessionID(session_id=session_id)
        with self.lock:
            return self._blind_session_public(session_id)

    def blind_session_submit(self, request):
        with self.lock, self.db:
            session = self.db.execute(
                "SELECT * FROM review_blind_sessions WHERE id=?", (request.session_id,)).fetchone()
            if session is None:
                raise PlanError("Unknown blind listening session")
            if session["completed_at"] is not None:
                raise PlanError("Blind listening session already completed")
            trial = self.db.execute(
                "SELECT * FROM review_blind_trials WHERE session_id=? AND answered IS NULL "
                "ORDER BY ordinal LIMIT 1", (request.session_id,)).fetchone()
            if trial is None:
                raise PlanError("Blind listening session has no unanswered trial")
            correct = None if request.guess == "unsure" else int(request.guess == trial["x_sample"])
            self.db.execute(
                "UPDATE review_blind_trials SET answered=?,guess=?,correct=? WHERE id=?",
                (time.time(), request.guess, correct, trial["id"]))
            remaining = self.db.execute(
                "SELECT COUNT(*) AS n FROM review_blind_trials WHERE session_id=? AND answered IS NULL",
                (request.session_id,)).fetchone()["n"]
            if remaining == 0:
                self.db.execute(
                    "UPDATE review_blind_sessions SET completed_at=? WHERE id=?",
                    (time.time(), request.session_id))
            return self._blind_session_public(request.session_id)

    def blind_session_history(self, review_id):
        from .review_contracts import ReviewID
        ReviewID(review_id=review_id)
        with self.lock:
            self.get(review_id)
            rows = self.db.execute(
                "SELECT id FROM review_blind_sessions WHERE review_id=? "
                "ORDER BY created DESC LIMIT 20", (review_id,)).fetchall()
            return [self._blind_session_public(row["id"]) for row in rows]

    def close(self):
        with self.lock:
            self.db.close()
