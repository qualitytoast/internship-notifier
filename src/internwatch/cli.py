"""internwatch command line.

  internwatch run                 one polling run (what the systemd timer calls every 15 minutes)
  internwatch check <company>     run one checker and print what it finds
  internwatch verify [company…]   run every checker and print the coverage table
  internwatch add <name> <url>    detect the hiring system, test it live, add it to companies.yaml
  internwatch report              send the weekly coverage report now
  internwatch digest              send the daily digest now
  internwatch alert-test          trigger a real health alert end to end (proves alerts reach you)
  internwatch status              what the service has been doing
  internwatch test-filters "<title>" [--location …]   see how the filters decide a title
  internwatch record [company…]   record test fixtures (offline replays for pytest)
  internwatch coverage            regenerate COVERAGE.md
  internwatch refilter            re-apply config/filters.yaml to every stored job (only ever adds matches)
  internwatch daemon              run forever, every 15 minutes (Docker)
"""
from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from . import config as configmod
from . import emails
from .adapters import all_types, get_checker
from .adapters.base import FetchContext, dedupe
from .config import Company, Config
from .db import DB, iso, utcnow
from .filters import evaluate, is_student_role
from .health import Outcome, assess
from .http import Cassette, Http, HttpSettings
from .mailer import Mailer
from .models import Job
from .report import (counts_agree, coverage_rows, fixture_path, load_results, load_verify, save_verify,
                     write_coverage_md)
from .runner import RunLocked, RunOptions, Runner, build_digest, http_settings, make_gate, run_checker

log = logging.getLogger("internwatch")


def setup_logging(cfg: Config, verbose: bool = False) -> None:
    logdir = cfg.settings.path("logs")
    logdir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.handlers.RotatingFileHandler(logdir / "internwatch.log", maxBytes=5_000_000, backupCount=5)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    sh.setLevel(logging.DEBUG if verbose else logging.WARNING)
    root.handlers = [fh, sh]
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------------------------

def cmd_run(cfg: Config, a) -> int:
    opts = RunOptions(companies=a.company or None, force=a.force, mode=a.mode, send=not a.no_send,
                      crosscheck=not a.no_crosscheck, daily=a.daily, checks=not a.emails_only)
    if sys.stderr.isatty() and opts.checks:  # someone is watching: show progress (the timer's logs stay clean)
        def progress(done, total, name, phase):
            print(f"\r  {phase} {done}/{total} companies  ({name[:28]})".ljust(72), end="", file=sys.stderr, flush=True)
            if done == total:
                print(file=sys.stderr)  # end the progress line so later messages start on their own line
        opts.progress = progress
        print("Checking every company's careers site (about 15 minutes)…", file=sys.stderr)
    try:
        s = Runner(cfg).run(opts)
    except RunLocked as e:
        print(f"skipped: {e}")
        return 0
    print(s.line() if opts.checks else f"sent what was pending ({len(s.emails)} email(s))")
    for e in s.emails:
        print("  email", e)
    for p in s.problems:
        print(f"  PROBLEM {p['name']}: {p['kind']} — {p['summary']}")
    for m in s.misses:
        print(f"  POSSIBLE MISS {m['company']}: {m['title']}")
    return 0 if not s.note.startswith("offline") else 1


def _print_jobs(cfg: Config, c: Company, jobs: list[Job], show: str, limit: int) -> None:
    shown = 0
    for j in sorted(jobs, key=lambda j: j.title.lower()):
        m = evaluate(j, cfg.rules, category=c.category, locations=c.locations, extra_role_keywords=c.extra_role_re)
        student = is_student_role(j, cfg.rules, c.extra_role_re)
        if show == "matches" and not m.matched:
            continue
        if show == "students" and not student:
            continue
        mark = "MATCH" if m.matched else ("student" if student else "")
        tags = ",".join(m.tags) if m.matched else "; ".join(m.reasons)
        print(f"  {mark:7} {j.title[:80]:80} | {j.location[:40]:40} | {m.term if m.matched else '':16} | {tags[:60]}")
        print(f"          {j.url}")
        shown += 1
        if shown >= limit:
            print(f"  … (limit {limit}; use --limit)")
            break


def cmd_check(cfg: Config, a) -> int:
    c = cfg.company(a.company)
    checker = get_checker(c.checker)
    print(f"{c.name} [{c.key}] — {c.checker}: {checker.describe(c.settings or {})}")
    if c.status != "active":
        print(f"status: {c.status} — {c.blocked_reason or c.notes}")
        if not a.force:
            return 0
    gate = make_gate(cfg)
    path = None
    if a.record:
        o, path = record_one(cfg, c, gate)
    else:
        o = run_checker(cfg, c, mode=a.mode, gate=gate)
    if not o.ok:
        print(f"FAILED ({o.error_kind}) after {o.duration:.1f}s, {o.requests} requests: {o.error}")
        return 2
    if o.degraded:
        print(f"DEGRADED (part of the feed failed; the rest was read): {o.degraded}")
    jobs = o.jobs or []
    students = [j for j in jobs if is_student_role(j, cfg.rules, c.extra_role_re)]
    if a.details and checker.supports_detail:
        http = Http(http_settings(cfg), gate=gate, min_interval=(c.settings or {}).get("min_interval"))
        for j in students[: a.details]:
            try:
                checker.detail(http, c.settings or {}, j)
            except Exception as e:  # noqa: BLE001
                print(f"  detail {j.id} failed: {e}")
        http.close()
    matches = [j for j in jobs if evaluate(j, cfg.rules, category=c.category, locations=c.locations,
                                           extra_role_keywords=c.extra_role_re).matched]
    print(f"{len(jobs)} jobs, {len(students)} student roles, {len(matches)} match your filters "
          f"({o.duration:.1f}s, {o.requests} requests" + (f", source total {o.reported_total}" if o.reported_total else "") + ")")
    if a.json:
        print(json.dumps([j.to_dict() for j in jobs], indent=1)[:200_000])
    else:
        _print_jobs(cfg, c, jobs, a.show, a.limit)
    if path:
        print(f"fixture saved: {path}")
    return 0


def save_fixture(cfg: Config, c: Company, cassette: Cassette, jobs: list[Job], detail_jobs: list[Job]) -> str:
    checker = get_checker(c.checker)
    trim = getattr(checker, "trim_fixture", None)
    if trim is not None:  # very large feeds keep a structurally complete subset
        trim(cassette.exchanges)
        jobs = dedupe(checker.fetch(Http(replay=Cassette(exchanges=cassette.exchanges)), c.settings or {}, FetchContext()))
        kept = {j.id for j in jobs}
        detail_jobs = [j for j in detail_jobs if j.id in kept]
    cassette.meta = {"key": c.key, "checker": c.checker, "settings": c.settings, "count": len(jobs),
                     "students": sum(1 for j in jobs if is_student_role(j, cfg.rules, c.extra_role_re)),
                     "ids_sample": sorted(j.id for j in jobs)[:25], "detail_ids": [j.id for j in detail_jobs],
                     "recorded_at": iso()}
    path = fixture_path(cfg, c.key)
    cassette.save(path)
    return str(path)


def record_one(cfg: Config, c: Company, gate) -> tuple[Outcome, str | None]:
    """Run a checker live with recording on, fetch 1–2 student-role details, save the cassette."""
    cassette = Cassette()
    o = run_checker(cfg, c, record=cassette, gate=gate)
    if not o.ok:
        return o, None
    jobs = o.jobs or []
    checker = get_checker(c.checker)
    detail_jobs = []
    if checker.supports_detail:
        http = Http(http_settings(cfg), gate=gate, record=cassette, min_interval=(c.settings or {}).get("min_interval"))
        for j in [j for j in jobs if is_student_role(j, cfg.rules, c.extra_role_re)][:2] or jobs[:1]:
            try:
                checker.detail(http, c.settings or {}, j)
                detail_jobs.append(j)
            except Exception as e:  # noqa: BLE001
                log.warning("%s: detail %s failed while recording: %s", c.key, j.id, e)
        http.close()
    return o, save_fixture(cfg, c, cassette, jobs, detail_jobs)


def cmd_record(cfg: Config, a) -> int:
    targets = [cfg.company(k) for k in a.company] if a.company else cfg.active
    gate = make_gate(cfg)
    bad = 0
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for c, (o, path) in zip(targets, pool.map(lambda c: record_one(cfg, c, gate), targets)):
            if path:
                print(f"{c.key:28} {len(o.jobs or []):6} jobs  -> {path}")
            else:
                bad += 1
                print(f"{c.key:28} FAILED {o.error_kind}: {(o.error or '')[:150]}")
    return 1 if bad else 0


def cmd_verify(cfg: Config, a) -> int:
    targets = [cfg.company(k) for k in a.company] if a.company else cfg.companies
    results = load_results(cfg.root)
    verify = load_verify(cfg.root) if a.write else {}
    gate = make_gate(cfg)
    active = [c for c in targets if c.status == "active"]

    def one(c):
        if a.record:
            return record_one(cfg, c, gate)[0]
        return run_checker(cfg, c, gate=gate)

    print(f"{'company':28} {'checker':16} {'status':10} {'jobs':>6} {'page':>6} {'intern':>6} {'match':>6}  note")
    outcomes = {}
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for c, o in zip(active, pool.map(one, active)):
            outcomes[c.key] = o
    bad = 0
    for c in targets:
        res = results.get(c.key, {})
        page = (c.verified or {}).get("page_total", res.get("page_total"))
        if c.status != "active":
            print(f"{c.key:28} {c.checker:16} {c.status:10} {'—':>6} {str(page or '—'):>6} {'—':>6} {'—':>6}  {c.blocked_reason[:70]}")
            continue
        o = outcomes[c.key]
        if not o.ok:
            bad += 1
            print(f"{c.key:28} {c.checker:16} {'ERROR':10} {'—':>6} {str(page or '—'):>6} {'—':>6} {'—':>6}  "
                  f"{o.error_kind}: {(o.error or '')[:90]}")
            if a.write:
                verify[c.key] = {"error": f"{o.error_kind}: {o.error}"[:500], "at": iso()}
            continue
        jobs = o.jobs or []
        students = sum(1 for j in jobs if is_student_role(j, cfg.rules, c.extra_role_re))
        matched = sum(1 for j in jobs if evaluate(j, cfg.rules, category=c.category, locations=c.locations,
                                                  extra_role_keywords=c.extra_role_re).matched)
        agree = counts_agree(len(jobs), page)
        explained = (c.verified or {}).get("explained") or res.get("explained")
        note = "" if agree else (f"differs from page ({explained[:60]})" if explained else
                                 ("no page total recorded" if page is None else "DIFFERS from careers page"))
        if o.degraded:
            note = f"part of the feed is failing: {o.degraded[:70]}"
        if (not agree and not explained) or o.degraded:
            bad += 1
        print(f"{c.key:28} {c.checker:16} {'degraded' if o.degraded else 'ok':10} {len(jobs):6} "
              f"{str(page if page is not None else '—'):>6} {students:6} {matched:6}  {note}")
        if a.write:
            verify[c.key] = {"jobs": len(jobs), "students": students, "matched": matched, "at": iso(),
                             "duration": round(o.duration, 1), "requests": o.requests,
                             **({"degraded": o.degraded[:500]} if o.degraded else {})}
    if a.write:
        save_verify(cfg.root, verify)
        print(f"wrote {write_coverage_md(cfg)}")
    print(f"\n{len(active)} checkers run, {bad} need attention")
    return 1 if bad else 0


def cmd_add(cfg: Config, a) -> int:
    from .detect import add_company
    return add_company(cfg, a)


def _send(cfg: Config, kind: str, built, no_send: bool) -> int:
    db = DB(cfg.settings.path("db"))
    m = Mailer(cfg, db, dry_run=no_send)
    sent, err, path = m.send(kind, *built)
    print(f"{built[0]}\n-> {'sent' if sent else err}; copy saved to {path}"
          + (f" (+ {len(built[3])} attachments)" if len(built) > 3 else ""))
    return 0 if sent or no_send or not m.ready()[0] else 1


def cmd_report(cfg: Config, a) -> int:
    db = DB(cfg.settings.path("db"))
    return _send(cfg, "coverage", emails.coverage(cfg, coverage_rows(cfg, db)), a.no_send)


def cmd_digest(cfg: Config, a) -> int:
    db = DB(cfg.settings.path("db"))
    return _send(cfg, "digest", build_digest(cfg, db), a.no_send)


ALERT_TEST_KEY = "_alert_test"


def cmd_alert_test(cfg: Config, a) -> int:
    """Make a real request fail, push it through the normal health logic, and email the alert."""
    db = DB(cfg.settings.path("db"))
    fake = Company(key=ALERT_TEST_KEY, name="Alert test (deliberate failure)", category="", checker="alert-test",
                   careers_url=["https://example.invalid/careers"])
    http = Http(HttpSettings(retries=1, backoff_base=0.5, connect_timeout=3, respect_robots=False))
    err_kind, err = "error", ""
    try:
        http.get("http://127.0.0.1:9/jobs")  # discard port: connection refused, retried with backoff
    except Exception as e:  # noqa: BLE001 — this failure is the point
        err_kind, err = getattr(e, "kind", "error"), f"{type(e).__name__}: {e}"
    finally:
        http.close()
    problem = None
    after = int(cfg.settings.get("health", "alert_after_failures", default=2))
    for _ in range(after):
        v = assess(cfg, db, Outcome(company=fake, error_kind=err_kind, error=err))
        problem = v.problem or problem
    db.conn.execute("DELETE FROM company_state WHERE company=?", (ALERT_TEST_KEY,))
    if problem is None:
        print("health logic did not raise an alert — this is a bug")
        return 1
    print(f"failure observed: {err}")
    return _send(cfg, "health", emails.health(cfg, [problem], [], [], test=True), a.no_send)


def cmd_status(cfg: Config, a) -> int:
    db = DB(cfg.settings.path("db"))
    act = cfg.active
    print(f"companies: {len(cfg.companies)} configured, {len(act)} active, "
          f"{sum(1 for c in cfg.companies if c.status == 'blocked')} blocked")
    r = db.one("SELECT * FROM runs ORDER BY id DESC LIMIT 1")
    if r:
        print(f"last run #{r['id']}: started {r['started_at']}, finished {r['finished_at'] or '—'}, {r['status']}, "
              f"checked {r['checked']}, failed {r['failed']}, new matches {r['new_matches']} {r['note'] or ''}")
    n = db.one("SELECT COUNT(*) n, SUM(matched) m, SUM(removed_at IS NULL) open FROM jobs")
    print(f"jobs stored: {n['n']} ({n['open'] or 0} open), matches ever: {n['m'] or 0}")
    for p in db.q("SELECT * FROM company_state WHERE alert_open=1 OR consecutive_failures>0 OR anomaly_streak>0"):
        print(f"  problem: {p['company']}: {(p['last_error'] or '')[:120]} (since {p['failing_since']})")
    for e in db.q("SELECT * FROM emails ORDER BY id DESC LIMIT 5"):
        print(f"  email {e['created_at']} {e['kind']:9} {'sent' if e['sent_at'] else (e['error'] or '')[:30]:30} {e['subject'][:80]}")
    never = [c.key for c in act if not db.state(c.key)["last_success"]]
    if never:
        print(f"never succeeded yet ({len(never)}): {', '.join(never[:20])}{' …' if len(never) > 20 else ''}")
    return 0


def cmd_test_filters(cfg: Config, a) -> int:
    c = cfg.company(a.company) if a.company else None
    job = Job(id="test", title=a.title, location=a.location or "", snippet=a.snippet or "",
              department=a.dept or "", employment_type=a.type or "")
    m = evaluate(job, cfg.rules, category=c.category if c else (a.category or ""),
                 locations=c.locations if c else None, extra_role_keywords=c.extra_role_re if c else None)
    print(f"{'MATCH' if m.matched else 'no match'}{' (unsure)' if m.unsure else ''}: term={m.term} field={m.field} "
          f"tags={m.tags}")
    for r in m.reasons:
        print(f"  - {r}")
    return 0


def cmd_coverage(cfg: Config, a) -> int:
    print(f"wrote {write_coverage_md(cfg)}")
    return 0


def cmd_refilter(cfg: Config, a) -> int:
    db = DB(cfg.settings.path("db"))
    comps = {c.key: c for c in cfg.companies}
    added = newly = kept = 0
    now = iso()
    with db.tx():
        for r in db.q("SELECT * FROM jobs WHERE source='checker'"):
            c = comps.get(r["company"])
            if c is None:
                continue
            j = Job(id=r["job_id"], title=r["title"], location=r["location"], url=r["url"], posted=r["posted"],
                    snippet=r["snippet"], department=r["department"], employment_type=r["employment_type"])
            m = evaluate(j, cfg.rules, category=c.category, locations=c.locations, extra_role_keywords=c.extra_role_re)
            if r["matched"] and not m.matched:
                # Additions only: a stored match is never taken back (its stored details may be poorer than the
                # ones it was first judged with, e.g. a job type read from the posting's page).
                kept += 1
                continue
            if m.matched and not r["matched"]:
                added += 1
                if r["removed_at"] is None:
                    # It was in no email so far (it did not match), even if it was recorded as already notified
                    # when its company was first seeded. --notify sends it with the next run.
                    newly += 1
                    db.conn.execute("UPDATE jobs SET notified_at=? WHERE company=? AND job_id=?",
                                    (None if a.notify else (r["notified_at"] or now), r["company"], r["job_id"]))
            db.set_match(r["company"], r["job_id"], m, is_student_role(j, cfg.rules, c.extra_role_re))
    print(f"re-evaluated; {added} jobs now match, {newly} of them open"
          + (" (they go out with the next run's email)" if a.notify
             else " (marked as already notified; use --notify to email them with the next run)")
          + (f"; {kept} existing matches the current filters would reject were kept as matches" if kept else ""))
    return 0


def cmd_reseed(cfg: Config, a) -> int:
    """After switching a company to a different checker its job ids change; without this every current posting
    would be emailed as new. The next run records them as a baseline instead (you get a 'Now watching' email)."""
    db = DB(cfg.settings.path("db"))
    for key in a.company:
        c = cfg.company(key)
        db.update_state(c.key, seeded_at=None)
        print(f"{c.name}: its next check records the current postings as a baseline (no 'new' emails for them)")
    return 0


def cmd_daemon(cfg: Config, a) -> int:
    period = a.minutes * 60
    while True:
        try:
            s = Runner(cfg).run(RunOptions())
            print(s.line(), flush=True)
        except RunLocked:
            pass
        except Exception:  # noqa: BLE001 — logged by the runner; keep the loop alive
            log.exception("run failed")
        time.sleep(period - (time.time() % period) + 5)


# ---------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="internwatch", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="one polling run")
    r.add_argument("--force", action="store_true", help="poll every company now, ignoring the schedule")
    r.add_argument("--company", action="append", help="only this company (repeatable)")
    r.add_argument("--mode", choices=["full", "quick"])
    r.add_argument("--no-send", action="store_true", help="write emails to data/outbox only")
    r.add_argument("--no-crosscheck", action="store_true")
    r.add_argument("--daily", action="store_true",
                   help="once-a-morning mode: check every company, retry failures, one morning email")
    r.add_argument("--emails-only", action="store_true",
                   help="don't check any site; just send the emails earlier runs could not deliver")
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("check", help="run one checker and print what it finds")
    c.add_argument("company")
    c.add_argument("--show", choices=["matches", "students", "all"], default="students")
    c.add_argument("--limit", type=int, default=200)
    c.add_argument("--mode", choices=["full", "quick"], default="full")
    c.add_argument("--details", type=int, default=0, help="fetch descriptions for N student roles")
    c.add_argument("--record", action="store_true", help="save the responses as a test fixture")
    c.add_argument("--json", action="store_true")
    c.add_argument("--force", action="store_true", help="run even if the company is blocked/disabled")
    c.set_defaults(fn=cmd_check)

    v = sub.add_parser("verify", help="run every checker and print the coverage table")
    v.add_argument("company", nargs="*")
    v.add_argument("--workers", type=int, default=6)
    v.add_argument("--write", action="store_true", help="save results to discovery/verify.json and COVERAGE.md")
    v.add_argument("--record", action="store_true", help="also record test fixtures")
    v.set_defaults(fn=cmd_verify)

    ad = sub.add_parser("add", help="add a company: detect its hiring system, test it, save it")
    ad.add_argument("name")
    ad.add_argument("url")
    ad.add_argument("--key")
    ad.add_argument("--category", default="")
    ad.add_argument("--checker", help=f"skip detection: one of {', '.join(all_types())}")
    ad.add_argument("--settings", help='checker settings as JSON, e.g. \'{"board": "stripe"}\'')
    ad.add_argument("--locations", help="comma-separated country codes, e.g. US,CA (default: filters.yaml)")
    ad.add_argument("--yes", action="store_true", help="save without asking")
    ad.add_argument("--browser", action="store_true", help="also load the page in headless Chromium to detect")
    ad.set_defaults(fn=cmd_add)

    for name, fn, h in (("report", cmd_report, "send the weekly coverage report now"),
                        ("digest", cmd_digest, "send the daily digest now"),
                        ("alert-test", cmd_alert_test, "trigger a real health alert end to end")):
        x = sub.add_parser(name, help=h)
        x.add_argument("--no-send", action="store_true", help="write to data/outbox only")
        x.set_defaults(fn=fn)

    sub.add_parser("status", help="what the service has been doing").set_defaults(fn=cmd_status)

    t = sub.add_parser("test-filters", help="show how the filters decide a title")
    t.add_argument("title")
    t.add_argument("--location", default="")
    t.add_argument("--company")
    t.add_argument("--category")
    t.add_argument("--type", help="employment type from the hiring system")
    t.add_argument("--dept")
    t.add_argument("--snippet", help="description text")
    t.set_defaults(fn=cmd_test_filters)

    rec = sub.add_parser("record", help="record test fixtures from the live sites")
    rec.add_argument("company", nargs="*")
    rec.add_argument("--workers", type=int, default=6)
    rec.set_defaults(fn=cmd_record)

    sub.add_parser("coverage", help="regenerate COVERAGE.md").set_defaults(fn=cmd_coverage)

    rf = sub.add_parser("refilter", help="re-apply filters.yaml to every stored job (only ever adds matches)")
    rf.add_argument("--notify", action="store_true", help="email open jobs that now match")
    rf.set_defaults(fn=cmd_refilter)

    rs = sub.add_parser("reseed", help="after changing a company's checker: re-record its postings as a baseline")
    rs.add_argument("company", nargs="+")
    rs.set_defaults(fn=cmd_reseed)

    d = sub.add_parser("daemon", help="run forever (for Docker)")
    d.add_argument("--minutes", type=int, default=15)
    d.set_defaults(fn=cmd_daemon)
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    cfg = configmod.load()
    setup_logging(cfg, a.verbose)
    return int(a.fn(cfg, a) or 0)


if __name__ == "__main__":
    sys.exit(main())
