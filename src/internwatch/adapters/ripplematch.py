"""RippleMatch public company pages (some companies post their student roles only there: eBay, Palo Alto Networks).

settings: company_id: 865     (from https://app.ripplematch.com/api/v2/company-branded-page/<slug> → company.id)
GET https://app.ripplematch.com/api/v2/public/roles/<company_id> → [{public_id, name, job_type, formatted_locations}]
The server sends an incomplete TLS chain; the missing intermediate ships in internwatch/certs/.
"""
from __future__ import annotations

from ..models import Job
from .base import Checker, need, register

API = "https://app.ripplematch.com/api/v2/public/roles/{company_id}"


@register
class RippleMatch(Checker):
    type = "ripplematch"

    def describe(self, s):
        return API.format(company_id=s["company_id"])

    def fetch(self, http, s, ctx=None):
        data = http.get_json(self.describe(s))
        need(isinstance(data, list), f"ripplematch:{s['company_id']}: expected a list, got {type(data).__name__}")
        jobs = []
        for r in data:
            need(isinstance(r, dict) and r.get("public_id") and "name" in r, f"ripplematch:{s['company_id']}: role without id/name")
            locs = r.get("formatted_locations") or "; ".join(
                x.get("city", "") for x in r.get("role_locations") or [] if isinstance(x, dict) and x.get("city"))
            jobs.append(Job(id=str(r["public_id"]), title=(r.get("name") or "").strip(), location=locs or "",
                            url=f"https://app.ripplematch.com/v2/public/job/{r['public_id']}",
                            employment_type=r.get("job_type") or ""))
        return jobs
