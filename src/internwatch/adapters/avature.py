r"""Avature career portals (careers.twosigma.com, bloomberg.avature.net, synopsys.avature.net), server-rendered HTML.

settings:
  list_url:  https://bloomberg.avature.net/careers/SearchJobs/   (the portal's job list, no filters)
  page_size: 12          cards per page the portal really serves (jobRecordsPerPage is ignored by these portals)
  fields:    how to read each card's info, either
               a list of names for the card's span.paragraph_inner-span values in order (Two Sigma:
               [location, department, employment_type]), or
               a mapping name → CSS selector (Synopsys: {employment_type: .list-item-hireType, posted: .list-item-posted})
             default: {location: .list-item-location}
  total_regex:        regex whose group 1 is the portal's total (e.g. 'aria-label="(\d+) results"')
  newest_first_query: query string that sorts newest first (used by quick scans of big portals)
List:   GET <list_url>?jobOffset=N → article.article--result cards linking to …/JobDetail/<slug>/<id>
Detail: GET the job page → description, and City / State / Country fields when the card has no location
See discovery/notes/two-sigma.md, bloomberg.md, synopsys.md.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, urljoin

from bs4 import BeautifulSoup

from ..models import Job
from .base import Checker, check_total, html_text, iso_date, join_locations, need, register

DETAIL_HREF = re.compile(r"/JobDetail/(?:[^/?#]+/)?(\d+)(?:[/?#]|$)")
DEFAULT_FIELDS = {"location": ".list-item-location"}


def parse_list(html: str, base: str, fields) -> list[Job]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("article.article--result") or soup.select("[class*='article--result']")
    if not cards:  # other templates: one block per JobDetail link
        cards = [a.find_parent(["li", "article", "div"]) or a for a in soup.find_all("a", href=DETAIL_HREF)]
    jobs: dict[str, Job] = {}
    for card in cards:
        a = card if getattr(card, "name", "") == "a" else (
            card.select_one("h3 a[href]") or card.find("a", href=DETAIL_HREF))
        if a is None or not DETAIL_HREF.search(a.get("href", "")):
            continue
        jid = DETAIL_HREF.search(a["href"]).group(1)
        if jid in jobs:
            continue
        if isinstance(fields, dict):
            info = {}
            for name, sel in fields.items():
                el = card.select_one(sel)
                if el is not None:
                    info[name] = el.get_text(" ", strip=True)
        else:
            spans = [s.get_text(" ", strip=True) for s in card.select("span.paragraph_inner-span")]
            info = dict(zip(fields, [x for x in spans if x]))
        posted = re.sub(r"^\s*posted\s*:?\s*", "", info.get("posted", ""), flags=re.I)
        jobs[jid] = Job(id=jid, title=a.get_text(" ", strip=True), url=urljoin(base, a["href"]),
                        location=info.get("location", ""), department=info.get("department", ""),
                        employment_type=info.get("employment_type", ""), posted=iso_date(posted))
    return list(jobs.values())


@register
class Avature(Checker):
    type = "avature"
    supports_detail = True
    supports_quick = True

    def describe(self, s):
        return f"GET {s['list_url']}?jobOffset=N (HTML, {s.get('page_size', 10)} per page)"

    def fetch(self, http, s, ctx=None):
        url, size = s["list_url"], int(s.get("page_size", 10))
        fields = s.get("fields") or DEFAULT_FIELDS
        quick = ctx is not None and ctx.quick and bool(s.get("newest_first_query"))
        base_params = dict(parse_qsl(s["newest_first_query"])) if quick else {}
        total_rx = re.compile(s["total_regex"]) if s.get("total_regex") else None
        out: dict[str, Job] = {}
        offset, pages, total = 0, 0, None
        while True:
            params = {**(s.get("params") or {}), **base_params}
            if offset:
                params["jobOffset"] = offset
            html = http.get_text(url, params=params or None)
            jobs = parse_list(html, url, fields)
            if pages == 0:
                need(jobs or "JobDetail" in html or "article--result" in html or re.search(r"no (results|jobs)", html, re.I),
                     f"avature:{url}: page has no job cards")
                if total_rx is not None:
                    m = total_rx.search(html)
                    need(m, f"avature:{url}: total not found on the page (total_regex)")
                    total = int(m.group(1).replace(",", ""))
            new = [j for j in jobs if j.id not in out]
            for j in new:
                out[j.id] = j
            pages += 1
            offset += size
            if len(jobs) < size or not new or pages > 400:
                break
            if total is not None and len(out) >= total:
                break
            if quick and ctx.page_is_old([j.id for j in jobs], key="list"):
                break
        if ctx is not None and total is not None:
            ctx.reported_total = total
        if not quick and total is not None:
            check_total(len(out), total, f"avature:{url}")
        return list(out.values())

    def detail(self, http, s, job):
        html = http.get_text(job.url)
        for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
            try:
                d = json.loads(m.group(1))
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                job.snippet = html_text(d.get("description")) or job.snippet
                job.posted = iso_date(d.get("datePosted")) or job.posted
        soup = BeautifulSoup(html, "lxml")
        labels = {}
        for f in soup.select(".article__content__view__field"):
            lab = f.select_one(".article__content__view__field__label")
            val = f.select_one(".article__content__view__field__value")
            if lab and val:
                labels[lab.get_text(" ", strip=True).rstrip(":").lower()] = val.get_text(" ", strip=True)
        loc = labels.get("location") or ", ".join(x for x in (labels.get("city"), labels.get("state/province") or
                                                               labels.get("state"), labels.get("country")) if x)
        if loc and not job.location:
            job.location = loc
        if not job.department:
            job.department = labels.get("job category") or labels.get("business area") or ""
        if not job.snippet:
            body = soup.select_one(".article__content, .job-description, main") or soup
            job.snippet = body.get_text(" ", strip=True)[:4000]
        return job
