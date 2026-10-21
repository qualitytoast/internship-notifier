"""HubSpot: the GraphQL API behind hubspot.com/careers/jobs (it proxies HubSpot's Greenhouse board).

POST https://wtcfns.hubspot.com/careers/graphql {"operationName": "Jobs", …} → data.jobs[] {id, title, department, office, location}
One response holds the whole list. In Oct 2026 HubSpot's backend answered with an error (its Greenhouse board
was switched off), so errors / data.jobs == null are reported as a broken feed, never as "0 jobs".
Job page: https://www.hubspot.com/careers/jobs/<id>. North America interns are also posted on RippleMatch
(company 708), which companies.yaml adds as a second source. See discovery/notes/hubspot.md.
"""
from __future__ import annotations

from ..adapters.base import Checker, need, register
from ..models import Job

API = "https://wtcfns.hubspot.com/careers/graphql"
QUERY = ("query Jobs($departmentIds: [Int], $officeIds: [Int], $languages: [String], $roleTypes: [String], "
         "$searchQuery: String) { jobs(departmentIds: $departmentIds, officeIds: $officeIds, languages: $languages, "
         "roleTypes: $roleTypes, searchQuery: $searchQuery) { id title department { name id } office { id location } "
         "location { name } } }")


@register
class HubSpot(Checker):
    type = "hubspot"

    def describe(self, s):
        return f"POST {API} (Jobs query, every job)"

    def fetch(self, http, s, ctx=None):
        body = {"operationName": "Jobs", "query": QUERY,
                "variables": {"departmentIds": [], "officeIds": [], "languages": [], "roleTypes": []}}
        d = http.post_json(API, json=body, headers={"Content-Type": "application/json"})
        need(isinstance(d, dict) and not d.get("errors"),
             f"hubspot: careers API answered with an error: {str(d.get('errors') if isinstance(d, dict) else d)[:200]}")
        jobs = (d.get("data") or {}).get("jobs")
        need(isinstance(jobs, list), "hubspot: data.jobs missing")
        out = []
        for j in jobs:
            need(j.get("id") and j.get("title"), "hubspot: job without id/title")
            loc = (j.get("location") or {}).get("name") or (j.get("office") or {}).get("location") or ""
            out.append(Job(id=str(j["id"]), title=j["title"], location=loc,
                           url=f"https://www.hubspot.com/careers/jobs/{j['id']}",
                           department=(j.get("department") or {}).get("name", "")))
        return out
