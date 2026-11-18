"""ServiceNow Service Portal career sites built on NewRocket's career app (Best Buy's jobs.bestbuy.com).

settings:
  host:   jobs.bestbuy.com
  portal: bby                                   the portal's path
  page:   all_jobs                              the portal page that lists every job
  widget: dd786d721b71b010b4c011f18c4bcb87      that page's job map and list widget
1. GET https://<host>/<portal>?id=<page>  (HTML, about 1 MB): the guest session's cookies and its token (g_ck), which
   the portal sends with every call it makes.
2. POST https://<host>/api/now/sp/widget/<widget>?id=<page>  {"action": "update_data", "options": {…, "filters": {},
   "limitResults": "getAll"}}  with X-UserToken: the call the page makes to list its jobs ("getAll" is the value it
   sends when the map is zoomed in) → {"result": {"data": {"total_count": N, "items": {"features": [{"properties":
   {auto_req_id, title, city, state, country, type, worker_type, category, sites, last_updated, …}}]}}}}
A job's page: https://<host>/<portal>?id=job_details&req_id=<auto_req_id>. robots.txt allows everything (2026-11-18).
The list is the site's whole list: on 2026-11-18 it held the 1,740 requisitions of the site's SEO sitemap, no more, no
fewer. `last_updated` is not a posting date and is not used. No job description is read.
"""
from __future__ import annotations

import re

from ..models import Job
from .base import Checker, check_total, need, register

TOKEN = re.compile(r"""g_ck\s*=\s*['"]([0-9a-f]{20,})['"]""")
OPTIONS = {"items_per_page": 20, "sort_val": "req_id_num", "lastLimit": 0, "currentPage": 0, "current_page": 0,
           "order": -1, "filters": {}, "sort": "req_id_num", "bby_loc_q": None, "limitResults": "getAll"}


@register
class ServiceNow(Checker):
    type = "servicenow"

    def describe(self, s):
        return f"POST https://{s['host']}/api/now/sp/widget/{s['widget']}?id={s['page']} (after the portal page)"

    def fetch(self, http, s, ctx=None):
        where = f"servicenow:{s['host']}"
        page = http.get(f"https://{s['host']}/{s['portal']}", params={"id": s["page"]}, headers={"Accept": "text/html"})
        m = TOKEN.search(page.text)
        need(m, f"{where}: no session token (g_ck) on the portal page")
        data = http.post_json(f"https://{s['host']}/api/now/sp/widget/{s['widget']}", params={"id": s["page"]},
                              json={"action": "update_data", "options": OPTIONS},
                              headers={"X-UserToken": m.group(1), "Accept": "application/json"})
        d = (data.get("result") or {}).get("data") if isinstance(data, dict) else None
        need(isinstance(d, dict) and isinstance(d.get("items"), dict), f"{where}: no job items in the widget's answer")
        feats = d["items"].get("features")
        need(isinstance(feats, list), f"{where}: the items are not a list of features")
        jobs: dict[str, Job] = {}
        for f in feats:
            p = f.get("properties") if isinstance(f, dict) else None
            need(isinstance(p, dict) and p.get("auto_req_id") and p.get("title"), f"{where}: a job without req id or title")
            rid = str(p["auto_req_id"])
            place = ", ".join(x for x in (p.get("city"), p.get("state"), p.get("country")) if x)
            kind = ", ".join(x for x in (p.get("type"), p.get("worker_type")) if x and x != "Regular")
            jobs.setdefault(rid, Job(id=rid, title=" ".join(str(p["title"]).split()), location=place,
                                     url=f"https://{s['host']}/{s['portal']}?id=job_details&req_id={rid}",
                                     department=p.get("category") or "", employment_type=kind))
        total = int(d["total_count"]) if str(d.get("total_count")).isdigit() else d.get("total_count")
        if ctx is not None:
            ctx.reported_total = total
        check_total(len(jobs), total, where, tolerance=0)
        return list(jobs.values())
