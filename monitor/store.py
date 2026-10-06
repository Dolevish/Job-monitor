from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import time

from .models import Job

CLASSIFICATION_VERSION = 2
DETECTION_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key TEXT PRIMARY KEY, source TEXT, company TEXT, title TEXT, url TEXT,
    status TEXT, reason TEXT, first_seen INTEGER, message TEXT, notified INTEGER DEFAULT 0,
    classification_version INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS jobs_source ON jobs(source);
CREATE TABLE IF NOT EXISTS sources (
    source TEXT PRIMARY KEY, first_run INTEGER, last_ok INTEGER,
    failures INTEGER DEFAULT 0, alerted INTEGER DEFAULT 0, last_error TEXT,
    last_count INTEGER, empty_runs INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS detections (
    company TEXT PRIMARY KEY, ats TEXT, board TEXT, ok INTEGER, checked_at INTEGER, note TEXT,
    detector_version INTEGER DEFAULT 1
);
"""


class Store:
    def __init__(self, path: str, snapshot: bool = False):
        if not snapshot and os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(":memory:" if snapshot else path)
        if snapshot and path != ":memory:" and Path(path).exists():
            source = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
            try:
                source.backup(self.db)
            finally:
                source.close()
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(jobs)")}
        for col, decl in (("message", "TEXT"), ("notified", "INTEGER DEFAULT 0"),
                          ("classification_version", "INTEGER DEFAULT 1")):
            if col not in cols:   # DB created by v0.1
                self.db.execute(f"ALTER TABLE jobs ADD COLUMN {col} {decl}")
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(sources)")}
        for col, decl in (("last_count", "INTEGER"), ("empty_runs", "INTEGER DEFAULT 0")):
            if col not in cols:
                self.db.execute(f"ALTER TABLE sources ADD COLUMN {col} {decl}")
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(detections)")}
        if "detector_version" not in cols:
            self.db.execute("ALTER TABLE detections ADD COLUMN detector_version INTEGER DEFAULT 1")

    # --- jobs ---
    def known_ids(self, source: str) -> set[str]:
        # Recover recent reviews omitted by the old baseline policy once, without a reset.
        cutoff = int(time.time()) - 3 * 86400
        rows = self.db.execute("SELECT key FROM jobs WHERE source=? AND NOT "
                               "(status='review' AND notified=0 AND message IS NULL "
                               "AND classification_version<? AND first_seen>=?)",
                               (source, CLASSIFICATION_VERSION, cutoff))
        return {k.split("#", 1)[1] for (k,) in rows}

    def add_job(self, job: Job, status: str, reason: str = "", message: str | None = None) -> None:
        """message != None queues a Telegram message for this job (sent by send_pending)."""
        self.db.execute(
            "INSERT INTO jobs (key, source, company, title, url, status, reason, "
            "first_seen, message, notified, classification_version) VALUES (?,?,?,?,?,?,?,?,?,0,?) "
            "ON CONFLICT(key) DO UPDATE SET title=excluded.title, url=excluded.url, "
            "status=excluded.status, reason=excluded.reason, message=excluded.message, "
            "classification_version=excluded.classification_version "
            "WHERE jobs.classification_version<excluded.classification_version AND jobs.notified=0",
            (job.key, job.source, job.company, job.title, job.url, status, reason,
             int(time.time()), message, CLASSIFICATION_VERSION),
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

    def mark_ok(self, source: str, count: int = 0) -> None:
        now = int(time.time())
        self.db.execute(
            "INSERT INTO sources(source, first_run, last_ok, failures, alerted, last_count, empty_runs) "
            "VALUES (?,?,?,0,0,?,?) "
            "ON CONFLICT(source) DO UPDATE SET last_ok=?, failures=0, alerted=0, "
            "first_run=COALESCE(first_run, ?), last_count=?, "
            "empty_runs=CASE WHEN ?=0 THEN sources.empty_runs+1 ELSE 0 END",
            (source, now, now, count, int(count == 0), now, now, count, count))

    def source_counts(self, source: str) -> tuple[int | None, int]:
        return self.db.execute("SELECT last_count, empty_runs FROM sources WHERE source=?",
                               (source,)).fetchone() or (None, 0)

    def mark_failure(self, source: str, error: str) -> int:
        self.db.execute(
            "INSERT INTO sources(source, failures, last_error) VALUES (?,1,?) "
            "ON CONFLICT(source) DO UPDATE SET failures=failures+1, last_error=?",
            (source, error[:500], error[:500]))
        return self.db.execute("SELECT failures FROM sources WHERE source=?", (source,)).fetchone()[0]

    def should_alert(self, source: str) -> bool:
        row = self.db.execute("SELECT alerted FROM sources WHERE source=?", (source,)).fetchone()
        return bool(row and not row[0])

    def mark_alerted(self, source: str) -> None:
        self.db.execute("UPDATE sources SET alerted=1 WHERE source=?", (source,))

    # --- ATS detections (cache) ---
    def detection(self, company: str):
        return self.db.execute(
            "SELECT ats, board, ok, checked_at, detector_version FROM detections WHERE company=?",
            (company,)).fetchone()

    def save_detection(self, company: str, ats: str | None, board: str | None, note: str = "") -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO detections "
            "(company, ats, board, ok, checked_at, note, detector_version) VALUES (?,?,?,?,?,?,?)",
            (company, ats, board, int(ats is not None), int(time.time()), note, DETECTION_VERSION))

    def commit(self) -> None:
        self.db.commit()

    def close(self) -> None:
        self.db.commit()
        self.db.close()
