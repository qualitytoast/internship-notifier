"""Regression tests for the adapter gaps found in the coverage audit: a failing or vanished board, a partly read
listing, a capped Workday partition, a malformed posting. Each must keep the jobs that were read and mark the poll
degraded (reported as a health problem, no removals recorded) instead of hiding everything or nothing being noticed."""
import collections
import copy
import json
import re

import pytest

from internwatch.adapters import get_checker
from internwatch.adapters.base import FetchContext
from internwatch.http import Cassette, Http, canonical_url
from internwatch.models import CheckerError, CheckTimeout, FetchError

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
# klaviyo-greenhouse: Klaviyo's two Greenhouse boards as recorded on 20 Oct 2026, 8 roles on the campus board (Klaviyo
# itself is read with its Ashby board too since 10 Nov 2026, when its campus board was empty)

def test_greenhouse_missing_ok_board_that_answered_before_and_vanishes_is_reported():
    ctx = FetchContext()
    jobs = replay("klaviyo-greenhouse", ctx=ctx)
    assert ctx.state["boards_ok"] == ["klaviyo", "klaviyocampus"] and not ctx.degraded
    campus = sum(1 for j in jobs if j.extra["board"] == "klaviyocampus")
    ctx2 = FetchContext(state=ctx.state)
    after = replay("klaviyo-greenhouse", gone("/boards/klaviyocampus/jobs"), ctx=ctx2)
    assert len(after) == len(jobs) - campus > 0
    assert ctx2.degraded == "greenhouse:klaviyocampus answered 404 (it answered before)"
    assert ctx2.state["boards_ok"] == ["klaviyo", "klaviyocampus"]  # still expected back: reported every poll


def test_greenhouse_missing_ok_board_never_seen_stays_silent():
    ctx = FetchContext()
    assert replay("instabase", ctx=ctx) == [] and ctx.degraded is None
    ctx = FetchContext()
    replay("klaviyo-greenhouse", gone("/boards/klaviyocampus/jobs"), ctx=ctx)
    assert ctx.degraded is None and ctx.state["boards_ok"] == ["klaviyo"]
    assert replay("klaviyo-greenhouse", gone("/boards/klaviyocampus/jobs")) and replay("instabase") == []  # no context: as before


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
    assert len(jobs) == cassette("electronic-arts").meta["count"] == ctx.reported_total
    assert ctx.degraded is None


def test_avature_short_walk_is_reported_and_its_jobs_kept():
    def short_page(e):  # one card fewer on page 3 ends the walk there
        if e["url"].endswith("jobOffset=40&jobRecordsPerPage=20"):
            i = e["text"].find('<article class="article article--result')
            e["text"] = e["text"][:i] + e["text"][e["text"].find('<article class="article article--result', i + 10):]
    ctx = FetchContext()
    jobs = replay("electronic-arts", short_page, settings=ea(total_regex=EA_TOTAL), ctx=ctx)
    total = cassette("electronic-arts").meta["count"]
    assert len(jobs) == 59 and f"collected 59 jobs but the source reports {total}" in ctx.degraded
    with pytest.raises(CheckerError):  # no context: fails as before
        replay("electronic-arts", short_page, settings=ea(total_regex=EA_TOTAL))


BLOOMBERG_LIST = "https://bloomberg.avature.net/careers/SearchJobs/"
BY_TITLE = {"jobSort": "schemaField_3_270_3", "jobSortDirection": "ASC"}
CARD = re.compile(r'<article class="article article--result".*?</article>', re.S)
JOB_ID = re.compile(r"/JobDetail/[^/]+/(\d+)")


def bloomberg(**extra) -> dict:
    return {k: v for k, v in {**cassette("bloomberg").meta["settings"], **extra}.items() if v is not None}


def walks() -> tuple[list[dict], list[dict]]:
    """The recorded read (Nov 9, 2026): Bloomberg's newest-first walk showed 330 cards but only 310 jobs (20 cards
    showed twice and 20 jobs on no page), so the reader walked again by title (second_order) and found all 330.
    Returns (the newest-first pages, the title-sorted pages)."""
    ex = cassette("bloomberg").exchanges
    return [e for e in ex if "jobSort" not in e["url"]], [e for e in ex if "jobSort" in e["url"]]


def ids(exchanges) -> set[str]:
    return {JOB_ID.search(c).group(1) for e in exchanges for c in CARD.findall(e.get("text") or "")}


def by_title(skip=()) -> list[dict]:
    """The title-sorted walk without the jobs in `skip`, 12 a page, as the portal's Job Title sort would serve it."""
    cards = [c for e in walks()[1] for c in CARD.findall(e["text"]) if JOB_ID.search(c).group(1) not in skip]
    return [{"method": "GET", "url": canonical_url(BLOOMBERG_LIST, {**BY_TITLE, **({"jobOffset": i} if i else {})}),
             "body": "", "status": 200, "headers": {"content-type": "text/html;charset=UTF-8"},
             "text": "".join(cards[i:i + 12])} for i in range(0, len(cards) + 1, 12)]


def bloomberg_replay(exchanges, settings, ctx=None):
    return get_checker("avature").fetch(Http(replay=Cassette(exchanges=copy.deepcopy(exchanges))), settings, ctx)


def test_avature_second_order_finds_the_jobs_a_shuffled_walk_hid():
    newest, titled = walks()
    hidden, total = ids(titled) - ids(newest), cassette("bloomberg").meta["count"]
    assert len(hidden) == 20 and len(ids(newest)) == total - 20
    ctx = FetchContext()
    old = bloomberg_replay(newest, bloomberg(second_order=None), ctx)  # without the setting: short, and reported
    assert len(old) == total - 20 and not hidden & {j.id for j in old}
    assert f"collected {total - 20} jobs but the source reports {total}" in ctx.degraded
    ctx = FetchContext()
    jobs = bloomberg_replay(newest + titled, bloomberg(), ctx)
    assert len(jobs) == len({j.id for j in jobs}) == total and hidden <= {j.id for j in jobs}
    assert ctx.degraded is None and not ctx.partial
    first = {j.id: j for j in old}
    assert all((j.title, j.location, j.url) == (first[j.id].title, first[j.id].location, first[j.id].url)
               for j in jobs if j.id in first)  # the same cards, so no stored job looks edited


def test_avature_complete_walk_never_takes_the_second_order():
    # every job once on the newest-first pages (the title-sorted cards in their place), and no title-sorted page
    # recorded: a second walk would fail on its first request
    newest, titled = walks()
    cards = [c for e in titled for c in CARD.findall(e["text"])]
    complete, n = [], 0
    for e in newest:
        page = CARD.findall(e.get("text") or "")
        if not page:  # not a list page
            complete.append(e)
            continue
        start, end = e["text"].find(page[0]), e["text"].rfind(page[-1]) + len(page[-1])
        complete.append({**e, "text": e["text"][:start] + "".join(cards[n:n + len(page)]) + e["text"][end:]})
        n += len(page)
    ctx = FetchContext()
    jobs = bloomberg_replay(complete, bloomberg(), ctx)
    assert len(jobs) == cassette("bloomberg").meta["count"] and ctx.degraded is None


def test_avature_still_short_after_both_orders_is_reported_and_jobs_kept():
    newest, titled = walks()
    gone = sorted(ids(titled) - ids(newest))[:6]
    ctx = FetchContext()
    jobs = bloomberg_replay(newest + by_title(skip=gone), bloomberg(), ctx)
    total = cassette("bloomberg").meta["count"]
    assert len(jobs) == total - 6 and f"collected {total - 6} jobs but the source reports {total}" in ctx.degraded


def test_avature_total_missing_from_the_page_is_reported_and_jobs_kept():
    ctx = FetchContext()
    jobs = replay("electronic-arts", settings=ea(total_regex=r'data-total="(\d+)"'), ctx=ctx)
    assert len(jobs) == cassette("electronic-arts").meta["count"] and "total not found on the page" in ctx.degraded
    with pytest.raises(CheckerError):
        replay("electronic-arts", settings=ea(total_regex=r'data-total="(\d+)"'))


# Workday ------------------------------------------------------------------------------------

class WorkdaySite:
    """A Workday CXS site in memory. Each job is a dict of facet → value; a search applies the facets, reports at most
    2000 jobs and wraps around to page 1 past offset 2000, as the real API does. Location facets are nested inside
    locationMainGroup, as on real sites."""

    def __init__(self, jobs: list[dict]):
        self.jobs, self.searches = jobs, []

    def post_json(self, url, json=None, headers=None):
        applied = json["appliedFacets"]
        if json["offset"] == 0:
            self.searches.append(applied)
        rows = [j for j in self.jobs if all(j.get(k) in ids for k, ids in applied.items())]
        offset = json["offset"] if json["offset"] < 2000 else 0
        page = [{"title": j["title"], "externalPath": j["path"]} for j in rows[offset:offset + json["limit"]]]
        flat, nested = [], []
        for name in sorted({k for j in rows for k in j} - {"title", "path"}):
            counts = collections.Counter(j[name] for j in rows if j.get(name))
            values = [{"id": v, "descriptor": v, "count": n} for v, n in counts.items()]
            (nested if name.startswith("location") else flat).append({"facetParameter": name, "values": values})
        facets = flat + ([{"facetParameter": "locationMainGroup", "values": nested}] if nested else [])
        return {"total": min(len(rows), 2000), "jobPostings": page, "facets": facets}


def wd_jobs(n: int, start: int = 0, **facets) -> list[dict]:
    """`n` jobs; each facet is a function of the job's number giving its value (None: no value)."""
    return [{"title": f"Job {i}", "path": f"/job/Job-{i}", **{k: f(i) for k, f in facets.items()}}
            for i in range(start, start + n)]


WD = {"host": "x.wd1.myworkdayjobs.com", "tenant": "x", "site": "Ext"}


def test_workday_auto_partition_prefers_a_facet_that_covers_every_job():
    # 2,100 jobs: 150 have no time type (the facet adds up to 1,950), every one has a job family group
    site = WorkdaySite(wd_jobs(2100, timeType=lambda i: "FT" if i < 1800 else "PT" if i < 1950 else None,
                               jobFamilyGroup=lambda i: "A" if i % 2 else "B"))
    ctx = FetchContext()
    jobs = get_checker("workday").fetch(site, WD, ctx)
    assert len(jobs) == 2100 and ctx.degraded is None and ctx.reported_total == 2100
    assert {next(iter(f)) for f in site.searches[1:]} == {"jobFamilyGroup"}  # not timeType, which loses 100 jobs


def test_workday_auto_partition_judges_coverage_by_the_real_size_not_the_capped_total():
    # the capped total says 2000; the worker types count all 2,100 jobs, the time types only 2,050
    site = WorkdaySite(wd_jobs(2100, timeType=lambda i: "FT" if i < 1900 else "PT" if i < 2050 else None,
                               workerSubType=lambda i: "Regular" if i < 1900 else "Intern"))
    ctx = FetchContext()
    assert len(get_checker("workday").fetch(site, WD, ctx)) == 2100 and ctx.degraded is None
    assert {next(iter(f)) for f in site.searches[1:]} == {"workerSubType"}


def test_workday_auto_partition_without_a_covering_facet_is_reported():
    site = WorkdaySite(wd_jobs(2100, timeType=lambda i: "FT" if i < 1500 else "PT" if i < 1800 else None))
    ctx = FetchContext()
    jobs = get_checker("workday").fetch(site, WD, ctx)
    assert len(jobs) == 2000  # the capped search's 2000 plus what the time types reach; 100 can't be read
    assert ctx.degraded.startswith("workday:x/Ext partitioned by timeType: collected 1800 jobs but the source "
                                   "reports 2000")
    assert len(get_checker("workday").fetch(site, WD)) == 2000  # no context: as before, no error


TMO = {**WD, "partitions": [{"timeType": ["FT"]}, {"timeType": ["PT"]}]}
STATES = lambda i: ("CA", "TX", "NY")[i % 3]  # noqa: E731


def test_workday_capped_partition_is_split_by_a_facet_from_its_own_page():
    # T-Mobile: Part time (1,892 in October) grows past the cap; its first page counts jobs per state
    site = WorkdaySite(wd_jobs(641, timeType=lambda i: "FT", locationRegionStateProvince=STATES)
                       + wd_jobs(2100, start=641, timeType=lambda i: "PT", locationRegionStateProvince=STATES))
    ctx = FetchContext()
    jobs = get_checker("workday").fetch(site, TMO, ctx)
    assert len(jobs) == 2741 and ctx.degraded is None and ctx.reported_total == 2741
    assert {"timeType": ["PT"], "locationRegionStateProvince": ["CA"]} in site.searches


def test_workday_capped_partition_that_cannot_be_split_keeps_what_was_read():
    site = WorkdaySite(wd_jobs(641, timeType=lambda i: "FT") + wd_jobs(2100, start=641, timeType=lambda i: "PT"))
    ctx = FetchContext()
    jobs = get_checker("workday").fetch(site, TMO, ctx)
    assert len(jobs) == 641 + 2000  # Full time (where the interns are) is not thrown away
    assert "{'timeType': ['PT']}: 2000+ jobs hit Workday's 2000 cap and no facet splits them" in ctx.degraded
    with pytest.raises(CheckerError):  # no context: fails as before
        get_checker("workday").fetch(site, TMO)


def test_workday_capped_site_that_no_facet_splits_keeps_what_was_read():
    site = WorkdaySite(wd_jobs(2100))
    ctx = FetchContext()
    assert len(get_checker("workday").fetch(site, WD, ctx)) == 2000
    assert "no facet splits them" in ctx.degraded
    with pytest.raises(CheckerError):
        get_checker("workday").fetch(site, WD)


def linkless_site(n: int) -> WorkdaySite:
    """Capital One's shape: a capped site split by location (100 jobs in "small"), `n` of small's jobs without a link,
    so each is listed twice: in the capped search and in small's own search."""
    jobs = wd_jobs(2100, locations=lambda i: "small" if i < 100 else f"city {i % 20}")
    for j in jobs[5:5 + n]:
        j["path"] = None
    return WorkdaySite(jobs)


def test_workday_unlinked_once_counts_a_posting_once_against_the_whole_site():
    with pytest.raises(CheckerError, match="4 postings without externalPath"):  # as on 10 Nov 2026: 2 postings, read lost
        get_checker("workday").fetch(linkless_site(2), WD, FetchContext())
    ctx = FetchContext()
    jobs = get_checker("workday").fetch(linkless_site(2), {**WD, "unlinked_once": True}, ctx)
    assert len(jobs) == 2098 and not ctx.degraded and not ctx.partial


def test_workday_unlinked_once_names_more_than_two_and_stops_past_two_percent():
    ctx = FetchContext()
    jobs = get_checker("workday").fetch(linkless_site(3), {**WD, "unlinked_once": True}, ctx)
    assert len(jobs) == 2097 and ctx.partial
    assert ctx.degraded == "workday:x: skipped 3 postings without a link: Job 5; Job 6; Job 7"
    with pytest.raises(CheckerError, match="41 postings without externalPath"):  # 2% of 2000: the format changed
        get_checker("workday").fetch(linkless_site(41), {**WD, "unlinked_once": True}, FetchContext())


def test_workday_unlinked_once_on_capital_ones_recorded_read():
    """Capital One's recorded read, whole and then by location, with two postings of a small location's search listed
    without a link wherever they appear."""
    cas = cassette("capital-one")
    listed = collections.Counter(p["externalPath"] for e in cas.exchanges for p in json.loads(e["text"]).get("jobPostings") or [])
    small = next(d for e in cas.exchanges if json.loads(e["body"] or "{}").get("appliedFacets")
                 and json.loads(e["body"])["offset"] == 0 and (d := json.loads(e["text"]))["total"] < 150)
    paths = [p["externalPath"] for p in small["jobPostings"] if listed[p["externalPath"]] > 1][:2]

    def unlink(e):
        d = json.loads(e["text"])
        for p in d.get("jobPostings") or []:
            if p.get("externalPath") in paths:
                p.pop("externalPath")
        e["text"] = json.dumps(d)
    settings = cas.meta["settings"]
    with pytest.raises(CheckerError, match="postings without externalPath"):  # as on 10 Nov 2026
        replay("capital-one", unlink, settings={k: v for k, v in settings.items() if k != "unlinked_once"})
    ctx = FetchContext()
    jobs = replay("capital-one", unlink, ctx=ctx)
    assert settings["unlinked_once"] and len(paths) == 2
    assert len(jobs) == cas.meta["count"] - 2 and not ctx.degraded and not ctx.partial


# Eightfold ----------------------------------------------------------------------------------

class OutOfTime:
    """Replays a fixture, but the check's time budget runs out after `pages` pages of the full listing (requests
    without a filter_ parameter), as on a slow day for Microsoft's 2,400-job walk."""

    def __init__(self, key: str, pages: int):
        self.http, self.pages, self.calls = Http(replay=cassette(key)), pages, []

    def get_json(self, url, params=None, **kw):
        listing = not any(k.startswith("filter_") for k in params or {})
        self.calls.append("listing" if listing else "filter")
        if listing:
            if self.pages == 0:
                raise CheckTimeout(f"time budget exhausted before GET {url}")
            self.pages -= 1
        return self.http.get_json(url, params=params, **kw)


def test_eightfold_reads_the_internship_filters_before_the_full_listing():
    http = OutOfTime("microsoft", pages=10_000)
    jobs = get_checker("eightfold").fetch(http, cassette("microsoft").meta["settings"], FetchContext())
    assert len(jobs) == cassette("microsoft").meta["count"]
    first_listing = http.calls.index("listing")
    assert first_listing > 0 and "filter" not in http.calls[first_listing:]


def test_eightfold_full_listing_out_of_time_keeps_the_internships_and_what_was_read():
    settings = cassette("microsoft").meta["settings"]
    ctx0 = FetchContext()
    student = get_checker("eightfold").fetch(OutOfTime("microsoft", pages=0), settings, ctx0)
    assert student and "stopped after 0 jobs (the internship filters were read in full)" in ctx0.degraded
    ctx = FetchContext()
    jobs = get_checker("eightfold").fetch(OutOfTime("microsoft", pages=50), settings, ctx)
    assert {j.id for j in student} < {j.id for j in jobs} and len(jobs) >= 490
    assert "the full listing stopped after" in ctx.degraded and "time budget exhausted" in ctx.degraded
    with pytest.raises(CheckTimeout):  # no context: fails as before
        get_checker("eightfold").fetch(OutOfTime("microsoft", pages=50), settings)


# One malformed posting ----------------------------------------------------------------------

def first_response(key: str, change):
    """An edit that applies `change(data)` to the fixture's first response (and its repeats, e.g. Eightfold's
    second read of page 1)."""
    first = cassette(key).exchanges[0]

    def edit(e):
        if (e["method"], e["url"], e["body"]) == (first["method"], first["url"], first["body"]):
            d = json.loads(e["text"])
            change(d)
            e["text"] = json.dumps(d)
    return edit


def drop(item, *keys):
    """A change that removes `keys` from the posting `item(data)` picks."""
    def change(d):
        for k in keys:
            item(d).pop(k, None)
    return change


MALFORMED = [
    ("akamai", drop(lambda d: d["items"][0]["requisitionList"][0], "Title"), "requisitions without Id/Title"),
    ("brevan-howard", drop(lambda d: d["refineSearch"]["data"]["jobs"][0], "jobId", "jobSeqNo", "reqId"),
     "jobs without id/title"),
    ("docusign", drop(lambda d: d["jobs"][0]["data"], "title"), "jobs without slug/title"),
    ("john-deere", drop(lambda d: d["data"]["positions"][0], "name", "posting_name"), "positions without id/name"),
    ("liberty-mutual", drop(lambda d: d["positions"][0], "name", "posting_name"), "positions without id/name"),
]


@pytest.mark.parametrize("key, change, label", MALFORMED, ids=[m[0] for m in MALFORMED])
def test_posting_without_id_or_title_is_skipped_and_reported(key, change, label):
    ctx = FetchContext()
    jobs = replay(key, first_response(key, change), ctx=ctx)
    assert len(jobs) == cassette(key).meta["count"] - 1
    assert ctx.degraded.endswith(f": skipped 1 {label}")
    with pytest.raises(CheckerError):  # no context: fails as before
        replay(key, first_response(key, change))


def test_wrong_response_shape_or_no_usable_posting_still_fails():
    def not_a_list(d):
        d["jobs"] = {"0": d["jobs"][0]}
    with pytest.raises(CheckerError):
        replay("docusign", first_response("docusign", not_a_list), ctx=FetchContext())

    def no_titles(d):
        for j in d["refineSearch"]["data"]["jobs"]:
            j.pop("title")
    with pytest.raises(CheckerError):
        replay("brevan-howard", first_response("brevan-howard", no_titles), ctx=FetchContext())
