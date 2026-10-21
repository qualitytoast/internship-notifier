"""Apple (jobs.apple.com): the student slice of the site's own search API.

POST https://jobs.apple.com/api/v1/search {"query": "", "filters": {}, "page": N, "locale": "en-us", "sort": "newest", …}
→ {"res": {"totalRecords": N, "searchResults": [{id, positionId, postingTitle, transformedPostingTitle,
     postDateInGMT, locations[{name, stateProvince, countryName}], team{teamCode, teamName}}]}}   (20 rows per page)
The site has ~6,000 rows (one per posting × location), so the checker reads, unioned by position:
  1. the Students team's Internships sub-team (every US internship is on it; its rows count as internships even
     when the title has no student word), then the rest of the Students team (retail student roles, academies,
     new grads: judged by title like any other job)
  2. exact-word searches "intern", "internship", "student", "co-op" and the freshman/sophomore words (student
     titles filed under functional teams abroad; unquoted 'intern' would prefix-match 'international')
Detail: GET https://jobs.apple.com/api/v1/jobDetails/<positionId>?locale=en-us → description, employmentType.
See discovery/notes/apple.md.
"""
from __future__ import annotations

from ..adapters.base import UNDERCLASS_SEARCH_WORDS, Checker, html_text, iso_date, join_locations, need, register
from ..models import Job

API = "https://jobs.apple.com/api/v1/search"
HEADERS = {"Content-Type": "application/json", "Accept": "*/*", "Origin": "https://jobs.apple.com",
           "Referer": "https://jobs.apple.com/en-us/search", "locale": "en_US", "browserLocale": "en-us"}
QUERIES = [("internships", {"query": "", "filters": {"teams": [{"team": "teamsAndSubTeams-STDNT", "subTeam": "subTeam-INTRN"}]}}),
           ("students-team", {"query": "", "filters": {"teams": [{"team": "teamsAndSubTeams-STDNT"}]}})] + [
    (f"keyword:{w}", {"query": f'"{w}"', "filters": {}})
    for w in ("intern", "internship", "student", "co-op", *UNDERCLASS_SEARCH_WORDS)]
PAGE = 20


def _row_url(r: dict) -> str:
    rid, pos = str(r.get("id") or ""), str(r.get("positionId") or "")
    h = pos if ("REQ" in rid or "PIPE" in rid) else rid
    team = (r.get("team") or {}).get("teamCode", "")
    return f"https://jobs.apple.com/en-us/details/{h}/{r.get('transformedPostingTitle', '')}" + (f"?team={team}" if team else "")


@register
class Apple(Checker):
    type = "apple"
    supports_detail = True
    supports_quick = True

    def describe(self, s):
        return f"POST {API} (student slice: Students team + exact-word searches)"

    def fetch(self, http, s, ctx=None):
        quick = ctx is not None and ctx.quick
        out: dict[str, Job] = {}
        slice_rows = 0
        for name, q in QUERIES:
            page, total, rows = 1, None, 0
            while True:
                body = {**q, "page": page, "locale": "en-us", "sort": "newest",
                        "format": {"longDate": "MMMM D, YYYY", "mediumDate": "MMM D, YYYY"}}
                d = http.post_json(API, json=body, headers=HEADERS)
                res = d.get("res") if isinstance(d, dict) else None
                need(isinstance(res, dict), f"apple: no 'res' in the answer for {name}")
                items = res.get("searchResults") or []
                if total is None:
                    total = int(res.get("totalRecords") or 0)
                ids = []
                for r in items:
                    need(r.get("id") and r.get("postingTitle"), f"apple: row without id/title ({name})")
                    pos = str(r.get("positionId") or r["id"])
                    ids.append(pos)
                    loc = (r.get("locations") or [{}])[0]
                    where = ", ".join(x for x in (loc.get("name"), loc.get("stateProvince"), loc.get("countryName")) if x)
                    team = r.get("team") or {}
                    j = out.get(pos)
                    if j is None:
                        out[pos] = Job(id=pos, title=r["postingTitle"], location=where, url=_row_url(r),
                                       posted=iso_date(r.get("postDateInGMT")), department=team.get("teamName", ""),
                                       employment_type="Intern (Apple Internships team)" if name == "internships" else "",
                                       extra={"alt_ids": [str(r["id"])]})
                    else:
                        j.location = join_locations(j.location.split("; "), where)
                        if name == "internships" and not j.employment_type:
                            j.employment_type = "Intern (Apple Internships team)"
                rows += len(items)
                page += 1
                if not items or rows >= total or page > 400:
                    break
                if quick and ctx.page_is_old(ids, key=name):
                    break
            if not quick:
                need(rows + max(2, total // 50) >= total, f"apple: {name} returned {rows} of {total} rows")
            slice_rows += total
        if ctx is not None:
            ctx.reported_total = slice_rows
        return list(out.values())

    def detail(self, http, s, job):
        d = http.get_json(f"https://jobs.apple.com/api/v1/jobDetails/{job.id}", params={"locale": "en-us"})
        res = d.get("res") if isinstance(d, dict) else None
        if isinstance(res, dict):
            job.snippet = html_text(" ".join(str(res.get(k) or "") for k in
                                             ("jobSummary", "description", "minimumQualifications", "keyQualifications"))) or job.snippet
            if res.get("employmentType") and not job.employment_type:
                job.employment_type = str(res["employmentType"])
        return job
