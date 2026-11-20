"""Settings only companies added in November 2026 use (each off unless a company sets it, so the others read exactly
as before): Workday `pack`, `split_first`, `past_total` and `unlinked_ok`, `anchor_host` address markers, SmartRecruiters `ignore_search_total`,
multi `twin_ids`."""
import json

import pytest

from internwatch.adapters import get_checker
from internwatch.config import Company
from internwatch.crosscheck import CompanyIndex, Row, find_in_db
from internwatch.adapters.base import FetchContext
from internwatch.db import iso
from internwatch.models import Job, ShapeError

from test_adapter_fixes import STATES, TMO, WD, WorkdaySite, cassette, replay, wd_jobs
from test_gap_fixes import _drop_links

# Simplify's links to DriveWealth's Ashby copies of three internships it also posts on Greenhouse (titled differently)
ASHBY = {"AI Consulting Associate Program – AI Engineer Intern": "a214dd6c-e3ac-481e-8308-bf74c2032b8a",
         "AI Consulting Associate Program Product Owner Intern": "ec17ef99-dea9-4150-b935-5f74750d7b87",
         "AI Consulting Associate Program Brokerage Intern": "b11409e6-a86d-4504-b4da-36636f888c16"}

STORES = lambda i: f"store {i % 100}"  # noqa: E731 — 100 store locations, the only facet that splits the site


def test_workday_pack_reads_a_site_split_only_by_store_locations_in_a_few_searches():
    jobs = wd_jobs(2500, locations=STORES)
    plain, packed = WorkdaySite(jobs), WorkdaySite(jobs)
    ctx1, ctx2 = FetchContext(), FetchContext()
    assert len(get_checker("workday").fetch(plain, WD, ctx1)) == 2500 and ctx1.degraded is None
    assert len(plain.searches) == 1 + 100                     # the capped search, then one search per store
    assert len(get_checker("workday").fetch(packed, {**WD, "pack": True}, ctx2)) == 2500 and ctx2.degraded is None
    assert len(packed.searches) == 1 + 2                      # 76 stores (1,900 jobs), then the other 24
    assert sorted(len(s["locations"]) for s in packed.searches[1:]) == [24, 76]


def test_workday_pack_leaves_a_split_into_a_few_searches_alone():
    jobs = wd_jobs(2100, timeType=lambda i: "FT" if i < 1500 else "PT")
    plain, packed = WorkdaySite(jobs), WorkdaySite(jobs)
    get_checker("workday").fetch(plain, WD, FetchContext())
    get_checker("workday").fetch(packed, {**WD, "pack": True}, FetchContext())
    assert packed.searches == plain.searches == [{}, {"timeType": ["FT"]}, {"timeType": ["PT"]}]


class Counted(WorkdaySite):
    """A WorkdaySite that counts every request, not only each search's first."""

    def __init__(self, jobs):
        super().__init__(jobs)
        self.requests = 0

    def post_json(self, url, json=None, headers=None):
        self.requests += 1
        return super().post_json(url, json=json, headers=headers)


def test_workday_split_first_splits_a_capped_site_from_its_first_page():
    jobs = wd_jobs(2100, timeType=lambda i: "FT" if i < 1500 else "PT")
    plain, split = Counted(jobs), Counted(jobs)
    ctx1, ctx2 = FetchContext(), FetchContext()
    a = get_checker("workday").fetch(plain, WD, ctx1)
    b = get_checker("workday").fetch(split, {**WD, "split_first": True}, ctx2)
    assert sorted(j.id for j in a) == sorted(j.id for j in b) and len(b) == 2100
    assert ctx1.degraded is ctx2.degraded is None and ctx1.reported_total == ctx2.reported_total == 2100
    assert split.searches == plain.searches == [{}, {"timeType": ["FT"]}, {"timeType": ["PT"]}]
    assert plain.requests == 100 + 75 + 30    # the capped search to its end, then each time type
    assert split.requests == 1 + 75 + 30      # only its first page


def test_workday_split_first_splits_a_capped_part_from_its_first_page_too():
    jobs = (wd_jobs(641, timeType=lambda i: "FT", locationRegionStateProvince=STATES)
            + wd_jobs(2100, start=641, timeType=lambda i: "PT", locationRegionStateProvince=STATES))
    plain, split = Counted(jobs), Counted(jobs)
    ctx = FetchContext()
    a = get_checker("workday").fetch(plain, TMO, FetchContext())
    b = get_checker("workday").fetch(split, {**TMO, "split_first": True}, ctx)
    assert sorted(j.id for j in a) == sorted(j.id for j in b) and len(b) == 2741
    assert ctx.degraded is None and ctx.reported_total == 2741 and split.searches == plain.searches
    assert plain.requests - split.requests == 99   # Part time's capped search: 100 pages, or the first


def test_workday_split_first_reads_a_capped_site_that_no_facet_splits_to_its_end():
    site = Counted(wd_jobs(2100))
    ctx = FetchContext()
    assert len(get_checker("workday").fetch(site, {**WD, "split_first": True}, ctx)) == 2000   # as without it
    assert "no facet splits them" in ctx.degraded and site.requests == 1 + 100


def test_workday_split_first_leaves_a_site_below_the_cap_alone():
    jobs = wd_jobs(150, timeType=lambda i: "FT")
    plain, split = Counted(jobs), Counted(jobs)
    a = get_checker("workday").fetch(plain, WD, FetchContext())
    b = get_checker("workday").fetch(split, {**WD, "split_first": True}, FetchContext())
    assert [j.id for j in a] == [j.id for j in b] and plain.requests == split.requests == 8


class Growing(Counted):
    """A site that gains `new` postings at the top of its list (newest first) after its `at`-th request."""

    def __init__(self, jobs, new: int, at: int):
        super().__init__(jobs)
        self.new, self.at = new, at

    def post_json(self, url, json=None, headers=None):
        if self.requests == self.at:
            self.jobs = wd_jobs(self.new, start=10_000, timeType=lambda i: "FT") + self.jobs
        return super().post_json(url, json=json, headers=headers)


def test_workday_past_total_reads_the_postings_a_growing_search_pushes_past_its_first_total():
    jobs = wd_jobs(400, timeType=lambda i: "FT")
    plain, ctx = Growing(jobs, new=18, at=5), FetchContext()
    with pytest.raises(ShapeError, match="collected 382 jobs but the source reports 400"):  # Walmart, 2026-11-13
        get_checker("workday").fetch(plain, WD, ctx)
    site, ctx = Growing(jobs, new=18, at=5), FetchContext()
    got = get_checker("workday").fetch(site, {**WD, "past_total": True}, ctx)
    assert {j.id for j in got} >= {f"/job/Job-{i}" for i in range(400)} and ctx.degraded is None   # none of the 400 lost
    assert site.requests == 20 + 1    # the 20 pages of the first total, then the page the oldest were pushed to


def test_workday_past_total_asks_once_more_only_after_a_full_last_page():
    for n, extra in ((150, 0), (160, 1)):   # 160 ends on a full page: one more request, which brings nothing
        plain, site = Counted(wd_jobs(n, timeType=lambda i: "FT")), Counted(wd_jobs(n, timeType=lambda i: "FT"))
        a = get_checker("workday").fetch(plain, WD, FetchContext())
        b = get_checker("workday").fetch(site, {**WD, "past_total": True}, FetchContext())
        assert [j.id for j in a] == [j.id for j in b] and site.requests == plain.requests + extra == 8 + extra


def test_workday_past_total_stops_when_the_page_past_the_end_repeats_the_first(monkeypatch):
    class Wraps(Counted):   # Target's tenant answers a page past the end with postings it already listed
        def post_json(self, url, json=None, headers=None):
            if json["offset"] >= len(self.jobs):
                json = {**json, "offset": 0}
            return super().post_json(url, json=json, headers=headers)
    site, ctx = Wraps(wd_jobs(160, timeType=lambda i: "FT")), FetchContext()
    assert len(get_checker("workday").fetch(site, {**WD, "past_total": True}, ctx)) == 160 and ctx.degraded is None
    assert site.requests == 9


def _sr_page(title, expired=False):
    button = ('<button id="st-apply" class="button">Sorry, this job has expired</button>' if expired
              else '<a class="apply-with-smartr-button">I&#39;m interested</a>')
    return (f'<html><h1 itemprop="title">{title}</h1><meta itemprop="datePosted" content="2026-09-28T19:47:06.751Z">'
            '<meta itemprop="addressLocality" content="Rochester"><meta itemprop="addressRegion" content="Minnesota">'
            f'<meta itemprop="addressCountry" content="United States"><div itemprop="description">Co-op</div>{button}</html>')


def test_smartrecruiters_watch_ids_read_postings_the_page_and_search_leave_out():
    # Western Digital, 2026-11-15: its page lists 162 postings, its search the newest 100 of 325; a Winter 2027 co-op
    # posted in September was in neither, and Simplify linked it
    from test_board_fixes import FakeHttp
    from internwatch.http import Resp
    wd = "https://jobs.smartrecruiters.com/WesternDigital/"
    http = FakeHttp({wd + "1": _sr_page("Winter 2027 Intern/Co-op Development Engineer"),
                     wd + "2": _sr_page("Spring 2027 Co-Op - AI Systems Strategy", expired=True),
                     wd + "3": Resp(404, wd + "3", {}, b"")})
    ctx = FetchContext()
    ctx.state = {"watch_closed": ["9"]}
    got = get_checker("smartrecruiters")._watched(http, {"company": "WesternDigital", "watch_ids": ["1", "2", "3", "4"]},
                                                 ctx, listed={"4"})
    assert [(j.id, j.title, j.location, j.posted, j.extra) for j in got] == [
        ("1", "Winter 2027 Intern/Co-op Development Engineer", "Rochester, Minnesota, United States", "2026-09-28",
         {"unlisted": True})]
    assert ctx.state == {"watch_open": ["1"], "watch_closed": ["2", "3", "9"]} and http.asked == [wd + "1", wd + "2", wd + "3"]


def test_smartrecruiters_learns_ids_from_simplify_links():
    from internwatch.runner import POSTING_ID_IN_URL
    rx = POSTING_ID_IN_URL["smartrecruiters"]
    assert rx.search("https://jobs.smartrecruiters.com/WesternDigital/744000152261929").group(1) == "744000152261929"
    assert rx.search("https://jobs.smartrecruiters.com/Intuitive/744000150000000-co-op-intern?trid=x").group(1) == "744000150000000"


def test_workday_unlinked_ok_skips_postings_without_a_link_quietly():
    from test_adapter_fixes import cassette
    base = cassette("crowdstrike").meta["settings"]
    ctx = FetchContext()
    replay("crowdstrike", _drop_links(5), ctx=ctx)
    assert "skipped 5 postings without a link" in ctx.degraded and ctx.partial       # as before
    ctx = FetchContext()
    jobs = replay("crowdstrike", _drop_links(5), settings={**base, "unlinked_ok": 50}, ctx=ctx)
    assert not ctx.degraded and not ctx.partial and len(jobs) == cassette("crowdstrike").meta["count"] - 5


def test_anchor_host_matches_the_tenant_only_at_the_start_of_a_link():
    def ms(**s):
        return Company(key="morgan-stanley", name="Morgan Stanley", category="", careers_url=[], checker="workday",
                       settings={"host": "ms.wd5.myworkdayjobs.com", "tenant": "ms", "site": "External", **s})

    def match(c, url):
        return CompanyIndex([c]).match(Row("", "", "Williams", "", "", url, "", ""))
    williams = "https://williams.wd5.myworkdayjobs.com/External/job/OK-Tulsa/Engineering-Intern_R1"
    own = "https://ms.wd5.myworkdayjobs.com/External/job/New-York/Technology-Intern_R2"
    assert match(ms(), williams) == "morgan-stanley"            # today: inside another tenant's link too
    assert match(ms(anchor_host=True), williams) is None
    assert match(ms(anchor_host=True), own) == "morgan-stanley"


def test_smartrecruiters_ignore_search_total_keeps_the_pages_own_count_check():
    def inflate(e):
        if "/sr-jobs/search" in e["url"]:
            e["text"] = json.dumps(dict(json.loads(e["text"]), totalFound=1000))
    from test_adapter_fixes import cassette
    base = cassette("servicenow").meta["settings"]
    ctx = FetchContext()
    assert len(replay("servicenow", inflate, settings={**base, "ignore_search_total": True}, ctx=ctx)) == 679
    assert ctx.degraded is None
    ctx = FetchContext()
    replay("servicenow", inflate, ctx=ctx)
    assert "the search reports 1000" in ctx.degraded            # as before


def _simplify_finds(memdb, jobs) -> dict:
    memdb.upsert_jobs("drivewealth", jobs, iso())
    return {t: (find_in_db(memdb, "drivewealth", Row("s", "k", "DriveWealth", t, "Chicago, IL",
                                                     f"https://jobs.ashbyhq.com/drivewealth/{u}?embed=true", "", ""))[1])
            for t, u in ASHBY.items()}


def test_multi_twin_ids_finds_simplify_rows_that_link_the_dropped_copy(memdb):
    base = {k: v for k, v in cassette("drivewealth").meta["settings"].items() if k != "twin_ids"}
    plain = replay("drivewealth", settings=base)
    twins = replay("drivewealth", settings={**base, "twin_ids": True})
    assert [j.id for j in twins] == [j.id for j in plain] and len(plain) == 27      # the same jobs are kept
    assert not any("twin_ids" in j.extra for j in plain)                                # as before
    assert sum(len(j.extra.get("twin_ids", [])) for j in twins) == 27                  # every Ashby copy, once
    assert _simplify_finds(memdb, plain) == dict.fromkeys(ASHBY, "")                   # today: three misses
    memdb.conn.execute("DELETE FROM jobs")
    assert _simplify_finds(memdb, twins) == dict.fromkeys(ASHBY, "id")


def test_multi_twin_ids_adds_a_copy_seen_later_to_the_stored_job(memdb):
    first = Job(id="8039350003", title="AI CAP Engineering Intern", extra={"alt_ids": ["R1"]})
    memdb.upsert_jobs("x", [first], iso())
    again = Job(id="8039350003", title="AI CAP Engineering Intern", extra={"alt_ids": ["R1", "R2"]})
    memdb.upsert_jobs("x", [again], iso())
    assert json.loads(memdb.job("x", "8039350003")["alt_ids"]) == ["R1"]               # as before: kept from the insert
    later = Job(id="8039350003", title="AI CAP Engineering Intern", extra={"alt_ids": ["R1"], "twin_ids": ["a214dd6c"]})
    memdb.upsert_jobs("x", [later], iso())
    memdb.upsert_jobs("x", [later], iso())
    assert json.loads(memdb.job("x", "8039350003")["alt_ids"]) == ["R1", "a214dd6c"]


def test_multi_twin_ids_counts_a_board_that_only_repeats_another_as_its_own():
    from internwatch import liveness
    from internwatch.health import Outcome
    base = {k: v for k, v in cassette("drivewealth").meta["settings"].items() if k != "twin_ids"}

    def boards(settings):
        c = Company(key="drivewealth", name="DriveWealth", category="", careers_url=[], checker="multi", settings=settings)
        o = Outcome(company=c, jobs=replay("drivewealth", settings=settings))
        return (sorted(liveness.source_counts(c, o).values()),
                sorted((what, len(jobs)) for what, jobs in liveness.boards(c, o).values()))
    # as before: every Ashby posting is a copy of a Greenhouse one, so the Ashby board looked empty (quiet in 45 days)
    assert boards(base) == ([("ashby source 2", 0), ("greenhouse source 1", 27)],
                            [("ashby source 2", 0), ("greenhouse source 1", 27)])
    assert boards({**base, "twin_ids": True}) == ([("ashby source 2", 27), ("greenhouse source 1", 27)],
                                                  [("ashby source 2", 27), ("greenhouse source 1", 27)])


# SmartRecruiters `sweep` (Western Digital, 2026-11-20: its page lists 162 postings and its search the newest 100 of
# 324, so older postings were in neither; the search takes a keyword, which reaches them whatever their age)

SR_SEARCH = "https://jobs.smartrecruiters.com/sr-jobs/search"
SR_PAGE = ('<div class="js-openings-load" data-groups-pages="1" data-more="/WD/api/groups">'
           '<section class="js-group" data-qty="1"><h3 class="opening-title">Engineering</h3><ul><li class="opening-job">'
           '<a href="https://jobs.smartrecruiters.com/WD/700001-engineer"><h4 class="job-title">Engineer</h4></a></li>'
           '</ul></section></div>')


def _sr_rows(*rows, total=None):
    return {"totalFound": len(rows) if total is None else total, "content": [
        {"id": i, "name": t, "releasedDate": "2026-08-03T10:00:00.000Z",
         "location": {"city": "San Jose", "region": "CA", "country": "us"}} for i, t in rows]}


def _sr_key(**params):
    return SR_SEARCH + "?" + json.dumps({"company": "WD", "limit": 100, **params}, sort_keys=True)


def _sr_site(newest=(), keywords=None, **more):
    """Western Digital for FakeHttp: a page with one posting, the newest-100 search and the answers of the keyword
    searches named (any other keyword finds nothing)."""
    from test_board_fixes import FakeHttp
    answers = {"https://careers.smartrecruiters.com/WD": SR_PAGE, SR_SEARCH: _sr_rows(), _sr_key(): _sr_rows(*newest)}
    answers.update({_sr_key(keyword=w): a for w, a in (keywords or {}).items()})
    return FakeHttp({**answers, **more})


def _swept(http):
    return [json.loads(a.split("?", 1)[1])["keyword"] for a in http.asked if a.startswith(SR_SEARCH) and '"keyword"' in a]


def _sweep_words(program=(), years=()):
    from internwatch.adapters.base import STUDENT_SEARCH_WORDS, UNDERCLASS_SEARCH_WORDS, WEAK_SEARCH_WORDS
    return list(dict.fromkeys([*STUDENT_SEARCH_WORDS, *UNDERCLASS_SEARCH_WORDS, *WEAK_SEARCH_WORDS, *program,
                               *map(str, years)]))


SWEEP = {"company": "WD", "sweep": True}
FOUND = {"intern": _sr_rows((700003, "Intern, Firmware Engineering"), (700002, "Staff Engineer")),
         "2nd year": _sr_rows((700004, "Technician 2, Process")),       # the search matches any one word
         "ignite": _sr_rows((700005, "Ignite Program: Hardware")), "2027": _sr_rows((700006, "Summer 2027 Analyst"))}


def test_smartrecruiters_sweep_runs_once_and_tags_what_only_it_found_as_already_open():
    http = _sr_site(newest=[(700002, "Staff Engineer")], keywords=FOUND)
    ctx = FetchContext(known=frozenset({"700001", "700002"}), program_words=("ignite",), years=(2027, 2028))
    jobs = {j.id: j for j in get_checker("smartrecruiters").fetch(http, SWEEP, ctx)}
    # every word a title can pass the role rule with, the company's program names and the filters' years
    assert _swept(http) == _sweep_words(("ignite",), (2027, 2028)) and len(_swept(http)) > 80
    assert sorted(jobs) == ["700001", "700002", "700003", "700005", "700006"]   # not the technician: no swept word in
    assert {i for i, j in jobs.items() if j.extra.get("baseline")} == {"700003", "700005", "700006"}   # its title
    assert jobs["700003"].location == "San Jose, CA, us" and jobs["700003"].posted == "2026-08-03"
    assert jobs["700002"].posted == "2026-08-03" and ctx.degraded is None and ctx.state["swept"]
    assert ctx.state["watch_open"] == ["700003", "700005", "700006"]           # read from their own pages from now on
    # the next read doesn't sweep; the runner hands it watch_open as watch_ids (learn_ids), so they stay read and open
    wd = "https://jobs.smartrecruiters.com/WD/"
    http = _sr_site(newest=[(700002, "Staff Engineer")], keywords=FOUND,
                    **{wd + "700003": _sr_page("Intern, Firmware Engineering"), wd + "700005": _sr_page("Ignite Program"),
                       wd + "700006": _sr_page("Summer 2027 Analyst", expired=True)})
    ctx2 = FetchContext(known=frozenset(jobs), state=dict(ctx.state), program_words=("ignite",), years=(2027, 2028))
    again = get_checker("smartrecruiters").fetch(http, {**SWEEP, "watch_ids": ctx.state["watch_open"]}, ctx2)
    assert _swept(http) == [] and sorted(j.id for j in again) == ["700001", "700002", "700003", "700005"]
    assert not any(j.extra.get("baseline") for j in again)
    assert ctx2.state["watch_open"] == ["700003", "700005"] and ctx2.state["watch_closed"] == ["700006"]


def test_smartrecruiters_sweep_that_is_cut_or_fails_is_reported_and_run_again():
    from internwatch.models import FetchError
    interns = [(710000 + i, f"Intern {i}") for i in range(100)]
    http = _sr_site(keywords={"intern": _sr_rows(*interns, total=150)})        # counts 150, lists its newest 100
    ctx = FetchContext(known=frozenset({"700001"}))
    jobs = get_checker("smartrecruiters").fetch(http, SWEEP, ctx)
    n = len(_sweep_words())
    assert ctx.degraded == (f"smartrecruiters:WD: keyword sweep incomplete (1 of {n} searches): "
                            "'intern' counts 150 postings and lists 100")
    assert len(jobs) == 101 and "swept" not in ctx.state and not any(j.extra.get("baseline") for j in jobs)
    assert len(ctx.state["watch_open"]) == 100
    http = _sr_site(**{_sr_key(keyword="co-op"): FetchError("HTTP 503 for the search")})
    ctx = FetchContext(known=frozenset({"700001"}))
    assert len(get_checker("smartrecruiters").fetch(http, SWEEP, ctx)) == 1 and "swept" not in ctx.state
    assert "keyword sweep incomplete (1 of" in ctx.degraded and "'co-op': HTTP 503 for the search" in ctx.degraded
    assert len(_swept(http)) == n                                              # the other words were still searched
    with pytest.raises(FetchError):                                            # no context: fails
        get_checker("smartrecruiters").fetch(_sr_site(**{_sr_key(keyword="co-op"): FetchError("HTTP 503")}), SWEEP)


def test_smartrecruiters_sweeps_again_when_the_newest_100_are_all_unknown():
    window = [(720000 + i, f"Engineer {i}") for i in range(100)]
    state = {"swept": "2026-11-20"}

    def read(newest, known):
        http = _sr_site(newest=newest, keywords=FOUND)
        ctx = FetchContext(known=frozenset(known), state=dict(state))
        return http, ctx, {j.id: j for j in get_checker("smartrecruiters").fetch(http, SWEEP, ctx)}
    http, ctx, jobs = read(window, {"700001", "600000"})        # 100 or more were posted since the last read
    assert _swept(http) == _sweep_words() and "700003" in jobs and ctx.degraded is None
    assert not any(j.extra.get("baseline") for j in jobs.values())             # these are new, not "already open"
    assert ctx.state["watch_open"] == ["700003"]
    assert _swept(read(window, {"700001", "720099"})[0]) == []                 # one posting of the 100 was known
    assert _swept(read(window[:99], {"700001"})[0]) == []                      # the answer isn't full
    assert _swept(read(window, {"smartrecruiters:720000"})[0]) == []           # a multi source's ids carry its name
    assert _swept(read(window, set())[0]) == []                                # no posting stored yet: nothing to say


def test_smartrecruiters_without_sweep_asks_the_search_once():
    http = _sr_site(newest=[(700002, "Staff Engineer")], keywords=FOUND)
    ctx = FetchContext(known=frozenset({"700001"}))
    jobs = get_checker("smartrecruiters").fetch(http, {"company": "WD"}, ctx)
    assert [a for a in http.asked if a.startswith(SR_SEARCH)] == [_sr_key()] and sorted(j.id for j in jobs) == ["700001", "700002"]
    assert ctx.state == {} and ctx.degraded is None


def test_sweep_words_cover_every_weak_hint_in_filters_yaml_and_sweep_needs_learn_ids():
    import re as _re
    import yaml
    from conftest import REPO
    from internwatch.adapters.base import WEAK_SEARCH_WORDS
    norm = lambda w: _re.sub(r"[\s\-*]+", "", w.lower())                      # noqa: E731
    weak = yaml.safe_load((REPO / "config" / "filters.yaml").read_text())["role"]["weak"]
    missing = [w for w in weak if norm(w) not in {norm(x) for x in WEAK_SEARCH_WORDS}]
    assert not missing, f"add a search word for {missing} to WEAK_SEARCH_WORDS in adapters/base.py"
    # what only the sweep found is kept read through watch_open, which the runner carries for learn_ids companies
    for c in yaml.safe_load((REPO / "config" / "companies.yaml").read_text())["companies"]:
        s = c.get("settings") or {}
        for one in [s, *((x.get("settings") or {}) for x in s.get("sources") or [])]:
            assert not one.get("sweep") or one.get("learn_ids"), f"{c['key']}: sweep needs learn_ids"
