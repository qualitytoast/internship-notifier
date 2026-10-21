"""Pinpoint ATS public postings feed.

settings: subdomain: <name>   e.g. wolve  (→ https://wolve.pinpointhq.com)
          host: careers.wolve.com   the company's own Pinpoint domain, when *.pinpointhq.com is robots-disallowed
GET https://<host>/postings.json → {"data": [{id, title, url, location{…}, employment_type, job{department}, …}]}
"""
from __future__ import annotations

from ..models import Job
from .base import Checker, html_text, iso_date, need, need_list, register


@register
class Pinpoint(Checker):
    type = "pinpoint"

    def describe(self, s):
        return f"https://{s.get('host') or s['subdomain'] + '.pinpointhq.com'}/postings.json"

    def fetch(self, http, s, ctx=None):
        data = http.get_json(self.describe(s))
        items = need_list(data, "data", f"pinpoint:{s['subdomain']}")
        jobs = []
        for p in items:
            need(p.get("id") and "title" in p, f"pinpoint:{s['subdomain']}: posting without id/title")
            loc = p.get("location") or {}
            if isinstance(loc, dict):
                loc = ", ".join(x for x in (loc.get("city"), loc.get("province"), loc.get("name")) if x) or loc.get("name", "")
            dept = p.get("department") or (p.get("job") or {}).get("department") or {}
            jobs.append(Job(
                id=str(p["id"]),
                title=p.get("title") or "",
                location=str(loc or ""),
                url=p.get("url") or "",
                posted=iso_date(p.get("created_at") or p.get("published_at")),
                snippet=html_text(" ".join(str(p.get(k) or "") for k in ("description", "key_responsibilities", "skills_knowledge_expertise"))),
                department=dept.get("name", "") if isinstance(dept, dict) else str(dept),
                employment_type=str(p.get("employment_type_text") or p.get("employment_type") or ""),
            ))
        return jobs
