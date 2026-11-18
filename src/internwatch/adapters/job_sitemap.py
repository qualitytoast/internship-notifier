"""A site whose job list a script can't read but whose sitemap lists every job page, with the title in its address
(Sandisk's Avature site draws its list in the browser; every ADP page but its sitemap refuses scripts).

settings:
  sitemap: https://avature.sandisk.com/Careers/sitemap.xml
  job_url: '/Careers/JobDetail/(?P<slug>[^/]+)/(?P<id>\\d+)$'   a regex on each <loc>: the job's id and title slug
  job_page: avature    optional: how a new student role's own page is read (`avature`: its JobPosting JSON-LD title
                       and date, and its City / State / Country/Region, Business Function and Employment Type fields)
GET <sitemap> → <urlset><url><loc>…</loc><lastmod>…</lastmod></url>…  Every address matching job_url is a job: its id,
and a title from its slug ("Summer-2027-Intern-FPG-T-I-US" → "Summer 2027 Intern FPG T I US"). A job listed under
several addresses (ADP lists each in about 20 languages; job_url takes the English one) is one job. <lastmod> is not
a posting date (ADP's are months old for new jobs) and is not used. Without `job_page` a job has no place: the filters
mark such a role unsure rather than reject it.
"""
from __future__ import annotations

import json
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

from ..models import Job
from .base import Checker, html_text, iso_date, join_locations, need, register

LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


def title_of(slug: str) -> str:
    return " ".join(unquote(slug).replace("-", " ").replace("_", " ").split())


@register
class JobSitemap(Checker):
    type = "job_sitemap"
    supports_detail = True  # a site without `job_page` returns the job as it is, with no request

    def describe(self, s):
        return f"GET {s['sitemap']} (job pages{', each new student role read from its page' if s.get('job_page') else ''})"

    def fetch(self, http, s, ctx=None):
        where = f"job_sitemap:{s['sitemap']}"
        text = http.get(s["sitemap"], headers={"Accept": "application/xml"}).text
        need("<urlset" in text[:2000], f"{where}: not a sitemap of pages")
        rx = re.compile(s["job_url"])
        jobs: dict[str, Job] = {}
        for url in LOC.findall(text):
            m = rx.search(url)
            if m and m.group("id") not in jobs:
                jobs[m.group("id")] = Job(id=m.group("id"), title=title_of(m.group("slug")), url=url)
        need(jobs or "<url>" not in text, f"{where}: no address matches job_url (page addresses changed?)")
        return list(jobs.values())

    def detail(self, http, s, job):
        if s.get("job_page") != "avature":
            return job
        soup = BeautifulSoup(http.get(job.url, headers={"Accept": "text/html"}).text, "html.parser")
        for tag in soup.select('script[type="application/ld+json"]'):
            try:
                d = json.loads(tag.string or "")
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                job.title = " ".join(str(d.get("title") or "").split()) or job.title
                job.posted = iso_date(d.get("datePosted")) or job.posted
        fields, text = {}, []
        for f in soup.select(".article__content__view__field"):
            label = f.select_one(".article__content__view__field__label")
            value = f.select_one(".article__content__view__field__value") or f
            if label is not None:
                fields[label.get_text(" ", strip=True).lower()] = value.get_text(" ", strip=True)
            else:
                text.append(str(value))
        place = join_locations(", ".join(x for x in (fields.get("city"), fields.get("state"),
                                                       fields.get("country/region")) if x))
        job.location = place or job.location
        job.department = fields.get("business function") or job.department
        job.employment_type = fields.get("employment type") or job.employment_type
        job.snippet = html_text(" ".join(text)) or job.snippet
        return job
