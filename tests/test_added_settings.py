"""Settings only companies added in November 2026 use (each off unless a company sets it, so the others read exactly
as before): Workday `pack` and `unlinked_ok`, `anchor_host` address markers, SmartRecruiters `ignore_search_total`."""
import json

from internwatch.adapters import get_checker
from internwatch.config import Company
from internwatch.crosscheck import CompanyIndex, Row
from internwatch.adapters.base import FetchContext

from test_adapter_fixes import WD, WorkdaySite, replay, wd_jobs
from test_gap_fixes import _drop_links

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
