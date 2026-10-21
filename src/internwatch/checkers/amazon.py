"""Amazon (amazon.jobs): the complete student slice of the site's own search API.

POST https://www.amazon.jobs/api/jobs/search?is_als=true   (JSON body; start/size paging, size ≤ 200)
→ {"found": N, "searchHits": [{"fields": {icimsJobId: [..], title: [..], normalizedLocation: [..], createdDate: [..],
     employeeClass: [..], isIntern: [..], description: [..], category: [..], businessCategory: [..]}}]}

Any search reports at most 10,000 hits and the site has ~22,000 jobs, so "read everything" is impossible.
Amazon tags student roles with structured fields, so the checker reads, unioned by job id:
  1. isIntern=1 OR employeeClass ∈ {Intern, Apprentice}                       (~600)
  2. businessCategory ∈ {studentprograms, university}, minus query 1          (~190)
  3. keyword searches (intern, interns, internship(s), apprentice, co-op, student, …, the freshman/sophomore
     words, "propel") over everything outside 1 and 2 (title-only student roles, e.g. RME apprentices)
     (~0–200 each; "internship" ~2,400, as it also matches descriptions)
Discovery showed this union contains every student title on the site (see discovery/notes/amazon.md).
Only the "a-confidential-job" business category is excluded: the default isConfidential=1 exclusion hides
public internships. Apply links (account.amazon.jobs) are robots-disallowed: linked, never fetched.

settings: {} (all defaults); `keywords` overrides the keyword list.
"""
from __future__ import annotations

import copy

from ..adapters.base import UNDERCLASS_SEARCH_WORDS, Checker, html_text, iso_date, join_locations, need, register
from ..models import Job

API = "https://www.amazon.jobs/api/jobs/search?is_als=true"
PAGE = 200
CAP = 10000
CONFIDENTIAL = {"name": "businessCategory", "values": [{"name": "a-confidential-job"}]}
FLAGS = [{"name": "isIntern", "values": [{"name": "1"}]},
         {"name": "employeeClass", "values": [{"name": "Intern"}, {"name": "Apprentice"}]}]
BIZ = [{"name": "businessCategory", "values": [{"name": "studentprograms"}, {"name": "university"}]}]
# Exact-word searches: the index does not stem, so "intern" misses an unflagged "… Internship" outside the
# student categories, and each form is searched. Most return 0-60 rows outside the structured slice, a few
# plural phrases up to ~200 ("discovery events"), and "internship" ~2,400 (it matches descriptions), all far
# below the cap. "propel" is Amazon's freshman/sophomore program (role_keywords in companies.yaml).
KEYWORDS = ["intern", "interns", "internship", "internships", "apprentice", "co-op", "student", "working student",
            "summer analyst", *UNDERCLASS_SEARCH_WORDS, "propel"]
HEADERS = {"Content-Type": "application/json", "Accept": "application/json", "Origin": "https://www.amazon.jobs"}


def _base() -> dict:
    return {"accessLevel": "EXTERNAL", "contentFilterFacets": [], "excludeFacets": [CONFIDENTIAL], "filterFacets": [],
            "includeFacets": [], "jobTypeFacets": [], "locationFacets": [], "query": "", "size": PAGE, "start": 0,
            "treatment": "OM", "sort": {"sortOrder": "DESCENDING", "sortType": "CREATED_DATE"}}


def _f(fields: dict, key: str) -> str:
    v = fields.get(key)
    if isinstance(v, list):
        v = v[0] if v else ""
    return str(v or "").strip()


def queries(keywords: list[str]) -> list[tuple[str, dict]]:
    q1 = _base()
    q1["jobTypeFacets"] = FLAGS
    q2 = _base()
    q2["filterFacets"] = BIZ
    q2["excludeFacets"] = [CONFIDENTIAL] + FLAGS
    out = [("flags", q1), ("student-business", q2)]
    for kw in keywords:
        q = _base()
        q["query"] = kw
        q["excludeFacets"] = [CONFIDENTIAL] + FLAGS + BIZ
        q["sort"] = {"sortOrder": "DESCENDING", "sortType": "SCORE"}
        out.append((f"keyword:{kw}", q))
    return out


@register
class Amazon(Checker):
    type = "amazon"
    supports_quick = True

    def describe(self, s):
        return f"POST {API} (student slice: intern/apprentice flags + student business categories + keyword sweep)"

    def _job(self, fields: dict) -> Job:
        jid = _f(fields, "icimsJobId")
        need(jid and _f(fields, "title"), "amazon: hit without icimsJobId/title")
        etype = "Intern" if _f(fields, "isIntern") == "1" else _f(fields, "employeeClass")
        return Job(id=jid, title=_f(fields, "title"),
                   location=join_locations(_f(fields, "normalizedLocation") or _f(fields, "location")),
                   url=f"https://www.amazon.jobs/en/jobs/{jid}", posted=iso_date(int(_f(fields, "createdDate") or 0) or None),
                   snippet=html_text(" ".join(_f(fields, k) for k in ("description", "basicQualifications"))),
                   department=" / ".join(x for x in (_f(fields, "category"), _f(fields, "businessCategory")) if x),
                   employment_type=etype)

    def fetch(self, http, s, ctx=None):
        out: dict[str, Job] = {}
        quick = ctx is not None and ctx.quick
        slice_total = 0
        for name, body in queries(list(s.get("keywords") or KEYWORDS)):
            start, found, seen = 0, None, 0
            while True:
                b = copy.deepcopy(body)
                b["start"] = start
                d = http.post_json(API, json=b, headers=HEADERS)
                need(isinstance(d, dict) and "searchHits" in d, f"amazon: unexpected answer for {name}")
                hits = d.get("searchHits") or []          # a query with no match answers searchHits: null
                if found is None:
                    found = int(d.get("found") or 0)
                    need(found < CAP, f"amazon: query {name} hit the {CAP} cap ({found}); the slice must be split")
                ids = []
                for h in hits:
                    j = self._job(h.get("fields") or {})
                    ids.append(j.id)
                    out.setdefault(j.id, j)
                seen += len(hits)
                start += PAGE
                if not hits or start >= found:
                    break
                if quick and body["sort"]["sortType"] == "CREATED_DATE" and ctx.page_is_old(ids, key=name):
                    break
            if not quick and found:
                need(seen + max(2, found // 50) >= found, f"amazon: query {name} returned {seen} of {found}")
            slice_total += found or 0
        if ctx is not None:
            ctx.reported_total = slice_total
        return list(out.values())
