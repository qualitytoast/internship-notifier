"""SQLite storage: every job ever seen, run history, per-company health and cross-check state."""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Job, Match

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  company TEXT NOT NULL,
  job_id TEXT NOT NULL,
  title TEXT NOT NULL,
  location TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL DEFAULT '',
  posted TEXT,
  department TEXT NOT NULL DEFAULT '',
  employment_type TEXT NOT NULL DEFAULT '',
  snippet TEXT NOT NULL DEFAULT '',
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  removed_at TEXT,                    -- absent from a healthy listing; cleared if it comes back
  reappeared INTEGER NOT NULL DEFAULT 0,
  student INTEGER NOT NULL DEFAULT 0, -- passes the role-type rule (intern/co-op/…)
  matched INTEGER NOT NULL DEFAULT 0, -- passes every rule (what gets emailed)
  unsure INTEGER NOT NULL DEFAULT 0,
  term TEXT, field TEXT, tags TEXT, reasons TEXT,
  repost_of TEXT,                     -- earlier job id with the same title + location
  notified_at TEXT,                   -- sent in a new-posting email or the first-run summary
  source TEXT NOT NULL DEFAULT 'checker',
  alt_ids TEXT NOT NULL DEFAULT '[]',     -- other ids for the same posting (requisition / ATS ids)
  baseline INTEGER NOT NULL DEFAULT 0,    -- already open when the company was first seeded (never "new")
  PRIMARY KEY (company, job_id)
);
CREATE INDEX IF NOT EXISTS jobs_first_seen ON jobs(first_seen);
CREATE INDEX IF NOT EXISTS jobs_title ON jobs(company, title);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL, finished_at TEXT, status TEXT,
  checked INTEGER DEFAULT 0, failed INTEGER DEFAULT 0, new_matches INTEGER DEFAULT 0, note TEXT
);

CREATE TABLE IF NOT EXISTS checks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER, company TEXT NOT NULL, started_at TEXT NOT NULL, duration REAL,
  status TEXT NOT NULL,               -- ok | error | anomaly | blocked
  error_kind TEXT, error TEXT,
  jobs INTEGER, students INTEGER, new_jobs INTEGER, new_matches INTEGER, requests INTEGER
);
CREATE INDEX IF NOT EXISTS checks_company ON checks(company, started_at);

CREATE TABLE IF NOT EXISTS company_state (
  company TEXT PRIMARY KEY,
  seeded_at TEXT,
  last_attempt TEXT, last_success TEXT, next_due TEXT, last_full TEXT,
  last_count INTEGER, baseline_count INTEGER,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  failing_since TEXT, last_error TEXT, last_error_kind TEXT,
  anomaly_streak INTEGER NOT NULL DEFAULT 0,
  alert_open INTEGER NOT NULL DEFAULT 0, last_alert_at TEXT
);

CREATE TABLE IF NOT EXISTS simplify_rows (
  source TEXT NOT NULL, row_key TEXT NOT NULL,
  company TEXT, title TEXT, location TEXT, url TEXT, category TEXT, terms TEXT, age TEXT,
  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
  tracked_company TEXT,
  status TEXT NOT NULL DEFAULT 'baseline', -- baseline | pending | found | filtered | missed | untracked | via_simplify
  resolved_at TEXT, note TEXT, digest_at TEXT, alerted_at TEXT,
  PRIMARY KEY (source, row_key)
);

CREATE TABLE IF NOT EXISTS emails (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT, subject TEXT, created_at TEXT, sent_at TEXT, error TEXT, path TEXT
);

CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime | None = None) -> str:
    return (dt or utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


class DB:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=60, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(jobs)")}
        if "baseline" not in cols:  # databases created before this column existed
            self.conn.execute("ALTER TABLE jobs ADD COLUMN baseline INTEGER NOT NULL DEFAULT 0")
            self.conn.execute("UPDATE jobs SET baseline=1 WHERE first_seen=(SELECT seeded_at FROM company_state "
                              "WHERE company_state.company=jobs.company)")

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def tx(self):
        if self.conn.in_transaction:  # inside an outer transaction (one company's whole update): join it
            yield self.conn
            return
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def q(self, sql: str, *args) -> list[sqlite3.Row]:
        return self.conn.execute(sql, args).fetchall()

    def one(self, sql: str, *args) -> sqlite3.Row | None:
        return self.conn.execute(sql, args).fetchone()

    # key/value -------------------------------------------------------------------------------
    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.one("SELECT value FROM kv WHERE key=?", key)
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self.conn.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          (key, value))

    # jobs ------------------------------------------------------------------------------------
    def known_ids(self, company: str) -> set[str]:
        return {r["job_id"] for r in self.q("SELECT job_id FROM jobs WHERE company=?", company)}

    def job(self, company: str, job_id: str) -> sqlite3.Row | None:
        return self.one("SELECT * FROM jobs WHERE company=? AND job_id=?", company, job_id)

    def upsert_jobs(self, company: str, jobs: list[Job], now: str) -> tuple[list[str], dict[str, sqlite3.Row]]:
        """Insert unseen jobs, refresh seen ones. Returns (new_ids, recheck): recheck maps each known job that
        doesn't match and came back after being removed, or was edited (a new title, location or employment type;
        an empty value in the listing is not an edit), to its row before this update, so the filters can look at it
        again with the best details known (a listing's "3 Locations" vs the real ones read from the job page)."""
        new, recheck = [], {}
        existing = {r["job_id"]: r for r in self.q(
            "SELECT job_id, removed_at, title, location, department, employment_type, snippet, matched FROM jobs"
            " WHERE company=?", company)}
        with self.tx() as c:
            for j in jobs:
                row = existing.get(j.id)
                if row is None:
                    c.execute(
                        "INSERT INTO jobs(company, job_id, title, location, url, posted, department, employment_type,"
                        " snippet, first_seen, last_seen, alt_ids) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (company, j.id, j.title, j.location, j.url, j.posted, j.department, j.employment_type,
                         j.snippet, now, now, json.dumps(j.extra.get("alt_ids", []))))
                    new.append(j.id)
                else:
                    edited = (j.title or "") != (row["title"] or "") or any(
                        new_v and new_v != (old_v or "") for new_v, old_v in
                        ((j.location, row["location"]), (j.employment_type, row["employment_type"])))
                    if not row["matched"] and (row["removed_at"] or edited):
                        recheck[j.id] = row
                    c.execute(
                        "UPDATE jobs SET title=?, location=?, url=?, posted=COALESCE(?, posted), department=?,"
                        " employment_type=?, snippet=CASE WHEN ?<>'' THEN ? ELSE snippet END, last_seen=?,"
                        " removed_at=NULL, reappeared=reappeared + ? WHERE company=? AND job_id=?",
                        (j.title, j.location, j.url, j.posted, j.department, j.employment_type, j.snippet,
                         j.snippet, now, 1 if row["removed_at"] else 0, company, j.id))
        return new, recheck

    def mark_removed(self, company: str, seen_ids: set[str], now: str) -> int:
        open_ids = {r["job_id"] for r in self.q(
            "SELECT job_id FROM jobs WHERE company=? AND removed_at IS NULL AND source='checker'", company)}
        gone = open_ids - seen_ids
        with self.tx() as c:
            c.executemany("UPDATE jobs SET removed_at=? WHERE company=? AND job_id=?",
                          [(now, company, jid) for jid in gone])
        return len(gone)

    def set_match(self, company: str, job_id: str, m: Match, student: bool) -> None:
        self.conn.execute(
            "UPDATE jobs SET student=?, matched=?, unsure=?, term=?, field=?, tags=?, reasons=? WHERE company=? AND job_id=?",
            (int(student), int(m.matched), int(m.unsure), m.term, m.field, json.dumps(m.tags),
             json.dumps(m.reasons), company, job_id))

    def set_student(self, company: str, job_ids: list[str], student: bool) -> None:
        self.conn.executemany("UPDATE jobs SET student=? WHERE company=? AND job_id=?",
                              [(int(student), company, j) for j in job_ids])

    def find_repost(self, company: str, job_id: str, title: str, location: str) -> str | None:
        """An older job (different id) with the same title and location means this is a repost."""
        t = norm_title(title)
        for r in self.q("SELECT job_id, title, location FROM jobs WHERE company=? AND job_id<>? "
                        "ORDER BY first_seen", company, job_id):
            if norm_title(r["title"]) == t and (r["location"] or "") == (location or ""):
                return r["job_id"]
        return None

    def simplify_twin(self, company: str, title: str) -> str | None:
        """An open job learned from the SimplifyJobs cross-check (checker down) with the same title, already emailed."""
        t = norm_title(title)
        for r in self.q("SELECT job_id, title FROM jobs WHERE company=? AND source='simplify' AND removed_at IS NULL "
                        "AND notified_at IS NOT NULL", company):
            if norm_title(r["title"]) == t:
                return r["job_id"]
        return None

    def set_repost(self, company: str, job_id: str, of: str) -> None:
        self.conn.execute("UPDATE jobs SET repost_of=? WHERE company=? AND job_id=?", (of, company, job_id))

    def unnotified_matches(self) -> list[sqlite3.Row]:
        return self.q("SELECT * FROM jobs WHERE matched=1 AND notified_at IS NULL AND removed_at IS NULL "
                      "ORDER BY company, title")

    def mark_notified(self, rows, now: str) -> None:
        with self.tx() as c:
            c.executemany("UPDATE jobs SET notified_at=? WHERE company=? AND job_id=?",
                          [(now, r["company"], r["job_id"]) for r in rows])

    def matches_first_seen_since(self, since: str) -> list[sqlite3.Row]:
        """Matching postings that appeared since `since` (not the ones recorded when a company was first seeded)."""
        return self.q("SELECT * FROM jobs WHERE matched=1 AND first_seen>=? AND notified_at IS NOT NULL AND baseline=0 "
                      "ORDER BY company, title", since)

    def open_matches(self, company: str | None = None) -> list[sqlite3.Row]:
        if company:
            return self.q("SELECT * FROM jobs WHERE matched=1 AND removed_at IS NULL AND company=? ORDER BY title", company)
        return self.q("SELECT * FROM jobs WHERE matched=1 AND removed_at IS NULL ORDER BY company, title")

    def jobs_for(self, company: str, *, open_only: bool = True) -> list[sqlite3.Row]:
        sql = "SELECT * FROM jobs WHERE company=?" + (" AND removed_at IS NULL" if open_only else "")
        return self.q(sql + " ORDER BY title", company)

    def add_external_job(self, company: str, job: Job, now: str, m: Match, source: str) -> bool:
        """Store a job learned from the cross-check (for blocked companies). True if it was new."""
        if self.job(company, job.id):
            return False
        with self.tx() as c:
            c.execute("INSERT INTO jobs(company, job_id, title, location, url, posted, first_seen, last_seen, student,"
                      " matched, unsure, term, field, tags, reasons, source) VALUES(?,?,?,?,?,?,?,?,1,?,?,?,?,?,?,?)",
                      (company, job.id, job.title, job.location, job.url, job.posted, now, now, int(m.matched),
                       int(m.unsure), m.term, m.field, json.dumps(m.tags), json.dumps(m.reasons), source))
        return True

    # company state ---------------------------------------------------------------------------
    def state(self, company: str) -> dict:
        row = self.one("SELECT * FROM company_state WHERE company=?", company)
        if row is None:
            self.conn.execute("INSERT OR IGNORE INTO company_state(company) VALUES(?)", (company,))
            row = self.one("SELECT * FROM company_state WHERE company=?", company)
        return dict(row)

    def update_state(self, company: str, **fields) -> None:
        self.state(company)
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE company_state SET {cols} WHERE company=?", (*fields.values(), company))

    # runs / checks ---------------------------------------------------------------------------
    def start_run(self, now: str) -> int:
        cur = self.conn.execute("INSERT INTO runs(started_at, status) VALUES(?, 'running')", (now,))
        return cur.lastrowid

    def finish_run(self, run_id: int, now: str, status: str, checked: int, failed: int, new_matches: int,
                   note: str = "") -> None:
        self.conn.execute("UPDATE runs SET finished_at=?, status=?, checked=?, failed=?, new_matches=?, note=? WHERE id=?",
                          (now, status, checked, failed, new_matches, note, run_id))

    def add_check(self, run_id: int | None, company: str, started_at: str, duration: float, status: str,
                  error_kind: str | None, error: str | None, jobs: int | None, students: int | None,
                  new_jobs: int | None, new_matches: int | None, requests: int | None) -> None:
        self.conn.execute(
            "INSERT INTO checks(run_id, company, started_at, duration, status, error_kind, error, jobs, students,"
            " new_jobs, new_matches, requests) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, company, started_at, duration, status, error_kind, error, jobs, students, new_jobs,
             new_matches, requests))

    def errors_since(self, company: str, since: str) -> list[sqlite3.Row]:
        return self.q("SELECT * FROM checks WHERE company=? AND started_at>=? AND status<>'ok' ORDER BY started_at",
                      company, since)

    def coverage_row(self, company: str) -> dict:
        r = self.one("SELECT COUNT(*) n, SUM(student) s, SUM(matched) m FROM jobs WHERE company=? AND removed_at IS NULL "
                     "AND source='checker'", company)
        ever = self.one("SELECT COUNT(*) n FROM jobs WHERE company=?", company)
        return {"open_jobs": r["n"] or 0, "open_student": r["s"] or 0, "open_matched": r["m"] or 0,
                "ever_seen": ever["n"] or 0}

    # emails ----------------------------------------------------------------------------------
    def log_email(self, kind: str, subject: str, path: str, sent: bool, error: str | None) -> None:
        now = iso()
        self.conn.execute("INSERT INTO emails(kind, subject, created_at, sent_at, error, path) VALUES(?,?,?,?,?,?)",
                          (kind, subject, now, now if sent else None, error, path))


def days_ago(n: float) -> str:
    return iso(utcnow() - timedelta(days=n))
