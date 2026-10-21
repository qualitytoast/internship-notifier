"""Lever postings API (https://github.com/lever/postings-api).

settings: site: <name>   (region: eu  for api.eu.lever.co)
GET https://api.lever.co/v0/postings/<site>?mode=json → [ {id, text, categories, hostedUrl, createdAt, descriptionPlain, …} ]
Descriptions are included, so no detail call is needed.
"""
from __future__ import annotations

from ..models import Job
from .base import Checker, iso_date, need, register


@register
class Lever(Checker):
    type = "lever"

    def url(self, s):
        host = "api.eu.lever.co" if s.get("region") == "eu" else "api.lever.co"
        return f"https://{host}/v0/postings/{s['site']}?mode=json"

    def describe(self, s):
        return self.url(s)

    def fetch(self, http, s, ctx=None):
        data = http.get_json(self.url(s))
        need(isinstance(data, list), f"lever:{s['site']}: expected a list, got {type(data).__name__}")
        jobs = []
        for p in data:
            need(isinstance(p, dict) and p.get("id") and "text" in p, f"lever:{s['site']}: posting without id/text")
            cat = p.get("categories") or {}
            locs = cat.get("allLocations") or ([cat["location"]] if cat.get("location") else [])
            if p.get("country") and locs:
                locs = [f"{loc}, {p['country']}" if p["country"] not in loc else loc for loc in locs]
            jobs.append(Job(
                id=p["id"],
                title=p.get("text") or "",
                location="; ".join(locs),
                url=p.get("hostedUrl") or "",
                posted=iso_date(p.get("createdAt")),
                snippet=" ".join(x for x in (p.get("descriptionPlain"), p.get("additionalPlain")) if x),
                department=" / ".join(x for x in (cat.get("department"), cat.get("team")) if x),
                employment_type=cat.get("commitment") or "",
            ))
        return jobs
