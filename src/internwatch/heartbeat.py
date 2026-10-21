"""Dead man's switch: ping healthchecks.io at the start and end of every run.

If pings stop (machine down, timer broken, run hung), healthchecks.io emails you — even though
this machine can't. Configure the check with period 15 min and grace 45 min (see README).
"""
from __future__ import annotations

import logging

import httpx

from .config import Config

log = logging.getLogger(__name__)


class Heartbeat:
    def __init__(self, cfg: Config):
        self.url = cfg.secrets.healthchecks_url.rstrip("/") if cfg.secrets.healthchecks_ready else ""

    def _ping(self, suffix: str = "", body: str = "") -> None:
        if not self.url:
            return
        try:
            httpx.post(self.url + suffix, content=body.encode()[:10_000], timeout=10)
        except httpx.HTTPError as e:  # never let monitoring break a run
            log.warning("healthchecks ping %s failed: %s", suffix or "/", e)

    def start(self) -> None:
        self._ping("/start")

    def success(self, summary: str = "") -> None:
        self._ping("", summary)

    def fail(self, summary: str = "") -> None:
        self._ping("/fail", summary)
