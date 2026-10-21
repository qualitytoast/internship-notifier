"""Eightfold AI career sites (e.g. apply.careers.microsoft.com, jobs.nvidia.com, paypal.eightfold.ai).

settings:
  host:   apply.careers.microsoft.com
  domain: microsoft.com
  api:    pcsx (default, /api/pcsx/search) | v2 (older /api/apply/v2/jobs, e.g. Netflix, Liberty Mutual)
  params: {…}            extra query params for every request (optional)
  quick_queries: [{…}]   extra param sets fully read on every poll, before the full listing (e.g. the site's
                         internship filter)
  count_tolerance: 0.03  allowed shortfall vs the reported total for sites whose sort order drifts while paging

Both APIs return 10 jobs per page (no larger page size is accepted), PCSX results are sorted newest-first
with sort_by=timestamp, which makes incremental "quick" scans safe for very large sites (v2 ignores it).
A full listing that runs out of time keeps what it read, and the poll is marked degraded.
robots.txt on Eightfold hosts explicitly allows /api/pcsx and /api/apply.
"""
from __future__ import annotations

from ..models import CheckTimeout, Job
from .base import (Checker, FetchContext, check_total_soft, dedupe, degrade, html_text, iso_date, join_locations, need,
                   need_list, register, report_skipped)

PAGE = 10


@register
class Eightfold(Checker):
    type = "eightfold"
    supports_detail = True
    supports_quick = True

    def describe(self, s):
        if s.get("api") == "v2":
            return f"https://{s['host']}/api/apply/v2/jobs?domain={s['domain']}"
        return f"https://{s['host']}/api/pcsx/search?domain={s['domain']}"

    # one listing (all pages) ---------------------------------------------------------------
    def _list(self, http, s, extra: dict, ctx: FetchContext | None, stop_early: bool,
              jobs: list[Job] | None = None) -> tuple[list[Job], int | None]:
        """Pages are added to `jobs` (a new list by default) as they arrive, so a walk cut short keeps what it read."""
        v2 = s.get("api") == "v2"
        url = f"https://{s['host']}/api/apply/v2/jobs" if v2 else f"https://{s['host']}/api/pcsx/search"
        jobs = [] if jobs is None else jobs
        start, total = 0, None
        while True:
            params = {"domain": s["domain"], "query": "", "location": "", "start": start, "sort_by": "timestamp",
                      **(s.get("params") or {}), **extra}
            if v2:
                params["num"] = PAGE
            data = http.get_json(url, params=params)
            where = f"eightfold:{s['domain']}"
            if v2:
                items = need_list(data, "positions", where)
                count = data.get("count")
            else:
                need(isinstance(data, dict) and isinstance(data.get("data"), dict), f"{where}: no data object")
                items = need_list(data["data"], "positions", where)
                count = data["data"].get("count")
            if total is None:
                total = count
            page = [j for j in (self._job(s, p, v2) for p in items) if j is not None]
            jobs += page
            start += PAGE
            if not items or (isinstance(total, int) and start >= total):
                break
            if stop_early and ctx is not None and ctx.page_is_old([j.id for j in page], key=str(sorted(extra.items()))):
                break
            need(start <= 20000, f"{where}: runaway pagination")
        return jobs, total

    def _job(self, s, p, v2: bool) -> Job | None:
        if not (isinstance(p, dict) and p.get("id") and (p.get("name") or p.get("posting_name"))):
            # a posting caught mid-edit: skipped, and reported by fetch (once, though later passes see it again)
            self.malformed.add(str(p.get("id") or p) if isinstance(p, dict) else str(p))
            return None
        if v2:
            locs = p.get("locations") or [p.get("location")]
            url = p.get("canonicalPositionUrl") or f"https://{s['host']}/careers/job/{p['id']}"
            posted = iso_date(p.get("t_create") or p.get("t_update"))
            snippet = html_text(p.get("job_description"))
        else:
            # "locations" spells countries out ("Israel, Tel Aviv"); standardizedLocations ends in an ISO code
            # ("Tel Aviv-Yafo, Tel Aviv District, IL") that reads like a US state, so it is only a fallback.
            locs = p.get("locations") or p.get("standardizedLocations")
            url = f"https://{s['host']}{p.get('positionUrl') or '/careers/job/' + str(p['id'])}"
            posted = iso_date(p.get("postedTs") or p.get("creationTs"))
            snippet = ""
        return Job(
            id=str(p["id"]),
            title=p.get("name") or p.get("posting_name") or "",
            location=join_locations(locs),
            url=url,
            posted=posted,
            snippet=snippet,
            department=p.get("department") or "",
            extra={"alt_ids": [x for x in (p.get("atsJobId") or p.get("ats_job_id"), p.get("displayJobId") or p.get("display_job_id")) if x]},
        )

    def fetch(self, http, s, ctx=None):
        # The v2 API ignores sort_by=timestamp, so only PCSX sites can stop early.
        quick = ctx is not None and ctx.quick and s.get("api") != "v2"
        self.malformed: set[str] = set()
        student: list[Job] = []
        for q in s.get("quick_queries") or []:  # the site's own student filters, every poll, first: a long full walk
            student += self._list(http, s, q, ctx, stop_early=False)[0]  # that runs out of time can't hide them
        jobs: list[Job] = []
        try:
            total = self._list(http, s, {}, ctx, stop_early=quick, jobs=jobs)[1]
            if not quick and isinstance(total, int) and len(dedupe(jobs)) < total and s.get("api") != "v2":
                # postings re-dated during a long walk jump to page 1 after it was read: read the top again
                seen = FetchContext(mode="quick", known=frozenset(j.id for j in jobs))
                self._list(http, s, {}, seen, stop_early=True, jobs=jobs)
        except CheckTimeout as e:
            if ctx is None:
                raise
            total = None  # a walk cut short: no count to check
            done = " (the internship filters were read in full)" if student else ""
            degrade(ctx, f"eightfold:{s['domain']}: the full listing stopped after {len(dedupe(jobs))} jobs{done}: {e}")
        if ctx is not None and isinstance(total, int):
            ctx.reported_total = total
        jobs = dedupe(jobs + student)
        if not quick:
            tol = int(total * float(s["count_tolerance"])) if s.get("count_tolerance") and isinstance(total, int) else None
            # a short walk keeps what it read (the internship filters were read in full first): degraded, not failed
            check_total_soft(len(jobs) + len(self.malformed), total, f"eightfold:{s['domain']}", ctx, tolerance=tol)
        bad = len(self.malformed)
        report_skipped(ctx, bad, len(jobs), f"eightfold:{s['domain']}: skipped {bad} positions without id/name")
        return jobs

    def detail(self, http, s, job):
        if s.get("api") == "v2":
            d = http.get_json(f"https://{s['host']}/api/apply/v2/jobs/{job.id}", params={"domain": s["domain"]})
            need(isinstance(d, dict), f"eightfold: bad detail for {job.id}")
            job.snippet = html_text(d.get("job_description"))
            if d.get("locations"):
                job.location = join_locations(d["locations"])
            return job
        d = http.get_json(f"https://{s['host']}/api/pcsx/position_details",
                          params={"position_id": job.id, "domain": s["domain"], "hl": "en"})
        data = d.get("data") if isinstance(d, dict) else None
        need(isinstance(data, dict), f"eightfold: bad detail for {job.id}")
        job.snippet = html_text(data.get("jobDescription") or data.get("job_description") or "")
        etype = data.get("efcustomTextEmploymentType") or data.get("employmentType")
        if etype:
            job.employment_type = ", ".join(etype) if isinstance(etype, list) else str(etype)
        return job
