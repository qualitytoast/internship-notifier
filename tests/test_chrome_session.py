"""Workday through the run's Chrome (chrome_session.py, Http's send step): the same request httpx would send, the same
answer, the same failures; Chrome's tabs, robots.txt, closing and the leftover sweep.

The first part uses a stand-in for Chrome. The tests marked `chrome` drive a real Google Chrome against servers on
127.0.0.1 and run only with INTERNWATCH_CHROME_TESTS=1."""
from __future__ import annotations

import functools
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest

from internwatch import browser, chrome_session
from internwatch import http as httpmod
from internwatch.browser import BrowserUnavailable
from internwatch.chrome_session import ChromeTimeout, TabClosed
from internwatch.http import Cassette, HostGate, HostGroup, Http, HttpSettings, Resp
from internwatch.models import CheckTimeout, FetchError, RobotsBlocked, ShapeError

WD = "https://acme.wd1.myworkdayjobs.com"
JOBS = WD + "/wday/cxs/acme/External/jobs"
DETAIL = WD + "/wday/cxs/acme/External/job/Austin-TX/Software-Intern_R123"
WD_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
BODY = {"appliedFacets": {}, "limit": 20, "offset": 40, "searchText": ""}
ROBOTS = b"User-agent: *\nDisallow: /wday/cxs/acme/Secret/\n"

# The headers Chrome sets itself (written here, as the plan asks; the user approved each): User-Agent, Accept-Encoding,
# Host, Connection, Content-Length (httpx sends them, Chrome replaces them), Cookie (each has its own session with the
# site), Origin, Referer, sec-ch-ua, sec-ch-ua-mobile, sec-ch-ua-platform, sec-fetch-dest, sec-fetch-mode,
# sec-fetch-site (only Chrome sends them), and Cache-Control and Pragma (Chrome adds "no-cache" because each request
# skips its cache). Any other difference between what httpx sends and what Chrome is given, or sends, fails.
CHROME_SETS = {"user-agent", "accept-encoding", "host", "connection", "content-length", "cookie", "origin", "referer",
               "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform", "sec-fetch-dest", "sec-fetch-mode",
               "sec-fetch-site", "cache-control", "pragma"}


def wd_group(browser=True, **kw):
    return HostGroup("workday", ("myworkdayjobs.com", "myworkdaysite.com"), per_second=1000, pause_on_429=(0.01,),
                     browser=browser, **kw)


class FakeChrome:
    """Stands in for ChromeSession: answers from a list (a Resp, an exception, or a function of the request)."""

    def __init__(self, *answers, robots=None):
        self.answers = list(answers)
        self.robots_answers = list(robots or [])
        self.tabs: set[str] = set()
        self.calls: list[tuple] = []
        self.closed = False

    def _tab_answer(self, origin):
        return Resp(200, origin + "/robots.txt", {"content-type": "text/plain"}, ROBOTS)

    def ensure_tab(self, origin, timeout):
        self.calls.append(("tab", origin))
        if origin in self.tabs:
            return None
        self.tabs.add(origin)
        return self._tab_answer(origin)

    def request(self, method, url, headers, body, timeout):
        self.calls.append(("request", method, url, list(headers), body))
        a = self.answers.pop(0)
        if isinstance(a, TabClosed):
            self.tabs.discard(httpmod.urlsplit(url).scheme + "://" + httpmod.urlsplit(url).netloc)
        if isinstance(a, Exception):
            raise a
        return a(method, url) if callable(a) else a

    def robots(self, url, headers, timeout):
        self.calls.append(("robots", url, list(headers)))
        origin = url.rsplit("/robots.txt", 1)[0]
        self.tabs.add(origin)
        if self.robots_answers:
            a = self.robots_answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return a
        return self._tab_answer(origin)

    def close(self):
        self.closed = True

    def requests(self):
        return [c for c in self.calls if c[0] == "request"]


def ok(content=b'{"total": 1, "jobPostings": []}', status=200, headers=None):
    return lambda method, url: Resp(status, url, dict(headers or {"content-type": "application/json"}), content)


def chrome_http(monkeypatch, fake, *, robots=False, retries=3, record=None, cache_dir=None, deadline=None, mock=None):
    """An Http whose Workday group reads through `fake`; httpx answers other hosts through `mock` (none: they fail)."""
    monkeypatch.setattr(chrome_session, "ChromeSession", lambda: fake)
    with_transport(monkeypatch, mock or no_httpx)
    return Http(HttpSettings(backoff_base=0.001, min_interval=0, retries=retries, respect_robots=robots,
                             host_groups=(wd_group(),)), gate=HostGate(cache_dir), record=record, deadline=deadline)


def httpx_http(monkeypatch, handler, *, robots=False, record=None):
    """The same Http with the Workday group read by httpx (as before), answered by `handler`."""
    with_transport(monkeypatch, handler)
    return Http(HttpSettings(backoff_base=0.001, min_interval=0, respect_robots=robots,
                             host_groups=(wd_group(browser=False),)), gate=HostGate(), record=record)


def with_transport(monkeypatch, handler):
    """Http's own httpx client (its user agent, language, TLS settings), answered by `handler` instead of the net."""
    monkeypatch.setattr(httpmod.httpx, "Client",
                        functools.partial(httpx.Client, transport=httpx.MockTransport(handler)))


def no_httpx(req):
    raise AssertionError(f"httpx was asked for {req.method} {req.url}")


# The same request ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("method,url,kw", [
    ("POST", JOBS, {"json": BODY, "headers": WD_HEADERS}),                       # the job list
    ("GET", DETAIL, {"headers": WD_HEADERS}),                                    # a job's detail
    ("GET", WD + "/en-US/External", {"headers": {"Accept": "text/html,*/*;q=0.8"}}),  # the careers-page scan
    ("GET", WD + "/en-US/External/jobs", {"params": {"q": "intern", "a": "1"}}),  # a query, sorted as always
    ("POST", WD + "/form", {"data": {"b": "2", "a": "1"}}),                      # a form body
])
def test_a_workday_request_reaches_chrome_exactly_as_httpx_would_send_it(monkeypatch, method, url, kw):
    sent = []

    def handler(req):
        sent.append(req)
        return httpx.Response(200, json={"total": 0})

    httpx_http(monkeypatch, handler).request(method, url, **kw)
    (old,) = sent

    fake = FakeChrome(ok())
    chrome_http(monkeypatch, fake).request(method, url, **kw)
    (_, c_method, c_url, c_headers, c_body) = fake.requests()[0]

    assert (c_method, c_url) == (old.method, str(old.url))
    assert (c_body or b"") == old.content
    given = {k.lower(): v for k, v in c_headers}
    assert len(given) == len(c_headers)                              # no header twice
    expected = {k.lower(): v for k, v in old.headers.multi_items() if k.lower() not in CHROME_SETS}
    assert given == expected
    assert {"accept", "accept-language"} <= set(given)               # what Workday's answers depend on reaches Chrome
    assert given["accept-language"] == "en-US,en;q=0.9"


def test_chromes_answer_is_the_resp_httpx_would_give(monkeypatch):
    content = '{"total": 2, "jobPostings": [{"title": "Intern – Zürich"}]}'.encode()
    headers = {"content-type": "application/json; charset=utf-8", "content-length": str(len(content)),
               "x-wd-request-id": "abc", "cf-ray": "1-MCI"}
    old = httpx_http(monkeypatch, lambda req: httpx.Response(200, headers=headers, content=content)).post(
        JOBS, json=BODY, headers=WD_HEADERS)
    new = chrome_http(monkeypatch, FakeChrome(ok(content, headers=headers))).post(JOBS, json=BODY, headers=WD_HEADERS)
    assert (new.status, new.url, new.headers, new.content) == (old.status, old.url, old.headers, old.content)
    assert new.json() == old.json() and new.text == old.text


def test_non_workday_hosts_never_touch_chrome(monkeypatch):
    fake = FakeChrome()
    h = chrome_http(monkeypatch, fake, mock=lambda req: httpx.Response(200, json={"jobs": []}))
    assert h.get_json("https://boards-api.greenhouse.io/v1/boards/acme/jobs") == {"jobs": []}
    assert fake.calls == []


def test_a_recording_through_chrome_is_the_same_as_one_through_httpx(monkeypatch):
    content = b'{"total": 1, "jobPostings": [{"title": "Intern"}]}'
    headers = {"content-type": "application/json", "etag": "W/1"}
    old_rec, new_rec = Cassette(), Cassette()
    httpx_http(monkeypatch, lambda req: httpx.Response(200, headers=headers, content=content),
               record=old_rec).post(JOBS, json=BODY, headers=WD_HEADERS)
    chrome_http(monkeypatch, FakeChrome(ok(content, headers=headers)), record=new_rec).post(
        JOBS, json=BODY, headers=WD_HEADERS)
    assert json.dumps(new_rec.exchanges, sort_keys=True) == json.dumps(old_rec.exchanges, sort_keys=True)


# Tabs and turns --------------------------------------------------------------------------------------------------

def count_turns(monkeypatch, h):
    turns = {"group": 0, "host": 0}
    wait_group, wait_turn = h.gate.wait_group, h.gate.wait_turn

    def g(group, deadline=None):
        turns["group"] += 1
        return wait_group(group, deadline)

    def t(host, interval):
        turns["host"] += 1
        return wait_turn(host, interval)
    monkeypatch.setattr(h.gate, "wait_group", g)
    monkeypatch.setattr(h.gate, "wait_turn", t)
    return turns


def test_opening_a_sites_tab_takes_a_turn_of_its_own(monkeypatch):
    fake = FakeChrome(ok(), ok())
    h = chrome_http(monkeypatch, fake)
    turns = count_turns(monkeypatch, h)
    h.post(JOBS, json=BODY, headers=WD_HEADERS)
    assert turns == {"group": 2, "host": 2}           # the tab's robots.txt load, then the request
    h.post(JOBS, json=BODY, headers=WD_HEADERS)
    assert turns == {"group": 3, "host": 3}           # the tab is open: one turn
    assert [c[0] for c in fake.calls] == ["tab", "request", "tab", "request"]


def test_a_get_of_robots_txt_is_answered_by_the_load_that_opens_the_tab(monkeypatch):
    fake = FakeChrome()
    h = chrome_http(monkeypatch, fake)
    turns = count_turns(monkeypatch, h)
    r = h.get(WD + "/robots.txt", check_robots=False, ok_statuses=(404,))   # moves.py's look for hidden sites
    assert r.content == ROBOTS and r.status == 200
    assert fake.requests() == [] and turns == {"group": 1, "host": 1}


def test_a_tab_lost_before_the_request_is_opened_again_in_a_turn_of_its_own(monkeypatch):
    fake = FakeChrome(TabClosed("gone"), ok())
    h = chrome_http(monkeypatch, fake)
    turns = count_turns(monkeypatch, h)
    h.post(JOBS, json=BODY, headers=WD_HEADERS)
    # open (turn 1), request in turn 2 finds no tab; open again in that unused turn 2, request in turn 3
    assert turns == {"group": 3, "host": 3}
    assert [c[0] for c in fake.calls] == ["tab", "request", "tab", "request"]
    assert h.requests_made == 1


def test_the_time_budget_ends_while_waiting_for_the_requests_own_turn(monkeypatch):
    fake = FakeChrome(ok())
    h = chrome_http(monkeypatch, fake, deadline=time.monotonic() + 60)
    real = h.gate.wait_group
    calls = []

    def wait_group(group, deadline=None):
        calls.append(1)
        return real(group, deadline) if len(calls) == 1 else False   # the second turn comes after the budget's end
    monkeypatch.setattr(h.gate, "wait_group", wait_group)
    with pytest.raises(CheckTimeout, match="time budget"):
        h.post(JOBS, json=BODY, headers=WD_HEADERS)
    assert fake.requests() == []


# robots.txt --------------------------------------------------------------------------------------------------------

def test_robots_txt_comes_through_chrome_and_is_kept_on_disk(monkeypatch, tmp_path):
    fake = FakeChrome(ok())
    h = chrome_http(monkeypatch, fake, robots=True, cache_dir=tmp_path)
    h.post(JOBS, json=BODY, headers=WD_HEADERS)
    with pytest.raises(RobotsBlocked):
        h.post(WD + "/wday/cxs/acme/Secret/jobs", json=BODY, headers=WD_HEADERS)
    assert [c[0] for c in fake.calls] == ["robots", "tab", "request"]   # the robots load opened the tab
    robots_call = fake.calls[0]
    assert robots_call[1] == WD + "/robots.txt"
    assert {k.lower() for k, _ in robots_call[2]} == {"accept", "accept-language"}
    (disk,) = [json.loads(p.read_text()) for p in tmp_path.glob("*.json")]
    assert (disk["origin"], disk["status"], disk["text"]) == (WD, 200, ROBOTS.decode())


def test_a_429_on_robots_txt_through_chrome_pauses_the_group_and_asks_again(monkeypatch, tmp_path, caplog):
    challenge = Resp(429, WD + "/robots.txt", {"cf-mitigated": "challenge", "server": "cloudflare"}, b"<html>")
    fake = FakeChrome(ok(), robots=[challenge])
    h = chrome_http(monkeypatch, fake, robots=True, cache_dir=tmp_path)
    with caplog.at_level(logging.WARNING, logger="internwatch.http"):
        h.post(JOBS, json=BODY, headers=WD_HEADERS)
    assert [c[0] for c in fake.calls] == ["robots", "robots", "tab", "request"]
    assert any("workday answered 429" in r.getMessage() and "cf-mitigated=challenge" in r.getMessage()
               for r in caplog.records)


def test_robots_txt_chrome_cannot_read_counts_as_unreachable(monkeypatch, tmp_path):
    fake = FakeChrome(robots=[FetchError("network error in Chrome")])
    h = chrome_http(monkeypatch, fake, robots=True, cache_dir=tmp_path)
    with pytest.raises(FetchError, match="robots.txt .* unreachable"):
        h.post(JOBS, json=BODY, headers=WD_HEADERS)
    assert fake.requests() == []


def test_chrome_missing_on_robots_txt_names_chrome(monkeypatch, tmp_path):
    fake = FakeChrome(robots=[BrowserUnavailable("Google Chrome could not be started: no window server")])
    h = chrome_http(monkeypatch, fake, robots=True, cache_dir=tmp_path)
    with pytest.raises(BrowserUnavailable, match="no window server"):
        h.post(JOBS, json=BODY, headers=WD_HEADERS)


# Failures look as they did ---------------------------------------------------------------------------------------

def test_a_chrome_timeout_on_every_attempt_is_a_check_timeout(monkeypatch):
    fake = FakeChrome(*[ChromeTimeout("no answer")] * 3)
    with pytest.raises(CheckTimeout, match="after 3 attempts"):
        chrome_http(monkeypatch, fake, retries=2).post(JOBS, json=BODY, headers=WD_HEADERS)
    assert len(fake.requests()) == 3


def test_a_network_failure_in_chrome_is_retried(monkeypatch):
    fake = FakeChrome(FetchError("network error in Chrome (TypeError: Failed to fetch)"), ok())
    assert chrome_http(monkeypatch, fake).post_json(JOBS, json=BODY, headers=WD_HEADERS)["total"] == 1
    assert len(fake.requests()) == 2


def test_network_failures_on_every_attempt_are_a_fetch_error_not_a_timeout(monkeypatch):
    fake = FakeChrome(*[FetchError("network error in Chrome (TypeError: Failed to fetch)")] * 2)
    with pytest.raises(FetchError, match="Failed to fetch") as e:
        chrome_http(monkeypatch, fake, retries=1).post(JOBS, json=BODY, headers=WD_HEADERS)
    assert not isinstance(e.value, CheckTimeout)


def test_chrome_that_cannot_start_is_not_retried(monkeypatch):
    fake = FakeChrome(BrowserUnavailable("Google Chrome could not be started"), ok())
    with pytest.raises(BrowserUnavailable):
        chrome_http(monkeypatch, fake).post(JOBS, json=BODY, headers=WD_HEADERS)
    assert len(fake.requests()) == 1


def test_a_429_through_chrome_pauses_the_group_and_asks_again_without_using_an_attempt(monkeypatch):
    fake = FakeChrome(ok(b"<html>challenge</html>", status=429, headers={"cf-mitigated": "challenge"}), ok())
    h = chrome_http(monkeypatch, fake, retries=0)
    assert h.post_json(JOBS, json=BODY, headers=WD_HEADERS)["total"] == 1
    assert len(fake.requests()) == 2


def test_a_5xx_through_chrome_is_retried_and_a_404_is_not(monkeypatch):
    fake = FakeChrome(ok(b"", status=503), ok())
    assert chrome_http(monkeypatch, fake).post_json(JOBS, json=BODY, headers=WD_HEADERS)["total"] == 1
    fake = FakeChrome(ok(b"", status=404), ok())
    with pytest.raises(FetchError, match="HTTP 404"):
        chrome_http(monkeypatch, fake).get(DETAIL, headers=WD_HEADERS)
    assert len(fake.requests()) == 1
    fake = FakeChrome(ok(b"gone", status=404))
    assert chrome_http(monkeypatch, fake).get(DETAIL, ok_statuses=(404,)).status == 404


def test_workdays_maintenance_page_reads_as_a_shape_error_as_before(monkeypatch):
    """Nov 15: a Citi job-list POST was redirected to community.workday.com's maintenance page (200, HTML)."""
    page = b"<!DOCTYPE html><html><head><title>Workday is currently unavailable</title>"
    moved = "https://community.workday.com/maintenance-page?d=5&s=1&e=1"
    fake = FakeChrome(lambda m, u: Resp(200, moved, {"content-type": "text/html"}, page))
    new = pytest.raises(ShapeError)
    with new as e_new:
        chrome_http(monkeypatch, fake).post_json(JOBS, json=BODY, headers=WD_HEADERS)

    def handler(req):
        if req.url.host == "community.workday.com":
            return httpx.Response(200, headers={"content-type": "text/html"}, content=page)
        return httpx.Response(302, headers={"location": moved})
    with pytest.raises(ShapeError) as e_old:
        httpx_http(monkeypatch, handler).post_json(JOBS, json=BODY, headers=WD_HEADERS)
    assert str(e_new.value) == str(e_old.value)


# The gate and the run close Chrome --------------------------------------------------------------------------------

def test_closing_the_gate_closes_chrome_and_a_later_request_starts_a_new_one(monkeypatch):
    made = []

    def factory():
        made.append(FakeChrome(ok(), ok()))
        return made[-1]
    monkeypatch.setattr(chrome_session, "ChromeSession", factory)
    with_transport(monkeypatch, no_httpx)
    gate = HostGate()
    h = Http(HttpSettings(min_interval=0, respect_robots=False, host_groups=(wd_group(),)), gate=gate)
    h.post(JOBS, json=BODY, headers=WD_HEADERS)
    gate.close()
    assert len(made) == 1 and made[0].closed
    gate.close()  # twice is fine
    h.post(JOBS, json=BODY, headers=WD_HEADERS)
    assert len(made) == 2 and not made[1].closed


@pytest.mark.parametrize("crash", [False, True])
def test_a_run_sweeps_leftovers_first_and_closes_its_chrome_at_the_end(monkeypatch, make_cfg, crash):
    from internwatch.db import DB
    from internwatch.runner import Runner, RunSummary
    cfg = make_cfg([])
    order = []
    monkeypatch.setattr(browser, "sweep_leftovers", lambda *a: order.append("sweep") or [])
    r = Runner(cfg, db=DB(cfg.settings.path("db")))
    monkeypatch.setattr(r.gate, "close", lambda: order.append("close"))

    def _run(opts):
        order.append("run")
        if crash:
            raise RuntimeError("boom")
        return RunSummary()
    monkeypatch.setattr(r, "_run", _run)
    if crash:
        with pytest.raises(RuntimeError):
            r.run()
    else:
        r.run()
    assert order == ["sweep", "run", "close"]


def test_a_session_whose_chrome_cannot_start_fails_at_once_ever_after():
    """conftest's no_chrome makes starting Chrome fail, as it fails with nobody logged in on the Mac."""
    s = chrome_session.ChromeSession()
    launches = []
    real = chrome_session.ChromeSession._launch

    async def counted(self):
        launches.append(1)
        await real(self)
    s._launch = counted.__get__(s)
    try:
        with pytest.raises(BrowserUnavailable, match="a test tried to start a real Chrome"):
            s.ensure_tab(WD, 5)
        with pytest.raises(BrowserUnavailable, match="a test tried to start a real Chrome"):
            s.request("POST", JOBS, [], b"{}", 5)
        assert launches == [1]
    finally:
        s.close()
    assert not s._thread.is_alive()


# Owners and the leftover sweep -------------------------------------------------------------------------------------

@pytest.fixture
def tmpdir_root(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


def owned(root: Path, name: str, owner) -> Path:
    p = root / (browser.PROFILE_PREFIX + name)
    p.mkdir()
    if owner is not None:
        (p / browser.OWNER_FILE).write_text(json.dumps(owner))
    return p


def ended_process() -> dict:
    """The owner record of a process that has ended."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        owner = {"pid": proc.pid, "started": browser._started(proc.pid)}
    finally:
        proc.kill()
        proc.wait()
    assert owner["started"]
    return owner


def test_a_new_profile_records_this_process_as_its_owner(tmpdir_root):
    p = browser.new_profile()
    owner = json.loads((p / browser.OWNER_FILE).read_text())
    assert p.parent == tmpdir_root and p.name.startswith(browser.PROFILE_PREFIX)
    assert owner["pid"] == os.getpid() and owner["started"] == browser._started(os.getpid())
    assert browser.owner_running(owner)


def test_the_sweep_removes_only_profiles_whose_owner_no_longer_runs(tmpdir_root):
    mine = browser.new_profile()                                                  # this live process: kept
    dead = owned(tmpdir_root, "dead", ended_process())                            # its owner ended: removed
    reused = owned(tmpdir_root, "reused", {"pid": os.getpid(), "started": "Mon Jan  1 00:00:00 2001"})  # PID reused
    unknown = owned(tmpdir_root, "unknown", None)                                 # no owner on record: kept
    unsure = owned(tmpdir_root, "unsure", {"pid": 12345, "started": None})        # no start time: kept
    other = tmpdir_root / "something-else"
    other.mkdir()
    gone = browser.sweep_leftovers(tmpdir_root)
    assert sorted(gone) == sorted([dead, reused])
    assert mine.exists() and unknown.exists() and unsure.exists() and other.exists()
    assert not dead.exists() and not reused.exists()


def test_the_sweep_stops_a_chrome_still_using_a_dead_owners_profile(tmpdir_root):
    dead = owned(tmpdir_root, "dead", ended_process())
    # a stand-in for a Chrome process: its command line names the profile, as Chrome's --user-data-dir does
    chrome = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", f"--user-data-dir={dead}"])
    try:
        assert browser.sweep_leftovers(tmpdir_root) == [dead]
        assert chrome.wait(10) is not None
    finally:
        chrome.kill()
    assert not dead.exists()


def test_the_sweep_never_touches_a_chrome_whose_owner_still_runs(tmpdir_root):
    owner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    alive = owned(tmpdir_root, "alive", {"pid": owner.pid, "started": browser._started(owner.pid)})
    chrome = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", f"--user-data-dir={alive}"])
    try:
        assert browser.sweep_leftovers(tmpdir_root) == []
        assert chrome.poll() is None and alive.exists()
    finally:
        for p in (owner, chrome):
            p.kill()
            p.wait()


def test_when_ps_cannot_say_nothing_is_removed(tmpdir_root, monkeypatch):
    dead = owned(tmpdir_root, "dead", ended_process())

    def no_ps(*a, **kw):
        raise OSError("ps: not found")
    monkeypatch.setattr(browser.subprocess, "run", no_ps)
    assert browser.sweep_leftovers(tmpdir_root) == []
    assert dead.exists()


def test_citadels_per_fetch_profile_records_its_owner(monkeypatch, tmp_path):
    """browser.fetch (Citadel) is unchanged but for this: its profile names this process as its owner."""
    import types
    seen = []

    class PwError(Exception):
        pass

    class Ctx:
        pages = []

        def new_page(self):
            raise PwError("page crashed")

        def close(self):
            pass

    class Pw:
        class chromium:
            @staticmethod
            def launch_persistent_context(path, **kw):
                seen.append(json.loads((Path(path) / browser.OWNER_FILE).read_text()))
                return Ctx()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake = types.ModuleType("playwright.sync_api")
    fake.Error, fake.sync_playwright = PwError, Pw
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with pytest.raises(FetchError):
        browser.fetch("https://x.test/a", 5)
    assert seen and seen[0]["pid"] == os.getpid() and seen[0]["started"] == browser._started(os.getpid())
    assert not list(tmp_path.iterdir())


# A real Chrome against local servers (INTERNWATCH_CHROME_TESTS=1) ---------------------------------------------------

live = pytest.mark.skipif(os.environ.get("INTERNWATCH_CHROME_TESTS") != "1",
                          reason="drives a real Google Chrome: set INTERNWATCH_CHROME_TESTS=1")

UNICODE = '{"total": 1, "jobPostings": [{"title": "Intern – Zürich ✓"}]}'.encode()
BINARY = bytes(range(256)) * 4


class Site:
    """A local server that logs every request it gets (method, path, headers, body)."""

    def __init__(self, routes):
        import http.server
        import threading
        self.log: list[dict] = []
        site = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _any(self):
                n = int(self.headers.get("content-length") or 0)
                body = self.rfile.read(n) if n else b""
                site.log.append({"method": self.command, "path": self.path, "body": body,
                                 "headers": {k.lower(): v for k, v in self.headers.items()}})
                route = routes.get((self.command, self.path.split("?")[0])) or routes.get(("*", self.path))
                if route is None:
                    status, headers, content = 404, {"content-type": "text/plain"}, b"not here"
                else:
                    status, headers, content = route(site, self)
                if status is None:  # drop the connection without an answer
                    self.close_connection = True
                    self.connection.shutdown(2)
                    return
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            do_GET = do_POST = _any

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def fixed(status, headers, content):
    return lambda site, req: (status, headers, content)


@pytest.fixture
def sites():
    other = Site({("GET", "/maintenance-page"): fixed(200, {"content-type": "text/html"},
                                                      b"<html><title>Workday is currently unavailable</title>")})
    main = Site({
        ("GET", "/robots.txt"): fixed(200, {"content-type": "text/plain"}, b"User-agent: *\nDisallow: /secret\n"),
        ("POST", "/jobs"): fixed(200, {"content-type": "application/json; charset=utf-8", "x-wd-request-id": "r1"},
                                 UNICODE),
        ("GET", "/bin"): fixed(200, {"content-type": "application/octet-stream"}, BINARY),
        ("GET", "/same-site-redirect"): fixed(301, {"location": "/bin"}, b""),
        ("POST", "/moved"): fixed(302, {"location": other.origin + "/maintenance-page"}, b""),
        ("GET", "/slow"): lambda site, req: (time.sleep(4), (200, {}, b"late"))[1],
        ("GET", "/drop"): fixed(None, {}, b""),
        ("GET", "/challenge"): fixed(403, {"cf-mitigated": "challenge", "content-type": "text/html"}, b"<html>"),
    })
    yield main, other
    main.close()
    other.close()


@pytest.fixture
def session():
    s = chrome_session.ChromeSession()
    yield s
    s.close()
    assert s.profile is None


def local_http(main, gate):
    group = HostGroup("local", (main.origin.split("//")[1],), per_second=1000, browser=True)
    return Http(HttpSettings(min_interval=0, backoff_base=0.01, host_groups=(group,)), gate=gate)


def plain_http():
    return Http(HttpSettings(min_interval=0, respect_robots=False))


@live
@pytest.mark.chrome
def test_real_chrome_sends_exactly_httpxs_request_and_returns_exactly_its_answer(sites):
    main, _ = sites
    gate = HostGate()
    try:
        h = local_http(main, gate)
        new = h.post(main.origin + "/jobs", json=BODY, headers=WD_HEADERS)
        new_detail = h.get(main.origin + "/bin", headers=WD_HEADERS)
        new_bin = h.get(main.origin + "/bin")
        new_moved = h.get(main.origin + "/same-site-redirect")
        profile = gate._chrome.profile
    finally:
        gate.close()
    chrome_log = list(main.log)
    main.log.clear()
    old = plain_http().post(main.origin + "/jobs", json=BODY, headers=WD_HEADERS)
    old_detail = plain_http().get(main.origin + "/bin", headers=WD_HEADERS)
    old_bin = plain_http().get(main.origin + "/bin")
    old_moved = plain_http().get(main.origin + "/same-site-redirect")
    httpx_log = list(main.log)

    # the server got robots.txt (the tab's load, which is also the robots check) and our requests: nothing else
    assert [(e["method"], e["path"]) for e in chrome_log] == [
        ("GET", "/robots.txt"), ("POST", "/jobs"), ("GET", "/bin"), ("GET", "/bin"), ("GET", "/same-site-redirect"),
        ("GET", "/bin")]
    assert [(e["method"], e["path"]) for e in httpx_log] == [(e["method"], e["path"]) for e in chrome_log[1:]]
    assert chrome_log[1]["body"] == httpx_log[0]["body"] == \
        b'{"appliedFacets":{},"limit":20,"offset":40,"searchText":""}'
    for c, x in zip(chrome_log[1:], httpx_log):
        assert c["body"] == x["body"]
        differ = {k for k in set(c["headers"]) | set(x["headers"]) if c["headers"].get(k) != x["headers"].get(k)}
        assert differ <= CHROME_SETS, (c["path"], differ - CHROME_SETS)
    for a, b in ((new, old), (new_detail, old_detail), (new_bin, old_bin), (new_moved, old_moved)):
        assert (a.status, a.url, a.content) == (b.status, b.url, b.content)
        assert {k: v for k, v in a.headers.items() if k not in ("date",)} == \
               {k: v for k, v in b.headers.items() if k not in ("date",)}
    assert profile is not None and not profile.exists()
    assert subprocess.run(["pgrep", "-f", str(profile)], capture_output=True).stdout == b""


@live
@pytest.mark.chrome
def test_real_chrome_follows_a_redirect_to_another_site_as_httpx_does(sites):
    main, other = sites
    gate = HostGate()
    try:
        new = local_http(main, gate).post(main.origin + "/moved", json=BODY, headers=WD_HEADERS)
    finally:
        gate.close()
    old = plain_http().post(main.origin + "/moved", json=BODY, headers=WD_HEADERS)
    assert (new.status, new.url, new.content) == (old.status, old.url, old.content)
    assert new.url == other.origin + "/maintenance-page"


@live
@pytest.mark.chrome
def test_real_chrome_timeouts_drops_and_challenges(sites, session):
    main, _ = sites
    assert session.ensure_tab(main.origin, 30).status == 200
    assert session.ensure_tab(main.origin, 30) is None
    with pytest.raises(ChromeTimeout):
        session.request("GET", main.origin + "/slow", [], None, 1)
    with pytest.raises(FetchError) as e:
        session.request("GET", main.origin + "/drop", [], None, 10)
    assert not isinstance(e.value, ChromeTimeout)
    r = session.request("GET", main.origin + "/challenge", [], None, 10)
    assert r.status == 403 and r.headers["cf-mitigated"] == "challenge"
    with pytest.raises(TabClosed):                                     # the challenged tab was retired …
        session.request("GET", main.origin + "/bin", [], None, 10)
    assert session.ensure_tab(main.origin, 30).status == 200          # … and the page is loaded again
    assert session.request("GET", main.origin + "/bin", [], None, 10).content == BINARY
    assert not any(e["path"] == "/favicon.ico" for e in main.log)


@live
@pytest.mark.chrome
def test_real_chrome_keeps_to_robots_txt_and_its_tab_limit(sites):
    main, _ = sites
    gate = HostGate()
    try:
        h = local_http(main, gate)
        with pytest.raises(RobotsBlocked):
            h.get(main.origin + "/secret")
        assert not any(e["path"] == "/secret" for e in main.log)
    finally:
        gate.close()
    s = chrome_session.ChromeSession(max_tabs=2)
    extra = [Site({("GET", "/robots.txt"): fixed(200, {}, b"")}) for _ in range(3)]
    try:
        for site in extra:
            assert s.ensure_tab(site.origin, 30) is not None
        assert len([o for o in s._tabs if s._open_tab(o) is not None]) == 2   # the least recently used one closed
        assert s.ensure_tab(extra[0].origin, 30) is not None                # … and opens again when needed
    finally:
        s.close()
        for site in extra:
            site.close()
