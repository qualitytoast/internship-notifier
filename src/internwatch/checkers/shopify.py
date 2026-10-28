"""Shopify: every posting is embedded in shopify.com/careers (React Router "turbo-stream" loader data).

GET https://www.shopify.com/careers → window.__reactRouterContext.streamController.enqueue("<chunk>")
  chunk line 1 = a flat JSON array; value 0 is the root; dict keys "_N" name flat[N]; ints point into the array
  root.loaderData["($locale)/careers"].jobPostingsWithJobs[] = {jobPosting: {id, title, locationName,
      publishedDate, employmentType, …}, job: {customFields[{title: Discipline, valueLabel}]}}
  (Shopify's postings come from a private Ashby board; the public posting API has no "shopify" board.)
/careers.data and /careers/search are robots-disallowed and never used. Staff names in job.hiringTeam /
job.author are never read. See discovery/notes/shopify.md.
"""
from __future__ import annotations

import json
import re
import unicodedata

from ..adapters.base import Checker, iso_date, join_locations, need, register
from ..models import Job

PAGE = "https://www.shopify.com/careers"
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
        return f"GET {PAGE} (embedded loader data, every posting)"

    def fetch(self, http, s, ctx=None):
        html = http.get_text(PAGE, headers={"Accept": "text/html"})
        chunks = [json.loads(m.group(1)) for m in ENQUEUE.finditer(html)]
        need(chunks, "shopify: no streamController.enqueue(...) data on /careers")
        flat = json.loads(chunks[0].split("\n", 1)[0])
        need(isinstance(flat, list) and flat, "shopify: turbo-stream root is not an array")
        root = decode_turbo_stream(flat)
        loader = ((root or {}).get("loaderData") or {}).get("($locale)/careers") or {}
        rows = loader.get("jobPostingsWithJobs")
        need(isinstance(rows, list), "shopify: loaderData['($locale)/careers'].jobPostingsWithJobs missing")
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
