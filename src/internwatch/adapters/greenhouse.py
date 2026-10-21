"""Greenhouse job board API (https://developers.greenhouse.io/job-board.html).

settings: board: <token>            e.g. stripe  (or boards: [a, b] for companies with several boards)
          dedupe_requisitions: true the same requisition posted on several boards is reported once (C3 AI)
          missing_ok: true          a board that answers 404 counts as empty (a company that switched its board
                                    off for now; the zero-jobs health check still flags a working board going to 0)
List:   GET https://boards-api.greenhouse.io/v1/boards/<board>/jobs        → {"jobs": [...], "meta": {"total": N}}
Detail: GET https://boards-api.greenhouse.io/v1/boards/<board>/jobs/<id>   → adds content, departments, offices
"""
from __future__ import annotations

from ..models import Job
from .base import Checker, check_total, html_text, iso_date, need, need_list, register

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


def _employment_type(meta) -> str:
    for m in meta or []:
        name = str(m.get("name", "")).lower()
        if any(k in name for k in ("employment type", "employee type", "job type", "worker type", "position type",
                                   "time type", "req type")):
            v = m.get("value")
            return ", ".join(v) if isinstance(v, list) else str(v or "")
    return ""


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
        reqs: set[str] = set()
        for board in self.boards(s):
            resp = http.get(API.format(board=board), ok_statuses=(404,) if s.get("missing_ok") else ())
            if resp.status == 404:
                continue
            data = resp.json()
            items = need_list(data, "jobs", f"greenhouse:{board}")
            for j in items:
                need(j.get("id") and "title" in j, f"greenhouse:{board}: job without id/title")
                req = str(j.get("requisition_id") or "")
                if s.get("dedupe_requisitions") and req:
                    if req in reqs:
                        continue
                    reqs.add(req)
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
