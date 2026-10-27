"""D. E. Shaw: the job list inside deshaw.com/careers (a Next.js page; no hiring system's feed is public).

GET https://www.deshaw.com/careers  (≈1 MB, ETag → 304 when unchanged)
→ <script id="__NEXT_DATA__"> props.pageProps: regularJobs[] (the "All positions" list), internships[] (the
  "Internships" list) and internalJobs[] (internal-only postings, activeOnJobsListing false: not on the page, not read)
Each item's data: {id, displayName, jobUrl, activeOnJobsListing, department.name, jobDescription.websiteDescription,
jobMetadata: {workStatus ("Intern", "Regular Full-Time", …), jobLocations[].name ("New York", "London", …)}}.
Job page: https://www.deshaw.com/careers/<jobUrl in lower case>, e.g. /careers/applied-ai-engineer-5375.
pageProps.jobsFetchingError means the page could not load its own jobs: reported, never read as 0 jobs.
See discovery/notes/de-shaw.md.
"""
from __future__ import annotations

import json
import re

from ..adapters.base import Checker, conditional_get, html_text, need, need_list, register
from ..models import Job

PAGE = "https://www.deshaw.com/careers"
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', re.S)
LISTS = ("regularJobs", "internships")


@register
class DEShaw(Checker):
    type = "deshaw"

    def describe(self, s):
        return f"GET {PAGE} (__NEXT_DATA__: {' + '.join(LISTS)})"

    def fetch(self, http, s, ctx=None):
        m = NEXT_DATA.search(conditional_get(http, PAGE, ctx).text)
        need(m, "deshaw: no __NEXT_DATA__ on the careers page")
        try:
            props = json.loads(m.group(1))["props"]["pageProps"]
        except (ValueError, KeyError, TypeError):
            props = None
        need(isinstance(props, dict), "deshaw: __NEXT_DATA__ has no props.pageProps")
        need(not props.get("jobsFetchingError"), "deshaw: the careers page could not load its jobs (jobsFetchingError)")
        jobs: dict[str, Job] = {}
        for name in LISTS:
            for item in need_list(props, name, "deshaw"):
                d = item.get("data") if isinstance(item, dict) else None
                need(isinstance(d, dict) and d.get("id") and d.get("displayName"), f"deshaw: {name} item without id/title")
                if d.get("activeOnJobsListing") is False:  # not shown on the page
                    continue
                jid = str(d["id"])
                meta = d.get("jobMetadata") or {}
                jobs.setdefault(jid, Job(
                    id=jid, title=d["displayName"],
                    location="; ".join(x["name"] for x in meta.get("jobLocations") or [] if x.get("name")),
                    url=f"{PAGE}/{(d.get('jobUrl') or jid).lower()}",
                    snippet=html_text((d.get("jobDescription") or {}).get("websiteDescription")),
                    department=(d.get("department") or {}).get("name") or "",
                    employment_type=meta.get("workStatus") or "",
                    extra={"list": name},
                ))
        return list(jobs.values())
