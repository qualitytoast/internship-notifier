"""Every request of a recorded morning through the real send step (Http.request) of two versions, compared.

    python -I tools/prove/sendstep.py <old ref> <recording dir> [<new dir>]      (the new version defaults to this tree)

Replays (golden.py, morning.py) never reach the send step, so they can't show that it changed nothing. Here each
version (a git ref is exported to a temporary folder; a directory is used as it is) runs in an interpreter of its own
(`sendstep.py run <version dir> <recording dir> <out.json>`) with:
- its own config's http settings (host groups, their pace, `browser`)
- every exchange of <recording dir>/morning.json.gz fed one at a time, in the recording's order, on one thread, through
  one Http and one HostGate, with the clock faked, so paces, group pauses and backoff take no real time
- httpx answered by a mock transport from the recording: a request recorded with its final answer at another URL is
  answered with a 302 to that URL, then the answer; a recorded failure is a connection error
- Chrome (a host group marked `browser`) answered by a stand-in session from the same recording (Chrome follows a
  redirect itself, so it gives the final answer at once); a recorded failure is a network error in Chrome
- robots.txt answered from the saved robots copies (data/robots; 404 for an origin without one), the same way on
  both sides, each origin once

Compared, and FAIL on any difference:
- every request's outcome: status, final URL, headers and body, or the error's class and kind
- hosts outside any `browser` group: the requests sent through httpx, in order (method, URL, headers, body); Chrome
  never asked; in the new version no request at all to a `browser` host through httpx
- hosts in a `browser` group: each request Chrome is given matches, in order, what httpx sent in the old version:
  method, URL and body exactly, and headers apart from the ones Chrome sets itself (CHROME_SETS, written below as in
  tests/test_chrome_session.py); the same for robots.txt (Chrome's loads against the old robots.txt GETs)
A redirect hop httpx follows for a `browser` host's request (Workday's maintenance page) is left out of both lists and
counted: Chrome follows it itself.
"""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

REPO = Path(__file__).resolve().parents[2]
ROBOTS_DIR = REPO / "data" / "robots"
WD_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
PAGE_HEADERS = {"Accept": "text/html,*/*;q=0.8"}
DROP = {"content-encoding", "transfer-encoding", "content-length"}  # the recording keeps bodies decoded
# The headers Chrome sets itself (the user's approved list, as in tests/test_chrome_session.py)
CHROME_SETS = {"user-agent", "accept-encoding", "host", "connection", "content-length", "cookie", "origin", "referer",
               "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform", "sec-fetch-dest", "sec-fetch-mode",
               "sec-fetch-site", "cache-control", "pragma"}


def run(version: Path, rec: Path, out: Path) -> None:
    sys.path.insert(0, str(version / "src"))
    import gzip
    import random
    import time as real_time

    import httpx

    from internwatch import config as configmod
    from internwatch import http as httpmod
    from internwatch.runner import http_settings

    random.seed(0)

    class Clock:
        """The http module's clock: sleeping moves it on at once."""

        def __init__(self):
            self.t, self.wall = 1000.0, real_time.time()

        def monotonic(self):
            return self.t

        def sleep(self, s):
            self.t += max(0.0, s)

        def time(self):
            return self.wall + self.t

        def __getattr__(self, name):
            return getattr(real_time, name)
    httpmod.time = Clock()

    cfg = configmod.load(version)
    settings = http_settings(cfg)
    browser_hosts = [g for g in settings.host_groups if getattr(g, "browser", False)]
    all_groups = list(settings.host_groups)

    def in_browser_group(host):
        return any(g.covers(host) for g in browser_hosts)

    def in_any_group_marked_browser_somewhere(host):  # for the report: hosts the new version reads through Chrome
        return any(g.covers(host) for g in all_groups if g.name == "workday")

    with gzip.open(rec / "morning.json.gz", "rt") as f:
        exchanges = json.load(f)["exchanges"]
    queues: dict[tuple, list] = {}
    for e in exchanges:
        queues.setdefault((e["method"], e["url"], e["body"]), []).append(e)

    robots: dict[str, tuple[int, str]] = {}
    for p in ROBOTS_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text())
            robots[d["origin"]] = (d["status"], d["text"])
        except (ValueError, KeyError):
            continue

    def robots_answer(origin):
        return robots.get(origin, (404, ""))

    def answer_of(method, url, bkey):
        q = queues.get((method, url, bkey)) or []
        if not q:
            return None
        return q.pop(0) if len(q) > 1 else q[0]

    def bkey_of(content: bytes) -> str:
        if not content:
            return ""
        text = content.decode("utf-8", "replace")
        if text[:1] in "{[":
            try:
                return httpmod.body_key(json.loads(text))
            except ValueError:
                pass
        if "=" in text:
            return httpmod.body_key(data=dict(parse_qsl(text, keep_blank_values=True)))
        return text

    def built(e):
        """The answer as httpx exposes it (the same headers whichever side it reaches)."""
        headers = {k: v for k, v in (e.get("headers") or {}).items() if k.lower() not in DROP}
        r = httpx.Response(int(e["status"]), headers=headers, content=(e.get("text") or "").encode("utf-8"))
        return r.status_code, {k.lower(): v for k, v in r.headers.items()}, r.content

    sent: list[dict] = []          # what reached httpx's transport or Chrome, in order
    hops: dict[str, dict] = {}     # final URL -> the recorded answer to give there (httpx follows the 302)
    current = {"i": -1, "browser": False}

    def log(via, method, url, headers, content, **kw):
        sent.append({"i": current["i"], "via": via, "method": method, "url": url,
                     "headers": [[k.lower(), v] for k, v in headers], "body": base64.b64encode(content or b"").decode(),
                     **kw})

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if url in hops:
            e = hops.pop(url)
            log("httpx", req.method, url, req.headers.multi_items(), req.content, hop=True,
                hop_of_browser=current["browser"])
            status, headers, content = built(e)
            return httpx.Response(status, headers=headers, content=content)
        if p.path == "/robots.txt" and url == origin + "/robots.txt" and not req.content and current.get("robots_check"):
            log("httpx", req.method, url, req.headers.multi_items(), req.content, robots=True)
            status, text = robots_answer(origin)
            return httpx.Response(status, text=text)
        log("httpx", req.method, url, req.headers.multi_items(), req.content)
        e = answer_of(req.method, httpmod.canonical_url(url), bkey_of(req.content))
        if e is None or "error" in e:
            raise httpx.ConnectError("recorded failure" if e else "not recorded")
        final = e.get("final_url") or url
        if final != url:
            hops[final] = e
            return httpx.Response(302, headers={"location": final})
        status, headers, content = built(e)
        return httpx.Response(status, headers=headers, content=content)

    real_client = httpx.Client
    httpmod.httpx.Client = lambda *a, **kw: real_client(*a, **{**kw, "transport": httpx.MockTransport(handler)})

    class Chrome:
        """Stands in for chrome_session.ChromeSession, answered from the recording."""

        def __init__(self):
            self.tabs: set[str] = set()

        def ensure_tab(self, origin, timeout):
            if origin in self.tabs:
                return None
            self.tabs.add(origin)
            return self._robots_resp(origin, [], tab=True)

        def robots(self, url, headers, timeout):
            origin = url.rsplit("/robots.txt", 1)[0]
            if origin not in self.tabs:
                self.tabs.add(origin)
                return self._robots_resp(origin, [], tab=True)
            return self._robots_resp(origin, headers, tab=False)

        def _robots_resp(self, origin, headers, tab):
            log("chrome-tab" if tab else "chrome", "GET", origin + "/robots.txt", headers, b"", robots=True)
            status, text = robots_answer(origin)
            r = httpx.Response(status, text=text)
            return httpmod.Resp(r.status_code, origin + "/robots.txt", {k.lower(): v for k, v in r.headers.items()},
                                r.content)

        def request(self, method, url, headers, body, timeout):
            from internwatch.models import FetchError
            log("chrome", method, url, headers, body)
            e = answer_of(method, url, bkey_of(body or b""))
            if e is None or "error" in e:
                raise FetchError(f"network error in Chrome ({'recorded failure' if e else 'not recorded'}) for "
                                 f"{method} {url[:160]}")
            status, headers_, content = built(e)
            return httpmod.Resp(status, e.get("final_url") or url, headers_, content)

        def close(self):
            pass

    try:
        from internwatch import chrome_session
        chrome = Chrome()
        chrome_session.ChromeSession = lambda *a, **kw: chrome
    except ImportError:
        pass  # a version without Chrome reading

    # the robots check's own GET of robots.txt is told apart from a fed GET of robots.txt
    fetch_robots = httpmod.Http._fetch_robots

    def robots_check(self, *a, **kw):
        current["robots_check"] = True
        try:
            return fetch_robots(self, *a, **kw)
        finally:
            current["robots_check"] = False
    httpmod.Http._fetch_robots = robots_check

    gate = httpmod.HostGate()
    http = httpmod.Http(settings, gate=gate)
    outcomes = []
    for i, e in enumerate(exchanges):
        current["i"] = i
        method, url, body = e["method"], e["url"], e["body"]
        host = urlsplit(url).netloc
        current["browser"] = in_any_group_marked_browser_somewhere(host)
        kw: dict = {}
        if body:
            if body[:1] in "{[":
                kw["json"] = json.loads(body)
            elif "=" in body:
                kw["data"] = dict(parse_qsl(body, keep_blank_values=True))
            else:
                kw["data"] = body
        if current["browser"]:
            kw["headers"] = WD_HEADERS if "/wday/cxs/" in url else PAGE_HEADERS
        try:
            r = http.request(method, url, **kw)
            outcomes.append({"status": r.status, "url": r.url, "headers": r.headers,
                             "sha": hashlib.sha256(r.content).hexdigest()})
        except Exception as err:  # noqa: BLE001 - compared by class and kind
            outcomes.append({"error": type(err).__name__, "kind": getattr(err, "kind", None)})
    out.write_text(json.dumps({"code": str(httpmod.__file__), "browser_groups": [g.name for g in browser_hosts],
                               "fed": len(exchanges), "outcomes": outcomes, "sent": sent}))
    print(f"{version}: fed {len(exchanges)}, sent {len(sent)}")


def compare(old: dict, new: dict) -> bool:
    problems = []
    a, b = old["outcomes"], new["outcomes"]
    if len(a) != len(b):
        problems.append(f"outcomes: {len(a)} against {len(b)}")
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    problems += [f"outcome {i}: {a[i]} against {b[i]}" for i in diff[:20]]

    def wd(entry):
        return any(h in urlsplit(entry["url"]).netloc for h in ("myworkdayjobs.com", "myworkdaysite.com"))

    def strip(entry):
        return {k: entry[k] for k in ("method", "url", "headers", "body")}

    # hosts outside the browser group: the same httpx requests, in order (hops of a Chrome request left out)
    old_other = [strip(e) for e in old["sent"] if e["via"] == "httpx" and not wd(e) and not e.get("hop_of_browser")]
    new_other = [strip(e) for e in new["sent"] if e["via"] == "httpx" and not wd(e) and not e.get("hop_of_browser")]
    if old_other != new_other:
        n = next((i for i, (x, y) in enumerate(zip(old_other, new_other)) if x != y), min(len(old_other), len(new_other)))
        problems.append(f"other hosts: {len(old_other)} httpx requests against {len(new_other)}; first difference "
                        f"at {n}: {old_other[n] if n < len(old_other) else None} | "
                        f"{new_other[n] if n < len(new_other) else None}")
    if any(e["via"].startswith("chrome") and not wd(e) for e in new["sent"]):
        problems.append("Chrome was asked for a host outside the Workday group")
    if any(e["via"] == "httpx" and wd(e) for e in new["sent"]):
        problems.append("the new version sent a Workday request through httpx")

    # Workday: what Chrome is given against what httpx sent
    old_wd = [e for e in old["sent"] if e["via"] == "httpx" and wd(e) and not e.get("robots") and not e.get("hop")]
    new_wd = [e for e in new["sent"] if e["via"] == "chrome" and wd(e) and not e.get("robots")]
    if len(old_wd) != len(new_wd):
        problems.append(f"Workday requests: {len(old_wd)} through httpx (old) against {len(new_wd)} given to Chrome")
    head = 0
    for x, y in zip(old_wd, new_wd):
        if (x["method"], x["url"], x["body"]) != (y["method"], y["url"], y["body"]):
            problems.append(f"Workday request differs: {x['method']} {x['url']} {x['body'][:60]} | "
                            f"{y['method']} {y['url']} {y['body'][:60]}")
            break
        want = sorted([k, v] for k, v in x["headers"] if k not in CHROME_SETS)
        if sorted(y["headers"]) != want:
            head += 1
            if head <= 3:
                problems.append(f"Workday headers differ for {x['method']} {x['url']}: httpx {want} | "
                                f"Chrome {sorted(y['headers'])}")
    old_rb = [e["url"] for e in old["sent"] if e["via"] == "httpx" and wd(e) and e.get("robots")]
    new_rb = [e["url"] for e in new["sent"] if e["via"].startswith("chrome") and wd(e) and e.get("robots")]
    if old_rb != new_rb:
        problems.append(f"Workday robots.txt: {len(old_rb)} httpx GETs against {len(new_rb)} Chrome loads")
    hops = sum(1 for e in old["sent"] if e.get("hop") and e.get("hop_of_browser"))

    def count(s, **kw):
        return sum(1 for e in s if all((e.get(k) if not callable(v) else v(e)) == (True if callable(v) else v)
                                       for k, v in kw.items()))
    print(f"fed {old['fed']} requests to each version")
    for name, d in (("old", old), ("new", new)):
        s = d["sent"]
        print(f"  {name}: browser groups {d['browser_groups']}; httpx {count(s, via='httpx')} "
              f"(Workday {sum(1 for e in s if e['via'] == 'httpx' and wd(e))}, other "
              f"{sum(1 for e in s if e['via'] == 'httpx' and not wd(e))}), Chrome requests "
              f"{sum(1 for e in s if e['via'] == 'chrome' and not e.get('robots'))}, Chrome robots.txt "
              f"{sum(1 for e in s if e['via'].startswith('chrome') and e.get('robots'))} "
              f"({sum(1 for e in s if e['via'] == 'chrome-tab')} tab loads)")
    print(f"  outcomes identical: {len(a) - len(diff)} of {len(a)}; other hosts' httpx requests identical: "
          f"{len(old_other)}; Workday requests matched: {len(new_wd)} (headers apart from CHROME_SETS: "
          f"{len(new_wd) - head} same); Workday robots.txt: {len(old_rb)}; redirect hops Chrome follows itself: {hops}")
    for p in problems:
        print("  DIFF", p)
    print("PASS" if not problems else "FAIL")
    return not problems


def main(argv: list[str]) -> int:
    if argv[:1] == ["run"]:
        run(Path(argv[1]), Path(argv[2]), Path(argv[3]))
        return 0
    old_ref, rec = argv[0], Path(argv[1]).resolve()
    new_dir = Path(argv[2]).resolve() if len(argv) > 2 else REPO
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        old_dir = tmp / "old"
        old_dir.mkdir()
        tar = subprocess.run(["git", "-C", str(REPO), "archive", old_ref, "src", "config"], check=True,
                             capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(old_dir)], input=tar, check=True)
        dumps = {}
        for name, d in (("old", old_dir), ("new", new_dir)):
            path = tmp / f"{name}.json"
            subprocess.run([sys.executable, "-I", __file__, "run", str(d), str(rec), str(path)], check=True)
            dumps[name] = json.loads(path.read_text())
        print(f"sendstep: old {dumps['old']['code']}\n          new {dumps['new']['code']}")
        return 0 if compare(dumps["old"], dumps["new"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
