"""Radancy TalentBrew career sites read from their sitemap (Intuit: jobs.intuit.com).

The underlying ATS has no public list, so the site's own sitemap is the complete feed: every job URL
  https://jobs.intuit.com/job/<city-slug>/<title-slug>/27595/<id>
Titles and cities come from the slugs; for new student-looking jobs the job page is read (JSON-LD JobPosting:
real title, datePosted, locations, description). /search-jobs/results (the AJAX pager) is robots-disallowed.

settings:
  sitemap_url: https://jobs.intuit.com/sitemap.xml
  org_id: 27595
  detail_limit: 40        job pages read per poll (new student-looking jobs only)
  max_sitemap_age_days: 3 every <lastmod> is the sitemap's build time: older than this, the site may have stopped
                          rebuilding it, and the poll is reported degraded (its jobs are still read)
See discovery/notes/intuit.md.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone

from ..adapters.base import Checker, html_text, iso_date, join_locations, need, register
from ..models import CheckerError, Job

STUDENTISH = re.compile(r"intern|co-?op|student|apprentic|campus|universit|graduate|summer|fall-20|spring-20|winter-20",
                        re.I)
LASTMOD_RE = re.compile(r"<lastmod>\s*([^<\s]+)\s*</lastmod>")


def _words(slug: str) -> str:
    return re.sub(r"\s+", " ", slug.replace("-", " ")).strip().title()


def utc_today() -> date:
    """A function so tests can pin the date while a recorded sitemap ages."""
    return datetime.now(timezone.utc).date()


def sitemap_age_days(xml: str, today: date) -> int | None:
    """Days since the newest <lastmod> in the sitemap (None when it has none)."""
    stamps = []
    for value in LASTMOD_RE.findall(xml):
        try:
            stamps.append(date.fromisoformat(iso_date(value) or ""))
        except ValueError:
            continue
    return (today - max(stamps)).days if stamps else None


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
        age, limit = sitemap_age_days(xml, utc_today()), int(s.get("max_sitemap_age_days", 3))
        if age is not None and age > limit and ctx is not None:
            ctx.degraded = (f"talentbrew:{s['sitemap_url']}: the newest <lastmod> is {age} days old (limit {limit}); "
                            "the sitemap may have stopped updating, so new jobs could be missing from it")
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
                places = item.get("jobLocation") or []
                locs = [_place_text(p) for p in (places if isinstance(places, list) else [places])]
                if any(locs):
                    job.location = join_locations([x for x in locs if x])
                return job
        return job
