"""SmartRecruiters, through the company's hosted career page (the official Posting API host,
api.smartrecruiters.com, disallows all crawlers in robots.txt, so it is never used).

settings: company: ServiceNow     (identifier in careers.smartrecruiters.com/<company>)
          ignore_search_total: true   the search's totalFound isn't compared (Western Digital's counts 325 and
                                      lists only the newest 100); the page's own count still is
          watch_ids: [744000152261929, …]   postings read one by one, from their own page: Western Digital's page
                                      leaves out older postings and its search lists only the newest 100 (a Winter
                                      2027 co-op posted in September was in neither on 2026-11-15). The runner adds
                                      the ids of SimplifyJobs rows when learn_ids is true. One whose page says it has
                                      expired is closed
          sweep: true     keyword searches of the same search, for a company whose page and newest-100 search leave
                          older postings out (Western Digital). Every word a title can pass the role rule with is
                          searched (base.STUDENT_SEARCH_WORDS, UNDERCLASS_SEARCH_WORDS and WEAK_SEARCH_WORDS, the
                          company's role_keywords, the years the filters accept), and a hit is kept when its title has
                          one of them: the search matches any single word ("2nd year" finds "Technician 2"). It runs
                          on the first read with the setting (`swept` in the saved state), whose finds go out once as
                          "already open", and again on a read whose newest 100 are all unknown: 100 or more were
                          posted since the last read (liveness's `burst` alert, the company setting `burst: 100`).
                          What only the sweep found joins watch_open, so it is read from its own page from then on
                          (learn_ids carries watch_open between runs, so sweep needs it); a posting the watch list
                          already reads is left to it, with the values its own page gives. A keyword search that
                          fails, or counts more postings than it lists, marks the poll degraded and leaves `swept`
                          unset: the sweep is run again on the next read
1. GET https://careers.smartrecruiters.com/<company>  → first group page (HTML): section.js-group[data-qty] with up
   to 9 li.opening-job each, and div.js-openings-load[data-groups-pages][data-more]
2. GET <data-more>?page=N for the other group pages (HTML fragments, 6 groups each)
3. GET <a.js-more data-more>?type=<data-type>&value=<data-value>&page=N for groups with more than 9 jobs (10 per page)
4. union with GET https://jobs.smartrecruiters.com/sr-jobs/search?limit=100&company=<company> (newest 100, JSON),
   which also catches postings dropped by the unstable ordering inside a group
Detail: GET https://jobs.smartrecruiters.com/<company>/<id>-<slug>  (schema.org microdata)
A group page without groups, a group whose "more" pages run dry before its data-qty, fewer postings than the groups'
data-qty, or fewer than 95% of the search's totalFound marks the poll degraded (the jobs read are kept).
See discovery/notes/servicenow.md.

A hosted page that is one flat list instead (Arista's: ul.js-openings-load[data-more] holding li.opening-job, no
groups; until 2026-11-20 nothing was read from it, and only the search's 98 of its 218 postings were stored):
1. the search first, so the postings it lists keep the values they have always had (its places read "City, Region,
   cc", the page's "City, Country")
2. the page's postings, then GET <data-more>?page=1, 2, … (24 each) until a page is empty; they add the postings
   the search doesn't list
The flat page shows no count, so the search's postings must be among the page's (all but 2 + 3%); a walk that repeats
a page or doesn't end within FLAT_PAGES is reported too. Either marks the poll degraded.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..db import iso, utcnow
from ..models import CheckerError, Job
from .base import (STUDENT_SEARCH_WORDS, UNDERCLASS_SEARCH_WORDS, WEAK_SEARCH_WORDS, Checker, degrade, html_text,
                   iso_date, join_locations, need, need_soft, register, title_words)

HOSTED = "https://careers.smartrecruiters.com"
SEARCH = "https://jobs.smartrecruiters.com/sr-jobs/search"
WINDOW = 100  # the most postings one search answer lists: its newest
ID_RE = re.compile(r"/(\d{6,})-")
EXPIRED = re.compile(r"this job has expired|no longer (?:available|accepting)", re.I)
FLAT_PAGES = 400  # a flat list's "more" pages are never followed past this many (24 postings each)


def _flat_jobs(node, out: dict) -> tuple[int, int]:
    """The postings of a flat list (the page, or one of its "more" pages) added to `out`. Returns (postings, new ones).
    Each li.opening-job has the link, the title and li.job-desc texts: department, place, and for some a third that
    is only a hybrid/remote icon. The place is the last text of two or more; a single text could be either, so the
    place is then left to the posting's own page."""
    seen = new = 0
    for li in node.select("li.opening-job"):
        a = li.select_one("a[href]")
        m = ID_RE.search(a["href"]) if a is not None else None
        if not m:
            continue
        seen += 1
        if m.group(1) in out:
            continue
        title_el = a.select_one("h4.job-title, .job-title")
        title = title_el.get_text(" ", strip=True) if title_el else a.get_text(" ", strip=True)
        descs = [t for t in (d.get_text(" ", strip=True) for d in li.select("li.job-desc")) if t]
        out[m.group(1)] = Job(id=m.group(1), title=" ".join(title.split()),
                              location=descs[-1] if len(descs) >= 2 else "", url=a["href"].split("?")[0])
        new += 1
    return seen, new


def _jobs_in(node, group: str, out: dict) -> int:
    n = 0
    for a in node.select("li.opening-job a[href], a.js-job-ad-link[href]"):
        m = ID_RE.search(a["href"])
        if not m:
            continue
        jid = m.group(1)
        title_el = a.select_one("h4.job-title, .job-title")
        title = (title_el.get_text(" ", strip=True) if title_el else a.get_text(" ", strip=True))
        if jid in out:
            if group and group not in out[jid].location:
                out[jid].location = join_locations(out[jid].location, group)
        else:
            out[jid] = Job(id=jid, title=" ".join(title.split()), location=group, url=a["href"].split("?")[0])
        n += 1
    return n


@register
class SmartRecruiters(Checker):
    type = "smartrecruiters"
    supports_detail = True

    def describe(self, s):
        return f"{HOSTED}/{s['company']} (hosted career page) + {SEARCH}?company={s['company']}"

    def _groups(self, http, html: str, out: dict, where: str, problems: list) -> tuple[int, int]:
        """Parse a page of groups; follow each group's 'more' pages. Returns (groups, sum of data-qty).
        A group whose 'more' pages run dry before its data-qty is noted in `problems`."""
        soup = BeautifulSoup(html, "lxml")
        groups = qty_sum = 0
        for sec in soup.select("section.js-group"):
            groups += 1
            title = sec.select_one("header .opening-title, .opening-title")
            name = title.get_text(" ", strip=True) if title else ""
            qty = int(sec.get("data-qty") or 0)
            qty_sum += qty
            seen = _jobs_in(sec, name, out)
            more = sec.select_one("a.js-more[data-more]")
            page = 1
            while more is not None and seen < qty and page <= 60:
                frag = http.get_text(HOSTED + more["data-more"], params={
                    "type": more.get("data-type", "location"), "value": _unquote_once(more.get("data-value", "")),
                    "page": page})
                got = _jobs_in(BeautifulSoup(frag, "lxml"), name, out)
                if not got:
                    if seen < qty - 2:  # a count off by a posting or two that closed during the walk is normal
                        problems.append(f"group '{name}' ended at {seen} of {qty} jobs")
                    break
                seen += got
                page += 1
        return groups, qty_sum

    def fetch(self, http, s, ctx=None):
        company = s["company"]
        where = f"smartrecruiters:{company}"
        out: dict[str, Job] = {}
        problems: list[str] = []
        html = http.get_text(f"{HOSTED}/{company}")
        soup = BeautifulSoup(html, "lxml")
        loader = soup.select_one("div.js-openings-load")
        need(loader is not None or soup.select("section.js-group") or "opening-job" in html,
             f"{where}: hosted career page has no job groups")
        flat = None
        if loader is None and not soup.select("section.js-group"):
            flat = soup.select_one("ul.js-openings-load[data-more]")
        if flat is not None:  # one flat list, not groups (see the module docstring)
            qty = 0
            found, newest, rows = self._search(http, company, out)
            listing = self._flat(http, soup, flat["data-more"], problems)
            lost = [i for i in newest if i not in listing]
            if len(lost) > 2 + 0.03 * len(newest):
                problems.append(f"{len(lost)} of the search's {len(newest)} postings are not among the "
                                f"{len(listing)} the page lists")
            for jid, j in listing.items():
                out.setdefault(jid, j)
        else:
            groups, qty = self._groups(http, html, out, where, problems)
            pages = int(loader.get("data-groups-pages") or 1) if loader is not None else 1
            more = loader.get("data-more") if loader is not None else None
            for page in range(1, pages if more else 1):
                g, q = self._groups(http, http.get_text(HOSTED + more, params={"page": page}), out, where, problems)
                if not g:  # its groups' data-qty is missing from `qty` too, so the count check below can't see the loss
                    problems.append(f"group page {page} has no groups")
                groups, qty = groups + g, qty + q
            found, newest, rows = self._search(http, company, out)
        swept = self._sweep(http, s, ctx, out, newest, rows, problems) if s.get("sweep") else []
        listed = set(out)
        if isinstance(found, int) and not s.get("ignore_search_total") and len(out) < found * 0.95:
            problems.append(f"collected {len(out)} postings but the search reports {found}")
        if ctx is not None:
            ctx.reported_total = qty or found
        if qty:
            need_soft(len(out) >= qty * 0.97 - 2, f"{where}: collected {len(out)} postings but the page lists {qty}",
                      ctx)
        if problems:
            degrade(ctx, f"{where}: " + "; ".join(problems))
        if s.get("watch_ids"):
            out.update((j.id, j) for j in self._watched(http, s, ctx, listed))
        if swept and ctx is not None:  # no list reaches them: read from their own pages from the next read on
            ctx.state["watch_open"] = list(dict.fromkeys([*(ctx.state.get("watch_open") or []), *swept]))
        return list(out.values())

    def _sweep(self, http, s: dict, ctx, out: dict, newest: list[str], rows: int, problems: list) -> list[str]:
        """`sweep` (see the module docstring): the keyword searches, when this is the first read with the setting or
        the newest-100 answer holds no posting known before. Returns the ids only the sweep found, added to `out`.
        A posting the watch list reads (watch_ids) is left to it: it keeps the values its own page gives."""
        company, watched = s["company"], {str(x) for x in s.get("watch_ids") or []}
        state = ctx.state if ctx is not None else {}
        known = {k.rsplit(":", 1)[-1] for k in ctx.known} if ctx is not None else set()  # a multi source's ids: prefixed
        first = not state.get("swept")
        burst = bool(known) and rows >= WINDOW and not known.intersection(newest)
        if not (first or burst):
            return []
        words = list(dict.fromkeys([*STUDENT_SEARCH_WORDS, *UNDERCLASS_SEARCH_WORDS, *WEAK_SEARCH_WORDS,
                                    *(ctx.program_words if ctx is not None else ()),
                                    *(str(y) for y in (ctx.years if ctx is not None else ()))]))
        keep, before, bad = title_words(words), set(out), []
        for w in words:
            try:
                found, _, listed = self._search(http, company, out, keyword=w, keep=keep, skip=watched)
            except CheckerError as e:
                if ctx is None:
                    raise
                bad.append(f"'{w}': {e}")
                continue
            if isinstance(found, int) and found > listed:
                bad.append(f"'{w}' counts {found} postings and lists {listed}")
        only = [i for i in out if i not in before]
        if bad:  # not the whole sweep: reported, no removals recorded, and run again on the next read
            problems.append(f"keyword sweep incomplete ({len(bad)} of {len(words)} searches): " + "; ".join(bad[:3]))
            return only
        if first:  # open before this read could see them: shown once as "already open", not as new (runner._process)
            for i in only:
                out[i].extra["baseline"] = True
        state["swept"] = iso(utcnow())[:10]
        return only

    def _watched(self, http, s, ctx, listed: set[str]) -> list[Job]:
        """watch_ids: each posting the page and search left out, read from its own page. Open: it has a title and no
        "this job has expired" notice; gone (404, 410) or expired: closed, and not read again (watch_closed)."""
        company = s["company"]
        out, opened, closed = [], [], []
        for wid in dict.fromkeys(str(x) for x in s["watch_ids"]):
            if wid in listed:
                continue
            url = f"https://jobs.smartrecruiters.com/{company}/{wid}"
            try:
                r = http.get(url, headers={"Accept": "text/html"}, ok_statuses=(404, 410))
            except CheckerError as e:
                if ctx is None:
                    raise
                degrade(ctx, f"smartrecruiters:{company}: watched posting {wid}: {e}")
                continue
            soup = BeautifulSoup(r.text, "lxml") if r.status == 200 else None
            title = soup.select_one("[itemprop=title]") if soup is not None else None
            if title is None or EXPIRED.search(soup.get_text(" ", strip=True)):
                closed.append(wid)
                continue
            opened.append(wid)
            out.append(self._from_page(soup, Job(id=wid, title=" ".join(title.get_text(" ", strip=True).split()),
                                                 location="", url=url, extra={"unlisted": True})))
        if ctx is not None:
            ctx.state["watch_open"] = opened
            ctx.state["watch_closed"] = sorted(set(ctx.state.get("watch_closed") or []) | set(closed))[-300:]
        return out

    def _flat(self, http, soup, more: str, problems: list) -> dict[str, Job]:
        """A hosted page that is one flat list: the postings on it, then its "more" pages until one is empty. A page
        that only repeats postings, or a list that doesn't end, is noted in `problems`."""
        out: dict[str, Job] = {}
        _flat_jobs(soup, out)
        for page in range(1, FLAT_PAGES + 1):
            seen, new = _flat_jobs(BeautifulSoup(http.get_text(HOSTED + more, params={"page": page}), "lxml"), out)
            if not seen:
                return out
            if not new:
                problems.append(f"page {page} of the list repeats postings already read")
                return out
        problems.append(f"the list did not end within {FLAT_PAGES} pages")
        return out

    def _search(self, http, company: str, out: dict, keyword: str | None = None, keep: re.Pattern | None = None,
                skip=frozenset()) -> tuple[int | None, list[str], int]:
        """The search's newest 100 postings added to `out`. With `keyword` (a sweep): the newest 100 of that keyword,
        only those whose title has one of the swept words (`keep`); nothing already in `out` is touched and the ids
        in `skip` are left out. Returns (its totalFound, the ids taken from it, the rows it listed)."""
        params = {"limit": WINDOW, "company": company}
        if keyword:
            params["keyword"] = keyword
        d = http.get_json(SEARCH, params=params)
        need(isinstance(d, dict) and isinstance(d.get("content"), list), f"smartrecruiters:{company}: bad search JSON")
        ids: list[str] = []
        for it in d["content"]:
            jid = str(it.get("id") or "")
            if not jid:
                continue
            if keyword and (jid in out or jid in skip
                            or (keep is not None and not keep.search(" ".join((it.get("name") or "").split())))):
                continue
            ids.append(jid)
            loc = it.get("location") or {}
            where = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)
            if loc.get("remote"):
                where = join_locations(where, "Remote")
            if jid in out:
                out[jid].posted = out[jid].posted or iso_date(it.get("releasedDate"))
            else:
                out[jid] = Job(id=jid, title=" ".join((it.get("name") or "").split()), location=where,
                               url=it.get("applyUrl") or f"https://jobs.smartrecruiters.com/{company}/{jid}",
                               posted=iso_date(it.get("releasedDate")))
        return d.get("totalFound"), ids, len(d["content"])

    def detail(self, http, s, job):
        return self._from_page(BeautifulSoup(http.get_text(job.url), "lxml"), job)

    @staticmethod
    def _from_page(soup, job):
        """A posting page's schema.org microdata: employment type, posted date, description, location."""
        et = soup.select_one("[itemprop=employmentType]")
        if et:
            job.employment_type = et.get_text(" ", strip=True)
        dp = soup.select_one("meta[itemprop=datePosted]")
        if dp and dp.get("content"):
            job.posted = iso_date(dp["content"]) or job.posted
        parts = [soup.select_one(f"[itemprop={k}]") for k in ("description", "responsibilities", "qualifications")]
        job.snippet = html_text(" ".join(str(p) for p in parts if p)) or job.snippet
        loc = [soup.select_one(f"meta[itemprop={k}]") for k in ("addressLocality", "addressRegion", "addressCountry")]
        loc_s = ", ".join(m["content"] for m in loc if m is not None and m.get("content"))
        if loc_s and loc_s not in job.location:
            job.location = join_locations(job.location, loc_s)
        return job


def _unquote_once(v: str) -> str:
    from urllib.parse import unquote
    return unquote(v)
