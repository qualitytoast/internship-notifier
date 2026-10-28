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


def confirm(ctx: Ctx, check: str, label: str, any_job=False) -> list[dict]:
    """Every morning: a job id noted on an earlier run that the company's healthy poll today still doesn't have.
    Student-like or unknown titles only, unless any_job (a bool, or a function of the company key: Uber's job
    sitemap carries every posting, so any job missing there counts)."""
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
            if (any_job(c.key) if callable(any_job) else any_job) or not p["title"] or student_like(p["title"]):
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
    """W. A new hidden site (Disallow line) on a tenant of the 31, or any new site on a tenant that the weekly
    Workday check can't see (myworkdaysite.com hosts, parent companies). Weekly per tenant. robots.txt comes from
    the checks' cache when it is fresh, else one plain GET that leaves the cache as it is."""
    tenants = workday_tenants(ctx)
    problems: list[dict] = []
    http = None
    try:
        for host in pick(ctx.db, "workday", sorted(tenants), 7, ctx.now):
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
            if known is None:
                continue  # first look: a silent baseline
            new = sorted(x for x in sites - known if x.lower() not in configured)
            if new:
                which = "hidden " if covered else ""
                problems.append(alert(
                    ctx.db, c, "workday-hidden", "new site", f"Workday tenant {host} lists new {which}sites: {', '.join(new)}",
                    "A hidden site (a Disallow line in robots.txt) can hold postings InternWatch doesn't read: American "
                    "Family moved an intern posting to its hidden AmFam-Private site on Oct 24. Add it to the config "
                    "if it has student roles.", restore_kv))
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
    """P. Weekly per company, spread over the week: the job systems each source names (an iCIMS portal, an Avature
    site and an Eightfold domain each on their own; a link to a configured host counts as that system) and the job
    ids it links. A source's first read is a silent baseline. New job ids wait for confirm()."""
    problems: list[dict] = []
    al = aliases(ctx.cfg)
    http = ctx.http()
    try:
        for key in pick(ctx.db, "page", sorted(k for k, c in ctx.comps.items() if page_sources(ctx, c)), 7, ctx.now):
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
                done(ctx.db, "page", key, "refused" if "refused" in errors else "failed", ctx.now)
                continue
            restore_kv = {skey: raw or "", **due_restore(ctx.db, "page", key)}
            known = known_systems(ctx, c)
            toks = stored_tokens(ctx.db, key)
            new_sys, gone, unknown = [], [], {}
            for url, (systems, ids) in results.items():
                before = state.get(url)
                state[url] = {"systems": systems, "ids": sorted(set(ids) | set((before or {}).get("ids") or []))}
                if before is None:
                    continue  # this source's first read: a silent baseline
                new_sys += [x for x in systems if x not in before["systems"] and x not in known]
                gone += [x for x in before["systems"] if x in known and x not in systems]
                unknown.update({i: t for i, t in ids.items() if i not in before["ids"] and not is_stored(i, toks)})
            ctx.db.set(skey, json.dumps(state))
            done(ctx.db, "page", key, "ok", ctx.now)
            note_unknown(ctx.db, "page", c, unknown, "its careers pages", ctx.started)
            if new_sys or gone:
                parts = ([f"now point at {', '.join(sorted(set(new_sys)))}"] if new_sys else []) + \
                        ([f"no longer mention {', '.join(sorted(set(gone)))}"] if gone else [])
                problems.append(alert(ctx.db, c, "page", "moved?", f"its careers pages {' and '.join(parts)}",
                                      f"InternWatch reads {', '.join(sorted(known))}. The jobs may have moved to "
                                      f"another job site: compare {', '.join(results)} with the config.", restore_kv))
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


# running them -----------------------------------------------------------------------------------------

CHECKS: list[tuple[str, callable]] = [  # (name, fn(ctx) -> problems), cheapest first
    ("confirm", check_confirm),
    ("workday", check_workday),
    ("page", check_pages),
]


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
