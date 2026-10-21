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
