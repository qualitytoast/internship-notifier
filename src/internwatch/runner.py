"""One polling run: check every due company, store what changed, send the emails.

Order of a run
1. ping the dead man's switch (/start), take the run lock, make sure this machine is online
2. pick the due companies (each is polled every 30-60 min with jitter)
3. run their checkers in worker threads (one request at a time per host, robots.txt respected,
   every request retried with backoff); new student roles get their description fetched
4. for each result, in this thread (SQLite has one writer): store jobs, filter new ones, health checks
5. SimplifyJobs cross-check
6. emails: new postings (one per run), health alert (one per run), daily digest
7. ping the dead man's switch (success or /fail)
"""
from __future__ import annotations

import dataclasses
import fcntl
import json
import logging
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from . import alerts, emails, liveness, moves
from .adapters import get_checker
from .adapters.base import FetchContext, dedupe
from .config import Company, Config
from .crosscheck import CrossCheck, Result
from .db import DB, iso, parse_iso, reopened, utcnow
from .filters import evaluate, is_student_role, vague_location
from .health import Outcome, assess
from .heartbeat import Heartbeat
from .http import HostGate, Http, HttpSettings
from .mailer import Mailer
from .models import CheckerError, Job, NotModified, ShapeError

log = logging.getLogger(__name__)

CROSSCHECK_KEY = "_simplify"   # company_state row used to track the cross-check's own health
CROSSCHECK_SECONDS = 180       # a hanging list must not hold up the morning email
CONNECTIVITY_URLS = ("https://raw.githubusercontent.com/", "https://www.google.com/generate_204")
# learn_ids: the posting id in a SimplifyJobs link, per checker that can read a posting by id (watch_ids)
POSTING_ID_IN_URL = {"ashby": re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"),
                     "oracle": re.compile(r"/job/(\d+)")}
LEARNED_IDS_MAX = 60


def http_settings(cfg: Config) -> HttpSettings:
    h = cfg.settings.get("http", default={}) or {}
    return HttpSettings(connect_timeout=float(h.get("connect_timeout", 10)), read_timeout=float(h.get("read_timeout", 30)),
                        retries=int(h.get("retries", 3)), min_interval=float(h.get("min_interval", 1.0)),
                        respect_robots=bool(h.get("respect_robots", True)))


def make_gate(cfg: Config) -> HostGate:
    return HostGate(cfg.settings.path("robots_cache"))


def check_budget(cfg: Config, c: Company) -> float:
    minutes = c.timeout_minutes or cfg.settings.get("schedule", "check_timeout_minutes", default=8)
    return float(minutes) * 60


def run_checker(cfg: Config, c: Company, *, mode: str = "full", known=(), state: dict | None = None,
                gate: HostGate | None = None, record=None, replay=None, detail_limit: int = 0,
                deadline: float | None = None) -> Outcome:
    """Run one company's checker (no database writes). Used by the runner and by `internwatch check`."""
    started = iso()
    t0 = time.monotonic()
    budget_end = t0 + check_budget(cfg, c)
    http = Http(http_settings(cfg), gate=gate or make_gate(cfg), record=record, replay=replay,
                min_interval=(c.settings or {}).get("min_interval"),
                deadline=min(budget_end, deadline) if deadline else budget_end)
    ctx = FetchContext(mode=mode, known=frozenset(known), state=dict(state or {}), program_words=tuple(c.role_keywords))
    out = Outcome(company=c, mode=mode, started_at=started)
    try:
        checker = get_checker(c.checker)
        jobs = checker.fetch(http, c.settings or {}, ctx)
        if not isinstance(jobs, list):
            raise ShapeError(f"{c.checker} returned {type(jobs).__name__}, not a list")
        jobs = dedupe(jobs)
        if detail_limit and checker.supports_detail:
            known_set = set(known)
            for j in jobs:
                if out.details_fetched >= detail_limit:
                    break
                if j.id in known_set:
                    continue
                m = evaluate(j, cfg.rules, category=c.category, locations=c.locations,
                             extra_role_keywords=c.extra_role_re)
                if not (m.matched and m.needs_detail):
                    continue
                try:
                    checker.detail(http, c.settings or {}, j)
                    out.details_fetched += 1
                except CheckerError as e:  # a missing description never hides the job itself
                    out.detail_errors.append(f"{j.id}: {e}")
                except Exception as e:  # noqa: BLE001 — nor does a job page the parser can't handle
                    log.warning("%s: detail %s crashed: %s: %s", c.key, j.id, type(e).__name__, e)
                    out.detail_errors.append(f"{j.id}: {type(e).__name__}: {e}")
        out.jobs = jobs
        out.reported_total = ctx.reported_total
        out.state = ctx.state
        out.degraded = ctx.degraded
        out.partial = ctx.partial
        out.source_counts = ctx.source_counts or None
    except NotModified:
        out.unchanged, out.state = True, ctx.state
    except CheckerError as e:
        out.error_kind, out.error = e.kind, str(e)
    except Exception as e:  # noqa: BLE001 — a checker bug must surface as a health problem, not crash the run
        log.exception("checker %s crashed", c.key)
        out.error_kind, out.error = "error", f"checker crashed: {type(e).__name__}: {e}"
    finally:
        out.duration = time.monotonic() - t0
        out.requests = http.requests_made
        http.close()
    return out


@dataclass
class RunOptions:
    companies: list[str] | None = None   # only these keys (default: every due company)
    force: bool = False                  # ignore the schedule
    mode: str | None = None              # force "full" or "quick"
    send: bool = True                    # False: write emails to the outbox only
    crosscheck: bool = True
    scheduled_mail: bool = True          # daily digest / weekly report when due
    workers: int | None = None
    daily: bool = False                  # once-a-morning use (`run --daily`): see Runner._run
    retry_delay: float = 90.0            # daily mode: seconds before failed companies are checked again
    progress: object = None              # callable(done, total, company_name, phase) for terminal output
    checks: bool = True                  # False (`--emails-only`): send what is pending without checking sites


@dataclass
class RunSummary:
    run_id: int = 0
    checked: int = 0
    failed: list[str] = field(default_factory=list)
    new_jobs: int = 0
    new_matches: int = 0
    seeded: list[str] = field(default_factory=list)
    problems: list[dict] = field(default_factory=list)
    recovered: list[dict] = field(default_factory=list)
    misses: list[dict] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    retry: list[str] = field(default_factory=list)          # unhealthy without an alert yet (first strike)
    email_errors: list[str] = field(default_factory=list)   # configured, but sending failed
    processed: set = field(default_factory=set)             # companies whose poll was stored (liveness.unchecked)
    healthy: set = field(default_factory=set)               # … and whose poll was ok, complete and full (moves.py)
    note: str = ""

    def line(self) -> str:
        return (f"run {self.run_id}: checked {self.checked}, failed {len(self.failed)}, new jobs {self.new_jobs}, "
                f"new matches {self.new_matches}, problems {len(self.problems)}, misses {len(self.misses)}"
                + (f", seeded {len(self.seeded)}" if self.seeded else "") + (f" — {self.note}" if self.note else ""))


class RunLocked(Exception):
    pass


class Runner:
    def __init__(self, cfg: Config, db: DB | None = None, mailer: Mailer | None = None,
                 gate: HostGate | None = None, heartbeat: Heartbeat | None = None, checker_fn=run_checker):
        self.cfg = cfg
        self.db = db or DB(cfg.settings.path("db"))
        self.mailer = mailer or Mailer(cfg, self.db)
        self.gate = gate or make_gate(cfg)
        self.heartbeat = heartbeat or Heartbeat(cfg)
        self.checker_fn = checker_fn
        self.tz = ZoneInfo(cfg.settings.get("email", "timezone", default="America/Chicago"))
        sched = cfg.settings.get("schedule", default={}) or {}
        self.poll_minutes = sched.get("poll_minutes", [30, 45])
        self.retry_minutes = sched.get("retry_minutes", [30, 40])
        self.workers = int(sched.get("workers", 8))
        self.run_timeout = float(sched.get("run_timeout_minutes", 25)) * 60
        self.full_scan_hours = float(sched.get("full_scan_hours", 24))
        self.detail_limit = int(sched.get("detail_fetch_limit", 40))

    # ------------------------------------------------------------------------------------------
    def due(self, opts: RunOptions) -> list[Company]:
        now = utcnow()
        pool = [c for c in self.cfg.active if not opts.companies or c.key in opts.companies]
        if opts.force or opts.companies or opts.daily:
            return pool
        out = []
        for c in pool:
            nd = parse_iso(self.db.state(c.key)["next_due"])
            if nd is None or nd <= now:
                out.append(c)
        return out

    def mode_for(self, c: Company, opts: RunOptions) -> str:
        if opts.mode:
            return opts.mode
        if opts.daily:
            return "full"  # once a morning: always read every page
        if not c.big or not get_checker(c.checker).supports_quick:
            return "full"
        st = self.db.state(c.key)
        if st["seeded_at"] is None:
            return "full"
        # the last full scan, successful or not: a failed full scan is not retried on every poll
        done = [d for d in (parse_iso(st["last_full"]), parse_iso(self.db.get(f"full_attempt:{c.key}"))) if d]
        hours = c.full_scan_hours or self.full_scan_hours
        if not done or utcnow() - max(done) >= timedelta(hours=hours):
            return "full"
        return "quick"

    def _with_learned_ids(self, c: Company) -> Company:
        """learn_ids: true (Ashby, Oracle): besides the configured watch_ids, read one by one the postings that the
        last poll found open and those SimplifyJobs lists for the company in its latest download, so a posting left
        out of the company's own list while it still takes applications is seen. Ids found closed are dropped."""
        s = c.settings or {}
        rx = POSTING_ID_IN_URL.get(c.checker)
        if not s.get("learn_ids") or rx is None:
            return c
        state = self._checker_state(c.key)
        closed = set(state.get("watch_closed") or [])
        ids = list(dict.fromkeys(str(x) for x in s.get("watch_ids") or []))
        ids += [x for x in state.get("watch_open") or [] if x not in ids]
        rows = self.db.q("SELECT r.url FROM simplify_rows r JOIN kv k ON k.key = 'simplify_baselined:' || r.source "
                         "WHERE r.tracked_company = ? AND r.last_seen = k.value ORDER BY r.first_seen DESC", c.key)
        learned = [m.group(1) for r in rows if (m := rx.search(r["url"] or ""))]
        ids += [x for x in dict.fromkeys(learned) if x not in closed and x not in ids][:LEARNED_IDS_MAX]
        return dataclasses.replace(c, settings={**s, "watch_ids": ids})

    def _checker_state(self, key: str) -> dict:
        try:
            return json.loads(self.db.get(f"ckstate:{key}") or "{}")
        except ValueError:
            return {}

    def wait_online(self, seconds: float) -> bool:
        """A Mac that just woke up may need a minute for Wi-Fi."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            time.sleep(15)
            if self.online():
                return True
        return False

    def online(self) -> bool:
        for url in CONNECTIVITY_URLS:
            try:
                httpx.get(url, timeout=10)
                return True
            except httpx.HTTPError:
                continue
        return False

    # ------------------------------------------------------------------------------------------
    def run(self, opts: RunOptions | None = None) -> RunSummary:
        opts = opts or RunOptions()
        lock_path = self.cfg.settings.path("db").with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RunLocked("another run is in progress") from None
            self.heartbeat.start()
            try:
                summary = self._run(opts)
            except Exception as e:
                log.exception("run crashed")
                self.heartbeat.fail(f"run crashed: {type(e).__name__}: {e}")
                raise
            if summary.note.startswith("offline"):
                self.heartbeat.fail(summary.line())
            elif summary.email_errors:
                # emails can't reach you, so tell healthchecks.io: it alerts you through its own channel
                self.heartbeat.fail("email delivery is failing: " + "; ".join(summary.email_errors)[:900])
            else:
                self.heartbeat.success(summary.line())
            return summary

    def _run(self, opts: RunOptions) -> RunSummary:
        """Continuous mode (systemd timer, every 15 min): poll the companies that are due, alert after two
        failed polls in a row. Daily mode (`run --daily`, once a morning): poll every company, check the
        unhealthy ones a second time at the end of the same run (so one blip never alerts but a real problem
        is reported this morning), and send ONE morning email with everything new since the last run."""
        s = RunSummary()
        if not opts.checks:  # only deliver what earlier runs could not send
            self._notify(s, self.db.get("first_run_done") is None, opts)
            return s
        if not self.online() and not (opts.daily and self.wait_online(300)):
            s.note = "offline: no internet connection, nothing checked"
            log.warning(s.note)
            return s
        start = time.monotonic()
        run_deadline = start + self.run_timeout + (opts.retry_delay + 600 if opts.daily else 0)
        s.run_id = self.db.start_run(iso())
        first_run = self.db.get("first_run_done") is None
        companies = self.due(opts)
        log.info("run %d: %d companies due", s.run_id, len(companies))
        self._check_all(companies, opts, s, first_run, run_deadline)
        if opts.daily and s.retry and time.monotonic() < run_deadline - 300:
            again = [c for c in companies if c.key in set(s.retry)]
            log.info("checking %d unhealthy companies again before alerting", len(again))
            s.retry, s.failed = [], [k for k in s.failed if k not in {c.key for c in again}]
            time.sleep(opts.retry_delay)
            self._check_all(again, opts, s, first_run, run_deadline)

        if opts.crosscheck:
            self._crosscheck(s)
        self._liveness_finish(companies, opts, s, run_deadline)
        self._notify(s, first_run, opts)
        if opts.scheduled_mail and not first_run:
            self._scheduled_mail(opts, s)
        status = "ok" if not s.failed else "partial"
        if s.skipped:
            s.note = f"run time limit reached; {len(s.skipped)} companies postponed to the next run"
        self.db.finish_run(s.run_id, iso(), status, s.checked, len(s.failed), s.new_matches, s.note)
        log.info(s.line())
        return s

    def _check_all(self, companies: list[Company], opts: RunOptions, s: RunSummary, first_run: bool,
                   run_deadline: float) -> None:
        workers = opts.workers or self.workers
        jobs_plan = []
        for c in companies:
            c = self._with_learned_ids(c)
            st = self.db.state(c.key)
            seeding = st["seeded_at"] is None
            jobs_plan.append((c, self.mode_for(c, opts), self.db.known_ids(c.key), self._checker_state(c.key),
                              0 if seeding else self.detail_limit))
        with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="check") as pool:
            futures = {}
            for c, mode, known, state, dlimit in jobs_plan:
                futures[pool.submit(self._guarded_check, c, mode, known, state, dlimit, run_deadline)] = (c, known)
            phase = "re-checking" if s.checked else "checking"
            for done, fut in enumerate(as_completed(futures), 1):
                c, known = futures[fut]
                o = fut.result()
                if opts.progress:
                    opts.progress(done, len(futures), c.name, phase)
                if o is None:
                    s.skipped.append(c.key)
                    continue
                try:
                    verdict = self._process(o, s, first_run)
                except Exception:  # noqa: BLE001 — one company's bad data must not stop the run
                    log.exception("processing %s failed", c.key)
                    s.failed.append(c.key)
                    continue
                self._liveness_observe(o, verdict, known, s)

    def _liveness_observe(self, o: Outcome, verdict, known, s: RunSummary) -> None:
        """Boards of this company that emptied, fell or went stale (liveness.py). Never affects the poll itself."""
        s.processed.add(o.company.key)
        if o.ok and not o.degraded and not o.partial and o.mode == "full":
            s.healthy.add(o.company.key)
        if not liveness.settings(self.cfg)["enabled"]:
            return
        try:
            problems, recovered = liveness.observe(self.cfg, self.db, o.company, o, verdict, known)
        except Exception:  # noqa: BLE001 — a bug here must never cost a company's poll or the run's emails
            log.exception("liveness: %s failed", o.company.key)
            return
        s.problems += problems
        s.recovered += recovered
        try:
            s.problems += moves.observe(self.cfg, self.db, o)
        except Exception:  # noqa: BLE001 — same: only logged
            log.exception("moves: %s failed", o.company.key)

    def _liveness_finish(self, companies: list[Company], opts: RunOptions, s: RunSummary, run_deadline: float) -> None:
        """Run-level checks (liveness.py): companies never processed, new Workday sites, careers pages that moved."""
        lv = liveness.settings(self.cfg)
        if not lv["enabled"]:
            return
        try:
            problems, recovered = liveness.unchecked(self.cfg, self.db, companies, s.processed)
            s.problems += problems
            s.recovered += recovered
            if not opts.daily:  # the weekly scans run once a morning, with time to spare
                return
            s.problems += liveness.scan_workday_sites(self.cfg, self.db, self.gate)
            budget_end = min(time.monotonic() + lv["scan_seconds"], run_deadline - 300)
            if time.monotonic() < budget_end:
                http = Http(http_settings(self.cfg), gate=self.gate)
                try:
                    s.problems += liveness.scan_pages(self.cfg, self.db, http, budget_end)
                finally:
                    http.close()
        except Exception:  # noqa: BLE001 — never block the run's emails
            log.exception("liveness: run-level checks failed")
        if not opts.daily:
            return
        # the companies whose careers page can't be read: where else they could start posting (moves.py)
        budget_end = min(time.monotonic() + lv["blocked_seconds"], run_deadline - 300)
        try:
            s.problems += moves.run(self.cfg, self.db, self.gate, self._scan_http, budget_end, s.healthy)
        except Exception:  # noqa: BLE001 — never block the run's emails
            log.exception("moves: checks of the blocked companies failed")

    def _scan_http(self, deadline: float, retries: int = 1, read_timeout: float | None = None) -> Http:
        """The client of one moves.py check: its own time budget and fewer retries than a checker's."""
        hs = dataclasses.replace(http_settings(self.cfg), retries=retries)
        if read_timeout:
            hs = dataclasses.replace(hs, read_timeout=read_timeout)
        return Http(hs, gate=self.gate, deadline=deadline)

    def _guarded_check(self, c: Company, mode: str, known, state, detail_limit: int, run_deadline: float):
        if time.monotonic() > run_deadline - 30:
            return None  # out of time: leave it due for the next run instead of failing it
        return self.checker_fn(self.cfg, c, mode=mode, known=known, state=state, gate=self.gate,
                               detail_limit=detail_limit, deadline=run_deadline)

    # ------------------------------------------------------------------------------------------
    def _process(self, o: Outcome, s: RunSummary, first_run: bool):
        c, db, rules = o.company, self.db, self.cfg.rules
        now = iso()
        st = db.state(c.key)
        seeding = st["seeded_at"] is None
        partial_seed = bool(db.get(f"partial_seed:{c.key}"))  # the company's first read was cut short
        new_ids: list[str] = []
        new_matches = 0
        # All of a company's writes (its jobs, their filter decisions, health, seeding) commit together: if the run
        # is interrupted or something raises half-way, nothing is saved and the next run redoes this company, so
        # a job can never end up stored but never filtered (and therefore never emailed).
        with db.tx():
            if o.ok and not o.unchanged:
                jobs = o.jobs or []
                new_ids, recheck = db.upsert_jobs(c.key, jobs, now)
                by_id = {j.id: j for j in jobs}
                for jid, old in ({} if seeding else recheck).items():
                    # A known posting that didn't match was edited (e.g. "Summer 2026" retitled "Summer 2027") or came
                    # back after being removed: judge it again. This only ever adds a match, never takes one back.
                    # Details the listing leaves out or blurs ("3 Locations") come from what was known before.
                    j = by_id[jid]
                    j = Job(id=jid, title=j.title,
                            location=(old["location"] or j.location) if vague_location(j.location) else j.location,
                            url=j.url, posted=j.posted, department=j.department or old["department"] or "",
                            employment_type=j.employment_type or old["employment_type"] or "",
                            snippet=j.snippet or old["snippet"] or "")
                    m = evaluate(j, rules, category=c.category, locations=c.locations, extra_role_keywords=c.extra_role_re)
                    if old["matched"]:
                        # Already emailed once: again only for a new round of the same posting, i.e. open again after
                        # a while or retitled for another term (its id reused); otherwise the stored match stays.
                        again = reopened(old["removed_at"], now)
                        if not m.matched or not (again or (m.term not in ("unspecified", "unclear")
                                                          and m.term != old["term"])):
                            continue
                        m.tags.append("reopened" if again else "new term")
                    db.set_match(c.key, jid, m, is_student_role(j, rules, c.extra_role_re))
                    if m.matched:
                        db.conn.execute("UPDATE jobs SET notified_at=NULL, baseline=0 WHERE company=? AND job_id=?",
                                        (c.key, jid))
                        new_matches += 1
                for jid in new_ids:
                    j = by_id[jid]
                    m = evaluate(j, rules, category=c.category, locations=c.locations, extra_role_keywords=c.extra_role_re)
                    db.set_match(c.key, jid, m, is_student_role(j, rules, c.extra_role_re))
                    if not m.matched or seeding:
                        continue
                    if j.extra.get("baseline") or partial_seed:
                        # A source of a multi-source company answered for the first time (it was failing, or was just
                        # added), or the company's first read was cut short: these postings were open before, so they
                        # are not new, but they were never shown either. They go out once, in the next email's
                        # "already open" section.
                        db.conn.execute("UPDATE jobs SET baseline=1 WHERE company=? AND job_id=?", (c.key, jid))
                        continue
                    twin = db.simplify_twin(c.key, j.title, now)
                    if twin:
                        # already emailed from the SimplifyJobs cross-check while this checker was down: not twice
                        db.conn.execute("UPDATE jobs SET notified_at=?, repost_of=? WHERE company=? AND job_id=?",
                                        (now, twin, c.key, jid))
                        db.conn.execute("UPDATE jobs SET removed_at=? WHERE company=? AND job_id=?", (now, c.key, twin))
                        continue
                    new_matches += 1
                    rep = db.find_repost(c.key, jid, j.title, j.location)
                    if rep:
                        db.set_repost(c.key, jid, rep)
            verdict = assess(self.cfg, db, o)
            if o.ok and not o.unchanged and verdict.healthy and o.mode == "full":
                db.mark_removed(c.key, {j.id for j in o.jobs or []}, now)
            if o.ok and o.state is not None:
                db.set(f"ckstate:{c.key}", json.dumps(o.state)[:200_000])
            if o.ok and seeding:
                # First successful look at this company: everything open now is the baseline, not "new".
                db.conn.execute("UPDATE jobs SET notified_at=?, baseline=1 WHERE company=? AND notified_at IS NULL", (now, c.key))
                db.update_state(c.key, seeded_at=now)
                s.seeded.append(c.key)
                new_matches = 0
                # cut short: the rest of what is open now must not arrive later as "new" (a complete re-seed clears it)
                db.set(f"partial_seed:{c.key}", now if o.partial else "")
            elif partial_seed and o.ok and not o.partial and o.mode == "full" and not o.unchanged:
                db.set(f"partial_seed:{c.key}", "")  # a complete read: from now on new postings are new
        lo, hi = self.retry_minutes if not o.ok else self.poll_minutes
        db.update_state(c.key, last_attempt=now,
                        next_due=iso(utcnow() + timedelta(minutes=random.uniform(float(lo), float(hi)))))
        students = sum(1 for j in (o.jobs or []) if is_student_role(j, rules, c.extra_role_re)) if o.jobs else None
        db.add_check(s.run_id, c.key, o.started_at or now, round(o.duration, 2),
                     "ok" if verdict.healthy and o.ok else verdict.status, o.error_kind, (o.error or "")[:2000] or None,
                     None if o.jobs is None else len(o.jobs), students, len(new_ids), new_matches, o.requests)
        s.checked += 1
        s.new_jobs += 0 if seeding else len(new_ids)
        s.new_matches += new_matches
        if not o.ok:
            s.failed.append(c.key)
            log.warning("%s: %s %s", c.key, o.error_kind, (o.error or "")[:300])
        else:
            log.info("%s: %s %s jobs (%d new, %d new matches) in %.1fs, %d requests",
                     c.key, o.mode, "unchanged" if o.unchanged else len(o.jobs or []), len(new_ids), new_matches,
                     o.duration, o.requests)
        if c.big and o.mode == "full":
            self._track_full_scan(c, o, verdict, s, now)
        if verdict.problem:
            s.problems.append(verdict.problem)
        elif not verdict.healthy:
            s.retry.append(c.key)
        if verdict.recovered:
            s.recovered.append(verdict.recovered)
        return verdict

    def _track_full_scan(self, c: Company, o: Outcome, verdict, s: RunSummary, now: str) -> None:
        """Big sites get one full scan a day between quick scans, so a full scan that keeps failing would never
        reach the two-failures-in-a-row alert on its own: count full-scan failures separately."""
        self.db.set(f"full_attempt:{c.key}", now)
        ok = o.ok and not o.degraded
        n = 0 if ok else int(self.db.get(f"full_fail:{c.key}") or 0) + 1
        self.db.set(f"full_fail:{c.key}", str(n))
        last = parse_iso(self.db.get(f"full_alert:{c.key}"))
        if n >= 2 and verdict.problem is None and (last is None or utcnow() - last >= timedelta(hours=24)):
            s.problems.append({"key": c.key, "name": c.name, "checker": c.checker, "kind": o.error_kind or "shape",
                               "summary": f"the daily full scan failed {n} times in a row (quick scans still run)",
                               "detail": (o.error or o.degraded or "")[:400], "since": now,
                               "careers_url": (c.careers_url or [""])[0], "reset_kv": f"full_alert:{c.key}",
                               "alert": {"id": f"full:{c.key}", "rule": "full"}})
            self.db.set(f"full_alert:{c.key}", now)

    # ------------------------------------------------------------------------------------------
    def _crosscheck(self, s: RunSummary) -> None:
        cc = CrossCheck(self.cfg, self.db)
        http = Http(http_settings(self.cfg), gate=self.gate, deadline=time.monotonic() + CROSSCHECK_SECONDS)
        try:  # whatever the list does, the run's emails still go out and the failure is named
            res = cc.resolve(cc.fetch_and_store(http))
        except Exception as e:  # noqa: BLE001
            log.exception("cross-check failed")
            res = Result(errors=[f"{type(e).__name__}: {e}"])
        finally:
            http.close()
        s.misses += res.misses
        # the cross-check's own health, so a broken README parser can't go unnoticed
        pseudo = Company(key=CROSSCHECK_KEY, name="SimplifyJobs cross-check", category="", checker="simplify",
                         careers_url=[src.get("page", src["url"]) for src in
                                      self.cfg.settings.get("crosscheck", "sources", default=[])][:1])
        o = Outcome(company=pseudo, mode="quick", jobs=[], error_kind="error" if res.errors else None,
                    error="; ".join(res.errors) or None)
        v = assess(self.cfg, self.db, o)
        if v.problem:
            s.problems.append(v.problem)
        if v.recovered:
            s.recovered.append(v.recovered)
        if res.via_simplify:
            log.info("cross-check: %d roles for blocked/failing companies stored via Simplify", res.via_simplify)

    def _deliver(self, kind: str, built, opts: RunOptions, s: RunSummary) -> bool:
        subject, text, html = built[:3]
        self.mailer.dry_run = not opts.send
        sent, error, path = self.mailer.send(kind, subject, text, html, attachments=built[3] if len(built) > 3 else None)
        s.emails.append(f"{kind}: {subject} ({'sent' if sent else error})")
        # Mark as delivered when sent, or when email isn't configured/sending is off (the outbox copy is the record).
        ready, _ = self.mailer.ready()
        if ready and opts.send and not sent:
            s.email_errors.append(f"{kind}: {error}")
        return sent or not ready or not opts.send

    def _update_alerts(self, s: RunSummary) -> tuple[list[dict], list[dict]]:
        """Bring the list of open alerts up to date. Returns the problems and misses a HEALTH email has yet to tell
        about. A bug here must never cost the run's emails: the alerts of this run then wait for the next one."""
        try:
            with self.db.tx():
                alerts.start(self.cfg, self.db)
                fresh = alerts.record(self.db, s.problems, s.misses)
                alerts.sweep(self.cfg, self.db)
            return fresh
        except Exception:  # noqa: BLE001 — see above
            log.exception("alerts: the list could not be updated")
            return s.problems, s.misses

    def _notify(self, s: RunSummary, first_run: bool, opts: RunOptions) -> None:
        db, now = self.db, iso()
        fresh, new_misses = self._update_alerts(s)
        if first_run and s.seeded:
            rows = db.open_matches()
            failed = [self.cfg.company(k).name for k in s.failed if k in {c.key for c in self.cfg.companies}]
            delivered = self._deliver("seed", emails.seed_summary(self.cfg, rows, len(s.seeded), failed), opts, s)
            db.set("first_run_done", now)          # the baseline exists either way
            db.set("seed_email_pending", "" if delivered else "1")
        elif db.get("seed_email_pending") == "1":   # the first-run summary never got out: try again
            seeded = sum(1 for c in self.cfg.active if db.state(c.key)["seeded_at"])
            if self._deliver("seed", emails.seed_summary(self.cfg, db.open_matches(), seeded, []), opts, s):
                db.set("seed_email_pending", "")
        elif s.seeded:
            rows = [r for k in s.seeded for r in db.open_matches(k)]
            self._deliver("watching", emails.watching_summary(self.cfg, rows, s.seeded), opts, s)
        rows = db.unnotified_matches()
        if opts.daily and not first_run:
            # one email every morning, even when nothing is new: silence would hide a broken setup
            if self._deliver("morning", build_digest(self.cfg, db, rows=rows), opts, s):
                db.mark_notified(rows, now)
                db.set("last_digest_at", now)
                db.set("last_digest", datetime.now(self.tz).date().isoformat())
                alerts.mark_told(db)
        elif rows:
            if self._deliver("new", emails.new_postings(self.cfg, rows), opts, s):
                db.mark_notified(rows, now)
        if fresh or new_misses:  # the morning email repeats every open alert; this one tells about new ones, once
            if self._deliver("health", emails.health(self.cfg, fresh, [], new_misses), opts, s):
                alerts.mark_sent(db)
            else:
                self._reopen_alerts(s)

    def _reopen_alerts(self, s: RunSummary) -> None:
        """The health email did not go out: undo 'alerted' so the next run raises the same alerts again."""
        for p in s.problems:
            liveness.restore(self.db, p)  # the baseline a liveness check had already moved past this alert
            if p.get("reset_kv"):
                self.db.set(p["reset_kv"], "")
            elif p.get("key"):
                self.db.update_state(p["key"], alert_open=0, last_alert_at=None, **(p.get("restore_state") or {}))
        for m in s.misses:
            if m.get("row_key"):
                self.db.conn.execute("UPDATE simplify_rows SET status='pending', resolved_at=NULL WHERE source=? AND row_key=?",
                                     (m["source"], m["row_key"]))

    def _scheduled_mail(self, opts: RunOptions, s: RunSummary) -> None:
        local = datetime.now(self.tz)
        today = local.date().isoformat()
        digest_hour = int(self.cfg.settings.get("email", "digest_hour", default=8))
        if not opts.daily and local.hour >= digest_hour and self.db.get("last_digest") != today:
            built_at = iso()
            if self._deliver("digest", build_digest(self.cfg, self.db), opts, s):
                self.db.set("last_digest", today)
                self.db.set("last_digest_at", built_at)  # untracked roles up to here have been reported
                alerts.mark_told(self.db)


def build_digest(cfg: Config, db: DB, rows=None):
    """Daily digest; with rows= (daily mode) the morning email listing those new rows."""
    since = iso(utcnow() - timedelta(hours=24))
    new_rows = db.matches_first_seen_since(since) if rows is None else rows
    last = db.get("last_digest_at") or since
    untracked = CrossCheck(cfg, db).untracked_for_digest(min(last, since))
    try:
        open_alerts, resolved = alerts.for_email(db)
    except Exception:  # noqa: BLE001 — the roles still go out
        log.exception("alerts: the list could not be read")
        open_alerts, resolved = None, []
    table = None
    if rows is not None:  # the morning email carries one line and the whole table, so nothing else has to
        from .report import coverage_rows
        table = coverage_rows(cfg, db)
    return emails.digest(cfg, new_rows, untracked, open_alerts, resolved, morning=rows is not None, table=table)
