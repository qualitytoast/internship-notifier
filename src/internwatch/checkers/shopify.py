"""Shopify: every posting is embedded in shopify.com/careers (React Router "turbo-stream" loader data).

GET https://www.shopify.com/careers → window.__reactRouterContext.streamController.enqueue("<chunk>")
  chunk line 1 = a flat JSON array; value 0 is the root; dict keys "_N" name flat[N]; ints point into the array
  root.loaderData["($locale)/careers"].roles[] = {id, title, location, locations[], discipline, href}    (since Oct 2026)
  or, as the page was before (it may yet come back: the loader also carries isCareersUplift), .jobPostingsWithJobs[] =
      {jobPosting: {id, title, locationName, publishedDate, employmentType, …}, job: {customFields[{title: Discipline,
      valueLabel}]}}
  (Shopify's postings come from a private Ashby board; the public posting API has no "shopify" board.)
GET https://www.shopify.com/careers/feed.xml → <source><job><partnerJobId/><experienceLevel/><listDate/>… (the same ids)
  roles[] has no posting date or employment type, so those come from here: the level is the only way left to tell a
  student role whose title has no student word. The feed's own location is coarser ("Canada" for "Remote - Canada,
  Americas"), so the page's is kept. A feed that can't be read marks the poll degraded; the jobs are still read.
/careers.data and /careers/search are robots-disallowed and never used. Staff names in job.hiringTeam /
job.author are never read. See discovery/notes/shopify.md.
"""
from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as ET

from ..adapters.base import Checker, degrade, iso_date, join_locations, need, register
from ..models import CheckerError, Job

PAGE = "https://www.shopify.com/careers"
FEED = "https://www.shopify.com/careers/feed.xml"
ENQUEUE = re.compile(r'streamController\.enqueue\(("(?:[^"\\]|\\.)*")\)', re.S)
CONST = {-1: None, -2: float("nan"), -3: float("-inf"), -4: -0.0, -5: None, -6: float("inf"), -7: None}


def decode_turbo_stream(flat: list):
    memo: dict[int, object] = {}

    def val(i):
        if isinstance(i, int) and i < 0:
            return CONST.get(i)
        if i in memo:
            return memo[i]
        v = flat[i]
        if isinstance(v, dict):
            out: dict = {}
            memo[i] = out
            for k, vi in v.items():
                name = flat[int(k[1:])] if k.startswith("_") and k[1:].isdigit() else k
                out[name] = val(vi)
            return out
        if isinstance(v, list):
            # A list of indices is a plain array; one that starts with a tag is a typed value: "D" (date) is kept,
            # the rest ("P" promise, "SingleFetchClassInstance", …) are unused and stay opaque.
            if v and isinstance(v[0], str):
                return v[1] if len(v) > 1 and v[0] == "D" else None
            out_l: list = []
            memo[i] = out_l
            out_l.extend(val(x) for x in v)
            return out_l
        return v

    return val(0)


def slug(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")


@register
class Shopify(Checker):
    type = "shopify"

    def describe(self, s):
        return f"GET {PAGE} (embedded loader data, every posting) + {FEED} (level, date)"

    def fetch(self, http, s, ctx=None):
        html = http.get_text(PAGE, headers={"Accept": "text/html"})
        chunks = [json.loads(m.group(1)) for m in ENQUEUE.finditer(html)]
        need(chunks, "shopify: no streamController.enqueue(...) data on /careers")
        flat = json.loads(chunks[0].split("\n", 1)[0])
        need(isinstance(flat, list) and flat, "shopify: turbo-stream root is not an array")
        root = decode_turbo_stream(flat)
        loader = ((root or {}).get("loaderData") or {}).get("($locale)/careers") or {}
        rows = loader.get("jobPostingsWithJobs")
        if rows is None and isinstance(loader.get("roles"), list):
            return self._roles(http, loader["roles"], ctx)
        need(isinstance(rows, list), "shopify: loaderData['($locale)/careers'] has neither roles nor jobPostingsWithJobs")
        places = {x.get("id"): x.get("name") for x in loader.get("atsLocations") or [] if isinstance(x, dict)}
        jobs = []
        for r in rows:
            p = (r or {}).get("jobPosting") or {}
            need(p.get("id") and p.get("title"), "shopify: posting without id/title")
            if p.get("isListed") is False:
                continue
            secondary = ((p.get("locationIds") or {}).get("secondaryLocationIds")) or []
            locs = [p.get("locationName")] + [places.get(x) for x in secondary]
            loc = join_locations(locs)
            if p.get("workplaceType") == "Remote" or p.get("isRemote"):
                loc = f"Remote ({loc})" if loc and "remote" not in loc.lower() else (loc or "Remote")
            fields = {f.get("title"): f.get("valueLabel") for f in ((r.get("job") or {}).get("customFields") or [])
                      if isinstance(f, dict)}
            jobs.append(Job(id=p["id"], title=p["title"], location=loc,
                            url=f"https://www.shopify.com/careers/{slug(p['title'])}_{p['id']}",
                            posted=iso_date(p.get("publishedDate")), employment_type=p.get("employmentType") or "",
                            department=" / ".join(x for x in (fields.get("Discipline"), fields.get("Subdiscipline")) if x)))
        need(jobs or not rows, "shopify: postings present but none parsed")
        return jobs

    def _roles(self, http, roles: list, ctx) -> list[Job]:
        feed = self._feed(http, ctx)
        jobs = []
        for r in roles:
            need(isinstance(r, dict) and r.get("id") and r.get("title"), "shopify: role without id/title")
            places = [str(x) for x in r.get("locations") or [r.get("location")] if x]
            loc = join_locations([re.sub(r"^remote\s*-\s*", "", x, flags=re.I) for x in places])
            if any(x.lower().startswith("remote") for x in places):
                loc = f"Remote ({loc})" if loc and "remote" not in loc.lower() else (loc or "Remote")
            level, listed = feed.get(r["id"], ("", ""))
            jobs.append(Job(id=r["id"], title=r["title"], location=loc,
                            url=f"https://www.shopify.com{r['href']}" if r.get("href")
                            else f"https://www.shopify.com/careers/{slug(r['title'])}_{r['id']}",
                            posted=iso_date(listed), employment_type=level, department=r.get("discipline") or ""))
        return jobs

    def _feed(self, http, ctx) -> dict[str, tuple[str, str]]:
        """{posting id: (experience level, date listed)}; {} and a degraded poll when the feed can't be read."""
        try:
            root = ET.fromstring(http.get_text(FEED, headers={"Accept": "application/xml"}))
        except (CheckerError, ET.ParseError) as e:
            if ctx is None:
                raise
            degrade(ctx, f"shopify: {FEED} not read ({e}): posting dates and job levels are missing")
            return {}
        return {(j.findtext("partnerJobId") or "").strip(): ((j.findtext("experienceLevel") or "").strip(),
                                                             (j.findtext("listDate") or "").strip())
                for j in root.findall("job")}
