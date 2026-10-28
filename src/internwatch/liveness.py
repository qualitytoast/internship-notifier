"""Notice a board that went dead, was abandoned or was replaced: what the company-wide health rules (health.py) can't see.

1. Per source, after each poll that read everything (not degraded, not cut short, not "unchanged"):
   source = a board or Workday site of a company that reads several, a multi source, an Eightfold quick query
   (FetchContext.source_counts), or a student slice of Apple, Meta or Amazon.
   emptied  a source that listed jobs lists none on two polls in a row: alert, kept open (reminded weekly) until it
            lists jobs again
   dropped  it lost more than half of at least 6 jobs on two polls in a row: alerted once, the new count accepted
   stale    the newest posting of a source (or of a one-source company) is older than `stale_days` and than
            `stale_gap_factor` × its usual gap between postings: alert, open until a newer posting appears. Only
            sources listing at least `stale_min_dated` dated postings are judged: small boards post in bursts.
   Nothing is judged while the company itself is failing or its zero/drop alert is out (that alert already says it).
2. Companies not checked: due in `unchecked_runs` runs in a row but never processed (skipped at the run deadline, a
   crash while storing its jobs, a company added and never run).
3. Weekly, in daily runs with time to spare: each company's careers page is read once and the hiring systems it
   points at (detect.from_text) are compared with the last time; a new one that isn't configured, or a configured
   one it no longer mentions, alerts ("moved"). Workday tenants' robots.txt, already cached by the checks (no request),
   is compared with the configured sites: a new site alerts. The first look at a page or tenant is a silent baseline.
Every alert goes into the run's health email with reset_kv="live_alert:…", so an email that fails is sent again.
State: table source_health, kv live_alert:*, unchecked_runs:*, page_systems:*, page_scan_at:*, workday_sites:*.
"""
from __future__ import annotations

import json
import logging
import statistics
import time
from datetime import date, timedelta

from .adapters import get_checker
from .config import Company, Config
from .db import DB, iso, parse_iso, utcnow
from .health import Outcome

log = logging.getLogger(__name__)

SCHEMA = """CREATE TABLE IF NOT EXISTS source_health (
  company TEXT NOT NULL, source TEXT NOT NULL, label TEXT NOT NULL DEFAULT '',
  baseline INTEGER, last_count INTEGER,
  zero_streak INTEGER NOT NULL DEFAULT 0, drop_streak INTEGER NOT NULL DEFAULT 0,
  empty_since TEXT, stale_since TEXT, updated_at TEXT,
  PRIMARY KEY (company, source))"""
WHOLE = "*"  # the company as one source (stale rule only)
# student slices read by one checker, recognised by the job's employment type
SLICES = {"apple": ("Apple's Internships team", lambda j: j.employment_type.startswith("Intern (Apple Internships")),
          "meta": ("Meta's Internship label", lambda j: j.employment_type == "Internship"),
          "amazon": ("Amazon's intern postings", lambda j: j.employment_type == "Intern")}
IDKEYS = ("board", "site", "host", "tenant", "account", "subdomain", "company_id")


def settings(cfg: Config) -> dict:
    h = cfg.settings.get("health", default={}) or {}
    lv = cfg.settings.get("liveness", default={}) or {}
    return {"after": int(h.get("alert_after_failures", 2)), "threshold": float(h.get("drop_threshold", 0.5)),
            "min_base": int(h.get("drop_min_baseline", 6)),
            "remind": timedelta(days=float(lv.get("source_reminder_days", 7))),
            "stale_days": float(lv.get("stale_days", 45)), "gap_factor": float(lv.get("stale_gap_factor", 3)),
            "stale_min_dated": int(lv.get("stale_min_dated", 20)),
            "stale_remind": timedelta(days=float(lv.get("stale_reminder_days", 14))),
            "unchecked_runs": int(lv.get("unchecked_runs", 2)),
            "scan_every": timedelta(days=float(lv.get("page_scan_days", 7))),
            "scan_seconds": float(lv.get("page_scan_seconds", 180)), "enabled": lv.get("enabled", True),
            "blocked_seconds": float(lv.get("blocked_scan_seconds", 150))}


def ensure_schema(db: DB) -> None:
    db.conn.execute(SCHEMA)


# sources ------------------------------------------------------------------------------------

def _subs(checker: str, s: dict) -> list[tuple[str, str]]:
    """The (Job.extra key, value) of each board/site/list a single checker reads, when it reads several."""
    if checker in ("greenhouse", "instabase") and len(s.get("boards") or []) > 1:
        return [("board", b) for b in s["boards"]]
    if checker == "workday" and len(s.get("sites") or []) > 1:
        return [("site", x) for x in s["sites"]]
    if checker == "deshaw":
        from .checkers.deshaw import LISTS
        return [("list", x) for x in LISTS]
    return []


def source_counts(c: Company, o: Outcome) -> dict[str, tuple[str, int]]:
    """{source id: (what it is, job count)} for a company that reads several sources; {} for one source."""
    s = c.settings or {}
    jobs = o.jobs or []
    out: dict[str, list] = {}

    def add(sid: str, what: str, n: int = 0):
        out.setdefault(sid, [what, 0])[1] += n

    if c.checker == "multi":
        from .checkers.multi import _source_ids
        srcs = [(i, get_checker(x["checker"]), x.get("settings") or {}) for i, x in enumerate(s.get("sources") or [])]
        ids = _source_ids(srcs)
        for i, ck, st in srcs:
            subs = _subs(ck.type, st)
            for k, v in subs or [("", "")]:
                add(f"{ids[i]} {k}:{v}" if k else ids[i], f"{ck.type} source {i + 1}" + (f" ({k} {v})" if k else ""))
        for j in jobs:
            i = int(j.extra.get("source", 0) or 0)
            if i >= len(srcs):
                continue
            subs = _subs(srcs[i][1].type, srcs[i][2])
            k = subs[0][0] if subs else ""
            add(f"{ids[i]} {k}:{j.extra.get(k)}" if k else ids[i], "", 1)
    else:
        subs = _subs(c.checker, s)
        for k, v in subs:
            add(f"{k}:{v}", f"{c.checker} {k} {v}")
        if subs:
            for j in jobs:
                add(f"{subs[0][0]}:{j.extra.get(subs[0][0])}", "", 1)
    if c.checker in SLICES:
        what, test = SLICES[c.checker]
        add("slice", what, sum(1 for j in jobs if test(j)))
    for sid, n in (getattr(o, "source_counts", None) or {}).items():
        add(sid, sid, n)
    return {k: (v[0] or k, v[1]) for k, v in out.items()}


# per-poll rules ------------------------------------------------------------------------------

def _row(db: DB, company: str, source: str):
    return db.one("SELECT * FROM source_health WHERE company=? AND source=?", company, source)


def _save(db: DB, company: str, source: str, label: str, **f) -> None:
    db.conn.execute("INSERT OR IGNORE INTO source_health(company, source, label) VALUES(?,?,?)", (company, source, label))
    f["updated_at"] = iso()
    db.conn.execute(f"UPDATE source_health SET {', '.join(f'{k}=?' for k in f)} WHERE company=? AND source=?",
                    (*f.values(), company, source))


def _problem(c: Company, kind: str, summary: str, detail: str, since: str | None, alert_key: str,
             restore_kv: dict | None = None, restore_row: dict | None = None) -> dict:
    p = {"key": c.key, "name": c.name, "checker": c.checker, "kind": kind, "summary": summary, "detail": detail,
         "since": since or iso(), "careers_url": (c.careers_url or [""])[0], "reset_kv": alert_key}
    # what the check saved before raising the alert, put back if the health email fails (restore())
    if restore_kv:
        p["restore_kv"] = restore_kv
    if restore_row:
        p["restore_row"] = restore_row
    return p


def restore(db: DB, p: dict) -> None:
    """The health email carrying `p` did not go out: put back the baseline its check had already moved on, so the
    next run raises the same alert again (runner._reopen_alerts)."""
    for k, v in (p.get("restore_kv") or {}).items():
        db.set(k, v)
    r = p.get("restore_row")
    if r:
        db.conn.execute("UPDATE source_health SET baseline=?, last_count=?, zero_streak=?, drop_streak=? "
                        "WHERE company=? AND source=?", (r["baseline"], r["last_count"], r["zero_streak"],
                                                         r["drop_streak"], r["company"], r["source"]))


def _due(db: DB, alert_key: str, every: timedelta, now) -> bool:
    last = parse_iso(db.get(alert_key) or None)
    return last is None or now - last >= every


def observe(cfg: Config, db: DB, c: Company, o: Outcome, verdict, known) -> tuple[list[dict], list[dict]]:
    """Judge one processed poll. Returns (problems, recovered) for the run's health email."""
    if not (o.ok and not o.degraded and not o.partial and not o.unchanged and o.mode == "full" and o.jobs is not None):
        return [], []
    if (verdict.problem and verdict.problem.get("kind") in ("zero", "drop")) or db.get(f"zero_open:{c.key}"):
        return [], []
    p = settings(cfg)
    ensure_schema(db)
    now = utcnow()
    problems, recovered = [], []
    for sid, (what, n) in source_counts(c, o).items():
        _count_rules(db, c, sid, what, n, p, now, problems, recovered)
    _stale_rule(db, c, o, known, p, now, problems, recovered)
    return problems, recovered


def _count_rules(db, c, sid, what, n, p, now, problems, recovered) -> None:
    r = _row(db, c.key, sid)
    base = r["baseline"] if r else None
    key = f"live_alert:{c.key}:{sid}:empty"
    if r and r["empty_since"]:
        if n == 0:
            if _due(db, key, p["remind"], now):
                problems.append(_problem(c, "board empty", f"{what} still lists 0 jobs (reminder)",
                                         "It used to list jobs. The board may be dead or replaced by another one.",
                                         r["empty_since"], key))
                db.set(key, iso(now))
            _save(db, c.key, sid, what, last_count=0)
            return
        recovered.append({"key": c.key, "name": c.name, "summary": f"{what} lists jobs again ({n})"})
        db.set(key, "")
        _save(db, c.key, sid, what, empty_since=None, zero_streak=0, drop_streak=0, baseline=n, last_count=n)
        return
    if base and n == 0:
        streak = (r["zero_streak"] or 0) + 1
        if streak >= p["after"]:
            problems.append(_problem(c, "board empty", f"{what} now lists 0 jobs (it listed {base})",
                                     "The board may be dead, replaced by another one, or between hiring seasons. "
                                     "The rest of the company's jobs are still read.", None, key))
            db.set(key, iso(now))
            _save(db, c.key, sid, what, empty_since=iso(now), zero_streak=streak, last_count=0)
        else:
            _save(db, c.key, sid, what, zero_streak=streak, last_count=0)
        return
    if base and base >= p["min_base"] and n < base * (1 - p["threshold"]):
        streak = (r["drop_streak"] or 0) + 1
        if streak >= p["after"]:
            dkey = f"live_alert:{c.key}:{sid}:drop"
            before = {"company": c.key, "source": sid, "baseline": base, "last_count": r["last_count"],
                      "zero_streak": r["zero_streak"], "drop_streak": r["drop_streak"]}
            problems.append(_problem(c, "board drop", f"{what} fell {100 * (base - n) / base:.0f}% ({base} → {n})",
                                     "More than half of this board's jobs disappeared at once.", None, dkey,
                                     restore_row=before))
            db.set(dkey, iso(now))
            _save(db, c.key, sid, what, baseline=n, drop_streak=0, zero_streak=0, last_count=n)
        else:
            _save(db, c.key, sid, what, drop_streak=streak, zero_streak=0, last_count=n)
        return
    _save(db, c.key, sid, what, baseline=n, last_count=n, zero_streak=0, drop_streak=0)


def newest_and_gap(posted: list[str]) -> tuple[date | None, float | None]:
    """The newest posting date and the median gap in days between the distinct posting dates (newest 30)."""
    days = sorted({d for d in (_date(x) for x in posted) if d}, reverse=True)[:30]
    if not days:
        return None, None
    gaps = [(a - b).days for a, b in zip(days, days[1:])]
    return days[0], (statistics.median(gaps) if gaps else None)


def _date(x) -> date | None:
    try:
        return date.fromisoformat(str(x)[:10]) if x else None
    except ValueError:
        return None


def _stale_rule(db, c, o, known, p, now, problems, recovered) -> None:
    """A source whose newest posting is too old for its usual pace (the whole company when it has one source)."""
    groups: dict[str, tuple[str, list]] = {}
    ids: list[str] = []
    if c.checker == "multi":
        from .checkers.multi import _source_ids
        srcs = [(i, get_checker(x["checker"]), x.get("settings") or {})
                for i, x in enumerate((c.settings or {}).get("sources") or [])]
        ids = _source_ids(srcs)
    for j in o.jobs or []:
        i = int(j.extra.get("source", 0) or 0)
        sid = ids[i] if i < len(ids) else WHOLE
        what = f"{sid.split(':')[0]} source {i + 1}" if sid != WHOLE else "the job list"
        groups.setdefault(sid, (what, []))[1].append(j)
    today = now.date()
    for sid, (what, jobs) in groups.items():
        posted = [j.posted for j in jobs if j.posted]
        if any(j.id not in known for j in jobs) and known:
            posted.append(today.isoformat())  # a posting seen for the first time today counts as new
        if len(posted) < p["stale_min_dated"]:
            continue
        newest, gap = newest_and_gap(posted)
        if newest is None:
            continue
        limit = max(p["stale_days"], p["gap_factor"] * (gap or 0))
        age = (today - newest).days
        key = f"live_alert:{c.key}:{sid}:stale"
        r = _row(db, c.key, f"stale {sid}")
        if age > limit:
            since = r["stale_since"] if r and r["stale_since"] else iso(now)
            if _due(db, key, p["stale_remind"], now):
                usual = f"; it usually posts every ~{gap:.0f} days" if gap else ""
                problems.append(_problem(
                    c, "board stale", f"no new posting on {what} in {age} days{usual}",
                    "The board may have been abandoned, or the company now posts somewhere else: check its careers page.",
                    since, key))
                db.set(key, iso(now))
            _save(db, c.key, f"stale {sid}", what, stale_since=since)
        elif r and r["stale_since"]:
            recovered.append({"key": c.key, "name": c.name, "summary": f"new postings on {what} again"})
            db.set(key, "")
            _save(db, c.key, f"stale {sid}", what, stale_since=None)


# run-level rules -------------------------------------------------------------------------------

def unchecked(cfg: Config, db: DB, due: list[Company], processed: set[str]) -> tuple[list[dict], list[dict]]:
    """A company due in `unchecked_runs` runs in a row that was never processed (no health verdict at all)."""
    p = settings(cfg)
    problems, recovered = [], []
    for c in due:
        key, akey = f"unchecked_runs:{c.key}", f"live_alert:{c.key}:unchecked"
        if c.key in processed:
            if db.get(key):
                db.set(key, "")
            if db.get(akey):
                recovered.append({"key": c.key, "name": c.name, "summary": "checked again"})
                db.set(akey, "")
            continue
        n = int(db.get(key) or 0) + 1
        db.set(key, str(n))
        st = db.one("SELECT alert_open FROM company_state WHERE company=?", c.key)
        if n >= p["unchecked_runs"] and not (st and st["alert_open"]) and _due(db, akey, timedelta(days=1), utcnow()):
            problems.append(_problem(c, "not checked", f"not checked in the last {n} runs",
                                     "It was due but never processed: skipped at the run time limit, or storing its "
                                     "jobs failed (see data/logs). Its new postings are not being emailed.", None, akey))
            db.set(akey, iso())
    return problems, recovered


def config_keys(c: Company) -> set[str]:
    """The hiring systems a company is configured to read, as detect.from_text would name them."""
    out = set()

    def one(checker, s):
        boards = list(s.get("boards") or []) or [s.get("board")]
        sites = list(s.get("sites") or []) or [s.get("site")]
        for b in boards:
            for site in sites:
                d = {k: v for k, v in {**s, "board": b, "site": site}.items() if k in IDKEYS and v}
                out.add(system_key(checker, d))

    s = c.settings or {}
    if c.checker == "multi":
        for x in s.get("sources") or []:
            one(x["checker"], x.get("settings") or {})
    else:
        one(c.checker, s)
    return out


def system_key(checker: str, s: dict) -> str:
    return checker + ":" + ",".join(f"{k}={str(s[k]).lower()}" for k in sorted(s) if k in IDKEYS and s[k])


def workday_sites(text: str) -> set[str]:
    """Site names a Workday tenant's robots.txt lists ("Allow: /<site>/", "Sitemap: …/<site>/siteMap.xml")."""
    import re
    return set(re.findall(r"(?im)^allow:\s*/([\w-]+)/\s*$", text or "")) | set(
        re.findall(r"(?im)^sitemap:\s*https?://[^/]+/([\w-]+)/sitemap\.xml", text or ""))


def scan_workday_sites(cfg: Config, db: DB, gate) -> list[dict]:
    """New Workday sites in the tenants' cached robots.txt (no request: the checks keep it fresh)."""
    problems = []
    tenants: dict[str, tuple[Company, set[str]]] = {}
    for c in cfg.active:
        s = c.settings or {}
        srcs = [(x["checker"], x.get("settings") or {}) for x in s.get("sources") or []] if c.checker == "multi" \
            else [(c.checker, s)]
        for checker, st in srcs:
            if checker == "workday" and st.get("host") and "myworkdaysite" not in st["host"]:
                configured = set(st.get("sites") or [st.get("site")])
                prev = tenants.get(st["host"])
                tenants[st["host"]] = (prev[0] if prev else c, (prev[1] if prev else set()) | configured)
    for host, (c, configured) in sorted(tenants.items()):
        disk = gate._disk_get(f"https://{host}")
        if not disk or disk[0] != 200:
            continue
        sites = workday_sites(disk[1])
        key = f"workday_sites:{host}"
        known = db.get(key)
        if known is None or known == "":
            db.set(key, json.dumps(sorted(sites)))  # first look: a silent baseline
            continue
        new = sorted(sites - set(json.loads(known)) - configured)
        if new:
            akey = f"live_alert:{c.key}:workday-sites"
            problems.append(_problem(c, "new site", f"Workday tenant {host} lists new sites: {', '.join(new)}",
                                     "A new site can hold postings InternWatch doesn't read (Fidelity's 'targeted' "
                                     "held most of its internships). Add it to the config if it has student roles.",
                                     None, akey, restore_kv={key: known}))
            db.set(akey, iso())
        db.set(key, json.dumps(sorted(sites | set(json.loads(known)))))
    return problems


def scan_pages(cfg: Config, db: DB, http, budget_end: float) -> list[dict]:
    """Read careers pages not looked at for `page_scan_days`, oldest first, until `budget_end` (time.monotonic())."""
    from .detect import from_text  # detect imports the runner
    p = settings(cfg)
    now = utcnow()
    problems = []
    todo = []
    for c in cfg.active:
        if not c.careers_url:
            continue
        last = parse_iso(db.get(f"page_scan_at:{c.key}") or None)
        if last is None or now - last >= p["scan_every"]:
            todo.append((last or now - timedelta(days=3650), c))
    for _, c in sorted(todo, key=lambda x: x[0]):
        if time.monotonic() > budget_end:
            break
        url = c.careers_url[0]
        scanned = db.get(f"page_scan_at:{c.key}")
        db.set(f"page_scan_at:{c.key}", iso(now))
        try:
            # */* too: Wolfram's server types its page application/x-httpd-php and answers 406 to text/html alone
            text = http.get_text(url, headers={"Accept": "text/html,*/*;q=0.8"})
        except Exception as e:  # noqa: BLE001 — an unreadable page (bot wall, robots) is only logged
            log.info("liveness: careers page of %s not read: %s", c.key, str(e)[:160])
            continue
        seen = {system_key(x.checker, x.settings) for x in from_text(text, url)}
        key = f"page_systems:{c.key}"
        raw = before = db.get(key)
        db.set(key, json.dumps(sorted(seen)))
        if before is None or before == "":
            continue  # first look: a silent baseline
        before = set(json.loads(before))
        configured = config_keys(c)
        new = sorted(seen - before - configured)
        gone = sorted((before & configured) - seen)
        if new or gone:
            akey = f"live_alert:{c.key}:moved"
            parts = ([f"now points at {', '.join(new)}"] if new else []) + \
                    ([f"no longer mentions {', '.join(gone)}"] if gone else [])
            problems.append(_problem(c, "moved?", f"the careers page {' and '.join(parts)}",
                                     f"InternWatch reads {', '.join(sorted(configured))}. The jobs may have moved to "
                                     f"another job site: compare {url} with the config.", None, akey,
                                     restore_kv={key: raw, f"page_scan_at:{c.key}": scanned or ""}))
            db.set(akey, iso())
    return problems


def status(cfg: Config, db) -> str:
    """What the dead-board checks are tracking (read-only)."""
    lines = []
    try:
        rows = db.execute("SELECT * FROM source_health ORDER BY company, source").fetchall()
    except Exception:  # noqa: BLE001 — no table before the first run with these checks
        rows = []
    open_ = [r for r in rows if r["empty_since"] or r["stale_since"]]
    lines.append(f"{len(rows)} sources tracked, {len(open_)} with an open alert")
    for r in open_:
        lines.append(f"  {r['company']}: {r['label'] or r['source']}: "
                     + (f"empty since {r['empty_since']}" if r["empty_since"] else f"stale since {r['stale_since']}"))
    kv = {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM kv WHERE key LIKE 'unchecked_runs:%' "
                                                   "OR key LIKE 'page_scan_at:%' OR key LIKE 'workday_sites:%'")}
    unchecked_ = {k.split(":", 1)[1]: v for k, v in kv.items() if k.startswith("unchecked_runs:") and v}
    lines.append(f"not processed in the last runs: {unchecked_ or 'none'}")
    scans = [v for k, v in kv.items() if k.startswith("page_scan_at:") and v]
    lines.append(f"careers pages compared: {len(scans)} of {len(cfg.active)}" + (f", last {max(scans)}" if scans else ""))
    lines.append(f"Workday tenants compared: {sum(1 for k in kv if k.startswith('workday_sites:'))}")
    return "\n".join(lines)
