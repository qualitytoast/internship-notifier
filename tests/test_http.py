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


# host groups: Workday's sites share one pace and one pause (2026-11-16: 429s at 11 requests a second across them) ----

from internwatch.http import HostGroup  # noqa: E402


def _wd_group(**kw):
    return HostGroup(name="workday", hosts=("myworkdayjobs.com", "myworkdaysite.com"), **{"per_second": 20, **kw})


def _grouped(handler, gate, **kw):
    h = Http(HttpSettings(backoff_base=0.01, min_interval=0, respect_robots=False, host_groups=(_wd_group(**kw),)),
             gate=gate)
    h._client = httpx.Client(transport=httpx.MockTransport(handler))
    return h


def test_a_host_group_paces_all_its_hosts_together_across_threads():
    import threading
    import time
    gate, times = HostGate(), []
    lock = threading.Lock()

    def handler(req):
        with lock:
            times.append((time.monotonic(), req.url.host))
        return httpx.Response(200, json={})

    hosts = [f"t{i}.wd{i % 3 + 1}.myworkdayjobs.com" for i in range(6)] + ["wd5.myworkdaysite.com"]
    threads = [threading.Thread(target=lambda h=h: [_grouped(handler, gate).get(f"https://{h}/jobs") for _ in range(3)])
               for h in hosts]
    [t.start() for t in threads]
    [t.join() for t in threads]
    stamps = sorted(t for t, _ in times)
    assert len(stamps) == 21 and len({h for _, h in times}) == 7
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert min(gaps) >= 0.05 - 0.01   # 20 a second across all seven hosts, not 20 a second each


def test_a_host_outside_the_group_is_not_paced_by_it():
    import time
    gate = HostGate()
    h = _grouped(lambda req: httpx.Response(200, json={}), gate, per_second=1)
    h.get("https://acme.wd5.myworkdayjobs.com/jobs")
    start = time.monotonic()
    h.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs")
    assert time.monotonic() - start < 0.5


def test_a_429_pauses_every_host_of_the_group_and_the_request_is_asked_again():
    import time
    gate, seen = HostGate(), []

    def handler(req):
        seen.append((time.monotonic(), req.url.host))
        if req.url.host == "a.wd1.myworkdayjobs.com" and len(seen) == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"ok": req.url.host})

    h = _grouped(handler, gate, pause_on_429=0.3)
    assert h.get_json("https://a.wd1.myworkdayjobs.com/jobs") == {"ok": "a.wd1.myworkdayjobs.com"}
    assert h.requests_made == 2 and seen[1][0] - seen[0][0] >= 0.29   # asked again after the pause, not given up
    t429 = seen[0][0]
    other = _grouped(handler, gate, pause_on_429=0.3)
    other.get_json("https://b.wd5.myworkdayjobs.com/jobs")             # another host of the group, another client
    assert seen[-1][0] - t429 >= 0.29


def test_a_group_that_keeps_answering_429_is_given_up_after_its_pauses():
    gate = HostGate()
    h = _grouped(lambda req: httpx.Response(429), gate, pause_on_429=0.01, pauses=3)
    with pytest.raises(FetchError, match="after 3 pauses of every workday host"):
        h.get("https://a.wd1.myworkdayjobs.com/jobs")
    assert h.requests_made == 4


def test_a_group_pause_never_runs_past_the_check_deadline():
    import time
    gate = HostGate()
    h = _grouped(lambda req: httpx.Response(429), gate, pause_on_429=30)
    h.deadline = time.monotonic() + 0.3
    start = time.monotonic()
    with pytest.raises(CheckTimeout, match="workday's next turn"):
        h.get("https://a.wd1.myworkdayjobs.com/jobs")
    assert time.monotonic() - start < 1
