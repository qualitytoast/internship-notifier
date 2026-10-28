"""Fixes for the boards found incomplete in the October 2026 audit: a twin Greenhouse board, postings left out of a
company's own list while they still take applications (Ashby unlisted, Oracle delisted), Jane Street's program
sessions, program pages that say when applications open, and posting ids learned from SimplifyJobs."""
import json

import pytest

from internwatch.adapters import get_checker
from internwatch.adapters.base import FetchContext
from internwatch.checkers.janestreet_programs import URL as JS_URL
from internwatch.db import DB, iso
from internwatch.http import Cassette, Resp
from internwatch.models import FetchError
from internwatch.runner import Runner

from conftest import FakeChecker, company


class FakeHttp:
    """Answers from a dict: url → JSON-able value, text, Resp or an exception to raise."""

    def __init__(self, answers: dict, replay=None):
        self.answers = answers
        self.replay = replay
        self.asked: list[str] = []

    def _get(self, url, params=None):
        key = url + ("?" + json.dumps(params, sort_keys=True) if params else "")
        self.asked.append(key)
        a = self.answers.get(key, self.answers.get(url))
        if isinstance(a, Exception):
            raise a
        return a

    def get(self, url, params=None, ok_statuses=(), **kw):
        a = self._get(url, params)
        if isinstance(a, Resp):
            return a
        body = a if isinstance(a, str) else json.dumps(a)
        return Resp(200, url, {}, body.encode())

    def get_json(self, url, params=None, **kw):
        return self.get(url, params).json()

    def get_text(self, url, **kw):
        return self.get(url).text


# Greenhouse: dedupe_requisitions: across_boards ----------------------------------------------

def _gh_board(*rows):
    return {"jobs": [{"id": i, "title": t, "location": {"name": loc}, "requisition_id": req,
                      "absolute_url": f"https://x/{i}"} for i, t, loc, req in rows], "meta": {"total": len(rows)}}


GH = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"
TWIN_BOARDS = {GH.format("main"): _gh_board((1, "Software Engineer Intern", "New York, NY", "R1"),
                                             (2, "Software Engineer Intern", "New York, NY", "R1"),
                                             (3, "Data Scientist, Intern", "Pittsburgh, PA", "R2")),
               GH.format("uni"): _gh_board((11, "Software Engineer Intern", "New York, NY", "R1"),
                                            (12, "Product Manager, Intern", "Pittsburgh, PA", "R3"))}


def test_greenhouse_across_boards_drops_only_twins_of_an_earlier_board():
    s = {"boards": ["main", "uni"], "dedupe_requisitions": "across_boards"}
    ids = [j.id for j in get_checker("greenhouse").fetch(FakeHttp(TWIN_BOARDS), s, FetchContext())]
    assert ids == ["1", "2", "3", "12"]  # both copies on the first board kept, its twin on the second dropped


def test_greenhouse_dedupe_requisitions_true_is_unchanged():
    s = {"boards": ["main", "uni"], "dedupe_requisitions": True}
    ids = [j.id for j in get_checker("greenhouse").fetch(FakeHttp(TWIN_BOARDS), s, FetchContext())]
    assert ids == ["1", "3", "12"]


# Ashby: watch_ids ------------------------------------------------------------------------

ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=false"


def _ashby_page(posting) -> str:
    return f"<html><script>window.__appData = {json.dumps({'posting': posting})};</script></html>"


def test_ashby_watched_postings_open_closed_and_failing():
    listed = {"jobs": [{"id": "listed-1", "title": "Software Engineer", "location": "SF"}]}
    open_p = {"id": "u-1", "title": "Embedded Engineer Intern", "locationName": "Mountain View, CA",
              "secondaryLocationNames": ["Bozeman, MT"], "employmentType": "Intern", "isListed": False,
              "departmentName": "Hardware", "descriptionHtml": "<p>Summer 2027</p>"}
    http = FakeHttp({ASHBY_API: listed,
                     "https://jobs.ashbyhq.com/acme/u-1": _ashby_page(open_p),
                     "https://jobs.ashbyhq.com/acme/u-2": Resp(404, "x", {}, b"not found"),
                     "https://jobs.ashbyhq.com/acme/u-3": _ashby_page(None),
                     "https://jobs.ashbyhq.com/acme/u-4": FetchError("HTTP 503")})
    ctx = FetchContext()
    jobs = get_checker("ashby").fetch(http, {"board": "acme", "watch_ids": ["u-1", "u-2", "u-3", "u-4", "listed-1"]}, ctx)
    assert [j.id for j in jobs] == ["listed-1", "u-1"]
    u1 = jobs[1]
    assert (u1.title, u1.location, u1.employment_type, u1.extra) == (
        "Embedded Engineer Intern", "Mountain View, CA; Bozeman, MT", "Intern", {"unlisted": True})
    assert u1.url == "https://jobs.ashbyhq.com/acme/u-1" and "Summer 2027" in u1.snippet
    assert ctx.state["watch_open"] == ["u-1"] and ctx.state["watch_closed"] == ["u-2", "u-3"]
    assert "watched posting u-4" in ctx.degraded  # a failed read is reported, never taken as closed
    assert "https://jobs.ashbyhq.com/acme/listed-1" not in http.asked  # listed ids are not read again


def test_ashby_without_watch_ids_reads_only_the_board():
    http = FakeHttp({ASHBY_API: {"jobs": [{"id": "a", "title": "Intern", "isListed": False}]}})
    ctx = FetchContext()
    assert get_checker("ashby").fetch(http, {"board": "acme"}, ctx) == [] and ctx.state == {}
    assert http.asked == [ASHBY_API]


# Oracle: watch_ids -----------------------------------------------------------------------

ORA = "https://h/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
ORA_D = "https://h/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"


def _details_params(jid):
    return {"expand": "all", "onlyData": "true", "finder": f"ById;Id=\"{jid}\",siteNumber=CX_1"}


def test_oracle_watched_requisitions():
    search = {"items": [{"TotalJobsCount": 1, "requisitionList": [{"Id": "10", "Title": "Engineer"}]}]}
    delisted = {"Id": "20", "Title": "IT Undergraduate Intern", "PrimaryLocation": "TX, United States",
                "ExternalPostedStartDate": None, "ApplyWhenNotPostedFlag": "True", "RequisitionType": "Intern",
                "ExternalDescriptionStr": "<p>Summer 2027</p>", "secondaryLocations": [{"Name": "Austin, TX"}]}
    not_applyable = {**delisted, "Id": "21", "ApplyWhenNotPostedFlag": "False"}
    answers = {ORA: search,
               ORA_D + "?" + json.dumps(_details_params("20"), sort_keys=True): {"items": [delisted]},
               ORA_D + "?" + json.dumps(_details_params("21"), sort_keys=True): {"items": [not_applyable]},
               ORA_D + "?" + json.dumps(_details_params("22"), sort_keys=True): {"items": []},
               ORA_D + "?" + json.dumps(_details_params("23"), sort_keys=True): FetchError("HTTP 500")}
    ctx = FetchContext()
    s = {"host": "h", "site": "CX_1", "watch_ids": [20, "21", "22", "23", "10"]}
    jobs = get_checker("oracle").fetch(FakeHttp(answers), s, ctx)
    assert [j.id for j in jobs] == ["10", "20"]
    j = jobs[1]
    assert (j.title, j.location, j.employment_type, j.extra) == (
        "IT Undergraduate Intern", "TX, United States; Austin, TX", "Intern", {"unlisted": True})
    assert j.url == "https://h/hcmUI/CandidateExperience/en/sites/CX_1/job/20" and "Summer 2027" in j.snippet
    assert ctx.state["watch_open"] == ["20"] and ctx.state["watch_closed"] == ["21", "22"]
    assert "watched requisition 23" in ctx.degraded


# Jane Street programs --------------------------------------------------------------------

PROGRAMS = [
    {"name": "FTTP", "sessions": [
        {"id": "fttp-nyc", "office": "NYC", "dates": "March 21st - March 25th, 2027", "apply_page": "/apply-fttp-nyc",
         "deadline": "2027-01-31T23:59:59-05:00", "formatted_deadline": "January 31st, 2027"},
        {"id": "fttp-hkg", "office": "HKG", "dates": "Sep 30 - Oct 3, 2026", "apply_page": "/apply-fttp-hkg",
         "deadline": "2026-08-23T23:59:59+08:00"}]},
    {"name": "AMP", "sessions": [{"id": "amp", "office": "NYC", "apply_page": "/apply-amp", "preuniversity": True,
                                  "deadline": "2027-03-11T23:59:59-04:00"}]},
    {"name": "SF Happy Hour", "sessions": [{"id": "sf-happy-hour", "office": "SF"}]},
]


def test_janestreet_programs_keep_open_sessions_only():
    replayed = Cassette(meta={"recorded_at": "2026-10-27T23:00:00Z"})
    jobs = get_checker("janestreet_programs").fetch(FakeHttp({JS_URL: PROGRAMS}, replay=replayed), {})
    assert [(j.id, j.title, j.location, j.url) for j in jobs] == [
        ("fttp-nyc:2027-01-31", "FTTP program (NYC): March 21st - March 25th, 2027", "New York, NY",
         "https://www.janestreet.com/apply-fttp-nyc")]
    assert jobs[0].snippet.startswith("Apply by January 31st, 2027")


def test_janestreet_programs_judge_deadlines_as_of_the_recording():
    later = Cassette(meta={"recorded_at": "2027-02-01T12:00:00Z"})  # after FTTP NYC's deadline
    assert get_checker("janestreet_programs").fetch(FakeHttp({JS_URL: PROGRAMS}, replay=later), {}) == []


# program pages ---------------------------------------------------------------------------

PAGE = "https://example.com/programs/possibilities-series"
SETTINGS = {"pages": [{"url": PAGE, "title": "Possibilities Series", "location": "United States"}]}


def _program_page(application: str, eligibility: str = "First-year students graduating May 2029") -> str:
    return (f"<html><script>var x = 'Applications are now closed';</script><h2>Possibilities</h2>"
            f"<h4>APPLICATION DETAILS</h4><p>{application}</p><h4>ELIGIBILITY</h4><p>{eligibility}</p>"
            f"<h4>LOCATION</h4><p>New York</p></html>")


def test_program_page_closed_then_open_with_a_stable_id():
    checker = get_checker("program_pages")
    assert checker.fetch(FakeHttp({PAGE: _program_page("Applications are now closed.")}), SETTINGS, FetchContext()) == []
    opened = checker.fetch(FakeHttp({PAGE: _program_page("Apply by March 1, 2027.")}), SETTINGS, FetchContext())
    extended = checker.fetch(FakeHttp({PAGE: _program_page("Apply by March 15, 2027.")}), SETTINGS, FetchContext())
    next_year = checker.fetch(FakeHttp({PAGE: _program_page("Apply by March 1, 2028.", "graduating May 2030")}),
                              SETTINGS, FetchContext())
    assert [j.title for j in opened] == ["Possibilities Series (applications open)"]
    assert opened[0].id == extended[0].id != next_year[0].id  # an edited deadline is not a new opening


def test_program_page_that_changed_is_reported():
    two = {"pages": SETTINGS["pages"] + [{"url": PAGE + "-2", "title": "Other", "location": "United States"}]}
    ctx = FetchContext()
    got = get_checker("program_pages").fetch(
        FakeHttp({PAGE: "<html>new layout</html>", PAGE + "-2": _program_page("Applications are now closed.")}), two, ctx)
    assert got == [] and "no 'APPLICATION DETAILS'" in ctx.degraded
    with pytest.raises(Exception, match="APPLICATION DETAILS"):
        get_checker("program_pages").fetch(FakeHttp({PAGE: "<html>new layout</html>"}), SETTINGS, FetchContext())


# learn_ids: posting ids from SimplifyJobs rows ---------------------------------------------

def _row(db, key, url, last_seen, company_key="dell"):
    db.conn.execute("INSERT INTO simplify_rows(source, row_key, company, title, url, first_seen, last_seen, "
                    "tracked_company, status) VALUES('summer', ?, 'Dell', 'Intern', ?, ?, ?, ?, 'baseline')",
                    (key, url, last_seen, last_seen, company_key))


def test_learned_ids_come_from_the_latest_download_and_skip_closed(make_cfg):
    dell = company("dell", checker="oracle",
                   settings={"host": "h", "site": "CX_1", "learn_ids": True, "watch_ids": ["1"]})
    other = company("acme", checker="oracle", settings={"host": "h2", "site": "CX_1"})
    cfg = make_cfg([dell, other])
    db = DB(cfg.settings.path("db"))
    now, before = iso(), "2026-10-01T00:00:00Z"
    db.set("simplify_baselined:summer", now)
    _row(db, "a", "https://iawmqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/careers/job/2", now)
    _row(db, "b", "https://iawmqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/careers/job/3", before)
    _row(db, "c", "https://x/job/4", now)
    _row(db, "d", "https://x/job/5", now, company_key="acme")
    db.set("ckstate:dell", json.dumps({"watch_open": ["9"], "watch_closed": ["4"]}))
    r = Runner(cfg, db=db, checker_fn=FakeChecker({}))
    assert r._with_learned_ids(dell).settings["watch_ids"] == ["1", "9", "2"]  # 3: no longer listed; 4: closed
    assert r._with_learned_ids(other) is other  # companies without learn_ids are passed through unchanged
