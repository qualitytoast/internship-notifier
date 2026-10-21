"""Rippling ATS job boards (ats.rippling.com/<board>).

settings: board: rippling
List:   GET https://ats.rippling.com/api/v2/board/<board>/jobs?page=N&pageSize=1000
        → {"items": [{id, name, url, department{name}, locations[{name, city, state, country, workplaceType}]}],
           "totalItems": rows, "totalPages": N}   (one row per job × location: grouped by id)
Detail: GET https://ats.rippling.com/api/v2/board/<board>/jobs/<id>  → createdOn, description{role}, employmentType
See discovery/notes/rippling.md.
"""
from __future__ import annotations

from ..models import Job
from .base import Checker, check_total, html_text, iso_date, join_locations, need, need_list, register

API = "https://ats.rippling.com/api/v2/board/{board}/jobs"
PAGE = 1000


@register
class Rippling(Checker):
    type = "rippling"
    supports_detail = True

    def describe(self, s):
        return API.format(board=s["board"])

    def fetch(self, http, s, ctx=None):
        url = API.format(board=s["board"])
        where = f"rippling:{s['board']}"
        jobs: dict[str, Job] = {}
        rows, page, pages, total_rows = 0, 0, 1, None
        while page < pages:
            d = http.get_json(url, params={"page": page, "pageSize": PAGE})
            items = need_list(d, "items", where)
            if total_rows is None:
                total_rows, pages = d.get("totalItems"), int(d.get("totalPages") or 1)
            for it in items:
                need(it.get("id") and "name" in it, f"{where}: row without id/name")
                locs = []
                for loc in it.get("locations") or []:
                    name = loc.get("name") or ", ".join(x for x in (loc.get("city"), loc.get("state"), loc.get("country")) if x)
                    if loc.get("workplaceType") == "REMOTE" and "remote" not in name.lower():
                        name = f"Remote ({name})" if name else "Remote"
                    locs.append(name)
                j = jobs.get(it["id"])
                if j is None:
                    jobs[it["id"]] = Job(id=it["id"], title=(it.get("name") or "").strip(), location=join_locations(locs),
                                         url=it.get("url") or f"https://ats.rippling.com/{s['board']}/jobs/{it['id']}",
                                         department=(it.get("department") or {}).get("name", ""))
                else:
                    j.location = join_locations(j.location.split("; "), locs)
            rows += len(items)
            page += 1
            if not items:
                break
        check_total(rows, total_rows, where, tolerance=0 if page == 1 else None)
        return list(jobs.values())

    def detail(self, http, s, job):
        d = http.get_json(f"{API.format(board=s['board'])}/{job.id}")
        need(isinstance(d, dict), f"rippling: bad detail for {job.id}")
        job.snippet = html_text((d.get("description") or {}).get("role")) or job.snippet
        job.posted = iso_date(d.get("createdOn")) or job.posted
        et = d.get("employmentType") or {}
        job.employment_type = et.get("id") or et.get("label") or job.employment_type
        return job
