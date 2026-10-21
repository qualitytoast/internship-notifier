"""HTTP client: retries with backoff, robots.txt gate, deadlines, record/replay."""
import httpx
import pytest

from internwatch.http import Cassette, HostGate, Http, HttpSettings
from internwatch.models import CheckTimeout, FetchError, RobotsBlocked
from internwatch.robots import RobotsRules, from_response


def client(handler, **kw):
    h = Http(HttpSettings(backoff_base=0.01, min_interval=0, **kw), gate=HostGate())
    h._client = httpx.Client(transport=httpx.MockTransport(handler))
    return h


def test_retries_then_succeeds():
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"ok": True})

    h = client(handler)
    assert h.get_json("https://x.test/jobs") == {"ok": True}


def test_gives_up_after_retries():
    h = client(lambda req: httpx.Response(404) if req.url.path == "/robots.txt" else httpx.Response(502), retries=2)
    with pytest.raises(FetchError, match="502"):
        h.get("https://x.test/jobs")


def test_timeouts_raise_check_timeout():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ReadTimeout("slow")

    with pytest.raises(CheckTimeout):
        client(handler, retries=1).get("https://x.test/jobs")


def test_deadline_stops_requests():
    h = client(lambda req: httpx.Response(200, text="ok"))
    h.deadline = 0  # already past
    with pytest.raises(CheckTimeout, match="time budget"):
        h.get("https://x.test/jobs")


def test_robots_disallow_raises():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /api/\n")
        return httpx.Response(200, text="ok")

    h = client(handler)
    assert h.get_text("https://x.test/careers") == "ok"
    with pytest.raises(RobotsBlocked):
        h.get("https://x.test/api/jobs")


def test_robots_rules():
    r = RobotsRules("User-agent: *\nDisallow: /\nAllow: /$\nAllow: /careers\nAllow: /api/pcsx\n")
    assert r.allowed("https://h/careers/job/1") and r.allowed("https://h/api/pcsx/search?x=1")
    assert not r.allowed("https://h/api/suggest") and r.allowed("https://h/")
    r = RobotsRules("User-agent: *\nDisallow: /*cursor=\nDisallow: /results?page=\n")
    assert not r.allowed("https://h/jobs?cursor=abc") and not r.allowed("https://h/results?page=2")
    assert r.allowed("https://h/results")
    assert from_response(404, "").allowed("https://h/anything")
    assert not from_response(503, "").allowed("https://h/anything")
    assert from_response(200, "<!doctype html><html>").allowed("https://h/x")


def test_record_and_replay_roundtrip(tmp_path):
    h = client(lambda req: httpx.Response(404) if req.url.path == "/robots.txt" else
               httpx.Response(200, json={"n": req.url.params.get("page")}))
    cas = Cassette()
    h.record = cas
    assert h.get_json("https://x.test/jobs", params={"page": 2}) == {"n": "2"}
    path = tmp_path / "c.json.gz"
    cas.save(path)
    replay = Http(replay=Cassette.load(path))
    assert replay.get_json("https://x.test/jobs", params={"page": 2}) == {"n": "2"}
    with pytest.raises(FetchError, match="no recorded response"):
        replay.get("https://x.test/jobs", params={"page": 3})
