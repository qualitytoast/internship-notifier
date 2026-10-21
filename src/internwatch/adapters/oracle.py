"""Oracle Recruiting Cloud (Oracle HCM "Candidate Experience") REST API.

settings:
  host: eeho.fa.us2.oraclecloud.com     (the REST host the career site calls; may be a vanity host)
  site: CX_45001                        (siteNumber)
  job_url: https://careers.oracle.com/en/sites/jobsearch/job/{id}   (optional public link template)
GET https://<host>/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true
    &expand=requisitionList.secondaryLocations
    &finder=findReqs;siteNumber=<site>,limit=200,offset=N,sortBy=POSTING_DATES_DESC
→ {"items": [{"TotalJobsCount": N, "requisitionList": [{Id, Title, PostedDate, PrimaryLocation, …}]}]}
"""
from __future__ import annotations

from ..models import Job
from .base import (Checker, check_total, dedupe, html_text, iso_date, join_locations, need, need_list, register,
                   report_skipped)

PAGE = 200


@register
class OracleRecruiting(Checker):
    type = "oracle"
    supports_detail = True

    def api(self, s):
        return f"https://{s['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"

    def describe(self, s):
        return f"{self.api(s)} (siteNumber={s['site']})"

    def fetch(self, http, s, ctx=None):
        jobs, offset, total, bad = [], 0, None, 0
        while True:
            finder = f"findReqs;siteNumber={s['site']},limit={PAGE},offset={offset},sortBy=POSTING_DATES_DESC"
            data = http.get_json(self.api(s), params={"onlyData": "true", "expand": "requisitionList.secondaryLocations",
                                                      "finder": finder})
            items = need_list(data, "items", f"oracle:{s['site']}")
            need(items and isinstance(items[0], dict), f"oracle:{s['site']}: empty items")
            reqs = need_list(items[0], "requisitionList", f"oracle:{s['site']}")
            if total is None:
                total = items[0].get("TotalJobsCount")
                need(isinstance(total, int), f"oracle:{s['site']}: no TotalJobsCount")
            for r in reqs:
                if not (isinstance(r, dict) and r.get("Id") and "Title" in r):
                    bad += 1  # a requisition caught mid-edit: skipped, and reported below
                    continue
                secondary = [x.get("Name") for x in r.get("secondaryLocations") or []]
                tmpl = s.get("job_url") or f"https://{s['host']}/hcmUI/CandidateExperience/en/sites/{s['site']}/job/{{id}}"
                jobs.append(Job(
                    id=str(r["Id"]),
                    title=r.get("Title") or "",
                    location=join_locations(r.get("PrimaryLocation"), secondary),
                    url=tmpl.format(id=r["Id"]),
                    posted=iso_date(r.get("PostedDate")),
                    snippet=html_text(" ".join(str(r.get(k) or "") for k in ("ShortDescriptionStr", "ExternalQualificationsStr"))),
                    department=r.get("Department") or r.get("JobFamily") or "",
                    employment_type=" ".join(str(r.get(k)) for k in ("WorkerType", "JobType", "ContractType") if r.get(k)),
                ))
            offset += PAGE
            if not reqs or offset >= total:
                break
        jobs = dedupe(jobs)
        check_total(len(jobs) + bad, total, f"oracle:{s['site']}")
        report_skipped(ctx, bad, len(jobs), f"oracle:{s['site']}: skipped {bad} requisitions without Id/Title")
        return jobs

    def detail(self, http, s, job):
        d = http.get_json(f"https://{s['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails",
                          params={"expand": "all", "onlyData": "true",
                                  "finder": f"ById;Id=\"{job.id}\",siteNumber={s['site']}"})
        items = need_list(d, "items", f"oracle:{s['site']} detail")
        if items:
            it = items[0]
            job.snippet = html_text(" ".join(str(it.get(k) or "") for k in (
                "ExternalDescriptionStr", "ExternalQualificationsStr", "ExternalResponsibilitiesStr"))) or job.snippet
        return job
