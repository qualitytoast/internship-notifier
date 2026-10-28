"""Ashby public posting API (https://developers.ashbyhq.com/docs/public-job-posting-api).

settings: board: <organization hosted jobs page name>   e.g. openai, mistral.ai, Talos-Trading
          (or boards: [Sierra, sierra-jp] for companies with several boards)
          mode: hosted   for orgs whose posting API answers 404 (e.g. whatnot): read the hosted page instead
          watch_ids: [<posting id>, …]   unlisted postings to read one by one (the API and the hosted board leave
                         them out, though they take applications: Aurora, Deepgram). The runner adds the ids of
                         SimplifyJobs rows when learn_ids is true.
GET https://api.ashbyhq.com/posting-api/job-board/<board>?includeCompensation=false → {"jobs": [...]}
hosted: GET https://jobs.ashbyhq.com/<board> → window.__appData = {jobBoard: {jobPostings: [...], teams: [...]}}
watched: GET https://jobs.ashbyhq.com/<board>/<id> → window.__appData.posting (404, or no posting, when closed)
(jobs.ashbyhq.com/api/* is disallowed by robots.txt; the public API and the hosted pages are allowed.)
With several boards, one that fails marks the poll degraded and the others are still read; all failing fails.
A watched posting that can't be read marks the poll degraded; one that is closed is left out.
"""
from __future__ import annotations

import json

from ..models import CheckerError, Job
from .base import Checker, degrade, html_text, iso_date, join_locations, need, need_list, register

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
        boards = self.boards(s)
        errors: list[CheckerError] = []
        for board in boards:
            one = {**s, "board": board}
            try:
                got = self._hosted(http, one) if s.get("mode") == "hosted" else self._api(http, one)
            except CheckerError as e:
                if ctx is None:
                    raise
                errors.append(e)  # the other boards are still read
                continue
            for j in got:
                if j.id not in seen:
                    seen.add(j.id)
                    jobs.append(j)
        if len(errors) == len(boards):
            raise errors[0]
        if errors:
            degrade(ctx, "; ".join(str(e) for e in errors))
        if s.get("watch_ids"):
            jobs += self._watched(http, s, ctx, boards[0], {j.id for j in jobs})
        return jobs

    def _watched(self, http, s, ctx, board: str, listed: set[str]) -> list[Job]:
        out, opened, closed = [], [], []
        for wid in dict.fromkeys(str(x) for x in s["watch_ids"]):
            if wid in listed:
                continue
            try:
                resp = http.get(f"{HOSTED.format(board=board)}/{wid}", ok_statuses=(404,))
                p = None if resp.status == 404 else self._app_data(resp.text, board).get("posting")
            except CheckerError as e:
                if ctx is None:
                    raise
                degrade(ctx, f"ashby:{board}: watched posting {wid}: {e}")
                continue
            if not (isinstance(p, dict) and p.get("title")):
                closed.append(wid)
                continue
            opened.append(wid)
            loc = join_locations([p.get("locationName")] + list(p.get("secondaryLocationNames") or []))
            if p.get("workplaceType") == "Remote" and "remote" not in loc.lower():
                loc = f"{loc}; Remote" if loc else "Remote"
            out.append(Job(id=wid, title=p["title"], location=loc, url=f"https://jobs.ashbyhq.com/{board}/{wid}",
                           posted=iso_date(p.get("publishedDate")), snippet=html_text(p.get("descriptionHtml")),
                           department=p.get("departmentName") or "", employment_type=p.get("employmentType") or "",
                           extra={"unlisted": True}))
        if ctx is not None:
            ctx.state["watch_open"] = opened
            ctx.state["watch_closed"] = sorted(set(ctx.state.get("watch_closed") or []) | set(closed))[-300:]
        return out

    def _app_data(self, html: str, board: str) -> dict:
        i = html.find("window.__appData = ")
        need(i >= 0, f"ashby:{board}: hosted page has no window.__appData")
        try:
            data, _ = json.JSONDecoder().raw_decode(html, i + len("window.__appData = "))
        except ValueError:
            need(False, f"ashby:{board}: window.__appData is not JSON")
        return data or {}

    def _hosted(self, http, s):
        data = self._app_data(http.get_text(HOSTED.format(board=s["board"])), s["board"])
        board = data.get("jobBoard") or {}
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
