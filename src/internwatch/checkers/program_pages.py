"""Program pages that say when applications open (Goldman Sachs' Possibilities and Emerging Leaders Series).

Some student programs are never posted as jobs: their page says "Applications are now closed" until the next round
opens, and applications go through a form InternWatch can't read. Each page is read, and the program is returned as
a job only while its application text no longer says closed.

settings: pages: [{url, title, location}]
          section: [APPLICATION DETAILS, ELIGIBILITY]  the headings around the application text
          cycle: [ELIGIBILITY, LOCATION]               text that changes each round (graduation years): it names one
                                                       opening, so a new round is a new job and an edited deadline is not
          closed: applications are now closed
A page that can't be read, or that no longer has the application heading, marks the poll degraded (both pages
failing fails it): a page that changed must not look like "still closed".
"""
from __future__ import annotations

import hashlib
import re

from ..adapters.base import Checker, degrade, html_text, need, register
from ..models import CheckerError, Job, ShapeError

_SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)


def _between(text: str, start: str, end: str, after: int = 0) -> tuple[str, int] | None:
    low = text.lower()
    i = low.find(start.lower(), after)
    if i < 0:
        return None
    i += len(start)
    j = low.find(end.lower(), i)
    return (text[i:j if j >= 0 else len(text)].strip(), i)


@register
class ProgramPages(Checker):
    type = "program_pages"

    def describe(self, s):
        return " + ".join(p["url"] for p in s.get("pages") or [])

    def fetch(self, http, s, ctx=None):
        pages = s.get("pages") or []
        need(pages, "program_pages: no pages configured")
        start, end = s.get("section") or ["APPLICATION DETAILS", "ELIGIBILITY"]
        cyc_start, cyc_end = s.get("cycle") or ["ELIGIBILITY", "LOCATION"]
        closed = (s.get("closed") or "applications are now closed").lower()
        jobs, errors = [], []
        for p in pages:
            try:
                text = html_text(_SCRIPT.sub(" ", http.get_text(p["url"], headers={"Accept": "text/html"})), limit=10**7)
                section = _between(text, start, end)
                if section is None:
                    raise ShapeError(f"program_pages: no '{start}' on {p['url']}")
            except CheckerError as e:
                if ctx is None:
                    raise
                errors.append(e)
                continue
            application, at = section
            if closed in application.lower():
                continue
            cycle = (_between(text, cyc_start, cyc_end, at) or (application, 0))[0]
            slug = p["url"].rstrip("/").rsplit("/", 1)[-1]
            jobs.append(Job(
                id=f"{slug}:{hashlib.sha1(cycle.encode()).hexdigest()[:10]}",
                title=f"{p['title']} (applications open)",
                location=p.get("location") or "",
                url=p["url"],
                snippet=f"{application} Eligibility: {cycle}"[:4000],
                employment_type="Program",
            ))
        if errors and len(errors) == len(pages):
            raise errors[0]
        if errors:
            degrade(ctx, "; ".join(str(e) for e in errors))
        return jobs
