"""Checkers added in October 2026, replayed from their recorded fixtures with edited responses: Instabase's
careers-page watch, D. E. Shaw, IBM."""
import copy
import json

import pytest

from internwatch.adapters import get_checker
from internwatch.adapters.base import FetchContext
from internwatch.health import assess
from internwatch.checkers.ibm import COUNTRIES, place
from internwatch.http import Cassette, Http
from internwatch.locations import countries
from internwatch.models import ShapeError
from internwatch.runner import run_checker

from conftest import REPO, company


def cassette(key: str, edit=None) -> Cassette:
    """A recorded fixture, optionally after `edit(exchange)` changed some of its responses."""
    cas = Cassette.load(REPO / "tests" / "fixtures" / "cassettes" / f"{key}.json.gz")
    ex = copy.deepcopy(cas.exchanges)
    for e in ex:
        if edit:
            edit(e)
    return Cassette(exchanges=ex, meta=cas.meta)


def replay(key: str, edit=None, ctx=None, checker=None, settings=None):
    cas = cassette(key, edit)
    return get_checker(checker or cas.meta["checker"]).fetch(Http(replay=cas), settings or cas.meta["settings"], ctx)


# Instabase ----------------------------------------------------------------------------------

PAGE = "https://www.instabase.com/careers/jobs"


def on_page(change):
    def edit(e):
        if e["url"] == PAGE:
            change(e)
    return edit


def test_instabase_page_that_still_loads_its_board_is_quiet():
    ctx = FetchContext()
    assert replay("instabase", ctx=ctx) == [] and ctx.degraded is None
    assert replay("instabase") == []  # without a context too


def test_instabase_page_pointing_at_another_job_site_is_reported():
    def to_ashby(e):  # the script loads another job site; the leftover cards still link the old board
        e["text"] = e["text"].replace("https://boards-api.greenhouse.io/v1/boards/instabase",
                                      "https://api.ashbyhq.com/posting-api/job-board/instabase")
    ctx = FetchContext()
    assert replay("instabase", on_page(to_ashby), ctx=ctx) == []
    assert ctx.degraded == ("instabase: the careers page now points at ashby instabase, but InternWatch reads "
                            "greenhouse instabase: its jobs may have moved")


def test_instabase_page_without_its_board_is_reported():
    def drop_board(e):
        e["text"] = e["text"].replace("greenhouse.io/v1/boards/instabase", "example.com/v1/jobs") \
                             .replace("greenhouse.io/instabase", "example.com/jobs")
    ctx = FetchContext()
    assert replay("instabase", on_page(drop_board), ctx=ctx) == []
    assert ctx.degraded == ("instabase: the careers page no longer mentions greenhouse instabase: its jobs may "
                            "have moved")


def test_instabase_unreadable_page_alerts_only_after_two_checks_in_a_row(make_cfg, memdb):
    def down(e):
        e["status"] = 503
    c = company("instabase", checker="instabase", settings=cassette("instabase").meta["settings"])
    cfg = make_cfg([c])
    first = run_checker(cfg, c, replay=cassette("instabase", on_page(down)))
    assert first.ok and first.jobs == [] and "the careers page could not be read" in first.degraded
    assert assess(cfg, memdb, first).problem is None  # one bad check: no alert
    second = assess(cfg, memdb, run_checker(cfg, c, replay=cassette("instabase", on_page(down))))
    assert second.problem["kind"] == "shape" and "could not be read" in second.problem["detail"]
    assert assess(cfg, memdb, run_checker(cfg, c, replay=cassette("instabase"))).recovered


def test_instabase_board_back_with_jobs_is_read_like_the_plain_greenhouse_board():
    board = {"jobs": [{"id": 8123456002, "title": "Software Engineer Intern, Summer 2027",
                       "location": {"name": "New York, NY"},
                       "absolute_url": "https://job-boards.greenhouse.io/instabase/jobs/8123456002",
                       "first_published": "2026-11-02T10:00:00-05:00", "metadata": None}],
             "meta": {"total": 1}}

    def back(e):
        if "boards-api.greenhouse.io" in e["url"]:
            e["status"], e["text"] = 200, json.dumps(board)
    ctx = FetchContext()
    jobs = replay("instabase", back, ctx=ctx)
    plain = replay("instabase", back, checker="greenhouse", settings={"board": "instabase", "missing_ok": True})
    assert [j.to_dict() for j in jobs] == [j.to_dict() for j in plain]
    assert [(j.id, j.title) for j in jobs] == [("8123456002", "Software Engineer Intern, Summer 2027")]
    assert ctx.degraded is None and ctx.state["boards_ok"] == ["instabase"]


# D. E. Shaw ---------------------------------------------------------------------------------

def test_deshaw_reads_both_listed_lists_and_not_the_internal_postings():
    jobs = replay("de-shaw")
    assert len(jobs) == len({j.id for j in jobs}) == 105
    assert sum(j.extra["list"] == "internships" for j in jobs) == 12
    assert not [j for j in jobs if "FinOp Intern" in j.title]  # internal-only: not on the page
    j = next(j for j in jobs if j.id == "5894")
    assert (j.title, j.location, j.employment_type, j.department) == (
        "Software Developer Intern (New York) – Summer 2027", "New York", "Intern", "Software Development")
    assert j.url == "https://www.deshaw.com/careers/software-developer-intern-new-york-summer-2027-5894"
    assert "2027" in j.snippet and all(x.url == x.url.lower() for x in jobs)


@pytest.mark.parametrize("old, new", [('"jobsFetchingError":false', '"jobsFetchingError":true'),
                                      ('id="__NEXT_DATA__"', 'id="__NEXT_DATA_GONE__"')])
def test_deshaw_page_that_could_not_load_its_jobs_fails_instead_of_reading_zero(old, new):
    def edit(e):
        e["text"] = e["text"].replace(old, new)
    with pytest.raises(ShapeError):
        replay("de-shaw", edit, ctx=FetchContext())


# IBM ----------------------------------------------------------------------------------------

def test_ibm_reads_every_page_of_the_whole_site():
    jobs = replay("ibm")
    assert len(jobs) == len({j.id for j in jobs}) == cassette("ibm").meta["count"] > 2000
    j = next(j for j in jobs if j.id == "134708")
    assert (j.title, j.location, j.employment_type) == ("2027 Software Developer Intern", "POUGHKEEPSIE, United States",
                                                        "Internship")
    assert j.url == "https://careers.ibm.com/careers/JobDetail?jobId=134708"


def test_ibm_walk_cut_short_fails_instead_of_hiding_jobs():
    def middle_page_empty(e):
        if json.loads(e["body"])["from"] == 1000:
            data = json.loads(e["text"])
            data["hits"]["hits"] = []
            e["text"] = json.dumps(data)
    with pytest.raises(ShapeError, match="pagination incomplete"):
        replay("ibm", middle_page_empty, ctx=FetchContext())


@pytest.mark.parametrize("raw, shown, country", [
    ("Ehningen, DE", "Ehningen, Germany", {"DE"}), ("Bangalore, IN", "Bangalore, India", {"IN"}),
    ("Bogota, CO", "Bogota, Colombia", {"CO"}), ("Jakarta, ID", "Jakarta, Indonesia", {"ID"}),
    ("Markham, CA", "Markham, Canada", {"CA"}), ("POUGHKEEPSIE, US", "POUGHKEEPSIE, United States", {"US"}),
    ("SÃ£o Paulo, BR", "São Paulo, Brazil", {"BR"}), ("Multiple Cities", "Multiple Cities", set())])
def test_ibm_country_codes_are_written_out_so_they_never_read_as_us_states(raw, shown, country):
    assert place(raw) == shown and set(countries(shown)[0]) == country


def test_every_ibm_country_name_reads_as_that_country():
    wrong = {cc: name for cc, name in COUNTRIES.items()
             if set(countries(f"Somewhere, {name}")[0]) != ({"US"} if cc in ("US", "PR") else {cc})}
    assert not wrong
