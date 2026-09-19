"""Durable receipts: intent is committed BEFORE crossing the DAW boundary."""
from __future__ import annotations
import json
import sqlite3
import threading
import time
from pathlib import Path
from .contracts import PlanError

class Journal:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, body TEXT NOT NULL,
                status TEXT NOT NULL, result TEXT, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id TEXT, kind TEXT NOT NULL, body TEXT NOT NULL, at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS flags(name TEXT PRIMARY KEY,value TEXT NOT NULL);
        """)
        with self.lock, self.db:
            count=self.db.execute("SELECT COUNT(*) FROM plans WHERE status='running'").fetchone()[0]
            if count:
                self.db.execute("UPDATE plans SET status='unknown_outcome' WHERE status='running'")
                self._flag("blocked","Interrupted execution; inspect live state and reconcile before any new write.")
            self.db.execute("UPDATE plans SET status='expired' WHERE status='ready'")
    def _flag(self,key,value):
        self.db.execute("INSERT OR REPLACE INTO flags VALUES(?,?)",(key,value))
    def blocked(self):
        with self.lock:
            row=self.db.execute("SELECT value FROM flags WHERE name='blocked'").fetchone()
            return row[0] if row else None
    def block(self,reason):
        with self.lock,self.db:
            self._flag("blocked",reason)
    def reconcile(self,evidence):
        with self.lock,self.db:
            self.db.execute("DELETE FROM flags WHERE name='blocked'")
            self._event(None,"reconciled",evidence)
    def add(self,plan):
        with self.lock,self.db:
            self.db.execute("INSERT INTO plans VALUES(?,?,?,NULL,?)",
                (plan.id,plan.model_dump_json(),"ready",time.time()))
    def claim(self,plan_id):
        with self.lock,self.db:
            cur=self.db.execute("UPDATE plans SET status='running' WHERE id=? AND status='ready'",(plan_id,))
            if cur.rowcount != 1:
                raise PlanError("Plan already consumed, expired, or missing; it will not be replayed.")
    def _event(self,plan_id,kind,body):
        self.db.execute("INSERT INTO events(plan_id,kind,body,at) VALUES(?,?,?,?)",
            (plan_id,kind,json.dumps(body,allow_nan=False),time.time()))
    def event(self,plan_id,kind,body):
        with self.lock,self.db:
            self._event(plan_id,kind,body)
    def finish(self,plan_id,status,result):
        with self.lock,self.db:
            self.db.execute("UPDATE plans SET status=?,result=? WHERE id=?",
                (status,json.dumps(result,allow_nan=False),plan_id))
            if status == "unknown_outcome":
                self._flag("blocked", "An action has an unknown outcome. Inspect and acknowledge before continuing.")
    def get(self,plan_id):
        with self.lock:
            row=self.db.execute("SELECT * FROM plans WHERE id=?",(plan_id,)).fetchone()
            if row is None: raise PlanError("Unknown plan")
            return dict(row)
    def history(self,limit=50):
        with self.lock:
            rows=self.db.execute("SELECT * FROM plans ORDER BY created DESC LIMIT ?",(limit,)).fetchall()
            return [{"id":r["id"],"status":r["status"],"created":r["created"],
                "plan":json.loads(r["body"]),"result":json.loads(r["result"]) if r["result"] else None} for r in rows]
    def close(self):
        with self.lock: self.db.close()
