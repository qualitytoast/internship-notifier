"""Normalized data shared by every checker."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field as dc_field

_WS = re.compile(r"\s+")


def clean(text: str | None, limit: int | None = None) -> str:
    """Collapse whitespace; optionally truncate."""
    out = _WS.sub(" ", text or "").strip()
    return out[:limit] if limit else out


@dataclass
class Job:
    """One posting as returned by a checker (before filtering).

    id       stable identifier within the company (the hiring system's job/requisition id)
    title    posting title
    location human-readable location(s), several joined with "; "
    url      direct link to the posting / apply page
    posted   ISO date (YYYY-MM-DD) if the source provides one
    snippet  plain-text description excerpt (used for term/field detection)
    """

    id: str
    title: str
    location: str = ""
    url: str = ""
    posted: str | None = None
    snippet: str = ""
    department: str = ""
    employment_type: str = ""
    extra: dict = dc_field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id).strip()
        self.title = clean(self.title)
        self.location = clean(self.location)
        self.snippet = clean(self.snippet, 4000)
        self.department = clean(self.department)
        self.employment_type = clean(self.employment_type)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Match:
    """Filter decision for one job."""

    matched: bool
    unsure: bool = False
    term: str = "unspecified"
    field: str = ""
    tags: list[str] = dc_field(default_factory=list)
    reasons: list[str] = dc_field(default_factory=list)
    needs_detail: bool = False  # role looks like an internship but the description was not available


class CheckerError(Exception):
    """Base class for checker failures that should be reported as health problems."""

    kind = "error"


class ShapeError(CheckerError):
    """The source answered, but not in the structure the checker expects."""

    kind = "shape"


class RobotsBlocked(CheckerError):
    """robots.txt disallows the URL the checker needs."""

    kind = "blocked"


class FetchError(CheckerError):
    """Network error, timeout or HTTP error status after retries."""

    kind = "fetch"


class CheckTimeout(FetchError):
    """The checker ran past its time budget (or every attempt of a request timed out)."""

    kind = "timeout"


class NotModified(Exception):
    """The source answered 304 Not Modified: nothing changed since the last poll.

    Not an error: the runner keeps the job list it already has.
    """
