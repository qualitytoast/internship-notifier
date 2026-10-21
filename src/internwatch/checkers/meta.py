"""Meta careers (metacareers.com): the site's own GraphQL search, one POST for every job.

1. GET  https://www.metacareers.com/jobsearch/   (navigation sec-fetch-* headers) → "LSD" token in the HTML
2. POST https://www.metacareers.com/graphql  form: lsd, doc_id=<CareersJobSearchResultsV2DataQuery>, variables
   → data.job_search_with_featured_jobs_v2.{all_jobs, featured_jobs}[] {id, title, locations[], teams[], sub_teams[]}
3. the same POST with roles=["Internship"] marks the official internships
Detail: GET https://www.metacareers.com/profile/job_details/<id>/ → JSON-LD JobPosting (datePosted, description)

settings: doc_id (persisted query id; Meta can rotate it). If the GraphQL answer stops parsing, the checker
falls back to the jobs sitemap (ids only) plus detail pages for unknown ids, and reports itself degraded so
you get a health alert asking for the new doc_id (copy it from your browser's devtools: the POST /graphql
with fb_api_req_friendly_name=CareersJobSearchResultsV2DataQuery). If only step 3 fails, every job from step 2
is kept (internships are then judged by title alone) and the poll is reported degraded. See discovery/notes/meta.md.
"""
from __future__ import annotations

import json
import re

from ..adapters.base import Checker, html_text, iso_date, join_locations, need, register
from ..models import CheckerError, CheckTimeout, FetchError, Job, ShapeError

BASE = "https://www.metacareers.com"
DOC_ID = "27129360303422352"
LSD_RE = re.compile(r'\["LSD",\[\],\{"token":"([^"]+)"\}')
NAV = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "sec-fetch-dest": "document",
       "sec-fetch-mode": "navigate", "sec-fetch-site": "none", "sec-fetch-user": "?1"}
XHR = {"Accept": "*/*", "Content-Type": "application/x-www-form-urlencoded", "sec-fetch-dest": "empty",
       "sec-fetch-mode": "cors", "sec-fetch-site": "same-origin", "Origin": BASE, "Referer": BASE + "/jobsearch/"}
SEARCH = {"q": None, "divisions": [], "offices": [], "roles": [], "leadership_levels": [], "saved_jobs": [],
          "saved_searches": [], "sub_teams": [], "teams": [], "is_leadership": False, "is_remote_only": False,
          "sort_by_new": False, "results_per_page": None}
FALLBACK_DETAIL_LIMIT = 60
FALLBACK_MAX_MISSES = 3     # runs an id's page may give no title before the fallback stops asking for it
FALLBACK_MISS_CAP = 300     # ids whose misses are remembered in ctx.state (the newest)


def job_url(jid: str) -> str:
    return f"{BASE}/profile/job_details/{jid}/"


def _place_text(place) -> str:
    """One schema.org jobLocation entry → "City, Region, Country". The Place may be a single object or plain
    text, its address an object or plain text, and addressCountry a Country object."""
    a = place.get("address") if isinstance(place, dict) else place
    if isinstance(a, str):
        return a.strip()
    if not isinstance(a, dict):
        return ""
    parts = [a.get(k) for k in ("addressLocality", "addressRegion", "addressCountry")]
    parts = [p.get("name") if isinstance(p, dict) else p for p in parts]
    return ", ".join(p.strip() for p in parts if isinstance(p, str) and p.strip())


@register
class Meta(Checker):
    type = "meta"
    supports_detail = True

    def describe(self, s):
        return f"POST {BASE}/graphql doc_id={s.get('doc_id', DOC_ID)} (all jobs in one response)"

    def _token(self, http, ctx, fresh: bool = False) -> str:
        if not fresh and ctx is not None and ctx.state.get("lsd"):
            return ctx.state["lsd"]
        html = http.get_text(BASE + "/jobsearch/", headers=NAV)
        m = LSD_RE.search(html)
        need(m, "meta: LSD token not found on /jobsearch/")
        if ctx is not None:
            ctx.state["lsd"] = m.group(1)
        return m.group(1)

    def _search(self, http, s, lsd: str, roles: list[str]):
        variables = {"search_input": {**SEARCH, "roles": roles}, "viewasUserID": None, "isLoggedIn": False}
        form = {"lsd": lsd, "doc_id": str(s.get("doc_id", DOC_ID)), "variables": json.dumps(variables, separators=(",", ":")),
                "fb_api_req_friendly_name": "CareersJobSearchResultsV2DataQuery", "fb_api_caller_class": "RelayModern"}
        r = http.post(BASE + "/graphql", data=form, headers={**XHR, "X-FB-LSD": lsd})
        try:
            d = json.loads(r.content)
        except ValueError:
            raise ShapeError(f"meta: GraphQL answer is not JSON ({r.content[:80]!r})") from None
        need(not d.get("errors"), f"meta: GraphQL errors {str(d.get('errors'))[:200]}")
        root = (d.get("data") or {}).get("job_search_with_featured_jobs_v2")
        need(isinstance(root, dict) and isinstance(root.get("all_jobs"), list),
             "meta: data.job_search_with_featured_jobs_v2.all_jobs missing (doc_id rotated?)")
        return root

    def _graphql(self, http, s, ctx):
        lsd = self._token(http, ctx)
        try:
            root = self._search(http, s, lsd, [])
        except (FetchError, ShapeError):
            lsd = self._token(http, ctx, fresh=True)  # tokens expire; retry once with a fresh one
            root = self._search(http, s, lsd, [])
        jobs: dict[str, Job] = {}
        for item in root["all_jobs"] + list(root.get("featured_jobs") or []):
            need(item.get("id") and "title" in item, "meta: job without id/title")
            jobs.setdefault(str(item["id"]), Job(
                id=str(item["id"]), title=item.get("title") or "", location=join_locations(item.get("locations") or []),
                url=job_url(item["id"]), department=" / ".join((item.get("teams") or []) + (item.get("sub_teams") or [])[:2]),
            ))
        need(jobs, "meta: GraphQL returned no jobs")
        try:
            interns = self._search(http, s, lsd, ["Internship"])
        except (FetchError, ShapeError) as e:
            if ctx is None:
                raise
            # the job list itself is complete: keep it rather than fall back to the sitemap
            ctx.degraded = f"meta: the Internship query failed ({e}); internships were judged by title only."
            return list(jobs.values())
        for item in interns["all_jobs"]:
            j = jobs.get(str(item.get("id")))
            if j is not None:
                j.employment_type = "Internship"
        return list(jobs.values())

    def _sitemap(self, http, ctx) -> list[Job]:
        """Fallback: new ids from the jobs sitemap, newest first, read one by one (known jobs are left untouched).
        An id whose page gives no title is tried again next run, for FALLBACK_MAX_MISSES runs: a few unreadable
        ids at the top must not use up the detail budget of every run."""
        xml = http.get_text(BASE + "/jobsearch/sitemap.xml")
        ids = sorted(set(re.findall(r"/profile/job_details/(\d+)/", xml)), key=int, reverse=True)
        need(ids, "meta: sitemap fallback has no job ids either")
        known = ctx.known if ctx is not None else frozenset()
        misses = dict(ctx.state.get("sitemap_misses") or {}) if ctx is not None else {}
        unknown = [i for i in ids if i not in known]
        jobs = []
        for jid in [i for i in unknown if misses.get(i, 0) < FALLBACK_MAX_MISSES][:FALLBACK_DETAIL_LIMIT]:
            j = Job(id=jid, title="", url=job_url(jid))
            try:
                self.detail(http, {}, j)
            except CheckTimeout:
                continue  # out of time (or a page that keeps timing out): not counted against the id
            except CheckerError:
                pass
            if j.title:
                jobs.append(j)
                misses.pop(jid, None)
            else:
                misses[jid] = misses.get(jid, 0) + 1
        if ctx is not None:  # keep the misses of ids still unread (not closed or known), the newest
            waiting = sorted(set(misses) & set(unknown), key=int, reverse=True)[:FALLBACK_MISS_CAP]
            ctx.state["sitemap_misses"] = {i: misses[i] for i in waiting}
        return jobs

    def fetch(self, http, s, ctx=None):
        try:
            return self._graphql(http, s, ctx)
        except ShapeError as e:
            jobs = self._sitemap(http, ctx)
            if ctx is None:
                raise
            ctx.degraded = f"{e}. Fell back to the jobs sitemap ({len(jobs)} ids); update doc_id in companies.yaml."
            return jobs

    def detail(self, http, s, job):
        html = http.get_text(job.url, headers=NAV)
        for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
            try:
                d = json.loads(m.group(1))
            except ValueError:
                continue
            if isinstance(d, list):  # several objects in one script
                d = next((x for x in d if isinstance(x, dict) and x.get("@type") == "JobPosting"), None)
            if not isinstance(d, dict) or d.get("@type") != "JobPosting":
                continue
            if d.get("title") and not job.title:
                job.title = " ".join(str(d["title"]).split())
            job.posted = iso_date(d.get("datePosted")) or job.posted
            job.snippet = html_text(" ".join(str(d.get(k) or "") for k in ("description", "responsibilities", "qualifications")))
            et = d.get("employmentType")
            if et and not job.employment_type:
                job.employment_type = ", ".join(et) if isinstance(et, list) else str(et)
            places = d.get("jobLocation") or []
            locs = [_place_text(p) for p in (places if isinstance(places, list) else [places])]
            if locs and not job.location:
                job.location = "; ".join(x for x in locs if x)
            break
        return job
