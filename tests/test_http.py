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


def _grouped_robots(handler, gate, **kw):
    h = Http(HttpSettings(backoff_base=0.01, min_interval=0, host_groups=(_wd_group(**kw),)), gate=gate)
    h._client = httpx.Client(transport=httpx.MockTransport(handler))
    return h


def test_robots_txt_takes_the_groups_turns():
    # until 2026-11-17 robots.txt went out unpaced: each morning began with a burst of them to every Workday site
    import time
    gate, times = HostGate(), []

    def handler(req):
        times.append((time.monotonic(), req.url.path))
        return httpx.Response(404) if req.url.path == "/robots.txt" else httpx.Response(200, json={})

    for i in range(3):
        _grouped_robots(handler, gate, per_second=10).get(f"https://t{i}.wd1.myworkdayjobs.com/jobs")
    assert [p for _, p in times].count("/robots.txt") == 3
    stamps = [t for t, _ in times]
    assert min(b - a for a, b in zip(stamps, stamps[1:])) >= 0.1 - 0.01   # 10 a second, robots.txt included


def test_robots_txt_takes_the_hosts_turn():
    import time
    times = []

    def handler(req):
        times.append(time.monotonic())
        return httpx.Response(404) if req.url.path == "/robots.txt" else httpx.Response(200, json={})

    h = Http(HttpSettings(backoff_base=0.01, min_interval=0.2), gate=HostGate())
    h._client = httpx.Client(transport=httpx.MockTransport(handler))
    h.get("https://x.test/jobs")
    assert len(times) == 2 and times[1] - times[0] >= 0.19


def test_a_429_on_robots_txt_pauses_the_group_and_asks_again():
    import time
    gate, seen = HostGate(), []

    def handler(req):
        seen.append((time.monotonic(), req.url.path))
        if req.url.path == "/robots.txt":
            return httpx.Response(429) if len(seen) == 1 else httpx.Response(200, text="User-agent: *\nDisallow: /x/\n")
        return httpx.Response(200, json={"ok": 1})

    h = _grouped_robots(handler, gate, pause_on_429=0.3)
    assert h.get_json("https://a.wd1.myworkdayjobs.com/jobs") == {"ok": 1}
    assert [p for _, p in seen] == ["/robots.txt", "/robots.txt", "/jobs"]
    assert seen[1][0] - seen[0][0] >= 0.29
    with pytest.raises(RobotsBlocked):   # the real rules were kept, not a 429's "no rules"
        h.get("https://a.wd1.myworkdayjobs.com/x/1")


def test_a_robots_txt_that_keeps_answering_429_reads_as_before_after_the_pauses():
    gate, paths = HostGate(), []

    def handler(req):
        paths.append(req.url.path)
        return httpx.Response(429) if req.url.path == "/robots.txt" else httpx.Response(200, json={})

    h = _grouped_robots(handler, gate, pause_on_429=0.01, pauses=2)
    h.get("https://a.wd1.myworkdayjobs.com/jobs")   # RFC 9309: a 4xx robots.txt means no rules
    assert paths == ["/robots.txt"] * 3 + ["/jobs"]


def test_a_429_soon_after_a_pause_takes_the_next_longer_pause():
    gate, group = HostGate(), _wd_group(pause_on_429=(0.1, 0.2, 0.4), escalate_within=5)
    resp = httpx.Response(429)
    import time
    ends = []
    for _ in range(4):
        start = time.monotonic()
        ends.append(gate.pause_group(group, "https://a.wd1.myworkdayjobs.com/jobs", resp) - start)
        time.sleep(ends[-1] + 0.01)
    assert [round(x, 1) for x in ends] == [0.1, 0.2, 0.4, 0.4]   # the last step repeats


def test_a_429_long_after_a_pause_starts_again_at_the_first_step():
    import time
    gate, group = HostGate(), _wd_group(pause_on_429=(0.1, 5), escalate_within=0.1)
    resp = httpx.Response(429)
    gate.pause_group(group, "", resp)
    time.sleep(0.25)                      # the pause ended 0.15 s ago, past escalate_within
    start = time.monotonic()
    assert gate.pause_group(group, "", resp) - start == pytest.approx(0.1, abs=0.02)


def test_a_429_to_a_request_sent_before_the_pause_does_not_step_it_up():
    import time
    gate, group = HostGate(), _wd_group(pause_on_429=(0.3, 5), escalate_within=10)
    first = gate.pause_group(group, "", httpx.Response(429))
    assert gate.pause_group(group, "", httpx.Response(429)) == first   # in flight when the pause began
    time.sleep(0.31)
    start = time.monotonic()
    assert gate.pause_group(group, "", httpx.Response(429)) - start == pytest.approx(5, abs=0.05)


def test_a_group_pause_honors_a_longer_retry_after_up_to_its_cap():
    import time
    from internwatch.http import RETRY_AFTER_CAP
    group = _wd_group(pause_on_429=(1,))
    for retry_after, pause in (("7", 7), ("99999", RETRY_AFTER_CAP), ("Wed, 18 Nov 2026 07:00:00 GMT", 1)):
        start = time.monotonic()   # a fresh gate each time: a first 429
        end = HostGate().pause_group(group, "", httpx.Response(429, headers={"Retry-After": retry_after}))
        assert end - start == pytest.approx(pause, abs=0.05), retry_after


def test_a_group_pause_logs_what_the_429_said(caplog):
    import logging
    gate, group = HostGate(), _wd_group(pause_on_429=(0.01,))
    resp = httpx.Response(429, headers={"Retry-After": "0", "Server": "cloudflare", "CF-Ray": "abc-MCI",
                                        "X-RateLimit-Remaining": "0"}, text="<html>  Too   many requests</html>")
    gate.wait_group(group)
    gate.wait_group(group)
    with caplog.at_level(logging.WARNING, logger="internwatch.http"):
        gate.pause_group(group, "https://a.wd1.myworkdayjobs.com/jobs", resp)
    msg = caplog.records[-1].getMessage()
    for part in ("a.wd1.myworkdayjobs.com", "the run's first 429, after 2 requests", "retry-after=0", "server=cloudflare",
                 "cf-ray=abc-MCI", "x-ratelimit-remaining=0", "Too many requests", "429 1 in a row"):
        assert part in msg, (part, msg)


def test_a_single_pause_length_still_reads_as_one_step():
    assert _wd_group(pause_on_429=60).pause_on_429 == (60.0,)
