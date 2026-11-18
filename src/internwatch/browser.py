"""GET a page through the real Google Chrome, for the sites that refuse every client but a browser.

Citadel's sitemaps (since 2026-11-13) answer scripts with a Cloudflare challenge, but give real Chrome the XML at once
(2026-11-17 trial: 200 on both sites, no challenge shown). Chrome's hidden (headless) mode names itself HeadlessChrome
and was challenged, so this opens a normal window and minimizes it at once (macOS keeps part of a window on screen,
so it can't be moved off it; a minimized page still counts as visible). Nothing hides that Chrome is automated, and a
challenge is never clicked: if Chrome is still shown one after the wait, that answer (403) is what the caller gets.

Each fetch is its own Chrome with a fresh temporary profile, one at a time across all threads. Chrome is always
closed and its profile deleted before the fetch returns, even on an error: no window or profile outlives it.
Only Http.request calls this, so robots.txt, pacing, time budgets and record/replay apply as for any request.

Every profile (these and chrome_session.py's) records the process that owns it (new_profile). A run that is killed
can't close its Chrome; the next run stops it and deletes its profile (sweep_leftovers), and touches nothing whose
owner is still running.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .models import FetchError

log = logging.getLogger(__name__)

PROFILE_PREFIX = "internwatch-chrome-"
OWNER_FILE = "internwatch-owner.json"   # in each profile: {"pid": …, "started": …} of the process that made it
WINDOW_ARGS = ["--window-size=800,600"]
_LOCK = threading.Lock()


class BrowserUnavailable(FetchError):
    """Chrome can't be driven here (Playwright or Google Chrome missing): retrying won't help."""


def fetch(url: str, timeout: float = 45.0):
    """The page's answer as an http.Resp: the first non-redirect answer below 400 the main frame gets within
    `timeout` seconds (a challenge that passes on its own reloads the page), else the last answer it got."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise BrowserUnavailable("fetching through Chrome needs Playwright: .venv/bin/pip install -e .") from e
    with _LOCK:
        profile = new_profile()
        try:
            with sync_playwright() as pw:
                try:
                    ctx = pw.chromium.launch_persistent_context(str(profile), channel="chrome", headless=False,
                                                                no_viewport=True, args=WINDOW_ARGS)
                except PlaywrightError as e:
                    msg = str(e).splitlines()[0][:200]
                    if "chrome" in msg.lower() and ("not found" in msg.lower() or "install" in msg.lower()):
                        raise BrowserUnavailable(f"Google Chrome could not be started: {msg}") from e
                    raise FetchError(f"Chrome could not be started for {url[:160]}: {msg}") from e
                try:
                    return _load(ctx, url, timeout)
                except PlaywrightError as e:
                    raise FetchError(f"Chrome failed on {url[:160]}: {str(e).splitlines()[0][:200]}") from e
                finally:
                    ctx.close()
        finally:
            _remove(profile)


def _load(ctx, url: str, timeout: float):
    from .http import Resp

    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    _minimize(ctx, page)
    answers = []
    page.on("response", lambda r: answers.append(r)
            if r.frame == page.main_frame and r.request.is_navigation_request() and not 300 <= r.status < 400
            else None)
    end = time.monotonic() + timeout
    page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
    while True:
        ok = next((r for r in answers if r.status < 400), None)
        if ok is not None or time.monotonic() >= end:
            break
        page.wait_for_timeout(500)
    r = ok or (answers[-1] if answers else None)
    if r is None:
        raise FetchError(f"Chrome got no answer for {url[:160]}")
    return Resp(r.status, r.url, {k.lower(): v for k, v in r.headers.items()}, r.body())


def _minimize(ctx, page) -> None:
    cdp = ctx.new_cdp_session(page)
    try:
        wid = cdp.send("Browser.getWindowForTarget")["windowId"]
        cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "minimized"}})
    finally:
        cdp.detach()


def new_profile() -> Path:
    """A fresh temporary Chrome profile that records its owner: this process's PID and start time (a PID alone can
    be reused by another process once this one is gone)."""
    profile = Path(tempfile.mkdtemp(prefix=PROFILE_PREFIX))
    (profile / OWNER_FILE).write_text(json.dumps({"pid": os.getpid(), "started": _started(os.getpid())}))
    return profile


def _started(pid: int) -> str | None:
    """When a process started, as ps prints it; "" when no such process runs; None when ps can't say."""
    try:
        r = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else ""


def owner_running(owner: dict) -> bool:
    """Whether the process that made a profile still runs. Unsure (no start time on record, or ps can't say) counts
    as running: a profile is never taken from a live process."""
    pid, started = owner.get("pid"), owner.get("started")
    if not isinstance(pid, int) or not started:
        return True
    now = _started(pid)
    return now is None or now == started


def sweep_leftovers(root: Path | None = None) -> list[Path]:
    """Chrome left by runs that were killed: every profile whose owner no longer runs is stopped and deleted. A
    profile whose owner still runs (another run, a manual command, a proof morning on a copy) or that records no
    owner (made before owners were recorded, or this very moment) is left alone. Returns the profiles removed."""
    gone = []
    for profile in sorted(Path(root or tempfile.gettempdir()).glob(PROFILE_PREFIX + "*")):
        try:
            owner = json.loads((profile / OWNER_FILE).read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(owner, dict) or owner_running(owner):
            continue
        log.warning("browser: Chrome profile %s was left by process %s, which no longer runs: removed",
                    profile, owner.get("pid"))
        _remove(profile)
        gone.append(profile)
    return gone


def _remove(profile: Path) -> None:
    """Whatever is left of this fetch's Chrome: any process still using the profile, then the profile itself."""
    if subprocess.run(["pkill", "-f", str(profile)], capture_output=True).returncode == 0:
        log.warning("browser: a Chrome process outlived its fetch and was stopped (%s)", profile)
        time.sleep(1)
    shutil.rmtree(profile, ignore_errors=True)
