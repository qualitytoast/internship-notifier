"""Radancy TalentBrew career sites read from their sitemap (Intuit: jobs.intuit.com).

The underlying ATS has no public list, so the site's own sitemap is the complete feed: every job URL
  https://jobs.intuit.com/job/<city-slug>/<title-slug>/27595/<id>
Titles and cities come from the slugs; for new student-looking jobs the job page is read (JSON-LD JobPosting:
real title, datePosted, locations, description). /search-jobs/results (the AJAX pager) is robots-disallowed.

settings:
  sitemap_url: https://jobs.intuit.com/sitemap.xml
  org_id: 27595
  detail_limit: 40        job pages read per poll (new student-looking jobs only)
See discovery/notes/intuit.md.
"""
from __future__ import annotations

import json
import re

from ..adapters.base import Checker, html_text, iso_date, join_locations, need, register
from ..models import CheckerError, Job

STUDENTISH = re.compile(r"intern|co-?op|student|apprentic|campus|universit|graduate|summer|fall-20|spring-20|winter-20",
                        re.I)


def _words(slug: str) -> str:
    return re.sub(r"\s+", " ", slug.replace("-", " ")).strip().title()


@register
class TalentBrewSitemap(Checker):
    type = "talentbrew"
    supports_detail = True

    def describe(self, s):
        return f"GET {s['sitemap_url']} (job URLs) + JSON-LD of new student roles"

    def fetch(self, http, s, ctx=None):
        xml = http.get_text(s["sitemap_url"], timeout=60)
        host = re.escape(re.match(r"https?://[^/]+", s["sitemap_url"]).group(0))
        rx = re.compile(rf"<loc>\s*({host}/job/([^/<]+)/([^/<]+)/{s['org_id']}/(\d+))\s*</loc>")
        jobs: dict[str, Job] = {}
        for m in rx.finditer(xml):
            url, city, slug, jid = m.groups()
            jobs.setdefault(jid, Job(id=jid, title=_words(slug), location=_words(city), url=url))
        need(jobs, f"talentbrew:{s['sitemap_url']}: no job URLs in the sitemap")
        known = ctx.known if ctx is not None else frozenset()
        budget = int(s.get("detail_limit", 40))
        for j in jobs.values():
            if budget <= 0:
                break
            if j.id not in known and STUDENTISH.search(j.url):
                try:
                    self.detail(http, s, j)
                except CheckerError:
                    pass  # slug title/city still let the filters judge it
                budget -= 1
        return list(jobs.values())

    def detail(self, http, s, job):
        html = http.get_text(job.url)
        for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
            try:
                d = json.loads(m.group(1))
            except ValueError:
                continue
            for item in d if isinstance(d, list) else [d]:
                if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                    continue
                job.title = " ".join(str(item.get("title") or job.title).split())
                job.posted = iso_date(item.get("datePosted")) or job.posted
                job.snippet = html_text(item.get("description")) or job.snippet
                locs = []
                places = item.get("jobLocation") or []
                for loc in places if isinstance(places, list) else [places]:
                    a = (loc or {}).get("address") or {}
                    locs.append(", ".join(x for x in (a.get("addressLocality"), a.get("addressRegion"), a.get("addressCountry")) if x))
                if any(locs):
                    job.location = join_locations([x for x in locs if x])
                return job
        return job
