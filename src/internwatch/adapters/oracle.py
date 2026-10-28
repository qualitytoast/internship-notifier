"""Oracle Recruiting Cloud (Oracle HCM "Candidate Experience") REST API.

settings:
  host: eeho.fa.us2.oraclecloud.com     (the REST host the career site calls; may be a vanity host)
  site: CX_45001                        (siteNumber)
  job_url: https://careers.oracle.com/en/sites/jobsearch/job/{id}   (optional public link template)
  watch_ids: [297770, …]                (optional) requisitions to look up one by one: Dell takes internships out
                                        of its search while they still take applications. The runner adds the ids
                                        of SimplifyJobs rows when learn_ids is true.
GET https://<host>/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true
    &expand=requisitionList.secondaryLocations
    &finder=findReqs;siteNumber=<site>,limit=200,offset=N,sortBy=POSTING_DATES_DESC
→ {"items": [{"TotalJobsCount": N, "requisitionList": [{Id, Title, PostedDate, PrimaryLocation, …}]}]}
Detail / watched: GET …/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id="<id>",siteNumber=<site>
→ 0 items when closed. A watched requisition outside the search is kept while it has posting dates or
ApplyWhenNotPostedFlag "True" (still takes applications by direct link); one that can't be read marks the poll degraded.
"""
from __future__ import annotations

from ..models import CheckerError, Job
from .base import (Checker, check_total, dedupe, degrade, html_text, iso_date, join_locations, need, need_list,
                   register, report_skipped)

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
        if s.get("watch_ids"):
            jobs += self._watched(http, s, ctx, {j.id for j in jobs})
        return jobs

    def _details(self, http, s, jid: str) -> dict | None:
        d = http.get_json(f"https://{s['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails",
                          params={"expand": "all", "onlyData": "true",
                                  "finder": f"ById;Id=\"{jid}\",siteNumber={s['site']}"})
        items = need_list(d, "items", f"oracle:{s['site']} detail")
        return items[0] if items else None

    @staticmethod
    def _description(it: dict) -> str:
        return html_text(" ".join(str(it.get(k) or "") for k in (
            "ExternalDescriptionStr", "ExternalQualificationsStr", "ExternalResponsibilitiesStr")))

    def _watched(self, http, s, ctx, listed: set[str]) -> list[Job]:
        tmpl = s.get("job_url") or f"https://{s['host']}/hcmUI/CandidateExperience/en/sites/{s['site']}/job/{{id}}"
        out, opened, closed = [], [], []
        for wid in dict.fromkeys(str(x) for x in s["watch_ids"]):
            if wid in listed:
                continue
            try:
                it = self._details(http, s, wid)
            except CheckerError as e:
                if ctx is None:
                    raise
                degrade(ctx, f"oracle:{s['site']}: watched requisition {wid}: {e}")
                continue
            if not (it and it.get("Title") and (it.get("ExternalPostedStartDate")
                                                 or str(it.get("ApplyWhenNotPostedFlag")).lower() == "true")):
                closed.append(wid)
                continue
            opened.append(wid)
            out.append(Job(
                id=wid, title=it["Title"],
                location=join_locations(it.get("PrimaryLocation"), [x.get("Name") for x in it.get("secondaryLocations") or []
                                                                    if isinstance(x, dict)]),
                url=tmpl.format(id=wid), posted=iso_date(it.get("ExternalPostedStartDate")),
                snippet=self._description(it),
                department=it.get("Department") or it.get("JobFamily") or "",
                employment_type=" ".join(str(it.get(k)) for k in ("WorkerType", "JobType", "ContractType", "RequisitionType")
                                         if it.get(k)),
                extra={"unlisted": True},
            ))
        if ctx is not None:
            ctx.state["watch_open"] = opened
            ctx.state["watch_closed"] = sorted(set(ctx.state.get("watch_closed") or []) | set(closed))[-300:]
        return out

    def detail(self, http, s, job):
        it = self._details(http, s, job.id)
        if it:
            job.snippet = self._description(it) or job.snippet
        return job
