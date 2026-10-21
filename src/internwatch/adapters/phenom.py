"""Phenom People career sites (careers.brevanhoward.com, careers.adobe.com, www.yelp.careers, …).

settings:
  base_url:  https://careers.brevanhoward.com
  ref_num:   BHABHAGB                 (the site's refNum, in the page source: phApp.ddo / "refNum")
  lang:      en_gb                    (site locale; default en_us)
  country:   gb                       (default us)
  site_type: external                 (default)
  page_name: search-results           (default)
  job_path:  /gb/en/job/{jobId}/{slug}   (public job page; default /<country>/<lang2>/job/{jobId}/{slug})
  page_id, all_fields: optional, as the site's own search request sends them (some sites need them)
List:   POST <base_url>/widgets {"ddoKey": "refineSearch", "from": N, "size": 100, …}
        → refineSearch.totalHits, refineSearch.data.jobs[]
Detail: the job page embeds phApp.ddo = {...}; jobDetail.data.job.description holds the full HTML
The default (relevance) order is not stable between calls, so paging can skip jobs (Adobe: 238 unique of 300
at size 100). The adapter therefore reads everything in ONE call (size ≥ totalHits) and checks the count.
  page_size: 1000      size of that call (raised to totalHits automatically when the site is bigger)
  id_field: jobSeqNo   use when jobId repeats across sibling postings (Snowflake); default jobId
"""
from __future__ import annotations

import json
import re

from ..models import Job
from .base import Checker, check_total, html_text, iso_date, join_locations, need, register, report_skipped



def slugify(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", title or "").strip("-")


@register
class Phenom(Checker):
    type = "phenom"
    supports_detail = True

    def describe(self, s):
        return f"POST {s['base_url'].rstrip('/')}/widgets (refineSearch, refNum {s['ref_num']})"

    def _body(self, s, start: int, size: int) -> dict:
        lang = s.get("lang", "en_us")
        return {"lang": lang, "deviceType": "desktop", "country": s.get("country", "us"),
                "pageName": s.get("page_name", "search-results"), "ddoKey": "refineSearch", "from": start,
                "size": size, "jobs": True, "counts": bool(s.get("all_fields")), "all_fields": s.get("all_fields", []),
                "selected_fields": s.get("selected_fields", {}),
                "keywords": "", "global": True, "sortBy": "", "subsearch": "", "clearAll": False,
                "jdsource": "facets", "isSliderEnable": False, "siteType": s.get("site_type", "external"),
                "refNum": s["ref_num"], **({"pageId": s["page_id"]} if s.get("page_id") else {})}

    def job_url(self, s, j: dict) -> str:
        lang = s.get("lang", "en_us")
        default = f"/{s.get('country', 'us')}/{lang.split('_')[0]}/job/{{jobId}}/{{slug}}"
        path = s.get("job_path", default).format(jobId=j.get("jobId") or j.get("reqId"), slug=slugify(j.get("title", "")),
                                                 jobSeqNo=j.get("jobSeqNo", ""))
        return s["base_url"].rstrip("/") + path

    def _call(self, http, s, size: int) -> tuple[int, list]:
        url = s["base_url"].rstrip("/") + "/widgets"
        where = f"phenom:{s['ref_num']}"
        data = http.post_json(url, json=self._body(s, 0, size),
                              headers={"Content-Type": "application/json", "Accept": "application/json, text/plain, */*"})
        rs = data.get("refineSearch") if isinstance(data, dict) else None
        need(isinstance(rs, dict), f"{where}: no refineSearch in response (keys {list(data)[:8] if isinstance(data, dict) else type(data)})")
        total = rs.get("totalHits")
        need(isinstance(total, int), f"{where}: no totalHits")
        items = (rs.get("data") or {}).get("jobs")
        need(isinstance(items, list), f"{where}: refineSearch.data.jobs missing")
        return total, items

    def fetch(self, http, s, ctx=None):
        where = f"phenom:{s['ref_num']}"
        size = int(s.get("page_size", 1000))
        total, items = self._call(http, s, size)
        if total > len(items) and total > size:
            total, items = self._call(http, s, total + 20)  # one call for everything: paging is unstable
        id_field = s.get("id_field", "jobId")
        seen: dict[str, Job] = {}
        bad = 0
        for j in items:
            jid = isinstance(j, dict) and (j.get(id_field) or j.get("jobSeqNo") or j.get("jobId") or j.get("reqId"))
            if not (jid and "title" in j):
                bad += 1  # a posting caught mid-edit: skipped, and reported below
                continue
            locs = j.get("multi_location") or [j.get("location") or j.get("cityStateCountry")]
            seen.setdefault(str(jid), Job(
                id=str(jid),
                title=j.get("title") or "",
                location=join_locations(locs),
                url=self.job_url(s, j),
                posted=iso_date(j.get("postedDate") or j.get("dateCreated")),
                snippet=j.get("descriptionTeaser") or "",
                department=j.get("category") or "",
                employment_type=" ".join(x for x in (j.get("type"), j.get("timeType")) if x),
                extra={"alt_ids": [x for x in (j.get("reqId"), j.get("jobSeqNo"), j.get("jobId")) if x and x != jid]},
            ))
        if ctx is not None:
            ctx.reported_total = total
        check_total(len(seen) + bad, total, where)
        report_skipped(ctx, bad, len(seen), f"{where}: skipped {bad} jobs without id/title")
        return list(seen.values())

    def detail(self, http, s, job):
        html = http.get_text(job.url)
        i = html.find("phApp.ddo = ")
        if i < 0:
            return job
        try:
            ddo, _ = json.JSONDecoder().raw_decode(html, i + len("phApp.ddo = "))
        except ValueError:
            return job
        d = ((ddo.get("jobDetail") or {}).get("data") or {}).get("job") or {}
        if d.get("description"):
            job.snippet = html_text(d["description"])
        if d.get("jobFamily") and not job.department:
            job.department = d["jobFamily"]
        return job
