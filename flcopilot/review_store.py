"""Durable review records and revision-checked human preferences, not DAW actions."""
import json
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

    def close(self):
        with self.lock:
            self.db.close()
