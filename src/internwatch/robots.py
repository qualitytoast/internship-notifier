"""robots.txt parsing and matching per RFC 9309 (wildcards, `$` anchors, longest match wins)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlsplit

PRODUCT_TOKEN = "internwatch"


@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, pattern)
    crawl_delay: float | None = None


@lru_cache(maxsize=4096)
def _compile(pattern: str) -> re.Pattern:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    return re.compile(regex + ("$" if anchored else ""))


def _normalize(path: str) -> str:
    # Percent-encoding differences are ignored by comparing on the raw path; good enough for job feeds.
    return path or "/"


class RobotsRules:
    """Parsed robots.txt. `allow_all`/`disallow_all` cover missing (4xx) and unreachable (5xx) files."""

    def __init__(self, text: str = "", *, allow_all: bool = False, disallow_all: bool = False):
        self.allow_all = allow_all
        self.disallow_all = disallow_all
        self.groups: list[Group] = []
        if text:
            self._parse(text)

    def _parse(self, text: str) -> None:
        current: Group | None = None
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if current is None or not last_was_agent:
                    current = Group()
                    self.groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if current is None:
                continue
            if key in ("allow", "disallow"):
                if value:  # an empty Disallow matches nothing
                    current.rules.append((key == "allow", value))
            elif key == "crawl-delay":
                try:
                    current.crawl_delay = float(value)
                except ValueError:
                    pass

    def _groups_for(self, token: str) -> list[Group]:
        token = token.lower()
        specific = [g for g in self.groups if any(a != "*" and a in token for a in g.agents)]
        if specific:
            return specific
        return [g for g in self.groups if "*" in g.agents]

    def allowed(self, url: str, token: str = PRODUCT_TOKEN) -> bool:
        if self.allow_all:
            return True
        if self.disallow_all:
            return False
        parts = urlsplit(url)
        path = _normalize(parts.path + (f"?{parts.query}" if parts.query else ""))
        best: tuple[int, bool] | None = None  # (pattern length, allow)
        for group in self._groups_for(token):
            for allow, pattern in group.rules:
                if _compile(pattern).match(path):
                    cand = (len(pattern), allow)
                    if best is None or cand[0] > best[0] or (cand[0] == best[0] and allow):
                        best = cand
        return True if best is None else best[1]

    def crawl_delay(self, token: str = PRODUCT_TOKEN) -> float | None:
        delays = [g.crawl_delay for g in self._groups_for(token) if g.crawl_delay is not None]
        return max(delays) if delays else None

    def matching_rule(self, url: str, token: str = PRODUCT_TOKEN) -> str:
        """Human-readable explanation of the rule that decided `url` (for reports)."""
        if self.allow_all:
            return "no robots.txt (allowed)"
        if self.disallow_all:
            return "robots.txt unreachable (treated as disallow)"
        parts = urlsplit(url)
        path = _normalize(parts.path + (f"?{parts.query}" if parts.query else ""))
        best = None
        for group in self._groups_for(token):
            for allow, pattern in group.rules:
                if _compile(pattern).match(path) and (best is None or len(pattern) > len(best[1]) or (len(pattern) == len(best[1]) and allow)):
                    best = (allow, pattern)
        if best is None:
            return "no matching rule (allowed)"
        return f"{'Allow' if best[0] else 'Disallow'}: {best[1]}"


def from_response(status: int | None, text: str) -> RobotsRules:
    """Build rules from a robots.txt fetch result following RFC 9309 status handling."""
    if status is None or status >= 500:
        return RobotsRules(disallow_all=True)
    if 400 <= status < 500:
        return RobotsRules(allow_all=True)
    if text.lstrip().lower().startswith("<!doctype html") or text.lstrip().lower().startswith("<html"):
        return RobotsRules(allow_all=True)  # an HTML page served at /robots.txt has no rules
    return RobotsRules(text)
