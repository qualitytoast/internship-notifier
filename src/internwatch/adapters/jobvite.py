"""Jobvite: the company's public XML job feed (every posting in one response).

settings:
  company_id: qKr9VfwZ      (the c= parameter of the company's Jobvite links)
  slug: nutanix             (for https://jobs.jobvite.com/<slug>/job/<id> links)
  job_url: https://careers.nutanix.com/en/jobs/{requisitionid}/{slug}/   (optional public link template)
GET https://app.jobvite.com/CompanyJobs/Xml.aspx?c=<company_id>
→ <result><job><id/><title/><requisitionid/><category/><jobtype/><location/><date/><detail-url/><description/>…
A requisition posted in several cities appears once per city: rows are merged by requisition id.
See discovery/notes/nutanix.md.
"""
from __future__ import annotations

import re

from lxml import etree

from ..models import Job
from .base import Checker, html_text, iso_date, join_locations, need, register

FEED = "https://app.jobvite.com/CompanyJobs/Xml.aspx"


def _slug(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (t or "").lower()).strip("-")


@register
class Jobvite(Checker):
    type = "jobvite"

    def describe(self, s):
        return f"{FEED}?c={s['company_id']}"

    def fetch(self, http, s, ctx=None):
        resp = http.get(FEED, params={"c": s["company_id"]}, timeout=120)
        try:
            root = etree.fromstring(resp.content, parser=etree.XMLParser(huge_tree=True, recover=True, resolve_entities=False,
                                                                         no_network=True))
        except etree.XMLSyntaxError as e:
            need(False, f"jobvite:{s['company_id']}: feed is not XML ({e})")
        need(root is not None and root.tag == "result", f"jobvite:{s['company_id']}: unexpected root element")
        jobs: dict[str, Job] = {}
        for el in root.iter("job"):
            def t(tag):
                x = el.find(tag)
                return (x.text or "").strip() if x is not None and x.text else ""
            row_id, req, title = t("id"), t("requisitionid"), t("title")
            need(row_id and title, f"jobvite:{s['company_id']}: job without id/title")
            key = req or row_id.split("-")[0]
            if key in jobs:
                jobs[key].location = join_locations(jobs[key].location.split("; "), t("location"))
                continue
            primary = row_id.split("-")[0]
            tmpl = s.get("job_url")
            url = (tmpl.format(requisitionid=key, id=primary, slug=_slug(title)) if tmpl
                   else f"https://jobs.jobvite.com/{s.get('slug', s['company_id'])}/job/{primary}")
            jobs[key] = Job(id=key, title=title, location=t("location"), url=url, posted=iso_date(t("date")),
                            snippet=html_text(t("description") or t("briefdescription")), department=t("category"),
                            employment_type=t("jobtype"), extra={"alt_ids": [primary]})
        return list(jobs.values())
