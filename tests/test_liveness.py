"""Boards that go dead, get abandoned or are replaced (liveness.py): per-source emptying and drops, stale boards,
companies never processed, new Workday sites, careers pages that point somewhere new. Every alert must reach the
health email, and nothing here may ever affect a company's poll or the run's emails."""
import copy
import json
import random
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from internwatch import alerts, liveness
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
    assert _observe(cfg, memdb, c, _jobs(10, 0)) == ([], [])  # still empty: the alert list repeats it, not this
    memdb.set("live_alert:acme:board:campus:empty", "")  # the health email failed (_reopen_alerts) …
    problems, _ = _observe(cfg, memdb, c, _jobs(10, 0))
    assert problems[0]["summary"].endswith("still lists 0 jobs")  # … so it is raised again
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


def test_a_board_without_new_postings_goes_quiet_until_one_appears(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings={"board": "acme"})
    cfg = make_cfg([c])
    today = datetime.now(timezone.utc).date()  # liveness judges dates in UTC
    old = [job(str(i), f"Engineer {i}", posted=(today - timedelta(days=70 + i)).isoformat()) for i in range(25)]
    problems, _ = _observe(cfg, memdb, c, old)
    assert problems[0]["kind"] == "board quiet" and "in 70 days" in problems[0]["summary"]
    assert _observe(cfg, memdb, c, old) == ([], [])  # the alert list repeats it
    fresh = old + [job("new", "Engineer", posted=today.isoformat())]
    problems, recovered = _observe(cfg, memdb, c, fresh)
    assert problems == [] and recovered[0]["summary"] == "new jobs on the job list again"


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


MAINTENANCE = '<!DOCTYPE html>\n<html lang="en" dir="ltr">\n<head><title>Workday is currently unavailable</title>'


def test_workdays_maintenance_page_in_place_of_robots_txt_is_no_look_at_the_sites(make_cfg, memdb, tmp_path):
    # 2026-11-14: Workday was down and some tenants answered /robots.txt with its maintenance page, which was cached.
    # The first look took it for a robots.txt naming no site; the next morning every site not read was "new" (HPE).
    c = company("hpe", checker="workday", settings={"host": "hpe.wd5.myworkdayjobs.com", "tenant": "hpe",
                                                    "sites": ["jobsathpe", "acjobsite"]})
    cfg = make_cfg([c])
    gate = HostGate(tmp_path / "robots")
    origin = "https://hpe.wd5.myworkdayjobs.com"
    real = ("User-agent: *\nSitemap: https://hpe.wd5.myworkdayjobs.com/Jobsathpe/siteMap.xml\n"
            "Sitemap: https://hpe.wd5.myworkdayjobs.com/ACJobSite/siteMap.xml\n"
            "Sitemap: https://hpe.wd5.myworkdayjobs.com/WFMathpe/siteMap.xml\n")
    gate._disk_put(origin, 200, MAINTENANCE)
    assert liveness.scan_workday_sites(cfg, memdb, gate) == [] and memdb.get("workday_sites:hpe.wd5.myworkdayjobs.com") is None
    gate._disk_put(origin, 200, real)
    assert liveness.scan_workday_sites(cfg, memdb, gate) == []   # the first look: a silent baseline
    gate._disk_put(origin, 200, real.replace("WFMathpe", "Students"))
    problems = liveness.scan_workday_sites(cfg, memdb, gate)     # the configured sites in another case are not new
    assert [p["summary"] for p in problems] == ["Workday tenant hpe.wd5.myworkdayjobs.com lists new sites: Students"]
    alerts.record(memdb, problems, [])
    gate._disk_put(origin, 200, MAINTENANCE)                     # another outage leaves the open alert as it is
    assert liveness.scan_workday_sites(cfg, memdb, gate) == [] and len(alerts.live(memdb, "hpe", "site")) == 1


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
    assert problems[0]["summary"] == "the careers page now points at ashby:board=acme-inc"
    memdb.set("page_scan_at:acme", "")
    problems = liveness.scan_pages(cfg, memdb, PageHttp({url: moved}), budget_end=float("inf"))  # gone two reads in a row
    assert [p["summary"] for p in problems] == ["the careers page no longer mentions greenhouse:board=acme"]
    memdb.set("page_scan_at:acme", "")
    assert liveness.scan_pages(cfg, memdb, PageHttp({url: RuntimeError("bot wall")}), float("inf")) == []
    retry = PageHttp({url: moved})
    assert liveness.scan_pages(cfg, memdb, retry, float("inf")) == [] and retry.calls == [url]  # the next morning
    later = PageHttp({url: moved})
    assert liveness.scan_pages(cfg, memdb, later, float("inf")) == [] and later.calls == []  # today's look is done


def test_a_page_in_chrome_pages_is_read_through_chrome_and_every_other_by_script(make_cfg, memdb):
    """liveness.chrome_pages (CLAUDE.md: a page a Cloudflare-style guard refuses is first tried through Chrome): that
    page is read with browser=True and no headers (Chrome sends its own); the others exactly as before."""
    a = company("acme", checker="greenhouse", settings={"board": "acme"})
    b = company("beta", checker="greenhouse", settings={"board": "beta"})
    cfg = make_cfg([a, b], liveness={"chrome_pages": [a.careers_url[0]]})
    asked = {}

    class Http(PageHttp):
        def get_text(self, url, **kw):
            asked[url] = kw
            return super().get_text(url, **kw)
    gh = '<script src="https://boards.greenhouse.io/embed/job_board/js?for={}"></script>'
    http = Http({a.careers_url[0]: gh.format("acme"), b.careers_url[0]: gh.format("beta")})
    assert liveness.scan_pages(cfg, memdb, http, budget_end=float("inf")) == []  # first looks: silent
    assert asked == {a.careers_url[0]: {"browser": True}, b.careers_url[0]: {"headers": {"Accept": "text/html,*/*;q=0.8"}}}
    assert memdb.get("page_scan_at:acme") and memdb.get("page_systems_v2:acme")  # read and remembered as any page
    assert liveness.chrome_pages(make_cfg([a], liveness={"chrome_pages": None})) == frozenset()  # none: by script


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
    assert _look(cfg, memdb, c, "<html></html>") == []  # gone once: it could flip back tomorrow
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
    state = json.loads(memdb.get("page_systems_v2:booking"))
    assert (state["systems"], state["portals"]) == (["icims:portal=external-x.icims.com", "icims:portal=internal-x.icims.com"],
                                                    ["icims:portal=external-x.icims.com", "icims:portal=internal-x.icims.com"])
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
    cfg = make_cfg([a, b], liveness={"page_scan_workers": 1})  # one at a time: the order of the reads is the order asked
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


def test_a_robots_block_waits_a_week(make_cfg, memdb):
    c = company("acme")
    cfg = make_cfg([c])
    http = PageHttp({c.careers_url[0]: RobotsBlocked("robots.txt disallows x (Disallow: /)")})
    liveness.scan_pages(cfg, memdb, http, float("inf"))
    assert not memdb.get("page_scan_retry:acme") and memdb.get("page_scan_at:acme")
    liveness.scan_pages(cfg, memdb, http, float("inf"))
    assert http.calls == [c.careers_url[0]]


@pytest.mark.parametrize("error", [FetchError("HTTP 404 for GET x"), FetchError("HTTP 503 for GET x"),
                                   CheckTimeout("timeout (ReadTimeout) for GET x")])
def test_a_page_that_is_gone_or_down_is_read_again_every_morning(make_cfg, memdb, error):
    c = company("acme")
    cfg = make_cfg([c])
    http = PageHttp({c.careers_url[0]: error})
    for _ in range(4):
        liveness.scan_pages(cfg, memdb, http, float("inf"))
    assert len(http.calls) == 4 and not memdb.get("page_scan_refused:acme") and memdb.get("page_scan_at:acme") is None
    assert [x[2:] for x in json.loads(memdb.get("blocked:rate:careers:acme"))] == [["failed"]] * 4


def test_every_careers_page_read_is_in_the_history_gone_dark_reads(make_cfg, memdb):
    c = company("acme")
    cfg = make_cfg([c])
    liveness.scan_pages(cfg, memdb, PageHttp({c.careers_url[0]: "<html></html>"}), float("inf"))
    assert [x[1] for x in json.loads(memdb.get("blocked:rate:careers:acme"))] == [1]
    assert memdb.get("blocked:ok:careers:acme")


def test_a_retry_is_never_read_for_a_company_blocked_since_or_after_the_budget(make_cfg, memdb):
    c = company("acme")
    memdb.set("page_scan_retry:acme", "1")
    http = PageHttp({c.careers_url[0]: "<html></html>"})
    liveness.scan_pages(make_cfg([c], liveness={"blocked": ["acme"]}), memdb, http, float("inf"))
    liveness.scan_pages(make_cfg([c]), memdb, http, budget_end=0)  # the page check's time is already spent
    assert http.calls == [] and memdb.get("page_scan_retry:acme") == "1" and memdb.get("page_scan_at:acme") is None


class SlowPageHttp(PageHttp):
    """PageHttp whose answers take a random few milliseconds, so pages read at once finish in any order."""
    def __init__(self, pages, seed=0, least=0.0):
        super().__init__(pages)
        self.rng, self.least, self.lock = random.Random(seed), least, threading.Lock()

    def get_text(self, url, **kw):
        with self.lock:
            pause = self.least + self.rng.random() * 0.01
        time.sleep(pause)
        return super().get_text(url, **kw)


STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z?")


def _scan_state(db):
    """Everything a page scan leaves behind, with the wall clock's readings blanked."""
    kv = {r["key"]: STAMP.sub("T", r["value"] or "") for r in db.q("SELECT key, value FROM kv")}
    rows = [{k: STAMP.sub("T", str(v)) for k, v in dict(r).items() if k != "id"} for r in db.q("SELECT * FROM alerts")]
    return kv, sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))


def test_pages_read_several_at_a_time_leave_exactly_what_one_at_a_time_leaves(make_cfg, monkeypatch):
    """Two mornings over 40 companies (a baseline, then pages that moved, refused, failed or are blocked by robots.txt):
    reading 8 at a time, finishing in a shuffled order, stores and reports exactly what reading one by one does."""
    cs = [company(f"c{i:02d}", checker="greenhouse", settings={"board": f"c{i:02d}"}) for i in range(40)]
    gh = '<script src="https://boards.greenhouse.io/embed/job_board/js?for={k}"></script>'
    moved = '<a href="https://jobs.ashbyhq.com/{k}-inc">Open roles</a>'
    errors = [FetchError("HTTP 403 for GET x"), FetchError("HTTP 503 for GET x (after 4 attempts)"),
              RobotsBlocked("robots.txt disallows x (Disallow: /)"), RuntimeError("bot wall"),
              CheckTimeout("timeout (ReadTimeout) for GET x (after 4 attempts)")]
    first = {c.careers_url[0]: gh.format(k=c.key) for c in cs}
    second = {c.careers_url[0]: (errors[i % 5] if i % 3 == 0 else moved.format(k=c.key) if i % 3 == 1
                                 else gh.format(k=c.key)) for i, c in enumerate(cs)}
    states, problems = [], []
    for workers in (1, 8):
        db = DB(":memory:")
        cfg = make_cfg(cs, liveness={"page_scan_workers": workers})
        found = []
        for pages, seed, day in ((first, 1, "2026-11-18T14:00:00Z"), (second, 2, "2026-11-19T14:00:00Z")):
            monkeypatch.setattr(liveness, "utcnow", lambda day=parse_iso(day): day)
            found.append(liveness.scan_pages(cfg, db, SlowPageHttp(pages, seed=seed + workers), float("inf")))
        states.append(_scan_state(db))
        problems.append(found)
        db.close()
    assert problems[0][0] == problems[1][0] == []  # the first look is a silent baseline
    assert [p["summary"] for p in problems[1][1]] == [p["summary"] for p in problems[0][1]] != []
    assert STAMP.sub("T", json.dumps(problems[1])) == STAMP.sub("T", json.dumps(problems[0]))
    assert states[1] == states[0]
    assert sum(1 for k in states[0][0] if k.startswith("page_scan_retry:") and states[0][0][k]) > 0


def test_pages_are_read_at_once(make_cfg, memdb):
    """Eight careers pages, each answering only once all eight are being read: one at a time, none would answer."""
    cs = [company(f"c{i}") for i in range(8)]
    barrier = threading.Barrier(8, timeout=10)

    class Together(PageHttp):
        def get_text(self, url, **kw):
            barrier.wait()
            return super().get_text(url, **kw)
    liveness.scan_pages(make_cfg(cs), memdb, Together({c.careers_url[0]: "<html></html>" for c in cs}), float("inf"))
    assert all(memdb.get(f"page_scan_at:{c.key}") and not memdb.get(f"page_scan_retry:{c.key}") for c in cs)


def test_pages_read_at_once_start_in_order_and_none_after_the_budget(make_cfg, memdb):
    """However the reads overlap, the pages read are the first ones in line: none starts once the budget is spent."""
    cs = [company(f"c{i:03d}") for i in range(200)]
    http = SlowPageHttp({c.careers_url[0]: "<html></html>" for c in cs}, least=0.005)
    liveness.scan_pages(make_cfg(cs, liveness={"page_scan_workers": 4}), memdb, http, time.monotonic() + 0.2)
    read = [c.key for c in cs if memdb.get(f"page_scan_at:{c.key}")]
    assert 0 < len(read) < len(cs)  # 200 reads of 5 ms or more, 4 at a time, can't fit in 0.2 s
    assert read == [c.key for c in cs[:len(read)]] and len(http.calls) == len(read)


def test_a_page_the_parsing_chokes_on_does_not_stay_first_in_line(make_cfg, memdb, monkeypatch):
    c = company("acme")
    monkeypatch.setattr(liveness, "page_systems", lambda text, found: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        liveness.scan_pages(make_cfg([c]), memdb, PageHttp({c.careers_url[0]: "<html></html>"}), float("inf"))
    assert memdb.get("page_scan_at:acme")  # read: the next run goes on to the other pages


def test_an_emptied_campus_board_in_a_real_recording(make_cfg, memdb, monkeypatch):
    """Klaviyo's Greenhouse boards as recorded on 20 Oct 2026, with the campus board answering an empty list on two
    polls (on the day it was recorded: weeks later the quiet-board rule would rightly call the board quiet too)."""
    cas = Cassette.load(REPO / "tests" / "fixtures" / "cassettes" / "klaviyo-greenhouse.json.gz")
    monkeypatch.setattr(liveness, "utcnow", lambda: parse_iso(cas.meta["recorded_at"]))
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


# ---------------------------------------------------------------------------------------------
# quiet failures: what no single poll shows

DAY = timedelta(days=1)


def _poll(cfg, db, c, jobs, students=0):
    """One healthy full poll: stored, recorded in checks, then judged, as the runner does it."""
    now = iso()
    db.upsert_jobs(c.key, jobs, now)
    db.add_check(1, c.key, now, 0.1, "ok", None, None, len(jobs), students, 0, 0, 1)
    return liveness.observe(cfg, db, c, Outcome(company=c, jobs=jobs), Verdict(True), set())[0]


def _age_seen(db, c, days):
    """Pretend the board was first read `days` ago."""
    then = iso(utcnow() - days * DAY)
    db.conn.execute("UPDATE jobs SET first_seen=?, baseline=1 WHERE company=?", (then, c.key))
    db.conn.execute("DELETE FROM kv WHERE key LIKE 'board_new:%'")


@pytest.mark.parametrize("size", [1, 5, 12, 300])
def test_a_frozen_board_with_no_dates_goes_quiet_after_45_days_whatever_its_size(make_cfg, memdb, size):
    c = company("acme", checker="ibm")
    cfg = make_cfg([c])
    jobs = [job(str(i), f"Engineer {i}") for i in range(size)]
    memdb.upsert_jobs("acme", jobs, iso())
    _age_seen(memdb, c, 45)
    assert _observe(cfg, memdb, c, jobs) == ([], [])    # 45 days: not yet
    _age_seen(memdb, c, 46)
    problems, _ = _observe(cfg, memdb, c, jobs)
    assert [(p["kind"], p["alert"]["rule"]) for p in problems] == [("board quiet", "quiet")]


def test_a_frozen_workday_site_goes_quiet_although_its_dates_stop_at_30_days(make_cfg, memdb):
    from internwatch.adapters.base import relative_posted
    c = company("acme", checker="workday", settings={"host": "h", "tenant": "t", "site": "x"})
    cfg = make_cfg([c])
    jobs = [job(str(i), "Engineer", posted=relative_posted("Posted 30+ Days Ago")) for i in range(300)]
    memdb.upsert_jobs("acme", jobs, iso())
    _age_seen(memdb, c, 60)
    assert [p["kind"] for p in _observe(cfg, memdb, c, jobs)[0]] == ["board quiet"]


def test_a_new_job_on_any_board_resets_only_that_board(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings=GH2)
    cfg = make_cfg([c])
    jobs = _jobs(4, 2)
    memdb.upsert_jobs("acme", jobs, iso())
    _age_seen(memdb, c, 60)
    problems, _ = _observe(cfg, memdb, c, jobs)
    assert sorted(p["summary"] for p in problems) == ["no new job on greenhouse board campus in 60 days",
                                                      "no new job on greenhouse board main in 60 days"]
    new = job("m-new", "Engineer", extra={"board": "main"})
    memdb.upsert_jobs("acme", [new], iso())
    problems, recovered = _observe(cfg, memdb, c, jobs + [new])
    assert problems == [] and [r["summary"] for r in recovered] == ["new jobs on greenhouse board main again"]
    assert memdb.one("SELECT stale_since FROM source_health WHERE source='stale board:campus'")["stale_since"]


def test_an_empty_board_goes_quiet_from_the_day_it_was_first_read(make_cfg, memdb):
    c = company("tgs", checker="lever", settings={"site": "tgsmc"})
    cfg = make_cfg([c])
    memdb.update_state("tgs", seeded_at=iso(utcnow() - 46 * DAY))
    problems, _ = _observe(cfg, memdb, c, [])
    assert [p["kind"] for p in problems] == ["board quiet"]


def test_a_feed_answering_unchanged_for_ever_goes_quiet(make_cfg, memdb):
    c = company("google", checker="google")
    cfg = make_cfg([c])
    jobs = [job(str(i), "Engineer") for i in range(30)]
    memdb.upsert_jobs("google", jobs, iso())
    _age_seen(memdb, c, 10)
    assert _observe(cfg, memdb, c, jobs) == ([], [])
    memdb.set("board_new:google:*", (utcnow() - 46 * DAY).date().isoformat())
    o = Outcome(company=c, unchanged=True)
    assert [p["kind"] for p in liveness.observe(cfg, memdb, c, o, Verdict(True), set())[0]] == ["board quiet"]


def test_a_slow_bleed_alerts_once_and_a_sudden_drop_leaves_it_to_the_drop_alert(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings={"board": "acme"})
    cfg = make_cfg([c])
    jobs = [job(str(i), f"Engineer {i}", posted=iso()) for i in range(30)]
    seen = [[p["kind"] for p in _poll(cfg, memdb, c, jobs[:n])] for n in (30, 20, 14, 10, 7, 5, 4, 3)]
    assert seen[:3] == [[], [], ["slow bleed"]] and not any(seen[3:])  # 14 is under half of 30
    a = memdb.get("bleed_high:acme")
    assert a == "30"
    d = company("beta", checker="greenhouse", settings={"board": "beta"})
    from internwatch import alerts
    _poll(cfg, memdb, d, jobs)
    alerts.record(memdb, [{"key": "beta", "name": "Beta", "kind": "drop", "summary": "x",
                           "alert": {"id": "drop:beta", "rule": "count", "need": 15}}], [])
    assert _poll(cfg, memdb, d, jobs[:9]) == []


@pytest.mark.parametrize("checker", ["amazon", "apple", "janestreet_programs", "program_pages"])
def test_lists_of_student_roles_are_left_out_of_the_slow_bleed(make_cfg, memdb, checker):
    c = company("acme", checker=checker)
    cfg = make_cfg([c])
    jobs = [job(str(i), f"Software Engineer Intern {i}", posted=iso()) for i in range(30)]
    assert not [p for n in (30, 3) for p in _poll(cfg, memdb, c, jobs[:n]) if p["kind"] == "slow bleed"]


def test_internships_vanishing_at_once_alert_after_two_polls_and_each_company_on_its_own(make_cfg, memdb):
    from internwatch import alerts
    c = company("acme", checker="greenhouse", settings={"board": "acme"})
    cfg = make_cfg([c])
    staff = [job(f"s{i}", f"Senior Engineer {i}", posted=iso()) for i in range(40)]
    interns = [job(f"i{i}", f"Software Engineer Intern {i}", posted=iso()) for i in range(10)]
    seen = [[p["kind"] for p in _poll(cfg, memdb, c, staff + interns[:n], students=n)] for n in (10, 10, 0, 0)]
    assert seen == [[], [], [], ["internships vanished"]]
    p = _poll(cfg, memdb, c, staff, students=0)
    alerts.record(memdb, [{"key": "acme", "name": "Acme", "kind": "internships vanished", "summary": "x",
                           "alert": {"id": "live_alert:acme:students", "rule": "students", "need": 5}}], [])
    alerts.sweep(cfg, memdb)
    assert [a["kind"] for a in alerts.for_email(memdb)[0]] == ["internships vanished"]
    _poll(cfg, memdb, c, staff + interns[:5], students=5)    # back at half
    alerts.sweep(cfg, memdb)
    assert alerts.for_email(memdb)[0] == []


def test_internships_closing_one_by_one_do_not_alert():
    assert liveness.vanished([1, 2, 3, 5]) is None
    assert liveness.vanished([0, 1, 2, 3]) is None      # under 5 roles: nothing to judge
    assert liveness.vanished([0, 2, 20, 20]) == 20
    assert liveness.vanished([0, 3, 20, 20]) is None    # 85% gone: not "nearly all"
    assert liveness.vanished([0, 0, 0, 20]) == 20
    assert liveness.vanished([0, 0]) is None


def test_a_page_that_flips_back_and_forth_alerts_once(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings={"board": "acme"})
    cfg = make_cfg([c])
    both = '<a href="https://boards.greenhouse.io/acme">a</a><a href="https://jobs.ashbyhq.com/acme-inc">b</a>'
    only = '<a href="https://boards.greenhouse.io/acme">a</a>'
    none = "<html></html>"
    assert _look(cfg, memdb, c, only) == []
    assert [p["summary"] for p in _look(cfg, memdb, c, both)] == ["the careers page now points at ashby:board=acme-inc"]
    assert _look(cfg, memdb, c, only) == []
    assert _look(cfg, memdb, c, both) == []                       # the same link back: said once
    assert [_look(cfg, memdb, c, none), _look(cfg, memdb, c, only), _look(cfg, memdb, c, none)] == [[], [], []]  # never twice in a row
    assert len(_look(cfg, memdb, c, none)) == 1                   # twice in a row: said
    assert [_look(cfg, memdb, c, only), _look(cfg, memdb, c, none), _look(cfg, memdb, c, none)] == [[], [], []]  # and said once


def test_the_careers_pages_are_read_daily_and_one_that_refuses_waits_a_week(make_cfg, memdb):
    from datetime import timedelta
    c = company("acme", checker="greenhouse", settings={"board": "acme"})
    cfg = make_cfg([c])
    url = c.careers_url[0]
    page = '<a href="https://boards.greenhouse.io/acme">a</a>'

    def read(answer, days_ago=0):
        http = PageHttp({url: answer})
        liveness.scan_pages(cfg, memdb, http, float("inf"))
        return http.calls == [url]

    def age(days):
        memdb.set("page_scan_at:acme", iso(utcnow() - timedelta(days=days, hours=2)))

    assert read(page)
    assert not read(page)              # the same morning: read already
    age(1)
    assert read(page)                  # the next morning, even a little earlier in the day
    age(1)
    assert read(FetchError("HTTP 403 for GET x"))
    assert read(FetchError("HTTP 403 for GET x"))   # asked once more
    age(3)
    assert not read(page)              # refused twice: it waits
    age(7)
    assert read(page)                  # answers again …
    age(1)
    assert read(page)                  # … and is daily again


# `burst: N`, a company setting (Western Digital: its search lists only its newest 100 postings, so 100 or more new
# ones between two reads means older ones among them may have gone unread)

WD_BURST = {"company": "WD", "burst": 100}


def _burst(cfg, db, c, new: int, known=("old",), **kw):
    jobs = [job("old", "Engineer")] + [job(f"n{i}", f"Engineer {i}") for i in range(new)]
    return liveness.observe(cfg, db, c, Outcome(company=c, jobs=jobs, **kw), Verdict(True), set(known))


def test_a_burst_of_new_postings_alerts_once_a_day_and_only_dismissing_ends_it(make_cfg, memdb, monkeypatch):
    c = company("wd", checker="smartrecruiters", settings=WD_BURST)
    cfg = make_cfg([c])
    monkeypatch.setattr(liveness, "utcnow", lambda: parse_iso("2026-11-21T14:00:00Z"))
    assert _burst(cfg, memdb, c, 99) == ([], [])
    problems, recovered = _burst(cfg, memdb, c, 100)
    assert [(p["kind"], p["summary"]) for p in problems] == [("burst", "100 postings are new since the last read")]
    assert problems[0]["alert"] == {"id": "live_alert:wd:burst:2026-11-21", "rule": "manual"} and recovered == []
    assert "when 100 or more are posted between two reads" in problems[0]["detail"]
    # the same morning again (the run's second look, by which the postings are stored anyway): told already
    assert _burst(cfg, memdb, c, 150) == ([], [])
    alerts.record(memdb, problems, [])
    for _ in range(3):
        alerts.sweep(cfg, memdb)
    assert [a["kind"] for a in alerts.live(memdb, "wd")] == ["burst"]          # nothing clears it …
    alerts.dismiss(memdb, kind="burst")
    assert [a["state"] for a in alerts.live(memdb, "wd")] == ["dismissed"]
    # … and another morning's burst is an alert of its own, dismissed or not
    monkeypatch.setattr(liveness, "utcnow", lambda: parse_iso("2026-11-25T14:00:00Z"))
    later, _ = _burst(cfg, memdb, c, 120)
    assert [p["alert"]["id"] for p in later] == ["live_alert:wd:burst:2026-11-25"]
    assert [p for p in alerts.record(memdb, later, [])[0]] == later


def test_a_burst_is_judged_on_any_poll_that_brought_jobs_but_not_a_first_read(make_cfg, memdb):
    c = company("wd", checker="smartrecruiters", settings=WD_BURST)
    cfg = make_cfg([c])
    for n, kw in enumerate(({"degraded": "smartrecruiters:WD: keyword sweep incomplete"}, {"partial": True}, {"mode": "quick"})):
        memdb.conn.execute("DELETE FROM kv")
        problems, _ = _burst(cfg, memdb, c, 100, **kw)                          # the other rules skip such a poll
        assert [p["kind"] for p in problems] == ["burst"], kw
    memdb.conn.execute("DELETE FROM kv")
    assert _burst(cfg, memdb, c, 300, known=()) == ([], [])                     # the company's first read: all is new
    failed = Outcome(company=c, error_kind="error", error="HTTP 503")
    assert liveness.observe(cfg, memdb, c, failed, Verdict(False), {"old"}) == ([], [])
    assert memdb.q("SELECT key FROM kv WHERE key LIKE '%burst%'") == []


def test_a_company_without_burst_is_untouched(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings={"board": "acme"})
    cfg = make_cfg([c])
    for kw in ({}, {"degraded": "x"}, {"partial": True}, {"mode": "quick"}):
        assert _burst(cfg, memdb, c, 150, **kw) == ([], [])
    assert memdb.q("SELECT key FROM kv WHERE key LIKE '%burst%'") == []
    # and its other rules read the poll as ever: a board that empties still alerts on its second empty poll
    g = company("gh", checker="greenhouse", settings=GH2)
    cfg = make_cfg([g])
    _observe(cfg, memdb, g, _jobs(10, 3))
    _observe(cfg, memdb, g, _jobs(10, 0))
    assert [p["kind"] for p in _observe(cfg, memdb, g, _jobs(10, 0))[0]] == ["board empty"]


def test_an_error_in_the_burst_rule_costs_no_other_rule_of_the_poll(make_cfg, tmp_path, monkeypatch, caplog):
    def broken(*a, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(liveness, "_burst_rule", broken)
    c = company("acme", checker="greenhouse", settings={**GH2, "burst": 100})
    cfg = make_cfg([c])
    db = DB(tmp_path / "burst.db")
    assert _observe(cfg, db, c, _jobs(10, 3)) == ([], [])
    assert _observe(cfg, db, c, _jobs(10, 0)) == ([], [])
    problems, _ = _observe(cfg, db, c, _jobs(10, 0))                            # the count rules still judge the poll
    assert [p["kind"] for p in problems] == ["board empty"]
    assert db.get("board_new:acme:board:main")                                  # … and so does the quiet-board rule
    assert "the burst rule failed" in caplog.text
    # in a run: the poll's liveness problems and the rule that follows (moves.observe) are still there
    from internwatch import moves
    from internwatch.runner import RunSummary
    seen = []
    monkeypatch.setattr(moves, "observe", lambda cfg_, db_, o: seen.append(o.company.key) or [])
    r, s = Runner(cfg, db=db, checker_fn=FakeChecker({})), RunSummary()
    jobs = _jobs(10, 0)
    r._liveness_observe(Outcome(company=c, jobs=jobs), Verdict(True), {j.id for j in jobs}, s)
    assert seen == ["acme"] and s.processed == {"acme"} and s.healthy == {"acme"}
    db.close()
