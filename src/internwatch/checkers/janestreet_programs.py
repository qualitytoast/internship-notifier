"""Jane Street's student programs (FTTP, FOCUS, INSIGHT, Bridge, …): janestreet.com/jobs/programs-endpoint.json.

The programs are not Greenhouse posts: each session is applied for through a janestreet.com form (/apply-<session>),
so the `jane-street` Greenhouse checker never sees them.
GET https://www.janestreet.com/jobs/programs-endpoint.json →
  [{name, location_filter, category_filter, sessions: [{id, office, dates, apply_page, deadline (ISO, with offset),
    formatted_deadline, preuniversity, availability_label, …}]}]
Only sessions taking applications are returned: an apply page and a deadline still ahead. The file also keeps past
sessions and events without a form (happy hours, puzzle events); high-school programs (preuniversity) are skipped.
A session id is reused every year ("fttp-nyc"), so the job id adds the deadline: the next round is a new job.
Deadlines are judged as of the response: now, or when a replayed recording was made (so fixtures don't age).
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..adapters.base import Checker, need, register
from ..models import Job

URL = "https://www.janestreet.com/jobs/programs-endpoint.json"
SITE = "https://www.janestreet.com"
OFFICES = {"NYC": "New York, NY", "LDN": "London, United Kingdom", "HKG": "Hong Kong", "SGP": "Singapore",
           "SF": "San Francisco, CA", "Sydney": "Sydney, Australia", "ON-CAMPUS": "On campus"}


def as_of(http) -> datetime:
    """The response's moment: now, or when a replayed recording was made."""
    meta = getattr(getattr(http, "replay", None), "meta", None) or {}
    if meta.get("recorded_at"):
        return datetime.fromisoformat(meta["recorded_at"].replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def place(office: str) -> str:
    if office in OFFICES:
        return OFFICES[office]
    return "; ".join(OFFICES.get(p, p) for p in office.split("-") if p)  # "NYC-LDN-HKG"


@register
class JaneStreetPrograms(Checker):
    type = "janestreet_programs"

    def describe(self, s):
        return f"GET {URL} (sessions with an apply form and a deadline still ahead)"

    def fetch(self, http, s, ctx=None):
        data = http.get_json(URL)
        need(isinstance(data, list) and data, "janestreet_programs: programs-endpoint.json is not a list of programs")
        now = as_of(http)
        jobs = []
        for p in data:
            need(isinstance(p, dict) and p.get("name"), "janestreet_programs: program without a name")
            for x in p.get("sessions") or []:
                if not (isinstance(x, dict) and x.get("id") and x.get("apply_page") and x.get("deadline")):
                    continue
                if x.get("preuniversity"):
                    continue
                try:
                    deadline = datetime.fromisoformat(str(x["deadline"]).replace("Z", "+00:00"))
                except ValueError:
                    deadline = None
                need(deadline is not None, f"janestreet_programs: unreadable deadline {x['deadline']!r} ({x['id']})")
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                if deadline < now:
                    continue
                apply = x["apply_page"] if x["apply_page"].startswith("http") else SITE + x["apply_page"]
                when = f": {x['dates']}" if x.get("dates") else ""
                due = f"Apply by {x['formatted_deadline']}. " if x.get("formatted_deadline") else ""
                name = p["name"] if "program" in p["name"].lower() else f"{p['name']} program"
                jobs.append(Job(
                    id=f"{x['id']}:{str(x['deadline'])[:10]}",
                    title=f"{name} ({x.get('office') or 'Jane Street'}){when}",
                    location=place(x.get("office") or ""),
                    url=apply,
                    snippet=f"{due}{x.get('availability_label') or ''}",
                    employment_type="Program",
                ))
        return jobs
