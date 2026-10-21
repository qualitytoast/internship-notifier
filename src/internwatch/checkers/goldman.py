"""Goldman Sachs "Higher" (higher.gs.com): the site's GraphQL API, every external role.

POST https://api-higher.gs.com/gateway/api/v1/graphql  {"operationName": "GetRoles", …, pageSize ≤ 250}
→ data.roleSearch.{totalCount, page.hasNext, items[]}; items carry externalSource.sourceId (the Oracle
requisition number, also the public URL id), jobTitle, corporateTitle, division, locations[], lastPostedDate.
Student roles are corporateTitle Summer Analyst / Summer Associate / Seasonal (off-cycle, placements).
higher.gs.com's own pages are robots-disallowed except /roles/, which is what the links point to.

settings: experiences: [PROFESSIONAL, EARLY_CAREER, CAMPUS]
See discovery/notes/goldman-sachs.md.
"""
from __future__ import annotations

from ..adapters.base import Checker, check_total, html_text, iso_date, join_locations, need, register
from ..models import Job

API = "https://api-higher.gs.com/gateway/api/v1/graphql"
PAGE = 250
QUERY = ("query GetRoles($searchQueryInput: RoleSearchQueryInput!) { roleSearch(searchQueryInput: $searchQueryInput) "
         "{ totalCount page { pageSize pageNumber hasNext } items { roleId corporateTitle jobTitle jobFunction division "
         "status externalJobStatus locations { primary city state country corporateRegion } shortDescription "
         "lastPostedDate externalSource { sourceId externalSourceType } } } }")
STUDENT_TITLES = {"summer analyst", "summer associate", "seasonal"}


@register
class Goldman(Checker):
    type = "goldman"

    def describe(self, s):
        return f"POST {API} (GetRoles, {', '.join(s.get('experiences', ['PROFESSIONAL', 'EARLY_CAREER', 'CAMPUS']))})"

    def fetch(self, http, s, ctx=None):
        experiences = s.get("experiences") or ["PROFESSIONAL", "EARLY_CAREER", "CAMPUS"]
        jobs: dict[str, Job] = {}
        page, total = 0, None
        while True:
            body = {"operationName": "GetRoles", "query": QUERY, "variables": {"searchQueryInput": {
                "page": {"pageSize": PAGE, "pageNumber": page}, "sort": {"sortStrategy": "POSTED_DATE", "sortOrder": "DESC"},
                "experiences": experiences, "filters": [], "searchTerm": ""}}}
            d = http.post_json(API, json=body, headers={"Content-Type": "application/json", "Accept": "application/json"})
            need(isinstance(d, dict) and not d.get("errors"), f"goldman: GraphQL errors {str(d.get('errors') if isinstance(d, dict) else d)[:200]}")
            rs = (d.get("data") or {}).get("roleSearch")
            need(isinstance(rs, dict) and isinstance(rs.get("items"), list), "goldman: data.roleSearch.items missing")
            if total is None:
                total = rs.get("totalCount")
            for it in rs["items"]:
                src = (it.get("externalSource") or {}).get("sourceId") or it.get("roleId")
                need(src and "jobTitle" in it, "goldman: role without sourceId/jobTitle")
                locs = [", ".join(x for x in (l.get("city"), l.get("state"), l.get("country")) if x)
                        for l in it.get("locations") or []]
                corp = it.get("corporateTitle") or ""
                jobs.setdefault(str(src), Job(
                    id=str(src), title=it.get("jobTitle") or "", location=join_locations(locs),
                    url=f"https://higher.gs.com/roles/{src}", posted=iso_date(it.get("lastPostedDate")),
                    snippet=html_text(it.get("shortDescription")),
                    department=" / ".join(x for x in (it.get("division"), it.get("jobFunction")) if x),
                    employment_type=f"Intern ({corp})" if corp.lower() in STUDENT_TITLES else corp,
                    extra={"alt_ids": [it["roleId"]] if it.get("roleId") else []},
                ))
            page += 1
            if not (rs.get("page") or {}).get("hasNext") or not rs["items"] or page > 40:
                break
        check_total(len(jobs), total, "goldman")
        return list(jobs.values())
