"""Workday candidate-experience ("CXS") API used by every *.myworkdayjobs.com career site.

settings:
  host:   autodesk.wd1.myworkdayjobs.com        (or wd1.myworkdaysite.com for /recruiting/<tenant>/<site> sites)
  tenant: autodesk
  site:   uni                                   (or sites: [uni, Ext] to watch several career sites)
  partitions: [{timeType: [<id>]}, …]           optional; see the 2000-job cap below
  quick_queries: [{Job_Family_Group: [<id>]}]   optional; read fully on quick scans of big sites (e.g. intern facet)
  pack: true          optional: when a capped site splits only by a facet with many values (one per store location
                      at CVS, Target, Lowe's), several values go in one search (Workday returns jobs matching any):
                      searches of at most PACK_VALUES values whose counts add up to under PACK_JOBS (CVS: 37 searches
                      instead of 4,990)
  unlinked_ok: 50     optional: up to this many postings listed without a link (no title, no link, no place: Walmart
                      lists a few dozen) are skipped quietly; without it a handful stops the read, more than two
                      mark it degraded
  unlinked_once: true optional: a posting without a link counts once however many searches list it, and the read
                      stops only when such postings pass 2% of the whole site, not of the search they are in; more
                      than two still mark it degraded, naming them. Capital One is read whole and then again by
                      location, a job under each of its places: on 10 Nov 2026 a few link-less postings, counted
                      again in each small location's search, stopped its whole 2,055-job read at "4"
List:  POST https://<host>/wday/cxs/<tenant>/<site>/jobs  {"appliedFacets":{}, "limit":20, "offset":N, "searchText":""}
        → {"total": N (first page only), "jobPostings": [{title, externalPath, locationsText, postedOn, bulletFields}],
           "facets": [{facetParameter, values: [{id, descriptor, count}]}]}
Detail: GET  https://<host>/wday/cxs/<tenant>/<site><externalPath> → {"jobPostingInfo": {jobDescription, location, …}}

The 2000-job cap: a search never reports more than 2000 jobs, and offsets past 2000 silently return page 1
again. A site that reaches the cap is read in partitions (one facet value at a time, each below the cap):
the `partitions` setting, or automatically from the first page's facets, preferring a facet whose counts add up
to the total (no job left without a value). A partition that reaches the cap itself is split once more by a facet
from its own first page (T-Mobile's Part time by state). When no facet does it, the jobs read are kept and the
poll is marked degraded.
"""
from __future__ import annotations

import json
import re

from ..models import CheckTimeout, Job, ShapeError
from .base import (Checker, check_total, degrade, html_text, iso_date, need, need_list, need_soft, register,
                   relative_posted)

PAGE = 20     # Workday rejects larger pages
CAP = 2000    # Workday's search result cap
PACK_MIN = 60       # `pack`: a split into more searches than this is packed …
PACK_VALUES = 150   # … into searches of at most this many values (Workday answers 400 values with an error, 200 work)
PACK_JOBS = 1900    # … whose counts add up to at most this (a job listed under several values counts once each)
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
REQ_ID = re.compile(r"^(?=[^ ]*\d{4})[A-Z0-9][A-Z0-9_-]{3,24}$")   # requisition-like bullet fields
AUTO_FACETS = ("timeType", "workerSubType", "jobFamilyGroup", "locationCountry", "locationRegionStateProvince",
               "locationMainGroup", "locations")


def _facets(page: dict):
    """A page's facets, including the ones Workday nests in a group (locationMainGroup → locationCountry, …)."""
    for f in page.get("facets") or []:
        yield f
        for v in f.get("values") or []:
            if isinstance(v, dict) and v.get("facetParameter") and isinstance(v.get("values"), list):
                yield v


def _title_from_path(path: str) -> str:
    """A posting listed without its title, read from its link: "/job/Module-Equipment-Technician_JR0288155-1" →
    "Module Equipment Technician" (the last part, without the requisition after "_")."""
    slug = path.rstrip("/").rsplit("/", 1)[-1].rsplit("_", 1)[0]
    return " ".join(slug.replace("-", " ").split())


def _cut_short(ctx) -> None:
    """Part of the site could not be read (see FetchContext.partial)."""
    if ctx is not None:
        ctx.partial = True


def _counted(page: dict, name: str) -> int:
    """How many jobs a facet's values count on this page (0 without that facet)."""
    return max((sum(v["count"] for v in f.get("values") or [] if isinstance(v.get("count"), int))
                for f in _facets(page) if f.get("facetParameter") == name), default=0)


def _pack(first: dict, parts: list[dict]) -> list[dict]:
    """One-value searches of a single facet, packed into searches of several values (first fit, biggest first)."""
    name = next(iter(parts[0]))
    counts = {v["id"]: v["count"] for f in _facets(first) if f.get("facetParameter") == name for v in f.get("values") or []
              if v.get("id") and isinstance(v.get("count"), int)}
    bins: list[list] = []  # [jobs, ids]
    for vid in sorted((i for p in parts for i in p[name]), key=lambda i: -counts.get(i, 0)):
        n = counts.get(vid, 0)
        b = next((b for b in bins if b[0] + n <= PACK_JOBS and len(b[1]) < PACK_VALUES), None)
        if b is None:
            bins.append([n, [vid]])
        else:
            b[0] += n
            b[1].append(vid)
    return [{name: ids} for _, ids in bins]


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
                self.biggest = max(self.biggest, total)
            page_ids = []
            for p in items:
                path = p.get("externalPath")
                title = p.get("title") or (_title_from_path(path) if path else "")  # Intel lists one without a title
                if not (path and title) and s.get("unlinked_once"):
                    key = json.dumps(p, sort_keys=True, default=str)
                    self.unlinked.setdefault(key, p.get("title") or "")
                    need(len(self.unlinked) <= max(3, self.biggest // 50, s.get("unlinked_ok", 0)),
                         f"{where}: {len(self.unlinked)} postings without externalPath")
                    page_ids.append(f"unlinked:{key}")  # listed, so it counts when the search's total is checked
                    continue
                if not (path and title):
                    self.malformed += 1  # no link to read or open; too many of them means the format changed
                    need(self.malformed <= max(3, total // 50, s.get("unlinked_ok", 0)),
                         f"{where}: {self.malformed} postings without externalPath")
                    continue
                jid = f"{site}:{path}" if len(self.sites(s)) > 1 else path
                page_ids.append(jid)
                if jid not in out:
                    out[jid] = Job(
                        id=jid, title=title, location=p.get("locationsText") or "",
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

    def _partitions(self, s, first: dict, total: int = 0, skip=()) -> list[dict]:
        """_facet_parts, packed when the site asks for it (`pack`) and they are many."""
        parts = self._facet_parts(s, first, total, skip)
        return _pack(first, parts) if s.get("pack") and len(parts) > PACK_MIN else parts

    def _facet_parts(self, s, first: dict, total: int = 0, skip=()) -> list[dict]:
        """The `partitions` setting, or facet values from a capped search's first page (one search each, all below the
        cap): the first facet in AUTO_FACETS order whose counts add up to `total`, so no job lacks a value for it;
        failing that, the one whose counts add up to the most. `skip`: facets the search already applies."""
        if s.get("partitions"):
            return list(s["partitions"])
        best, best_n = [], 0
        for name in AUTO_FACETS:
            if name in skip:
                continue
            for f in _facets(first):
                vals = [v for v in f.get("values") or [] if v.get("id") and isinstance(v.get("count"), int)]
                if f.get("facetParameter") != name or not vals or any(v["count"] >= CAP for v in vals):
                    continue
                n = sum(v["count"] for v in vals)
                if n >= total:
                    return [{name: [v["id"]]} for v in vals]
                if n > best_n:
                    best, best_n = [{name: [v["id"]]} for v in vals], n
        return best

    def _split(self, http, s, site, facets: dict, total: int, first: dict, out: dict, ctx,
               depth: int) -> tuple[int, set]:
        """Read a capped search again one facet value at a time. Returns (sum of the partitions' totals, ids read)."""
        where = f"workday:{s['tenant']}/{site}" + (f" {facets}" if facets else "")
        # a capped total only says "2000 or more": the time type and worker type counts (one per job) say how many
        known = max([total] + [_counted(first, name) for name in ("timeType", "workerSubType") if name not in facets])
        # never the configured partitions (they are what is split here); `pack` still applies
        parts = self._partitions({"pack": True} if s.get("pack") else {}, first, known, skip=facets)
        if not need_soft(parts, f"{where}: {total}+ jobs hit Workday's {CAP} cap and no facet splits them; "
                                f"set `partitions` in companies.yaml", ctx):
            _cut_short(ctx)
            return total, set()  # the jobs the capped search returned are kept
        reported, got, _ = self._read_parts(http, s, site, facets, parts, out, ctx, depth)
        if not (ctx is not None and ctx.quick):
            try:  # jobs without a value for the facet are in none of its partitions
                check_total(len(got), known, f"{where} partitioned by {next(iter(parts[0]))}")
            except ShapeError as e:
                degrade(ctx, str(e))
                _cut_short(ctx)
        return reported, got

    def _read_parts(self, http, s, site, facets: dict, parts: list[dict], out: dict, ctx,
                    depth: int = 0) -> tuple[int, set, list]:
        """Read each partition (`facets` plus one part). One that reaches the cap itself is split once more by a facet
        from its own first page; a part of that split still at the cap keeps what it returned and marks the poll
        degraded. Returns (sum of the partitions' totals, ids read, each partition's first page)."""
        where = f"workday:{s['tenant']}/{site}"
        quick = ctx is not None and ctx.quick
        reported, got, firsts = 0, set(), []
        for part in parts:
            sub = {**facets, **part}
            total, first, seen = self._search(http, s, site, sub, out, ctx, stop_early=quick)
            got |= seen
            firsts.append(first)
            if total < CAP:
                reported += total
                if not quick:
                    check_total(len(seen), total, f"{where} {sub}")
            elif depth == 0:
                n, more = self._split(http, s, site, sub, total, first, out, ctx, depth=1)
                reported, got = reported + n, got | more
            else:
                need_soft(False, f"{where}: partition {sub} reports {total} jobs (cap {CAP}); split it further "
                                 f"in companies.yaml", ctx)
                _cut_short(ctx)
                reported += total
        return reported, got, firsts

    def _check_partitions(self, s, site, parts: list[dict], firsts: list, got: set, ctx) -> None:
        """Configured partitions (T-Mobile: one search per time type) must still cover the site. Each first page counts
        every value of the partitioned facet: a value no partition selects (a new time type), or fewer jobs read than
        those counts (beyond the usual tolerance), marks the poll degraded."""
        names = {name for p in parts for name in p}
        if len(names) != 1 or not firsts:
            return
        name = next(iter(names))
        chosen = {v for p in parts for v in p[name]}
        vals = [v for f in _facets(firsts[0]) if f.get("facetParameter") == name for v in f.get("values") or []
                if v.get("id") and isinstance(v.get("count"), int)]
        where = f"workday:{s['tenant']}/{site}"
        missing = [v for v in vals if v["id"] not in chosen and v["count"]]
        if missing:
            degrade(ctx, f"{where}: no partition reads {name} " +
                    ", ".join(f"{v.get('descriptor') or v['id']} ({v['count']} jobs)" for v in missing))
            _cut_short(ctx)
        try:
            check_total(len(got), sum(v["count"] for v in vals), f"{where} partitioned by {name}")
        except ShapeError as e:
            degrade(ctx, str(e))
            _cut_short(ctx)

    def fetch(self, http, s, ctx=None):
        out: dict[str, Job] = {}
        self.malformed = 0
        self.unlinked: dict[str, str] = {}  # unlinked_once: each posting without a link (as listed) → its title
        self.biggest = 0                    # unlinked_once: the largest total a search of this read reported
        try:
            reported = self._fetch_sites(http, s, ctx, out)
        except CheckTimeout as e:
            if ctx is None:
                raise
            # out of time (Capital One's split by location takes minutes): keep what was read, record no removals
            degrade(ctx, f"workday:{s['tenant']}: ran out of time after {len(out)} jobs: {e}")
            _cut_short(ctx)
            reported = 0
        # one or two stray entries (GEICO lists one) are normal; more are worth a look, unless the site allows them
        if self.malformed > max(2, s.get("unlinked_ok", 0)):
            degrade(ctx, f"workday:{s['tenant']}: skipped {self.malformed} postings without a link")
            _cut_short(ctx)
        if len(self.unlinked) > max(2, s.get("unlinked_ok", 0)):
            titles = [t for t in self.unlinked.values() if t]
            degrade(ctx, f"workday:{s['tenant']}: skipped {len(self.unlinked)} postings without a link"
                         + (": " + "; ".join(titles[:5]) if titles else ""))
            _cut_short(ctx)
        if ctx is not None and reported:
            ctx.reported_total = reported
        return list(out.values())

    def _fetch_sites(self, http, s, ctx, out: dict) -> int:
        """Read every site into `out`. Returns the sum of the searches' reported totals."""
        quick = ctx is not None and ctx.quick
        reported = 0
        for site in self.sites(s):
            where = f"workday:{s['tenant']}/{site}"
            parts = [dict(p) for p in s.get("partitions") or []]
            if parts:
                n, got, firsts = self._read_parts(http, s, site, s.get("facets", {}), parts, out, ctx)
                reported += n
                if not quick:
                    self._check_partitions(s, site, parts, firsts, got, ctx)
            else:
                total, first, seen = self._search(http, s, site, s.get("facets", {}), out, ctx, stop_early=quick)
                if total >= CAP:  # capped: read it again one facet value at a time
                    reported += self._split(http, s, site, s.get("facets", {}), total, first, out, ctx, depth=0)[0]
                else:
                    reported += total
                    if not quick:
                        check_total(len(seen), total, where)
            for facets in (s.get("quick_queries") or []) if quick else []:
                self._search(http, s, site, facets, out, ctx, stop_early=False)
        return reported

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
