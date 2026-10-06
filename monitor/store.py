from __future__ import annotations

import os
import sqlite3
import time

from .models import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key TEXT PRIMARY KEY, source TEXT, company TEXT, title TEXT, url TEXT,
    status TEXT, reason TEXT, first_seen INTEGER, message TEXT, notified INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS jobs_source ON jobs(source);
CREATE TABLE IF NOT EXISTS sources (
    source TEXT PRIMARY KEY, first_run INTEGER, last_ok INTEGER,
    failures INTEGER DEFAULT 0, alerted INTEGER DEFAULT 0, last_error TEXT
);
CREATE TABLE IF NOT EXISTS detections (
    company TEXT PRIMARY KEY, ats TEXT, board TEXT, ok INTEGER, checked_at INTEGER, note TEXT
);
"""


class Store:
    def __init__(self, path: str):
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(jobs)")}
        for col, decl in (("message", "TEXT"), ("notified", "INTEGER DEFAULT 0")):
            if col not in cols:   # DB created by v0.1
                self.db.execute(f"ALTER TABLE jobs ADD COLUMN {col} {decl}")

    # --- jobs ---
    def known_ids(self, source: str) -> set[str]:
        rows = self.db.execute("SELECT key FROM jobs WHERE source=?", (source,))
        return {k.split("#", 1)[1] for (k,) in rows}

    def add_job(self, job: Job, status: str, reason: str = "", message: str | None = None) -> None:
        """message != None queues a Telegram message for this job (sent by send_pending)."""
        self.db.execute(
            "INSERT OR IGNORE INTO jobs (key, source, company, title, url, status, reason, "
            "first_seen, message, notified) VALUES (?,?,?,?,?,?,?,?,?,0)",
            (job.key, job.source, job.company, job.title, job.url, status, reason,
             int(time.time()), message),
        )

    # --- outgoing message queue (survives Telegram outages / bad config) ---
    def pending(self, max_age_days: int = 3) -> list[tuple[str, str]]:
        cutoff = int(time.time()) - max_age_days * 86400
        self.db.execute("UPDATE jobs SET notified=-1 WHERE notified=0 AND message IS NOT NULL "
                        "AND first_seen < ?", (cutoff,))   # too old to be news; drop
        return self.db.execute("SELECT key, message FROM jobs WHERE notified=0 AND message IS NOT NULL "
                               "ORDER BY first_seen, rowid").fetchall()

    def mark_notified(self, key: str) -> None:
        self.db.execute("UPDATE jobs SET notified=1 WHERE key=?", (key,))

    # --- sources ---
    def source_seen(self, source: str) -> bool:
        return self.db.execute("SELECT 1 FROM sources WHERE source=? AND first_run IS NOT NULL",
                               (source,)).fetchone() is not None

    def mark_ok(self, source: str) -> None:
        now = int(time.time())
        self.db.execute(
            "INSERT INTO sources(source, first_run, last_ok, failures, alerted) VALUES (?,?,?,0,0) "
            "ON CONFLICT(source) DO UPDATE SET last_ok=?, failures=0, alerted=0, "
            "first_run=COALESCE(first_run, ?)", (source, now, now, now, now))

    def mark_failure(self, source: str, error: str) -> int:
        self.db.execute(
            "INSERT INTO sources(source, failures, last_error) VALUES (?,1,?) "
            "ON CONFLICT(source) DO UPDATE SET failures=failures+1, last_error=?",
            (source, error[:500], error[:500]))
        return self.db.execute("SELECT failures FROM sources WHERE source=?", (source,)).fetchone()[0]

    def should_alert(self, source: str) -> bool:
        row = self.db.execute("SELECT alerted FROM sources WHERE source=?", (source,)).fetchone()
        if row and not row[0]:
            self.db.execute("UPDATE sources SET alerted=1 WHERE source=?", (source,))
            return True
        return False

    # --- ATS detections (cache) ---
    def detection(self, company: str):
        return self.db.execute(
            "SELECT ats, board, ok, checked_at FROM detections WHERE company=?", (company,)).fetchone()

    def save_detection(self, company: str, ats: str | None, board: str | None, note: str = "") -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO detections VALUES (?,?,?,?,?,?)",
            (company, ats, board, int(ats is not None), int(time.time()), note))

    def commit(self) -> None:
        self.db.commit()

    def close(self) -> None:
        self.db.commit()
        self.db.close()
