"""Atlassian: the listings endpoint behind atlassian.com/company/careers (all 6 iCIMS portals merged).

GET https://www.atlassian.com/endpoint/careers/listings  (≈500 KB gzipped, ETag → 304 when unchanged)
→ [ {id, title, locations[], category, type, overview, responsibilities, qualifications, applyUrl,
     portalJobPost: {portalUrl, updatedDate}} ]   (rows can repeat: de-duplicated by id)
Interns are category "Interns" (no employment type is given). The careers page renders a CMS copy that lags
this feed by a few jobs. See discovery/notes/atlassian.md.
"""
from __future__ import annotations

from ..adapters.base import Checker, conditional_get, html_text, need, register
from ..models import Job

FEED = "https://www.atlassian.com/endpoint/careers/listings"


@register
class Atlassian(Checker):
    type = "atlassian"

    def describe(self, s):
        return f"GET {FEED}"

    def fetch(self, http, s, ctx=None):
        data = conditional_get(http, FEED, ctx, headers={"Accept": "application/json"}).json()
        need(isinstance(data, list), f"atlassian: expected a list, got {type(data).__name__}")
        jobs: dict[str, Job] = {}
        for r in data:
            need(isinstance(r, dict) and r.get("id") and "title" in r, "atlassian: listing without id/title")
            jid = str(r["id"])
            if jid in jobs:
                continue
            portal = r.get("portalJobPost") or {}
            category = r.get("category") or ""
            jobs[jid] = Job(
                id=jid, title=(r.get("title") or "").strip(),
                location="; ".join(" ".join(str(x).split()) for x in r.get("locations") or []),
                url=portal.get("portalUrl") or f"https://www.atlassian.com/company/careers/details/{jid}",
                snippet=html_text(" ".join(str(r.get(k) or "") for k in ("overview", "responsibilities", "qualifications"))),
                department=category,
                employment_type="Intern" if category == "Interns" else (r.get("type") or ""),
                extra={"updated": portal.get("updatedDate")},
            )
        return list(jobs.values())
