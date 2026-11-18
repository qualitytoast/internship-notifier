"""iCIMS "Jibe" career sites (careers.docusign.com, careers.amd.com, careers.sig.com, jobs.booking.com).

settings:
  host: careers.docusign.com
  use_employment_type: true   trust the site's employment_type (INTERN) as a student marker. Tenant-dependent:
                              SIG tags experienced roles INTERN too, so it is off there and titles decide.
  queries: [{categories: "A|B"}, {keywords: intern}]   optional: read only these listings, each to its end, and merge
                              them (a giant site's student slice: Costco's 19,000 jobs are 17,400 warehouse and 960
                              depot jobs; its other categories and an "intern" search hold the rest). Without it the
                              whole site is read.
GET https://<host>/api/jobs?page=N&limit=100&internal=false   (page is 1-based, limit ≤ 100)
→ {"totalCount": N, "jobs": [{"data": {slug, req_id, title, full_location, city, state, country, posted_date,
     employment_type, categories[{name}], description, meta_data{canonical_url}}}]}
Never send internal=true (adds internal-only postings). See discovery/notes/docusign.md.
"""
from __future__ import annotations

import json

from ..models import Job
from .base import Checker, check_total, html_text, iso_date, need, need_list, register, report_skipped

PAGE = 100


@register
class Jibe(Checker):
    type = "jibe"

    def describe(self, s):
        return f"GET https://{s['host']}/api/jobs?page=N&limit={PAGE}&internal=false"

    def fetch(self, http, s, ctx=None):
        url = f"https://{s['host']}/api/jobs"
        where = f"jibe:{s['host']}"
        if s.get("queries"):  # a giant site's student slice: each query read to its end, the jobs merged
            out: dict[str, Job] = {}
            bad = 0
            for q in s["queries"]:
                got, total, skipped = self._walk(http, s, url, f"{where} {json.dumps(q, sort_keys=True)}",
                                                 {**(s.get("params") or {}), **q})
                check_total(len(got) + skipped, total, f"{where} {json.dumps(q, sort_keys=True)}")
                for jid, job in got.items():
                    out.setdefault(jid, job)
                bad += skipped
            report_skipped(ctx, bad, len(out), f"{where}: skipped {bad} jobs without slug/title")
            return list(out.values())
        out, total, bad = self._walk(http, s, url, where, s.get("params") or {})
        if ctx is not None:
            ctx.reported_total = total
        check_total(len(out) + bad, total, where)
        report_skipped(ctx, bad, len(out), f"{where}: skipped {bad} jobs without slug/title")
        return list(out.values())

    def _walk(self, http, s, url: str, where: str, params: dict) -> tuple[dict[str, Job], int, int]:
        """Every page of one listing: (jobs by id, the listing's totalCount, postings skipped without slug/title)."""
        out: dict[str, Job] = {}
        page, total, bad = 1, None, 0
        while True:
            d = http.get_json(url, params={"page": page, "limit": PAGE, "internal": "false", **params},
                              headers={"Accept": "application/json"})
            items = need_list(d, "jobs", where)
            if total is None:
                total = d.get("totalCount")
                need(isinstance(total, int), f"{where}: no totalCount")
            for it in items:
                j = it.get("data") if isinstance(it, dict) else None
                if not (isinstance(j, dict) and (j.get("slug") or j.get("req_id")) and "title" in j):
                    bad += 1  # a posting caught mid-edit: skipped, and reported below
                    continue
                jid = str(j.get("slug") or j.get("req_id"))
                if jid in out:
                    continue
                loc = j.get("full_location") or ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)
                etype = j.get("employment_type") or ""
                if not s.get("use_employment_type", True) and etype.upper() == "INTERN":
                    etype = ""
                out[jid] = Job(
                    id=jid, title=j.get("title") or "", location=loc,
                    url=(j.get("meta_data") or {}).get("canonical_url") or f"https://{s['host']}/jobs/{jid}?lang={j.get('language') or 'en-us'}",
                    posted=iso_date(j.get("posted_date") or j.get("create_date")),
                    snippet=html_text(" ".join(str(j.get(k) or "") for k in ("description", "qualifications"))),
                    department=" / ".join(c.get("name", "").strip() for c in j.get("categories") or [] if c.get("name")),
                    employment_type=etype, extra={"alt_ids": [str(j["req_id"])] if j.get("req_id") else []},
                )
            page += 1
            if not items or len(out) + bad >= total or page > 200:
                break
        return out, total, bad
