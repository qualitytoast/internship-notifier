"""Regression tests for the adapter gaps found in the coverage audit: a failing or vanished board, a partly read
listing, a capped Workday partition, a malformed posting. Each must keep the jobs that were read and mark the poll
degraded (reported as a health problem, no removals recorded) instead of hiding everything or nothing being noticed."""
import copy
import json

import pytest

from internwatch.adapters import get_checker
from internwatch.adapters.base import FetchContext
from internwatch.http import Cassette, Http
from internwatch.models import CheckerError, FetchError

from conftest import REPO


def cassette(key: str) -> Cassette:
    return Cassette.load(REPO / "tests" / "fixtures" / "cassettes" / f"{key}.json.gz")


def replay(key: str, edit=None, settings=None, ctx=None):
    """Replay a recorded fixture, optionally after `edit(exchange)` changed some of its responses."""
    cas = cassette(key)
    ex = copy.deepcopy(cas.exchanges)
    for e in ex:
        if edit:
            edit(e)
    checker = get_checker(cas.meta["checker"])
    return checker.fetch(Http(replay=Cassette(exchanges=ex)), settings or cas.meta["settings"], ctx)


def gone(*suffixes):
    """An edit that makes the responses for URLs ending in one of `suffixes` answer 404."""
    def edit(e):
        if e["url"].endswith(suffixes):
            e["status"], e["text"] = 404, '{"status":404,"error":"Not found"}'
    return edit


# Greenhouse ---------------------------------------------------------------------------------

def test_greenhouse_missing_ok_board_that_answered_before_and_vanishes_is_reported():
    ctx = FetchContext()
    jobs = replay("klaviyo", ctx=ctx)
    assert ctx.state["boards_ok"] == ["klaviyo", "klaviyocampus"] and not ctx.degraded
    campus = sum(1 for j in jobs if j.extra["board"] == "klaviyocampus")
    ctx2 = FetchContext(state=ctx.state)
    after = replay("klaviyo", gone("/boards/klaviyocampus/jobs"), ctx=ctx2)
    assert len(after) == len(jobs) - campus > 0
    assert ctx2.degraded == "greenhouse:klaviyocampus answered 404 (it answered before)"
    assert ctx2.state["boards_ok"] == ["klaviyo", "klaviyocampus"]  # still expected back: reported every poll


def test_greenhouse_missing_ok_board_never_seen_stays_silent():
    ctx = FetchContext()
    assert replay("instabase", ctx=ctx) == [] and ctx.degraded is None
    ctx = FetchContext()
    replay("klaviyo", gone("/boards/klaviyocampus/jobs"), ctx=ctx)
    assert ctx.degraded is None and ctx.state["boards_ok"] == ["klaviyo"]
    assert replay("klaviyo", gone("/boards/klaviyocampus/jobs")) and replay("instabase") == []  # no context: as before


def test_greenhouse_one_failing_board_keeps_the_other_boards_jobs():
    full = replay("robinhood")
    ctx = FetchContext()
    jobs = replay("robinhood", gone("/boards/sherwoodmedia/jobs"), ctx=ctx)
    assert {j.id for j in jobs} == {j.id for j in full if j.extra["board"] == "robinhood"}
    assert "HTTP 404" in ctx.degraded and "sherwoodmedia" in ctx.degraded
    with pytest.raises(FetchError):  # without a context it fails as before
        replay("robinhood", gone("/boards/sherwoodmedia/jobs"))
    with pytest.raises(FetchError):  # every board failing still fails the check
        replay("robinhood", gone("/boards/sherwoodmedia/jobs", "/boards/robinhood/jobs"), ctx=FetchContext())


def test_greenhouse_board_with_a_bad_response_keeps_the_others():
    def bad(e):
        if e["url"].endswith("/boards/samsaradach/jobs"):
            e["text"] = '{"unexpected": true}'
    ctx = FetchContext()
    jobs = replay("samsara", bad, ctx=ctx)
    assert jobs and all(j.extra["board"] == "samsara" for j in jobs)
    assert "greenhouse:samsaradach" in ctx.degraded


def _c3_twin(title: str, location: str):
    """An edit that lists, just before C3 AI's real 'Software Engineer - Intern (Summer 2027)' (req 1400), a posting
    with the same requisition id but `title` and `location`."""
    def edit(e):
        if e["url"].endswith("/boards/c3iot/jobs"):
            d = json.loads(e["text"])
            real = next(j for j in d["jobs"] if j.get("requisition_id") == "1400")
            d["jobs"].insert(d["jobs"].index(real), dict(real, id=1, title=title, location={"name": location}))
            d["meta"]["total"] += 1
            e["text"] = json.dumps(d)
    return edit


@pytest.mark.parametrize("title, location", [
    ("Software Engineer - Intern (Summer 2026)", "Redwood City, California, United States"),  # an older term
    ("Software Engineer - Intern (Summer 2027)", "Guadalajara, Jalisco, Mexico"),             # a copy abroad
])
def test_greenhouse_requisition_twin_with_another_title_or_place_is_kept(title, location):
    ids = {j.id for j in replay("c3-ai", _c3_twin(title, location))}
    assert {"1", "8739037002"} <= ids  # the twin no longer hides the real Summer 2027 Redwood City posting
    assert "8739036002" not in ids     # c3ascend's copy of it (same title, "Redwood City, CA ") is still one posting


def test_greenhouse_requisition_twin_with_same_title_and_place_is_dropped():
    ids = {j.id for j in replay("c3-ai", _c3_twin("Software Engineer  - Intern (Summer 2027)", "Redwood City, CA"))}
    assert "1" in ids and "8739037002" not in ids  # the first one wins, as before
    assert len(replay("c3-ai")) == cassette("c3-ai").meta["count"]


def test_greenhouse_employment_type_reads_every_matching_metadata_field():
    from internwatch.adapters.greenhouse import _employment_type
    meta = [{"name": "Time Type", "value": "Full time"}, {"name": "Early Career Time Type", "value": "Internship"},
            {"name": "Worker Sub-Type", "value": "Intern"}, {"name": "Job Level", "value": ["Intern", "5"]},
            {"name": "Employment Type", "value": "Full time"}, {"name": "Job Family", "value": None},
            {"name": "Location Type", "value": "Hybrid"}]
    assert _employment_type(meta) == "Full time, Internship, Intern, 5"
    assert _employment_type(None) == "" and _employment_type([{"name": "Job Type", "value": None}]) == ""
    types = [j.employment_type for j in replay("datadog")]
    assert types.count("Full time, Internship") == 8  # was just "Full time"


# Ashby --------------------------------------------------------------------------------------

def test_ashby_one_failing_board_keeps_the_other_boards_jobs():
    full = replay("sierra")
    ctx = FetchContext()
    jobs = replay("sierra", gone("/job-board/sierra-jp?includeCompensation=false"), ctx=ctx)
    assert 0 < len(jobs) < len(full) and "sierra-jp" in ctx.degraded
    with pytest.raises(FetchError):
        replay("sierra", gone("/job-board/sierra-jp?includeCompensation=false"))
    with pytest.raises(CheckerError):
        replay("sierra", gone("/job-board/sierra-jp?includeCompensation=false",
                              "/job-board/Sierra?includeCompensation=false"), ctx=FetchContext())


# SmartRecruiters ----------------------------------------------------------------------------

def blank(*parts):
    """An edit that empties the responses whose URL contains one of `parts` (a 200 page with nothing on it)."""
    def edit(e):
        if any(p in e["url"] for p in parts):
            e["text"] = "<div></div>"
    return edit


def test_smartrecruiters_group_page_without_groups_is_reported():
    ctx = FetchContext()
    jobs = replay("servicenow", blank("/ServiceNow/api/groups?page=11"), ctx=ctx)
    assert 0 < len(jobs) < cassette("servicenow").meta["count"]
    assert "group page 11 has no groups" in ctx.degraded
    assert "collected 515 postings but the search reports 668" in ctx.degraded
    assert len(replay("servicenow", blank("/ServiceNow/api/groups?page=11"))) == len(jobs)  # no context: as before


@pytest.mark.parametrize("page, kept", [(4, 670), (2, 650)])
def test_smartrecruiters_more_pages_that_run_dry_are_reported_and_jobs_kept(page, kept):
    ctx = FetchContext()
    jobs = replay("servicenow", blank(f"/ServiceNow/api/more?page={page}&type=location&value=San+Diego"), ctx=ctx)
    assert len(jobs) == kept and "group 'San Diego, CALIFORNIA' ended at" in ctx.degraded
    if page == 2:  # more than the 3% the groups' data-qty allows: still kept, and reported
        assert "collected 650 postings but the page lists 679" in ctx.degraded
        with pytest.raises(CheckerError):  # no context: fails as before
            replay("servicenow", blank("/ServiceNow/api/more?page=2&type=location&value=San+Diego"))


def test_smartrecruiters_search_total_far_above_collected_is_reported():
    def inflate(e):
        if "/sr-jobs/search" in e["url"]:
            e["text"] = json.dumps(dict(json.loads(e["text"]), totalFound=1000))
    ctx = FetchContext()
    assert len(replay("servicenow", inflate, ctx=ctx)) == 679
    assert ctx.degraded == "smartrecruiters:ServiceNow: collected 679 postings but the search reports 1000"
    for key in ("servicenow", "linkedin"):  # the recorded polls collect more than totalFound: healthy
        ctx = FetchContext()
        assert len(replay(key, ctx=ctx)) == cassette(key).meta["count"] and ctx.degraded is None


# Avature ------------------------------------------------------------------------------------

EA_TOTAL = r'aria-label="(\d+) results"'


def ea(**extra) -> dict:
    return {**cassette("electronic-arts").meta["settings"], **extra}


def test_avature_ea_total_regex_reads_the_portal_total():
    ctx = FetchContext()
    jobs = replay("electronic-arts", settings=ea(total_regex=EA_TOTAL), ctx=ctx)
    assert len(jobs) == cassette("electronic-arts").meta["count"] == ctx.reported_total == 364
    assert ctx.degraded is None


def test_avature_short_walk_is_reported_and_its_jobs_kept():
    def short_page(e):  # one card fewer on page 3 ends the walk there
        if e["url"].endswith("jobOffset=40&jobRecordsPerPage=20"):
            i = e["text"].find('<article class="article article--result')
            e["text"] = e["text"][:i] + e["text"][e["text"].find('<article class="article article--result', i + 10):]
    ctx = FetchContext()
    jobs = replay("electronic-arts", short_page, settings=ea(total_regex=EA_TOTAL), ctx=ctx)
    assert len(jobs) == 59 and "collected 59 jobs but the source reports 364" in ctx.degraded
    with pytest.raises(CheckerError):  # no context: fails as before
        replay("electronic-arts", short_page, settings=ea(total_regex=EA_TOTAL))


def test_avature_total_missing_from_the_page_is_reported_and_jobs_kept():
    ctx = FetchContext()
    jobs = replay("electronic-arts", settings=ea(total_regex=r'data-total="(\d+)"'), ctx=ctx)
    assert len(jobs) == 364 and "total not found on the page" in ctx.degraded
    with pytest.raises(CheckerError):
        replay("electronic-arts", settings=ea(total_regex=r'data-total="(\d+)"'))
