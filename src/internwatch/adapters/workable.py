"""Workable hosted careers page API (apply.workable.com).

settings: account: <subdomain>   e.g. huggingface
List:   POST https://apply.workable.com/api/v3/accounts/<account>/jobs  {"query":"", …, "token": <nextPage>}
        → {"total": N, "results": [...], "nextPage": "..."}
Detail: GET  https://apply.workable.com/api/v2/accounts/<account>/jobs/<shortcode>
"""
from __future__ import annotations

from ..models import Job
from .base import Checker, check_total, html_text, iso_date, join_locations, need, need_list, register


def _loc(loc: dict | None) -> str:
    if not loc:
        return ""
    return ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)


@register
class Workable(Checker):
    type = "workable"
    supports_detail = True

    def describe(self, s):
        return f"https://apply.workable.com/api/v3/accounts/{s['account']}/jobs"

    def fetch(self, http, s, ctx=None):
        acct = s["account"]
        url = f"https://apply.workable.com/api/v3/accounts/{acct}/jobs"
        body = {"query": "", "department": [], "location": [], "workplace": [], "worktype": []}
        jobs, total, pages = [], None, 0
        while True:
            data = http.post_json(url, json=body)
            items = need_list(data, "results", f"workable:{acct}")
            total = data.get("total") if total is None else total
            for j in items:
                need(j.get("shortcode") and "title" in j, f"workable:{acct}: job without shortcode/title")
                locs = [_loc(x) for x in j.get("locations") or []] or [_loc(j.get("location"))]
                if j.get("remote") or j.get("workplace") == "remote":
                    locs.append("Remote")
                jobs.append(Job(
                    id=j["shortcode"],
                    title=j.get("title") or "",
                    location=join_locations(locs),
                    url=f"https://apply.workable.com/{acct}/j/{j['shortcode']}/",
                    posted=iso_date(j.get("published")),
                    department=", ".join(j.get("department") or []),
                    employment_type=j.get("type") or "",
                ))
            pages += 1
            nxt = data.get("nextPage")
            if not nxt or not items or pages > 50:
                break
            body = {**body, "token": nxt}
        check_total(len(jobs), total, f"workable:{acct}")
        return jobs

    def detail(self, http, s, job):
        d = http.get_json(f"https://apply.workable.com/api/v2/accounts/{s['account']}/jobs/{job.id}")
        need(isinstance(d, dict), f"workable: bad detail for {job.id}")
        job.snippet = html_text(" ".join(str(d.get(k) or "") for k in ("description", "requirements")))
        return job
