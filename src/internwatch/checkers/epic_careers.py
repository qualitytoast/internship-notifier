"""Epic (Epic Systems): careers.epic.com renders every open job into its Next.js payload.

GET https://careers.epic.com/jobs/ → self.__next_f.push([1,"…"]) chunks (React Server Components data)
  "allOpenJobs": [{"id": "30318"}, …]              every open, published job, in display order
  "avaturePositions": {"30318": {externalName, shortSummary, background, isOpen, isPublished}, …}
The system of record is Avature (epic.avature.net), whose portal is robots-disallowed: its job links go in
emails but are never fetched. Epic hires on its campus in Verona, WI, and the data has no location field.
See discovery/notes/epic-systems.md.
"""
from __future__ import annotations

import json
import re

from ..adapters.base import Checker, need, register
from ..models import Job

PAGE = "https://careers.epic.com/jobs/"
PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', re.S)


def _value_after(text: str, key: str):
    i = text.find(f'"{key}":')
    need(i >= 0, f"epic: '{key}' not found in the page data")
    return json.JSONDecoder().raw_decode(text, i + len(key) + 3)[0]


@register
class EpicCareers(Checker):
    type = "epic-careers"

    def describe(self, s):
        return f"GET {PAGE} (embedded allOpenJobs + avaturePositions)"

    def fetch(self, http, s, ctx=None):
        html = http.get_text(s.get("url", PAGE))
        text = "".join(json.loads(m.group(1)) for m in PUSH.finditer(html))
        need(text, "epic: no Next.js payload (self.__next_f) on the jobs page")
        open_jobs = _value_after(text, "allOpenJobs")
        positions = _value_after(text, "avaturePositions")
        need(isinstance(open_jobs, list) and isinstance(positions, dict), "epic: unexpected payload shape")
        default_loc = s.get("default_location", "Verona, WI, United States")
        jobs = []
        for row in open_jobs:
            jid = str((row or {}).get("id") or "")
            p = positions.get(jid)
            need(jid and isinstance(p, dict) and p.get("externalName"), f"epic: open job {jid!r} has no position data")
            title = p["externalName"]
            jobs.append(Job(id=jid, title=title, location=default_loc,
                            url=f"https://epic.avature.net/Careers/FolderDetail/{re.sub(r'[^A-Za-z0-9]', '-', title)}/{jid}",
                            snippet=" ".join(x for x in (p.get("shortSummary"), p.get("background")) if x)))
        return jobs
