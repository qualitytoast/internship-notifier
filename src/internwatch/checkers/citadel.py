"""Citadel and Citadel Securities: the career sitemap of each WordPress site.

GET <base_url>/career-sitemap.xml   (Yoast sitemap of the "career" post type, advertised in robots.txt)
→ <urlset><url><loc>https://www.citadel.com/careers/details/<slug>/</loc>…
The listing and detail pages answer automated clients with an interactive challenge, so they are never
fetched (the links go in emails and open normally in your browser). Titles and a region hint come from the
slug; the slug words carry the job type ("intern", "phd-intern", "university-graduate"). There is no posting
date (lastmod is rewritten on every sync): first-seen is used. robots.txt asks for 10 s between requests,
and one request per poll is enough.

settings: base_url: https://www.citadel.com    (min_interval: 10)
See discovery/notes/citadel.md.

`citadel_programs`: the student programs, which are never job posts (Citadel Securities' Spark, Discover, Ignite).
GET <base_url>/page-sitemap.xml → every page one level below a program page is returned as a job
(…/programs-and-events/citadel-securities-spark/apply/ → id citadel-securities-spark/apply, title "Citadel
Securities Spark"): a program takes applications through such a page and drops it when it closes (Ignite, Oct 2026).
The page's lastmod is its posted date: on this sitemap it is real, not rewritten on every sync.
See discovery/notes/citadel-securities.md.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ..adapters.base import Checker, iso_date, need, register
from ..models import Job

NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
DUP = re.compile(r"-([2-9]|[1-9]\d)$")   # WordPress duplicate-slug suffix (-2 … -99), never a 4-digit year
SMALL = {"and", "of", "for", "the", "in", "to", "a", "an", "on", "with", "or"}
UPPER = {"us", "uk", "emea", "apac", "bs", "ms", "ui", "ux", "it", "hr", "ai", "ml", "fx", "etf", "ces", "gqs",
         "fpga", "sre", "otc", "llm", "api", "vp", "pm", "dmm", "mba", "kdb", "sdet"}
REGIONS = {"us": "United States", "usa": "United States", "europe": "Europe", "asia": "Asia", "emea": "EMEA",
           "apac": "APAC", "australia": "Australia", "americas": "Americas", "uk": "United Kingdom",
           "canada": "Canada", "india": "India"}
CITIES = ["new-york", "london", "hong-kong", "singapore", "miami", "chicago", "greenwich", "houston", "sydney",
          "tokyo", "dublin", "zurich", "paris", "amsterdam", "san-francisco", "boston", "toronto", "shanghai"]


def title_from_slug(slug: str) -> str:
    words = DUP.sub("", slug).split("-")
    out = []
    for i, w in enumerate(words):
        if w == "phd":
            out.append("PhD")
        elif w in UPPER:
            out.append(w.upper())
        elif w in SMALL and i:
            out.append(w)
        else:
            out.append(w.capitalize())
    return " ".join(out)


def region_hint(slug: str) -> str:
    s = DUP.sub("", slug)
    hits = [c.replace("-", " ").title() for c in CITIES if re.search(rf"(^|-){c}(-|$)", s)]
    words = s.split("-")
    for w in (words[-1], words[0]):
        if w in REGIONS and REGIONS[w] not in hits:
            hits.append(REGIONS[w])
    return "; ".join(hits)


@register
class CitadelSitemap(Checker):
    type = "citadel"

    def describe(self, s):
        return f"GET {s['base_url'].rstrip('/')}/career-sitemap.xml (job slugs)"

    def fetch(self, http, s, ctx=None):
        base = s["base_url"].rstrip("/")
        detail = re.compile(rf"^{re.escape(base)}/careers/details/([a-z0-9-]+)/?$")
        jobs: dict[str, Job] = {}
        for loc, _ in sitemap(http, base, "career"):
            m = detail.match(loc)
            if m:
                slug = m.group(1)
                jobs.setdefault(slug, Job(id=slug, title=title_from_slug(slug), location=region_hint(slug), url=loc))
        need(jobs, f"citadel:{base}: no job URLs in the career sitemap")
        return list(jobs.values())


@register
class CitadelPrograms(Checker):
    type = "citadel_programs"

    def describe(self, s):
        return f"GET {s['base_url'].rstrip('/')}/page-sitemap.xml (program application pages)"

    def fetch(self, http, s, ctx=None):
        base = s["base_url"].rstrip("/")
        root = f"{base}/careers/programs-and-events/"
        child = re.compile(rf"^{re.escape(root)}([a-z0-9-]+)/([a-z0-9-]+)/?$")
        pages = sitemap(http, base, "page")
        need(any(loc.startswith(root) for loc, _ in pages), f"citadel:{base}: the page sitemap lists no program pages")
        jobs: dict[str, Job] = {}
        for loc, lastmod in pages:
            m = child.match(loc)
            if m:  # no open program at all is a valid answer
                program, page = m.groups()
                jobs.setdefault(f"{program}/{page}", Job(
                    id=f"{program}/{page}", title=title_from_slug(program), url=loc, posted=iso_date(lastmod),
                    location=region_hint(page) or region_hint(program)))
        return list(jobs.values())


def sitemap(http, base: str, name: str) -> list[tuple[str, str]]:
    """(loc, lastmod) of every entry of the Yoast sitemap <base>/<name>-sitemap.xml and its split pages."""
    out: list[tuple[str, str]] = []
    pages = [f"{base}/{name}-sitemap.xml"]
    n = 0
    while pages and n < 20:
        body = http.get(pages.pop(0)).content
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            need(False, f"citadel:{base}: {name} sitemap is not XML (challenge page?) {body[:80]!r}")
        need(root.tag.endswith("urlset"), f"citadel:{base}: unexpected sitemap root {root.tag}")
        urls = root.findall("s:url", NS)
        out += [((u.findtext("s:loc", namespaces=NS) or "").strip(), (u.findtext("s:lastmod", namespaces=NS) or "").strip())
                for u in urls]
        n += 1
        if len(urls) >= 1000:  # Yoast splits at 1000 entries: career-sitemap2.xml, 3, …
            pages.append(f"{base}/{name}-sitemap{n + 1}.xml")
    return out
