"""Notice when a company whose careers page InternWatch can't read starts posting jobs somewhere new.

The companies are named in settings `liveness.blocked`: the 31 whose careers page answers scripts with a bot check,
an HTTP 400 or a robots.txt block, so the weekly page check (liveness.scan_pages) never sees where they point. Only
those companies are read here. Nothing here stores a job or touches a poll: every check compares what it sees now
with its own last look and raises a health alert for what is new. The first look of each check is a silent
baseline. The checks run once a morning in daily runs, within `blocked_scan_seconds`, before the emails.

  W  Workday tenants' robots.txt: hidden sites (Disallow lines), plus tenants of a parent company (extra_tenants)
  P  the careers page and any WordPress pages (/wp-json/wp/v2/pages): job systems they name, keyed per iCIMS
     portal, Avature site and Eightfold domain; job ids on the page that InternWatch has never stored
  A  archive.org's copies: new pages under the careers paths, job ids in them, systems named in the newest copies
  J  the company's own job list (sitemap or job file) against every job InternWatch has stored
  N  new student and program pages in sitemaps, WordPress page lists and Goldman's programs feed
  G  new labels: Goldman's experience and source types, Meta's team labels (from its poll, no request)
  S  parallel boards read with the existing adapters: a matching role InternWatch doesn't have
  L  third-party lists and board registries, and Getro boards that read the careers page: a job system for one of
     these companies that the config doesn't name

A job id seen where InternWatch has no such job is only reported once a healthy poll of the company on a later run
still doesn't have it (a posting can simply be newer than this morning's poll).
A read refused by the site (bot check, 5xx, timeout) is retried once the next morning; robots.txt blocks never are.
State: kv blocked:* (and live_alert:<key>:<check> for open alerts), each restored if the health email fails.
"""
from __future__ import annotations

import html as htmllib
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from . import liveness
from .config import Company, Config
from .db import DB, iso, parse_iso, utcnow
from .models import CheckTimeout, RobotsBlocked

log = logging.getLogger(__name__)

STUDENT = re.compile(r"intern|co-?op|student|campus|early[-_ ]?(?:career|talent)|universit|graduate|program|fellow|"
                     r"residen|emerging|apprentic|scholar|discover|insight|explore|sneak|academy|summit|datathon|"
                     r"invitational|bootcamp|externship", re.I)


# companies and settings ---------------------------------------------------------------------

def opts(cfg: Config) -> dict:
    return cfg.settings.get("liveness", default={}) or {}


def blocked(cfg: Config) -> dict[str, Company]:
    """The companies these checks may read: active and named in liveness.blocked."""
    keys = set(opts(cfg).get("blocked") or [])
    return {c.key: c for c in cfg.active if c.key in keys}


def per_company(cfg: Config, name: str) -> dict:
    """Setting liveness.<name> ({company key: value}) for the blocked companies only; any other key is ignored."""
    comps = blocked(cfg)
    out = {}
    for k, v in (opts(cfg).get(name) or {}).items():
        if k in comps:
            out[k] = v
        else:
            log.warning("moves: liveness.%s names %s, which is not in liveness.blocked: ignored", name, k)
    return out


def entries(cfg: Config, name: str) -> list[dict]:
    """Setting liveness.<name> ([{company: key, …}]) for the blocked companies only."""
    comps = blocked(cfg)
    out = []
    for x in opts(cfg).get(name) or []:
        if x.get("company") in comps:
            out.append(x)
        else:
            log.warning("moves: liveness.%s names %s, which is not in liveness.blocked: ignored", name, x.get("company"))
    return out


@dataclass
class Ctx:
    cfg: Config
    db: DB
    gate: object                  # http.HostGate: robots.txt rules of an archived copy's own site
    make_http: object             # (deadline, retries=1, read_timeout=None) -> Http
    budget_end: float             # time.monotonic() after which no check starts a read
    healthy: set                  # companies whose poll in this run was ok, complete and full
    now: object = field(default_factory=utcnow)
    started: str = field(default_factory=iso)

    @property
    def comps(self) -> dict[str, Company]:
        return blocked(self.cfg)

    def out_of_time(self) -> bool:
        return time.monotonic() > self.budget_end

    def http(self, **kw):
        return self.make_http(self.budget_end, **kw)


# when each (check, company) is read ---------------------------------------------------------

def pick(db: DB, check: str, keys: list[str], every_days: float, now) -> list[str]:
    """Due for `check` today: yesterday's refused reads (outside the quota), then the oldest due ones, at most a
    1/every_days share of them a day so a weekly check spreads over the week (never-read ones first)."""
    retry = [k for k in keys if db.get(f"blocked:retry:{check}:{k}")]
    due = []
    for k in keys:
        if k in retry:
            continue
        last = parse_iso(db.get(f"blocked:at:{check}:{k}") or None)
        if last is None or now - last >= timedelta(days=every_days) - timedelta(hours=12):
            due.append((last.isoformat() if last else "", k))
    quota = len(due) if every_days <= 1 else math.ceil(len(keys) / every_days)
    return retry + [k for _, k in sorted(due)[:quota]]


def outcome(e: Exception) -> str:
    """refused: a bot check, 5xx, timeout (retried once the next morning); failed: robots.txt, 401/404/410."""
    if isinstance(e, RobotsBlocked):
        return "failed"
    m = re.search(r"HTTP (\d{3})", str(e))
    return "failed" if m and m.group(1) in ("401", "404", "410") else "refused"


def out_of_budget(e: Exception) -> bool:
    return isinstance(e, CheckTimeout) and "time budget" in str(e)


def done(db: DB, check: str, key: str, result: str, now) -> None:
    """Record a read: ok, failed, or refused (a first refusal is retried the next morning; a second one waits)."""
    rkey = f"blocked:retry:{check}:{key}"
    if result == "refused" and not db.get(rkey):
        db.set(rkey, "1")
    else:
        db.set(rkey, "")
        db.set(f"blocked:at:{check}:{key}", iso(now))
    k = f"blocked:rate:{check}:{key}"
    since = (now - timedelta(days=28)).date().isoformat()
    hist = [x for x in json.loads(db.get(k) or "[]") if x[0] >= since]
    db.set(k, json.dumps(hist + [[now.date().isoformat(), 1 if result == "ok" else 0]]))


def due_restore(db: DB, check: str, key: str) -> dict:
    """kv to put back with an alert so a failed health email makes the read due (and the alert raised) again."""
    return {f"blocked:at:{check}:{key}": db.get(f"blocked:at:{check}:{key}") or ""}


def alert(db: DB, c: Company, check: str, kind: str, summary: str, detail: str, restore_kv: dict) -> dict:
    akey = f"live_alert:{c.key}:{check}"
    p = liveness._problem(c, kind, summary, detail, None, akey, restore_kv=restore_kv)
    db.set(akey, iso())
    return p


def load(db: DB, key: str, default):
    raw = db.get(key)
    return json.loads(raw) if raw else default


# jobs InternWatch has stored ------------------------------------------------------------------

def stored_tokens(db: DB, company: str) -> set[str]:
    """Every word of every stored job's id, URL and alternative ids (ids carry prefixes: workday:/job/…_R123)."""
    toks: set[str] = set()
    for r in db.q("SELECT job_id, url, alt_ids FROM jobs WHERE company=?", company):
        for x in (r["job_id"], r["url"], r["alt_ids"]):
            toks.update(t.lower() for t in re.findall(r"[A-Za-z0-9]+", x or ""))
    return toks


def is_stored(ident: str, toks: set[str]) -> bool:
    i = ident.lower()
    if i in toks:
        return True
    long = re.findall(r"\d{5,}", i)  # jr-202622954 is stored as …_JR-202622954
    return bool(long) and all(d in toks for d in long)


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def stored_titles(db: DB, company: str, days: int = 30) -> set[str]:
    """Titles of the company's jobs open now or closed within `days` (a twin of a stored posting is no news)."""
    since = iso(utcnow() - timedelta(days=days))
    return {norm_title(r["title"]) for r in db.q("SELECT title FROM jobs WHERE company=? AND (removed_at IS NULL "
                                                 "OR removed_at >= ?)", company, since)}


def student_like(title: str) -> bool:
    return bool(STUDENT.search(title or ""))


def note_unknown(db: DB, check: str, c: Company, found: dict[str, str], where: str, started: str) -> None:
    """Job ids seen on a source but not stored: kept until a later healthy poll confirms (confirm())."""
    if not found:
        return
    k = f"blocked:pending:{check}:{c.key}"
    pending = load(db, k, {})
    for ident, title in found.items():
        pending.setdefault(ident, {"title": title, "found": started, "where": where})
    db.set(k, json.dumps(pending))


def confirm(ctx: Ctx, check: str, label: str, any_job: bool = False) -> list[dict]:
    """Every morning: a job id noted on an earlier run that the company's healthy poll today still doesn't have.
    Student-like titles only, unless any_job (Uber's job sitemap carries no titles worth judging)."""
    problems = []
    for c in ctx.comps.values():
        k = f"blocked:pending:{check}:{c.key}"
        raw = ctx.db.get(k)
        if not raw:
            continue
        pending = json.loads(raw)
        toks = stored_tokens(ctx.db, c.key)
        keep, report = {}, []
        for ident, p in pending.items():
            if is_stored(ident, toks):
                continue  # the poll caught up with it
            if p["found"] >= ctx.started or c.key not in ctx.healthy:
                keep[ident] = p  # no healthy poll since it was seen: wait
                continue
            if any_job or student_like(p["title"]):
                report.append((ident, p))
        ctx.db.set(k, json.dumps(keep))
        if report:
            shown = "; ".join(f"'{p['title'] or ident}' ({ident})" for ident, p in report[:6])
            where = report[0][1]["where"]
            problems.append(alert(ctx.db, c, check, "posting elsewhere?",
                                  f"{label} lists {len(report)} job(s) InternWatch has never seen: {shown}",
                                  f"Seen on {where} and still missing after today's healthy poll of {c.name}: the "
                                  "company may now post on a board InternWatch doesn't read. Open the link and "
                                  "check where the posting lives.", {k: raw}))
    return problems


# job systems (keyed per iCIMS portal, Avature site and Eightfold domain) ---------------------

def _host(url: str) -> str:
    return urlsplit(url if "//" in url else "https://" + url).netloc.lower()


def system_key_v2(checker: str, s: dict) -> str:
    """liveness.system_key, but an iCIMS portal, an Avature site and an Eightfold domain each count on their own,
    and a Workday site is keyed by tenant and site (wd1.myworkdaysite.com and fmr.wd1.myworkdayjobs.com are one)."""
    if checker == "icims" and s.get("portal"):
        return "icims:portal=" + _host(s["portal"])
    if checker == "avature" and s.get("list_url"):
        return "avature:site=" + _host(s["list_url"])
    if checker == "eightfold" and (s.get("domain") or s.get("host")):
        return "eightfold:domain=" + str(s.get("domain") or s.get("host")).lower()
    if checker == "workday" and s.get("tenant") and s.get("site"):
        return f"workday:site={str(s['site']).lower()},tenant={str(s['tenant']).lower()}"
    if checker == "smartrecruiters" and s.get("company"):
        return "smartrecruiters:company=" + str(s["company"]).lower()
    if checker == "jobvite" and s.get("slug"):
        return "jobvite:slug=" + str(s["slug"]).lower()
    return liveness.system_key(checker, s)


def _sources(c: Company) -> list[tuple[str, dict]]:
    s = c.settings or {}
    if c.checker == "multi":
        return [(x["checker"], x.get("settings") or {}) for x in s.get("sources") or []]
    return [(c.checker, s)]


def config_keys_v2(c: Company) -> set[str]:
    out = set()
    for checker, s in _sources(c):
        for b in list(s.get("boards") or []) or [s.get("board")]:
            for site in list(s.get("sites") or []) or [s.get("site")]:
                out.add(system_key_v2(checker, {k: v for k, v in {**s, "board": b, "site": site}.items() if v}))
    return out


def configured_hosts(c: Company) -> dict[str, str]:
    """Hosts in the company's settings (a custom Eightfold domain, a Workday tenant…) → the system they belong to."""
    out = {}
    for checker, s in _sources(c):
        first = {**s, "site": (s.get("sites") or [s.get("site")])[0], "board": (s.get("boards") or [s.get("board")])[0]}
        key = system_key_v2(checker, {k: v for k, v in first.items() if v})
        for v in s.values():
            if isinstance(v, str) and re.match(r"^(?:https?://)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:[/?#]|$)", v, re.I):
                out[_host(v)] = key
    return out


# links that detect.PATTERNS doesn't know; kept here so `internwatch add` and the checkers are unchanged
EXTRA_PATTERNS: list[tuple[str, callable]] = [
    (r"https?://([\w-]+\.eightfold\.ai)/careers[^\s\"'<>]*",
     lambda m: "eightfold:domain=" + ((parse_qs(urlsplit(m[0]).query).get("domain") or [m[1]])[0]).lower()),
    (r"https?://(?:[\w-]+\.)?joinhandshake\.com(?:/(?:stu/)?(?:employers|e)/([\w-]+))?",
     lambda m: "handshake:" + (f"employer={m[1].lower()}" if m[1] else "")),
    (r"https?://(?:app\.)?ripplematch\.com/(?:v2/public/)?company/([\w-]+)", lambda m: f"ripplematch:company={m[1].lower()}"),
    (r"https?://(?:careers|jobs)\.smartrecruiters\.com/([\w-]+)", lambda m: f"smartrecruiters:company={m[1].lower()}"),
    (r"https?://jobs\.jobvite\.com/([\w-]+)", lambda m: f"jobvite:slug={m[1].lower()}"),
]


def systems_in(text: str, page_url: str, c: Company, aliases: dict) -> set[str]:
    """The job systems a page (or a list's link) points at, aliases resolved. A link to a host in the company's own
    settings counts as that configured system, except the page's own host (its self-links come and go)."""
    from .detect import from_text  # detect imports the runner
    seen = {system_key_v2(x.checker, x.settings) for x in from_text(text, page_url)}
    for rx, build in EXTRA_PATTERNS:
        seen.update(build(m) for m in re.finditer(rx, text))
    own = _host(page_url) if page_url else ""
    hosts = configured_hosts(c)
    for h in re.findall(r"https?://([a-z0-9.-]+)", text, re.I):
        h = h.lower()
        if h != own and h in hosts:
            seen.add(hosts[h])
    return {aliases.get(k, k) for k in seen}


def aliases(cfg: Config) -> dict[str, str]:
    return {str(k).lower(): str(v).lower() for k, v in (opts(cfg).get("aliases") or {}).items()}


def known_systems(ctx: Ctx, c: Company) -> set[str]:
    """What isn't news for a company: its configured systems and the parallel boards watched for it (S)."""
    al = aliases(ctx.cfg)
    keys = config_keys_v2(c) | {system_key_v2(x["checker"], x.get("settings") or {})
                                for x in entries(ctx.cfg, "parallel_sources") if x["company"] == c.key}
    return {al.get(k, k) for k in keys}


# running them -----------------------------------------------------------------------------------------

CHECKS: list[tuple[str, callable]] = []  # (name, fn(ctx) -> problems), cheapest first


def run(cfg: Config, db: DB, gate, make_http, budget_end: float, healthy: set) -> list[dict]:
    """Every check, each on its own: a bug or an outage in one never stops the others or the run's emails."""
    if not blocked(cfg):
        return []
    ctx = Ctx(cfg, db, gate, make_http, budget_end, set(healthy))
    problems: list[dict] = []
    for name, fn in CHECKS:
        if ctx.out_of_time():
            log.info("moves: out of time before %s; it runs on a later morning", name)
            break
        try:
            problems += fn(ctx)
        except Exception:  # noqa: BLE001 — logged; never costs the run
            log.exception("moves: %s failed", name)
    return problems


def observe(cfg: Config, db: DB, o) -> list[dict]:
    """Per-poll hook (runner._liveness_observe): checks that read nothing but the company's own poll."""
    return []
