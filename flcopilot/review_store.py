"""Durable review records and revision-checked human preferences, not DAW actions."""
import json
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
                guess TEXT, correct INTEGER);
            CREATE INDEX IF NOT EXISTS review_blind_trials_review_created
                ON review_blind_trials(review_id, created DESC);
        """)

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
    def _blind_public(row):
        result = {"trial_id": row["id"], "review_id": row["review_id"],
                  "created": row["created"], "status": "open" if row["answered"] is None else "completed",
                  "answer_revealed": row["answered"] is not None, "project_changed": False}
        if row["answered"] is None:
            result["note"] = "Reference identities and X are hidden until you submit the trial."
            return result
        b_side = "candidate" if row["a_side"] == "baseline" else "baseline"
        x_side = row["a_side"] if row["x_sample"] == "a" else b_side
        result.update({"answered": row["answered"], "guess": row["guess"],
                       "correct": None if row["correct"] is None else bool(row["correct"]),
                       "x_matches": row["x_sample"],
                       "mapping": {"a": row["a_side"], "b": b_side, "x": x_side},
                       "note": "This records one human discrimination attempt, not a preference or quality verdict."})
        return result

    def blind_start(self, review_id):
        from .review_contracts import ReviewID
        ReviewID(review_id=review_id)
        with self.lock, self.db:
            self.get(review_id)
            ident = secrets.token_hex(16)
            created = time.time()
            a_side = "baseline" if secrets.randbits(1) == 0 else "candidate"
            x_sample = "a" if secrets.randbits(1) == 0 else "b"
            self.db.execute(
                "INSERT INTO review_blind_trials(id,review_id,created,a_side,x_sample) VALUES(?,?,?,?,?)",
                (ident, review_id, created, a_side, x_sample))
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
                    "answered": row["answered"], "guess": row["guess"]}

    def blind_submit(self, request):
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM review_blind_trials WHERE id=?", (request.trial_id,)).fetchone()
            if row is None:
                raise PlanError("Unknown blind listening trial")
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
                "SELECT * FROM review_blind_trials WHERE review_id=? ORDER BY created DESC LIMIT 20",
                (review_id,)).fetchall()
            return [self._blind_public(row) for row in rows]

    def close(self):
        with self.lock:
            self.db.close()
