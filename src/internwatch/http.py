"""The only way checkers talk to the network.

* real browser user agent, connect/read timeouts
* retries with exponential backoff + jitter on timeouts, connection errors, 429 and 5xx
* per-host pacing shared by all threads (at least `min_interval` seconds between requests to one
  host, more if robots.txt asks for a Crawl-delay)
* host groups: hosts of one vendor share one pace, whatever host each request goes to (Workday's sites are hundreds
  of hosts behind one rate limit), and a 429 from any of them pauses the whole group
* a host group marked `browser` is read through one real Chrome per run (chrome_session.py): each request is built
  as httpx would send it and sent from a Chrome tab on its site; everything around the send stays the same
* robots.txt gate: every URL is checked before it is fetched; disallowed URLs raise RobotsBlocked
* record / replay of every exchange, so checkers can be tested offline from fixtures
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json as jsonlib
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

import httpx

from .models import CheckTimeout, FetchError, RobotsBlocked
from .robots import RobotsRules, from_response

log = logging.getLogger(__name__)

DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 524}


RETRY_AFTER_CAP = 900.0   # a group pause honors a server's Retry-After up to this many seconds


@dataclass
class HostGroup:
    """Hosts that share one pace: every request to a host ending in one of `hosts` (robots.txt included) takes a turn
    at most `per_second` times a second across all threads, and a 429 from any of them pauses all of them.
    Workday answered 429 to most of its sites on 2026-11-16 after mornings that reached 11 requests a second across
    its sites, each site paced on its own.

    The pause steps up: the first 429 pauses for `pause_on_429[0]` seconds, and a 429 that comes within
    `escalate_within` seconds of the end of the last pause takes the next step (the last step repeats). A Retry-After
    longer than the step is honored, up to RETRY_AFTER_CAP. On 2026-11-17 a fixed 60 s pause met a new 429 nearly
    every minute (98 pauses in 97 minutes): coming back after 60 s only tripped the limit again."""
    name: str
    hosts: tuple[str, ...]
    per_second: float
    pause_on_429: tuple[float, ...] | float = (60.0, 120.0, 300.0)
    pauses: int = 3               # a request is given up after this many pauses
    escalate_within: float = 300.0
    browser: bool = False         # every request to the group goes through the run's Chrome (chrome_session.py)

    def __post_init__(self):
        steps = self.pause_on_429
        self.pause_on_429 = tuple(float(x) for x in steps) if isinstance(steps, (list, tuple)) else (float(steps),)
        if not self.pause_on_429:
            raise ValueError(f"host group {self.name}: pause_on_429 needs at least one step")

    def covers(self, host: str) -> bool:
        return any(host == h or host.endswith("." + h) for h in self.hosts)

    def pause_for(self, step: int, retry_after: float | None) -> float:
        """The pause of the step-th 429 in a row (1-based), lengthened to the server's Retry-After."""
        pause = self.pause_on_429[min(step, len(self.pause_on_429)) - 1]
        if retry_after is not None:
            pause = max(pause, min(retry_after, RETRY_AFTER_CAP))
        return pause


# Headers Chrome sets itself on a request sent from a page, whatever it is given (the list the user approved on
# 2026-11-17, measured against a local server): the ones httpx sends that Chrome replaces with its own (User-Agent,
# Accept-Encoding, Host, Connection, Content-Length, Cookie: each client has its own session with the site); the ones
# only Chrome adds (Origin, Referer, sec-ch-ua*, sec-fetch-*); and Cache-Control and Pragma "no-cache", which Chrome
# adds because each request skips its cache, so every answer comes from the site as httpx's do. Every other header
# httpx would send is given to Chrome as it is.
CHROME_SETS = frozenset({"user-agent", "accept-encoding", "host", "connection", "content-length", "cookie",
                         "origin", "referer", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
                         "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site", "cache-control", "pragma"})


def chrome_headers(headers) -> list[tuple[str, str]]:
    """The headers of an httpx request that Chrome is given (CHROME_SETS are left to Chrome)."""
    return [(k, v) for k, v in headers.multi_items() if k.lower() not in CHROME_SETS]


def chrome_timeout(read_timeout: float) -> float:
    """How long a Chrome fetch may wait for its page: longer than a plain read, since Chrome starts first and a
    challenge that passes on its own reloads the page."""
    return max(45.0, read_timeout)


def limit_info(resp) -> str:
    """What a 429 answer says about the limit behind it, for the log: the headers that can carry it and the start of
    the body. Workday sits behind Cloudflare, whose rate limiting and bot rules both answer 429."""
    h = {k.lower(): v for k, v in resp.headers.items()}
    keep = [k for k in sorted(h) if k in ("retry-after", "server", "cf-ray", "cf-mitigated", "x-wd-request-id",
                                            "content-type")
            or "ratelimit" in k or "rate-limit" in k]
    parts = [f"{k}={h[k][:120]}" for k in keep]
    body = " ".join(resp.content[:400].decode("utf-8", "replace").split())[:160]
    parts.append(f"body={body!r}" if body else "no body")
    return ", ".join(parts)


def retry_after_seconds(resp) -> float | None:
    ra = resp.headers.get("retry-after", "").strip()
    return float(ra) if ra.isdigit() else None


@dataclass
class HttpSettings:
    user_agent: str = DEFAULT_UA
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    retries: int = 3               # attempts after the first one
    backoff_base: float = 2.0      # seconds; delays are base, base*3, base*9 … plus jitter
    min_interval: float = 1.0      # seconds between requests to the same host
    max_crawl_delay: float = 10.0  # cap for robots.txt Crawl-delay
    robots_ttl_hours: float = 12.0
    respect_robots: bool = True
    host_groups: tuple[HostGroup, ...] = ()


@dataclass
class Resp:
    status: int
    url: str
    headers: dict
    content: bytes

    @property
    def text(self) -> str:
        enc = "utf-8"
        ctype = self.headers.get("content-type", "")
        if "charset=" in ctype:
            enc = ctype.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        try:
            return self.content.decode(enc, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")

    def json(self):
        try:
            return jsonlib.loads(self.content)
        except ValueError as e:
            from .models import ShapeError
            raise ShapeError(f"expected JSON from {self.url[:120]}, got {self.content[:80]!r}") from e


class HostGate:
    """Process-wide politeness state shared by all threads: pacing and robots.txt cache."""

    def __init__(self, cache_dir: Path | None = None):
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._last: dict[str, float] = {}
        self._robots: dict[str, tuple[RobotsRules, float]] = {}
        self._group_next: dict[str, float] = {}    # a host group's next free turn (time.monotonic())
        self._group_pause: dict[str, float] = {}   # … and the end of its pause after a 429
        self._group_step: dict[str, int] = {}      # … the step of that pause (429s in a row)
        self._group_turns: dict[str, int] = {}     # … turns given since that pause ended (requests sent)
        self._chrome = None                        # the run's Chrome (chrome_session.py), started when first needed
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def chrome(self):
        """The run's Chrome session, shared by every thread (created here, started at its first request)."""
        with self._guard:
            if self._chrome is None:
                from . import chrome_session
                self._chrome = chrome_session.ChromeSession()
            return self._chrome

    def close(self) -> None:
        """Close the run's Chrome, if one was started, and delete its profile. The gate stays usable: a later request
        through Chrome starts a new one."""
        with self._guard:
            session, self._chrome = self._chrome, None
        if session is not None:
            session.close()

    def lock_for(self, host: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(host, threading.Lock())

    def wait_turn(self, host: str, interval: float) -> None:
        with self.lock_for(host):
            now = time.monotonic()
            wait = self._last.get(host, 0) + interval - now
            if wait > 0:
                time.sleep(wait)
            self._last[host] = time.monotonic()

    def wait_group(self, group: HostGroup, deadline: float | None = None) -> bool:
        """Take the group's next turn: 1/per_second after the last one taken by any thread, and not before its pause
        ends. False when that turn comes after `deadline` (the caller's time budget), without waiting for it."""
        spacing = 1.0 / group.per_second
        while True:
            with self.lock_for("group:" + group.name):
                now = time.monotonic()
                turn = max(now, self._group_next.get(group.name, 0.0), self._group_pause.get(group.name, 0.0))
                if deadline is not None and turn > deadline:
                    return False
                self._group_next[group.name] = turn + spacing
            if turn > now:
                time.sleep(turn - now)
            with self.lock_for("group:" + group.name):
                if time.monotonic() >= self._group_pause.get(group.name, 0.0):
                    self._group_turns[group.name] = self._group_turns.get(group.name, 0) + 1
                    return True
            # a 429 paused the group while this turn was waiting: take a turn after the pause

    def pause_group(self, group: HostGroup, url: str = "", resp=None) -> float:
        """A host of the group answered 429: no request to any of them before the pause ends. A 429 to a request sent
        before the current pause began belongs to that pause and changes nothing. Returns the pause's end."""
        with self.lock_for("group:" + group.name):
            now = time.monotonic()
            end = self._group_pause.get(group.name)
            if end is not None and now < end:
                return end
            sent = self._group_turns.get(group.name, 0)
            if end is not None and now - end <= group.escalate_within:
                step = self._group_step.get(group.name, 0) + 1
                since = f"{sent} requests in {now - end:.0f} s since the last pause ended"
            else:
                step = 1
                since = (f"{sent} requests since the last pause, {now - end:.0f} s ago" if end is not None
                         else f"the run's first 429, after {sent} requests")
            pause = group.pause_for(step, retry_after_seconds(resp) if resp is not None else None)
            self._group_pause[group.name] = now + pause
            self._group_step[group.name] = step
            self._group_turns[group.name] = 0
            info = limit_info(resp) if resp is not None else "no answer kept"
            log.warning("http: %s answered 429 (%s; %s; %s): all its hosts wait %.0f s (429 %d in a row)",
                        group.name, urlsplit(url).netloc or "?", since, info, pause, step)
            return now + pause

    # robots cache -----------------------------------------------------------------------------
    def robots(self, origin: str, fetch, ttl_hours: float) -> RobotsRules:
        with self.lock_for("robots:" + origin):
            hit = self._robots.get(origin)
            if hit and time.time() - hit[1] < ttl_hours * 3600:
                return hit[0]
            disk = self._disk_get(origin)
            if disk and time.time() - disk[2] < ttl_hours * 3600:
                rules = from_response(disk[0], disk[1])
                self._robots[origin] = (rules, disk[2])
                return rules
            status, text = fetch(origin + "/robots.txt")
            if status is None or status >= 500:
                if not disk:
                    # RFC 9309: an unreachable robots.txt means "crawl nothing", so the request is not made. It is a
                    # temporary error (retried next poll), not a site policy, so it is neither cached nor reported as
                    # "blocked".
                    raise FetchError(f"robots.txt for {origin} unreachable ({status or 'network error'}); will retry")
                # RFC 9309 allows a cached copy while robots.txt is temporarily unreachable.
                log.warning("robots.txt for %s unreachable (%s); using cached copy", origin, status)
                status, text = disk[0], disk[1]
            else:
                self._disk_put(origin, status, text)
            rules = from_response(status, text)
            self._robots[origin] = (rules, time.time())
            return rules

    def _disk_path(self, origin: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / (hashlib.sha1(origin.encode()).hexdigest()[:16] + ".json")

    def _disk_get(self, origin: str):
        p = self._disk_path(origin)
        if p and p.exists():
            try:
                d = jsonlib.loads(p.read_text())
                return d["status"], d["text"], d["fetched_at"]
            except (ValueError, KeyError):
                return None
        return None

    def _disk_put(self, origin: str, status, text: str) -> None:
        p = self._disk_path(origin)
        if p and status is not None and status < 500:
            p.write_text(jsonlib.dumps({"origin": origin, "status": status, "text": text[:500_000],
                                        "fetched_at": time.time()}))


# ---------------------------------------------------------------------------------------------
# record / replay
# ---------------------------------------------------------------------------------------------

def canonical_url(url: str, params: dict | None = None) -> str:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if params:
        for k, v in params.items():
            if isinstance(v, (list, tuple)):
                query += [(k, str(x)) for x in v]
            elif v is not None:
                query.append((k, str(v)))
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, urlencode(sorted(query)), ""))


def body_key(json_body=None, data=None) -> str:
    if json_body is not None:
        return jsonlib.dumps(json_body, sort_keys=True, separators=(",", ":"))
    if data is not None:
        if isinstance(data, dict):
            return urlencode(sorted(data.items()))
        return data.decode() if isinstance(data, bytes) else str(data)
    return ""


def _shrink(content: bytes, ctype: str) -> bytes:
    """Shorten long text values inside recorded JSON so fixtures stay small."""
    if "json" not in ctype and content[:1] not in (b"{", b"["):
        return content

    def walk(x):
        if isinstance(x, str) and len(x) > 1500:
            return x[:1500]
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        return x
    try:
        return jsonlib.dumps(walk(jsonlib.loads(content)), separators=(",", ":")).encode()
    except ValueError:
        return content


@dataclass
class Cassette:
    """Recorded HTTP exchanges for one checker run (gzipped JSON on disk)."""

    exchanges: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    shrink: bool = True
    _cursor: dict = field(default_factory=dict)

    def add(self, method: str, url: str, body: str, resp: Resp) -> None:
        content = _shrink(resp.content, resp.headers.get("content-type", "")) if self.shrink else resp.content
        e = {"method": method, "url": url, "body": body, "status": resp.status,
             "headers": {k: v for k, v in resp.headers.items() if k in ("content-type", "location", "etag")}}
        try:
            e["text"] = content.decode("utf-8")  # text compresses far better than base64 in the gzip file
        except UnicodeDecodeError:
            e["content_b64"] = base64.b64encode(content).decode()
        self.exchanges.append(e)

    def find(self, method: str, url: str, body: str) -> Resp:
        key = (method, url, body)
        matches = [e for e in self.exchanges if (e["method"], e["url"], e["body"]) == key]
        if not matches:
            raise FetchError(f"replay: no recorded response for {method} {url} {body[:200]}")
        i = self._cursor.get(key, 0)
        e = matches[min(i, len(matches) - 1)]
        self._cursor[key] = i + 1
        content = e["text"].encode("utf-8") if "text" in e else base64.b64decode(e["content_b64"])
        return Resp(e["status"], url, dict(e["headers"]), content)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = jsonlib.dumps({"meta": self.meta, "exchanges": self.exchanges}, separators=(",", ":"))
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(payload)

    @classmethod
    def load(cls, path: Path) -> "Cassette":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            d = jsonlib.load(fh)
        return cls(exchanges=d["exchanges"], meta=d.get("meta", {}))


# ---------------------------------------------------------------------------------------------

CERTS_DIR = Path(__file__).resolve().parent / "certs"
_ssl_ctx = None


def ssl_context():
    """certifi's roots plus the intermediates in internwatch/certs/ (for servers that send an incomplete
    chain, e.g. app.ripplematch.com omits Sectigo's DV R36 intermediate; browsers fetch it, Python can't)."""
    global _ssl_ctx
    if _ssl_ctx is None:
        import ssl

        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        for pem in sorted(CERTS_DIR.glob("*.pem")):
            ctx.load_verify_locations(cadata=pem.read_text())
        _ssl_ctx = ctx
    return _ssl_ctx


class Http:
    """HTTP client used by one checker run. Cheap to create; share the HostGate."""

    def __init__(self, settings: HttpSettings | None = None, gate: HostGate | None = None,
                 record: Cassette | None = None, replay: Cassette | None = None,
                 host_intervals: dict | None = None, min_interval: float | None = None,
                 deadline: float | None = None):
        self.s = settings or HttpSettings()
        self.gate = gate or HostGate()
        self.record = record
        self.replay = replay
        self.host_intervals = host_intervals or {}
        self.min_interval = min_interval  # per-company pacing override (e.g. 3 s for a rate-limited host)
        self.deadline = deadline          # time.monotonic() value after which requests stop (check budget)
        self.requests_made = 0
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"User-Agent": self.s.user_agent, "Accept-Language": "en-US,en;q=0.9"},
                timeout=httpx.Timeout(self.s.read_timeout, connect=self.s.connect_timeout),
                follow_redirects=True,
                http2=False,
                verify=ssl_context(),
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # public helpers -------------------------------------------------------------------------
    def get(self, url, **kw) -> Resp:
        return self.request("GET", url, **kw)

    def post(self, url, **kw) -> Resp:
        return self.request("POST", url, **kw)

    def get_json(self, url, **kw):
        return self.request("GET", url, **kw).json()

    def post_json(self, url, **kw):
        return self.request("POST", url, **kw).json()

    def get_text(self, url, **kw) -> str:
        return self.request("GET", url, **kw).text

    # core -----------------------------------------------------------------------------------
    def request(self, method: str, url: str, *, params: dict | None = None, json=None, data=None,
                headers: dict | None = None, timeout: float | None = None,
                ok_statuses: tuple[int, ...] = (), check_robots: bool = True, browser: bool = False) -> Resp:
        """browser=True: a GET made by the real Google Chrome (browser.py) instead of httpx, for sites that refuse
        every client but a browser. robots.txt, pacing, retries, the time budget and record/replay work the same.
        A host in a host group marked `browser` is read through the run's Chrome (chrome_session.py) whatever is
        asked: the request httpx would send, sent from a Chrome tab on that site."""
        if browser and (method != "GET" or json is not None or data is not None or headers):
            raise ValueError("browser=True is for plain GETs")
        full = canonical_url(url, params)
        bkey = body_key(json, data)
        if self.replay is not None:
            resp = self.replay.find(method, full, bkey)
            if resp.status >= 400 and resp.status not in ok_statuses:
                raise FetchError(f"HTTP {resp.status} for {method} {url[:160]} (replayed)")
            return resp
        parts = urlsplit(full)
        origin = f"{parts.scheme}://{parts.netloc}"
        interval = self.host_intervals.get(parts.netloc, self.s.min_interval)
        if self.min_interval:
            interval = max(interval, self.min_interval)
        group = next((g for g in self.s.host_groups if g.covers(parts.netloc)), None)
        use_chrome = not browser and group is not None and group.browser
        rules = None
        if check_robots and self.s.respect_robots:
            rules = self.gate.robots(origin, lambda u: self._fetch_robots(u, parts.netloc, interval, group),
                                     self.s.robots_ttl_hours)
            if not rules.allowed(full):
                raise RobotsBlocked(f"robots.txt disallows {full[:160]} ({rules.matching_rule(full)})")
        if rules is not None:
            cd = rules.crawl_delay()
            if cd:
                interval = max(interval, min(cd, self.s.max_crawl_delay))

        last_err, timeouts, paused, attempt, after_pause = "", 0, 0, 0, False
        while attempt <= self.s.retries:
            self._check_deadline(method, url)
            if attempt and not after_pause:
                delay = self.s.backoff_base * (3 ** (attempt - 1)) * (0.75 + random.random() / 2)
                if self.deadline is not None:
                    delay = min(delay, max(0.0, self.deadline - time.monotonic()))
                time.sleep(min(delay, 60))
                self._check_deadline(method, url)
            after_pause = False
            if group is not None and not self.gate.wait_group(group, self.deadline):
                raise CheckTimeout(f"time budget exhausted waiting for {group.name}'s next turn before {method} "
                                   f"{url[:160]} ({self.requests_made} requests made)")
            self.gate.wait_turn(parts.netloc, interval)
            if browser:
                from . import browser as chrome
                wait = timeout or chrome_timeout(self.s.read_timeout)
                if self.deadline is not None:
                    wait = max(1.0, min(wait, self.deadline - time.monotonic()))
                try:
                    resp = chrome.fetch(full, wait)
                    self.requests_made += 1
                except chrome.BrowserUnavailable:
                    raise
                except FetchError as e:
                    last_err = f"{e} ({method} {url[:160]})"
                    attempt += 1
                    continue
            elif use_chrome:
                from .browser import BrowserUnavailable
                from .chrome_session import ChromeTimeout
                try:
                    resp = self._chrome_send(method, full, json, data, headers, timeout, origin, parts.netloc,
                                             group, interval)
                    self.requests_made += 1
                except BrowserUnavailable:
                    raise
                except ChromeTimeout as e:
                    last_err = f"timeout (Chrome) for {method} {url[:160]}: {e}"
                    timeouts += 1
                    attempt += 1
                    continue
                except CheckTimeout:
                    raise
                except FetchError as e:
                    last_err = str(e)
                    attempt += 1
                    continue
            else:
                try:
                    r = self.client.request(method, full, json=json, data=data, headers=headers,
                                            timeout=timeout or httpx.USE_CLIENT_DEFAULT)
                    self.requests_made += 1
                except httpx.TimeoutException as e:
                    last_err = f"timeout ({type(e).__name__}) for {method} {url[:160]}"
                    timeouts += 1
                    attempt += 1
                    continue
                except httpx.TransportError as e:
                    last_err = f"network error ({type(e).__name__}: {str(e)[:120]}) for {method} {url[:160]}"
                    attempt += 1
                    continue
                resp = Resp(r.status_code, str(r.url), {k.lower(): v for k, v in r.headers.items()}, r.content)
            if resp.status == 429 and group is not None and 429 not in ok_statuses:
                # the vendor limits all its hosts together: pause them all and ask again after the pause, which is
                # not one of the request's attempts
                self.gate.pause_group(group, full, resp)
                paused += 1
                if paused > group.pauses:
                    raise FetchError(f"HTTP 429 for {method} {url[:160]} (after {group.pauses} pauses of every "
                                     f"{group.name} host)")
                after_pause = True
                continue
            if resp.status in RETRY_STATUSES and resp.status not in ok_statuses:
                last_err = f"HTTP {resp.status} for {method} {url[:160]}"
                ra = resp.headers.get("retry-after", "")
                if ra.isdigit():
                    wait = min(int(ra), 60)
                elif resp.status == 429:
                    wait = min(30.0 * (attempt + 1), 90)  # rate limited without a hint: back off hard
                else:
                    wait = 0
                if self.deadline is not None:
                    wait = min(wait, max(0.0, self.deadline - time.monotonic()))
                if wait and attempt < self.s.retries:  # no wait when no attempt follows
                    time.sleep(wait)
                attempt += 1
                continue
            if self.record is not None:
                self.record.add(method, full, bkey, resp)
            if resp.status >= 400 and resp.status not in ok_statuses:
                raise FetchError(f"HTTP {resp.status} for {method} {url[:160]}")
            return resp
        err = CheckTimeout if timeouts == self.s.retries + 1 else FetchError
        raise err(f"{last_err} (after {self.s.retries + 1} attempts)")

    def _chrome_wait(self, wait: float) -> float:
        """A Chrome wait, cut to the time budget's end (at least a second, as for browser=True)."""
        if self.deadline is not None:
            wait = max(1.0, min(wait, self.deadline - time.monotonic()))
        return wait

    def _chrome_send(self, method: str, full: str, json, data, headers, timeout, origin: str, host: str,
                     group: HostGroup, interval: float) -> Resp:
        """One attempt through the run's Chrome, in the turn the caller took. The request is built exactly as httpx
        would send it; Chrome is given its method, URL, body and headers (but CHROME_SETS). A site without a tab gets
        one first, by loading its robots.txt: that load uses this turn and the request takes the next one, unless the
        request is that same GET of robots.txt, which the load answers."""
        from .chrome_session import TabClosed
        session = self.gate.chrome()
        req = self.client.build_request(method, full, json=json, data=data, headers=headers)
        sent, body = chrome_headers(req.headers), req.read() or None
        wait = self._chrome_wait(timeout or self.s.read_timeout)
        for _ in range(3):
            opened = session.ensure_tab(origin, self._chrome_wait(chrome_timeout(self.s.read_timeout)))
            if opened is not None:
                if method == "GET" and full == origin + "/robots.txt" and body is None:
                    return opened
                self._check_deadline(method, full)
                if not self.gate.wait_group(group, self.deadline):
                    raise CheckTimeout(f"time budget exhausted waiting for {group.name}'s next turn before {method} "
                                       f"{full[:160]} ({self.requests_made} requests made)")
                self.gate.wait_turn(host, interval)
                wait = self._chrome_wait(timeout or self.s.read_timeout)
            try:
                return session.request(method, full, sent, body, wait)
            except TabClosed:
                continue  # closed since (retired after a challenge, or for room): open it again, in a turn of its own
        raise FetchError(f"Chrome kept losing its tab for {origin} ({method} {full[:160]})")

    def _check_deadline(self, method: str, url: str) -> None:
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise CheckTimeout(f"time budget exhausted before {method} {url[:160]} "
                               f"({self.requests_made} requests made)")

    def _fetch_robots(self, url: str, host: str, interval: float, group: HostGroup | None):
        """robots.txt takes its turn like any request to the host: its pace and its group's pace. Until 2026-11-17 it
        went out unpaced, so each morning, with every copy older than robots_ttl_hours, began with a burst of them to
        dozens of Workday sites at once. A 429 from a group's host pauses the group and robots.txt is asked again after
        the pause; after the group's pauses the 429 is the answer, as before (RFC 9309: a 4xx means no rules)."""
        paused = 0
        while True:
            self._check_deadline("GET", url)
            if group is not None and not self.gate.wait_group(group, self.deadline):
                raise CheckTimeout(f"time budget exhausted waiting for {group.name}'s next turn before GET {url[:160]} "
                                   f"({self.requests_made} requests made)")
            self.gate.wait_turn(host, interval)
            if group is not None and group.browser:
                from .browser import BrowserUnavailable
                try:
                    r = self.gate.chrome().robots(url, chrome_headers(self.client.build_request("GET", url).headers),
                                                  self._chrome_wait(chrome_timeout(15)))
                except BrowserUnavailable:
                    raise
                except FetchError:
                    return None, ""
                status, text = r.status, r.text
            else:
                try:
                    r = self.client.get(url, timeout=15)
                except httpx.HTTPError:
                    return None, ""
                status, text = r.status_code, r.text
            if status == 429 and group is not None and paused < group.pauses:
                self.gate.pause_group(group, url, r)
                paused += 1
                continue
            return status, text
