"""Several sources for one company (e.g. Palo Alto Networks: Workday + the student roles it posts on RippleMatch).

settings:
  sources:
    - {checker: workday, settings: {host: …, tenant: …, site: …}}
    - {checker: ripplematch, settings: {company_id: 676}}
  dedupe: true   a later source's job is dropped when its id or requisition id (alt_ids) was already seen
                 (Autodesk: the same requisitions on Eightfold and Workday)
  dedupe_titles: true   ... or when its title matches an earlier source's job apart from text in brackets,
                 case and punctuation (Rockwell: "Co-Op, Delivery - Projects" on RippleMatch is Workday's
                 "Co-op, Delivery - Projects (LCS)"); terms outside brackets still count
Ids from the first source are kept as they are; later sources' ids are prefixed with "<checker>:" so they can
never collide. If one source fails, the others are still read and their new postings emailed, and the check
is reported as degraded (a health alert after repeated failures); if every source fails, the check fails.
"""
from __future__ import annotations

import re

from ..adapters import get_checker
from ..adapters.base import Checker, need, register
from ..models import CheckerError


def _bare_title(title: str) -> str:
    """The title without text in brackets, case or punctuation: "Co-op, Delivery - Projects (LCS)" →
    "co op delivery projects"."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", title.lower())).split())


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
        sources = self._sources(s)
        # sources that answered before; None on the company's very first check (everything is a baseline then)
        prev = set(ctx.state.get("ok_sources", [])) if ctx is not None and "ok_sources" in ctx.state else None
        ok_now: set[int] = set()
        for i, checker, st in sources:
            try:
                got = checker.fetch(http, st, ctx)
            except CheckerError as e:
                errors.append(f"{checker.type}: {e}")
                if len(errors) == len(sources):
                    raise
                continue
            ok_now.add(i)
            if prev is not None and i not in prev:
                for j in got:  # first answer from a source that was failing: existing postings, not new ones
                    j.extra["baseline"] = True
            if ctx is not None and ctx.reported_total is not None:
                total += ctx.reported_total
                ctx.reported_total = None
            for j in got:
                keys = {j.id, *map(str, j.extra.get("alt_ids") or [])}
                if i and s.get("dedupe") and keys & seen:
                    continue
                bare = _bare_title(j.title)
                if i and s.get("dedupe_titles") and bare in titles:
                    continue
                seen |= keys
                titles.add(bare)
                if i:
                    j.id = f"{checker.type}:{j.id}"
                j.extra["source"] = i
                jobs.append(j)
        if ctx is not None:
            ctx.state["ok_sources"] = sorted((prev or set()) | ok_now)
            if total:
                ctx.reported_total = total
            if errors:
                ctx.degraded = "; ".join(errors)[:900]
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
            checker.detail(http, st, job)
        finally:
            job.id = raw_id
        return job
