"""Ashby public posting API (https://developers.ashbyhq.com/docs/public-job-posting-api).

settings: board: <organization hosted jobs page name>   e.g. openai, mistral.ai, Talos-Trading
          (or boards: [Sierra, sierra-jp] for companies with several boards)
          mode: hosted   for orgs whose posting API answers 404 (e.g. whatnot): read the hosted page instead
GET https://api.ashbyhq.com/posting-api/job-board/<board>?includeCompensation=false → {"jobs": [...]}
hosted: GET https://jobs.ashbyhq.com/<board> → window.__appData = {jobBoard: {jobPostings: [...], teams: [...]}}
(jobs.ashbyhq.com/api/* is disallowed by robots.txt; the public API and the hosted page are allowed.)
"""
from __future__ import annotations

import json

from ..models import Job
from .base import Checker, iso_date, join_locations, need, need_list, register

API = "https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=false"
HOSTED = "https://jobs.ashbyhq.com/{board}"


def _country(addr) -> str:
    try:
        return addr["postalAddress"].get("addressCountry") or ""
    except (KeyError, TypeError, AttributeError):
        return ""


@register
class Ashby(Checker):
    type = "ashby"

    def boards(self, s):
        return list(s.get("boards") or [s["board"]])

    def describe(self, s):
        return ", ".join((HOSTED if s.get("mode") == "hosted" else API).format(board=b) for b in self.boards(s))

    def fetch(self, http, s, ctx=None):
        jobs, seen = [], set()
        for board in self.boards(s):
            one = {**s, "board": board}
            for j in (self._hosted(http, one) if s.get("mode") == "hosted" else self._api(http, one)):
                if j.id not in seen:
                    seen.add(j.id)
                    jobs.append(j)
        return jobs

    def _hosted(self, http, s):
        html = http.get_text(HOSTED.format(board=s["board"]))
        i = html.find("window.__appData = ")
        need(i >= 0, f"ashby:{s['board']}: hosted page has no window.__appData")
        try:
            data, _ = json.JSONDecoder().raw_decode(html, i + len("window.__appData = "))
        except ValueError:
            need(False, f"ashby:{s['board']}: window.__appData is not JSON")
        board = (data or {}).get("jobBoard") or {}
        posts = board.get("jobPostings")
        need(isinstance(posts, list), f"ashby:{s['board']}: jobBoard.jobPostings missing")
        teams = {t.get("id"): t.get("name", "") for t in board.get("teams") or []}
        jobs = []
        for p in posts:
            need(p.get("id") and "title" in p, f"ashby:{s['board']}: posting without id/title")
            locs = [p.get("locationName")] + [x.get("locationName") for x in p.get("secondaryLocations") or []]
            loc = join_locations(locs)
            if p.get("workplaceType") == "Remote" and "remote" not in loc.lower():
                loc = f"{loc}; Remote" if loc else "Remote"
            jobs.append(Job(id=p["id"], title=p.get("title") or "", location=loc,
                            url=f"https://jobs.ashbyhq.com/{s['board']}/{p['id']}",
                            posted=iso_date(p.get("publishedDate") or p.get("updatedAt")),
                            department=teams.get(p.get("teamId"), ""), employment_type=p.get("employmentType") or ""))
        return jobs

    def _api(self, http, s):
        data = http.get_json(API.format(board=s["board"]))
        items = need_list(data, "jobs", f"ashby:{s['board']}")
        jobs = []
        for j in items:
            need(j.get("id") and "title" in j, f"ashby:{s['board']}: job without id/title")
            if j.get("isListed") is False:
                continue  # unlisted postings are not on the public board
            locs = [j.get("location")] + [x.get("location") for x in j.get("secondaryLocations") or []]
            country = _country(j.get("address"))
            loc = join_locations(locs)
            if country and country.lower() not in loc.lower():
                loc = f"{loc} ({country})" if loc else country
            if j.get("isRemote") and "remote" not in loc.lower():
                loc = f"{loc}; Remote" if loc else "Remote"
            jobs.append(Job(
                id=j["id"],
                title=j.get("title") or "",
                location=loc,
                url=j.get("jobUrl") or "",
                posted=iso_date(j.get("publishedAt")),
                snippet=j.get("descriptionPlain") or "",
                department=" / ".join(x for x in (j.get("department"), j.get("team")) if x),
                employment_type=j.get("employmentType") or "",
            ))
        return jobs
