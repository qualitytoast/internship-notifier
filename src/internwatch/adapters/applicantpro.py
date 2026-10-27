"""ApplicantPro job boards (<subdomain>.applicantpro.com).

settings: subdomain: group1   the board's subdomain (Group One Trading)
          domain_id: 489      the board's numeric id (its pages' widgets call /core/…/<domain_id>)
List: GET https://<subdomain>.applicantpro.com/core/jobs/<domain_id>?getParams={"isInternal":0}
      → {"success": true, "data": {"jobs": [...], "jobCount": N}}   (the list the board's /jobs/ page shows)
      job: {id, title, city, abbreviation (state), iso3, jobLocation, employmentType ("Internship", "Seasonal", …),
            orgTitle (department), startDateRef ("Sep 24, 2026"), workplaceType, jobUrl}
"""
from __future__ import annotations

import json

from ..models import Job
from .base import Checker, check_total, iso_date, need, need_list, register


@register
class ApplicantPro(Checker):
    type = "applicantpro"

    def describe(self, s):
        return f"GET https://{s['subdomain']}.applicantpro.com/core/jobs/{s['domain_id']}"

    def fetch(self, http, s, ctx=None):
        sub = s["subdomain"]
        d = http.get_json(f"https://{sub}.applicantpro.com/core/jobs/{s['domain_id']}",
                          params={"getParams": json.dumps({"isInternal": 0}, separators=(",", ":"))})
        need(isinstance(d, dict) and d.get("success") is not False,
             f"applicantpro:{sub}: the board answered with an error: {str(d)[:200]}")
        data = d.get("data")
        items = need_list(data, "jobs", f"applicantpro:{sub}")
        jobs = []
        for j in items:
            need(j.get("id") and j.get("title"), f"applicantpro:{sub}: job without id/title")
            place = ", ".join(str(x) for x in (j.get("city"), j.get("abbreviation"), j.get("iso3")) if x)
            jobs.append(Job(
                id=str(j["id"]), title=j["title"], location=place or j.get("jobLocation") or "",
                url=j.get("jobUrl") or f"https://{sub}.applicantpro.com/jobs/{j['id']}",
                posted=iso_date(j.get("startDateRef")), department=j.get("orgTitle") or "",
                employment_type=j.get("employmentType") or "", extra={"workplace": j.get("workplaceType") or ""},
            ))
        check_total(len(items), data.get("jobCount"), f"applicantpro:{sub}", tolerance=0)
        return jobs
