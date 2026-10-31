"""Boards InternWatch reads but doesn't store, for a role nothing else has.

A board whose `new job site?` alert you dismissed would otherwise never be read again, and a mirror (liveness.aliases)
was proven once and then trusted for good. Both are read here (settings `liveness.watch_boards`, and the dismissed
alerts), and a job alerts only when all three are true:

  1. it passes your filters, unsure roles included
  2. it isn't stored: no stored job has its id or requisition id, and none has the same title_key in a location that
     also passes your location rule. Titles naming different years aren't twins, and a title twin must be open or closed
     within TITLE_TWIN_DAYS
  3. a healthy poll of the company on a later run still doesn't have it: a mirror can simply post first

There is no baseline. A board's other jobs fail 1 or 2 on every read, so a first look is never silent and a job retitled
into an internship is caught on the next read. Each job alerts once, and the alert clears when the job is stored or
leaves the board. Nothing here stores a job or touches a poll.

Reads are recorded like the checks' in moves.py (kv blocked:*, checks "watch" and "watch-full"): one that fails comes back
the next morning and three missed mornings raise `check gone dark`. A dismissed board that answers 404, 410, 422 or an
empty page has nothing today, which is what a dead board does. A board robots.txt has always forbidden can't be read,
which `internwatch liveness` says. A weekly full read starts only if the time left covers its last read.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit

from . import alerts, moves
from .adapters import get_checker
from .adapters.base import FetchContext
from .config import Company, Config
from .crosscheck import _YEARS, title_key
from .db import DB, iso
from .filters import evaluate, vague_location
from .locations import location_decision
from .models import CheckTimeout, Job, RobotsBlocked, ShapeError

log = logging.getLogger(__name__)

TITLE_TWIN_DAYS = 30
ROOM = 1.15  # a weekly full read starts only with this much more time than its last read took
NOTHING_TODAY = re.compile(r"HTTP (?:404|410|422)\b")
ONE_SETTING = {"greenhouse": "board", "lever": "site", "ashby": "board", "smartrecruiters": "company"}


@dataclass
class Board:
    company: str
    name: str
    checker: str
    settings: dict
    every_days: float = 1
    dismissed: bool = False

    @property
    def id(self) -> str:
        return f"{self.company}/{self.name}"

    @property
    def check(self) -> str:
        return "watch" if self.every_days <= 1 else "watch-full"


def workday_settings(url: str) -> dict:
    """A system key loses a Workday site's host and case, so they come from the link that named it."""
    p = urlsplit(url)
    path = [x for x in p.path.split("/") if x and not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", x)]
    if "recruiting" in path:
        i = path.index("recruiting")
        return {"host": p.netloc, "tenant": path[i + 1], "site": path[i + 2]}
    return {"host": p.netloc, "tenant": p.netloc.split(".")[0], "site": path[0]}


def source_of(system: str, url: str) -> tuple[str, dict] | None:
    """The checker and settings that read a job system, from its key and a link to it. None when they can't be told."""
    kind, _, rest = system.partition(":")
    kv = dict(x.split("=", 1) for x in rest.split(",") if "=" in x)
    name = ONE_SETTING.get(kind)
    if name and kv.get(name):
        return kind, {name: kv[name]}
    if kind == "icims" and kv.get("portal"):
        return kind, {"portal": "https://" + kv["portal"]}
    if kind == "oracle" and kv.get("host") and kv.get("site"):
        return kind, {"host": kv["host"], "site": kv["site"].upper()}
    if kind == "workday" and "myworkday" in url:
        try:
            return kind, workday_settings(url)
        except IndexError:
            return None
    return None


def dismissed(cfg: Config, db) -> dict[tuple[str, str], str]:
    """{(company, job system): link} of each `new job site?` alert you dismissed, until the system is in the config.
    Also after the alert cleared because no list links the board any more: the board can still post."""
    active = {c.key for c in cfg.active}
    out: dict[tuple[str, str], str] = {}
    for a in db.q("SELECT * FROM alerts WHERE kind='new job site?' AND dismissed_at IS NOT NULL ORDER BY id"):
        d = json.loads(a["data"])
        if a["company"] in active and d.get("item") and not alerts._cfg_system(cfg, a, d):
            out[(a["company"], d["item"])] = d.get("url") or ""
    return out


def boards(cfg: Config, db) -> list[Board]:
    lv = moves.opts(cfg)
    active = {c.key for c in cfg.active}
    out = [Board(x["company"], x.get("name") or moves.source_id(x), x["checker"], x.get("settings") or {},
                 float(x.get("every_days", 1))) for x in lv.get("watch_boards") or [] if x.get("company") in active]
    every = lv.get("watch_every_days") or {}
    for (company, system), url in dismissed(cfg, db).items():
        source = source_of(system, url)
        if source:
            out.append(Board(company, system, *source, float(every.get(system, 1)), True))
    return out


# rule 2 --------------------------------------------------------------------------------------------------------------

def job_ids(job: Job) -> list[str]:
    """Every id a posting goes by. On Workday its id is a path that ends in the requisition: …/Title_JR2012345."""
    tail = job.id.rstrip("/").rsplit("/", 1)[-1]
    return [job.id, tail, tail.rsplit("_", 1)[-1], *(str(a) for a in job.extra.get("alt_ids") or [])]


def item_of(job: Job) -> str:
    return job_ids(job)[2]


class Stored:
    """What InternWatch has for a company."""

    def __init__(self, cfg: Config, db: DB, c: Company, now):
        self.toks = moves.stored_tokens(db, c.key)
        self.places = c.locations or cfg.rules.default_locations
        self.titles: dict[frozenset, list] = {}
        since = iso(now - timedelta(days=TITLE_TWIN_DAYS))
        for r in db.q("SELECT title, location FROM jobs WHERE company=? AND (removed_at IS NULL OR removed_at >= ?)",
                      c.key, since):
            self.titles.setdefault(title_key(r["title"]), []).append(r)

    def has(self, job: Job) -> bool:
        if any(moves.is_stored(i, self.toks) for i in job_ids(job)):
            return True
        years = set(_YEARS.findall(job.title))
        for r in self.titles.get(title_key(job.title), []):
            theirs = set(_YEARS.findall(r["title"]))
            if years and theirs and not years & theirs:
                continue
            if vague_location(job.location) or vague_location(r["location"]) \
                    or location_decision(r["location"], self.places)[0]:
                return True
        return False


# reading -------------------------------------------------------------------------------------------------------------

def has_room(ctx: moves.Ctx, b: Board) -> bool:
    took = ctx.db.get(f"blocked:took:{b.id}")
    return b.every_days <= 1 or not took or ctx.budget_end - time.monotonic() >= float(took) * ROOM


def read(ctx: moves.Ctx, http, b: Board) -> list[Job] | None:
    """The board's jobs, or None if it wasn't read. A dismissed board with nothing on it is read, and empty."""
    unreadable = f"blocked:unreadable:{b.check}:{b.id}"
    started = time.monotonic()
    fc = FetchContext()
    try:
        jobs = get_checker(b.checker).fetch(http, b.settings, fc)
    except RobotsBlocked as e:
        if ctx.db.get(f"blocked:ok:{b.check}:{b.id}"):
            moves.done(ctx.db, b.check, b.id, "failed", ctx.now)  # it used to answer: a read gone dark
        else:
            ctx.db.set(unreadable, str(e)[:160])
        return None
    except Exception as e:  # noqa: BLE001 — a board that fails is read again tomorrow
        if moves.out_of_budget(e):
            raise
        if b.dismissed and (isinstance(e, ShapeError) or NOTHING_TODAY.search(str(e))):
            moves.done(ctx.db, b.check, b.id, "ok", ctx.now)
            return []
        moves.done(ctx.db, b.check, b.id, moves.outcome(e), ctx.now)
        log.info("watch: %s not read: %s", b.id, str(e)[:160])
        return None
    if fc.partial:  # cut short (Workday keeps what it read through a timeout): its jobs say nothing about the rest
        if not ctx.out_of_time():
            moves.done(ctx.db, b.check, b.id, "failed", ctx.now)
        return None  # out of time it just stays due
    moves.done(ctx.db, b.check, b.id, "ok", ctx.now)
    ctx.db.set(f"blocked:took:{b.id}", f"{time.monotonic() - started:.0f}")
    ctx.db.set(unreadable, "")
    return jobs


def judge(ctx: moves.Ctx, b: Board, c: Company, jobs: list[Job], stored: Stored) -> None:
    """Rules 1 and 2. What is left waits for rule 3 (confirm), unless it has an alert already."""
    missing = {item_of(j): j for j in jobs
               if evaluate(j, ctx.cfg.rules, category=c.category, locations=c.locations,
                           extra_role_keywords=c.extra_role_re).matched and not stored.has(j)}
    alerts.seen(ctx.db, c.key, "posting", set(missing), scope=b.id)
    told = {d.get("item") for d in (json.loads(a["data"]) for a in alerts.live(ctx.db, c.key, "posting"))
            if d.get("scope") == b.id}
    key = f"blocked:pending:watch:{b.id}"
    pending = moves.load(ctx.db, key, {})
    keep = {}
    for item, j in missing.items():
        if item not in told:
            keep[item] = pending.get(item) or {"id": j.id, "title": j.title, "location": j.location, "url": j.url,
                                               "alt_ids": j.extra.get("alt_ids") or [], "found": ctx.started}
    ctx.db.set(key, json.dumps(keep))


def confirm(ctx: moves.Ctx, listed: list[Board], comps: dict[str, Company], stored_for) -> list[dict]:
    """Rule 3, no request: a job noted on an earlier run that today's healthy poll of the company still lacks."""
    problems: list[dict] = []
    for b in listed:
        key = f"blocked:pending:watch:{b.id}"
        raw = ctx.db.get(key)
        if not raw or raw == "{}":
            continue
        c = comps[b.company]
        keep, report = {}, []
        for item, p in json.loads(raw).items():
            if stored_for(c).has(Job(id=p["id"], title=p["title"], location=p["location"], extra={"alt_ids": p["alt_ids"]})):
                continue  # the poll caught up with it
            if p["found"] >= ctx.started or c.key not in ctx.healthy:
                keep[item] = p  # no healthy poll since it was seen: wait
            else:
                report.append((item, p))
        ctx.db.set(key, json.dumps(keep))
        if report:
            shown = "; ".join(f"'{p['title']}' ({p['location'] or 'no location'}) {p['url']}" for _, p in report[:5])
            problems.append(moves.alert(
                ctx.db, c, f"watch:{b.name}", "posting elsewhere?",
                f"{b.name} lists {len(report)} matching role(s) InternWatch doesn't have: {shown}",
                "InternWatch only watches this board, it doesn't store it. If it keeps posting roles you want, add it to "
                "the company's config.", {key: raw},
                [{"suffix": item, "rule": "posting", "item": item, "scope": b.id,
                  "summary": f"{b.name} lists '{p['title']}', a matching role InternWatch doesn't have: {p['url']}"}
                 for item, p in report]))
    return problems


def read_boards(ctx: moves.Ctx, listed: list[Board], comps: dict[str, Company], stored_for) -> None:
    """The daily reads first, then the weekly ones. A read that runs out of time stays due for the next morning."""
    groups: dict[tuple[float, str], dict[str, Board]] = {}
    for b in listed:
        groups.setdefault((b.every_days, b.check), {})[b.id] = b
    http = ctx.http()
    try:
        for (every, check), by_id in sorted(groups.items()):
            for bid in moves.pick(ctx.db, check, sorted(by_id), every, ctx.now):
                if ctx.out_of_time():
                    return
                b = by_id[bid]
                if not has_room(ctx, b):
                    log.info("watch: no room for %s this morning", b.id)
                    continue
                try:
                    jobs = read(ctx, http, b)
                except CheckTimeout as e:  # read() lets only the time budget through
                    log.info("watch: out of time at %s: %s", b.id, str(e)[:160])
                    return
                if jobs is not None:
                    judge(ctx, b, comps[b.company], jobs, stored_for(comps[b.company]))
    finally:
        http.close()


def run(cfg: Config, db: DB, gate, make_http, budget_end: float, healthy: set) -> list[dict]:
    listed = boards(cfg, db)
    if not listed:
        return []
    ctx = moves.Ctx(cfg, db, gate, make_http, budget_end, set(healthy))
    comps = {c.key: c for c in cfg.active}
    stored: dict[str, Stored] = {}

    def stored_for(c: Company) -> Stored:
        if c.key not in stored:
            stored[c.key] = Stored(cfg, db, c, ctx.now)
        return stored[c.key]

    read_boards(ctx, listed, comps, stored_for)
    return confirm(ctx, listed, comps, stored_for)


def status(cfg: Config, conn: sqlite3.Connection) -> str:
    """Each watched board and its last read, and what can't be read, for `internwatch liveness` (read-only)."""

    class Conn:
        @staticmethod
        def q(sql, *args):
            try:
                return conn.execute(sql, args).fetchall()
            except sqlite3.OperationalError:  # no alerts table before the first run
                return []

    kv = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM kv WHERE key LIKE 'blocked:at:watch%' "
                                                     "OR key LIKE 'blocked:unreadable:watch%'")}
    listed = boards(cfg, Conn)
    lines = [f"boards watched, never stored: {sum(b.every_days <= 1 for b in listed)} read every run, "
             f"{sum(b.every_days > 1 for b in listed)} weekly"]
    for b in listed:
        lines.append(f"  {b.id}: last read {kv.get(f'blocked:at:{b.check}:{b.id}') or 'never'}"
                     + (" (weekly)" if b.every_days > 1 else ""))
    cant = [f"{x['company']}/{x['board']}: {x['why']}" for x in moves.opts(cfg).get("watch_unreadable") or []]
    cant += [f"{k.split(':', 3)[3]}: {v}" for k, v in sorted(kv.items()) if k.startswith("blocked:unreadable:") and v]
    cant += [f"{company}/{system}: no checker for it" for (company, system), url in dismissed(cfg, Conn).items()
             if source_of(system, url) is None]
    lines.append(f"boards that can't be read: {len(cant)}")
    lines += [f"  {x}" for x in cant]
    return "\n".join(lines)
