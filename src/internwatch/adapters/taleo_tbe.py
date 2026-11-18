"""Taleo Business Edition career sites: the site's own RSS feed lists every open job in one response (Costco's IT jobs).

settings:
  server: phf.tbe.taleo.net   (every Taleo Business Edition site there shares it: not named `host`, so it is never
                              a URL marker or a job system's identity; org and cws are, moves.system_key_v2)
  dc:   phf02          (the site's data center, the first part of its paths)
  org:  COSTCO
  cws:  41             (the career web site)
GET https://<server>/<dc>/ats/servlet/Rss?org=<org>&cws=<cws>
→ <rss><channel><item><title/><link/><description/><pubDate/><taleo:reqId/><taleo:location/><taleo:locationCountry/>
  <taleo:locationState/><taleo:locationCity/><taleo:department/></item>…
A job's page: https://<server>/<dc>/ats/careers/v2/viewRequisition?org=<org>&cws=<cws>&rid=<reqId> (the link SimplifyJobs
uses; a closed job's page says "This job has moved or is no longer available"). robots.txt answers 404 (no rules,
2026-11-18). Costco's feed listed 41 jobs on 2026-11-09 (25 Costco Digital Services interns) and 16 on 2026-11-18,
the same jobs its search pages list.
"""
from __future__ import annotations

from email.utils import parsedate_to_datetime

from lxml import etree

from ..models import Job
from .base import Checker, html_text, need, register

NS = "{urn:TBERss}"


def _date(text: str) -> str | None:
    try:
        return parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return None


@register
class TaleoTBE(Checker):
    type = "taleo_tbe"

    def describe(self, s):
        return f"GET https://{s['server']}/{s['dc']}/ats/servlet/Rss?org={s['org']}&cws={s['cws']}"

    def job_url(self, s, rid: str) -> str:
        return f"https://{s['server']}/{s['dc']}/ats/careers/v2/viewRequisition?org={s['org']}&cws={s['cws']}&rid={rid}"

    def fetch(self, http, s, ctx=None):
        where = f"taleo_tbe:{s['org']}/{s['cws']}"
        resp = http.get(f"https://{s['server']}/{s['dc']}/ats/servlet/Rss", params={"org": s["org"], "cws": s["cws"]})
        try:
            root = etree.fromstring(resp.content, parser=etree.XMLParser(recover=False, resolve_entities=False,
                                                                         no_network=True, huge_tree=True))
        except etree.XMLSyntaxError as e:
            need(False, f"{where}: the feed is not XML ({e})")
        need(root.tag == "rss" and root.find("channel") is not None, f"{where}: not an RSS feed")
        jobs: dict[str, Job] = {}
        for it in root.find("channel").iter("item"):
            def t(tag):
                x = it.find(tag)
                return (x.text or "").strip() if x is not None and x.text else ""
            rid, title = t(f"{NS}reqId"), t("title")
            need(rid and title, f"{where}: a job without reqId or title")
            place = t(f"{NS}location") or ", ".join(x for x in (t(f"{NS}locationCity"), t(f"{NS}locationState")) if x)
            country = t(f"{NS}locationCountry")
            if country and not place.endswith(country):
                place = f"{place}, {country}" if place else country
            jobs.setdefault(rid, Job(id=rid, title=title, location=place, url=self.job_url(s, rid),
                                     posted=_date(t("pubDate")), snippet=html_text(t("description")),
                                     department=t(f"{NS}department")))
        return list(jobs.values())
