"""Notice when a company whose careers page InternWatch can't read starts posting jobs somewhere new.

The companies are named in settings `liveness.blocked`: the 31 whose careers page answers scripts with a bot check,
an HTTP 400 or a robots.txt block, so the weekly page check (liveness.scan_pages) never sees where they point. Only
those companies are read here. Nothing here stores a job or touches a poll: every check compares what it sees now
with its own last look and raises a health alert for what is new. The first look of each check is a silent
baseline. The checks run once a morning in daily runs, within `blocked_scan_seconds`, before the emails: every one of
them every morning except archive.org's (spread over the week: a copy only changes when someone saves one, and it
throttles scripts), and a page that refuses reads waits a week.

  W  Workday tenants' robots.txt: hidden sites (Disallow lines), plus tenants of a parent company (extra_tenants)
  P  the careers page and any WordPress pages (/wp-json/wp/v2/pages): job systems they name, keyed per iCIMS
     portal, Avature site and Eightfold domain; job ids on the page that InternWatch has never stored
  A  archive.org's copies: new pages under the careers paths, job ids in them, systems named in the newest copies
  J  the company's own job list (sitemap or job file) against every job InternWatch has stored
  N  new student and program pages in sitemaps, WordPress page lists and Goldman's programs feed
  G  new labels: Goldman's experience and source types, Meta's team labels (from its poll, no request)
  S  parallel boards read with the existing adapters: a matching role InternWatch doesn't have
  L  third-party lists and board registries (for every active company, not just these), and Getro boards that read
     the careers page: a job system the config doesn't name

A job id seen where InternWatch has no such job is only reported once a healthy poll of the company on a later run
still doesn't have it (a posting can simply be newer than this morning's poll).
A read that failed (5xx, timeout, a page that's gone) is read again the next morning, every morning. A page that refuses
(a bot check, a block) gets one retry and then waits a week, and a robots.txt block just waits. Lists, Getro, parallel
boards and watched boards never wait. A daily read missed three mornings in a row raises `check gone dark`.
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
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

from . import alerts, liveness
from .config import Company, Config
from .db import DB, iso, parse_iso, utcnow
from .filters import is_student_role
from .models import CheckTimeout, Job, RobotsBlocked

log = logging.getLogger(__name__)

REFUSED_DAYS = 7   # how long a page that refuses reads waits, in a check that runs daily
DARK_DAYS = 14     # a weekly read that answered before and hasn't for this long is reported
DARK_MORNINGS = 3  # a daily read missed this many mornings in a row is reported
REFUSED_STATUSES = ("400", "401", "403", "406", "429")  # the site says no; it isn't down
NEVER_WAIT = ("listings", "getro", "parallel", "watch", "watch-full")  # read again the next morning, whatever happened
WEEKLY = ("archive", "watch-full")

# a page address or title that reads like a students, internships or program page (not "internaliser", "residents")
STUDENT = re.compile(r"\bintern(?:s|ship|ships)?\b|\bco-?ops?\b|\bstudents?\b|\bcampus\b|early[-_ ]?(?:career|talent)|"
                     r"universit|\bgraduates?\b|\bprograms?\b|\bfellow(?:s|ship|ships)?\b|\bresiden(?:cy|t)\b|"
                     r"emerging[-_ ]talent|apprentic|\bscholar(?:s|ship|ships)?\b|sneak[-_ ]peek|\bacademy\b|"
                     r"\bsummits?\b|datathon|invitational|bootcamp|externship|\bdiscover[-_ ]", re.I)


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

def refused_last(db: DB, check: str, key: str) -> bool:
    """The last read was refused or robots.txt forbade it (or older, when the kind wasn't kept), so a page waits. A read
    that failed doesn't count: it stays due."""
    if check in NEVER_WAIT:
        return False
    history = load(db, f"blocked:rate:{check}:{key}", [])
    return bool(history) and not history[-1][1] and history[-1][2:] != ["failed"]


def pick(db: DB, check: str, keys: list[str], every_days: float, now) -> list[str]:
    """Due for `check` today: yesterday's failed and refused reads (outside the quota), then the oldest due ones, at most
    a 1/every_days share of them a day so a weekly check spreads over the week (never-read ones first). A page that
    refuses waits REFUSED_DAYS, whatever the check's pace: asking a site that refuses every day teaches nothing and gives
    it a reason to block the feed read from the same host. It goes back to the check's pace once it answers."""
    retry = [k for k in keys if db.get(f"blocked:retry:{check}:{k}")]
    due = []
    for k in keys:
        if k in retry:
            continue
        last = parse_iso(db.get(f"blocked:at:{check}:{k}") or None)
        days = max(every_days, REFUSED_DAYS) if refused_last(db, check, k) else every_days
        if last is None or now - last >= timedelta(days=days) - timedelta(hours=12):
            due.append((last.isoformat() if last else "", k))
    quota = len(due) if every_days <= 1 else math.ceil(len(keys) / every_days)
    return retry + [k for _, k in sorted(due)[:quota]]


def outcome(e: Exception) -> str:
    """robots: robots.txt forbids the read. refused: the site says no (a bot check, a block). failed: anything else
    (5xx, a timeout, a page that's gone): nothing to learn from asking again tomorrow but a good answer."""
    if isinstance(e, RobotsBlocked):
        return "robots"
    m = re.search(r"HTTP (\d{3})", str(e))
    return "refused" if m and m.group(1) in REFUSED_STATUSES else "failed"


def worst(errors: list[str]) -> str:
    """What a read of several sources that all failed counts as."""
    return next((x for x in ("refused", "robots") if x in errors), "failed")


def archive_outcome(e: Exception) -> str:
    """archive.org throttles scripts, so it keeps its own pace: one retry, and none for a block or a missing copy."""
    return "robots" if isinstance(e, RobotsBlocked) or re.search(r"HTTP (?:401|404|410)\b", str(e)) else "refused"


def out_of_budget(e: Exception) -> bool:
    return isinstance(e, CheckTimeout) and "time budget" in str(e)


def done(db: DB, check: str, key: str, result: str, now) -> None:
    """Record a read: ok; failed (read again the next morning, every morning); refused (a first refusal is retried the
    next morning, a second one waits, and one still refused after its wait waits again, with no retry); or robots
    (it waits, with no retry)."""
    if result != "ok" and check in NEVER_WAIT:
        result = "failed"
    rkey = f"blocked:retry:{check}:{key}"
    if result == "failed" or (result == "refused" and not db.get(rkey) and not refused_last(db, check, key)):
        db.set(rkey, "1")
    else:
        db.set(rkey, "")
        db.set(f"blocked:at:{check}:{key}", iso(now))
    record(db, check, key, result, now)


def record(db: DB, check: str, key: str, result: str, now) -> None:
    """One line of a source's history, and the last day it answered, which outlives the history's 28 days: a source
    dark for longer must not pass for one that never answered."""
    k = f"blocked:rate:{check}:{key}"
    hist = json.loads(db.get(k) or "[]")
    today = now.date().isoformat()
    answered = f"blocked:ok:{check}:{key}"
    if result == "ok":
        db.set(answered, today)
    elif not db.get(answered) and any(x[1] for x in hist):
        db.set(answered, max(x[0] for x in hist if x[1]))
    since = (now - timedelta(days=28)).date().isoformat()
    line = [today, 1 if result == "ok" else 0] + (["failed"] if result == "failed" else [])
    db.set(k, json.dumps([x for x in hist if x[0] >= since] + [line]))


def due_restore(db: DB, check: str, key: str) -> dict:
    """kv to put back with an alert so a failed health email makes the read due (and the alert raised) again."""
    return {f"blocked:at:{check}:{key}": db.get(f"blocked:at:{check}:{key}") or ""}


def alert(db: DB, c: Company, check: str, kind: str, summary: str, detail: str, restore_kv: dict,
          items: list[dict] | None = None) -> dict:
    """`items`: how each thing this alert covers clears (alerts.py), {suffix, rule, summary, …}; suffix names the thing."""
    akey = f"live_alert:{c.key}:{check}"
    full = [{"id": f"{akey}:{x['suffix']}", **{k: v for k, v in x.items() if k != "suffix"}} for x in items or []]
    p = liveness._problem(c, kind, summary, detail, None, akey, restore_kv=restore_kv, items=full)
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


def note_unknown(db: DB, check: str, c: Company, found: dict[str, str], where: str, started: str) -> None:
    """Job ids seen on a source but not stored: kept until a later healthy poll confirms (confirm())."""
    if not found:
        return
    k = f"blocked:pending:{check}:{c.key}"
    pending = load(db, k, {})
    for ident, title in found.items():
        pending.setdefault(ident, {"title": title, "found": started, "where": where})
    db.set(k, json.dumps(pending))


def confirm(ctx: Ctx, check: str, label: str, any_job=False) -> list[dict]:
    """Every morning: a job id noted on an earlier run that the company's healthy poll today still doesn't have.
    Student roles (by the filters' role rule) or unknown titles only, unless any_job (a bool, or a function of the
    company key: Uber's job sitemap carries every posting, so any job missing there counts)."""
    problems = []
    for c in ctx.comps.values():
        k = f"blocked:pending:{check}:{c.key}"
        raw = ctx.db.get(k)
        if not raw:
            continue
        pending = json.loads(raw)
        toks = stored_tokens(ctx.db, c.key)
        keep, report = {}, []
        titles = None
        for ident, p in pending.items():
            if ident.startswith("title:"):
                if titles is None:
                    titles = {re.sub(r"[^a-z0-9]", "", t) for t in stored_titles(ctx.db, c.key, days=3650)}
                if title_stored(p["title"], titles):
                    continue  # the poll caught up with it
            elif is_stored(ident, toks):
                continue  # the poll caught up with it
            if p["found"] >= ctx.started or c.key not in ctx.healthy:
                keep[ident] = p  # no healthy poll since it was seen: wait
                continue
            if (any_job(c.key) if callable(any_job) else any_job) or not p["title"] \
                    or is_student_role(Job(id=ident, title=p["title"]), ctx.cfg.rules, c.extra_role_re):
                report.append((ident, p))
        ctx.db.set(k, json.dumps(keep))
        if report:
            shown = "; ".join(f"'{p['title'] or ident}'" + ("" if ident.startswith("title:") else f" ({ident})")
                              for ident, p in report[:6])
            where = report[0][1]["where"]
            problems.append(alert(ctx.db, c, check, "posting elsewhere?",
                                  f"{len(report)} job(s) on {label} that InternWatch has never seen: {shown}",
                                  f"Seen on {where} and still missing after today's healthy poll of {c.name}: the "
                                  "company may now post on a board InternWatch doesn't read. Open the link and "
                                  "check where the posting lives.", {k: raw},
                                  [{"suffix": ident, "rule": "posting", "item": ident, "scope": check,
                                    "summary": f"a job on {label} that InternWatch has never seen: "
                                               f"'{p['title'] or ident}'"} for ident, p in report]))
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


HOST_SETTINGS = ("host", "portal", "list_url", "base_url")  # where a job system lives (not Eightfold's domain=)
SHARED_HOSTS = re.compile(r"myworkdaysite\.com$|greenhouse\.io$|lever\.co$|ashbyhq\.com$|oraclecloud\.com$")


def configured_hosts(c: Company) -> dict[str, str]:
    """Hosts a company's own job systems live on (a custom Eightfold host, its Workday tenant…) → that system.
    Hosts every company shares (wd1.myworkdaysite.com, boards.greenhouse.io…) are left to detect.PATTERNS."""
    out = {}
    for checker, s in _sources(c):
        first = {**s, "site": (s.get("sites") or [s.get("site")])[0], "board": (s.get("boards") or [s.get("board")])[0]}
        key = system_key_v2(checker, {k: v for k, v in first.items() if v})
        for name in HOST_SETTINGS:
            v = s.get(name)
            if isinstance(v, str) and v and not SHARED_HOSTS.search(_host(v)):
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
    return {aliases.get(k, k) for k in seen if not NOT_A_SYSTEM.match(k)}


NOT_A_SYSTEM = re.compile(r"^icims:portal=(?:cdn\d*|www|images?|static|assets?)\.icims\.com$")  # iCIMS's own hosts


def aliases(cfg: Config) -> dict[str, str]:
    return {str(k).lower(): str(v).lower() for k, v in (opts(cfg).get("aliases") or {}).items()}


def known_systems(ctx: Ctx, c: Company) -> set[str]:
    """What isn't news for a company: its configured systems and the parallel boards watched for it (S)."""
    al = aliases(ctx.cfg)
    keys = config_keys_v2(c) | {system_key_v2(x["checker"], x.get("settings") or {})
                                for x in entries(ctx.cfg, "parallel_sources") if x["company"] == c.key}
    return {al.get(k, k) for k in keys}


# W: hidden Workday sites -------------------------------------------------------------------------------

WORKDAY_PATHS = {"refreshfacet", "wday", "api", "cdn-cgi"}  # robots.txt paths that are Workday's own, not sites


def workday_tenants(ctx: Ctx) -> dict[str, tuple[Company, set[str], bool]]:
    """{host: (company, its configured sites, whether liveness.scan_workday_sites already compares the host's
    Allow lines)}. A myworkdaysite.com config (Fidelity) is looked up on <tenant>.<wdN>.myworkdayjobs.com, whose
    robots.txt names the hidden sites; extra_tenants adds a parent company's tenant (PitchBook's Morningstar)."""
    out: dict[str, tuple[Company, set[str], bool]] = {}
    for c in ctx.comps.values():
        for checker, s in _sources(c):
            host, tenant = s.get("host") or "", s.get("tenant")
            if checker != "workday" or not tenant or not host:
                continue
            covered = "myworkdaysite" not in host
            if not covered:
                m = re.match(r"(wd\d+)\.myworkdaysite\.com", host)
                if not m:
                    continue
                host = f"{tenant}.{m.group(1)}.myworkdayjobs.com"
            sites = {str(x).lower() for x in (s.get("sites") or [s.get("site")]) if x}
            prev = out.get(host)
            out[host] = (c, (prev[1] if prev else set()) | sites, covered)
    for key, hosts in per_company(ctx.cfg, "extra_tenants").items():
        for h in hosts:
            out.setdefault(h, (ctx.comps[key], set(), False))
    return out


def workday_robots_sites(text: str) -> tuple[set[str], set[str]]:
    """(sites robots.txt allows, sites it hides with a Disallow line), Workday's own paths left out."""
    allow = set(re.findall(r"(?im)^\s*allow:\s*/([\w-]+)/", text or ""))
    hidden = set(re.findall(r"(?im)^\s*disallow:\s*/([\w-]+)/", text or ""))
    return ({x for x in allow if x.lower() not in WORKDAY_PATHS}, {x for x in hidden if x.lower() not in WORKDAY_PATHS})


def check_workday(ctx: Ctx) -> list[dict]:
    """W. A new hidden site (Disallow line) on a tenant of the 31, or any new site on a tenant that the daily
    Workday check can't see (myworkdaysite.com hosts, parent companies). robots.txt comes from
    the checks' cache when it is fresh, else one plain GET that leaves the cache as it is."""
    tenants = workday_tenants(ctx)
    problems: list[dict] = []
    http = None
    try:
        for host in pick(ctx.db, "workday", sorted(tenants), 1, ctx.now):
            if ctx.out_of_time():
                break
            c, configured, covered = tenants[host]
            origin = f"https://{host}"
            disk = ctx.gate._disk_get(origin) if ctx.gate is not None else None
            if disk and disk[0] == 200 and time.time() - disk[2] < 12 * 3600:
                text = disk[1]
            else:
                http = http or ctx.http()
                try:
                    r = http.get(origin + "/robots.txt", check_robots=False, ok_statuses=(404,))
                except Exception as e:  # noqa: BLE001 — a refused read is retried tomorrow
                    if out_of_budget(e):
                        break
                    done(ctx.db, "workday", host, outcome(e), ctx.now)
                    continue
                if r.status != 200:
                    done(ctx.db, "workday", host, "failed", ctx.now)
                    continue
                text = r.text
            allow, hidden = workday_robots_sites(text)
            sites = hidden if covered else allow | hidden
            key = f"blocked:workday_hidden:{host}"
            raw = ctx.db.get(key)
            restore_kv = {key: raw or "", **due_restore(ctx.db, "workday", host)}
            known = set(json.loads(raw)) if raw else None
            ctx.db.set(key, json.dumps(sorted(sites | (known or set()))))
            done(ctx.db, "workday", host, "ok", ctx.now)
            alerts.seen(ctx.db, c.key, "site", sites, scope=host)
            if known is None:
                continue  # first look: a silent baseline
            new = sorted(x for x in sites - known if x.lower() not in configured)
            if new:
                which = "hidden " if covered else ""
                problems.append(alert(
                    ctx.db, c, "workday-hidden", "new site", f"Workday tenant {host} lists new {which}sites: {', '.join(new)}",
                    "A hidden site (a Disallow line in robots.txt) can hold postings InternWatch doesn't read: American "
                    "Family moved an intern posting to its hidden AmFam-Private site on Oct 24. Add it to the config "
                    "if it has student roles.", restore_kv,
                    [{"suffix": x, "rule": "site", "item": x, "scope": host,
                      "summary": f"Workday tenant {host} lists a new {which}site: {x}"} for x in new]))
    finally:
        if http is not None:
            http.close()
    return problems


# P: careers pages, WordPress pages, job ids on pages ---------------------------------------------------------

JOB_ID_PATTERNS = [
    re.compile(r"gh_jid=(\d{5,})"),
    re.compile(r"greenhouse\.io/[\w-]+/jobs/(\d{5,})"),
    re.compile(r"jobs\.(?:eu\.)?lever\.co/[\w.-]+/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"),
    re.compile(r"jobs\.ashbyhq\.com/[\w.%-]+/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"),
    re.compile(r"icims\.com/jobs/(\d{3,})"),
    re.compile(r"myworkday(?:jobs|site)\.com/[^\"'\s<>]*?_((?:JR|R)-?\d{4,}(?:-\d+)?)"),
]
TAG = re.compile(r"<[^>]+>")


def ids_with_titles(text: str) -> dict[str, str]:
    """Job ids linked from a page, each with the link's title (data-title, else its text) when there is one."""
    out: dict[str, str] = {}
    for m in re.finditer(r"<a\b([^>]*)>(.*?)</a>", text, re.S | re.I):
        attrs, inner = m.group(1), m.group(2)
        href = re.search(r"href\s*=\s*[\"']([^\"']+)", attrs)
        if not href:
            continue
        for rx in JOB_ID_PATTERNS:
            for i in rx.findall(htmllib.unescape(href.group(1))):
                t = re.search(r"data-title\s*=\s*[\"']([^\"']+)", attrs)
                title = t.group(1) if t else " ".join(htmllib.unescape(TAG.sub(" ", inner)).split())
                if not out.get(i):
                    out[i] = title[:120]
    for rx in JOB_ID_PATTERNS:  # ids outside links (JSON in the page)
        for i in rx.findall(text):
            out.setdefault(i, "")
    return out


def wp_pages(http, base: str) -> str:
    """Every WordPress page's content, through the site's REST API (it answers where the HTML pages don't)."""
    parts, page, total = [], 1, 1
    while page <= min(total, 20):
        r = http.get(f"{base.rstrip('/')}/wp-json/wp/v2/pages",
                     params={"per_page": 100, "page": page, "_fields": "link,content"})
        for item in json.loads(r.text):
            rendered = htmllib.unescape(((item.get("content") or {}).get("rendered")) or "")
            parts.append(f"<!-- {item.get('link', '')} -->\n{rendered}")
        total = int(r.headers.get("x-wp-totalpages") or 1)
        page += 1
    return "\n".join(parts)


def page_sources(ctx: Ctx, c: Company) -> list[tuple[str, str]]:
    """(kind, url) of what P reads for a company: its careers page, its WordPress site, pages that list postings."""
    out = [("page", c.careers_url[0])] if c.careers_url else []
    wp = per_company(ctx.cfg, "wp_pages").get(c.key)
    if wp:
        out.append(("wp", wp))
    out += [("ids", u) for u in per_company(ctx.cfg, "id_pages").get(c.key) or []]
    return out


def check_pages(ctx: Ctx) -> list[dict]:
    """P. Daily: the job systems each source names (an iCIMS portal, an Avature site and an Eightfold domain each on
    their own; a link to a configured host counts as that system) and the job ids it links. A source's first read is
    a silent baseline. New job ids wait for confirm(). Every system a source ever named is remembered, so a page that
    flips back and forth alerts once, and one that stops naming a configured system alerts after two reads in a row."""
    problems: list[dict] = []
    al = aliases(ctx.cfg)
    http = ctx.http()
    try:
        for key in pick(ctx.db, "page", sorted(k for k, c in ctx.comps.items() if page_sources(ctx, c)), 1, ctx.now):
            if ctx.out_of_time():
                break
            c = ctx.comps[key]
            skey = f"blocked:page:{key}"
            raw = ctx.db.get(skey)
            state = json.loads(raw) if raw else {}
            results, errors = {}, []
            for kind, url in page_sources(ctx, c):
                try:
                    text = wp_pages(http, url) if kind == "wp" else http.get_text(
                        url, headers={"Accept": "text/html,*/*;q=0.8"})  # */* too, as liveness.scan_pages
                except Exception as e:  # noqa: BLE001 — a bot wall is only counted
                    if out_of_budget(e):
                        return problems
                    errors.append(outcome(e))
                    log.info("moves: %s of %s not read: %s", kind, key, str(e)[:160])
                    continue
                results[url] = (sorted(systems_in(text, "" if kind == "wp" else url, c, al)), ids_with_titles(text))
            if not results:
                done(ctx.db, "page", key, worst(errors), ctx.now)
                continue
            restore_kv = {skey: raw or "", **due_restore(ctx.db, "page", key)}
            known = known_systems(ctx, c)
            toks = stored_tokens(ctx.db, key)
            new_sys, gone, unknown = [], [], {}
            for url, (systems, ids) in results.items():
                before = state.get(url)
                ever = set((before or {}).get("ever") or (before or {}).get("systems") or [])
                absent = {x: ((before or {}).get("absent") or {}).get(x, 0) + 1 for x in ever
                          if x in known and x not in systems}
                told = set((before or {}).get("told") or [])
                gone_now = [x for x, n in absent.items() if n >= 2 and x not in told]
                state[url] = {"systems": systems, "ids": sorted(set(ids) | set((before or {}).get("ids") or [])),
                              "ever": sorted(ever | set(systems)), "absent": absent, "told": sorted(told | set(gone_now))}
                if before is None:
                    continue  # this source's first read: a silent baseline
                new_sys += [x for x in systems if x not in ever and x not in known]
                gone += gone_now
                unknown.update({i: t for i, t in ids.items() if i not in before["ids"] and not is_stored(i, toks)})
            ctx.db.set(skey, json.dumps(state))
            done(ctx.db, "page", key, "ok", ctx.now)
            note_unknown(ctx.db, "page", c, unknown, "its careers pages", ctx.started)
            if not errors:  # every source was read: what none of them names is gone
                named = {x for systems, _ in results.values() for x in systems}
                alerts.seen(ctx.db, key, "system_new", named, scope="moves", needed=2)
                alerts.back(ctx.db, key, "system_gone", named, scope="moves")
                alerts.seen(ctx.db, key, "posting", {i for _, ids in results.values() for i in ids}, scope="page")
            if new_sys or gone:
                parts = ([f"now point at {', '.join(sorted(set(new_sys)))}"] if new_sys else []) + \
                        ([f"no longer mention {', '.join(sorted(set(gone)))}"] if gone else [])
                problems.append(alert(ctx.db, c, "page", "moved?", f"its careers pages {' and '.join(parts)}",
                                      f"InternWatch reads {', '.join(sorted(known))}. The jobs may have moved to "
                                      f"another job site: compare {', '.join(results)} with the config.", restore_kv,
                                      [{"suffix": f"new:{x}", "rule": "system_new", "item": x, "scope": "moves",
                                        "summary": f"its careers pages now point at {x}"} for x in sorted(set(new_sys))]
                                      + [{"suffix": f"gone:{x}", "rule": "system_gone", "item": x, "scope": "moves",
                                          "summary": f"its careers pages no longer mention {x}"} for x in sorted(set(gone))]))
    finally:
        http.close()
    return problems


def check_confirm(ctx: Ctx) -> list[dict]:
    """Every morning, no request: job ids noted by P, J, A or the Getro check that today's healthy poll still lacks."""
    jl = per_company(ctx.cfg, "job_lists")
    return (confirm(ctx, "page", "its careers pages")
            + confirm(ctx, "joblist", "its job list", any_job=lambda k: (jl.get(k) or {}).get("any_job", False))
            + confirm(ctx, "archive", "archived copies of its careers pages")
            + confirm(ctx, "getro", "Getro's copy of its careers page"))


# A: archive.org's copies ------------------------------------------------------------------------------------

CDX = "https://web.archive.org/cdx/search/cdx"
BOT_CHECK = re.compile(r"Just a moment|cf-chl|Checking your browser|Attention Required|px-captcha|captcha-delivery|"
                       r"Pardon Our Interruption|HASHCASH", re.I)


def norm_url(u: str) -> str:
    p = urlsplit(u if "//" in u else "https://" + u)
    host = p.netloc.lower().split(":")[0]
    host = host[4:] if host.startswith("www.") else host
    return host + (p.path.rstrip("/") or "/")


def original_allowed(ctx: Ctx, http, url: str) -> bool:
    """Read an archived copy only where the original site's robots.txt allows the page itself."""
    if ctx.gate is None:
        return True
    p = urlsplit(url)
    try:
        rules = ctx.gate.robots(f"{p.scheme}://{p.netloc}", http._fetch_robots, 12.0)
    except Exception:  # noqa: BLE001 — unreachable robots.txt: treated as "crawl nothing" (RFC 9309)
        return False
    return rules.allowed(url)


def check_archive(ctx: Ctx) -> list[dict]:
    """A. Weekly per company, spread over the week. One listing of the pages archive.org saved under each configured
    path since the last look: a new student or program page, and (where `ids` is set) job ids InternWatch never
    stored. Then the newest copy of each configured page, when it is at most `archive_max_days` old, isn't a bot
    check and its own site's robots.txt allows the page: the job systems it names."""
    paths = per_company(ctx.cfg, "archive_paths")
    max_age = timedelta(days=float(opts(ctx.cfg).get("archive_max_days", 45)))
    al = aliases(ctx.cfg)
    problems: list[dict] = []
    http = ctx.http(retries=0, read_timeout=45)  # archive.org can be slow or "temporarily offline": retry tomorrow
    try:
        for key in pick(ctx.db, "archive", sorted(paths), 7, ctx.now):
            if ctx.out_of_time():
                break
            c, conf = ctx.comps[key], paths[key]
            skey = f"blocked:archive:{key}"
            raw = ctx.db.get(skey)
            state = json.loads(raw) if raw else {}
            first = not state
            since = state.get("since") or (ctx.now - timedelta(days=30)).strftime("%Y%m%d")
            rows = []
            try:
                for path in conf.get("list") or []:
                    r = http.get(CDX, params={"url": path, "fl": "original,timestamp", "filter": "statuscode:200",
                                              "from": since, "limit": "3000"}, timeout=45)
                    rows += [ln.split(" ") for ln in r.text.splitlines() if ln.count(" ") == 1]
                copies = []
                for page in conf.get("pages") or []:
                    r = http.get(CDX, params={"url": page, "fl": "original,timestamp", "filter": "statuscode:200",
                                              "limit": "-1"}, timeout=45)
                    last = [ln.split(" ") for ln in r.text.splitlines() if ln.count(" ") == 1]
                    if last:
                        copies.append((page, last[-1][0], last[-1][1]))
            except Exception as e:  # noqa: BLE001 — archive.org down or slow: tomorrow
                if out_of_budget(e):
                    break
                done(ctx.db, "archive", key, archive_outcome(e), ctx.now)
                log.info("moves: archive.org listing for %s failed: %s", key, str(e)[:160])
                continue
            restore_kv = {skey: raw or "", **due_restore(ctx.db, "archive", key)}
            seen_urls = set(state.get("urls") or [])
            urls = {norm_url(u) for u, _ in rows}
            new_pages = sorted(u for u in urls - seen_urls if conf.get("any_page") or STUDENT.search(u.split("/", 1)[-1]))
            ids = {}
            if conf.get("ids"):
                rx = re.compile(conf["ids"])
                for u, _ in rows:
                    m = rx.search(u.split("?")[0])
                    if m and m.group(1).isdigit():
                        ids[m.group(1)] = ""
            toks = stored_tokens(ctx.db, key)
            stored_numbers = [int(t) for t in toks if t.isdigit() and len(t) >= 5]
            floor = state.get("floor")
            if floor is None:
                floor = max(stored_numbers + [int(i) for i in ids] + [0])
            unknown = {i: t for i, t in ids.items() if int(i) > floor and not is_stored(i, toks)}
            systems = dict(state.get("systems") or {})
            read_copies = dict(state.get("copies") or {})
            new_sys: list[tuple[str, str, str]] = []
            newest: set[str] = set()
            known = known_systems(ctx, c)
            for page, original, ts in copies:
                if ts <= read_copies.get(page, ""):
                    continue  # no newer copy since the last look
                age = ctx.now - datetime.strptime(ts[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                if age > max_age or not original_allowed(ctx, http, original):
                    continue
                try:
                    text = http.get_text(f"https://web.archive.org/web/{ts}id_/{original}")
                except Exception as e:  # noqa: BLE001 — one unreadable copy: the next one comes
                    log.info("moves: archived copy of %s not read: %s", page, str(e)[:160])
                    continue
                read_copies[page] = ts
                if BOT_CHECK.search(text[:30000]):
                    continue
                now_sys = sorted(systems_in(text, original, c, al))
                newest.update(now_sys)
                before = systems.get(page)
                systems[page] = sorted(set(now_sys) | set(before or []))
                if before is not None:
                    new_sys += [(page, ts, x) for x in now_sys if x not in before and x not in known]
            state.update(urls=sorted(seen_urls | urls), floor=max(floor, *(int(i) for i in ids)) if ids else floor,
                         systems=systems, copies=read_copies, since=ctx.now.strftime("%Y%m%d"))
            ctx.db.set(skey, json.dumps(state))
            done(ctx.db, "archive", key, "ok", ctx.now)
            if newest:  # a newer copy was read: what none of them names is gone
                alerts.seen(ctx.db, key, "system_new", newest, scope="archive", needed=2)
            if first:
                continue  # first look: a silent baseline
            note_unknown(ctx.db, "archive", c, unknown, "archived copies of its careers pages", ctx.started)
            if new_pages:
                problems.append(alert(ctx.db, c, "archive-pages", "new page",
                                      f"archive.org saved new student or program pages: {', '.join(new_pages[:5])}",
                                      "A new students, internships or program page is often the first sign of a new "
                                      "program or job site. Open it and compare with the config.", restore_kv,
                                      [{"suffix": u, "rule": "manual", "summary": f"archive.org saved a new page: {u}"}
                                       for u in new_pages[:5]]))
            if new_sys:
                shown = ", ".join(sorted({x for _, _, x in new_sys}))
                page, ts, _ = new_sys[0]
                problems.append(alert(ctx.db, c, "archive", "moved?",
                                      f"an archived copy of {page} (saved {ts[:4]}-{ts[4:6]}-{ts[6:8]}) points at {shown}",
                                      f"InternWatch reads {', '.join(sorted(known))}. The jobs may have moved to another "
                                      f"job site: https://web.archive.org/web/{ts}/{page}", restore_kv,
                                      [{"suffix": x, "rule": "system_new", "item": x, "scope": "archive",
                                        "summary": f"an archived copy of {pg} points at {x}"} for pg, _, x in new_sys]))
    finally:
        http.close()
    return problems


# J: the company's own job list ------------------------------------------------------------------------------

def job_list(text: str) -> dict[str, str]:
    """{job id: title} from a job file (a JSON list of {id, title}) or a sitemap of job pages (title from the slug)."""
    t = text.lstrip()
    if t.startswith(("[", "{")):
        data = json.loads(t)
        items = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])
        return {str(x["id"]): str(x.get("title") or "") for x in items if isinstance(x, dict) and x.get("id")}
    out = {}
    for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text):
        loc = htmllib.unescape(loc)
        m = re.search(r"/(?:jobs?|careers/job)/([\w%-]*\d[\w%-]*?)(?:/([\w%-]+))?/?(?:[?#].*)?$", loc)
        if not m:
            continue
        ident, slug = m.group(1).lower(), m.group(2) or ""
        if not slug and re.match(r"^\d+-", ident):  # Eightfold: /careers/job/<id>-<slug>
            ident, slug = ident.split("-", 1)
        out.setdefault(ident, re.sub(r"%[0-9a-f]{2}", " ", slug, flags=re.I).replace("-", " ").strip())
    return out


def title_stored(title: str, stored: set[str]) -> bool:
    """A sitemap slug carries the title and often the place after it ("sr-legal-counsel-san-jose-…")."""
    t = re.sub(r"[^a-z0-9]", "", title.lower())
    return any(s and (s in t or t.startswith(s[:max(12, len(s) - 2)])) for s in stored)


def check_job_lists(ctx: Ctx) -> list[dict]:
    """J. Daily: the job list a company publishes itself (a sitemap of job pages, Akuna's job file), compared with every
    job InternWatch ever stored for it: by the id in the URL, or by title where the list uses its own ids
    (PayPal's Eightfold copy of Workday). The first read is a silent baseline; a job added since that InternWatch
    doesn't have is noted, and confirm() reports it if a healthy poll on a later run still lacks it."""
    lists = per_company(ctx.cfg, "job_lists")
    problems: list[dict] = []
    http = ctx.http()
    try:
        groups: dict[float, list[str]] = {}
        for key, conf in lists.items():
            groups.setdefault(float(conf.get("every_days", 1)), []).append(key)
        for every, keys in sorted(groups.items()):
            for key in pick(ctx.db, "joblist", sorted(keys), every, ctx.now):
                if ctx.out_of_time():
                    return problems
                c, conf = ctx.comps[key], lists[key]
                try:
                    jobs = job_list(http.get_text(conf["url"], headers={"Accept": "application/json,application/xml,*/*"}))
                except Exception as e:  # noqa: BLE001 — refused: tomorrow
                    if out_of_budget(e):
                        return problems
                    done(ctx.db, "joblist", key, outcome(e), ctx.now)
                    log.info("moves: job list of %s not read: %s", key, str(e)[:160])
                    continue
                skey = f"blocked:joblist:{key}"
                raw = ctx.db.get(skey)
                seen = set(json.loads(raw)) if raw else None
                ctx.db.set(skey, json.dumps(sorted(set(jobs) | (seen or set()))))
                done(ctx.db, "joblist", key, "ok", ctx.now)
                alerts.seen(ctx.db, key, "posting", set(jobs) | {f"title:{t}" for t in jobs.values()}, scope="joblist")
                if seen is None or not jobs:
                    continue  # first read: a silent baseline
                if conf.get("match") == "title":
                    stored = {re.sub(r"[^a-z0-9]", "", t) for t in stored_titles(ctx.db, key, days=3650)}
                    unknown = {i: t for i, t in jobs.items() if i not in seen and not title_stored(t, stored)}
                    unknown = {f"title:{t}": t for t in unknown.values()}
                else:
                    toks = stored_tokens(ctx.db, key)
                    unknown = {i: t for i, t in jobs.items() if i not in seen and not is_stored(i, toks)}
                note_unknown(ctx.db, "joblist", c, unknown, conf["url"], ctx.started)
    finally:
        http.close()
    return problems


# N: new student and program pages --------------------------------------------------------------------------

def page_list(http, source: str) -> dict[str, str]:
    """{page: title} of a site: a sitemap, a WordPress page list ("wp:<site>") or a JSON feed of programs."""
    if source.startswith("wp:"):
        out, page, total = {}, 1, 1
        while page <= min(total, 20):
            r = http.get(f"{source[3:].rstrip('/')}/wp-json/wp/v2/pages", params={"per_page": 100, "page": page,
                                                                                   "_fields": "link,title"})
            for item in json.loads(r.text):
                out[item.get("link") or ""] = htmllib.unescape(((item.get("title") or {}).get("rendered")) or "")
            total = int(r.headers.get("x-wp-totalpages") or 1)
            page += 1
        return {k: v for k, v in out.items() if k}
    text = http.get_text(source, headers={"Accept": "application/xml,application/json,*/*"})
    t = text.lstrip()
    if t.startswith(("[", "{")):
        data = json.loads(t)
        items = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])
        return {str(x.get("path") or x.get("url") or x.get("slug")): str(x.get("title") or "") for x in items
                if isinstance(x, dict) and (x.get("path") or x.get("url") or x.get("slug"))}
    return {htmllib.unescape(u): "" for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)}


def check_programs(ctx: Ctx) -> list[dict]:
    """N. Daily: a page on the company's site that wasn't there before and whose
    address or title reads like a students, internships or program page. A source's first read is a silent
    baseline."""
    sources = per_company(ctx.cfg, "program_pages")
    problems: list[dict] = []
    http = ctx.http()
    try:
        for key in pick(ctx.db, "programs", sorted(sources), 1, ctx.now):
            if ctx.out_of_time():
                break
            c = ctx.comps[key]
            skey = f"blocked:programs:{key}"
            raw = ctx.db.get(skey)
            state = json.loads(raw) if raw else {}
            new, errors = [], []
            for source in sources[key]:
                try:
                    pages = page_list(http, source)
                except Exception as e:  # noqa: BLE001 — refused: tomorrow
                    if out_of_budget(e):
                        return problems
                    errors.append(outcome(e))
                    log.info("moves: page list %s of %s not read: %s", source, key, str(e)[:160])
                    continue
                before = state.get(source)
                state[source] = sorted(set(pages) | set(before or []))
                if before is not None:
                    new += [(u, t) for u, t in pages.items() if u not in before
                            and STUDENT.search(f"{urlsplit(u).path} {t}")]
            if errors and len(errors) == len(sources[key]):
                done(ctx.db, "programs", key, worst(errors), ctx.now)
                continue
            restore_kv = {skey: raw or "", **due_restore(ctx.db, "programs", key)}
            ctx.db.set(skey, json.dumps(state))
            done(ctx.db, "programs", key, "ok", ctx.now)
            if new:
                shown = ", ".join(f"{u}" + (f" ({t})" if t else "") for u, t in new[:5])
                problems.append(alert(ctx.db, c, "programs", "new page", f"its site has new student or program pages: {shown}",
                                      "A new students, internships or program page is often the first sign of a new "
                                      "program or job site. Open it and compare with the config.", restore_kv,
                                      [{"suffix": u, "rule": "manual", "summary": f"its site has a new page: {u}"
                                        + (f" ({t})" if t else "")} for u, t in new[:5]]))
    finally:
        http.close()
    return problems


# G: new labels ----------------------------------------------------------------------------------------------

GOLDMAN_TYPES = ("RoleSearchExperience", "ExternalSourceType")
LABEL = re.compile(r"intern|universit|student|graduate|new grad|phd|campus|early|co-?op|apprentic|rotation|fellow|"
                   r"residen", re.I)


def _new_labels(db: DB, c: Company, labels: set[str], what: str, detail: str) -> list[dict]:
    key = f"blocked:labels:{c.key}"
    raw = db.get(key)
    known = set(json.loads(raw)) if raw else None
    db.set(key, json.dumps(sorted(labels | (known or set()))))
    new = sorted(labels - known) if known is not None else []  # first look: a silent baseline
    if not new:
        return []
    return [alert(db, c, "labels", "new label", f"{what}: {', '.join(new)}", detail, {key: raw or ""},
                  [{"suffix": x, "rule": "manual", "summary": f"{what}: {x}"} for x in new])]


def check_labels(ctx: Ctx) -> list[dict]:
    """G. Daily: the values Goldman's job API (the one InternWatch reads) accepts for experience and source types.
    A new one (Goldman's schema already names an unused AVATURE source) can mean roles InternWatch doesn't ask for."""
    c = ctx.comps.get("goldman-sachs")
    if c is None or not pick(ctx.db, "labels", [c.key], 1, ctx.now):
        return []
    from .checkers.goldman import API
    query = "{ " + " ".join(f'{t}: __type(name: "{t}") {{ enumValues {{ name }} }}' for t in GOLDMAN_TYPES) + " }"
    http = ctx.http()
    try:
        data = http.post_json(API, json={"query": query}, headers={"Accept": "application/json"})
    except Exception as e:  # noqa: BLE001 — refused: tomorrow
        if not out_of_budget(e):
            done(ctx.db, "labels", c.key, outcome(e), ctx.now)
        return []
    finally:
        http.close()
    labels = {f"{t}.{v['name']}" for t in GOLDMAN_TYPES for v in (((data.get("data") or {}).get(t) or {})
                                                                   .get("enumValues") or [])}
    if not labels:
        done(ctx.db, "labels", c.key, "failed", ctx.now)
        return []
    done(ctx.db, "labels", c.key, "ok", ctx.now)
    return _new_labels(ctx.db, c, labels, "Goldman's job API has new experience or source types",
                       "InternWatch asks Higher for PROFESSIONAL, EARLY_CAREER and CAMPUS roles. A new type can hold "
                       "roles it never asks for (the AVATURE source would be the Avature-only programs).")


def observe(cfg: Config, db: DB, o) -> list[dict]:
    """Per poll (runner._liveness_observe), no request: Meta's team labels in its healthy, complete poll. A new
    student-like team ("Internship - …", "University Grad - …") can carry internships the Internship label misses."""
    c = blocked(cfg).get(o.company.key)
    if c is None or c.key != "meta":
        return []
    if not (o.ok and not o.degraded and not o.partial and not o.unchanged and o.mode == "full" and o.jobs):
        return []
    labels = {x.strip() for j in o.jobs for x in (j.department or "").split(" / ") if LABEL.search(x)}
    return _new_labels(db, c, labels, "Meta labels jobs with new student teams",
                       "InternWatch marks Meta's internships by its Internship label and their titles. A new student "
                       "team can be a new program; check that its roles reach you.")


# S: parallel boards ----------------------------------------------------------------------------------------

def source_id(x: dict) -> str:
    return x["checker"] + ":" + ",".join(f"{k}={v}" for k, v in sorted((x.get("settings") or {}).items()))


def check_parallel(ctx: Ctx) -> list[dict]:
    """S. Daily: boards next to the configured ones (a campus board, a hidden Workday site, RippleMatch), read with
    the existing adapters but never stored. A role posted there since the first look, matching your filters (or
    unsure) and with a title InternWatch doesn't have for the company (open, or closed within 30 days), alerts
    once: twins of a configured board's postings and rejected roles stay quiet."""
    from .adapters import get_checker
    from .adapters.base import FetchContext
    from .filters import evaluate
    sources = {source_id(x): x for x in entries(ctx.cfg, "parallel_sources")}
    problems: list[dict] = []
    http = ctx.http()
    try:
        for sid in pick(ctx.db, "parallel", sorted(sources), 1, ctx.now):
            if ctx.out_of_time():
                break
            x = sources[sid]
            c = ctx.comps[x["company"]]
            try:
                jobs = get_checker(x["checker"]).fetch(http, x.get("settings") or {}, FetchContext())
            except Exception as e:  # noqa: BLE001 — refused: tomorrow
                if out_of_budget(e):
                    break
                done(ctx.db, "parallel", sid, outcome(e), ctx.now)
                log.info("moves: parallel source %s not read: %s", sid, str(e)[:160])
                continue
            skey = f"blocked:parallel:{c.key}:{sid}"
            raw = ctx.db.get(skey)
            state = json.loads(raw) if raw else None
            ids = {j.id for j in jobs}
            alerts.seen(ctx.db, c.key, "posting", {f"title:{j.title}" for j in jobs}, scope=sid)
            new_state = {"ids": sorted(ids | set((state or {}).get("ids") or [])),
                         "alerted": (state or {}).get("alerted") or []}
            done(ctx.db, "parallel", sid, "ok", ctx.now)
            if state is None:
                ctx.db.set(skey, json.dumps(new_state))
                continue  # first look: a silent baseline
            stored = stored_titles(ctx.db, c.key)
            found = []
            for j in jobs:
                t = norm_title(j.title)
                if j.id in state["ids"] or t in stored or t in new_state["alerted"]:
                    continue
                m = evaluate(j, ctx.cfg.rules, category=c.category, locations=c.locations,
                             extra_role_keywords=c.extra_role_re)
                if m.matched:
                    found.append((j, m))
                    new_state["alerted"].append(t)
            ctx.db.set(skey, json.dumps(new_state))
            if found:
                shown = "; ".join(f"'{j.title}' ({j.location or 'no location'}){' (unsure)' if m.unsure else ''} "
                                  f"{j.url}" for j, m in found[:5])
                problems.append(alert(ctx.db, c, "parallel", "posting elsewhere?",
                                      f"{sid} lists {len(found)} matching role(s) InternWatch doesn't have: {shown}",
                                      "InternWatch only watches this board, it doesn't read it. If it keeps posting "
                                      "roles you want, add it to the company's config.", {skey: raw},
                                      [{"suffix": f"{sid}:{norm_title(j.title)}", "rule": "posting", "scope": sid,
                                        "item": f"title:{j.title}", "summary": f"{sid} lists '{j.title}', a matching role "
                                                                               "InternWatch doesn't have"} for j, _ in found]))
    finally:
        http.close()
    return problems


# L: third-party lists, board registries, Getro boards ---------------------------------------------------------

REGISTRY_KEYS = {"greenhouse": "greenhouse:board={slug}", "lever": "lever:site={slug}", "ashby": "ashby:board={slug}",
                 "workable": "workable:account={slug}", "smartrecruiters": "smartrecruiters:company={slug}",
                 "workday": "workday:site={site},tenant={slug}", "oracle": "oracle:host={host},site={site}",
                 "eightfold": "eightfold:domain={domain}"}
REGISTRY_URLS = {"greenhouse": "https://job-boards.greenhouse.io/{slug}", "lever": "https://jobs.lever.co/{slug}",
                 "ashby": "https://jobs.ashbyhq.com/{slug}", "workable": "https://apply.workable.com/{slug}",
                 "smartrecruiters": "https://careers.smartrecruiters.com/{slug}",
                 "workday": "https://{slug}.{wd}.myworkdayjobs.com/{site}"}


def _md_cell(cell: str) -> str:
    cell = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", TAG.sub(" ", cell))
    return " ".join(htmllib.unescape(cell).replace("*", " ").split())


def list_rows(fmt: str, text: str) -> list[tuple[str, str, str, str | None]]:
    """(company, title, url, system key if the source names it outright) from one third-party list."""
    if fmt == "markdown":  # pipe tables; "↳" repeats the company above
        rows, header, company = [], None, ""
        for line in text.splitlines():
            if not line.startswith("|"):
                header = None if not line.strip() or line.startswith("#") else header
                continue
            cells = [x.strip() for x in line.strip().strip("|").split("|")]
            if cells and _md_cell(cells[0]).lower() == "company":
                header = [_md_cell(x).lower() for x in cells]
                continue
            if header is None or set("".join(cells)) <= set("-: ") or len(cells) < len(header):
                continue
            col = dict(zip(header, cells))
            name = _md_cell(col.get("company", ""))
            company = company if name in ("", "↳") else name
            def links(cell):
                found = [a or b for a, b in re.findall(r'href="([^"]+)"|\]\((https?://[^)\s]+)\)', cell)]
                return [u for u in found if "img.shields.io" not in u and "imgur.com" not in u]
            apply = next((col[k] for k in ("posting", "apply", "application", "link") if col.get(k)), "")
            urls = links(apply) or links(" ".join(v for k, v in col.items() if k != "company"))
            title = _md_cell(col.get("position") or col.get("role") or col.get("title") or "")
            if company and urls:
                rows.append((company, title, htmllib.unescape(urls[0]), None))
        return rows
    data = json.loads(text)
    items = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])
    if fmt == "simplify":
        return [(x.get("company_name") or "", x.get("title") or "", x.get("url") or "", None) for x in items]
    if fmt == "boardsweep":
        return [(x.get("company") or "", x.get("title") or "", x.get("url") or "", None) for x in items]
    if fmt == "trackr":
        return [(str(x.get("companyId") or "").replace("-", " "), x.get("name") or "", x.get("url") or "", None)
                for x in items]
    if fmt == "registry":
        out = []
        for x in items:
            ats, v = x.get("ats"), {k: str(x.get(k) or "").lower() for k in ("slug", "site", "host", "domain", "wd")}
            if ats in REGISTRY_KEYS and v["slug"]:
                v["host"] = v["host"] or v["slug"]
                url = REGISTRY_URLS.get(ats, "").format(**{**v, "slug": x.get("slug"), "site": x.get("site") or ""})
                out.append((x.get("name") or "", "", url, REGISTRY_KEYS[ats].format(**v)))
        return out
    raise ValueError(f"unknown list format {fmt}")


def ripplematch_rows(text: str) -> list[tuple[str, str, str, str | None]]:
    out = []
    for slug in re.findall(r"<loc>\s*https://app\.ripplematch\.com/company/([\w-]+)/?\s*</loc>", text):
        out.append((slug.replace("-", " "), "", f"https://app.ripplematch.com/company/{slug}",
                    f"ripplematch:company={slug.lower()}"))
    return out


def company_of(index, comps: dict[str, Company], name: str, url: str, slug: bool = False) -> Company | None:
    """The blocked company a list row belongs to: matched among every configured company first, so another
    company's row is never taken for one of the 31. In a source that names companies by slug (RippleMatch, Trackr),
    "ukg-ultimate-kronos-group" also matches the company whose name starts it."""
    from .crosscheck import Row, norm_company
    key = index.match(Row("", "", name, "", "", url, "", ""))
    if key is None and slug:
        n = norm_company(name)
        for c in comps.values():
            for alias in c.all_names:
                a = norm_company(alias)
                if a and n.startswith(a + " ") and len(a) >= 3:
                    return c
        return None
    return comps.get(key)


def check_listings(ctx: Ctx) -> list[dict]:
    """L. Every active company, daily: a job system a list links that the config doesn't name (aliases and the parallel
    boards count as named) or that no stored posting links. A first look is never silent: Akuna's second board was
    missed for that reason, so a list's first download raises what it finds like any other. One alert per company and
    job system, however many lists link it. An unchanged list (ETag) costs one request. vanshb03's list links everything
    through go.vansh.nyc, whose robots.txt disallows all readers, so its links are never followed and reveal nothing."""
    from .crosscheck import CompanyIndex
    sources = {x["name"]: x for x in opts(ctx.cfg).get("listings") or []}
    comps = {c.key: c for c in ctx.cfg.active}
    index = CompanyIndex(ctx.cfg.companies)
    al = aliases(ctx.cfg)
    found: dict[tuple[str, str], tuple[str, str, str]] = {}
    http = ctx.http(read_timeout=90)
    try:
        for name in pick(ctx.db, "listings", sorted(sources), 1, ctx.now):
            if ctx.out_of_time():
                break
            src = sources[name]
            etag_key, skey = f"lists:etag:{name}", f"lists:links:{name}"
            headers = {"If-None-Match": ctx.db.get(etag_key)} if ctx.db.get(skey) and ctx.db.get(etag_key) else {}
            try:
                r = http.get(src["url"], headers=headers, ok_statuses=(304,), timeout=90)
            except Exception as e:  # noqa: BLE001 — refused: tomorrow
                if out_of_budget(e):
                    break
                done(ctx.db, "listings", name, outcome(e), ctx.now)
                log.info("moves: list %s not read: %s", name, str(e)[:160])
                continue
            if r.status == 304:
                done(ctx.db, "listings", name, "ok", ctx.now)
                continue
            try:
                rows = ripplematch_rows(r.text) if src["format"] == "ripplematch" else list_rows(src["format"], r.text)
            except (ValueError, KeyError, TypeError) as e:
                done(ctx.db, "listings", name, "failed", ctx.now)
                log.warning("moves: list %s could not be parsed: %s", name, e)
                continue
            linked: dict[str, set[str]] = {}
            for company, title, url, system in rows:
                c = company_of(index, comps, company, url, slug=src["format"] in ("ripplematch", "trackr"))
                if c is None:
                    continue
                for k in ([al.get(system, system)] if system else systems_in(url, "", c, al)):
                    linked.setdefault(c.key, set()).add(k)
                    found.setdefault((c.key, k), (src.get("label", name), title, url))
            ctx.db.set(skey, json.dumps({k: sorted(v) for k, v in linked.items()}))
            if r.headers.get("etag"):
                ctx.db.set(etag_key, r.headers["etag"])
            done(ctx.db, "listings", name, "ok", ctx.now)
    finally:
        http.close()
    if all(ctx.db.get(f"lists:links:{n}") for n in sources):  # every list has been read: what none links has gone
        everywhere: dict[str, set[str]] = {}
        for n in sources:
            for key, systems in load(ctx.db, f"lists:links:{n}", {}).items():
                everywhere.setdefault(key, set()).update(systems)
        for company in {a["company"] for a in alerts.live(ctx.db, rule="list_system")}:
            alerts.seen(ctx.db, company, "list_system", everywhere.get(company, set()), scope="lists")
    raw = ctx.db.get("lists:alerted")
    told = set(json.loads(raw)) if raw else set()
    problems: list[dict] = []
    for (key, k), (label, title, url) in sorted(found.items()):
        c = comps[key]
        if f"{key}|{k}" in told or k in known_systems(ctx, c):
            continue
        told.add(f"{key}|{k}")
        if liveness._portal(k) and k in liveness.posting_portals(ctx.db, key):
            continue  # a stored posting links it: InternWatch reads what is posted there
        summary = f"{label} links a job site InternWatch doesn't read: {k} (e.g. '{title or 'a posting'}' {url})"
        problems.append(alert(ctx.db, c, f"list:{k}", "new job site?", summary,
                              "A list maintainer or contributor found a posting there. If it is the company's and "
                              "carries student roles, add it to the config.", {"lists:alerted": raw or ""},
                              [{"suffix": "board", "rule": "list_system", "item": k, "scope": "lists", "url": url,
                                "summary": summary}]))
    ctx.db.set("lists:alerted", json.dumps(sorted(told)))
    return problems


def check_getro(ctx: Ctx) -> list[dict]:
    """L, Getro. Daily: Getro-powered VC job boards (Accel, Thrive) copy some companies' jobs from their
    careers page itself (source "career_page"), the page InternWatch can't read. A job new on Getro's copy that
    links a job system InternWatch doesn't read alerts; one whose posting id InternWatch doesn't have waits for
    confirm(). The first look is a silent baseline."""
    entries_ = {x["company"]: x for x in entries(ctx.cfg, "getro")}
    al = aliases(ctx.cfg)
    problems: list[dict] = []
    http = ctx.http(read_timeout=60)
    try:
        for key in pick(ctx.db, "getro", sorted(entries_), 1, ctx.now):
            if ctx.out_of_time():
                break
            c, x = ctx.comps[key], entries_[key]
            board = x["board"].rstrip("/")
            try:
                index = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", http.get_text(board + "/sitemap.xml"))
                jobs = {}
                for sm in [u for u in index if "jobs" in u.rsplit("/", 1)[-1]]:
                    for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", http.get_text(sm)):
                        m = re.search(re.escape(x["path"].rstrip("/")) + r"/jobs/(\d+)-?([\w%-]*)", u)
                        if m:
                            jobs[m.group(1)] = (u, m.group(2).replace("-", " "))
            except Exception as e:  # noqa: BLE001 — refused: tomorrow
                if out_of_budget(e):
                    break
                done(ctx.db, "getro", key, outcome(e), ctx.now)
                log.info("moves: Getro board %s not read: %s", board, str(e)[:160])
                continue
            skey = f"blocked:getro:{key}"
            raw = ctx.db.get(skey)
            seen = set(json.loads(raw)) if raw else None
            ctx.db.set(skey, json.dumps(sorted(set(jobs) | (seen or set()))))
            done(ctx.db, "getro", key, "ok", ctx.now)
            if seen is None or not jobs:
                continue  # first look: a silent baseline
            known = known_systems(ctx, c)
            toks = stored_tokens(ctx.db, key)
            elsewhere, unknown = {}, {}
            for gid in sorted(set(jobs) - seen)[:20]:
                url, title = jobs[gid]
                try:
                    page = http.get_text(url, headers={"Accept": "text/html"})
                except Exception as e:  # noqa: BLE001 — that one job page: skipped
                    if out_of_budget(e):
                        break
                    continue
                links = [htmllib.unescape(u) for u in re.findall(r'"url":"(https?:[^"]+)"', page)]
                for link in links:
                    for k in systems_in(link, "", c, al) - known:
                        elsewhere.setdefault(k, (title, link))
                    ids = ids_with_titles(f'<a href="{link}">{title}</a>')
                    unknown.update({i: title for i in ids if not is_stored(i, toks)})
            note_unknown(ctx.db, "getro", c, unknown, f"Getro's copy ({board})", ctx.started)
            if elsewhere:
                shown = "; ".join(f"{k} (e.g. '{t}' {u})" for k, (t, u) in list(elsewhere.items())[:3])
                problems.append(alert(ctx.db, c, "getro", "new job site?",
                                      f"Getro's copy of its careers page links a job site InternWatch doesn't read: {shown}",
                                      f"{board} copies {c.name}'s jobs from its careers page. The company may now post "
                                      "there; if so and it carries student roles, add it to the config.",
                                      {skey: raw, **due_restore(ctx.db, "getro", key)},
                                      [{"suffix": k, "rule": "list_system", "item": k, "scope": "getro", "url": v[1],
                                        "summary": f"Getro's copy of its careers page links a job site InternWatch "
                                                   f"doesn't read: {k}"} for k, v in elsewhere.items()]))
    finally:
        http.close()
    return problems


# watching the watchers ---------------------------------------------------------------------------------

def weekly(cfg: Config, check: str, key: str) -> bool:
    """A read that comes round once a week, so three missed mornings would say nothing about it."""
    if check == "joblist":
        return float((opts(cfg).get("job_lists") or {}).get(key, {}).get("every_days", 1)) > 1
    if check == "careers":
        return liveness.settings(cfg)["scan_every"] > timedelta(days=1)
    return check in WEEKLY


def dark(cfg: Config, db: DB, check: str, key: str, now) -> str | None:
    """The day a source last answered, if it has gone dark. A daily read has when it missed DARK_MORNINGS mornings in a
    row: failed, or never reached because time ran out. A day with no run isn't a morning, and two runs in a day are one.
    A weekly read, or a page waiting out a refusal, has when it hasn't answered for DARK_DAYS. None while it answers,
    and for a page that never has: one that refuses scripts from the start is no news. The boards in NEVER_WAIT have no
    such excuse, so one that never answered counts from its first read."""
    history = load(db, f"blocked:rate:{check}:{key}", [])
    days = [x[0] for x in history if x[1]]
    last = max(days + [db.get(f"blocked:ok:{check}:{key}") or ""]) or None
    if weekly(cfg, check, key) or refused_last(db, check, key):
        return last if last and (now.date() - datetime.fromisoformat(last).date()).days > DARK_DAYS else None
    if last:
        missed = [d for d in load(db, "blocked:mornings", []) if d > last]
    elif check in NEVER_WAIT and history:
        last = history[0][0]
        missed = [d for d in load(db, "blocked:mornings", []) if d >= last]
    else:
        return None
    return last if len(missed) >= DARK_MORNINGS else None


def _watched(ctx: Ctx, check: str) -> set[str]:
    """What `check` reads today, so a source taken out of the config is not reported as dark."""
    if check == "listings":
        return {x["name"] for x in opts(ctx.cfg).get("listings") or []}
    if check == "parallel":
        return {source_id(x) for x in entries(ctx.cfg, "parallel_sources")}
    if check == "workday":
        return set(workday_tenants(ctx))
    if check == "careers":
        return {c.key for c in ctx.cfg.active if c.careers_url and c.key not in ctx.comps}
    if check in ("watch", "watch-full"):
        from .watch import boards  # watch imports this module
        return {b.id for b in boards(ctx.cfg, ctx.db) if b.check == check}
    return set(ctx.comps)


def check_dark(ctx: Ctx) -> list[dict]:
    """A list or check that stopped answering stops watching without a word: its reads are only logged. No request."""
    problems: list[dict] = []
    companies = {c.key: c for c in ctx.cfg.companies}
    watched: dict[str, set[str]] = {}
    for r in ctx.db.q("SELECT key FROM kv WHERE key LIKE 'blocked:rate:%'"):
        _, _, check, key = r["key"].split(":", 3)
        if check not in watched:
            watched[check] = _watched(ctx, check)
        last = dark(ctx.cfg, ctx.db, check, key, ctx.now)
        if last is None or key not in watched[check]:
            continue
        company, _, board = key.partition("/")  # a watched board's key: company/board
        c = companies.get(company)
        label = f"{LABELS.get(check, check)} {board}" if c and board else LABELS.get(check, check)
        problems.append({"key": c.key if c else "", "name": c.name if c else key, "checker": check, "kind": "check gone dark",
                         "summary": f"{label} has not answered since {last}",
                         "detail": "It is no longer watching anything: see `internwatch liveness` and data/logs.",
                         "since": f"{last}T00:00:00Z", "careers_url": c.careers_url[0] if c and c.careers_url else "",
                         "alert": {"id": f"dark:{check}:{key}", "rule": "dark", "check": check, "item": key}})
    return problems


# running them -----------------------------------------------------------------------------------------

CHECKS: list[tuple[str, callable]] = [  # (name, fn(ctx) -> problems), cheapest first, so a slow site starves none of them
    ("confirm", check_confirm),
    ("workday", check_workday),
    ("joblist", check_job_lists),
    ("programs", check_programs),
    ("labels", check_labels),
    ("parallel", check_parallel),
    ("page", check_pages),
    ("listings", check_listings),
    ("getro", check_getro),
    ("archive", check_archive),
]


LABELS = {"confirm": "unknown job ids (confirmed next day)", "workday": "W  hidden Workday sites",
          "parallel": "S  parallel boards", "page": "P  careers and WordPress pages", "joblist": "J  own job lists",
          "programs": "N  new student/program pages", "labels": "G  Goldman API types", "archive": "A  archive.org copies",
          "listings": "L  third-party lists", "getro": "L  Getro copies", "careers": "Careers page",
          "watch": "Watched board", "watch-full": "Watched board, weekly read"}


def status(cfg: Config, conn) -> str:
    """What these checks track, for `internwatch liveness` (read-only: conn is a read-only sqlite3 connection)."""
    comps = blocked(cfg)
    kv = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM kv WHERE key LIKE 'blocked:%' "
                                                      "OR key LIKE 'live_alert:%'")}
    since = (utcnow() - timedelta(days=28)).date().isoformat()
    lines = [f"companies whose careers page can't be read, watched by moves.py: {len(comps)}"]
    for check, label in LABELS.items():
        if check == "careers":  # liveness.status reports these
            continue
        if check == "confirm":
            pending = sum(len(json.loads(v or "{}")) for k, v in kv.items() if k.startswith("blocked:pending:"))
            lines.append(f"  {label}: {pending} waiting for a healthy poll")
            continue
        at = [v for k, v in kv.items() if k.startswith(f"blocked:at:{check}:") and v]
        retry = sum(1 for k, v in kv.items() if k.startswith(f"blocked:retry:{check}:") and v)
        hist = [x for k, v in kv.items() if k.startswith(f"blocked:rate:{check}:") for x in json.loads(v or "[]")
                if x[0] >= since]
        rate = f"{sum(x[1] for x in hist)}/{len(hist)} reads answered in 28 days" if hist else "no reads yet"
        lines.append(f"  {label}: {len(at)} read, last {max(at) if at else 'never'}; {rate}; {retry} to retry")
    mine = {"page", "archive", "archive-pages", "joblist", "programs", "labels", "parallel", "getro", "workday-hidden"}
    recent = []
    for k, v in sorted(kv.items()):
        parts = k.split(":", 2)
        if parts[0] == "live_alert" and len(parts) == 3 and v and v[:10] >= since and parts[1] in comps \
                and (parts[2] in mine or parts[2].startswith("list:")):
            recent.append(f"{parts[1]} ({parts[2]}, {v[:10]})")
    lines.append(f"  alerts in the last 28 days: {len(recent)}" + (f": {', '.join(recent[:12])}" if recent else ""))
    return "\n".join(lines)


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


def finish(cfg: Config, db: DB, gate, make_http, healthy: set) -> list[dict]:
    """Last in a daily run, and no request: this morning counts, whatever was read, so a third miss alerts the same
    morning even if time ran out."""
    today = utcnow().date().isoformat()
    db.set("blocked:mornings", json.dumps(sorted({*load(db, "blocked:mornings", []), today})[-40:]))
    return check_dark(Ctx(cfg, db, gate, make_http, float("inf"), set(healthy)))


