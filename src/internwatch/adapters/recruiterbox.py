"""Recruiterbox (Trakstar Hire) careers widget, e.g. Wolfram.

settings:
  client_id: 42716
  job_url: https://www.wolfram.com/company/careers/opportunities/#op-{id}-{slug}   (the page that embeds the widget)
GET https://app.recruiterbox.com/widget/<client_id>/openings/ → [ {id, title, location{city,state,country},
    description, position_type, team, allows_remote} ]   (one response, no paging)
See discovery/notes/wolfram.md.
"""
from __future__ import annotations

import re

from ..models import Job
from .base import Checker, html_text, need, register


def sluggify(title: str) -> str:
    """The widget's own slug: lowercase, drop '-', whitespace runs → '-', keep [a-z0-9-]."""
    s = re.sub(r"\s+", "-", (title or "").lower().replace("-", ""))
    return re.sub(r"[^a-z0-9-]", "", s)


@register
class Recruiterbox(Checker):
    type = "recruiterbox"

    def describe(self, s):
        return f"https://app.recruiterbox.com/widget/{s['client_id']}/openings/"

    def fetch(self, http, s, ctx=None):
        data = http.get_json(self.describe(s))
        need(isinstance(data, list), f"recruiterbox:{s['client_id']}: expected a list, got {type(data).__name__}")
        jobs = []
        for o in data:
            need(isinstance(o, dict) and o.get("id") and "title" in o, f"recruiterbox:{s['client_id']}: opening without id/title")
            loc = o.get("location") or {}
            where = ", ".join(x for x in (loc.get("city"), loc.get("state"), loc.get("country")) if x)
            if o.get("allows_remote") and "remote" not in where.lower():
                where = f"{where}; Remote" if where else "Remote"
            title = (o.get("title") or "").strip()
            tmpl = s.get("job_url") or f"https://app.recruiterbox.com/widget/{s['client_id']}/openings/#op-{{id}}-{{slug}}"
            jobs.append(Job(id=str(o["id"]), title=title, location=where, url=tmpl.format(id=o["id"], slug=sluggify(title)),
                            snippet=html_text(o.get("description")), department=o.get("team") or "",
                            employment_type=o.get("position_type") or ""))
        return jobs
