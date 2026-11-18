"""Oleeo (tal.net) campus job boards: the programs and events of Bank of America's and Morgan Stanley's campus sites.

settings:
  host:  bankcampuscareers.tal.net
  feeds: [1, 2, 5, 6]     job boards read from their Atom feeds (Bank of America: Global Programs, Campus Events,
                          Japan Programs, Japan Events)
  pages: [/vx/lang-en-GB/mobile-0/brand-2/candidate/jobboard/vacancy/1/adv/]   job boards read from their HTML pages,
                          50 a page (?start=50 …), for a site whose feeds are off (Morgan Stanley's answer 404)
GET https://<host>/vx/mobile-0/candidate/jobboard/vacancy/<n>/feed → Atom entries: link …/opp/<id>-<slug>/en-GB,
    title, published, and a content block of "Label:value" lines (Title, City, Country, Program closing date or Event
    Date, Program description or Event description).
A page lists tr.details_row (data-oppid, data-title), the opportunity's link and its city.
robots.txt (both sites, 2026-11-18) allows these addresses for every agent and asks for Crawl-delay: 10, which the
client keeps (a board a request: Bank of America 40 s, Morgan Stanley 20 s). The banks' summer programs are only here,
not on their Workday sites. Stage 1 (2026-11-09): Bank of America 29 programs and events, Morgan Stanley 72 programs;
2026-11-18: 20 and 68.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup
from lxml import etree

from ..models import Job
from .base import Checker, html_text, iso_date, need, register

ATOM = "{http://www.w3.org/2005/Atom}"
OPP = re.compile(r"/opp/(\d+)-")
PAGE = 50


def _fields(content) -> dict[str, str]:
    """The "Label:value" lines of a feed entry's content."""
    text = etree.tostring(content, encoding="unicode", method="html") if content is not None else ""
    out = {}
    for line in re.split(r"<br\s*/?>", text):
        label, sep, value = html_text(line).partition(":")
        if sep and label and label not in out:
            out[label.strip().lower()] = value.strip()
    return out


@register
class Oleeo(Checker):
    type = "oleeo"

    def describe(self, s):
        boards = [f"https://{s['host']}/vx/mobile-0/candidate/jobboard/vacancy/{n}/feed" for n in s.get("feeds") or []]
        boards += [f"https://{s['host']}{p}" for p in s.get("pages") or []]
        return "GET " + " + ".join(boards)

    def fetch(self, http, s, ctx=None):
        need(s.get("feeds") or s.get("pages"), f"oleeo:{s['host']}: no feeds or pages configured")
        jobs: dict[str, Job] = {}
        for n in s.get("feeds") or []:
            for j in self._feed(http, s, n):
                jobs.setdefault(j.id, j)
        for path in s.get("pages") or []:
            for j in self._pages(http, s, path):
                jobs.setdefault(j.id, j)
        return list(jobs.values())

    def _feed(self, http, s, n) -> list[Job]:
        where = f"oleeo:{s['host']} board {n}"
        resp = http.get(f"https://{s['host']}/vx/mobile-0/candidate/jobboard/vacancy/{n}/feed",
                        headers={"Accept": "application/atom+xml"})
        try:
            root = etree.fromstring(resp.content, parser=etree.XMLParser(resolve_entities=False, no_network=True))
        except etree.XMLSyntaxError as e:
            need(False, f"{where}: the feed is not XML ({e})")
        need(root.tag == f"{ATOM}feed", f"{where}: not an Atom feed")
        out = []
        for e in root.iter(f"{ATOM}entry"):
            link = e.find(f"{ATOM}link[@rel='alternate']")
            url = (link.get("href") if link is not None else "") or (e.findtext(f"{ATOM}id") or "")
            m = OPP.search(url)
            title = (e.findtext(f"{ATOM}title") or "").strip()
            need(m and title, f"{where}: an entry without an opportunity id or title")
            f = _fields(e.find(f"{ATOM}content"))
            place = ", ".join(x for x in (f.get("city"), f.get("country")) if x)
            out.append(Job(id=m.group(1), title=title, location=place, url=url,
                           posted=iso_date(e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated")),
                           snippet=html_text(f.get("program description") or f.get("event description") or ""),
                           department=f.get("line of business") or f.get("program (event)") or ""))
        return out

    def _pages(self, http, s, path) -> list[Job]:
        where = f"oleeo:{s['host']}{path}"
        out: dict[str, Job] = {}
        start = 0
        while True:
            html = http.get(f"https://{s['host']}{path}", params={"start": start} if start else None,
                            headers={"Accept": "text/html"}).text
            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select("tr.details_row[data-oppid]")
            need(rows or start or "details_row" not in html, f"{where}: rows without opportunity ids")
            added = 0
            for row in rows:
                a = row.select_one("a[href*='/opp/']")
                title = " ".join((row.get("data-title") or (a.get_text(" ") if a else "")).split())
                need(a is not None and title, f"{where}: a row without its link or title")
                cells = row.find_all("td")
                place = " ".join(cells[1].get_text(" ").split()) if len(cells) > 1 else ""
                if row["data-oppid"] not in out:
                    out[row["data-oppid"]] = Job(id=row["data-oppid"], title=title, location=place, url=a["href"])
                    added += 1
            start += PAGE
            if not added or len(rows) < PAGE or f"start={start}" not in html:
                break
            need(start <= 2000, f"{where}: runaway pagination")
        return list(out.values())
