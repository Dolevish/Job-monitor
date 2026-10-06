from __future__ import annotations

import os
import sqlite3
import time

from .models import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key TEXT PRIMARY KEY, source TEXT, company TEXT, title TEXT, url TEXT,
    status TEXT, reason TEXT, first_seen INTEGER
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

    # --- jobs ---
    def known_ids(self, source: str) -> set[str]:
        rows = self.db.execute("SELECT key FROM jobs WHERE source=?", (source,))
        return {k.split("#", 1)[1] for (k,) in rows}

    def add_job(self, job: Job, status: str, reason: str = "") -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO jobs VALUES (?,?,?,?,?,?,?,?)",
            (job.key, job.source, job.company, job.title, job.url, status, reason, int(time.time())),
        )

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
