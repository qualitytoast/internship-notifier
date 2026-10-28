"""Greenhouse job board API (https://developers.greenhouse.io/job-board.html).

settings: board: <token>            e.g. stripe  (or boards: [a, b] for companies with several boards)
          dedupe_requisitions: true the same requisition posted on several boards is reported once (C3 AI), when
                                    the title and place match too ("Redwood City, CA" = "Redwood City, California,
                                    United States"); a twin with another title or place (a new term, a copy in
                                    Mexico) is kept
          dedupe_requisitions: across_boards   the same, but only a twin of a posting on an earlier board is dropped;
                                    every posting of the first board is kept as it was (Duolingo's university board)
          missing_ok: true          a board that answers 404 counts as empty (a company that switched its board
                                    off for now; the zero-jobs health check still flags a working board going to 0).
                                    A board that answered before and now answers 404 marks the poll degraded.
List:   GET https://boards-api.greenhouse.io/v1/boards/<board>/jobs        → {"jobs": [...], "meta": {"total": N}}
Detail: GET https://boards-api.greenhouse.io/v1/boards/<board>/jobs/<id>   → adds content, departments, offices
With several boards, one that fails marks the poll degraded and the others are still read; all failing fails.
"""
from __future__ import annotations

import re

from ..locations import countries
from ..models import CheckerError, Job
from .base import Checker, check_total, degrade, html_text, iso_date, need, need_list, register

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


def _alnum(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _place(location: str) -> tuple:
    """Where a posting is, however the board spells it: its cities (the first part of each location) and countries."""
    return frozenset(_alnum(p.split(",")[0]) for p in location.split(";")), countries(location)[0]


# metadata fields that can say a posting is an internship ("Worker Sub Type: Intern", "Job Level: Intern", …)
TYPE_FIELDS = ("employment type", "employee type", "job type", "worker type", "position type", "time type", "req type",
               "worker sub", "job level", "job profile", "career page", "careersite", "careers page", "job family")


def _employment_type(meta) -> str:
    """The values of every matching field, not just the first: Datadog's "Time Type" says "Full time" while its
    "Early Career Time Type" says "Internship"."""
    vals: list[str] = []
    for m in meta or []:
        name = str(m.get("name", "")).lower()
        if any(k in name for k in TYPE_FIELDS):
            v = m.get("value")
            for x in v if isinstance(v, list) else [v]:
                x = str(x or "").strip()
                if x and x not in vals:
                    vals.append(x)
    return ", ".join(vals)


@register
class Greenhouse(Checker):
    type = "greenhouse"
    supports_detail = True

    def boards(self, s: dict) -> list[str]:
        return list(s.get("boards") or [s["board"]])

    def describe(self, s):
        return ", ".join(API.format(board=b) for b in self.boards(s))

    def fetch(self, http, s, ctx=None):
        jobs: list[Job] = []
        reqs: set[tuple] = set()
        # boards that answered before (kept between polls): a 404 from one of them is news, not a board switched off
        answered = set(ctx.state.get("boards_ok") or []) if ctx is not None else set()
        errors: list[CheckerError] = []
        read = 0
        for board in self.boards(s):
            try:
                resp = http.get(API.format(board=board), ok_statuses=(404,) if s.get("missing_ok") else ())
                if resp.status == 404:
                    if board in answered:
                        degrade(ctx, f"greenhouse:{board} answered 404 (it answered before)")
                    continue
                got = self._board(board, resp.json())
            except CheckerError as e:
                if ctx is None:
                    raise
                errors.append(e)  # the other boards are still read
                continue
            read += 1
            answered.add(board)
            across = s.get("dedupe_requisitions") == "across_boards"
            this_board: set[tuple] = set()
            for j in got:
                req = j.extra["alt_ids"][0] if j.extra["alt_ids"] else ""
                if s.get("dedupe_requisitions") and req:
                    key = (req, _alnum(j.title), _place(j.location))
                    if key in reqs:
                        continue
                    (this_board if across else reqs).add(key)
                jobs.append(j)
            reqs |= this_board
        if errors and not read:
            raise errors[0]
        if ctx is not None and s.get("missing_ok"):
            ctx.state["boards_ok"] = sorted(answered)
        if errors:
            degrade(ctx, "; ".join(str(e) for e in errors))
        return jobs

    def _board(self, board: str, data) -> list[Job]:
        items = need_list(data, "jobs", f"greenhouse:{board}")
        jobs = []
        for j in items:
            need(j.get("id") and "title" in j, f"greenhouse:{board}: job without id/title")
            req = str(j.get("requisition_id") or "")
            jobs.append(Job(
                id=str(j["id"]),
                title=j.get("title") or "",
                location=(j.get("location") or {}).get("name", ""),
                url=j.get("absolute_url") or f"https://job-boards.greenhouse.io/{board}/jobs/{j['id']}",
                posted=iso_date(j.get("first_published") or j.get("updated_at")),
                employment_type=_employment_type(j.get("metadata")),
                extra={"board": board, "alt_ids": [req] if req else []},
            ))
        check_total(len(items), (data.get("meta") or {}).get("total"), f"greenhouse:{board}", tolerance=0)
        return jobs

    def detail(self, http, s, job):
        board = job.extra.get("board") or self.boards(s)[0]
        d = http.get_json(f"{API.format(board=board)}/{job.id}")
        need(isinstance(d, dict) and "title" in d, f"greenhouse:{board}: bad detail for {job.id}")
        job.snippet = html_text(d.get("content"))
        depts = [x.get("name", "") for x in d.get("departments") or [] if x.get("name")]
        if depts:
            job.department = " / ".join(depts)
        offices = [o.get("location") or o.get("name") for o in d.get("offices") or []]
        if offices and (not job.location or job.location.lower() in ("remote", "multiple locations")):
            job.location = "; ".join(x for x in offices if x)
        return job
