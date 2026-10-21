"""Gem job boards (jobs.gem.com/<board>), via the board's public GraphQL batch endpoint.

settings: board: <vanity path>   e.g. groq
POST https://jobs.gem.com/api/public/graphql/batch  [JobBoardList query] → oatsExternalJobPostings.jobPostings
"""
from __future__ import annotations

from ..models import Job
from .base import Checker, join_locations, need, register

ENDPOINT = "https://jobs.gem.com/api/public/graphql/batch"
LIST_QUERY = """query JobBoardList($boardId: String!) {
  oatsExternalJobPostings(boardId: $boardId) {
    jobPostings {
      id
      extId
      title
      locations { id name city isoCountry isRemote extId __typename }
      job { id department { id name extId __typename } locationType employmentType __typename }
      __typename
    }
    __typename
  }
}"""



@register
class Gem(Checker):
    type = "gem"

    def describe(self, s):
        return f"{ENDPOINT} (JobBoardList, boardId={s['board']})"

    def fetch(self, http, s, ctx=None):
        board = s["board"]
        payload = [{"operationName": "JobBoardList", "variables": {"boardId": board}, "query": LIST_QUERY}]
        data = http.post_json(ENDPOINT, json=payload, headers={"Content-Type": "application/json"})
        need(isinstance(data, list) and data and isinstance(data[0], dict), f"gem:{board}: unexpected response")
        errors = data[0].get("errors")
        need(not errors, f"gem:{board}: GraphQL errors {str(errors)[:200]}")
        try:
            posts = data[0]["data"]["oatsExternalJobPostings"]["jobPostings"]
        except (KeyError, TypeError):
            posts = None
        need(isinstance(posts, list), f"gem:{board}: jobPostings missing")
        jobs = []
        for p in posts:
            need(p.get("extId") and "title" in p, f"gem:{board}: posting without extId/title")
            locs = []
            for loc in p.get("locations") or []:
                name = loc.get("name") or loc.get("city") or ""
                if loc.get("isoCountry") and loc["isoCountry"] not in name:
                    name = f"{name}, {loc['isoCountry']}" if name else loc["isoCountry"]
                if loc.get("isRemote"):
                    name = f"Remote ({name})" if name else "Remote"
                locs.append(name)
            job = p.get("job") or {}
            jobs.append(Job(
                id=p["extId"],
                title=p.get("title") or "",
                location=join_locations(locs),
                url=f"https://jobs.gem.com/{board}/{p['extId']}",
                department=((job.get("department") or {}).get("name")) or "",
                employment_type=job.get("employmentType") or "",
            ))
        return jobs
