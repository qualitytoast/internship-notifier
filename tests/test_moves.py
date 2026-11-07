"""Where a company whose careers page can't be read starts posting (moves.py). Only the companies named in
liveness.blocked are ever read; every other company, every poll and every email stays exactly as before."""
import json
from datetime import timedelta

import pytest

from internwatch import alerts, liveness, moves
from internwatch.db import iso, utcnow
from internwatch.http import Resp
from internwatch.models import CheckTimeout, FetchError, Job, RobotsBlocked
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

    def _fetch_robots(self, url):
        return 404, ""


def ctx(cfg, db, http=None, healthy=(), gate=None, days=0):
    return moves.Ctx(cfg, db, gate, lambda deadline, **kw: http or FakeHttp({}), float("inf"), set(healthy),
                     now=utcnow() + timedelta(days=days))


@pytest.fixture
def blocked_cfg(make_cfg):
    def _make(companies, **liveness_settings):
        empty = {k: {} for k in ("extra_tenants", "wp_pages", "id_pages", "job_lists", "program_pages",
                                  "archive_paths", "aliases")}
        empty.update(parallel_sources=[], listings=[], getro=[])
        return make_cfg(companies, liveness={"blocked": [c.key for c in companies if not c.key.startswith("other")],
                                             **empty, **liveness_settings})
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


def test_the_real_settings_name_the_32_companies():
    from internwatch.config import load
    cfg = load()
    keys = cfg.settings.get("liveness", "blocked")
    assert len(keys) == len(set(keys)) == 32
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
    for status in (400, 401, 403, 406, 429):
        assert moves.outcome(FetchError(f"HTTP {status} for GET x")) == "refused"   # the site says no
    assert moves.outcome(FetchError("HTTP 503 for GET x (after 2 attempts)")) == "failed"
    assert moves.outcome(CheckTimeout("timeout")) == "failed"
    assert moves.outcome(FetchError("HTTP 404 for GET x")) == "failed"
    assert moves.outcome(RobotsBlocked("robots.txt disallows x")) == "robots"
    assert moves.out_of_budget(CheckTimeout("time budget exhausted before GET x (0 requests made)"))


def test_a_page_whose_read_failed_is_read_again_every_morning_and_never_waits(memdb):
    now = utcnow()
    for day in range(5):
        when = now + timedelta(days=day)
        assert moves.pick(memdb, "page", ["acme"], 1, when) == ["acme"]
        moves.done(memdb, "page", "acme", "failed", when)
    assert not moves.refused_last(memdb, "page", "acme")
    assert memdb.get("blocked:at:page:acme") is None


def test_a_failed_read_goes_ahead_of_a_weekly_checks_quota(memdb):
    now = utcnow()
    keys = [f"c{i:02d}" for i in range(14)]
    moves.done(memdb, "pages", "c07", "failed", now)
    assert moves.pick(memdb, "pages", keys, 7, now + timedelta(days=1))[0] == "c07"


def test_only_a_page_that_refuses_or_forbids_the_read_waits_a_week(memdb):
    now = utcnow()
    moves.done(memdb, "page", "shy", "refused", now)
    moves.done(memdb, "page", "shy", "refused", now + timedelta(days=1))
    moves.done(memdb, "page", "forbids", "robots", now)
    later = now + timedelta(days=6)
    assert moves.pick(memdb, "page", ["shy", "forbids"], 1, later) == []
    later = now + timedelta(days=8)
    assert moves.pick(memdb, "page", ["shy", "forbids"], 1, later) == ["forbids", "shy"]


@pytest.mark.parametrize("check", ["listings", "getro", "parallel"])
@pytest.mark.parametrize("result", ["failed", "refused", "robots"])
def test_lists_getro_and_side_boards_are_read_every_morning_whatever_happened(memdb, check, result):
    now = utcnow()
    for day in range(6):
        when = now + timedelta(days=day)
        assert moves.pick(memdb, check, ["x"], 1, when) == ["x"]
        moves.done(memdb, check, "x", result, when)


def test_a_page_already_waiting_keeps_waiting_after_the_upgrade(memdb):
    now = utcnow()
    memdb.set("blocked:at:page:acme", iso(now - timedelta(days=1)))  # as revision 6 left it
    memdb.set("blocked:rate:page:acme", json.dumps([[(now - timedelta(days=2)).date().isoformat(), 0],
                                                    [(now - timedelta(days=1)).date().isoformat(), 0]]))
    assert moves.refused_last(memdb, "page", "acme")
    assert moves.pick(memdb, "page", ["acme"], 1, now) == []
    assert moves.pick(memdb, "page", ["acme"], 1, now + timedelta(days=6)) == ["acme"]


def test_a_read_that_fails_after_its_wait_goes_back_to_every_morning(memdb):
    now = utcnow()
    moves.done(memdb, "page", "acme", "robots", now)
    later = now + timedelta(days=7)
    moves.done(memdb, "page", "acme", "failed", later)
    assert moves.pick(memdb, "page", ["acme"], 1, later + timedelta(days=1)) == ["acme"]


def test_archive_org_keeps_its_own_pace():
    assert moves.archive_outcome(FetchError("HTTP 503 for GET x")) == "refused"       # one retry
    assert moves.archive_outcome(CheckTimeout("timeout")) == "refused"
    assert moves.archive_outcome(FetchError("HTTP 403 for GET x")) == "refused"
    assert moves.archive_outcome(FetchError("HTTP 404 for GET x")) == "robots"        # no retry
    assert moves.archive_outcome(FetchError("HTTP 401 for GET x")) == "robots"
    assert moves.archive_outcome(RobotsBlocked("robots.txt disallows x")) == "robots"


def test_several_sources_that_all_failed_count_as_the_strictest():
    assert moves.worst(["failed", "refused"]) == "refused"
    assert moves.worst(["failed", "robots"]) == "robots"
    assert moves.worst(["robots", "refused"]) == "refused"
    assert moves.worst(["failed", "failed"]) == "failed"


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
    # the weekly page check of every other company keys portals the same way (Avature by portal, not host), and every
    # other system as it always did; page_systems:* keeps one key per system
    page = liveness.page_key
    lm = {"portal": "https://campus-libertymutual.icims.com"}
    assert page("icims", lm) == k("icims", lm) and liveness.system_key("icims", lm) == "icims:"
    assert page("eightfold", {"host": "searchjobs.libertymutualgroup.com", "domain": "libertymutual.com"}) == \
        "eightfold:domain=libertymutual.com"
    assert page("avature", {"list_url": "https://a.avature.net/x/SearchJobs/"}) == "avature:site=a.avature.net/x"
    fid = {"host": "wd1.myworkdaysite.com", "tenant": "fmr", "site": "FidelityCareers"}
    assert page("workday", fid) == liveness.system_key("workday", fid) != k("workday", fid)


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


# P: careers pages, WordPress pages, job ids on pages -------------------------------------------------------

LM = {"host": "searchjobs.libertymutualgroup.com", "domain": "libertymutual.com", "api": "v2"}
WP = "https://jobs.libertymutualgroup.com/wp-json/wp/v2/pages?per_page=100&page={}&_fields=link,content"


def wp_answer(links: list[str], total_pages=1) -> Resp:
    """A WordPress REST answer as the site sends it: JSON with escaped slashes."""
    items = [{"link": "https://jobs.libertymutualgroup.com/x/", "content": {"rendered": f'<a href="{u}">Apply</a>'}}
             for u in links]
    body = json.dumps(items).replace("/", "\\/")
    return Resp(200, "", {"content-type": "application/json", "x-wp-totalpages": str(total_pages)}, body.encode())


def liberty(blocked_cfg):
    c = company("liberty-mutual", checker="eightfold", settings=LM)
    c.careers_url = ["https://jobs.libertymutualgroup.com/"]
    return c, blocked_cfg([c], wp_pages={"liberty-mutual": "https://jobs.libertymutualgroup.com"})


def test_wordpress_pages_that_start_linking_a_new_portal(blocked_cfg, memdb):
    c, cfg = liberty(blocked_cfg)
    campus = "https://campus-libertymutual.icims.com/jobs/intro"
    http = FakeHttp({c.careers_url[0]: FetchError("HTTP 403 for GET page"),
                     WP.format(1): wp_answer([campus, "https://libertymutual.eightfold.ai/careers?domain=libertymutual.com"], 2),
                     WP.format(2): wp_answer(["https://searchjobs.libertymutualgroup.com/careers"])})
    assert moves.check_pages(ctx(cfg, memdb, http)) == []  # first look; the refused page is skipped
    state = json.loads(memdb.get("blocked:page:liberty-mutual"))
    assert state["https://jobs.libertymutualgroup.com"]["systems"] == [
        "eightfold:domain=libertymutual.com", "icims:portal=campus-libertymutual.icims.com"]
    memdb.set("blocked:at:page:liberty-mutual", "")
    assert moves.check_pages(ctx(cfg, memdb, http)) == []  # the same portals: nothing new
    memdb.set("blocked:at:page:liberty-mutual", "")
    http.pages[WP.format(2)] = wp_answer(["https://students-libertymutual.icims.com/jobs/1/intern/job"])
    problems = moves.check_pages(ctx(cfg, memdb, http))
    assert [(p["kind"], p["summary"]) for p in problems] == [
        ("moved?", "its careers pages now point at icims:portal=students-libertymutual.icims.com")]


def test_a_source_not_read_today_never_reports_its_systems_as_gone(blocked_cfg, memdb):
    c, cfg = liberty(blocked_cfg)
    http = FakeHttp({c.careers_url[0]: '<a href="https://searchjobs.libertymutualgroup.com/careers">jobs</a>'
                                       '<a href="https://careers-libertymutual.icims.com/jobs">x</a>',
                     WP.format(1): wp_answer([])})
    moves.check_pages(ctx(cfg, memdb, http))
    memdb.set("blocked:at:page:liberty-mutual", "")
    http.pages[c.careers_url[0]] = FetchError("HTTP 403 for GET page")  # a bot check today
    assert moves.check_pages(ctx(cfg, memdb, http)) == []
    memdb.set("blocked:at:page:liberty-mutual", "")
    http.pages[c.careers_url[0]] = '<a href="https://careers-libertymutual.icims.com/jobs">x</a>'
    assert moves.check_pages(ctx(cfg, memdb, http)) == []  # read again, and the configured host is gone: once
    memdb.set("blocked:at:page:liberty-mutual", "")
    problems = moves.check_pages(ctx(cfg, memdb, http))    # and a second read in a row
    assert [p["summary"] for p in problems] == ["its careers pages no longer mention eightfold:domain=libertymutual.com"]


TOWER_PAGE = ('<a href="https://tower-research.com/open-positions/?gh_jid=8044334"><h3>Quantitative Developer Intern'
              ' - Summer 2027</h3></a><a href="https://www.tower-research.com/open-positions/?gh_jid=8212158">'
              '<h3>Software Engineer Intern (Summer 2027)</h3> New York</a>')


def tower(blocked_cfg, memdb):
    c = company("tower-research", checker="greenhouse", settings={"board": "towerresearchcapital"})
    c.careers_url = ["https://tower-research.com/open-positions/"]
    cfg = blocked_cfg([c], id_pages={"tower-research": ["https://tower-research.com/internships/"]})
    memdb.conn.execute("INSERT INTO jobs(company, job_id, title, url, first_seen, last_seen) VALUES "
                       "('tower-research', '8044334', 'Quantitative Developer Intern', '', 't', 't')")
    return c, cfg


def test_a_hand_made_link_to_a_closed_posting_stays_quiet(blocked_cfg, memdb):
    c, cfg = tower(blocked_cfg, memdb)
    http = FakeHttp({c.careers_url[0]: '<script src="https://boards.greenhouse.io/embed/job_board/js?for=towerresearchcapital"></script>',
                     "https://tower-research.com/internships/": TOWER_PAGE})
    first = moves.Ctx(cfg, memdb, None, lambda d, **kw: http, float("inf"), set(), started="2026-10-28T09:00:00Z")
    assert moves.check_pages(first) == []  # 8212158 (closed, never stored) is part of the first look
    later = moves.Ctx(cfg, memdb, None, lambda d, **kw: http, float("inf"), {"tower-research"},
                      started="2026-10-29T09:00:00Z")
    assert moves.check_confirm(later) == []
    assert json.loads(memdb.get("blocked:page:tower-research"))["https://tower-research.com/internships/"]["ids"] == [
        "8044334", "8212158"]


def test_a_new_posting_linked_from_a_page_is_reported_after_a_healthy_poll_still_lacks_it(blocked_cfg, memdb):
    c, cfg = tower(blocked_cfg, memdb)
    http = FakeHttp({c.careers_url[0]: "<html></html>", "https://tower-research.com/internships/": TOWER_PAGE})
    moves.check_pages(moves.Ctx(cfg, memdb, None, lambda d, **kw: http, float("inf"), set(), started="2026-10-28T09:00:00Z"))
    memdb.set("blocked:at:page:tower-research", "")
    http.pages["https://tower-research.com/internships/"] = TOWER_PAGE + (
        '<a href="https://tower-research.com/open-positions/?gh_jid=9100001"><h3>Quantitative Trader Intern (Summer 2027)'
        '</h3></a>')
    day2 = moves.Ctx(cfg, memdb, None, lambda d, **kw: http, float("inf"), {"tower-research"}, started="2026-10-29T09:00:00Z")
    assert moves.check_pages(day2) == [] and moves.check_confirm(day2) == []  # noted today: wait for tomorrow's poll
    day3 = moves.Ctx(cfg, memdb, None, lambda d, **kw: http, float("inf"), {"tower-research"}, started="2026-10-30T09:00:00Z")
    problems = moves.check_confirm(day3)
    assert [p["kind"] for p in problems] == ["posting elsewhere?"]
    assert "'Quantitative Trader Intern (Summer 2027)' (9100001)" in problems[0]["summary"]


def test_a_refused_page_is_retried_the_next_morning_and_a_robots_block_is_not(blocked_cfg, memdb):
    a, g = company("acme"), company("goldman")
    cfg = blocked_cfg([a, g])
    http = FakeHttp({a.careers_url[0]: FetchError("HTTP 403 for GET page"),
                     g.careers_url[0]: RobotsBlocked("robots.txt disallows the page")})
    moves.check_pages(ctx(cfg, memdb, http))  # one of the two a day: acme, refused
    assert memdb.get("blocked:retry:page:acme") == "1" and not memdb.get("blocked:at:page:acme")
    moves.check_pages(ctx(cfg, memdb, http))  # acme's retry (outside the quota) and goldman's turn
    assert not memdb.get("blocked:retry:page:acme") and memdb.get("blocked:at:page:acme")  # refused twice: next week
    assert not memdb.get("blocked:retry:page:goldman") and memdb.get("blocked:at:page:goldman")  # robots: never retried


def test_the_daily_page_check_leaves_the_31_out_and_reads_every_other_page(blocked_cfg, memdb):
    from test_liveness import PageHttp
    acme, other = company("acme", checker="greenhouse", settings={"board": "acme"}), company("other-co")
    cfg = blocked_cfg([acme, other])
    pages = PageHttp({other.careers_url[0]: '<a href="https://jobs.lever.co/other">x</a>'})
    assert liveness.scan_pages(cfg, memdb, pages, float("inf")) == []
    assert memdb.get("page_systems:other-co") == '["lever:site=other"]'
    state = json.loads(memdb.get("page_systems_v2:other-co"))
    assert (state["systems"], state["portals"]) == (["lever:site=other"], [])
    assert memdb.get("page_scan_at:acme") is None and memdb.get("page_systems:acme") is None
    assert memdb.get("page_systems_v2:acme") is None and memdb.get("page_scan_retry:acme") is None


def test_icims_own_hosts_are_not_portals():
    text = '<img src="https://cdn07.icims.com/x.png"><a href="https://careers-gtsx.icims.com/jobs/search">jobs</a>'
    assert moves.systems_in(text, "https://gtsx.com/careers/", company("gts"), {}) == {"icims:portal=careers-gtsx.icims.com"}


def test_the_real_aliases_point_at_configured_or_watched_systems():
    from internwatch.config import load
    cfg = load()
    c = moves.Ctx(cfg, None, None, None, float("inf"), set())
    known = set().union(*(moves.known_systems(c, x) for x in cfg.active))
    assert set(moves.aliases(cfg).values()) <= known


# A: archive.org's copies ----------------------------------------------------------------------------------------

class FakeGate:
    def __init__(self, robots: dict):
        self.robots_txt = robots

    def robots(self, origin, fetch, ttl):
        from internwatch.robots import from_response
        return from_response(200, self.robots_txt.get(origin, ""))

    def _disk_get(self, origin):
        return None


CDX = "https://web.archive.org/cdx/search/cdx?url="


def archive_setup(blocked_cfg, memdb, listing: str, copy_ts: str, copy: str):
    c = company("coinbase", checker="greenhouse", settings={"board": "coinbase"})
    cfg = blocked_cfg([c], archive_paths={"coinbase": {"list": ["coinbase.com/careers*"], "ids": r"/positions/(\d{6,})",
                                                       "pages": ["https://www.coinbase.com/careers/positions"]}})
    memdb.conn.execute("INSERT INTO jobs(company, job_id, title, url, first_seen, last_seen) VALUES "
                       "('coinbase', '8175873', 'Software Engineer Intern', "
                       "'https://www.coinbase.com/careers/positions/8175873?gh_jid=8175873', 't', 't')")
    page = "https://www.coinbase.com/careers/positions"
    http = FakeHttp({CDX + "coinbase.com/careers*": listing,
                     CDX + page: f"{page} {copy_ts}\n",
                     f"https://web.archive.org/web/{copy_ts}id_/{page}": copy})
    return c, cfg, http


def recent(days=1):
    return (utcnow() - timedelta(days=days)).strftime("%Y%m%d%H%M%S")


def test_archived_pages_new_student_pages_and_systems(blocked_cfg, memdb):
    ts = recent()
    listing = (f"https://www.coinbase.com/careers {ts}\nhttps://www.coinbase.com/careers/positions/8175873?gh_jid=8175873 {ts}\n")
    gh = '<a href="https://boards.greenhouse.io/embed/job_app?for=coinbase&token=1">x</a>'
    c, cfg, http = archive_setup(blocked_cfg, memdb, listing, ts, gh)
    gate = FakeGate({})
    assert moves.check_archive(ctx(cfg, memdb, http, gate=gate)) == []  # first look
    memdb.set("blocked:at:archive:coinbase", "")
    ts2 = recent(0)
    http.pages[CDX + "coinbase.com/careers*"] = (listing + f"https://www.coinbase.com/careers/university {ts2}\n"
                                                 f"https://www.coinbase.com/careers/about-us {ts2}\n")
    http.pages[CDX + "https://www.coinbase.com/careers/positions"] = f"https://www.coinbase.com/careers/positions {ts2}\n"
    http.pages[f"https://web.archive.org/web/{ts2}id_/https://www.coinbase.com/careers/positions"] = (
        gh + '<a href="https://coinbase-students.icims.com/jobs">x</a>')
    problems = moves.check_archive(ctx(cfg, memdb, http, gate=gate))
    assert sorted((p["kind"], p["summary"].split(" (saved")[0]) for p in problems) == [
        ("moved?", "an archived copy of https://www.coinbase.com/careers/positions"),
        ("new page", "archive.org saved new student or program pages: coinbase.com/careers/university")]
    assert "icims:portal=coinbase-students.icims.com" in [p for p in problems if p["kind"] == "moved?"][0]["summary"]


def test_archived_job_ids_newer_than_the_first_look_and_unstored_wait_for_a_poll(blocked_cfg, memdb):
    ts = recent()
    listing = f"https://www.coinbase.com/careers/positions/8000001 {ts}\n"  # an old posting, closed long ago
    c, cfg, http = archive_setup(blocked_cfg, memdb, listing, ts, "<html></html>")
    moves.check_archive(ctx(cfg, memdb, http))
    memdb.set("blocked:at:archive:coinbase", "")
    http.pages[CDX + "coinbase.com/careers*"] = (f"https://www.coinbase.com/careers/positions/9000001 {ts}\n"
                                                 f"https://www.coinbase.com/careers/positions/8000002 {ts}\n")
    later = moves.Ctx(cfg, memdb, None, lambda d, **kw: http, float("inf"), {"coinbase"}, started="2026-10-29T09:00:00Z")
    assert moves.check_archive(later) == []
    assert list(json.loads(memdb.get("blocked:pending:archive:coinbase"))) == ["9000001"]  # 8000002 is below the floor
    after = moves.Ctx(cfg, memdb, None, None, float("inf"), {"coinbase"}, started="2026-10-30T09:00:00Z")
    assert "(9000001)" in moves.check_confirm(after)[0]["summary"]


def test_a_copy_is_read_only_where_the_original_site_allows_it_and_only_when_recent(blocked_cfg, memdb):
    ts = recent()
    c, cfg, http = archive_setup(blocked_cfg, memdb, "", ts, "<html></html>")
    blocked_gate = FakeGate({"https://www.coinbase.com": "User-agent: *\nDisallow: /careers/\n"})
    moves.check_archive(ctx(cfg, memdb, http, gate=blocked_gate))
    assert not any("/web/" in x for x in http.calls)  # robots.txt of coinbase.com disallows the page itself
    memdb.set("blocked:at:archive:coinbase", "")
    memdb.set("blocked:archive:coinbase", "")
    old = recent(60)
    http.pages[CDX + "https://www.coinbase.com/careers/positions"] = f"https://www.coinbase.com/careers/positions {old}\n"
    http.calls.clear()
    moves.check_archive(ctx(cfg, memdb, http, gate=FakeGate({})))
    assert not any("/web/" in x for x in http.calls)  # 60 days old: says nothing about today


def test_archive_org_down_is_retried_the_next_morning_without_an_alert(blocked_cfg, memdb):
    c, cfg, http = archive_setup(blocked_cfg, memdb, "", recent(), "")
    http.pages[CDX + "coinbase.com/careers*"] = FetchError("HTTP 503 for GET cdx (after 1 attempts)")
    assert moves.check_archive(ctx(cfg, memdb, http)) == []
    assert memdb.get("blocked:retry:archive:coinbase") == "1" and memdb.get("blocked:archive:coinbase") is None


def test_a_bot_check_copy_is_skipped(blocked_cfg, memdb):
    ts = recent()
    c, cfg, http = archive_setup(blocked_cfg, memdb, "", ts, "<title>Just a moment...</title>")
    moves.check_archive(ctx(cfg, memdb, http, gate=FakeGate({})))
    assert json.loads(memdb.get("blocked:archive:coinbase"))["systems"] == {}


# J: the company's own job list -----------------------------------------------------------------------------

def sitemap(*locs):
    return "<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in locs) + "</urlset>"


def test_job_lists_as_each_site_writes_them():
    assert moves.job_list(sitemap("https://www.dropbox.jobs/en/jobs/6330377/infrastructure-software-engineer/",
                                  "https://www.dropbox.jobs/en/jobs/", "https://www.dropbox.jobs/pl/jobs/6330377/x/")) == {
        "6330377": "infrastructure software engineer"}
    assert moves.job_list(sitemap("https://search-careers.gm.com/en/jobs/jr-202622954/site-strategy-admin-intern/")) == {
        "jr-202622954": "site strategy admin intern"}
    assert moves.job_list(sitemap("https://jobs.uber.com/en/jobs/303612/")) == {"303612": ""}
    assert moves.job_list(sitemap("https://careers.amfam.com/jobs/r38296/insurance-agency-owner-burr-ridge-il/")) == {
        "r38296": "insurance agency owner burr ridge il"}
    pp = moves.job_list(sitemap("https://paypal.eightfold.ai/careers/job/274922526453-senior-legal-counsel-%E2%80%93-"
                                "cybersecurity-london?domain=paypal.com&amp;microsite=paypal.com"))
    assert list(pp) == ["274922526453"] and pp["274922526453"].startswith("senior legal counsel")
    assert moves.job_list(json.dumps([{"id": 4730408005, "title": "Platform Engineer Intern, Summer 2027"}])) == {
        "4730408005": "Platform Engineer Intern, Summer 2027"}


def joblist_setup(blocked_cfg, memdb, key="dropbox", **conf):
    c = company(key, checker="greenhouse", settings={"board": key})
    url = f"https://{key}.example.com/sitemap.xml"
    cfg = blocked_cfg([c], job_lists={key: {"url": url, **conf}})
    memdb.conn.execute("INSERT INTO jobs(company, job_id, title, url, first_seen, last_seen) VALUES "
                       f"('{key}', '6330377', 'Infrastructure Software Engineer', '', 't', 't')")
    return c, cfg, url


def day(cfg, memdb, http, n, healthy=()):
    return moves.Ctx(cfg, memdb, None, lambda d, **kw: http, float("inf"), set(healthy),
                     started=f"2026-11-0{n}T09:00:00Z", now=utcnow() + timedelta(days=7 * n))


def test_a_job_on_the_companys_list_that_a_later_poll_still_lacks(blocked_cfg, memdb):
    c, cfg, url = joblist_setup(blocked_cfg, memdb)
    old = "https://x/en/jobs/6330377/infrastructure-software-engineer/"
    closed = "https://x/en/jobs/5000001/old-intern-never-stored/"
    http = FakeHttp({url: sitemap(old, closed)})
    assert moves.check_job_lists(day(cfg, memdb, http, 1)) == []  # first read: 5000001 is part of the baseline
    http.pages[url] = sitemap(old, closed, "https://x/en/jobs/9100001/software-engineer-intern-summer-2027/",
                              "https://x/en/jobs/9100002/senior-accountant/")
    assert moves.check_job_lists(day(cfg, memdb, http, 2, {"dropbox"})) == []
    assert sorted(json.loads(memdb.get("blocked:pending:joblist:dropbox"))) == ["9100001", "9100002"]
    problems = moves.check_confirm(day(cfg, memdb, http, 3, {"dropbox"}))
    assert [p["summary"] for p in problems] == [
        "1 job(s) on its job list that InternWatch has never seen: 'software engineer intern summer 2027' (9100001)"]


def test_any_job_counts_on_a_list_without_titles(blocked_cfg, memdb):
    c, cfg, url = joblist_setup(blocked_cfg, memdb, key="uber", any_job=True)
    http = FakeHttp({url: sitemap("https://jobs.uber.com/en/jobs/149574/")})
    moves.check_job_lists(day(cfg, memdb, http, 1))
    http.pages[url] = sitemap("https://jobs.uber.com/en/jobs/149574/", "https://jobs.uber.com/en/jobs/303612/")
    moves.check_job_lists(day(cfg, memdb, http, 2, {"uber"}))
    assert "(303612)" in moves.check_confirm(day(cfg, memdb, http, 3, {"uber"}))[0]["summary"]


def test_a_list_with_its_own_ids_is_matched_by_title(blocked_cfg, memdb):
    c, cfg, url = joblist_setup(blocked_cfg, memdb, key="paypal", match="title")
    memdb.conn.execute("INSERT INTO jobs(company, job_id, title, url, first_seen, last_seen) VALUES "
                       "('paypal', 'workday:/job/x_R1', 'Software Engineer Intern', '', 't', 't')")
    ef = "https://paypal.eightfold.ai/careers/job/{}-{}?domain=paypal.com"
    http = FakeHttp({url: sitemap(ef.format(1, "staff-engineer-austin"))})
    moves.check_job_lists(day(cfg, memdb, http, 1))
    http.pages[url] = sitemap(ef.format(1, "staff-engineer-austin"),
                              ef.format(2, "software-engineer-intern-san-jose-california"),  # on Workday: stored
                              ef.format(3, "data-science-intern-new-york"))                  # only on Eightfold
    moves.check_job_lists(day(cfg, memdb, http, 2, {"paypal"}))
    problems = moves.check_confirm(day(cfg, memdb, http, 3, {"paypal"}))
    assert [p["summary"] for p in problems] == [
        "1 job(s) on its job list that InternWatch has never seen: 'data science intern new york'"]


def test_job_lists_are_read_daily_and_one_that_refuses_waits_a_week(blocked_cfg, memdb):
    keys = [company("good"), company("shy")]
    lists = {"good": {"url": "https://good/sitemap.xml"}, "shy": {"url": "https://shy/sitemap.xml"}}
    cfg = blocked_cfg(keys, job_lists=lists)
    http = FakeHttp({"https://good/sitemap.xml": sitemap(), "https://shy/sitemap.xml": FetchError("HTTP 403 for GET x")})

    def read(days):
        http.calls.clear()
        moves.check_job_lists(ctx(cfg, memdb, http, days=days))
        return sorted(u.split("/")[2] for u in http.calls)

    assert read(0) == ["good", "shy"]    # shy refuses …
    assert read(1) == ["good", "shy"]    # … is asked once more the next morning, and refuses again
    assert read(2) == ["good"]
    assert read(7) == ["good"]           # a week after the second refusal is day 8
    assert read(8) == ["good", "shy"]
    http.pages["https://shy/sitemap.xml"] = sitemap()
    assert read(9) == ["good"]           # that was its one retry, refused or not …
    assert read(15) == ["good", "shy"]   # … then it answers …
    assert read(16) == ["good", "shy"]   # … and goes back to daily


# N: new student and program pages ------------------------------------------------------------------------

def test_a_new_student_page_in_a_sitemap(blocked_cfg, memdb):
    c = company("citadel")
    cfg = blocked_cfg([c], program_pages={"citadel": ["https://www.citadel.com/page-sitemap.xml"]})
    base = ["https://www.citadel.com/careers/internships/", "https://www.citadel.com/notices/"]
    http = FakeHttp({"https://www.citadel.com/page-sitemap.xml": sitemap(*base)})
    assert moves.check_programs(ctx(cfg, memdb, http)) == []
    memdb.set("blocked:at:programs:citadel", "")
    http.pages["https://www.citadel.com/page-sitemap.xml"] = sitemap(
        *base, "https://www.citadel.com/careers/programs-and-events/discover-citadel-2027/",
        "https://www.citadel.com/what-we-do/commodities/")
    problems = moves.check_programs(ctx(cfg, memdb, http))
    assert [p["summary"] for p in problems] == [
        "its site has new student or program pages: https://www.citadel.com/careers/programs-and-events/discover-citadel-2027/"]


def test_a_new_program_in_a_feed_and_a_new_wordpress_page(blocked_cfg, memdb):
    g, cap = company("goldman-sachs"), company("capstone")
    feed = "https://www.goldmansachs.com/feeds/programs-and-internships.json"
    wp = "https://www.capstoneco.com/wp-json/wp/v2/pages?per_page=100&page=1&_fields=link,title"
    cfg = blocked_cfg([g, cap], program_pages={"goldman-sachs": [feed], "capstone": ["wp:https://www.capstoneco.com"]})
    http = FakeHttp({feed: [{"path": "/careers/students/programs-and-internships/americas/possibilities-series",
                             "title": "Possibilities Series"}],
                     wp: Resp(200, "", {"x-wp-totalpages": "1"},
                              json.dumps([{"link": "https://www.capstoneco.com/careers/", "title": {"rendered": "Careers"}}]).encode())})
    for _ in range(2):
        assert moves.check_programs(ctx(cfg, memdb, http)) == []  # first looks, one company a day
    for k in ("goldman-sachs", "capstone"):
        memdb.set(f"blocked:at:programs:{k}", "")
    http.pages[feed] = http.pages[feed] + [{"path": "/careers/students/programs-and-internships/americas/new-analyst-week",
                                            "title": "New Analyst Week"}]
    http.pages[wp] = Resp(200, "", {"x-wp-totalpages": "1"}, json.dumps([
        {"link": "https://www.capstoneco.com/careers/", "title": {"rendered": "Careers"}},
        {"link": "https://www.capstoneco.com/careers/internship-program/", "title": {"rendered": "Internship Program"}}]).encode())
    problems = moves.check_programs(ctx(cfg, memdb, http)) + moves.check_programs(ctx(cfg, memdb, http))
    assert sorted(p["key"] for p in problems) == ["capstone", "goldman-sachs"]
    assert "new-analyst-week (New Analyst Week)" in [p for p in problems if p["key"] == "goldman-sachs"][0]["summary"]


# G: new labels ---------------------------------------------------------------------------------------------

def test_new_goldman_experience_or_source_types(blocked_cfg, memdb):
    from internwatch.checkers.goldman import API
    g = company("goldman-sachs", checker="goldman")
    cfg = blocked_cfg([g])
    types = lambda *extra: {"data": {"RoleSearchExperience": {"enumValues": [{"name": n} for n in (
        "PROFESSIONAL", "EARLY_CAREER", "CAMPUS", "INTERNAL_MOBILITY", *extra)]},
        "ExternalSourceType": {"enumValues": [{"name": "AVATURE"}, {"name": "ORACLE"}]}}}
    http = FakeHttp({API: types()})
    assert moves.check_labels(ctx(cfg, memdb, http)) == []
    memdb.set("blocked:at:labels:goldman-sachs", "")
    http.pages[API] = types("SEASONAL")
    problems = moves.check_labels(ctx(cfg, memdb, http))
    assert [p["summary"] for p in problems] == [
        "Goldman's job API has new experience or source types: RoleSearchExperience.SEASONAL"]
    assert http.calls[-1].startswith("POST")


class GoldmanApi(FakeHttp):
    """Goldman's job API since Nov 2026: a query naming __type more than once is refused (HTTP 200 with an error)."""

    def __init__(self, types: dict):
        super().__init__({})
        self.types = types

    def post_json(self, url, **kw):
        query = kw["json"]["query"]
        self.calls.append(f"POST {url} {query}")
        if query.count("__type") > 1:
            return {"errors": [{"message": "This request is not asking for introspection in good faith - Query.__type "
                                           "is present too often!", "extensions": {"classification": "BadFaithIntrospection"}}]}
        t = query.split('__type(name: "')[1].split('"')[0]
        return {"data": {t: {"enumValues": [{"name": n} for n in self.types[t]]} if t in self.types else None}}


def test_goldman_types_are_asked_for_one_at_a_time_as_the_api_requires(blocked_cfg, memdb):
    cfg = blocked_cfg([company("goldman-sachs", checker="goldman")])
    api = GoldmanApi({"RoleSearchExperience": ["PROFESSIONAL", "EARLY_CAREER", "CAMPUS", "INTERNAL_MOBILITY"],
                      "ExternalSourceType": ["AVATURE", "ORACLE"]})
    assert moves.check_labels(ctx(cfg, memdb, api)) == []  # first look: a silent baseline
    assert len(api.calls) == 2 and memdb.get("blocked:ok:labels:goldman-sachs")
    assert json.loads(memdb.get("blocked:labels:goldman-sachs")) == [
        "ExternalSourceType.AVATURE", "ExternalSourceType.ORACLE", "RoleSearchExperience.CAMPUS",
        "RoleSearchExperience.EARLY_CAREER", "RoleSearchExperience.INTERNAL_MOBILITY", "RoleSearchExperience.PROFESSIONAL"]
    memdb.set("blocked:at:labels:goldman-sachs", "")
    api.types["ExternalSourceType"].append("WORKDAY")
    assert [p["summary"] for p in moves.check_labels(ctx(cfg, memdb, api))] == [
        "Goldman's job API has new experience or source types: ExternalSourceType.WORKDAY"]


def test_goldman_type_the_api_stops_answering_is_a_failed_read(blocked_cfg, memdb):
    cfg = blocked_cfg([company("goldman-sachs", checker="goldman")])
    api = GoldmanApi({"RoleSearchExperience": ["CAMPUS"]})  # ExternalSourceType answers null
    assert moves.check_labels(ctx(cfg, memdb, api)) == []
    assert memdb.get("blocked:labels:goldman-sachs") is None  # not taken as a baseline
    assert memdb.get("blocked:retry:labels:goldman-sachs") == "1" and not memdb.get("blocked:ok:labels:goldman-sachs")


def test_new_student_team_labels_at_meta_from_its_own_poll(blocked_cfg, memdb):
    from internwatch.health import Outcome
    meta = company("meta", checker="meta")
    cfg = blocked_cfg([meta])
    poll = lambda *deps: Outcome(company=meta, jobs=[job(str(i), "x", department=d) for i, d in enumerate(deps)])
    assert moves.observe(cfg, memdb, poll("AI Research / Internship - PhD / Research", "Security / Program Management")) == []
    assert json.loads(memdb.get("blocked:labels:meta")) == ["Internship - PhD"]  # Program Management isn't a student team
    problems = moves.observe(cfg, memdb, poll("AI Research / Internship - PhD", "Infrastructure / Internship - Product"))
    assert [p["summary"] for p in problems] == ["Meta labels jobs with new student teams: Internship - Product"]
    assert moves.observe(cfg, memdb, poll("AI Research / Internship - PhD")) == []  # a label that leaves stays known
    assert moves.observe(cfg, memdb, poll("X / Internship - Product")) == []
    degraded = poll("X / University Grad - New")
    degraded.degraded = "the Internship query failed"
    assert moves.observe(cfg, memdb, degraded) == []  # an incomplete poll is never judged


def test_no_other_company_poll_is_looked_at(blocked_cfg, memdb):
    from internwatch.health import Outcome
    other = company("other-meta", checker="meta")
    cfg = blocked_cfg([company("acme"), other])
    assert moves.observe(cfg, memdb, Outcome(company=other, jobs=[job("1", "x", department="Internship - Y")])) == []
    assert memdb.get("blocked:labels:other-meta") is None


def test_what_reads_like_a_student_or_program_page():
    yes = ["/careers/internships/", "/careers/early-talent/", "/programs-and-events/discover-citadel/", "/residency/",
           "/careers/students-and-early-career/", "/university-careers/", "/careers/emerging-talent/", "co-op"]
    no = ["/news-insights/", "/tower-research-capital-systematic-internaliser/", "/disclosure-for-residents-of-japan/",
          "/careers/international/", "/what-we-do/equities/"]
    assert [u for u in yes if not moves.STUDENT.search(u)] == []
    assert [u for u in no if moves.STUDENT.search(u)] == []


# S: parallel boards ----------------------------------------------------------------------------------------

BOARDS: dict = {}


@pytest.fixture
def fake_board(monkeypatch):
    from internwatch.adapters.base import REGISTRY, Checker

    class FakeBoard(Checker):
        type = "fake-board"

        def fetch(self, http, s, ctx=None):
            res = BOARDS[s["board"]]
            if isinstance(res, Exception):
                raise res
            return list(res)
    monkeypatch.setitem(REGISTRY, "fake-board", FakeBoard)
    BOARDS.clear()
    return BOARDS


def test_a_matching_role_only_on_a_parallel_board(blocked_cfg, memdb, fake_board):
    ctc = company("chicago-trading-company", checker="greenhouse", settings={"board": "chicagotradingcampus"})
    cfg = blocked_cfg([ctc], parallel_sources=[{"company": "chicago-trading-company", "checker": "fake-board",
                                                "settings": {"board": "ctccampusboard"}}])
    memdb.conn.execute("INSERT INTO jobs(company, job_id, title, url, first_seen, last_seen) VALUES "
                       "('chicago-trading-company', '1', 'Quant Trading Internship - Summer 2027', '', 't', 't')")
    fake_board["ctccampusboard"] = [job("a1", "Associate Engineer - 2027 Start")]
    assert moves.check_parallel(ctx(cfg, memdb)) == []  # first look
    fake_board["ctccampusboard"] = [job("a1", "Associate Engineer - 2027 Start"),
                                    job("a2", "Quant Trading Internship - Summer 2027"),   # a twin: stored already
                                    job("a3", "Accountant"),                                 # not a student role
                                    job("a4", "Software Engineering Internship - Summer 2027", "Chicago, IL")]
    problems = moves.check_parallel(ctx(cfg, memdb, days=1))  # the next morning
    assert len(problems) == 1 and problems[0]["kind"] == "posting elsewhere?"
    assert "1 matching role(s)" in problems[0]["summary"] and "'Software Engineering Internship - Summer 2027'" in problems[0]["summary"]
    assert moves.check_parallel(ctx(cfg, memdb, days=2)) == []  # once, not every morning
    assert memdb.q("SELECT job_id FROM jobs WHERE company='chicago-trading-company'")[0]["job_id"] == "1"  # nothing stored


def test_a_refused_parallel_board_and_boards_of_other_companies(blocked_cfg, memdb, fake_board):
    ukg = company("ukg")
    cfg = blocked_cfg([ukg, company("other-co")], parallel_sources=[
        {"company": "ukg", "checker": "fake-board", "settings": {"board": "rm926"}},
        {"company": "other-co", "checker": "fake-board", "settings": {"board": "never"}}])
    fake_board["rm926"] = FetchError("HTTP 503 for GET x")
    assert moves.check_parallel(ctx(cfg, memdb)) == []
    assert memdb.get("blocked:retry:parallel:fake-board:board=rm926") == "1"
    assert memdb.get("blocked:parallel:other-co:fake-board:board=never") is None  # never read: not one of the 32


def test_the_real_parallel_sources_name_adapters_that_exist():
    from internwatch.adapters import get_checker
    from internwatch.config import load
    for x in load().settings.get("liveness", "parallel_sources"):
        assert get_checker(x["checker"]) is not None


# L: third-party lists, board registries, Getro boards -----------------------------------------------------------

SPEEDY = """## US internships
| Company | Position | Location | Posting | Age |
|---|---|---|---|---|
| <a href="https://x"><strong>Chicago Trading Company</strong></a> | Software Engineering Intern | Chicago | <a href="https://job-boards.greenhouse.io/ctccampusboard/jobs/1"><img src="https://img.shields.io/x"></a> | 2d |
| ↳ | Quant Intern | Chicago | [Apply](https://job-boards.greenhouse.io/chicagotradingcampus/jobs/2) | 3d |
"""


def test_list_formats():
    assert moves.list_rows("markdown", SPEEDY) == [
        ("Chicago Trading Company", "Software Engineering Intern", "https://job-boards.greenhouse.io/ctccampusboard/jobs/1", None),
        ("Chicago Trading Company", "Quant Intern", "https://job-boards.greenhouse.io/chicagotradingcampus/jobs/2", None)]
    assert moves.list_rows("simplify", json.dumps([{"company_name": "Coinbase", "title": "SWE Intern", "url": "u"}])) == [
        ("Coinbase", "SWE Intern", "u", None)]
    assert moves.list_rows("trackr", json.dumps([{"companyId": "chicago-trading-company", "name": "Quant", "url": "u"}])) == [
        ("chicago trading company", "Quant", "u", None)]
    reg = moves.list_rows("registry", json.dumps([
        {"name": "Fidelity Investments", "slug": "fmr", "ats": "workday", "wd": "wd1", "site": "targeted"},
        {"name": "Chicago Trading Company", "slug": "ctccampusboard", "ats": "greenhouse"},
        {"name": "Uber", "slug": "iaziqy.fa.ocs.oraclecloud.com", "ats": "oracle", "site": "CX_1"},
        {"name": "X", "slug": "x", "ats": "unknownats"}]))
    assert [r[3] for r in reg] == ["workday:site=targeted,tenant=fmr", "greenhouse:board=ctccampusboard",
                                   "oracle:host=iaziqy.fa.ocs.oraclecloud.com,site=cx_1"]
    assert reg[0][2] == "https://fmr.wd1.myworkdayjobs.com/targeted"
    assert moves.ripplematch_rows(sitemap("https://app.ripplematch.com/company/ukg-ultimate-kronos-group",
                                          "https://app.ripplematch.com/about")) == [
        ("ukg ultimate kronos group", "", "https://app.ripplematch.com/company/ukg-ultimate-kronos-group",
         "ripplematch:company=ukg-ultimate-kronos-group")]


ROW = "| {} | {} | x | [Apply]({}) | 1d |\n"
HEAD = "| Company | Position | Location | Posting | Age |\n|---|---|---|---|---|\n"
GH = "https://job-boards.greenhouse.io/{}/jobs/{}"


def _list_cfg(blocked_cfg, *companies, **kw):
    url = "https://lists.example/README.md"
    return blocked_cfg(list(companies), listings=[{"name": "speedy", "format": "markdown", "label": "speedy", "url": url}], **kw), url


def akuna():
    return company("akuna-capital", name="Akuna Capital", checker="greenhouse", settings={"board": "akunacapital"})


def test_a_first_look_at_a_list_raises_a_board_nobody_named(blocked_cfg, memdb):
    """Akuna's second board was missed because a list's first read was recorded silently."""
    cfg, url = _list_cfg(blocked_cfg, akuna())
    http = FakeHttp({url: HEAD + ROW.format("Akuna Capital", "Quant Intern", GH.format("akunacapitaloci", 2))})
    problems = moves.check_listings(ctx(cfg, memdb, http))
    assert [(p["key"], p["kind"]) for p in problems] == [("akuna-capital", "new job site?")]
    assert "greenhouse:board=akunacapitaloci" in problems[0]["summary"] and "'Quant Intern'" in problems[0]["summary"]
    assert moves.check_listings(ctx(cfg, memdb, http, days=1)) == []     # a second run raises nothing new …
    alerts.record(memdb, problems, [])
    assert [a["kind"] for a in alerts.for_email(memdb)[0]] == ["new job site?"]   # … and it stays listed


def test_a_first_look_raises_for_every_company_not_just_the_31(blocked_cfg, memdb):
    flow = company("other-flow-traders", name="Flow Traders", checker="greenhouse", settings={"board": "flowtraders"})
    cfg, url = _list_cfg(blocked_cfg, flow)          # keys starting "other" are outside the blocked list
    assert "other-flow-traders" not in moves.blocked(cfg)
    http = FakeHttp({url: HEAD + ROW.format("Flow Traders", "Co-op", GH.format("ftsp27co-ops", 8176219))})
    assert [p["key"] for p in moves.check_listings(ctx(cfg, memdb, http))] == ["other-flow-traders"]


def test_what_is_read_mirrored_or_linked_by_a_posting_raises_nothing(blocked_cfg, memdb):
    ctc = company("chicago-trading-company", name="Chicago Trading Company", checker="greenhouse",
                  settings={"boards": ["chicagotrading", "chicagotradingcampus"]})
    uber = company("uber", name="Uber", checker="oracle", settings={"host": "iaziqy.fa.ocs.oraclecloud.com", "site": "UberCareers"})
    atl = company("atlassian", name="Atlassian", checker="atlassian")
    freight = company("other-uber-freight", name="Uber Freight", checker="greenhouse", settings={"board": "uberfreight"})
    cfg, url = _list_cfg(blocked_cfg, ctc, uber, atl, freight,
                         aliases={"oracle:host=iaziqy.fa.ocs.oraclecloud.com,site=cx_1":
                                  "oracle:host=iaziqy.fa.ocs.oraclecloud.com,site=ubercareers"},
                         parallel_sources=[{"company": "chicago-trading-company", "checker": "greenhouse",
                                            "settings": {"board": "ctccampusboard"}}])
    memdb.upsert_jobs("atlassian", [Job(id="1", title="Intern", url="https://campus-americas.icims.com/jobs/1/intern/job")], iso())
    text = HEAD + "".join(ROW.format(*r) for r in [
        ("Chicago Trading Company", "Configured", GH.format("chicagotradingcampus", 2)),
        ("Chicago Trading Company", "Watched", GH.format("ctccampusboard", 3)),
        ("Uber", "Mirror", "https://iaziqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/1"),
        ("Uber Freight", "Its own company", GH.format("uberfreight", 4)),
        ("Atlassian", "Stored", "https://campus-americas.icims.com/jobs/1/intern/job")])
    assert moves.check_listings(ctx(cfg, memdb, FakeHttp({url: text}))) == []


def test_a_board_on_three_lists_is_one_alert(blocked_cfg, memdb):
    urls = [f"https://lists.example/{i}.md" for i in range(3)]
    cfg = blocked_cfg([akuna()], listings=[{"name": f"l{i}", "format": "markdown", "url": u} for i, u in enumerate(urls)])
    text = HEAD + ROW.format("Akuna Capital", "Quant Intern", GH.format("akunacapitaloci", 2))
    assert len(moves.check_listings(ctx(cfg, memdb, FakeHttp({u: text for u in urls})))) == 1


def test_an_earlier_silent_baseline_does_not_suppress_the_alert(blocked_cfg, memdb):
    cfg, url = _list_cfg(blocked_cfg, akuna())
    memdb.set("blocked:list:speedy", json.dumps({"akuna-capital": ["greenhouse:board=akunacapitaloci"]}))
    http = FakeHttp({url: HEAD + ROW.format("Akuna Capital", "Quant Intern", GH.format("akunacapitaloci", 2))})
    assert len(moves.check_listings(ctx(cfg, memdb, http))) == 1


def test_a_dismissed_board_is_not_raised_again(blocked_cfg, memdb):
    cfg, url = _list_cfg(blocked_cfg, akuna())
    http = FakeHttp({url: HEAD + ROW.format("Akuna Capital", "Quant Intern", GH.format("akunacapitaloci", 2))})
    alerts.record(memdb, moves.check_listings(ctx(cfg, memdb, http)), [])
    assert len(alerts.dismiss(memdb, kind="new job site?")) == 1
    alerts.record(memdb, moves.check_listings(ctx(cfg, memdb, http, days=1)), [])
    assert alerts.for_email(memdb)[0] == []


def test_a_board_no_list_links_any_more_clears(blocked_cfg, memdb):
    cfg, url = _list_cfg(blocked_cfg, akuna())
    http = FakeHttp({url: HEAD + ROW.format("Akuna Capital", "Quant Intern", GH.format("akunacapitaloci", 2))})
    alerts.record(memdb, moves.check_listings(ctx(cfg, memdb, http)), [])
    http.pages[url] = HEAD + ROW.format("Akuna Capital", "Quant Intern", GH.format("akunacapital", 3))
    assert moves.check_listings(ctx(cfg, memdb, http, days=1)) == []
    assert alerts.for_email(memdb)[0] == []


def test_a_board_failing_email_is_raised_again(blocked_cfg, memdb):
    cfg, url = _list_cfg(blocked_cfg, akuna())
    http = FakeHttp({url: HEAD + ROW.format("Akuna Capital", "Quant Intern", GH.format("akunacapitaloci", 2))})
    p = moves.check_listings(ctx(cfg, memdb, http))[0]
    liveness.restore(memdb, p)
    assert len(moves.check_listings(ctx(cfg, memdb, http, days=1))) == 1


def test_a_shortened_link_is_never_followed(blocked_cfg, memdb):
    """go.vansh.nyc's robots.txt disallows every reader: its links name a company but reveal no job system."""
    cfg, url = _list_cfg(blocked_cfg, akuna())
    http = FakeHttp({url: HEAD + ROW.format("Akuna Capital", "Quant Intern", "https://go.vansh.nyc/10y")})
    assert moves.check_listings(ctx(cfg, memdb, http)) == []
    assert http.calls == [f"GET {url}"]


def test_an_unchanged_list_is_not_parsed_again(blocked_cfg, memdb):
    url = "https://lists.example/listings.json"
    cfg = blocked_cfg([company("coinbase", name="Coinbase")], listings=[{"name": "s", "format": "simplify", "url": url}])
    http = FakeHttp({url: Resp(200, url, {"etag": '"v1"'}, b"[]")})
    moves.check_listings(ctx(cfg, memdb, http))
    assert memdb.get("lists:etag:s") == '"v1"'
    http.pages[url] = Resp(304, url, {}, b"")
    assert moves.check_listings(ctx(cfg, memdb, http, days=7)) == []


def test_getros_copy_of_a_careers_page(blocked_cfg, memdb):
    sg = company("seatgeek", name="SeatGeek", checker="greenhouse", settings={"board": "seatgeek"})
    cfg = blocked_cfg([sg], getro=[{"company": "seatgeek", "board": "https://jobs.accel.com", "path": "/companies/seatgeek/"}])
    job_url = "https://jobs.accel.com/companies/seatgeek/jobs/{}-{}"
    http = FakeHttp({"https://jobs.accel.com/sitemap.xml": sitemap("https://jobs.accel.com/sitemap_jobs1.xml"),
                     "https://jobs.accel.com/sitemap_jobs1.xml": sitemap(job_url.format(1, "ux-design-internship"))})
    assert moves.check_getro(ctx(cfg, memdb, http)) == []  # first look
    http.pages["https://jobs.accel.com/sitemap_jobs1.xml"] = sitemap(
        job_url.format(1, "ux-design-internship"), job_url.format(2, "software-engineer-internship"),
        job_url.format(3, "data-internship"))
    http.pages[job_url.format(2, "software-engineer-internship")] = (
        '{"source":"career_page","url":"https://seatgeek.com","x":{"url":"https://job-boards.greenhouse.io/sgcampus/jobs/7700001"}}')
    http.pages[job_url.format(3, "data-internship")] = (
        '{"source":"career_page","url":"https://boards.greenhouse.io/seatgeek/jobs/8888888"}')
    problems = moves.check_getro(moves.Ctx(cfg, memdb, None, lambda d, **kw: http, float("inf"), set(),
                                           now=utcnow() + timedelta(days=7), started="2026-11-04T09:00:00Z"))
    assert [p["summary"].split(" (e.g.")[0] for p in problems] == [
        "Getro's copy of its careers page links a job site InternWatch doesn't read: greenhouse:board=sgcampus"]
    assert sorted(json.loads(memdb.get("blocked:pending:getro:seatgeek"))) == ["7700001", "8888888"]


def test_the_status_shows_each_check_and_recent_alerts(blocked_cfg, memdb):
    cfg = blocked_cfg([company("acme")])
    moves.done(memdb, "page", "acme", "refused", utcnow())
    memdb.set("live_alert:acme:page", iso())
    memdb.set("live_alert:other:page", iso())
    memdb.conn.row_factory = __import__("sqlite3").Row
    out = moves.status(cfg, memdb.conn)
    assert "watched by moves.py: 1" in out
    assert "P  careers and WordPress pages: 0 read, last never; 0/1 reads answered in 28 days; 1 to retry" in out
    assert "alerts in the last 28 days: 1: acme (page," in out



def test_a_link_to_the_companys_own_domain_is_not_a_job_system():
    c = company("liberty", checker="eightfold", settings={"host": "searchjobs.libertymutualgroup.com",
                                                          "domain": "libertymutual.com", "api": "v2"})
    assert moves.configured_hosts(c) == {"searchjobs.libertymutualgroup.com": "eightfold:domain=libertymutual.com"}
    assert moves.systems_in('<a href="https://www.libertymutual.com/about">About</a>', "https://jobs.x.com/", c, {}) == set()
    fid = company("fidelity", checker="workday", settings={"host": "wd1.myworkdaysite.com", "tenant": "fmr", "site": "x"})
    assert moves.configured_hosts(fid) == {}  # shared by every tenant on it
