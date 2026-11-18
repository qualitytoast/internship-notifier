"""One real Google Chrome for a whole run, for the host groups whose vendor refuses every client but a browser.

Workday's Cloudflare has answered our script with a challenge since 2026-11-16, at any pace, while it answers real
Chrome. On 2026-11-17 a minimized Chrome sent 2,163 job-list POSTs from inside its tabs at 3, 5 and 10 requests a second
across 12 Workday sites: all 200, none challenged. 20 of them sent again through httpx came back byte-identical,
except one list that changed in the minute between the two.

How a request travels here: Http builds it exactly as httpx would send it (method, URL, headers, body bytes) and hands
it over. It is sent by fetch() from a tab on the request's origin, and the answer (status, final URL, headers, body
bytes) comes back as the same Resp. robots.txt, pacing, retries, time budgets and recording stay in Http.

- One Chrome per session (HostGate keeps one per run), launched at the first request. It runs in a fresh temporary
  profile that records its owner (browser.new_profile), in one normal window minimized at once. Nothing hides that
  Chrome is automated, and nothing is clicked (as browser.py).
- One tab per origin, opened by loading the origin's robots.txt (ensure_tab, robots), which the robots check needs
  anyway. At most MAX_TABS; for a new one the least recently used idle tab is closed.
- Playwright's objects belong to the thread that made them, and a run's checks run in 8 to 12 threads. So Chrome runs
  on a daemon thread of its own with an asyncio loop, and callers wait for their answer: several requests can be in
  flight at once.
- fetch() can't read an answer from another site (no CORS). A redirect to one, like Workday's maintenance page on
  community.workday.com, is followed as httpx follows it: the redirect's target is loaded in a scratch tab (a GET; a
  POST answered 301, 302 or 303 becomes a GET there, as in httpx).
- An answer with `cf-mitigated` (a challenge) retires its tab, so the next request to that site loads its page again.
- Chrome's automatic favicon request is not sent.
- close() closes Chrome and deletes the profile. An exit handler calls it too. If Chrome goes away mid-run, the next
  request starts it again. If it can't be started, every request fails at once with BrowserUnavailable for the rest
  of the session.
"""
from __future__ import annotations

import asyncio
import atexit
import base64
import concurrent.futures
import logging
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from . import browser
from .browser import BrowserUnavailable
from .models import FetchError

log = logging.getLogger(__name__)

MAX_TABS = 16
LAUNCH_TIMEOUT = 90.0   # seconds for Chrome to start
SPARE = 30.0            # seconds a caller waits beyond a request's own timeout before giving up on the loop

# A request sent from a page: the exact headers and body given, the answer's bytes. timeoutMs ends it as httpx's read
# timeout would (error "timeout"); any other failure (refused connection, DNS, an answer from another site) is
# reported with its message.
FETCH_JS = """async ([url, method, headers, bodyB64, timeoutMs]) => {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    let body = null;
    if (bodyB64 !== null) {
      const bin = atob(bodyB64);
      body = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) body[i] = bin.charCodeAt(i);
    }
    const r = await fetch(url, {method, headers, body, credentials: 'same-origin', redirect: 'follow',
                                cache: 'no-store', signal: ctl.signal});
    const buf = new Uint8Array(await r.arrayBuffer());
    let bin = '';
    for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    return {status: r.status, url: r.url, headers: [...r.headers], b64: btoa(bin)};
  } catch (e) {
    return {error: e && e.name === 'AbortError' ? 'timeout' : String(e)};
  } finally {
    clearTimeout(timer);
  }
}"""


class ChromeTimeout(FetchError):
    """No answer within the request's timeout: Http counts it as it counts an httpx timeout."""


class TabClosed(FetchError):
    """The origin's tab went away between ensure_tab and request (retired, closed for room, or crashed): Http opens it
    again in a paced turn of its own."""


def origin_of(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def _resp(status: int, url: str, headers, content: bytes):
    from .http import Resp
    return Resp(status, url, {k.lower(): v for k, v in headers}, content)


def _first_line(e: BaseException) -> str:
    return (str(e).splitlines() or [type(e).__name__])[0][:200]


class ChromeSession:
    def __init__(self, max_tabs: int = MAX_TABS):
        self.max_tabs = max_tabs
        self._guard = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._closed = False
        self._unavailable: str | None = None    # why Chrome can't be started, once it couldn't
        # state of the loop thread only
        self._pw = None
        self._ctx = None
        self._profile: Path | None = None
        self._spare_page = None                 # the tab Chrome opened with, used for the first origin
        self._tabs: dict[str, object] = {}      # origin -> its tab
        self._used: dict[object, float] = {}    # tab -> when it was last used
        self._busy: dict[object, int] = {}      # tab -> requests in flight on it
        self._retired: set = set()              # tabs that met a challenge: closed once idle
        self._opening: dict[str, asyncio.Lock] = {}
        self._launching: asyncio.Lock | None = None
        self._watch: dict[tuple, list] = {}     # (method, url, body) of a fetch in flight -> the requests it started
        self._watchers: dict[tuple, int] = {}

    # -- from any thread ----------------------------------------------------------------------------------------------
    def ensure_tab(self, origin: str, timeout: float):
        """Open the origin's tab if it has none, by loading <origin>/robots.txt. Returns that load's answer (a Resp), or
        None when the tab was already open."""
        return self._call(lambda: self._ensure_tab(origin, timeout), timeout)

    def request(self, method: str, url: str, headers: list[tuple[str, str]], body: bytes | None, timeout: float):
        """Send one request from its origin's tab (opened by ensure_tab). Raises TabClosed if the tab is gone,
        ChromeTimeout if no answer comes within `timeout` seconds, FetchError for any other failure."""
        return self._call(lambda: self._request(method, url, headers, body, timeout), timeout)

    def robots(self, url: str, headers: list[tuple[str, str]], timeout: float):
        """robots.txt as a Resp: the load that opens the origin's tab, or a request from the tab already open."""
        return self._call(lambda: self._robots(url, headers, timeout), timeout)

    def close(self) -> None:
        """Close Chrome and delete its profile. Safe to call twice and from an exit handler."""
        with self._guard:
            if self._closed:
                return
            self._closed = True
            loop, thread = self._loop, self._thread
        if loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(self._discard(), loop).result(60)
            except Exception as e:  # noqa: BLE001 - the profile is removed below whatever happened
                log.warning("chrome: closing Chrome failed: %s: %s", type(e).__name__, _first_line(e))
            loop.call_soon_threadsafe(loop.stop)
            if thread is not None:
                thread.join(10)
        if self._profile is not None:
            browser._remove(self._profile)
            self._profile = None

    @property
    def profile(self) -> Path | None:
        return self._profile

    def _call(self, make, timeout: float):
        with self._guard:
            if self._closed:
                raise FetchError("Chrome session already closed")
            if self._unavailable:
                raise BrowserUnavailable(self._unavailable)
            if self._loop is None:
                loop = asyncio.new_event_loop()
                thread = threading.Thread(target=loop.run_forever, name="internwatch-chrome", daemon=True)
                thread.start()
                self._loop, self._thread = loop, thread
                atexit.register(self.close)
            loop = self._loop
        fut = asyncio.run_coroutine_threadsafe(make(), loop)
        try:
            return fut.result(timeout + SPARE + (LAUNCH_TIMEOUT if self._ctx is None else 0))
        except concurrent.futures.TimeoutError:
            fut.cancel()
            raise ChromeTimeout(f"Chrome gave no answer in {timeout:.0f} s") from None

    # -- on the loop thread -------------------------------------------------------------------------------------------
    async def _ensure_ctx(self):
        if self._ctx is not None:
            return self._ctx
        if self._launching is None:
            self._launching = asyncio.Lock()
        async with self._launching:
            if self._unavailable:
                raise BrowserUnavailable(self._unavailable)
            if self._ctx is None:
                await self._discard()  # whatever is left of a Chrome that went away
                try:
                    await asyncio.wait_for(self._launch(), LAUNCH_TIMEOUT)
                except BrowserUnavailable as e:
                    self._unavailable = str(e)
                    raise
                except Exception as e:  # noqa: BLE001 - any failure to start is the same for the run
                    self._unavailable = f"Google Chrome could not be started: {type(e).__name__}: {_first_line(e)}"
                    await self._discard()
                    raise BrowserUnavailable(self._unavailable) from e
        return self._ctx

    async def _launch(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise BrowserUnavailable("fetching through Chrome needs Playwright: .venv/bin/pip install -e .") from e
        self._profile = browser.new_profile()
        self._pw = await async_playwright().start()
        ctx = await self._pw.chromium.launch_persistent_context(
            str(self._profile), channel="chrome", headless=False, no_viewport=True, args=browser.WINDOW_ARGS)
        self._ctx = ctx

        async def no_favicon(route):
            await route.abort()
        await ctx.route("**/favicon.ico", no_favicon)
        ctx.on("request", self._seen)
        ctx.on("close", lambda _: self._lost(ctx))
        self._spare_page = ctx.pages[0] if ctx.pages else None
        log.info("chrome: started Chrome (profile %s)", self._profile)

    def _lost(self, ctx) -> None:
        """Chrome went away (crashed, or quit by someone): the next request starts it again."""
        if ctx is self._ctx and not self._closed:
            log.warning("chrome: Chrome closed unexpectedly; it is started again for the next request")
            self._ctx = None

    async def _discard(self) -> None:
        """Close Chrome, stop Playwright, delete the profile: what close() and a restart need."""
        ctx, pw, profile = self._ctx, self._pw, self._profile
        self._ctx = self._pw = self._spare_page = None
        self._tabs.clear()
        self._used.clear()
        self._busy.clear()
        self._retired.clear()
        if ctx is not None:
            try:
                await ctx.close()
            except Exception as e:  # noqa: BLE001
                log.warning("chrome: closing the window failed: %s", _first_line(e))
        if pw is not None:
            try:
                await pw.stop()
            except Exception as e:  # noqa: BLE001
                log.warning("chrome: stopping Playwright failed: %s", _first_line(e))
        if profile is not None and not self._closed:  # close() removes its own after the loop stops
            browser._remove(profile)
            self._profile = None

    async def _minimize(self, page) -> None:
        cdp = await self._ctx.new_cdp_session(page)
        try:
            wid = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
            await cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "minimized"}})
        finally:
            await cdp.detach()

    async def _new_page(self):
        page, self._spare_page = self._spare_page, None
        if page is None or page.is_closed():
            page = await self._ctx.new_page()
        await self._minimize(page)
        return page

    def _open_tab(self, origin: str):
        page = self._tabs.get(origin)
        return page if page is not None and not page.is_closed() else None

    async def _make_room(self) -> None:
        open_ = [(self._used.get(p, 0.0), o, p) for o, p in self._tabs.items() if not p.is_closed()]
        if len(open_) < self.max_tabs:
            return
        idle = sorted((u, o, p) for u, o, p in open_ if not self._busy.get(p))
        if idle:
            _, origin, page = idle[0]
            del self._tabs[origin]
            await self._close_page(page)

    async def _close_page(self, page) -> None:
        self._used.pop(page, None)
        self._busy.pop(page, None)
        self._retired.discard(page)
        try:
            await page.close()
        except Exception:  # noqa: BLE001 - already gone
            pass

    async def _ensure_tab(self, origin: str, timeout: float):
        await self._ensure_ctx()
        if self._open_tab(origin) is not None:
            return None
        lock = self._opening.setdefault(origin, asyncio.Lock())
        async with lock:
            if self._open_tab(origin) is not None:
                return None
            await self._make_room()
            page = await self._new_page()
            self._tabs[origin] = page
            self._used[page] = time.monotonic()
            self._busy[page] = 1
            try:
                return await self._load(page, origin + "/robots.txt", timeout)
            except BaseException:
                self._tabs.pop(origin, None)
                await self._close_page(page)
                raise
            finally:
                self._done(page)

    async def _load(self, page, url: str, timeout: float):
        """Load a page in the tab: the main frame's answer (redirects followed). A challenge that passes on its own
        reloads the page, so while the answer is a challenge the load waits, up to `timeout`, for one that isn't."""
        from playwright.async_api import Error as PlaywrightError
        answers = []

        def keep(r):
            if r.frame == page.main_frame and r.request.is_navigation_request() and not 300 <= r.status < 400:
                answers.append(r)
        page.on("response", keep)
        end = time.monotonic() + timeout
        try:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            except PlaywrightError as e:
                if not answers:
                    if "Timeout" in type(e).__name__ or "timeout" in str(e).lower():
                        raise ChromeTimeout(f"Chrome got no answer in {timeout:.0f} s for GET {url[:160]}") from e
                    raise FetchError(f"network error in Chrome ({_first_line(e)}) for GET {url[:160]}") from e
            while answers and answers[-1].headers.get("cf-mitigated") and time.monotonic() < end:
                await page.wait_for_timeout(500)
            if not answers:
                raise FetchError(f"Chrome got no answer for GET {url[:160]}")
            r = answers[-1]
            try:
                body = await r.body()
            except PlaywrightError:
                body = b""
            return _resp(r.status, r.url, r.headers.items(), body)
        finally:
            page.remove_listener("response", keep)

    def _done(self, page) -> None:
        if page.is_closed():
            self._busy.pop(page, None)
            self._used.pop(page, None)
            self._retired.discard(page)
            return
        self._busy[page] = max(0, self._busy.get(page, 1) - 1)
        self._used[page] = time.monotonic()
        if page in self._retired and not self._busy[page]:
            asyncio.ensure_future(self._close_page(page))

    def _seen(self, req) -> None:
        """Every request Chrome sends: the ones a fetch in flight started are kept, to see where they were redirected."""
        if not self._watch or req.redirected_from is not None:
            return
        key = (req.method, req.url, req.post_data_buffer or None)
        if key in self._watch:
            self._watch[key].append(req)

    async def _request(self, method, url, headers, body, timeout):
        from playwright.async_api import Error as PlaywrightError
        await self._ensure_ctx()
        origin = origin_of(url)
        page = self._open_tab(origin)
        if page is None:
            self._tabs.pop(origin, None)
            raise TabClosed(f"no tab for {origin}")
        self._busy[page] = self._busy.get(page, 0) + 1
        self._used[page] = time.monotonic()
        key = (method, url, body or None)
        self._watch.setdefault(key, [])
        self._watchers[key] = self._watchers.get(key, 0) + 1
        try:
            args = [url, method, [list(h) for h in headers],
                    base64.b64encode(body).decode() if body is not None else None, int(timeout * 1000)]
            try:
                res = await asyncio.wait_for(page.evaluate(FETCH_JS, args), timeout + 10)
            except asyncio.TimeoutError:
                self._retire(origin, page)  # the page no longer answers
                raise ChromeTimeout(f"Chrome gave no answer in {timeout:.0f} s for {method} {url[:160]}") from None
            except PlaywrightError as e:
                self._retire(origin, page)  # the tab crashed or was closed under the request
                raise FetchError(f"network error in Chrome ({_first_line(e)}) for {method} {url[:160]}") from e
            if res.get("error") == "timeout":
                raise ChromeTimeout(f"Chrome got no answer in {timeout:.0f} s for {method} {url[:160]}")
            if "error" in res:
                hop = self._elsewhere(key, origin)
                if hop is not None:
                    return await self._follow(hop, method, url, timeout)
                raise FetchError(f"network error in Chrome ({res['error'][:160]}) for {method} {url[:160]}")
            resp = _resp(res["status"], res["url"], res["headers"], base64.b64decode(res["b64"]))
            if resp.headers.get("cf-mitigated"):
                self._retire(origin, page)
            return resp
        finally:
            self._watchers[key] -= 1
            if not self._watchers[key]:
                del self._watchers[key]
                self._watch.pop(key, None)
            self._done(page)

    def _retire(self, origin: str, page) -> None:
        """The next request to this origin opens a new tab; this one closes once its requests are done."""
        if self._tabs.get(origin) is page:
            del self._tabs[origin]
        self._retired.add(page)

    def _elsewhere(self, key, origin: str):
        """The last hop of a redirect this fetch followed to another site, or None."""
        for req in reversed(self._watch.get(key) or []):
            hop = req
            while hop.redirected_to is not None:
                hop = hop.redirected_to
            if hop is not req and origin_of(hop.url) != origin:
                return hop
        return None

    async def _follow(self, hop, method: str, url: str, timeout: float):
        """Read the other site's answer as httpx would after following the redirect: load it in a scratch tab."""
        if hop.method != "GET":
            raise FetchError(f"redirected to another site with {hop.method} ({hop.url[:120]}), which Chrome can't "
                             f"follow, for {method} {url[:160]}")
        log.info("chrome: %s %s was redirected to %s: read there", method, url[:160], hop.url[:160])
        page = await self._new_page()
        try:
            return await self._load(page, hop.url, timeout)
        finally:
            await self._close_page(page)

    async def _robots(self, url, headers, timeout):
        origin = origin_of(url)
        for _ in range(3):
            opened = await self._ensure_tab(origin, timeout)
            if opened is not None:
                return opened
            try:
                return await self._request("GET", url, headers, None, timeout)
            except TabClosed:
                continue
        raise FetchError(f"Chrome kept losing the tab for {origin}")
