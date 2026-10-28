"""Where a company whose careers page can't be read starts posting (moves.py). Only the companies named in
liveness.blocked are ever read; every other company, every poll and every email stays exactly as before."""
import json
from datetime import timedelta

import pytest

from internwatch import liveness, moves
from internwatch.db import iso, utcnow
from internwatch.http import Resp
from internwatch.models import CheckTimeout, FetchError, RobotsBlocked
from internwatch.runner import RunOptions, Runner

from conftest import FakeChecker, company, job


class FakeHttp:
    """Answers by URL (exact, or the longest registered prefix); an Exception value is raised. Records the calls."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.calls: list[str] = []

    def _find(self, url):
        hit = self.pages.get(url)
        if hit is None:
            prefix = max((k for k in self.pages if url.startswith(k)), key=len, default=None)
            hit = self.pages.get(prefix) if prefix else None
        if hit is None:
            raise FetchError(f"HTTP 404 for GET {url}")
        if isinstance(hit, Exception):
            raise hit
        return hit

    def request(self, method, url, params=None, json=None, headers=None, **kw):
        if params:
            url = url + ("&" if "?" in url else "?") + "&".join(f"{k}={v}" for k, v in params.items())
        self.calls.append(f"{method} {url}")
        hit = self._find(url)
        if isinstance(hit, Resp):
            return hit
        body = hit if isinstance(hit, str) else __import__("json").dumps(hit)
        return Resp(200, url, {"content-type": "text/html"}, body.encode())

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def get_text(self, url, **kw):
        return self.get(url, **kw).text

    def get_json(self, url, **kw):
        return self.get(url, **kw).json()

    def post_json(self, url, **kw):
        return self.post(url, **kw).json()

    def close(self):
        pass


def ctx(cfg, db, http=None, healthy=(), gate=None):
    return moves.Ctx(cfg, db, gate, lambda deadline, **kw: http or FakeHttp({}), float("inf"), set(healthy))


@pytest.fixture
def blocked_cfg(make_cfg):
    def _make(companies, **liveness_settings):
        return make_cfg(companies, liveness={"blocked": [c.key for c in companies if not c.key.startswith("other")],
                                             **liveness_settings})
    return _make


# who is read ---------------------------------------------------------------------------------------------

def test_only_the_named_companies_are_ever_read(blocked_cfg, caplog):
    a, other = company("acme"), company("other")
    cfg = blocked_cfg([a, other], wp_pages={"acme": "https://acme.example.com", "other": "https://other.example.com"},
                      parallel_sources=[{"company": "other", "checker": "greenhouse", "settings": {"board": "x"}}])
    assert list(moves.blocked(cfg)) == ["acme"]
    assert moves.per_company(cfg, "wp_pages") == {"acme": "https://acme.example.com"}
    assert moves.entries(cfg, "parallel_sources") == []
    assert "not in liveness.blocked" in caplog.text


def test_the_real_settings_name_the_31_companies():
    from internwatch.config import load
    cfg = load()
    keys = cfg.settings.get("liveness", "blocked")
    assert len(keys) == len(set(keys)) == 31
    assert set(keys) <= {c.key for c in cfg.companies}


def test_nothing_runs_without_blocked_companies(make_cfg, memdb):
    calls = []
    moves.CHECKS.append(("spy", lambda c: calls.append(1) or []))
    try:
        cfg = make_cfg([company("acme")], liveness={"blocked": []})
        assert moves.run(cfg, memdb, None, None, float("inf"), set()) == [] and calls == []
    finally:
        moves.CHECKS.pop()


def test_a_failing_check_never_stops_the_others(blocked_cfg, memdb):
    cfg = blocked_cfg([company("acme")])
    seen = []

    def boom(c):
        raise RuntimeError("bug")
    moves.CHECKS[:0] = [("boom", boom), ("after", lambda c: seen.append(1) or [{"kind": "x"}])]
    try:
        assert moves.run(cfg, memdb, None, None, float("inf"), set()) == [{"kind": "x"}] and seen == [1]
    finally:
        del moves.CHECKS[:2]


# when -------------------------------------------------------------------------------------------------------------

def test_a_weekly_check_spreads_over_the_week_and_retries_a_refused_read_once(memdb):
    now = utcnow()
    keys = [f"c{i:02d}" for i in range(14)]
    first = moves.pick(memdb, "pages", keys, 7, now)
    assert first == ["c00", "c01"]  # 14 companies over 7 days: 2 a day, never-read ones first
    moves.done(memdb, "pages", "c00", "ok", now)
    moves.done(memdb, "pages", "c01", "refused", now)
    tomorrow = now + timedelta(days=1)
    assert moves.pick(memdb, "pages", keys, 7, tomorrow) == ["c01", "c02", "c03"]  # the retry is outside the quota
    moves.done(memdb, "pages", "c01", "refused", tomorrow)  # refused again: wait for its next turn
    assert "c01" not in moves.pick(memdb, "pages", keys, 7, tomorrow + timedelta(days=1))
    assert "c00" in moves.pick(memdb, "pages", ["c00"], 7, now + timedelta(days=7))
    assert json.loads(memdb.get("blocked:rate:pages:c01")) == [[now.date().isoformat(), 0],
                                                               [tomorrow.date().isoformat(), 0]]


def test_what_counts_as_refused():
    assert moves.outcome(FetchError("HTTP 403 for GET x")) == "refused"   # a bot check: retried tomorrow
    assert moves.outcome(FetchError("HTTP 503 for GET x (after 2 attempts)")) == "refused"
    assert moves.outcome(CheckTimeout("timeout")) == "refused"
    assert moves.outcome(FetchError("HTTP 404 for GET x")) == "failed"
    assert moves.outcome(RobotsBlocked("robots.txt disallows x")) == "failed"  # never retried
    assert moves.out_of_budget(CheckTimeout("time budget exhausted before GET x (0 requests made)"))


# stored jobs and job systems -------------------------------------------------------------------------------

def test_ids_match_stored_jobs_whatever_their_prefix(memdb):
    memdb.conn.execute("INSERT INTO jobs(company, job_id, title, url, first_seen, last_seen, alt_ids) VALUES "
                       "('gm', '/job/Warren-MI/CAE-Engineer_JR-202623182', 'CAE', 'https://x/job/1', 't', 't', '[]'),"
                       "('gm', 'workday:/job/Boston/Intern_R39449', 'Intern', '', 't', 't', '[]'),"
                       "('gm', '4730408005', 'Trader', 'https://www.chicagotrading.com/job/?gh_jid=4730408005', 't', 't', '[\"777\"]')")
    toks = moves.stored_tokens(memdb, "gm")
    assert moves.is_stored("jr-202623182", toks) and moves.is_stored("R39449", toks)
    assert moves.is_stored("4730408005", toks)
    assert not moves.is_stored("8212158", toks) and not moves.is_stored("jr-202699999", toks)


def test_portals_sites_and_domains_are_keyed_separately():
    k = moves.system_key_v2
    assert k("icims", {"portal": "https://campus-libertymutual.icims.com"}) != k("icims", {"portal": "https://careers-libertymutual.icims.com"})
    assert k("avature", {"list_url": "https://a.avature.net/x/SearchJobs/"}) == "avature:site=a.avature.net"
    assert k("eightfold", {"host": "searchjobs.libertymutualgroup.com", "domain": "libertymutual.com"}) == "eightfold:domain=libertymutual.com"
    assert k("workday", {"host": "wd1.myworkdaysite.com", "tenant": "fmr", "site": "FidelityCareers"}) == \
        k("workday", {"host": "fmr.wd1.myworkdayjobs.com", "tenant": "fmr", "site": "fidelitycareers"})
    assert k("greenhouse", {"board": "acme"}) == liveness.system_key("greenhouse", {"board": "acme"})
    # the weekly page check of every other company keeps today's keys
    assert liveness.system_key("icims", {"portal": "https://campus-libertymutual.icims.com"}) == "icims:"


def test_links_to_configured_hosts_count_as_that_system_except_the_page_itself():
    c = company("liberty", checker="eightfold", settings={"host": "searchjobs.libertymutualgroup.com",
                                                          "domain": "libertymutual.com", "api": "v2"})
    text = ('<a href="https://searchjobs.libertymutualgroup.com/careers?query=intern">jobs</a>'
            '<a href="https://libertymutual.eightfold.ai/careers?domain=libertymutual.com">jobs</a>'
            '<a href="https://campus-libertymutual.icims.com/jobs/intro">campus</a>'
            '<a href="https://app.joinhandshake.com/employers/liberty-mutual-123">handshake</a>')
    seen = moves.systems_in(text, "https://jobs.libertymutualgroup.com/", c, {})
    assert seen == {"eightfold:domain=libertymutual.com", "icims:portal=campus-libertymutual.icims.com",
                    "handshake:employer=liberty-mutual-123"}
    own = moves.systems_in('<a href="https://searchjobs.libertymutualgroup.com/x">self</a>',
                           "https://searchjobs.libertymutualgroup.com/careers", c, {})
    assert own == set()
    assert moves.systems_in("https://boards.greenhouse.io/old", "", company("x"),
                            {"greenhouse:board=old": "greenhouse:board=new"}) == {"greenhouse:board=new"}


# confirming an unknown job ------------------------------------------------------------------------------

def test_an_unknown_job_is_reported_only_after_a_later_healthy_poll(blocked_cfg, memdb):
    c = company("acme")
    cfg = blocked_cfg([c])
    first = moves.Ctx(cfg, memdb, None, None, float("inf"), set(), started="2026-10-28T09:00:00Z")
    moves.note_unknown(memdb, "joblist", c, {"111": "Software Engineer Intern", "222": "Accountant"}, "its job list",
                       first.started)
    assert moves.confirm(first, "joblist", "acme's job list") == []  # seen this run: wait for tomorrow's poll
    unhealthy = moves.Ctx(cfg, memdb, None, None, float("inf"), set(), started="2026-10-29T09:00:00Z")
    assert moves.confirm(unhealthy, "joblist", "acme's job list") == []  # the poll failed: keep waiting
    memdb.conn.execute("INSERT INTO jobs(company, job_id, title, first_seen, last_seen) VALUES "
                       "('acme', '333', 'x', 't', 't')")
    healthy = moves.Ctx(cfg, memdb, None, None, float("inf"), {"acme"}, started="2026-10-30T09:00:00Z")
    problems = moves.confirm(healthy, "joblist", "acme's job list")
    assert [p["kind"] for p in problems] == ["posting elsewhere?"]
    assert "'Software Engineer Intern' (111)" in problems[0]["summary"] and "222" not in problems[0]["summary"]
    assert moves.confirm(healthy, "joblist", "acme's job list") == []  # reported once
    liveness.restore(memdb, problems[0])  # the email failed: …
    assert len(moves.confirm(healthy, "joblist", "acme's job list")) == 1  # … reported again


def test_a_job_the_poll_catches_up_with_is_never_reported(blocked_cfg, memdb):
    c = company("acme")
    cfg = blocked_cfg([c])
    moves.note_unknown(memdb, "joblist", c, {"111": "Software Engineer Intern"}, "its job list", "2026-10-28T09:00:00Z")
    memdb.conn.execute("INSERT INTO jobs(company, job_id, title, first_seen, last_seen) VALUES "
                       "('acme', '111', 'x', 't', 't')")
    healthy = moves.Ctx(cfg, memdb, None, None, float("inf"), {"acme"}, started="2026-10-29T09:00:00Z")
    assert moves.confirm(healthy, "joblist", "acme's job list") == []
    assert json.loads(memdb.get("blocked:pending:joblist:acme")) == {}


# the run ------------------------------------------------------------------------------------------------------

@pytest.fixture
def online(monkeypatch):
    monkeypatch.setattr(Runner, "online", lambda self: True)


def test_the_checks_run_in_daily_runs_after_the_page_check_with_the_healthy_polls(blocked_cfg, monkeypatch, online):
    from internwatch.db import DB
    order = []
    monkeypatch.setattr(liveness, "scan_pages", lambda *a, **kw: order.append("scan_pages") or [])
    monkeypatch.setattr(moves, "run", lambda cfg, db, gate, make_http, budget_end, healthy:
                        order.append(("moves", sorted(healthy))) or [])
    cfg = blocked_cfg([company("acme"), company("beta")])
    db = DB(cfg.settings.path("db"))
    r = Runner(cfg, db=db, checker_fn=FakeChecker({"acme": [[job("1", "SWE")]], "beta": [FetchError("HTTP 503")]}))
    r.run(RunOptions(crosscheck=False, send=False, scheduled_mail=False, daily=True, retry_delay=0))
    assert order == ["scan_pages", ("moves", ["acme"])]
    order.clear()
    r.run(RunOptions(crosscheck=False, send=False, scheduled_mail=False, force=True))  # continuous mode: never
    assert order == []


def test_a_bug_in_these_checks_never_costs_the_run(blocked_cfg, monkeypatch, online):
    from internwatch.db import DB

    def boom(*a, **kw):
        raise RuntimeError("moves bug")
    monkeypatch.setattr(moves, "run", boom)
    monkeypatch.setattr(moves, "observe", boom)
    cfg = blocked_cfg([company("acme")])
    db = DB(cfg.settings.path("db"))
    r = Runner(cfg, db=db, checker_fn=FakeChecker({"acme": [[job("1", "Software Engineer Intern (Summer 2027)")]]}))
    s = r.run(RunOptions(crosscheck=False, send=False, scheduled_mail=False, daily=True, retry_delay=0))
    assert s.seeded == ["acme"] and not s.failed
    assert [e["kind"] for e in db.q("SELECT kind FROM emails")] == ["seed"]


# W: hidden Workday sites -------------------------------------------------------------------------------------

AMFAM = {"host": "amfam.wd1.myworkdayjobs.com", "tenant": "amfam", "sites": ["AmFamGroupInternCareers", "Careers"]}
AMFAM_ROBOTS = ("User-agent: *\nAllow: /Careers/\nAllow: /Agent-Staff/\nDisallow: /AmFamGroupInternCareers/\n"
                "Disallow: /AmFam-Private/\nDisallow: /refreshFacet/\n")


def test_a_new_hidden_workday_site(blocked_cfg, memdb, tmp_path):
    from internwatch.http import HostGate
    c = company("american-family", checker="workday", settings=AMFAM)
    cfg = blocked_cfg([c])
    gate = HostGate(tmp_path / "robots")
    origin = "https://amfam.wd1.myworkdayjobs.com"
    gate._disk_put(origin, 200, AMFAM_ROBOTS)
    assert moves.check_workday(ctx(cfg, memdb, gate=gate)) == []  # first look: AmFam-Private is old news
    assert json.loads(memdb.get("blocked:workday_hidden:amfam.wd1.myworkdayjobs.com")) == [
        "AmFam-Private", "AmFamGroupInternCareers"]  # every hidden site; the configured one never alerts
    memdb.set("blocked:at:workday:amfam.wd1.myworkdayjobs.com", "")  # due again
    gate._disk_put(origin, 200, AMFAM_ROBOTS + "Disallow: /Agent-Staff-Private/\nAllow: /Students/\n")
    problems = moves.check_workday(ctx(cfg, memdb, gate=gate))
    # the hidden site alerts; a new Allow site is left to the weekly Workday check, which already reports it
    assert [p["summary"] for p in problems] == [
        "Workday tenant amfam.wd1.myworkdayjobs.com lists new hidden sites: Agent-Staff-Private"]
    liveness.restore(memdb, problems[0])  # the health email failed: due and raised again next run
    assert len(moves.check_workday(ctx(cfg, memdb, gate=gate))) == 1


def test_a_myworkdaysite_config_is_read_on_its_tenant_host(blocked_cfg, memdb):
    c = company("fidelity", checker="multi", settings={"sources": [
        {"checker": "workday", "settings": {"host": "wd1.myworkdaysite.com", "tenant": "fmr", "site": "FidelityCareers"}},
        {"checker": "workday", "settings": {"host": "wd1.myworkdaysite.com", "tenant": "fmr", "site": "targeted"}}]})
    pb = company("pitchbook", checker="greenhouse", settings={"board": "pitchbookdata"})
    cfg = blocked_cfg([c, pb], extra_tenants={"pitchbook": ["morningstar.wd5.myworkdayjobs.com"]})
    http = FakeHttp({"https://fmr.wd1.myworkdayjobs.com/robots.txt": "Allow: /FidelityCareers/\nDisallow: /targeted/\n",
                     "https://morningstar.wd5.myworkdayjobs.com/robots.txt": "Allow: /Americas/\nAllow: /EMEA/\n"})
    for _ in range(2):  # weekly, spread: one of the two tenants a day
        assert moves.check_workday(ctx(cfg, memdb, http)) == []  # first looks
    for h in ("fmr.wd1.myworkdayjobs.com", "morningstar.wd5.myworkdayjobs.com"):
        memdb.set(f"blocked:at:workday:{h}", "")
    http.pages["https://fmr.wd1.myworkdayjobs.com/robots.txt"] += "Disallow: /targeted2/\n"
    http.pages["https://morningstar.wd5.myworkdayjobs.com/robots.txt"] += "Allow: /PitchBook/\n"
    problems = moves.check_workday(ctx(cfg, memdb, http)) + moves.check_workday(ctx(cfg, memdb, http))
    assert sorted((p["key"], p["summary"]) for p in problems) == [
        ("fidelity", "Workday tenant fmr.wd1.myworkdayjobs.com lists new sites: targeted2"),
        ("pitchbook", "Workday tenant morningstar.wd5.myworkdayjobs.com lists new sites: PitchBook")]


def test_workday_tenants_of_other_companies_are_never_read(blocked_cfg, memdb):
    other = company("other-co", checker="workday", settings={"host": "other.wd5.myworkdayjobs.com", "tenant": "other",
                                                          "site": "External"})
    cfg = blocked_cfg([company("acme"), other])
    http = FakeHttp({})
    assert moves.check_workday(ctx(cfg, memdb, http)) == [] and http.calls == []


def test_a_refused_robots_txt_is_read_again_the_next_morning(blocked_cfg, memdb):
    c = company("american-family", checker="workday", settings=AMFAM)
    cfg = blocked_cfg([c])
    http = FakeHttp({"https://amfam.wd1.myworkdayjobs.com/robots.txt": FetchError("HTTP 503 for GET robots.txt")})
    moves.check_workday(ctx(cfg, memdb, http))
    assert memdb.get("blocked:retry:workday:amfam.wd1.myworkdayjobs.com") == "1"
    http.pages["https://amfam.wd1.myworkdayjobs.com/robots.txt"] = AMFAM_ROBOTS
    moves.check_workday(ctx(cfg, memdb, http))
    assert memdb.get("blocked:workday_hidden:amfam.wd1.myworkdayjobs.com")  # read on the retry
