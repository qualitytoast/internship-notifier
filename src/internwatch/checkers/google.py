"""Google careers: the official XML feed of every job (Google, YouTube, DeepMind).

GET https://www.google.com/about/careers/applications/jobs/feed.xml  (≈4.4 MB gzipped, If-Modified-Since → 304)
→ <jobs><updated/><job><jobid/><title/><url/><locations><location><city/><state/><country/></location>…
  <published/><description/><jobtype>INTERN|FULL_TIME|…</jobtype><employer/><languageCode/><categories/>…</job>…
The search pages only allow the first 20 results to robots (results?page= is disallowed), so the feed is
the complete source. Feed <url>s use the legacy careers.google.com host; links are rewritten to the
current page. See discovery/notes/google.md.
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET

from ..adapters.base import Checker, check_total, conditional_get, html_text, iso_date, need, register
from ..models import Job

FEED = "https://www.google.com/about/careers/applications/jobs/feed.xml"
OLD_PREFIX = "https://careers.google.com/jobs/results/"
NEW_PREFIX = "https://www.google.com/about/careers/applications/jobs/results/"


def _text(el, tag: str) -> str:
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def _location(loc) -> str:
    city, state, country = (_text(loc, t) for t in ("city", "state", "country"))
    if country in ("USA", "United States") or country.endswith(", USA"):
        country = "USA"
    parts = [p for p in (city, state, country) if p]
    return ", ".join(dict.fromkeys(parts))


def parse_feed(data: bytes) -> tuple[list[Job], str]:
    jobs, updated = [], ""
    for _, el in ET.iterparse(io.BytesIO(data), events=("end",)):
        if el.tag == "updated" and not updated:
            updated = (el.text or "").strip()
        if el.tag != "job":
            continue
        jid = _text(el, "jobid")
        need(jid and el.find("title") is not None, "google: <job> without jobid/title")
        url = _text(el, "url")
        if url.startswith(OLD_PREFIX):
            url = NEW_PREFIX + url[len(OLD_PREFIX):]
        locs = [_location(l) for l in el.iter("location")]
        cats = [c.text.strip() for c in el.iter("category") if c.text]
        employer = _text(el, "employer")
        jobs.append(Job(
            id=jid, title=_text(el, "title"), location="; ".join(l for l in locs if l), url=url or f"{NEW_PREFIX}{jid}-/",
            posted=iso_date(_text(el, "published")), snippet=html_text(_text(el, "description")),
            department=" / ".join([employer] + cats[:3]) if employer else " / ".join(cats[:3]),
            employment_type=_text(el, "jobtype"),
            extra={"language": _text(el, "languageCode"), "employer": employer},
        ))
        el.clear()
    return jobs, updated


@register
class Google(Checker):
    type = "google"

    def describe(self, s):
        return f"GET {FEED} (XML, all jobs)"

    @staticmethod
    def trim_fixture(exchanges: list[dict], keep: int = 400) -> None:
        """Keep the first `keep` <job>s of the recorded feed (the full feed is 22 MB)."""
        for e in exchanges:
            text = e.get("text", "")
            if "<jobs>" in text and text.count("<job>") > keep:
                cut = 0
                for _ in range(keep):
                    cut = text.index("</job>", cut) + len("</job>")
                e["text"] = text[:cut] + "\n</jobs>\n"

    def fetch(self, http, s, ctx=None):
        resp = conditional_get(http, s.get("feed", FEED), ctx, timeout=120)
        need(resp.content.lstrip()[:5] in (b"<?xml", b"<jobs"), f"google: feed is not XML ({resp.content[:60]!r})")
        jobs, updated = parse_feed(resp.content)
        need(updated, "google: feed has no <updated> timestamp")
        check_total(len({j.id for j in jobs}), len(jobs), "google", tolerance=0)
        return jobs
