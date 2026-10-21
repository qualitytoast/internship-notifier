"""Workday candidate-experience ("CXS") API used by every *.myworkdayjobs.com career site.

settings:
  host:   autodesk.wd1.myworkdayjobs.com        (or wd1.myworkdaysite.com for /recruiting/<tenant>/<site> sites)
  tenant: autodesk
  site:   uni                                   (or sites: [uni, Ext] to watch several career sites)
  partitions: [{timeType: [<id>]}, …]           optional; see the 2000-job cap below
  quick_queries: [{Job_Family_Group: [<id>]}]   optional; read fully on quick scans of big sites (e.g. intern facet)
List:   POST https://<host>/wday/cxs/<tenant>/<site>/jobs  {"appliedFacets":{}, "limit":20, "offset":N, "searchText":""}
        → {"total": N (first page only), "jobPostings": [{title, externalPath, locationsText, postedOn, bulletFields}],
           "facets": [{facetParameter, values: [{id, descriptor, count}]}]}
Detail: GET  https://<host>/wday/cxs/<tenant>/<site><externalPath> → {"jobPostingInfo": {jobDescription, location, …}}

The 2000-job cap: a search never reports more than 2000 jobs, and offsets past 2000 silently return page 1
again. A site that reaches the cap is read in partitions (one facet value at a time, each below the cap):
the `partitions` setting, or automatically from the first page's facets.
"""
from __future__ import annotations

import re

from ..models import Job
from .base import Checker, check_total, html_text, iso_date, need, need_list, register, relative_posted

PAGE = 20     # Workday rejects larger pages
CAP = 2000    # Workday's search result cap
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
REQ_ID = re.compile(r"^(?=[^ ]*\d{4})[A-Z0-9][A-Z0-9_-]{3,24}$")   # requisition-like bullet fields
AUTO_FACETS = ("timeType", "workerSubType", "jobFamilyGroup", "locationCountry", "locationMainGroup", "locations")


@register
class Workday(Checker):
    type = "workday"
    supports_detail = True
    supports_quick = True

    def sites(self, s):
        return list(s.get("sites") or [s["site"]])

    def base(self, s, site):
        return f"https://{s['host']}/wday/cxs/{s['tenant']}/{site}"

    def public_url(self, s, site, path):
        if "myworkdaysite.com" in s["host"]:
            return f"https://{s['host']}/en-US/recruiting/{s['tenant']}/{site}{path}"
        return f"https://{s['host']}/en-US/{site}{path}"

    def describe(self, s):
        return ", ".join(self.base(s, site) + "/jobs" for site in self.sites(s))

    # one search (all pages) ------------------------------------------------------------------
    def _search(self, http, s, site, facets: dict, out: dict, ctx=None, stop_early=False) -> tuple[int, dict, set]:
        """Read one search to its end. Returns (reported total, first page, ids this search returned)."""
        url = self.base(s, site) + "/jobs"
        where = f"workday:{s['tenant']}/{site}"
        offset, total, first = 0, None, {}
        seen: set[str] = set()
        while True:
            body = {"appliedFacets": facets, "limit": PAGE, "offset": offset, "searchText": s.get("search", "")}
            data = http.post_json(url, json=body, headers=HEADERS)
            items = need_list(data, "jobPostings", where)
            if total is None:
                total, first = data.get("total"), data
                need(isinstance(total, int), f"{where}: no total in first page")
            page_ids = []
            for p in items:
                if not (p.get("externalPath") and p.get("title")):
                    self.malformed += 1  # a posting caught mid-edit; too many of them means the format changed
                    need(self.malformed <= max(3, total // 50), f"{where}: {self.malformed} postings without externalPath/title")
                    continue
                path = p["externalPath"]
                jid = f"{site}:{path}" if len(self.sites(s)) > 1 else path
                page_ids.append(jid)
                if jid not in out:
                    out[jid] = Job(
                        id=jid, title=p.get("title") or "", location=p.get("locationsText") or "",
                        url=self.public_url(s, site, path), posted=relative_posted(p.get("postedOn")),
                        employment_type=p.get("timeType") or "",
                        extra={"site": site, "path": path,
                               "alt_ids": [b for b in p.get("bulletFields") or [] if REQ_ID.match(str(b))]},
                    )
            fresh = [j for j in page_ids if j not in seen]
            seen.update(page_ids)
            offset += PAGE
            if not items or offset >= min(total, CAP):
                break
            if not fresh:
                break  # the page repeated earlier results (Workday wraps around); counts are checked by the caller
            if stop_early and ctx is not None and ctx.page_is_old(page_ids, key=f"{site}:{sorted(facets.items())}"):
                break
        return total, first, seen

    def _partitions(self, s, first: dict) -> list[dict]:
        if s.get("partitions"):
            return list(s["partitions"])
        for name in AUTO_FACETS:
            for f in first.get("facets") or []:
                vals = [v for v in f.get("values") or [] if v.get("id") and isinstance(v.get("count"), int)]
                if f.get("facetParameter") == name and vals and all(v["count"] < CAP for v in vals):
                    return [{name: [v["id"]]} for v in vals]
        return []

    def fetch(self, http, s, ctx=None):
        out: dict[str, Job] = {}
        self.malformed = 0
        quick = ctx is not None and ctx.quick
        reported = 0
        for site in self.sites(s):
            where = f"workday:{s['tenant']}/{site}"
            parts = [dict(p) for p in s.get("partitions") or []]
            if not parts:
                total, first, seen = self._search(http, s, site, s.get("facets", {}), out, ctx, stop_early=quick)
                if total >= CAP:  # capped: read it again one facet value at a time
                    parts = self._partitions(s, first)
                    need(parts, f"{where}: {total}+ jobs hit Workday's {CAP} cap and no facet splits them; "
                                f"set `partitions` in companies.yaml")
                else:
                    reported += total
                    if not quick:
                        check_total(len(seen), total, where)
            for facets in parts:
                total, _, seen = self._search(http, s, site, {**s.get("facets", {}), **facets}, out, ctx, stop_early=quick)
                need(total < CAP, f"{where}: partition {facets} reports {total} jobs (cap {CAP}); split it further")
                reported += total
                if not quick:
                    check_total(len(seen), total, f"{where} {facets}")
            for facets in (s.get("quick_queries") or []) if quick else []:
                self._search(http, s, site, facets, out, ctx, stop_early=False)
        if ctx is not None and reported:
            ctx.reported_total = reported
        return list(out.values())

    def detail(self, http, s, job):
        site, path = job.extra.get("site") or self.sites(s)[0], job.extra.get("path") or job.id
        d = http.get_json(self.base(s, site) + path, headers=HEADERS)
        info = d.get("jobPostingInfo") if isinstance(d, dict) else None
        need(isinstance(info, dict), f"workday: bad detail for {path}")
        job.snippet = html_text(info.get("jobDescription"))
        locs = [info.get("location")] + list(info.get("additionalLocations") or [])
        country = (info.get("country") or {}).get("descriptor") if isinstance(info.get("country"), dict) else None
        loc = "; ".join(x for x in locs if x)
        if country and country not in loc:
            loc = f"{loc} ({country})" if loc else country
        if loc:
            job.location = loc
        job.employment_type = info.get("timeType") or job.employment_type
        job.posted = iso_date(info.get("startDate")) if not job.posted else job.posted
        return job
