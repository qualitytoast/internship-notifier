"""Regression tests for the checker gaps found in the coverage audit: Amazon's unstemmed searches, the
freshman/sophomore search words, Intuit's stale sitemap, JSON-LD location shapes, and Meta's fallbacks."""
import json
import re
from datetime import date, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
import yaml

from internwatch.adapters.base import UNDERCLASS_SEARCH_WORDS, FetchContext
from internwatch.checkers import amazon, apple, meta, talentbrew
from internwatch.checkers.amazon import Amazon
from internwatch.checkers.meta import Meta
from internwatch.checkers.talentbrew import TalentBrewSitemap
from internwatch.http import Cassette, HostGate, Http, HttpSettings
from internwatch.models import CheckerError, Job

from conftest import REPO


def mock_http(handler) -> Http:
    """A real Http client whose requests `handler(request)` answers (no network, no robots.txt)."""
    h = Http(HttpSettings(retries=0, backoff_base=0, min_interval=0, respect_robots=False), gate=HostGate())
    h._client = httpx.Client(transport=httpx.MockTransport(handler))
    return h


def jsonld_page(obj) -> str:
    return f'<html><script type="application/ld+json">{json.dumps(obj)}</script></html>'


# Amazon -------------------------------------------------------------------------------------------

def test_amazon_finds_an_unflagged_internship_that_only_its_own_word_matches():
    # the index does not stem: "intern" misses "Internship", so a role the hiring system files as a regular job
    # outside the student categories is found only by searching the word itself
    def handler(req):
        body = json.loads(req.content)
        if body["query"] != "internship":
            return httpx.Response(200, json={"found": None, "searchHits": None})
        hit = {"icimsJobId": ["10553907"], "title": ["Data Engineer Internship - 2027 (US)"],
               "normalizedLocation": ["Seattle, Washington, USA"], "isIntern": ["0"], "employeeClass": ["Regular Full Time"]}
        return httpx.Response(200, json={"found": 1, "searchHits": [{"fields": hit}]})
    jobs = Amazon().fetch(mock_http(handler), {}, FetchContext())
    assert [(j.id, j.title) for j in jobs] == [("10553907", "Data Engineer Internship - 2027 (US)")]
    assert {"keyword:interns", "keyword:internships"} <= {name for name, _ in amazon.queries(amazon.KEYWORDS)}


def test_underclass_search_words_cover_every_filters_yaml_phrase():
    """Amazon and Apple find freshman/sophomore programs only through these searches, so a phrase added to
    role.underclassmen must get a search word too ("*" phrases by their stem)."""
    def norm(w):
        return " ".join(t for t in re.split(r"[\s\-]+", w.lower().rstrip("*")) if t)
    words = {norm(w) for w in UNDERCLASS_SEARCH_WORDS}
    phrases = yaml.safe_load((REPO / "config" / "filters.yaml").read_text())["role"]["underclassmen"]
    missing = [p for p in phrases if norm(p) not in words]
    assert not missing, f"add a search word for {missing} to UNDERCLASS_SEARCH_WORDS in adapters/base.py"
    assert set(UNDERCLASS_SEARCH_WORDS) <= set(amazon.KEYWORDS)
    assert {f"keyword:{w}" for w in UNDERCLASS_SEARCH_WORDS} <= {name for name, _ in apple.QUERIES}


# Intuit (TalentBrew sitemap) ----------------------------------------------------------------------

SITEMAP_URL = "https://jobs.example.com/sitemap.xml"
TB = {"sitemap_url": SITEMAP_URL, "org_id": 99, "detail_limit": 0}


def sitemap(lastmod: str = "2026-10-01T23:20:08.3029216Z") -> str:
    return ('<urlset><url><loc>https://jobs.example.com/job/austin/software-engineer-intern/99/1</loc>'
            f'<lastmod>{lastmod}</lastmod></url></urlset>')


def test_sitemap_age_is_counted_from_the_newest_lastmod():
    xml = sitemap("2026-10-01T23:20:08.3029216Z") + "<lastmod>2026-10-15</lastmod><lastmod>2026-13-45</lastmod>"
    assert talentbrew.sitemap_age_days(xml, date(2026, 10, 20)) == 5
    assert talentbrew.sitemap_age_days("<urlset><loc>x</loc></urlset>", date(2026, 10, 20)) is None


def test_stale_sitemap_is_reported_degraded_and_its_jobs_still_read(monkeypatch):
    http = mock_http(lambda req: httpx.Response(200, text=sitemap()))
    monkeypatch.setattr(talentbrew, "utc_today", lambda: date(2026, 10, 4))       # 3 days: fresh enough
    ctx = FetchContext()
    assert len(TalentBrewSitemap().fetch(http, TB, ctx)) == 1 and ctx.degraded is None
    monkeypatch.setattr(talentbrew, "utc_today", lambda: date(2026, 10, 20))      # not rebuilt for 19 days
    ctx = FetchContext()
    assert [j.id for j in TalentBrewSitemap().fetch(http, TB, ctx)] == ["1"]
    assert "19 days old" in ctx.degraded
    ctx = FetchContext()
    TalentBrewSitemap().fetch(http, {**TB, "max_sitemap_age_days": 30}, ctx)
    assert ctx.degraded is None
    assert len(TalentBrewSitemap().fetch(http, TB, None)) == 1                    # no context: nothing to flag


def test_intuit_replay_is_fresh_when_recorded_and_stale_days_later(monkeypatch):
    # "today" is pinned to the recording, so this keeps passing as the recorded sitemap ages
    cas = Cassette.load(REPO / "tests" / "fixtures" / "cassettes" / "intuit.json.gz")
    recorded = date.fromisoformat(cas.meta["recorded_at"][:10])
    s = {**cas.meta["settings"], "detail_limit": 0}
    for days, degraded in ((0, False), (4, True)):
        monkeypatch.setattr(talentbrew, "utc_today", lambda: recorded + timedelta(days=days))
        ctx = FetchContext()
        jobs = TalentBrewSitemap().fetch(Http(replay=cas), s, ctx)
        assert len(jobs) == cas.meta["count"] and bool(ctx.degraded) == degraded


# JSON-LD shapes (a crash here escaped the CheckerError handling and failed the whole company) -----

MENLO = {"@type": "Place", "address": {"addressLocality": "Menlo Park", "addressRegion": "CA", "addressCountry": "US"}}
PLACES = {
    "list of Places": ([MENLO], "Menlo Park, CA, US"),
    "mixed list": ([MENLO, {"@type": "Place", "address": "Seattle, WA"}], "Menlo Park, CA, US; Seattle, WA"),
    "single Place object": ({"@type": "Place", "address": {"addressLocality": "Menlo Park", "addressCountry": "US"}},
                            "Menlo Park, US"),
    "address as text": ([{"@type": "Place", "address": "Menlo Park, CA, US"}], "Menlo Park, CA, US"),
    "Country object": ({"@type": "Place", "address": {"addressLocality": "Austin", "addressRegion": "TX",
                                                      "addressCountry": {"@type": "Country", "name": "US"}}},
                       "Austin, TX, US"),
    "Place as text": ("Remote, US", "Remote, US"),
    "nothing usable": ([{"@type": "Place"}, 7, None, {"address": ["x"]}], ""),
}


@pytest.mark.parametrize("checker", [Meta(), TalentBrewSitemap()], ids=["meta", "talentbrew"])
@pytest.mark.parametrize("shape", list(PLACES))
def test_every_jsonld_location_shape_is_read(checker, shape):
    places, want = PLACES[shape]
    page = jsonld_page({"@type": "JobPosting", "title": "Software Engineer Intern", "jobLocation": places})
    j = checker.detail(mock_http(lambda req: httpx.Response(200, text=page)), {},
                       Job(id="1", title="", url="https://jobs.example.com/job/1"))
    assert (j.title, j.location) == ("Software Engineer Intern", want)


def test_meta_reads_a_jobposting_inside_a_jsonld_list():
    page = jsonld_page([{"@type": "Organization"}, {"@type": "JobPosting", "title": "Data Science Intern",
                                                    "jobLocation": {"address": "New York, NY"}}])
    j = Meta().detail(mock_http(lambda req: httpx.Response(200, text=page)), {},
                      Job(id="1", title="", url="https://jobs.example.com/job/1"))
    assert (j.title, j.location) == ("Data Science Intern", "New York, NY")


def test_talentbrew_check_survives_an_address_given_as_text():
    page = jsonld_page({"@type": "JobPosting", "title": "Software Engineer Intern - Summer 2027",
                        "jobLocation": {"@type": "Place", "address": "Mountain View, CA, US"}})
    http = mock_http(lambda req: httpx.Response(200, text=sitemap() if req.url.path == "/sitemap.xml" else page))
    jobs = TalentBrewSitemap().fetch(http, {**TB, "detail_limit": 5}, FetchContext())
    assert [(j.title, j.location) for j in jobs] == [("Software Engineer Intern - Summer 2027", "Mountain View, CA, US")]


# Meta -----------------------------------------------------------------------------------------------

def meta_handler(interns=None, sitemap_ids=(), titled=(), slow=()):
    """metacareers.com: two GraphQL jobs ("11" is an internship without a student word in its title), a jobs
    sitemap with `sitemap_ids`, and job pages that have a JobPosting only for the ids in `titled`."""
    def handler(req):
        path = req.url.path
        if path == "/jobsearch/":
            return httpx.Response(200, text='<script>["LSD",[],{"token":"tok"}]</script>')
        if path == "/graphql":
            roles = json.loads(parse_qs(req.content.decode())["variables"][0])["search_input"]["roles"]
            if roles and interns is not None:
                return httpx.Response(**interns)
            jobs = [{"id": "11", "title": "Software Engineer, Product"}, {"id": "12", "title": "Data Engineer"}]
            return httpx.Response(200, json={"data": {"job_search_with_featured_jobs_v2": {
                "all_jobs": jobs[:1] if roles else jobs, "featured_jobs": []}}})
        if path == "/jobsearch/sitemap.xml":
            return httpx.Response(200, text="".join(f"<loc>https://www.metacareers.com/profile/job_details/{i}/</loc>"
                                                    for i in sitemap_ids))
        jid = path.rstrip("/").split("/")[-1]
        if jid in slow:
            raise httpx.ReadTimeout("slow page")
        if jid in titled:
            return httpx.Response(200, text=jsonld_page({"@type": "JobPosting", "title": f"Software Engineer Intern {jid}"}))
        return httpx.Response(200, text="<html>This job is no longer available</html>")
    return handler


def test_meta_marks_internships_from_the_second_query():
    jobs = {j.id: j for j in Meta().fetch(mock_http(meta_handler()), {}, FetchContext())}
    assert jobs["11"].employment_type == "Internship" and jobs["12"].employment_type == ""


@pytest.mark.parametrize("failure", [{"status_code": 500}, {"status_code": 200, "json": {"errors": [{"message": "x"}]}}],
                         ids=["http-error", "graphql-error"])
def test_meta_keeps_the_complete_list_when_only_the_internship_query_fails(failure):
    ctx = FetchContext()
    jobs = Meta().fetch(mock_http(meta_handler(interns=failure, sitemap_ids=["99"])), {}, ctx)
    assert sorted(j.id for j in jobs) == ["11", "12"]           # all jobs, not the sitemap fallback's few
    assert "Internship query failed" in ctx.degraded
    with pytest.raises(CheckerError):                           # without a context it cannot be flagged: fails
        Meta().fetch(mock_http(meta_handler(interns=failure)), {})


def test_meta_fallback_reads_the_newest_ids_first(monkeypatch):
    ids = ["999999999999999", "1000000000000000", "10000000000000000"]  # as text, "999…" sorts first
    monkeypatch.setattr(meta, "FALLBACK_DETAIL_LIMIT", 1)
    jobs = Meta()._sitemap(mock_http(meta_handler(sitemap_ids=ids, titled=ids)), FetchContext())
    assert [j.id for j in jobs] == ["10000000000000000"]


def test_meta_fallback_stops_retrying_ids_whose_page_gives_no_title(monkeypatch):
    # the two newest ids never give a title; without a limit they would take both detail slots every run
    monkeypatch.setattr(meta, "FALLBACK_DETAIL_LIMIT", 2)
    ids = ["1000000000000003", "1000000000000002", "1000000000000001"]
    state: dict = {}
    for run in range(4):
        ctx = FetchContext(state=state)
        jobs = Meta()._sitemap(mock_http(meta_handler(sitemap_ids=ids, titled=[ids[2]])), ctx)
        assert [j.id for j in jobs] == ([] if run < 3 else [ids[2]])
        state = json.loads(json.dumps(ctx.state))                # saved between polls as JSON
    assert state["sitemap_misses"] == {ids[0]: 3, ids[1]: 3}
    ctx = FetchContext(state=state, known=frozenset({ids[2]}))
    Meta()._sitemap(mock_http(meta_handler(sitemap_ids=ids[1:])), ctx)   # ids[0] closed: forgotten
    assert ctx.state["sitemap_misses"] == {ids[1]: 3}


def test_meta_fallback_does_not_count_a_timeout_against_an_id():
    ctx = FetchContext()
    Meta()._sitemap(mock_http(meta_handler(sitemap_ids=["5", "4"], slow=["5"])), ctx)
    assert ctx.state["sitemap_misses"] == {"4": 1}
