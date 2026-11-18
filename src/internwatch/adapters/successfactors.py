"""SAP SuccessFactors career sites (Recruiting Marketing), e.g. jobs.netapp.com, careers.paramount.com, careers.qorvo.com.

settings:
  host: jobs.netapp.com
GET https://<host>/search/?q=&sortColumn=referencedate&sortDirection=desc&startrow=N   (HTML, 25 jobs a page, newest
    first; "Results 1 – 25 of 332" or "1 – 25 of 199 Jobs"). A job's page is /job/<slug>/<id>/. Two layouts:
    a table (tr.data-row: title, location, and on some sites department) and tiles (li.job-tile: title and labeled
    fields such as Location, Date, Job Function). Every row links its job twice (desktop and phone).
Detail: GET https://<host>/job/<slug>/<id>/ → itemprop title, datePosted ("Mon Nov 16 08:00:00 UTC 2026"), description.
robots.txt (all three, 2026-11-18) disallows /services/ (the RSS feed) and allows /search/ and /job/.
Stage 1 (2026-11-09): NetApp 320 jobs, Paramount 223, Qorvo 8, each the site's own reported total.
"""
from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from ..locations import COUNTRY_NAMES, OTHER_WORDS
from ..models import Job
from .base import Checker, check_total_soft, html_text, iso_date, need, register

PAGE = 25
MORE = re.compile(r"\s*\+\s*(\d+)\s+more\W*$", re.I)
CODE = re.compile(r"[A-Z]{2}")
# a country code's name, so "Dusseldorf, DE" can't read as Delaware
COUNTRY = {cc: ws[0].title() for cc, ws in OTHER_WORDS.items() if ws and ws[0] in COUNTRY_NAMES} | {"CA": "Canada"}
JOB_HREF = re.compile(r"/job/[^/?#]+/(\d+)/?")
TOTAL = (re.compile(r"Results\s*<b>[^<]*</b>\s*of\s*<b>\s*([\d,]+)"), re.compile(r"\bof\s+([\d,]+)\s+Jobs\b"))
DEPARTMENT_LABELS = {"department", "job function", "function", "category"}


def posted_date(text: str | None) -> str | None:
    """The job page's datePosted ("Mon Nov 16 08:00:00 UTC 2026") or a tile's date ("Nov 18, 2026") → YYYY-MM-DD."""
    t = (text or "").strip()
    try:
        return datetime.strptime(t, "%a %b %d %H:%M:%S UTC %Y").date().isoformat()
    except ValueError:
        return iso_date(t)


def place(text: str) -> str:
    """A place as these sites write it, "City, [State,] country code, postal code", for the filters: the postal code is
    dropped, and a country code with no state before it is written out ("Dusseldorf, DE, 40472" → "Dusseldorf,
    Germany": a US place always has its state, and DE, IN, IL, GA … are also state codes). A list row's "+1 more…"
    (the job's other places are on its page) stays as "+1 more", which the filters can't place: unsure, not rejected."""
    t = " ".join((text or "").split())
    more = MORE.search(t)
    parts = [p.strip() for p in MORE.sub("", t).split(",") if p.strip()]
    if len(parts) > 1 and re.search(r"\d", parts[-1]) and not CODE.fullmatch(parts[-1]):
        parts = parts[:-1]
    if len(parts) <= 2 and parts and CODE.fullmatch(parts[-1]) and parts[-1] != "US":
        parts[-1] = COUNTRY.get(parts[-1], parts[-1])
    out = ", ".join(parts)
    return f"{out}; +{more.group(1)} more" if more and out else out


def _total(html: str) -> int | None:
    for rx in TOTAL:
        m = rx.search(html)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


def _text(el) -> str:
    return el.get_text(" ", strip=True) if el is not None else ""


def _rows(host: str, html: str) -> list[Job]:
    """The jobs of one search page, in its order, each once."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: dict[str, Job] = {}
    for box in soup.select("tr.data-row, li.job-tile"):
        a = box.select_one("a.jobTitle-link[href]")
        m = JOB_HREF.search(a["href"]) if a else None
        if not m or m.group(1) in jobs:
            continue
        path = a["href"].split("?")[0].split("#")[0]
        job = Job(id=m.group(1), title=_text(a), url=f"https://{host}{path}")
        if box.name == "tr":  # table layout: fixed columns
            job.location = place(_text(box.select_one("td.colLocation .jobLocation") or box.select_one(".jobLocation")))
            job.department = _text(box.select_one(".jobDepartment"))
        else:  # tiles: one labeled field each (the desktop copy)
            for f in box.select(".sub-section-desktop .section-field") or box.select(".section-field"):
                label = _text(f.select_one(".section-label")).lower()
                value = _text(f.find("div"))
                if "location" in f.get("class", []) or label == "location":
                    job.location = job.location or place(value)
                elif "date" in f.get("class", []) or label == "date":
                    job.posted = job.posted or posted_date(value)
                elif label in DEPARTMENT_LABELS:
                    job.department = job.department or value
        jobs[job.id] = job
    return list(jobs.values())


@register
class SuccessFactors(Checker):
    type = "successfactors"
    supports_detail = True

    def describe(self, s):
        return f"GET https://{s['host']}/search/?q=&sortColumn=referencedate&sortDirection=desc (HTML, 25 a page)"

    def fetch(self, http, s, ctx=None):
        host, where = s["host"], f"successfactors:{s['host']}"
        jobs: dict[str, Job] = {}
        start, total = 0, None
        while True:
            html = http.get(f"https://{host}/search/", params={"q": "", "sortColumn": "referencedate",
                                                               "sortDirection": "desc", "startrow": start},
                            headers={"Accept": "text/html"}).text
            if total is None:
                total = _total(html)
                need(total is not None, f"{where}: no job total on the search page (page format changed?)")
            page = _rows(host, html)
            # a first page without jobs while the total says there are some: the page changed. A later one ends the
            # walk, and a walk short of the total keeps its jobs and is marked degraded (check_total_soft)
            need(page or start or total == 0, f"{where}: no jobs on the first search page of {total} (page format changed?)")
            added = [j for j in page if j.id not in jobs]
            for j in added:
                jobs[j.id] = j
            start += PAGE
            if not added or start >= total:
                break
            need(start <= 20000, f"{where}: runaway pagination")
        if ctx is not None:
            ctx.reported_total = total
        check_total_soft(len(jobs), total, where, ctx)
        return list(jobs.values())

    def detail(self, http, s, job):
        soup = BeautifulSoup(http.get(job.url, headers={"Accept": "text/html"}).text, "html.parser")
        date = soup.select_one("[itemprop=datePosted]")
        if date is not None:
            job.posted = posted_date(date.get("content") or _text(date)) or job.posted
        job.snippet = html_text(str(soup.select_one("[itemprop=description]") or "")) or job.snippet
        places = [place(_text(x)) for x in soup.select(".jobGeoLocation")]  # every place, where the list said "+1 more"
        places = list(dict.fromkeys(p for p in places if p))
        if places:
            job.location = "; ".join(places)
        return job
