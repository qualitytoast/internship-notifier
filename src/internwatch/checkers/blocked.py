"""Placeholder for companies marked `status: blocked` in companies.yaml (their site disallows automated access).

They are never polled; the SimplifyJobs cross-check covers them and the fallback in their entry says what
else to do (usually: sign up for the company's own job-alert emails).
"""
from __future__ import annotations

from ..adapters.base import Checker, register
from ..models import RobotsBlocked


@register
class Blocked(Checker):
    type = "blocked"

    def describe(self, s):
        return "not polled (automated access disallowed)"

    def fetch(self, http, s, ctx=None):
        raise RobotsBlocked(s.get("reason", "this company is blocked; it is covered by the SimplifyJobs cross-check"))
