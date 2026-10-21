"""SmartRecruiters, through the company's hosted career page (the official Posting API host,
api.smartrecruiters.com, disallows all crawlers in robots.txt, so it is never used).

settings: company: ServiceNow     (identifier in careers.smartrecruiters.com/<company>)
1. GET https://careers.smartrecruiters.com/<company>  → first group page (HTML): section.js-group[data-qty] with up
   to 9 li.opening-job each, and div.js-openings-load[data-groups-pages][data-more]
2. GET <data-more>?page=N for the other group pages (HTML fragments, 6 groups each)
3. GET <a.js-more data-more>?type=<data-type>&value=<data-value>&page=N for groups with more than 9 jobs (10 per page)
4. union with GET https://jobs.smartrecruiters.com/sr-jobs/search?limit=100&company=<company> (newest 100, JSON),
   which also catches postings dropped by the unstable ordering inside a group
Detail: GET https://jobs.smartrecruiters.com/<company>/<id>-<slug>  (schema.org microdata)
See discovery/notes/servicenow.md.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Job
from .base import Checker, html_text, iso_date, join_locations, need, register

HOSTED = "https://careers.smartrecruiters.com"
SEARCH = "https://jobs.smartrecruiters.com/sr-jobs/search"
ID_RE = re.compile(r"/(\d{6,})-")


def _jobs_in(node, group: str, out: dict) -> int:
    n = 0
    for a in node.select("li.opening-job a[href], a.js-job-ad-link[href]"):
        m = ID_RE.search(a["href"])
        if not m:
            continue
        jid = m.group(1)
        title_el = a.select_one("h4.job-title, .job-title")
        title = (title_el.get_text(" ", strip=True) if title_el else a.get_text(" ", strip=True))
        if jid in out:
            if group and group not in out[jid].location:
                out[jid].location = join_locations(out[jid].location, group)
        else:
            out[jid] = Job(id=jid, title=" ".join(title.split()), location=group, url=a["href"].split("?")[0])
        n += 1
    return n


@register
class SmartRecruiters(Checker):
    type = "smartrecruiters"
    supports_detail = True

    def describe(self, s):
        return f"{HOSTED}/{s['company']} (hosted career page) + {SEARCH}?company={s['company']}"

    def _groups(self, http, html: str, out: dict, where: str) -> tuple[int, int]:
        """Parse a page of groups; follow each group's 'more' pages. Returns (groups, sum of data-qty)."""
        soup = BeautifulSoup(html, "lxml")
        groups = qty_sum = 0
        for sec in soup.select("section.js-group"):
            groups += 1
            title = sec.select_one("header .opening-title, .opening-title")
            name = title.get_text(" ", strip=True) if title else ""
            qty = int(sec.get("data-qty") or 0)
            qty_sum += qty
            seen = _jobs_in(sec, name, out)
            more = sec.select_one("a.js-more[data-more]")
            page = 1
            while more is not None and seen < qty and page <= 60:
                frag = http.get_text(HOSTED + more["data-more"], params={
                    "type": more.get("data-type", "location"), "value": _unquote_once(more.get("data-value", "")),
                    "page": page})
                got = _jobs_in(BeautifulSoup(frag, "lxml"), name, out)
                if not got:
                    break
                seen += got
                page += 1
        return groups, qty_sum

    def fetch(self, http, s, ctx=None):
        company = s["company"]
        where = f"smartrecruiters:{company}"
        out: dict[str, Job] = {}
        html = http.get_text(f"{HOSTED}/{company}")
        soup = BeautifulSoup(html, "lxml")
        loader = soup.select_one("div.js-openings-load")
        need(loader is not None or soup.select("section.js-group") or "opening-job" in html,
             f"{where}: hosted career page has no job groups")
        groups, qty = self._groups(http, html, out, where)
        pages = int(loader.get("data-groups-pages") or 1) if loader is not None else 1
        more = loader.get("data-more") if loader is not None else None
        for page in range(1, pages if more else 1):
            g, q = self._groups(http, http.get_text(HOSTED + more, params={"page": page}), out, where)
            groups, qty = groups + g, qty + q
        found = self._search(http, company, out)
        if ctx is not None:
            ctx.reported_total = qty or found
        if qty:
            need(len(out) >= qty * 0.97 - 2, f"{where}: collected {len(out)} postings but the page lists {qty}")
        return list(out.values())

    def _search(self, http, company: str, out: dict) -> int | None:
        d = http.get_json(SEARCH, params={"limit": 100, "company": company})
        need(isinstance(d, dict) and isinstance(d.get("content"), list), f"smartrecruiters:{company}: bad search JSON")
        for it in d["content"]:
            jid = str(it.get("id") or "")
            if not jid:
                continue
            loc = it.get("location") or {}
            where = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)
            if loc.get("remote"):
                where = join_locations(where, "Remote")
            if jid in out:
                out[jid].posted = out[jid].posted or iso_date(it.get("releasedDate"))
            else:
                out[jid] = Job(id=jid, title=" ".join((it.get("name") or "").split()), location=where,
                               url=it.get("applyUrl") or f"https://jobs.smartrecruiters.com/{company}/{jid}",
                               posted=iso_date(it.get("releasedDate")))
        return d.get("totalFound")

    def detail(self, http, s, job):
        soup = BeautifulSoup(http.get_text(job.url), "lxml")
        et = soup.select_one("[itemprop=employmentType]")
        if et:
            job.employment_type = et.get_text(" ", strip=True)
        dp = soup.select_one("meta[itemprop=datePosted]")
        if dp and dp.get("content"):
            job.posted = iso_date(dp["content"]) or job.posted
        parts = [soup.select_one(f"[itemprop={k}]") for k in ("description", "responsibilities", "qualifications")]
        job.snippet = html_text(" ".join(str(p) for p in parts if p)) or job.snippet
        loc = [soup.select_one(f"meta[itemprop={k}]") for k in ("addressLocality", "addressRegion", "addressCountry")]
        loc_s = ", ".join(m["content"] for m in loc if m is not None and m.get("content"))
        if loc_s and loc_s not in job.location:
            job.location = join_locations(job.location, loc_s)
        return job


def _unquote_once(v: str) -> str:
    from urllib.parse import unquote
    return unquote(v)
