"""Boards that go dead, get abandoned or are replaced (liveness.py): per-source emptying and drops, stale boards,
companies never processed, new Workday sites, careers pages that point somewhere new. Every alert must reach the
health email, and nothing here may ever affect a company's poll or the run's emails."""
import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from internwatch import liveness
from internwatch.adapters import get_checker
from internwatch.adapters.base import FetchContext
from internwatch.db import DB, iso, parse_iso, utcnow
from internwatch.detect import from_text
from internwatch.health import Outcome, Verdict
from internwatch.http import Cassette, HostGate, Http, Resp
from internwatch.models import CheckTimeout, FetchError, RobotsBlocked
from internwatch.runner import RunOptions, Runner

from conftest import REPO, FakeChecker, company, job

GH2 = {"boards": ["main", "campus"]}


def _jobs(main: int, campus: int):
    return ([job(f"m{i}", f"Engineer {i}", extra={"board": "main"}) for i in range(main)]
            + [job(f"c{i}", f"Intern {i}", extra={"board": "campus"}) for i in range(campus)])


def _observe(cfg, db, c, jobs, **kw):
    o = Outcome(company=c, jobs=jobs, **kw)
    return liveness.observe(cfg, db, c, o, Verdict(True), {j.id for j in jobs})


def test_sources_of_several_boards_multi_sources_and_slices():
    c = company("acme", checker="greenhouse", settings=GH2)
    counts = liveness.source_counts(c, Outcome(company=c, jobs=_jobs(3, 0)))
    assert counts == {"board:main": ("greenhouse board main", 3), "board:campus": ("greenhouse board campus", 0)}
    m = company("plaid", checker="multi", settings={"sources": [{"checker": "ashby", "settings": {"board": "plaid"}},
                                                              {"checker": "ripplematch", "settings": {"company_id": 1}}]})
    counts = liveness.source_counts(m, Outcome(company=m, jobs=[job("a", "SWE", extra={"source": 0})]))
    assert sorted(v for v in counts.values()) == [("ashby source 1", 1), ("ripplematch source 2", 0)]
    a = company("apple", checker="apple")
    jobs = [job("1", "ML Intern", employment_type="Intern (Apple Internships team)"), job("2", "Engineer")]
    assert liveness.source_counts(a, Outcome(company=a, jobs=jobs)) == {"slice": ("Apple's Internships team", 1)}
    assert liveness.source_counts(company("solo", checker="greenhouse", settings={"board": "x"}),
                                  Outcome(company=company("solo"), jobs=jobs)) == {}


def test_a_board_that_empties_alerts_on_the_second_poll_and_stays_open(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings=GH2)
    cfg = make_cfg([c])
    assert _observe(cfg, memdb, c, _jobs(10, 3)) == ([], [])
    assert _observe(cfg, memdb, c, _jobs(10, 0)) == ([], [])  # one empty poll: could be a blip
    problems, _ = _observe(cfg, memdb, c, _jobs(10, 0))
    assert [(p["kind"], p["summary"]) for p in problems] == [("board empty", "greenhouse board campus now lists 0 jobs (it listed 3)")]
    assert problems[0]["reset_kv"] == "live_alert:acme:board:campus:empty"
    assert _observe(cfg, memdb, c, _jobs(10, 0)) == ([], [])  # still empty: reminded weekly, not every poll
    memdb.set("live_alert:acme:board:campus:empty", "")  # the health email failed (_reopen_alerts) …
    problems, _ = _observe(cfg, memdb, c, _jobs(10, 0))
    assert problems[0]["summary"].endswith("still lists 0 jobs (reminder)")  # … so it is raised again
    problems, recovered = _observe(cfg, memdb, c, _jobs(10, 2))
    assert problems == [] and recovered[0]["summary"] == "greenhouse board campus lists jobs again (2)"


def test_a_board_that_loses_more_than_half_alerts_once(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings=GH2)
    cfg = make_cfg([c])
    _observe(cfg, memdb, c, _jobs(10, 12))
    assert _observe(cfg, memdb, c, _jobs(10, 4))[0] == []
    problems, _ = _observe(cfg, memdb, c, _jobs(10, 4))
    assert problems[0]["kind"] == "board drop" and "(12 → 4)" in problems[0]["summary"]
    assert _observe(cfg, memdb, c, _jobs(10, 4))[0] == []  # the new count is accepted


def test_nothing_is_judged_on_an_incomplete_poll_or_while_the_company_alert_is_out(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings=GH2)
    cfg = make_cfg([c])
    _observe(cfg, memdb, c, _jobs(10, 3))
    for kw in ({"degraded": "campus: HTTP 503"}, {"partial": True}, {"mode": "quick"}):
        for _ in range(3):
            assert _observe(cfg, memdb, c, _jobs(10, 0), **kw) == ([], [])
    memdb.set("zero_open:acme", "2026-10-27T00:00:00Z")
    for _ in range(3):
        assert _observe(cfg, memdb, c, _jobs(10, 0)) == ([], [])
    assert memdb.one("SELECT zero_streak FROM source_health WHERE source='board:campus'")["zero_streak"] == 0


def test_a_big_board_without_new_postings_is_stale_until_one_appears(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings={"board": "acme"})
    cfg = make_cfg([c])
    today = datetime.now(timezone.utc).date()  # liveness judges dates in UTC
    old = [job(str(i), f"Engineer {i}", posted=(today - timedelta(days=70 + i)).isoformat()) for i in range(25)]
    problems, _ = _observe(cfg, memdb, c, old)
    assert problems[0]["kind"] == "board stale" and "in 70 days" in problems[0]["summary"]
    assert "every ~1 days" in problems[0]["summary"]
    fresh = old + [job("new", "Engineer", posted=today.isoformat())]
    problems, recovered = _observe(cfg, memdb, c, fresh)
    assert problems == [] and recovered[0]["summary"] == "new postings on the job list again"
    small = [job(str(i), "Quant", posted="2026-01-01") for i in range(8)]  # small boards post in bursts: not judged
    assert _observe(cfg, memdb, company("tiny"), small) == ([], [])


def test_a_company_never_processed_in_two_runs_is_reported(make_cfg, memdb):
    a, b = company("acme"), company("beta")
    cfg = make_cfg([a, b])
    assert liveness.unchecked(cfg, memdb, [a, b], {"acme"}) == ([], [])
    problems, _ = liveness.unchecked(cfg, memdb, [a, b], {"acme"})
    assert [(p["key"], p["kind"]) for p in problems] == [("beta", "not checked")]
    _, recovered = liveness.unchecked(cfg, memdb, [a, b], {"acme", "beta"})
    assert recovered[0]["summary"] == "checked again" and memdb.get("unchecked_runs:beta") == ""


def test_a_new_workday_site_in_the_cached_robots_txt(make_cfg, memdb, tmp_path):
    c = company("acme", checker="workday", settings={"host": "acme.wd5.myworkdayjobs.com", "tenant": "acme",
                                                     "site": "External"})
    cfg = make_cfg([c])
    gate = HostGate(tmp_path / "robots")
    origin = "https://acme.wd5.myworkdayjobs.com"
    gate._disk_put(origin, 200, "User-agent: *\nAllow: /External/\nAllow: /Alumni/\nDisallow: /refreshFacet/\n")
    assert liveness.scan_workday_sites(cfg, memdb, gate) == []  # first look: baseline (Alumni is old news)
    gate._disk_put(origin, 200, "User-agent: *\nAllow: /External/\nAllow: /Alumni/\nAllow: /Students/\n")
    problems = liveness.scan_workday_sites(cfg, memdb, gate)
    assert [p["summary"] for p in problems] == ["Workday tenant acme.wd5.myworkdayjobs.com lists new sites: Students"]
    assert liveness.scan_workday_sites(cfg, memdb, gate) == []  # alerted once


class PageHttp:
    def __init__(self, pages):
        self.pages = pages
        self.headers = None
        self.calls = []

    def get_text(self, url, **kw):
        self.headers = kw.get("headers")
        self.calls.append(url)
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return page


def test_a_careers_page_that_points_at_a_new_job_site(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings={"board": "acme"})
    cfg = make_cfg([c])
    url = c.careers_url[0]
    gh = '<script src="https://boards.greenhouse.io/embed/job_board/js?for=acme"></script>'
    assert liveness.scan_pages(cfg, memdb, PageHttp({url: gh}), budget_end=float("inf")) == []  # baseline
    memdb.set("page_scan_at:acme", "")
    moved = '<a href="https://jobs.ashbyhq.com/acme-inc">Open roles</a>'
    problems = liveness.scan_pages(cfg, memdb, PageHttp({url: moved}), budget_end=float("inf"))
    assert problems[0]["kind"] == "moved?"
    assert problems[0]["summary"] == ("the careers page now points at ashby:board=acme-inc and no longer mentions "
                                      "greenhouse:board=acme")
    memdb.set("page_scan_at:acme", "")
    assert liveness.scan_pages(cfg, memdb, PageHttp({url: RuntimeError("bot wall")}), float("inf")) == []
    retry = PageHttp({url: moved})
    assert liveness.scan_pages(cfg, memdb, retry, float("inf")) == [] and retry.calls == [url]  # the next morning
    later = PageHttp({url: moved})
    assert liveness.scan_pages(cfg, memdb, later, float("inf")) == [] and later.calls == []  # this week's look is done


def test_careers_pages_accept_any_content_type(make_cfg, memdb):
    """Wolfram's server answers 406 to Accept: text/html alone (its page is typed application/x-httpd-php)."""
    c = company("acme", checker="greenhouse", settings={"board": "acme"})
    http = PageHttp({c.careers_url[0]: "<html></html>"})
    liveness.scan_pages(make_cfg([c]), memdb, http, budget_end=float("inf"))
    assert http.headers["Accept"].startswith("text/html,") and "*/*" in http.headers["Accept"]


# careers pages: each portal on its own ---------------------------------------------------------------------------

def _look(cfg, db, c, page):
    """One weekly look at c's careers page (made due, as a week after the last one)."""
    db.set(f"page_scan_at:{c.key}", "")
    return liveness.scan_pages(cfg, db, PageHttp({c.careers_url[0]: page}), float("inf"))


def test_each_icims_portal_avature_portal_and_eightfold_domain_counts_on_its_own(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings={"board": "acme"})
    cfg = make_cfg([c])
    page = ('<a href="https://careers-acme.icims.com/jobs/1/intern/job">Apply</a><img src="https://cdn07.icims.com/a.png">'
            '<script src="https://cookie-policy-scripts.icims.com/acme/careers.acme.com/script.js"></script>'
            '<a href="https://acme.avature.net/Careers/SearchJobs">Jobs</a>')
    assert _look(cfg, memdb, c, page) == []  # first look
    assert _look(cfg, memdb, c, page.replace("/Careers/", "/careers/")) == []  # the same portals
    problems = _look(cfg, memdb, c, page + '<a href="https://campus-acme.icims.com/jobs">Campus</a>'
                     '<a href="https://acme.avature.net/en_US/Internships">Interns</a>'
                     '<a href="https://acme.eightfold.ai/careers?domain=acme.com">Join</a>')
    assert [p["summary"] for p in problems] == [
        "the careers page now points at avature:site=acme.avature.net/internships, eightfold:domain=acme.com, "
        "icims:portal=campus-acme.icims.com"]
    e = company("bolt", checker="eightfold", settings={"host": "jobs.bolt.com", "domain": "bolt.com", "api": "pcsx"})
    cfg = make_cfg([e])
    assert _look(cfg, memdb, e, "<html></html>") == []
    assert _look(cfg, memdb, e, '<a href="https://app.eightfold.ai/careers?domain=bolt.com">Jobs</a>') == []  # its own


def test_what_counts_as_a_portal_on_a_page():
    def systems(page):
        return liveness.page_systems(page, from_text(page, ""))
    assert systems('<img src="https://cdn07.icims.com/a.png"><a href="https://www.icims.com/legal/">Privacy</a>'
                   '<script src="https://cookie-policy-scripts.icims.com/sig/careers.sig.com/script.js"></script>'
                   '<a href="https://careers-sig.icims.com/jobs/login">Log in</a>') == {"icims:portal=careers-sig.icims.com"}
    assert systems('<a href="https://acme.avature.net/Careers/SearchJobs/">a</a><a href="https://acme.avature.net/careers">'
                   'b</a><a href="https://acme.avature.net/en_US/careers/JobDetail/x/1">c</a>') == {
        "avature:site=acme.avature.net/careers"}
    for page in ('<a href="https://app.eightfold.ai/careers?domain=mlp.com">x</a>',  # Millennium's page writes all four
                 '{"link": "https://app.eightfold.ai/careers?domain=mlp.com\\"}',
                 '<a href="https://app.eightfold.ai/careers?pid=1&amp;amp;domain=mlp.com">x</a>',
                 '{"u": "https:\\/\\/app.eightfold.ai\\/careers?pid=1\\u0026domain=mlp.com"}'):
        assert systems(page) == {"eightfold:domain=mlp.com"}, page
    assert systems('<a href="https://boards.greenhouse.io/acme">x</a>') == {"greenhouse:board=acme"}  # others unchanged


def test_a_portal_that_drops_off_the_page_or_that_a_stored_posting_links_stays_quiet(make_cfg, memdb):
    c = company("acme")
    cfg = make_cfg([c])
    a = '<a href="https://careers-acme.icims.com/jobs/1/x/job">x</a>'
    b = '<a href="https://campus-acme.icims.com/jobs/2/y/job">y</a>'
    assert _look(cfg, memdb, c, a + b) == []
    assert _look(cfg, memdb, c, a) == []  # the campus portal's only posting closed …
    assert _look(cfg, memdb, c, a + b) == []  # … and a new one opened: a portal the page linked before
    memdb.conn.execute("INSERT INTO jobs(company, job_id, title, url, first_seen, last_seen) VALUES "
                       "('acme', '3', 'Intern', 'https://globalmobility-acme.icims.com/jobs/3/intern/job', 't', 't')")
    z = '<a href="https://globalmobility-acme.icims.com/jobs/3/intern/job">z</a>'
    assert _look(cfg, memdb, c, a + b + z) == []  # InternWatch already reads postings there
    assert [p["summary"] for p in _look(cfg, memdb, c, a + b + z + '<a href="https://new-acme.icims.com/">n</a>')] == [
        "the careers page now points at icims:portal=new-acme.icims.com"]


def test_a_configured_portal_is_gone_only_once_no_portal_of_its_system_is_left(make_cfg, memdb):
    c = company("yelp", checker="multi", settings={"sources": [
        {"checker": "icims", "settings": {"portal": "https://uscareers-yelp.icims.com"}},
        {"checker": "phenom", "settings": {"base_url": "https://www.yelp.careers", "ref_num": "YELPUS"}}]})
    cfg = make_cfg([c])
    us = '<a href="https://uscareers-yelp.icims.com/jobs/1/x/job">x</a>'
    ca = '<a href="https://cancareers-yelp.icims.com/jobs/2/y/job">y</a>'
    assert _look(cfg, memdb, c, us + ca) == []
    assert _look(cfg, memdb, c, ca) == []  # its first results are all Canadian this week: still on iCIMS
    assert [p["summary"] for p in _look(cfg, memdb, c, "<html></html>")] == [
        "the careers page no longer mentions icims:portal=uscareers-yelp.icims.com"]
    assert _look(cfg, memdb, c, "<html></html>") == []  # said once
    p = company("acme")
    portal = '<a href="https://campus-acme.icims.com/jobs/1/x/job">x</a>'
    assert _look(make_cfg([p]), memdb, p, portal) == [] and _look(make_cfg([p]), memdb, p, "<html></html>") == []
    p = company("acme", checker="icims", settings={"portal": "https://campus-acme.icims.com"})  # configured later
    assert _look(make_cfg([p]), memdb, p, "<html></html>") == []  # not linked last week: nothing gone


def test_last_weeks_looks_carry_over_without_false_alerts_or_a_blank_week(make_cfg, memdb):
    a = company("booking", checker="jibe", settings={"host": "jobs.booking.com"})
    b = company("aqr", checker="greenhouse", settings={"board": "aqr"})
    e = company("capone", checker="workday", settings={"host": "capitalone.wd12.myworkdayjobs.com", "tenant": "capitalone",
                                                       "site": "Capital_One"})
    cfg = make_cfg([a, b, e])
    wd = "workday:host=capitalone.wd12.myworkdayjobs.com,site=capital_one,tenant=capitalone"
    memdb.set("page_systems:booking", '["icims:"]')  # what last week's look stored: every portal as one
    memdb.set("page_systems:aqr", "[]")
    memdb.set("page_systems:capone", json.dumps([wd]))
    pages = {a.careers_url[0]: '<a href="https://external-x.icims.com/jobs/login">a</a><a href="https://internal-x.icims.com/">b</a>',
             b.careers_url[0]: '<a href="https://jobs.ashbyhq.com/aqr">Open roles</a>',
             e.careers_url[0]: '<a href="https://capitalone.wd12.myworkdayjobs.com/Capital_One">Jobs</a>'
                               '<a href="https://capitalone.eightfold.ai/careers/join?form=1">Join</a>'}
    problems = liveness.scan_pages(cfg, memdb, PageHttp(pages), float("inf"))
    # compared with last week's look as before: AQR's new Ashby board alerts; Booking's portals and Capital One's
    # Eightfold link, which that look couldn't tell apart or see, are taken as they are now
    assert [(p["key"], p["summary"]) for p in problems] == [("aqr", "the careers page now points at ashby:board=aqr")]
    assert memdb.get("page_systems:booking") == '["icims:"]'
    assert json.loads(memdb.get("page_systems_v2:booking")) == {
        "systems": ["icims:portal=external-x.icims.com", "icims:portal=internal-x.icims.com"],
        "portals": ["icims:portal=external-x.icims.com", "icims:portal=internal-x.icims.com"]}
    for k in ("booking", "aqr", "capone"):
        memdb.set(f"page_scan_at:{k}", "")
    pages[a.careers_url[0]] += '<a href="https://campus-x.icims.com/">c</a>'
    problems = liveness.scan_pages(cfg, memdb, PageHttp(pages), float("inf"))  # a week later: portal by portal
    assert [(p["key"], p["summary"]) for p in problems] == [
        ("booking", "the careers page now points at icims:portal=campus-x.icims.com")]


def test_a_change_on_the_first_look_since_the_upgrade_comes_back_after_a_failed_email(make_cfg, memdb):
    c = company("aqr", checker="greenhouse", settings={"board": "aqr"})
    cfg = make_cfg([c])
    memdb.set("page_systems:aqr", '["greenhouse:board=aqr"]')
    memdb.set("page_scan_at:aqr", "2026-10-01T00:00:00Z")
    moved = PageHttp({c.careers_url[0]: '<a href="https://jobs.ashbyhq.com/aqr">Open roles</a>'})
    problems = liveness.scan_pages(cfg, memdb, moved, float("inf"))
    assert [p["summary"] for p in problems] == [
        "the careers page now points at ashby:board=aqr and no longer mentions greenhouse:board=aqr"]
    _email_failed(memdb, problems)
    assert memdb.get("page_systems_v2:aqr") == "" and memdb.get("page_systems:aqr") == '["greenhouse:board=aqr"]'
    assert [p["summary"] for p in liveness.scan_pages(cfg, memdb, moved, float("inf"))] == [problems[0]["summary"]]


def test_a_failed_email_puts_back_the_portals_known_before(make_cfg, memdb):
    c = company("acme")
    cfg = make_cfg([c])
    a, b = '<a href="https://careers-acme.icims.com/">a</a>', '<a href="https://campus-acme.icims.com/">b</a>'
    _look(cfg, memdb, c, a + b)
    _look(cfg, memdb, c, a)
    before = memdb.get("page_systems_v2:acme")
    problems = _look(cfg, memdb, c, a + '<a href="https://new-acme.icims.com/">n</a>')
    assert len(problems) == 1
    _email_failed(memdb, problems)
    assert memdb.get("page_systems_v2:acme") == before
    assert [p["summary"] for p in _look(cfg, memdb, c, a + '<a href="https://new-acme.icims.com/">n</a>')] == [
        problems[0]["summary"]]


# careers pages: a refused read is retried the next morning -----------------------------------------------------

def test_a_refused_page_is_read_again_first_the_next_morning_and_only_once(make_cfg, memdb):
    a, b = company("acme"), company("beta")
    cfg = make_cfg([a, b])
    memdb.set("page_scan_at:acme", iso(utcnow() - timedelta(days=9)))
    memdb.set("page_scan_at:beta", iso(utcnow() - timedelta(days=8)))
    http = PageHttp({a.careers_url[0]: FetchError("HTTP 403 for GET x"), b.careers_url[0]: "<html></html>"})
    liveness.scan_pages(cfg, memdb, http, float("inf"))
    assert memdb.get("page_scan_retry:acme") == "1"
    assert parse_iso(memdb.get("page_scan_at:acme")) < utcnow() - timedelta(days=8)  # still due
    http.calls.clear()
    liveness.scan_pages(cfg, memdb, http, float("inf"))  # the next morning: refused again …
    assert http.calls == [a.careers_url[0]]
    assert not memdb.get("page_scan_retry:acme") and memdb.get("page_scan_at:acme") >= iso(utcnow() - timedelta(minutes=1))
    http.calls.clear()
    liveness.scan_pages(cfg, memdb, http, float("inf"))
    assert http.calls == []  # … so it waits for next week
    memdb.set("page_scan_retry:acme", "1")
    memdb.set("page_scan_at:beta", "")  # never read: due too, but the retry goes first
    http.pages[a.careers_url[0]] = "<html></html>"
    http.calls.clear()
    liveness.scan_pages(cfg, memdb, http, float("inf"))
    assert http.calls == [a.careers_url[0], b.careers_url[0]] and not memdb.get("page_scan_retry:acme")


@pytest.mark.parametrize("error", [FetchError("HTTP 503 for GET x (after 4 attempts)"), RuntimeError("bot wall"),
                                   CheckTimeout("timeout (ReadTimeout) for GET x (after 4 attempts)")])
def test_a_5xx_a_timeout_or_a_bot_wall_is_read_again_the_next_morning(make_cfg, memdb, error):
    c = company("acme")
    liveness.scan_pages(make_cfg([c]), memdb, PageHttp({c.careers_url[0]: error}), float("inf"))
    assert memdb.get("page_scan_retry:acme") == "1" and memdb.get("page_scan_at:acme") is None


@pytest.mark.parametrize("error", [RobotsBlocked("robots.txt disallows x (Disallow: /)"), FetchError("HTTP 404 for GET x")])
def test_a_robots_block_or_a_missing_page_waits_a_week(make_cfg, memdb, error):
    c = company("acme")
    cfg = make_cfg([c])
    http = PageHttp({c.careers_url[0]: error})
    liveness.scan_pages(cfg, memdb, http, float("inf"))
    assert not memdb.get("page_scan_retry:acme") and memdb.get("page_scan_at:acme")
    liveness.scan_pages(cfg, memdb, http, float("inf"))
    assert http.calls == [c.careers_url[0]]


def test_a_retry_is_never_read_for_a_company_blocked_since_or_after_the_budget(make_cfg, memdb):
    c = company("acme")
    memdb.set("page_scan_retry:acme", "1")
    http = PageHttp({c.careers_url[0]: "<html></html>"})
    liveness.scan_pages(make_cfg([c], liveness={"blocked": ["acme"]}), memdb, http, float("inf"))
    liveness.scan_pages(make_cfg([c]), memdb, http, budget_end=0)  # the page check's time is already spent
    assert http.calls == [] and memdb.get("page_scan_retry:acme") == "1" and memdb.get("page_scan_at:acme") is None


def test_a_page_the_parsing_chokes_on_does_not_stay_first_in_line(make_cfg, memdb, monkeypatch):
    c = company("acme")
    monkeypatch.setattr(liveness, "page_systems", lambda text, found: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        liveness.scan_pages(make_cfg([c]), memdb, PageHttp({c.careers_url[0]: "<html></html>"}), float("inf"))
    assert memdb.get("page_scan_at:acme")  # read: the next run goes on to the other pages


def test_an_emptied_campus_board_in_a_real_recording(make_cfg, memdb):
    """Klaviyo's recorded fixture, with the campus board answering an empty list on two polls."""
    cas = Cassette.load(REPO / "tests" / "fixtures" / "cassettes" / "klaviyo.json.gz")
    c = company("klaviyo", checker="greenhouse", settings=cas.meta["settings"])
    cfg = make_cfg([c])

    def poll(empty_campus: bool):
        ex = copy.deepcopy(cas.exchanges)
        for e in ex:
            if empty_campus and e["url"].endswith("/boards/klaviyocampus/jobs"):
                e["text"] = json.dumps({"jobs": [], "meta": {"total": 0}})
        ctx = FetchContext()
        jobs = get_checker("greenhouse").fetch(Http(replay=Cassette(exchanges=ex)), cas.meta["settings"], ctx)
        return liveness.observe(cfg, memdb, c, Outcome(company=c, jobs=jobs, degraded=ctx.degraded), Verdict(True),
                                {j.id for j in jobs})

    assert poll(False) == ([], [])
    assert poll(True)[0] == []
    problems, _ = poll(True)
    assert problems[0]["summary"].startswith("greenhouse board klaviyocampus now lists 0 jobs")


def test_a_bug_in_the_liveness_checks_never_costs_the_run(make_cfg, monkeypatch):
    cfg = make_cfg([company("acme")])
    db = DB(cfg.settings.path("db"))
    monkeypatch.setattr(Runner, "online", lambda self: True)

    def boom(*a, **kw):
        raise RuntimeError("liveness bug")
    monkeypatch.setattr(liveness, "observe", boom)
    monkeypatch.setattr(liveness, "unchecked", boom)
    r = Runner(cfg, db=db, checker_fn=FakeChecker({"acme": [[job("1", "Software Engineer Intern (Summer 2027)")]]}))
    s = r.run(RunOptions(crosscheck=False, send=False, scheduled_mail=False))
    assert s.seeded == ["acme"] and not s.failed
    assert [e["kind"] for e in db.q("SELECT kind FROM emails")] == ["seed"]


# a health email that fails to send: every alert comes back on the next run ----------------------------------

def _email_failed(db, problems):
    """What runner._reopen_alerts does when the health email carrying `problems` did not go out."""
    for p in problems:
        liveness.restore(db, p)
        db.set(p["reset_kv"], "")


def test_a_failed_email_brings_back_a_careers_page_that_moved(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings={"board": "acme"})
    cfg = make_cfg([c])
    url = c.careers_url[0]
    gh = '<script src="https://boards.greenhouse.io/embed/job_board/js?for=acme"></script>'
    moved = '<a href="https://jobs.ashbyhq.com/acme-inc">Open roles</a>'
    liveness.scan_pages(cfg, memdb, PageHttp({url: gh}), float("inf"))
    memdb.set("page_scan_at:acme", "2026-10-01T00:00:00Z")  # last week's look
    problems = liveness.scan_pages(cfg, memdb, PageHttp({url: moved}), float("inf"))
    assert [p["kind"] for p in problems] == ["moved?"]
    _email_failed(memdb, problems)
    assert memdb.get("page_scan_at:acme") == "2026-10-01T00:00:00Z"  # due again on the next run …
    again = liveness.scan_pages(cfg, memdb, PageHttp({url: moved}), float("inf"))
    assert [p["summary"] for p in again] == [p["summary"] for p in problems]  # … and raised again


def test_a_failed_email_brings_back_a_new_workday_site(make_cfg, memdb, tmp_path):
    c = company("acme", checker="workday", settings={"host": "acme.wd5.myworkdayjobs.com", "tenant": "acme",
                                                     "site": "External"})
    cfg = make_cfg([c])
    gate = HostGate(tmp_path / "robots")
    origin = "https://acme.wd5.myworkdayjobs.com"
    gate._disk_put(origin, 200, "User-agent: *\nAllow: /External/\n")
    liveness.scan_workday_sites(cfg, memdb, gate)
    gate._disk_put(origin, 200, "User-agent: *\nAllow: /External/\nAllow: /Students/\n")
    problems = liveness.scan_workday_sites(cfg, memdb, gate)
    assert len(problems) == 1
    _email_failed(memdb, problems)
    assert [p["summary"] for p in liveness.scan_workday_sites(cfg, memdb, gate)] == [problems[0]["summary"]]


def test_a_failed_email_brings_back_a_board_drop(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings=GH2)
    cfg = make_cfg([c])
    _observe(cfg, memdb, c, _jobs(10, 12))
    _observe(cfg, memdb, c, _jobs(10, 4))
    problems, _ = _observe(cfg, memdb, c, _jobs(10, 4))
    assert [p["kind"] for p in problems] == ["board drop"]
    _email_failed(memdb, problems)
    again, _ = _observe(cfg, memdb, c, _jobs(10, 4))
    assert [p["summary"] for p in again] == [problems[0]["summary"]]  # "(12 → 4)" again, not lost
    assert _observe(cfg, memdb, c, _jobs(10, 4))[0] == []  # delivered this time: accepted as before


def test_alerts_without_a_saved_baseline_are_unchanged():
    """Only the checks that move a baseline before alerting carry restore fields; every other alert is as before."""
    p = liveness._problem(company("acme"), "board empty", "s", "d", None, "live_alert:acme:x")
    assert set(p) == {"key", "name", "checker", "kind", "summary", "detail", "since", "careers_url", "reset_kv"}


def test_the_runner_raises_a_board_drop_again_after_its_email_failed(make_cfg, monkeypatch):
    from internwatch.config import Secrets
    from internwatch.mailer import Mailer
    monkeypatch.setattr(Runner, "online", lambda self: True)
    monkeypatch.setattr("internwatch.mailer.time.sleep", lambda s: None)
    c = company("acme", checker="greenhouse", settings=GH2)
    cfg = make_cfg([c])
    cfg.secrets = Secrets(smtp_user="me@example.com", smtp_password="app-password")
    db = DB(cfg.settings.path("db"))
    sent = []

    def smtp(self, msg):
        if fail_next:
            raise OSError("535 bad credentials")
        sent.append(msg["Subject"])
    monkeypatch.setattr(Mailer, "_smtp_send", smtp)
    r = Runner(cfg, db=db, checker_fn=FakeChecker({"acme": [_jobs(10, 12), _jobs(10, 4), _jobs(10, 4), _jobs(10, 4)]}))
    opts = RunOptions(crosscheck=False, send=True, scheduled_mail=False, force=True)
    fail_next = False
    r.run(opts)
    r.run(opts)
    fail_next = True
    s3 = r.run(opts)
    assert [p["kind"] for p in s3.problems] == ["board drop"] and s3.email_errors
    fail_next = False
    s4 = r.run(opts)
    assert [p["summary"] for p in s4.problems] == [s3.problems[0]["summary"]]
    assert any("HEALTH" in x for x in sent)


def test_the_health_email_never_shows_the_restore_fields(make_cfg):
    from internwatch import emails
    cfg = make_cfg([company("acme")])
    plain = liveness._problem(company("acme"), "board drop", "campus fell 67% (12 → 4)", "d", "2026-10-28", "k")
    with_restore = dict(plain, restore_kv={"page_systems:acme": "[]"},
                        restore_row={"company": "acme", "source": "board:campus", "baseline": 12, "last_count": 4,
                                     "zero_streak": 0, "drop_streak": 1})
    assert emails.health(cfg, [with_restore], [], []) == emails.health(cfg, [plain], [], [])
