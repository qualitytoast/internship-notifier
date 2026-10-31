"""Boards read but not stored (watch.py): dismissed `new job site?` boards and mirrors. The job lists below are the real
ones of Oct 30, so "stays quiet" means quiet on what these boards really list."""
import json
import sqlite3
from datetime import timedelta

import pytest

from internwatch import alerts, moves, watch
from internwatch.db import iso, parse_iso, utcnow
from internwatch.models import CheckTimeout, FetchError, RobotsBlocked, ShapeError
from internwatch.runner import RunOptions, Runner

from conftest import FakeChecker, company, job

BOARDS: dict = {}
CONTRACTORS = [job("/job/a_R1", "Corporate Counsel - eDiscovery", "Remote, Massachusetts"),
               job("/job/b_R2", "Sr Business Strategist, TFB Base Analytics", "Bellevue, Washington"),
               job("/job/c_R3", "VM-Analytics Manager", "Remote, California"),
               job("/job/d_R4", "Sr Director, Digital Engagement and Commerce", "Bellevue, Washington")]
ALUMNI = [job("/job/e_R5", "Mobile Associate - Retail Sales", "Half Moon Bay, California"),
          job("/job/f_R6", "Sr Business Intelligence Analyst, Broadband", "3 Locations")]
DRW_FR = [job("1", "Développeur de Logiciels", "Montreal"), job("2", "Ingénieur de plateforme – Ingénierie IA", "Montreal")]
ANYSCALE = [job("x", "We have moved our Careers Page to: https://jobs.ashbyhq.com/anyscale", "San Francisco or Palo Alto, CA")]
RAMP = [job("7", "Copy of Chief Legal Officer", "dublin")]
INTERN = job("99", "Software Engineer Intern - Summer 2027", "Bellevue, WA")


class FakeBoard:
    def fetch(self, http, s, ctx=None):
        res = BOARDS[next(str(s[k]) for k in ("board", "site", "company", "portal", "company_id", "host") if k in s)]
        if isinstance(res, Exception):
            raise res
        if ctx is not None and res and res[-1] == "cut short":
            ctx.partial = True
            return list(res[:-1])
        return list(res)


@pytest.fixture(autouse=True)
def fake_board(monkeypatch):
    monkeypatch.setattr(watch, "get_checker", lambda kind: FakeBoard())
    BOARDS.clear()
    return BOARDS


class Http:
    def close(self):
        pass


def cfg_of(make_cfg, companies, boards=(), **liveness):
    return make_cfg(companies, liveness={"watch_boards": list(boards), "watch_every_days": {}, "blocked": [], **liveness})


def read(cfg, db, healthy=(), budget=float("inf")):
    return watch.run(cfg, db, None, lambda deadline, **kw: Http(), budget, set(healthy))


def next_morning(db):
    for r in db.q("SELECT key, value FROM kv WHERE key LIKE 'blocked:at:watch%' AND value <> ''"):
        db.set(r["key"], iso(parse_iso(r["value"]) - timedelta(days=1)))
    for r in db.q("SELECT key, value FROM kv WHERE key LIKE 'blocked:pending:watch:%'"):
        pending = json.loads(r["value"])
        db.set(r["key"], json.dumps({k: {**p, "found": iso(parse_iso(p["found"]) - timedelta(days=1))}
                                     for k, p in pending.items()}))


def dismiss(db, c, system, url=""):
    alerts.record(db, [{"key": c.key, "name": c.name, "kind": "new job site?", "summary": f"a list links {system}",
                        "alert": {"id": f"live_alert:{c.key}:list:{system}:board", "rule": "list_system", "item": system,
                                  "scope": "lists", "url": url}}], [])
    alerts.dismiss(db, kind="new job site?")


def store(db, company_key, jid, title, location="New York, NY", removed=None, alt_ids=()):
    db.conn.execute("INSERT INTO jobs(company, job_id, title, location, url, first_seen, last_seen, removed_at, alt_ids)"
                    " VALUES(?,?,?,?,'','t','t',?,?)", (company_key, jid, title, location, removed, json.dumps(list(alt_ids))))


@pytest.fixture
def tmobile():
    return company("t-mobile", name="T-Mobile")


@pytest.fixture
def live(make_cfg, memdb, tmobile):
    """The five boards that list jobs today, each behind a dismissed `new job site?` alert."""
    drw, anyscale, ramp = company("drw", name="DRW"), company("anyscale"), company("ramp")
    BOARDS.update(contractorconversion=list(CONTRACTORS), alumni=list(ALUMNI), drwfr=list(DRW_FR), anyscale=list(ANYSCALE),
                  ramp=list(RAMP))
    dismiss(memdb, tmobile, "workday:site=contractorconversion,tenant=tmobile",
            "https://tmobile.wd1.myworkdayjobs.com/contractorconversion/job/Bellevue-Washington/x")
    dismiss(memdb, tmobile, "workday:site=alumni,tenant=tmobile", "https://tmobile.wd1.myworkdayjobs.com/alumni")
    dismiss(memdb, drw, "greenhouse:board=drwfr")
    dismiss(memdb, anyscale, "lever:site=anyscale")
    dismiss(memdb, ramp, "greenhouse:board=ramp")
    return cfg_of(make_cfg, [tmobile, drw, anyscale, ramp])


EVERYONE = ("t-mobile", "drw", "anyscale", "ramp")


# quiet until something new that matters ----------------------------------------------------------------------------

def test_the_five_boards_that_list_jobs_stay_quiet_morning_after_morning(live, memdb):
    for _ in range(4):
        assert read(live, memdb, EVERYONE) == []
        next_morning(memdb)
    assert all(memdb.get(f"blocked:pending:watch:{b.id}") == "{}" for b in watch.boards(live, memdb))


def test_a_role_that_matters_is_held_a_morning_then_alerts_once(live, memdb):
    BOARDS["alumni"].append(INTERN)
    assert read(live, memdb, EVERYONE) == []                # seen: it may just be newer than this morning's poll
    next_morning(memdb)
    problems = read(live, memdb, EVERYONE)
    assert [p["kind"] for p in problems] == ["posting elsewhere?"]
    assert "'Software Engineer Intern - Summer 2027'" in problems[0]["summary"]
    alerts.record(memdb, problems, [])
    next_morning(memdb)
    assert read(live, memdb, EVERYONE) == []                # once, not every morning
    assert [a["kind"] for a in alerts.for_email(memdb)[0]] == ["posting elsewhere?"]  # and it stays listed


@pytest.mark.parametrize("quiet", [job("50", "Senior Software Engineer, Backend (Python, Node.js, AWS, Postgres)"),
                                   job("51", "Software Engineer Intern - Summer 2027", "Paris, France")])
def test_a_senior_or_a_foreign_role_stays_quiet(live, memdb, quiet):
    BOARDS["alumni"].append(quiet)
    read(live, memdb, EVERYONE)
    next_morning(memdb)
    assert read(live, memdb, EVERYONE) == []


def test_a_role_with_a_stored_twin_stays_quiet(live, memdb):
    store(memdb, "t-mobile", "/job/main_R77", "Software Engineer Intern - Summer 2027", "Seattle, WA")
    BOARDS["alumni"].append(INTERN)
    read(live, memdb, EVERYONE)
    next_morning(memdb)
    assert read(live, memdb, EVERYONE) == []


def test_a_job_retitled_into_an_internship_alerts(live, memdb):
    assert read(live, memdb, EVERYONE) == []
    BOARDS["drwfr"][0] = job("1", "Software Developer Intern", "New York, NY")
    next_morning(memdb)
    read(live, memdb, EVERYONE)
    next_morning(memdb)
    assert [p["key"] for p in read(live, memdb, EVERYONE)] == ["drw"]


def test_a_dismissed_alert_about_a_role_stays_off_while_the_role_is_there(live, memdb):
    BOARDS["alumni"].append(INTERN)
    read(live, memdb, EVERYONE)
    next_morning(memdb)
    alerts.record(memdb, read(live, memdb, EVERYONE), [])
    alerts.dismiss(memdb, kind="posting elsewhere?")
    for _ in range(2):
        next_morning(memdb)
        assert read(live, memdb, EVERYONE) == []


# dead boards ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("answer", [FetchError("HTTP 404 for GET x"), FetchError("HTTP 422 for POST x"), [],
                                    ShapeError("smartrecruiters:visa: hosted career page has no job groups")])
def test_a_dead_board_stays_quiet_is_read_daily_and_never_goes_dark(make_cfg, memdb, answer):
    c = company("visa")
    dismiss(memdb, c, "smartrecruiters:company=visa")
    cfg = cfg_of(make_cfg, [c])
    BOARDS["visa"] = answer
    for _ in range(4):
        assert read(cfg, memdb, ["visa"]) == []
        assert moves.finish(cfg, memdb, None, None, set()) == []
        next_morning(memdb)
    assert not moves.refused_last(memdb, "watch", "visa/smartrecruiters:company=visa")
    assert not memdb.get("blocked:retry:watch:visa/smartrecruiters:company=visa")


def test_a_dead_board_that_wakes_up(make_cfg, memdb):
    c = company("glean")
    dismiss(memdb, c, "smartrecruiters:company=glean")
    cfg = cfg_of(make_cfg, [c])
    BOARDS["glean"] = []
    assert read(cfg, memdb, ["glean"]) == []
    BOARDS["glean"] = [job("5", "Senior Software Engineer, Backend (Python, Node.js, AWS, Postgres)")]  # Glean's, on Oct 30
    next_morning(memdb)
    assert read(cfg, memdb, ["glean"]) == []
    BOARDS["glean"].append(job("6", "Software Engineer Intern", "New York, NY"))
    next_morning(memdb)
    read(cfg, memdb, ["glean"])
    next_morning(memdb)
    assert [p["key"] for p in read(cfg, memdb, ["glean"])] == ["glean"]


def test_a_dismissed_board_stays_watched_after_its_alert_cleared(make_cfg, memdb):
    c = company("drw")
    dismiss(memdb, c, "greenhouse:board=drwfr")
    cfg = cfg_of(make_cfg, [c])
    alerts.seen(memdb, "drw", "list_system", set(), scope="lists")  # no list links it any more
    assert memdb.q("SELECT state FROM alerts")[0]["state"] == "cleared"
    assert [b.id for b in watch.boards(cfg, memdb)] == ["drw/greenhouse:board=drwfr"]


def test_a_board_added_to_the_config_is_no_longer_watched(make_cfg, memdb):
    c = company("drw", checker="greenhouse", settings={"boards": ["drweng", "drwfr"]})
    dismiss(memdb, c, "greenhouse:board=drwfr")
    assert watch.boards(cfg_of(make_cfg, [c]), memdb) == []


# timing --------------------------------------------------------------------------------------------------------------

def snowflake(make_cfg):
    c = company("snowflake")
    BOARDS["snowflake"] = [job("97e37c43", "Product Management Intern (Summer 2027)", "US-CA-Menlo Park (United States)")]
    return cfg_of(make_cfg, [c], [{"company": "snowflake", "checker": "ashby", "settings": {"board": "snowflake"}}])


def test_a_role_the_next_poll_stores_raises_nothing(make_cfg, memdb):
    cfg = snowflake(make_cfg)
    assert read(cfg, memdb, ["snowflake"]) == []
    store(memdb, "snowflake", "SNCOUS1", "Product Management Intern (Summer 2027)", "Menlo Park, California, United States")
    next_morning(memdb)
    assert read(cfg, memdb, ["snowflake"]) == []
    assert memdb.get("blocked:pending:watch:snowflake/ashby:board=snowflake") == "{}"
    assert alerts.for_email(memdb)[0] == []


def test_the_hold_goes_on_while_the_company_has_no_healthy_poll(make_cfg, memdb):
    cfg = snowflake(make_cfg)
    read(cfg, memdb)
    for _ in range(3):
        next_morning(memdb)
        assert read(cfg, memdb, healthy=()) == []
    next_morning(memdb)
    assert len(read(cfg, memdb, ["snowflake"])) == 1


def test_a_main_board_that_lags_longer_alerts_and_then_resolves(make_cfg, memdb):
    cfg = snowflake(make_cfg)
    read(cfg, memdb, ["snowflake"])
    next_morning(memdb)
    alerts.record(memdb, read(cfg, memdb, ["snowflake"]), [])
    assert len(alerts.for_email(memdb)[0]) == 1
    store(memdb, "snowflake", "SNCOUS1", "Product Management Intern (Summer 2027)", "Menlo Park, California, United States")
    next_morning(memdb)
    read(cfg, memdb, ["snowflake"])
    assert alerts.for_email(memdb)[0] == []
    assert [a["state"] for a in alerts.for_email(memdb)[1]] == ["resolved"]


def test_a_role_that_leaves_the_board_clears_its_alert(make_cfg, memdb):
    cfg = snowflake(make_cfg)
    read(cfg, memdb, ["snowflake"])
    next_morning(memdb)
    alerts.record(memdb, read(cfg, memdb, ["snowflake"]), [])
    BOARDS["snowflake"] = []
    next_morning(memdb)
    read(cfg, memdb, ["snowflake"])
    assert alerts.for_email(memdb)[0] == []


# twins ---------------------------------------------------------------------------------------------------------------

def stored_for(make_cfg, memdb, key="acme", **kw):
    c = company(key, **kw)
    return watch.Stored(cfg_of(make_cfg, [c]), memdb, c, utcnow())


def test_peak6_title_differs_only_by_the_season(make_cfg, memdb):
    store(memdb, "peak6", "1", "Trading Internship for Women+ Summer 2027", "Chicago, IL")
    assert stored_for(make_cfg, memdb, "peak6").has(job("r", "Trading Internship for Women+ 2027", "Chicago, IL, USA"))


def test_epic_city_differs_but_the_title_is_stored(make_cfg, memdb):
    store(memdb, "epic", "1", "Software Developer Intern - Summer 2027", "Verona, WI, United States")
    assert stored_for(make_cfg, memdb, "epic").has(job("r", "Software Developer Intern - Summer 2027", "Madison, WI, USA"))


def test_titles_naming_different_years_are_not_twins(make_cfg, memdb):
    store(memdb, "acme", "1", "Software Engineer Intern 2027")
    assert not stored_for(make_cfg, memdb).has(job("r", "Software Engineer Intern 2028"))


def test_a_stored_twin_abroad_does_not_count(make_cfg, memdb):
    store(memdb, "acme", "1", "Software Engineer Intern", "Taipei, Taiwan")
    assert not stored_for(make_cfg, memdb).has(job("r", "Software Engineer Intern", "Austin, TX"))


def test_a_vague_location_on_either_side_counts_as_the_same_place(make_cfg, memdb):
    store(memdb, "acme", "1", "Data Engineer Intern", "2 Locations")
    store(memdb, "acme", "2", "ML Engineer Intern", "Paris, France")
    s = stored_for(make_cfg, memdb)
    assert s.has(job("r", "Data Engineer Intern", "Austin, TX")) and s.has(job("q", "ML Engineer Intern", "3 Locations"))


def test_a_title_twin_closed_over_30_days_ago_does_not_count_but_an_id_always_does(make_cfg, memdb):
    old = iso(utcnow() - timedelta(days=31))
    store(memdb, "acme", "1", "Software Engineer Intern", removed=old)
    store(memdb, "acme", "778899", "Quant Intern", removed=old)
    s = stored_for(make_cfg, memdb)
    assert not s.has(job("r", "Software Engineer Intern")) and s.has(job("778899", "Quant Intern"))


def test_a_workday_job_matches_a_stored_requisition(make_cfg, memdb):
    store(memdb, "acme", "2732", "Anything", alt_ids=["JR2012345"])
    s = stored_for(make_cfg, memdb)
    assert s.has(job("/job/US-CA-Santa-Clara/Intern_JR2012345", "Intern")) and not s.has(job("/job/x/Intern_JR999", "Intern"))
    assert s.has(job("/job/x/Other", "Other", extra={"alt_ids": ["JR2012345"]}))


# controls: the real boards that should have fired -----------------------------------------------------------------------

def test_visas_apprentices_alert_and_its_stored_repeat_does_not(make_cfg, memdb):
    c = company("visa")
    store(memdb, "visa", "/job/a_REF777", "Workforce Protection Intern - Summer 2027", "US - Foster City, CA")
    BOARDS["Visa_Talent_Portal"] = [job(f"/job/Cybersecurity-Apprentice_REF{i}", "Cybersecurity Apprentice", "US - Ashburn, VA")
                                    for i in range(5)]
    BOARDS["Visa_Talent_Portal"].append(job("/job/w_REF9", "Workforce Protection Intern - Summer 2027", "US - Foster City, CA"))
    cfg = cfg_of(make_cfg, [c], [{"company": "visa", "name": "Talent Portal", "checker": "workday", "settings": {
        "host": "visa.wd5.myworkdayjobs.com", "tenant": "visa", "site": "Visa_Talent_Portal"}}])
    read(cfg, memdb, ["visa"])
    next_morning(memdb)
    problems = read(cfg, memdb, ["visa"])
    assert len(problems) == 1 and "5 matching role(s)" in problems[0]["summary"]
    assert "Workforce" not in problems[0]["summary"]
    assert len(problems[0]["alerts"]) == 5


# schedule ------------------------------------------------------------------------------------------------------------

def nvidia(make_cfg):
    c, t = company("nvidia", name="NVIDIA"), company("t-mobile", name="T-Mobile")
    BOARDS.update(interns=[job("/job/a_JR1", "Research Intern")], whole=[], alumni=[])
    return c, t, cfg_of(make_cfg, [c, t], [
        {"company": "nvidia", "name": "interns", "checker": "workday", "settings": {"site": "interns"}},
        {"company": "nvidia", "name": "full", "checker": "workday", "every_days": 7, "settings": {"site": "whole"}},
        {"company": "t-mobile", "name": "alumni", "checker": "workday", "every_days": 7, "settings": {"site": "alumni"}}])


def spy(monkeypatch):
    calls = []
    original = FakeBoard.fetch

    def fetch(self, http, s, ctx=None):
        calls.append(s.get("site"))
        return original(self, http, s, ctx)
    monkeypatch.setattr(FakeBoard, "fetch", fetch)
    return calls


def test_full_reads_are_weekly_on_different_mornings_and_the_intern_read_daily(make_cfg, memdb, monkeypatch):
    *_, cfg = nvidia(make_cfg)
    calls = spy(monkeypatch)
    week = []
    for _ in range(9):
        calls.clear()
        read(cfg, memdb, ["nvidia", "t-mobile"])
        week.append(list(calls))
        next_morning(memdb)
    assert all(day[0] == "interns" for day in week)
    assert [d[1:] for d in week][:2] == [["whole"], ["alumni"]]  # one full read a morning
    assert sum("whole" in d for d in week) == 2 and sum("alumni" in d for d in week) == 2  # and each is back after a week


def test_a_full_read_waits_for_a_morning_with_room(make_cfg, memdb, monkeypatch):
    import time
    *_, cfg = nvidia(make_cfg)
    calls = spy(monkeypatch)
    memdb.set("blocked:took:nvidia/full", "246")
    memdb.set("blocked:took:t-mobile/alumni", "90")
    read(cfg, memdb, ["nvidia"], budget=time.monotonic() + 100)     # alumni's turn would fit, but NVIDIA's comes first
    assert "whole" not in calls and memdb.get("blocked:at:watch-full:nvidia/full") is None
    calls.clear()
    read(cfg, memdb, ["nvidia"], budget=time.monotonic() + 300)     # the next morning has room
    assert "whole" in calls


def test_a_read_out_of_budget_stays_due(make_cfg, memdb):
    *_, cfg = nvidia(make_cfg)
    BOARDS["interns"] = CheckTimeout("time budget exhausted before GET x (0 requests made)")
    assert read(cfg, memdb, ["nvidia"]) == []
    assert memdb.get("blocked:at:watch:nvidia/interns") is None and memdb.get("blocked:rate:watch:nvidia/interns") is None
    BOARDS["interns"] = []
    read(cfg, memdb, ["nvidia"])
    assert memdb.get("blocked:at:watch:nvidia/interns")


def test_a_read_cut_short_by_time_stays_due(make_cfg, memdb):
    *_, cfg = nvidia(make_cfg)
    BOARDS["whole"] = [job("/job/a_JR5", "Software Engineer Intern"), "cut short"]
    read(cfg, memdb, ["nvidia"], budget=0)  # out of time before anything starts
    assert memdb.get("blocked:at:watch-full:nvidia/full") is None


def test_a_read_an_adapter_cut_short_with_time_left_is_a_failed_read_not_an_empty_board(make_cfg, memdb):
    *_, cfg = nvidia(make_cfg)
    BOARDS["interns"] = [job("/job/a_JR5", "Software Engineer Intern"), "cut short"]  # Workday keeps what it read
    assert read(cfg, memdb, ["nvidia"]) == []
    assert json.loads(memdb.get("blocked:rate:watch:nvidia/interns"))[-1][1:] == [0, "failed"]
    assert memdb.get("blocked:retry:watch:nvidia/interns") == "1" and memdb.get("blocked:at:watch:nvidia/interns") is None
    assert memdb.get("blocked:pending:watch:nvidia/interns") is None   # and its jobs aren't judged


def test_a_timeout_through_the_real_workday_adapter_counts_as_a_failed_read(make_cfg, memdb, monkeypatch):
    from internwatch.adapters import get_checker
    monkeypatch.setattr(watch, "get_checker", get_checker)
    c = company("ebay")
    cfg = cfg_of(make_cfg, [c], [{"company": "ebay", "name": "Workday", "checker": "workday", "settings": {
        "host": "ebay.wd5.myworkdayjobs.com", "tenant": "ebay", "site": "apply"}}])

    class Timeouts(Http):
        def post_json(self, url, **kw):
            raise CheckTimeout("timeout (ReadTimeout) for POST x (after 2 attempts)")
    watch.run(cfg, memdb, None, lambda deadline, **kw: Timeouts(), float("inf"), {"ebay"})
    assert json.loads(memdb.get("blocked:rate:watch:ebay/Workday"))[-1][1:] == [0, "failed"]


def test_no_time_at_all_reads_nothing(make_cfg, memdb, monkeypatch):
    *_, cfg = nvidia(make_cfg)
    calls = spy(monkeypatch)
    assert read(cfg, memdb, ["nvidia"], budget=0) == [] and calls == []


# reads that fail -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("error", [CheckTimeout("timeout (ReadTimeout) for GET x (after 2 attempts)"),
                                   FetchError("HTTP 503 for GET x (after 2 attempts)"), FetchError("HTTP 403 for GET x")])
def test_a_watched_board_that_fails_is_read_again_every_morning(make_cfg, memdb, monkeypatch, error):
    *_, cfg = nvidia(make_cfg)
    BOARDS["interns"] = error
    calls = spy(monkeypatch)
    for _ in range(5):
        calls.clear()
        read(cfg, memdb, ["nvidia"])
        assert "interns" in calls
        next_morning(memdb)


def test_a_weekly_full_read_that_fails_retries_the_next_morning(make_cfg, memdb, monkeypatch):
    *_, cfg = nvidia(make_cfg)
    BOARDS["whole"] = FetchError("HTTP 503 for GET x")
    calls = spy(monkeypatch)
    read(cfg, memdb, ["nvidia"])
    next_morning(memdb)
    calls.clear()
    read(cfg, memdb, ["nvidia"])
    assert "whole" in calls


def morning(cfg, db):
    read(cfg, db, ["nvidia"])
    problems = moves.finish(cfg, db, None, None, set())
    alerts.record(db, problems, [])
    alerts.sweep(cfg, db)
    return problems


def test_a_watched_board_goes_dark_on_the_third_missed_morning_and_clears(make_cfg, memdb, monkeypatch):
    days = iter(range(30))
    start = utcnow()
    monkeypatch.setattr(moves, "utcnow", lambda: start + timedelta(days=next(days)))
    *_, cfg = nvidia(make_cfg)
    real_ctx = moves.Ctx

    def ctx_on_day(*a, **k):
        return real_ctx(*a, now=start + timedelta(days=n["day"]), **k)
    n = {"day": 0}
    monkeypatch.setattr(moves, "Ctx", ctx_on_day)
    monkeypatch.setattr(watch.moves, "Ctx", ctx_on_day)
    BOARDS["interns"] = []
    assert morning(cfg, memdb) == []                                # it answers
    BOARDS["interns"] = FetchError("HTTP 503 for GET x")
    for n["day"] in (1, 2):
        assert morning(cfg, memdb) == []                            # two misses
    n["day"] = 3
    assert [p["kind"] for p in morning(cfg, memdb)] == ["check gone dark"]
    assert "Watched board interns" in alerts.for_email(memdb)[0][0]["summary"]
    BOARDS["interns"] = []
    n["day"] = 4
    assert morning(cfg, memdb) == []
    assert alerts.for_email(memdb)[0] == []


def test_a_weekly_full_read_keeps_14_days(make_cfg, memdb):
    *_, cfg = nvidia(make_cfg)
    moves.record(memdb, "watch-full", "nvidia/full", "ok", utcnow() - timedelta(days=10))
    moves.record(memdb, "watch-full", "nvidia/full", "failed", utcnow() - timedelta(days=3))
    memdb.set("blocked:mornings", json.dumps([(utcnow() - timedelta(days=d)).date().isoformat() for d in range(9, 0, -1)]))
    assert moves.dark(cfg, memdb, "watch-full", "nvidia/full", utcnow()) is None
    moves.record(memdb, "watch-full", "nvidia/full", "ok", utcnow() - timedelta(days=16))
    memdb.set("blocked:rate:watch-full:nvidia/full", json.dumps([[(utcnow() - timedelta(days=16)).date().isoformat(), 1]]))
    memdb.set("blocked:ok:watch-full:nvidia/full", (utcnow() - timedelta(days=16)).date().isoformat())
    assert moves.dark(cfg, memdb, "watch-full", "nvidia/full", utcnow())


# boards that can't be read -------------------------------------------------------------------------------------------

def test_a_board_robots_txt_always_forbade_is_named_and_never_goes_dark(make_cfg, memdb):
    c = company("uber")
    dismiss(memdb, c, "icims:portal=university-uber.icims.com")
    cfg = cfg_of(make_cfg, [c])
    BOARDS["https://university-uber.icims.com"] = RobotsBlocked("robots.txt disallows https://university-uber.icims.com/jobs")
    for _ in range(4):
        assert read(cfg, memdb, ["uber"]) == []
        assert moves.finish(cfg, memdb, None, None, set()) == []
        next_morning(memdb)
    conn = sqlite3.connect(":memory:")
    memdb.conn.backup(conn)
    conn.row_factory = sqlite3.Row
    assert "uber/icims:portal=university-uber.icims.com: robots.txt disallows" in watch.status(cfg, conn)


def test_a_board_that_used_to_answer_and_is_now_forbidden_counts_as_missed(make_cfg, memdb):
    *_, cfg = nvidia(make_cfg)
    read(cfg, memdb, ["nvidia"])
    BOARDS["interns"] = RobotsBlocked("robots.txt disallows x")
    next_morning(memdb)
    read(cfg, memdb, ["nvidia"])
    assert json.loads(memdb.get("blocked:rate:watch:nvidia/interns"))[-1][1:] == [0, "failed"]


def test_status_lists_each_board_and_the_ones_that_cant_be_read(make_cfg, memdb):
    *_, cfg = nvidia(make_cfg)
    cfg.settings.raw["liveness"]["watch_unreadable"] = [{"company": "sig", "board": "icims:x", "why": "robots.txt blocks it"}]
    read(cfg, memdb, ["nvidia"])
    conn = sqlite3.connect(":memory:")
    memdb.conn.backup(conn)
    conn.row_factory = sqlite3.Row
    text = watch.status(cfg, conn)
    assert "1 read every run, 2 weekly" in text
    assert "nvidia/full: last read 20" in text and "t-mobile/alumni: last read never (weekly)" in text or "(weekly)" in text
    assert "sig/icims:x: robots.txt blocks it" in text


def test_status_before_the_first_run(make_cfg):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE kv (key TEXT, value TEXT)")
    assert "boards watched" in watch.status(cfg_of(make_cfg, [company("acme")]), conn)


# which boards --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("system, url, expected", [
    ("greenhouse:board=drwfr", "", ("greenhouse", {"board": "drwfr"})),
    ("lever:site=voleon", "", ("lever", {"site": "voleon"})),
    ("ashby:board=mtesting.ai", "", ("ashby", {"board": "mtesting.ai"})),
    ("smartrecruiters:company=glean", "", ("smartrecruiters", {"company": "glean"})),
    ("icims:portal=university-uber.icims.com", "", ("icims", {"portal": "https://university-uber.icims.com"})),
    ("oracle:host=hdpc.fa.us2.oraclecloud.com,site=cx_1", "", ("oracle", {"host": "hdpc.fa.us2.oraclecloud.com", "site": "CX_1"})),
    ("workday:site=alumni,tenant=tmobile", "https://tmobile.wd1.myworkdayjobs.com/alumni",
     ("workday", {"host": "tmobile.wd1.myworkdayjobs.com", "tenant": "tmobile", "site": "alumni"})),
    ("workday:site=careers_gm,tenant=generalmotors", "https://generalmotors.wd5.myworkdayjobs.com/en-CA/Careers_GM/job/x",
     ("workday", {"host": "generalmotors.wd5.myworkdayjobs.com", "tenant": "generalmotors", "site": "Careers_GM"})),
    ("workday:site=bh,tenant=brevanhoward", "https://wd3.myworkdaysite.com/recruiting/brevanhoward/BH_External/job/x",
     ("workday", {"host": "wd3.myworkdaysite.com", "tenant": "brevanhoward", "site": "BH_External"})),
    ("workday:site=x,tenant=y", "", None),
    ("workday:site=x,tenant=y", "https://y.wd1.myworkdayjobs.com", None),
    ("ripplematch:company=hubspot", "https://app.ripplematch.com/company/hubspot", None),
])
def test_what_reads_a_dismissed_board(system, url, expected):
    assert watch.source_of(system, url) == expected


def test_the_real_settings_name_active_companies_and_adapters_that_exist(monkeypatch):
    from internwatch.adapters import get_checker
    from internwatch.config import load
    cfg = load()
    active = {c.key for c in cfg.active}
    boards = cfg.settings.get("liveness", "watch_boards")
    assert len({watch.moves.source_id(x) for x in boards}) == len(boards) == 11  # the 10 mirrors, NVIDIA twice
    for x in boards:
        assert x["company"] in active and get_checker(x["checker"])
    assert len(cfg.settings.get("liveness", "watch_unreadable")) == 6


def test_a_list_keeps_the_link_a_watched_board_needs(make_cfg, memdb):
    from conftest import company as make
    c = make("flow-traders", name="Flow Traders")
    cfg = make_cfg([c], liveness={"blocked": ["flow-traders"], "aliases": {}, "parallel_sources": [], "getro": [],
                                  "listings": [{"name": "speedy", "format": "markdown", "url": "https://l/x.md"}]})

    class List:
        calls = []

        def get(self, url, **kw):
            from internwatch.http import Resp
            body = "| Company | Role | Apply |\n|---|---|---|\n| Flow Traders | Quant Intern | " \
                   "[Apply](https://tmobile.wd1.myworkdayjobs.com/Alumni/job/x) |\n"
            return Resp(200, url, {}, body.encode())

        def close(self):
            pass
    problems = moves.check_listings(moves.Ctx(cfg, memdb, None, lambda d, **k: List(), float("inf"), set()))
    assert problems[0]["alerts"][0]["url"] == "https://tmobile.wd1.myworkdayjobs.com/Alumni/job/x"


# never at the cost of a poll or an email ---------------------------------------------------------------------------------

def run_morning(cfg, db):
    r = Runner(cfg, db=db, checker_fn=FakeChecker({"acme": [[job("1", "Software Engineer Intern (Summer 2027)")]]}))
    r.online = lambda: True
    return r.run(RunOptions(daily=True, retry_delay=0, crosscheck=False, send=False, scheduled_mail=False))


def test_a_bug_here_never_costs_the_morning_email(make_cfg, memdb, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bug")
    monkeypatch.setattr(watch, "run", boom)
    cfg = cfg_of(make_cfg, [company("acme")], parallel_sources=[], listings=[], getro=[])
    summary = run_morning(cfg, memdb)
    assert summary.checked == 1 and memdb.q("SELECT COUNT(*) n FROM runs WHERE finished_at IS NOT NULL")[0]["n"] == 1


def test_a_run_reads_the_boards_and_the_jobs_table_stays_as_it_was(make_cfg, memdb):
    c = company("acme")
    BOARDS["mirror"] = [job("m1", "Software Engineer Intern", "New York, NY")]
    cfg = cfg_of(make_cfg, [c], [{"company": "acme", "checker": "greenhouse", "settings": {"board": "mirror"}}],
                 parallel_sources=[], listings=[], getro=[])
    run_morning(cfg, memdb)
    assert [r["job_id"] for r in memdb.q("SELECT job_id FROM jobs")] == ["1"]  # read, never stored
    assert memdb.get("blocked:at:watch:acme/greenhouse:board=mirror")
    assert memdb.get("blocked:mornings")
