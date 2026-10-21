"""Common interface for every checker (shared hiring-system adapters and custom checkers).

A checker turns its `settings` (from companies.yaml) into a list of normalized `Job`s:

    class MyChecker(Checker):
        type = "my-system"
        def fetch(self, http, s) -> list[Job]: ...

Rules every checker follows:
* fetch ALL jobs on the site (filters are applied later by internwatch.filters)
* raise ShapeError when a response does not have the expected structure
* when the source reports a total, call `check_total` so a pagination bug can never hide jobs
* optional `detail()` fills in the description/location for one job (used only for new
  student roles, so it costs a handful of requests per run)
"""
from __future__ import annotations

import html as htmlmod
import re
from datetime import date, datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Iterable

from ..http import Http
from ..models import Job, NotModified, ShapeError

REGISTRY: dict[str, type["Checker"]] = {}


@dataclass
class FetchContext:
    """How much of a site to read, plus a little memory kept between polls.

    mode "full":  enumerate every job (normal case).
    mode "quick": for very large sites whose feed is sorted newest-first, read pages only until a page
                  contains nothing new (`known` holds the ids already in the database). The runner still
                  does a full scan every `full_scan_hours`, and only full scans can mark jobs as removed.
    state:          small JSON-able dict saved per company after a successful poll (ETag, Last-Modified, tokens)
    reported_total: the job total the source itself reports; set it in quick mode so health checks can
                    still compare counts
    degraded:       set by a checker that had to use its fallback source: the jobs it returns are still
                    processed (new postings are emailed) but the poll is reported as a health problem
    """

    mode: str = "full"
    known: frozenset = frozenset()
    state: dict = field(default_factory=dict)
    reported_total: int | None = None
    degraded: str | None = None
    _old_streak: dict = field(default_factory=dict, repr=False)

    @property
    def quick(self) -> bool:
        return self.mode == "quick"

    def page_is_old(self, ids: list[str], key: str = "") -> bool:
        """Quick scans stop after TWO pages in a row of already-known jobs (per listing `key`): newest-first sorts
        wobble (same-day timestamps, re-dated postings), and one extra page is cheap insurance."""
        if not self.quick or not ids:
            return False
        old = all(i in self.known for i in ids)
        self._old_streak[key] = self._old_streak.get(key, 0) + 1 if old else 0
        return self._old_streak[key] >= 2


def conditional_get(http: Http, url: str, ctx: FetchContext | None, *, headers: dict | None = None, **kw):
    """GET with If-None-Match / If-Modified-Since from the previous poll; raises NotModified on 304.

    Validators are only sent when the database already holds this company's jobs (ctx.known), so a
    304 can never leave the runner without a job list.
    """
    h = dict(headers or {})
    memo = (ctx.state.get("validators") or {}).get(url, {}) if ctx is not None else {}
    if ctx is not None and ctx.known and memo:
        if memo.get("etag"):
            h["If-None-Match"] = memo["etag"]
        if memo.get("last_modified"):
            h["If-Modified-Since"] = memo["last_modified"]
    resp = http.get(url, headers=h, ok_statuses=(304,), **kw)
    if resp.status == 304:
        raise NotModified(url)
    if ctx is not None:
        new = {k: v for k, v in (("etag", resp.headers.get("etag")),
                                 ("last_modified", resp.headers.get("last-modified"))) if v}
        ctx.state.setdefault("validators", {})[url] = new
    return resp


def register(cls: type["Checker"]) -> type["Checker"]:
    if not cls.type:
        raise ValueError(f"{cls.__name__} has no type")
    REGISTRY[cls.type] = cls
    return cls


class Checker:
    type: str = ""
    supports_detail: bool = False
    supports_quick: bool = False   # can stop early on newest-first feeds (see FetchContext)

    def fetch(self, http: Http, s: dict, ctx: FetchContext | None = None) -> list[Job]:
        raise NotImplementedError

    def detail(self, http: Http, s: dict, job: Job) -> Job:
        return job

    def describe(self, s: dict) -> str:
        """Short human description of the feed (for COVERAGE.md and `check`)."""
        return self.type


# ---------------------------------------------------------------------------------------------
# helpers shared by checkers

# Freshman/sophomore words for checkers that can only read a site's student slice through its search
# (Amazon, Apple), in the order of role.underclassmen in config/filters.yaml. They must cover every phrase there
# (a test checks): a "*" phrase by its stem and plural, since Amazon's index does not stem. Most match no job;
# the broadest match ~200 (Amazon, in descriptions).
UNDERCLASS_SEARCH_WORDS = ["freshman", "freshmen", "sophomore", "sophomores", "underclassman", "underclassmen",
                           "first year", "first years", "second year", "second years", "1st year", "2nd year",
                           "rising sophomore", "rising sophomores", "rising junior", "rising juniors",
                           "early insight", "early insights", "insight program", "insight programs", "insight day",
                           "insight days", "insight week", "insight weeks", "insight event", "insight events",
                           "insight series", "discovery program", "discovery programs", "discovery day",
                           "discovery days", "discovery event", "discovery events", "discovery summit",
                           "discovery summits", "discovery series", "exploration program", "exploration programs",
                           "explore program", "explore programs", "career prep", "pre-internship", "pre-internships",
                           "possibilities series", "possibilities summit", "possibilities summits",
                           "early identification", "early id", "winternship", "winternships"]


def need(cond, message: str) -> None:
    if not cond:
        raise ShapeError(message)


def need_list(obj, key: str, where: str) -> list:
    need(isinstance(obj, dict), f"{where}: expected an object, got {type(obj).__name__}")
    val = obj.get(key)
    need(isinstance(val, list), f"{where}: '{key}' missing or not a list (keys: {list(obj)[:12]})")
    return val


_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_RE = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr|section)[^>]*>", re.I)


def html_text(s: str | None, limit: int = 4000) -> str:
    """HTML (possibly entity-escaped HTML) → plain text."""
    if not s:
        return ""
    s = htmlmod.unescape(s) if "&lt;" in s else s
    s = _BLOCK_RE.sub(" \n", s)
    s = _TAG_RE.sub(" ", s)
    s = htmlmod.unescape(s)
    return re.sub(r"\s+", " ", s).strip()[:limit]


def iso_date(value) -> str | None:
    """Best-effort conversion of timestamps / date strings to YYYY-MM-DD."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1e12:  # milliseconds
                ts /= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        s = str(value).strip()
        m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
        if m:
            return m.group(1)
        for fmt in ("%m/%d/%Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y", "%d-%b-%Y"):
            try:
                return datetime.strptime(s, fmt).date().isoformat()
            except ValueError:
                pass
    except (ValueError, OverflowError, OSError):
        return None
    return None


def relative_posted(text: str | None, today: date | None = None) -> str | None:
    """'Posted Today' / 'Posted 3 Days Ago' / 'Posted 30+ Days Ago' → YYYY-MM-DD (None if unknown)."""
    if not text:
        return None
    today = today or datetime.now(timezone.utc).date()
    t = text.lower()
    if "today" in t:
        return today.isoformat()
    if "yesterday" in t:
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\+?\s*days?", t)
    if m and "+" not in t:
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    return None


def dedupe(jobs: Iterable[Job]) -> list[Job]:
    seen: dict[str, Job] = {}
    for j in jobs:
        if j.id and j.id not in seen:
            seen[j.id] = j
    return list(seen.values())


def check_total(got: int, total, where: str, tolerance: int | None = None) -> None:
    """The source said there are `total` jobs; make sure pagination really collected them.

    Default tolerance: 1.5% (at least 2). Paging through a big live site takes minutes, and postings that
    close meanwhile shift later pages, so a few jobs can slip past one walk (they are still there on the next).
    Real pagination bugs (a cap, a stuck cursor) lose far more than that. Single-response feeds pass 0.
    """
    if not isinstance(total, int):
        return
    if tolerance is None:
        tolerance = max(2, int(total * 0.015))
    if got + tolerance < total:
        raise ShapeError(f"{where}: collected {got} jobs but the source reports {total} (pagination incomplete)")


def join_locations(*parts) -> str:
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        if isinstance(p, (list, tuple)):
            for x in p:
                if x and str(x).strip() and str(x).strip() not in out:
                    out.append(str(x).strip())
        elif str(p).strip() and str(p).strip() not in out:
            out.append(str(p).strip())
    return "; ".join(out)


def degrade(ctx: FetchContext | None, message: str) -> None:
    """Part of the feed failed (or could not be verified), but what was read is good: the poll's jobs are still
    processed and new ones emailed, while the poll is reported as a health problem and records no removals
    (FetchContext.degraded). Several problems in one poll are joined. Without a context it does nothing."""
    if ctx is not None:
        ctx.degraded = (f"{ctx.degraded}; {message}" if ctx.degraded else message)[:900]


def need_soft(cond, message: str, ctx: FetchContext | None) -> bool:
    """`need` for a problem that leaves the jobs already read intact: with a context the poll is marked degraded and
    keeps its jobs; without one it raises ShapeError as before. Returns whether `cond` held."""
    if not cond:
        if ctx is None:
            raise ShapeError(message)
        degrade(ctx, message)
    return bool(cond)


def check_total_soft(got: int, total, where: str, ctx: FetchContext | None, tolerance: int | None = None) -> None:
    """`check_total` that keeps the jobs read: a shortfall marks the poll degraded (raises without a context)."""
    try:
        check_total(got, total, where, tolerance)
    except ShapeError as e:
        if ctx is None:
            raise
        degrade(ctx, str(e))
