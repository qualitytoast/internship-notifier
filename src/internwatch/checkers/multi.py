"""Several sources for one company (e.g. Palo Alto Networks: Workday + the student roles it posts on RippleMatch).

settings:
  sources:
    - {checker: workday, settings: {host: …, tenant: …, site: …}}
    - {checker: ripplematch, settings: {company_id: 676}}
  dedupe: true   a later source's job is dropped when its id or requisition id (alt_ids) was already seen
                 (Autodesk: the same requisitions on Eightfold and Workday)
  dedupe_titles: true   ... or when its title matches an earlier source's job apart from case and punctuation;
                 text in brackets counts, since it can name another place or term (Rockwell: RippleMatch's
                 "Technical Sales Specialist" is the US role, not Workday's "Technical Sales Specialist (Canada)")
  twin_ids: true   a dropped job's id and requisition ids are kept with the job that stays (its alt_ids), so a
                 Simplify row or list that links the dropped copy still finds it (DriveWealth: the same internships
                 on Greenhouse and on Ashby, where Simplify titles them differently); the liveness rules count the
                 job on the dropped copy's board too, so a board that only repeats another's isn't empty or quiet
Ids from the first source are kept as they are; later sources' ids are prefixed with "<checker>:" so they can
never collide. If one source fails, the others are still read and their new postings emailed, and the check
is reported as degraded (a health alert after repeated failures); if every source fails, the check fails.
A source's first answer (it was failing since the company was first read, or it was just added) is its baseline:
those postings go out once in the next email's "already open" section, not as new.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from contextlib import contextmanager

from ..adapters import get_checker
from ..adapters.base import Checker, degrade, need, register
from ..models import CheckerError, NotModified

log = logging.getLogger(__name__)


def _bare_title(title: str) -> str:
    """The title's words and brackets, without case or other punctuation: "Co-op, Delivery - Projects (LCS)" →
    "co op delivery projects ( lcs )". The brackets stay so that "Co-op (LCS)" still differs from "Co-op LCS", as
    it did when bracketed text was ignored (until October 2026): no posting kept then is dropped now."""
    return " ".join(re.findall(r"[a-z0-9]+|[()\[\]]", title.lower()))


def _source_ids(sources) -> list[str]:
    """Each source's name in the saved state: its checker and settings, so inserting or reordering sources in
    companies.yaml can't make one source look like another (identical sources get #2, #3…)."""
    out, seen = [], {}
    for _, checker, st in sources:
        sid = f"{checker.type}:{hashlib.sha1(json.dumps(st, sort_keys=True, default=str).encode()).hexdigest()[:10]}"
        seen[sid] = seen.get(sid, 0) + 1
        out.append(sid if seen[sid] == 1 else f"{sid}#{seen[sid]}")
    return out


def _twin(kept, dropped, i: int) -> None:
    """twin_ids: the dropped copy's ids, kept with the job that stays (DB.upsert_jobs adds them to its alt_ids), and
    the board it was on (the liveness rules count the job there too)."""
    have = {kept.id, *map(str, kept.extra.get("alt_ids") or []), *kept.extra.get("twin_ids", [])}
    for x in [dropped.id, *map(str, dropped.extra.get("alt_ids") or [])]:
        if x not in have:
            kept.extra.setdefault("twin_ids", []).append(x)
            have.add(x)
    where = {"source": i, **{k: dropped.extra[k] for k in ("board", "site", "list") if k in dropped.extra}}
    own = {"source": kept.extra.get("source", 0), **{k: kept.extra[k] for k in ("board", "site", "list") if k in kept.extra}}
    if where != own and where not in kept.extra.get("twin_boards", []):
        kept.extra.setdefault("twin_boards", []).append(where)


@contextmanager
def _pacing(http, st: dict):
    """A source's own min_interval (Autodesk's Eightfold site asks for 2.5 s) while that source is read."""
    old = getattr(http, "min_interval", None)
    if http is not None and st.get("min_interval"):
        http.min_interval = max(float(st["min_interval"]), old or 0.0)
    try:
        yield
    finally:
        if http is not None:
            http.min_interval = old

@register
class Multi(Checker):
    type = "multi"
    supports_detail = True

    def _sources(self, s):
        src = s.get("sources") or []
        need(src, "multi: no sources configured")
        return [(i, get_checker(x["checker"]), x.get("settings") or {}) for i, x in enumerate(src)]

    def describe(self, s):
        return " + ".join(f"{c.type}: {c.describe(st)}" for _, c, st in self._sources(s))

    def fetch(self, http, s, ctx=None):
        jobs, total, seen, titles, errors = [], 0, set(), set(), []
        by_key, by_title = {}, {}  # twin_ids: the kept job each id and title belongs to
        sources = self._sources(s)
        ids = _source_ids(sources)
        # sources that answered before; None on the company's very first check (everything is a baseline then)
        prev = None
        if ctx is not None and "ok_source_ids" in ctx.state:
            prev = set(ctx.state["ok_source_ids"])
        elif ctx is not None and "ok_sources" in ctx.state:  # saved by list position before October 2026
            prev = {ids[i] for i in ctx.state["ok_sources"] if isinstance(i, int) and i < len(ids)}
        ok_now: set[str] = set()
        for i, checker, st in sources:
            was_partial = ctx is not None and ctx.partial
            if ctx is not None:
                ctx.partial = False  # this source's own flag
            try:
                with _pacing(http, st):
                    got = checker.fetch(http, st, ctx)
            except NotModified:
                raise  # unchanged: the runner keeps the stored list, as before
            except Exception as e:  # noqa: BLE001 — one source failing or crashing must not hide the others
                if not isinstance(e, CheckerError):
                    log.warning("multi: source %s crashed", checker.type, exc_info=True)
                errors.append(f"{checker.type}: {e}" if isinstance(e, CheckerError)
                              else f"{checker.type}: crashed: {type(e).__name__}: {e}")
                if ctx is not None:
                    ctx.reported_total = None  # a total from the failed source must not count for the next one
                    ctx.partial = was_partial
                if len(errors) == len(sources):
                    raise
                continue
            partial = ctx is not None and ctx.partial
            if ctx is not None:
                ctx.partial = was_partial or partial
            if not (partial and prev is not None and ids[i] not in prev):
                ok_now.add(ids[i])  # a cut-short first answer is not the source's baseline yet: the rest comes later
            if prev is not None and ids[i] not in prev:
                for j in got:  # this source's first answer: what it lists was open before (shown once, not as new)
                    j.extra["baseline"] = True
            if ctx is not None and ctx.reported_total is not None:
                total += ctx.reported_total
                ctx.reported_total = None
            for j in got:
                keys = {j.id, *map(str, j.extra.get("alt_ids") or [])}
                if i and s.get("dedupe") and keys & seen:
                    if s.get("twin_ids"):
                        _twin(by_key[min(keys & seen)], j, i)
                    continue
                bare = _bare_title(j.title)
                if i and s.get("dedupe_titles") and bare in titles:
                    if s.get("twin_ids"):
                        _twin(by_title[bare], j, i)
                    continue
                seen |= keys
                titles.add(bare)
                if s.get("twin_ids"):
                    by_key.update(dict.fromkeys(keys, j))
                    by_title.setdefault(bare, j)
                if i:
                    j.id = f"{checker.type}:{j.id}"
                j.extra["source"] = i
                jobs.append(j)
        if ctx is not None:
            ctx.state.pop("ok_sources", None)
            ctx.state["ok_source_ids"] = sorted((prev or set()) | ok_now)
            if total:
                ctx.reported_total = total
            if errors:
                degrade(ctx, "; ".join(errors))
        elif errors:
            raise CheckerError("; ".join(errors))
        return jobs

    def detail(self, http, s, job):
        i = int(job.extra.get("source", 0))
        _, checker, st = self._sources(s)[i]
        if not checker.supports_detail:
            return job
        prefix = f"{checker.type}:" if i else ""
        raw_id, job.id = job.id, job.id[len(prefix):]
        try:
            with _pacing(http, st):
                checker.detail(http, st, job)
        finally:
            job.id = raw_id
        return job
