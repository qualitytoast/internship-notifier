"""iCIMS hosted career portals (https://<portal>.icims.com), server-rendered HTML.

settings:
  portal: https://careers-gtsx.icims.com
  params: {searchCategory: 123}   optional extra query params (default: none = every job)
List:   GET <portal>/jobs/search?ss=1&in_iframe=1&pr=<0-based page>   ("Search Results Page X of N")
Detail: GET <portal>/jobs/<id>/<slug>/job?in_iframe=1   (JSON-LD JobPosting: datePosted, employmentType, description)
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from ..models import Job
from .base import Checker, html_text, iso_date, join_locations, need, register

JOB_HREF = re.compile(r"/jobs/(\d+)/[^/?#]+/job")
PAGE_OF = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)", re.I)


def _clean_url(href: str) -> str:
    p = urlsplit(href)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def parse_list(html: str, base: str) -> tuple[list[Job], int | None]:
    soup = BeautifulSoup(html, "lxml")
    jobs: dict[str, Job] = {}
    for a in soup.find_all("a", href=JOB_HREF):
        m = JOB_HREF.search(a["href"])
        jid = m.group(1)
        if jid in jobs:
            continue
        card = a.find_parent(class_=re.compile(r"iCIMS_JobCardItem|row|iCIMS_JobsTable")) or a.parent
        title = (a.find(["h2", "h3"]) or a).get_text(" ", strip=True)
        if not title and a.get("title"):
            title = re.sub(r"^\d+\s*-\s*", "", a["title"])
        locs = []
        for dt in card.find_all(["dt", "span", "div"], string=re.compile(r"^\s*(Job Locations?|Additional Locations?|Location)\s*$", re.I)):
            dd = dt.find_next(["dd", "span", "div"])
            if dd:
                locs += [x.strip() for x in dd.get_text(" ", strip=True).split("|") if x.strip()]
        if not locs:
            hdr = card.find(class_=re.compile(r"iCIMS_JobHeaderData|header.*left", re.I))
            if hdr:
                locs.append(hdr.get_text(" ", strip=True))
        desc = card.find(class_=re.compile(r"description", re.I))
        jobs[jid] = Job(id=jid, title=title, location=join_locations(locs),
                        url=_clean_url(urljoin(base, a["href"])),
                        snippet=desc.get_text(" ", strip=True) if desc else "")
    pages = None
    m = PAGE_OF.search(soup.get_text(" ", strip=True))
    if m:
        pages = int(m.group(2))
    return list(jobs.values()), pages


@register
class Icims(Checker):
    type = "icims"
    supports_detail = True

    def describe(self, s):
        return f"{s['portal'].rstrip('/')}/jobs/search?ss=1&in_iframe=1&pr=N"

    def fetch(self, http, s, ctx=None):
        base = s["portal"].rstrip("/")
        out: dict[str, Job] = {}
        page, pages = 0, None
        while True:
            params = {"ss": 1, "in_iframe": 1, "pr": page, **(s.get("params") or {})}
            html = http.get_text(base + "/jobs/search", params=params)
            jobs, n = parse_list(html, base)
            if pages is None:
                need(n is not None or jobs or "iCIMS" in html, f"icims:{base}: not an iCIMS job list")
                pages = n or 1
            new = [j for j in jobs if j.id not in out]
            for j in new:
                out[j.id] = j
            page += 1
            if page >= pages or not new or page > 100:
                break
        if pages and pages > 1:
            need(page >= pages, f"icims:{base}: stopped at page {page} of {pages}")
        return list(out.values())

    def detail(self, http, s, job):
        html = http.get_text(job.url, params={"in_iframe": 1})
        for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
            try:
                d = json.loads(m.group(1))
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                job.snippet = html_text(d.get("description")) or job.snippet
                job.posted = iso_date(d.get("datePosted")) or job.posted
                et = d.get("employmentType")
                job.employment_type = ", ".join(et) if isinstance(et, list) else (et or job.employment_type)
                break
        return job
