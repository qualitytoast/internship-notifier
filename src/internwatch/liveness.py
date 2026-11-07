"""Notice a board that went dead, was abandoned or was replaced: what the company-wide health rules (health.py) can't see.

1. Per source, after each poll that read everything (not degraded, not cut short, not "unchanged"):
   source = a board or Workday site of a company that reads several, a multi source, an Eightfold quick query
   (FetchContext.source_counts), or a student slice of Apple, Meta or Amazon.
   emptied  a source that listed jobs lists none on two polls in a row: alert, kept open until it lists jobs again
   dropped  it lost more than half of at least 6 jobs on two polls in a row: alerted once, the new count accepted
   quiet    no new job id on a board for `quiet_days`, whatever its size: alert, open until a new one appears
   Per company: slow bleed (under half its highest count of the last `bleed_days`) and internships vanished (nearly
   all its student roles gone at once while its other jobs stay).
   Nothing is judged while the company itself is failing or its zero/drop alert is out (that alert already says it).
2. Companies not checked: due in `unchecked_runs` runs in a row but never processed (skipped at the run deadline, a
   crash while storing its jobs, a company added and never run).
3. In daily runs, with time to spare: each company's careers page is read once and the hiring systems it
   points at (detect.from_text, plus links to an Eightfold site) are compared with the last time, each iCIMS portal,
   Avature portal and Eightfold domain on its own; a new one that isn't configured, or a configured one it no longer
   mentions (for those three: no portal of it at all) on two reads in a row, alerts ("moved"). Every system a page ever
   named is remembered, so a page that flips back and forth alerts once. A portal the page linked on an earlier look,
   or that a stored posting links, is not new. A read the site refused (bot check, 5xx, timeout) is retried once,
   first the next morning, then waits REFUSED_DAYS; robots.txt blocks never are retried. Workday tenants' robots.txt, already cached by the checks (no
   request), is compared with the configured sites: a new site alerts. The first look at a page or tenant is a
   silent baseline.
Every alert goes into the run's health email with reset_kv="live_alert:…", so an email that fails is sent again, and
onto the list in alerts.py, which repeats it each morning until it clears.
State: table source_health, kv live_alert:*, unchecked_runs:*, page_systems:* (by system_key, as before),
page_systems_v2:* (by page_key), page_scan_at:*, page_scan_retry:*, workday_sites:*.
"""
from __future__ import annotations

import html
import json
import logging
import re
import time
from datetime import date, timedelta
from urllib.parse import urlsplit

from . import alerts
from .adapters import get_checker
from .config import Company, Config
from .db import DB, iso, parse_iso, utcnow
from .filters import is_student_role
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
# lists that are mostly student roles: they fall at every season's end, so a fall says nothing about the board
STUDENT_LISTS = ("amazon", "apple", "janestreet_programs", "program_pages")
REFUSED_DAYS = 7  # how long a careers page that refused waits (moves.REFUSED_DAYS for the checks there)


def settings(cfg: Config) -> dict:
    h = cfg.settings.get("health", default={}) or {}
    lv = cfg.settings.get("liveness", default={}) or {}
    return {"after": int(h.get("alert_after_failures", 2)), "threshold": float(h.get("drop_threshold", 0.5)),
            "min_base": int(h.get("drop_min_baseline", 6)),
            "quiet_days": float(lv.get("quiet_days", 45)), "bleed_days": int(lv.get("bleed_days", 30)),
            "unchecked_runs": int(lv.get("unchecked_runs", 2)),
            "scan_every": timedelta(days=float(lv.get("page_scan_days", 1))),
            "scan_seconds": float(lv.get("page_scan_seconds", 180)), "enabled": lv.get("enabled", True),
            "blocked_seconds": float(lv.get("blocked_scan_seconds", 150)),
            "watch_seconds": float(lv.get("watch_seconds", 360))}


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
             restore_kv: dict | None = None, restore_row: dict | None = None, *, alert: dict | None = None,
             items: list[dict] | None = None) -> dict:
    """`alert`: how the alert clears (alerts.py); `items`: the same for each thing it covers, when several clear apart."""
    p = {"key": c.key, "name": c.name, "checker": c.checker, "kind": kind, "summary": summary, "detail": detail,
         "since": since or iso(), "careers_url": (c.careers_url or [""])[0], "reset_kv": alert_key}
    if alert:
        p["alert"] = {"id": alert_key, **alert}
    if items:
        p["alerts"] = items
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
    if not (o.ok and not o.degraded and not o.partial and o.mode == "full"):
        return [], []
    if (verdict.problem and verdict.problem.get("kind") in ("zero", "drop")) or db.get(f"zero_open:{c.key}"):
        return [], []
    p = settings(cfg)
    ensure_schema(db)
    now = utcnow()
    problems, recovered = [], []
    if not o.unchanged and o.jobs is not None:
        for sid, (what, n) in source_counts(c, o).items():
            _count_rules(db, c, sid, what, n, p, now, problems, recovered)
        if verdict.healthy:  # an unhealthy poll is a drop or a zero on its first strike: those rules decide
            _bleed_rule(db, c, len(o.jobs), p, now, problems)
            _vanished_rule(db, c, sum(1 for j in o.jobs if is_student_role(j, cfg.rules, c.extra_role_re)), p, now, problems)
    _quiet_rule(db, c, o, known, p, now, problems, recovered)  # a feed that answers "unchanged" for ever goes quiet too
    return problems, recovered


def _count_rules(db, c, sid, what, n, p, now, problems, recovered) -> None:
    r = _row(db, c.key, sid)
    base = r["baseline"] if r else None
    key = f"live_alert:{c.key}:{sid}:empty"
    if r and r["empty_since"]:
        if n == 0:
            if not db.get(key):  # the email about it failed: raised again
                problems.append(_problem(c, "board empty", f"{what} still lists 0 jobs",
                                         "It used to list jobs. The board may be dead or replaced by another one.",
                                         r["empty_since"], key, alert={"rule": "source_empty", "source": sid}))
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
                                     "The rest of the company's jobs are still read.", None, key,
                                     alert={"rule": "source_empty", "source": sid}))
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
                                     restore_row=before, alert={"rule": "source_count", "source": sid,
                                                                "need": base * (1 - p["threshold"])}))
            db.set(dkey, iso(now))
            _save(db, c.key, sid, what, baseline=n, drop_streak=0, zero_streak=0, last_count=n)
        else:
            _save(db, c.key, sid, what, drop_streak=streak, zero_streak=0, last_count=n)
        return
    _save(db, c.key, sid, what, baseline=n, last_count=n, zero_streak=0, drop_streak=0)


def _date(x) -> date | None:
    try:
        return date.fromisoformat(str(x)[:10]) if x else None
    except ValueError:
        return None


def boards(c: Company, o: Outcome) -> dict[str, tuple[str, list]]:
    """{board id: (what it is, its jobs in this poll)}: each board, site or source a company reads, even an empty one;
    the company as one board when it reads just one."""
    s = c.settings or {}
    jobs = o.jobs or []
    out: dict[str, tuple[str, list]] = {}
    if c.checker == "multi":
        from .checkers.multi import _source_ids
        srcs = [(i, get_checker(x["checker"]), x.get("settings") or {}) for i, x in enumerate(s.get("sources") or [])]
        ids = _source_ids(srcs)
        for i, ck, st in srcs:
            for k, v in _subs(ck.type, st) or [("", "")]:
                out[f"{ids[i]} {k}:{v}" if k else ids[i]] = (f"{ck.type} source {i + 1}" + (f" ({k} {v})" if k else ""), [])
        for j in jobs:
            i = int(j.extra.get("source", 0) or 0)
            if i < len(srcs):
                subs = _subs(srcs[i][1].type, srcs[i][2])
                k = subs[0][0] if subs else ""
                sid = f"{ids[i]} {k}:{j.extra.get(k)}" if k else ids[i]
                out.setdefault(sid, (sid, []))[1].append(j)
        return out
    subs = _subs(c.checker, s)
    if not subs:
        return {WHOLE: ("the job list", list(jobs))}
    for k, v in subs:
        out[f"{k}:{v}"] = (f"{c.checker} {k} {v}", [])
    for j in jobs:
        sid = f"{subs[0][0]}:{j.extra.get(subs[0][0])}"
        out.setdefault(sid, (sid, []))[1].append(j)
    return out


def _quiet_rule(db, c, o, known, p, now, problems, recovered) -> None:
    """No new job id on a board for `quiet_days`, whatever its size. A feed's own dates can't be relied on (Workday's
    stop at "30+ days", many feeds have none), so the newest date is the latest of them and of the day InternWatch
    first saw a job there. A board with neither is judged from the day it was first read."""
    today = now.date()
    stored = {r["job_id"]: r for r in db.q("SELECT job_id, first_seen, baseline FROM jobs WHERE company=?", c.key)}
    for sid, (what, jobs) in boards(c, o).items():
        kv = f"board_new:{c.key}:{sid}"
        rows = [stored[j.id] for j in jobs if j.id in stored]
        dates = [_date(db.get(kv)), *(_date(j.posted) for j in jobs),
                 *(_date(r["first_seen"]) for r in rows if not r["baseline"])]
        if known and any(j.id not in known for j in jobs):
            dates.append(today)
        newest = max((d for d in dates if d and d <= today), default=None)
        if newest is None:
            first = [_date(r["first_seen"]) for r in rows]
            seeded = _date(db.state(c.key)["seeded_at"]) if sid == WHOLE else None
            newest = min([d for d in first if d] or [seeded or today])
        db.set(kv, newest.isoformat())
        age = (today - newest).days
        key, r = f"live_alert:{c.key}:{sid}:quiet", _row(db, c.key, f"stale {sid}")
        if age > p["quiet_days"]:
            if not db.get(key):
                problems.append(_problem(
                    c, "board quiet", f"no new job on {what} in {age} days",
                    "The board may have been abandoned, or the company now posts somewhere else: check its careers page.",
                    f"{newest.isoformat()}T00:00:00Z", key, alert={"rule": "quiet", "source": f"stale {sid}"}))
                db.set(key, iso(now))
            _save(db, c.key, f"stale {sid}", what, stale_since=r["stale_since"] if r and r["stale_since"] else iso(now))
        elif r and r["stale_since"]:
            recovered.append({"key": c.key, "name": c.name, "summary": f"new jobs on {what} again"})
            db.set(key, "")
            _save(db, c.key, f"stale {sid}", what, stale_since=None)


def _bleed_rule(db, c, n: int, p, now, problems) -> None:
    """A slow decline no single poll shows: under half the company's highest count of the last 30 days. Once per high."""
    if c.checker in STUDENT_LISTS:
        return
    since = iso(now - timedelta(days=p["bleed_days"]))
    high = max(n, db.one("SELECT MAX(jobs) m FROM checks WHERE company=? AND started_at>=?", c.key, since)["m"] or 0)
    akey, hkey = f"live_alert:{c.key}:bleed", f"bleed_high:{c.key}"
    if high < p["min_base"] or n >= high * (1 - p["threshold"]) or db.get(hkey) == str(high):
        return
    if alerts.live(db, c.key, "count"):  # its drop alert already says so
        return
    problems.append(_problem(c, "slow bleed", f"down to {n} jobs from {high} in the last {p['bleed_days']} days",
                             "No single poll lost enough to alert. The board may be winding down, or jobs moved elsewhere.",
                             None, akey, restore_kv={hkey: db.get(hkey) or ""},
                             alert={"rule": "count", "need": high * (1 - p["threshold"])}))
    db.set(hkey, str(high))
    db.set(akey, iso(now))


def vanished(history: list[int], minimum: int = 5, percent: int = 90) -> int | None:
    """The count student roles fell from, if nearly all of them went at once: `history` is the newest polls first, one
    a day. The last two polls must both show it (one could be a blip), against the two before. Internships closing
    one by one at the end of a season never do; a company moving them to another board does."""
    if len(history) < 3:
        return None
    high = max(history[2:4])
    return high if high >= minimum and 100 * (high - max(history[:2])) >= percent * high else None


def _vanished_rule(db, c, n: int, p, now, problems) -> None:
    if c.checker in STUDENT_LISTS or c.checker in SLICES:  # all of them, or a slice with its own board rules
        return
    history = [n] + [r["students"] or 0 for r in db.q("SELECT students FROM checks WHERE company=? ORDER BY id DESC LIMIT 4",
                                                      c.key)][1:]
    high = vanished(history)
    if high is None:
        return
    akey = f"live_alert:{c.key}:students"
    problems.append(_problem(c, "internships vanished", f"student roles fell {100 * (high - n) // high}% ({high} → {n})",
                             "Its other jobs are still listed. Hiring may have ended, or its internships moved to another "
                             "board: check its careers page.", None, akey, alert={"rule": "students", "need": high / 2}))
    db.set(akey, iso(now))


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
                                     "jobs failed (see data/logs). Its new postings are not being emailed.", None, akey,
                                     alert={"rule": "unchecked"}))
            db.set(akey, iso())
    return problems, recovered


def config_keys(c: Company, key=None) -> set[str]:
    """The hiring systems a company is configured to read, as detect.from_text would name them (system_key), or as
    the weekly page check names them (key=page_key)."""
    key = key or system_key
    out = set()

    def one(checker, s):
        boards = list(s.get("boards") or []) or [s.get("board")]
        sites = list(s.get("sites") or []) or [s.get("site")]
        for b in boards:
            for site in sites:
                out.add(key(checker, {k: v for k, v in {**s, "board": b, "site": site}.items() if v}))

    s = c.settings or {}
    if c.checker == "multi":
        for x in s.get("sources") or []:
            one(x["checker"], x.get("settings") or {})
    else:
        one(c.checker, s)
    return out


def system_key(checker: str, s: dict) -> str:
    return checker + ":" + ",".join(f"{k}={str(s[k]).lower()}" for k in sorted(s) if k in IDKEYS and s[k])


PORTALS = ("icims", "avature", "eightfold")  # each iCIMS portal, Avature portal and Eightfold domain is a system
NOT_A_PORTAL = {"icims:portal=cookie-policy-scripts.icims.com"}  # iCIMS's cookie script on SIG's page
AVATURE_LINK = re.compile(r"https?://[\w.-]+\.avature\.net/[\w%/.-]*")


def page_key(checker: str, s: dict) -> str:
    """system_key, but an iCIMS portal, an Avature portal and an Eightfold domain each count on their own, as
    moves.system_key_v2 keys them for the 32 blocked companies (except Avature, which it keys by host)."""
    from .moves import system_key_v2  # moves imports this module
    if checker == "avature" and s.get("list_url"):
        return avature_key(s["list_url"])
    return system_key_v2(checker, s) if checker in PORTALS else system_key(checker, s)


def avature_key(url: str) -> str:
    """An Avature portal: its host and the first part of its path after a locale (bloomberg.avature.net/careers)."""
    p = urlsplit(url)
    path = [x for x in p.path.split("/") if x]
    if path and re.fullmatch(r"[a-z]{2}_[a-z]{2}", path[0], re.I):
        path = path[1:]
    return f"avature:site={p.netloc.lower()}/{(path[0] if path else '').lower()}"


def page_systems(text: str, found) -> set[str]:
    """The job systems a careers page points at, keyed by page_key: what detect.from_text found in it (`found`), every
    Avature link (also one without the "/" detect needs after the portal) and every link to an Eightfold site, read
    with the HTML and JSON escaping around them undone. iCIMS's own hosts are not portals."""
    from . import moves  # moves imports this module
    seen = {page_key(x.checker, x.settings) for x in found if x.checker != "avature"}
    if "avature.net" in text or "eightfold.ai" in text:
        plain = html.unescape(html.unescape(text)).replace("\\u0026", "&").replace("\\/", "/")
        seen.update(avature_key(m[0]) for m in AVATURE_LINK.finditer(plain))
        for rx, build in moves.EXTRA_PATTERNS:  # the links moves.py knows besides detect's; only Eightfold's count
            for m in re.finditer(rx, plain):
                k = build(m)
                if k.startswith("eightfold:domain="):
                    domain = re.match(r"[\w.-]*", k.removeprefix("eightfold:domain="))[0]  # drops a JSON-escaped quote
                    if domain:
                        seen.add("eightfold:domain=" + domain)
    return {k for k in seen if not moves.NOT_A_SYSTEM.match(k) and k not in NOT_A_PORTAL}


def _portal(k: str) -> bool:
    return k.split(":", 1)[0] in PORTALS


def _system(k: str) -> str:
    """What counts as still mentioned: any portal of the same system, any other system itself."""
    return k.split(":", 1)[0] + ":" if _portal(k) else k


def posting_portals(db: DB, company: str) -> set[str]:
    """The portals the company's stored postings link (Atlassian's postings carry their iCIMS portal)."""
    from .detect import from_text  # detect imports the runner
    urls = "\n".join(r["url"] or "" for r in db.q("SELECT url FROM jobs WHERE company=?", company))
    return {k for k in page_systems(urls, from_text(urls, "")) if _portal(k)}


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
        alerts.seen(db, c.key, "site", sites, scope=host)
        if new:
            akey = f"live_alert:{c.key}:workday-sites"
            problems.append(_problem(c, "new site", f"Workday tenant {host} lists new sites: {', '.join(new)}",
                                     "A new site can hold postings InternWatch doesn't read (Fidelity's 'targeted' "
                                     "held most of its internships). Add it to the config if it has student roles.",
                                     None, akey, restore_kv={key: known},
                                     items=[{"id": f"{akey}:{x}", "rule": "site", "item": x, "scope": host,
                                             "summary": f"Workday tenant {host} lists a new site: {x}"} for x in new]))
            db.set(akey, iso())
        db.set(key, json.dumps(sorted(sites | set(json.loads(known)))))
    return problems


def scan_pages(cfg: Config, db: DB, http, budget_end: float) -> list[dict]:
    """Read careers pages not looked at today, oldest first, until `budget_end` (time.monotonic()). A page whose read
    failed goes first the next morning, every morning. One the site refused goes first the next morning, and if it
    refuses again waits REFUSED_DAYS."""
    from .detect import from_text  # detect imports the runner
    from .moves import outcome, record  # moves imports this module
    p = settings(cfg)
    now = utcnow()
    problems = []
    todo = []
    blocked = set((cfg.settings.get("liveness", default={}) or {}).get("blocked") or [])
    for c in cfg.active:
        if not c.careers_url or c.key in blocked:  # pages that refuse scripts: moves.py watches those companies
            continue
        last = parse_iso(db.get(f"page_scan_at:{c.key}") or None)
        retry = bool(db.get(f"page_scan_retry:{c.key}"))
        every = timedelta(days=REFUSED_DAYS) if db.get(f"page_scan_refused:{c.key}") else p["scan_every"]
        if retry or last is None or now - last >= every - timedelta(hours=12):  # by hand, runs drift by some hours
            todo.append((not retry, last or now - timedelta(days=3650), c))
    for *_, c in sorted(todo, key=lambda x: x[:2]):
        if time.monotonic() > budget_end:
            break
        url = c.careers_url[0]
        scanned = db.get(f"page_scan_at:{c.key}")
        rkey = f"page_scan_retry:{c.key}"
        retried = db.get(rkey)
        try:
            # */* too: Wolfram's server types its page application/x-httpd-php and answers 406 to text/html alone
            text = http.get_text(url, headers={"Accept": "text/html,*/*;q=0.8"})
        except Exception as e:  # noqa: BLE001 — an unreadable page (bot wall, robots) is only logged
            log.info("liveness: careers page of %s not read: %s", c.key, str(e)[:160])
            result = outcome(e)
            record(db, "careers", c.key, result, now)
            if result == "failed":  # 5xx, a timeout, a missing page: read again first thing next morning, every morning
                db.set(rkey, "1")
                db.set(f"page_scan_refused:{c.key}", "")
            elif result == "refused" and not retried and not db.get(f"page_scan_refused:{c.key}"):
                db.set(rkey, "1")  # a bot check: read again first thing next morning
            else:  # robots.txt, or refused again: its next turn is next week
                db.set(f"page_scan_at:{c.key}", iso(now))
                db.set(f"page_scan_refused:{c.key}", "1")
                if retried:
                    db.set(rkey, "")
            continue
        db.set(f"page_scan_at:{c.key}", iso(now))  # before the parsing: a page it chokes on must not stay due
        record(db, "careers", c.key, "ok", now)
        if retried:
            db.set(rkey, "")
        if db.get(f"page_scan_refused:{c.key}"):
            db.set(f"page_scan_refused:{c.key}", "")
        found = from_text(text, url)
        old_seen = {system_key(x.checker, x.settings) for x in found}
        seen = page_systems(text, found)
        key, key2 = f"page_systems:{c.key}", f"page_systems_v2:{c.key}"
        raw, raw2 = db.get(key), db.get(key2)
        prev = json.loads(raw2) if raw2 else None
        db.set(key, json.dumps(sorted(old_seen)))  # as before portals counted on their own
        ever = set((prev or {}).get("ever") or (prev or {}).get("systems") or [])  # flipping pages alert once
        told = set((prev or {}).get("told") or [])
        absent: dict[str, int] = {}
        gone_now: list[str] = []
        if prev is not None:
            configured = config_keys(c, page_key)
            was, mentioned = {_system(k) for k in ever}, {_system(k) for k in seen}
            absent = {k: (prev.get("absent") or {}).get(k, 0) + 1 for k in configured
                      if _system(k) in was and _system(k) not in mentioned}
            gone_now = sorted(k for k, n in absent.items() if n >= 2 and k not in told)
        db.set(key2, json.dumps({"systems": sorted(seen), "ever": sorted(ever | seen), "absent": absent,
                                 "told": sorted(told | set(gone_now)),
                                 "portals": sorted(  # every portal it ever linked
                                     {k for k in seen if _portal(k)} | set(prev["portals"] if prev else []))}))
        if prev is None and (raw is None or raw == ""):
            continue  # first look: a silent baseline
        if prev is None:  # the first look since portals count on their own: compared with the last look as before
            before, configured = set(json.loads(raw)), config_keys(c)
            new = sorted(old_seen - before - configured)
            gone = sorted((before & configured) - old_seen)
        else:
            new = seen - ever - set(prev["portals"]) - configured
            if any(_portal(k) for k in new):
                new -= posting_portals(db, c.key)  # InternWatch already reads postings there
            new = sorted(new)
            gone = gone_now
        alerts.seen(db, c.key, "system_new", seen | old_seen, scope="page", needed=2)
        alerts.back(db, c.key, "system_gone", {_system(k) for k in seen | old_seen}, scope="page")
        if new or gone:
            akey = f"live_alert:{c.key}:moved"
            parts = ([f"now points at {', '.join(new)}"] if new else []) + \
                    ([f"no longer mentions {', '.join(gone)}"] if gone else [])
            problems.append(_problem(c, "moved?", f"the careers page {' and '.join(parts)}",
                                     f"InternWatch reads {', '.join(sorted(configured))}. The jobs may have moved to "
                                     f"another job site: compare {url} with the config.", None, akey,
                                     restore_kv={key: raw or "", key2: raw2 or "",
                                                 f"page_scan_at:{c.key}": scanned or ""},
                                     items=[{"id": f"{akey}:new:{k}", "rule": "system_new", "item": k, "scope": "page",
                                             "summary": f"the careers page now points at {k}"} for k in new]
                                     + [{"id": f"{akey}:gone:{k}", "rule": "system_gone", "item": _system(k), "system": k,
                                         "scope": "page", "summary": f"the careers page no longer mentions {k}"}
                                        for k in gone]))
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
                     + (f"empty since {r['empty_since']}" if r["empty_since"] else f"quiet since {r['stale_since']}"))
    kv = {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM kv WHERE key LIKE 'unchecked_runs:%' "
                                                   "OR key LIKE 'page_scan_at:%' OR key LIKE 'page_scan_retry:%' "
                                                   "OR key LIKE 'workday_sites:%'")}
    unchecked_ = {k.split(":", 1)[1]: v for k, v in kv.items() if k.startswith("unchecked_runs:") and v}
    lines.append(f"not processed in the last runs: {unchecked_ or 'none'}")
    scans = [v for k, v in kv.items() if k.startswith("page_scan_at:") and v]
    retry = sum(1 for k, v in kv.items() if k.startswith("page_scan_retry:") and v)
    lines.append(f"careers pages compared: {len(scans)} of {len(cfg.active)}" + (f", last {max(scans)}" if scans else "")
                 + (f"; {retry} refused, read again tomorrow" if retry else ""))
    lines.append(f"Workday tenants compared: {sum(1 for k in kv if k.startswith('workday_sites:'))}")
    return "\n".join(lines)
