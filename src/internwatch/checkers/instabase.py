"""Instabase: its Greenhouse board, plus a look at its careers page to notice a move to another job site.

settings: board: instabase      the Greenhouse board, read by the shared greenhouse adapter (missing_ok: true, so
          missing_ok: true      its 404 counts as no jobs)
          page: <url>           the careers page, whose own script loads its job list from that board
The board has answered 404 since October 2026 (switched off; the page shows "No jobs available"), so on its own a
move to another job site would look like "still no jobs". Each check therefore also reads the page and lists the
job sites it points at (detect.from_text, as `internwatch add` does). Anything besides this board, no mention of it,
or a page that can't be read marks the poll degraded: a health alert after two checks in a row. The page's leftover
Webflow cards link old postings on the same board, so they are not a change. See discovery/notes/instabase.md.
"""
from __future__ import annotations

from ..adapters import get_checker
from ..adapters.base import Checker, need_soft, register
from ..models import CheckerError


def _name(checker: str, settings: dict) -> str:
    return " ".join([checker, *(str(v) for v in settings.values())])


@register
class Instabase(Checker):
    type = "instabase"
    supports_detail = True

    def describe(self, s):
        return f"{get_checker('greenhouse').describe(s)} + {s['page']} (still loads that board?)"

    def fetch(self, http, s, ctx=None):
        jobs = get_checker("greenhouse").fetch(http, s, ctx)
        change = self.page_change(http, s)
        need_soft(not change, f"instabase: {change}", ctx)
        return jobs

    def page_change(self, http, s) -> str:
        """What on the careers page no longer fits the board that is read ('' when nothing does)."""
        from ..detect import from_text  # imported here: detect imports the runner, which imports this registry
        try:
            text = http.get_text(s["page"])
        except CheckerError as e:
            return f"the careers page could not be read to see where its jobs come from ({e})"
        board = ("greenhouse", {"board": s["board"]})
        seen = [(c.checker, c.settings) for c in from_text(text, s["page"])]
        others = [_name(*x) for x in seen if x != board]
        if others:
            return (f"the careers page now points at {', '.join(others)}, but InternWatch reads {_name(*board)}: "
                    "its jobs may have moved")
        if board not in seen:
            return f"the careers page no longer mentions {_name(*board)}: its jobs may have moved"
        return ""

    def detail(self, http, s, job):
        return get_checker("greenhouse").detail(http, s, job)
