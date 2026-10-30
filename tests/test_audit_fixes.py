"""The October 2026 board audit: Shopify's redesigned page and the sources it found unread."""
import json

import pytest

from internwatch.adapters import get_checker
from internwatch.adapters.base import FetchContext
from internwatch.checkers.shopify import FEED, PAGE
from internwatch.config import load
from internwatch.crosscheck import url_markers
from internwatch.db import DB
from internwatch.filters import evaluate, is_student_role
from internwatch.http import Resp
from internwatch.models import FetchError, Job, ShapeError
from internwatch.runner import RunOptions, Runner

from conftest import REPO, FakeChecker, company, job


@pytest.fixture(autouse=True)
def online(monkeypatch):
    monkeypatch.setattr(Runner, "online", lambda self: True)


class FakeHttp:
    """Answers GETs from a dict of url → text or an exception to raise."""

    def __init__(self, answers: dict):
        self.answers = answers

    def get_text(self, url, **kw):
        a = self.answers[url]
        if isinstance(a, Exception):
            raise a
        return a

    def get(self, url, **kw):
        return Resp(200, url, {}, self.get_text(url).encode())

    def get_json(self, url, **kw):
        return json.loads(self.get_text(url))


def turbo(value) -> list:
    """Encode a value the way React Router's turbo-stream does (see checkers/shopify.py)."""
    flat: list = []

    def add(v) -> int:
        i = len(flat)
        flat.append(None)
        if isinstance(v, dict):
            d = {}
            for k, x in v.items():
                name = len(flat)
                flat.append(k)
                d[f"_{name}"] = add(x)
            flat[i] = d
        elif isinstance(v, list):
            flat[i] = [add(x) for x in v]
        else:
            flat[i] = v
        return i

    add(value)
    return flat


def page(loader: dict) -> str:
    chunk = json.dumps(turbo({"loaderData": {"($locale)/careers": loader}}))
    return f"<script>window.__reactRouterContext.streamController.enqueue({json.dumps(chunk)});</script>"


ROLE = {"id": "1affb074", "title": "Software Engineer, Intern", "location": "Remote - Canada , Americas",
        "locations": ["Remote - Canada", "Remote - Americas"], "discipline": "Engineering",
        "href": "/careers/software-engineer-intern_1affb074"}
FEED_XML = ("<source><lastBuildDate><![CDATA[Fri, 30 Oct 2026]]></lastBuildDate><job>"
            "<partnerJobId><![CDATA[1affb074]]></partnerJobId><title><![CDATA[Software Engineer, Intern (Americas)]]></title>"
            "<location><![CDATA[Canada]]></location><experienceLevel><![CDATA[INTERNSHIP]]></experienceLevel>"
            "<listDate><![CDATA[10/15/2026]]></listDate></job></source>")


def test_shopify_reads_the_redesigned_page_and_the_feed():
    ctx = FetchContext()
    jobs = get_checker("shopify").fetch(FakeHttp({PAGE: page({"roles": [ROLE]}), FEED: FEED_XML}), {}, ctx)
    j = jobs[0]
    assert ctx.degraded is None and len(jobs) == 1
    assert (j.id, j.title, j.department) == ("1affb074", "Software Engineer, Intern", "Engineering")
    assert j.location == "Remote (Canada; Americas)"  # not the feed's "Canada": that would reject a role open to the US
    assert j.url == "https://www.shopify.com/careers/software-engineer-intern_1affb074"
    assert (j.employment_type, j.posted) == ("INTERNSHIP", "2026-10-15")


def test_shopify_level_marks_a_student_role_with_no_student_word(rules):
    xml = FEED_XML.replace("Software Engineer, Intern", "Software Engineer")
    role = {**ROLE, "title": "Software Engineer"}
    j = get_checker("shopify").fetch(FakeHttp({PAGE: page({"roles": [role]}), FEED: xml}), {}, FetchContext())[0]
    assert is_student_role(j, rules)
    other = xml.replace("INTERNSHIP", "MID_SENIOR_LEVEL")
    j = get_checker("shopify").fetch(FakeHttp({PAGE: page({"roles": [role]}), FEED: other}), {}, FetchContext())[0]
    assert not is_student_role(j, rules)


@pytest.mark.parametrize("feed", [FetchError("HTTP 503"), "<source><job>"])
def test_shopify_feed_failing_keeps_the_jobs_and_degrades_the_poll(feed):
    ctx = FetchContext()
    jobs = get_checker("shopify").fetch(FakeHttp({PAGE: page({"roles": [ROLE]}), FEED: feed}), {}, ctx)
    assert [j.id for j in jobs] == ["1affb074"] and jobs[0].location == "Remote (Canada; Americas)"
    assert "not read" in ctx.degraded


def test_shopify_still_reads_the_page_as_it_was():
    old = {"jobPostingsWithJobs": [{"jobPosting": {"id": "abc", "title": "Data Intern", "locationName": "Toronto",
                                                   "employmentType": "Intern"}}]}
    jobs = get_checker("shopify").fetch(FakeHttp({PAGE: page(old)}), {}, FetchContext())  # one request: no feed
    assert [(j.id, j.employment_type) for j in jobs] == [("abc", "Intern")]


def test_shopify_page_with_neither_list_is_a_shape_error():
    with pytest.raises(ShapeError, match="neither roles nor jobPostingsWithJobs"):
        get_checker("shopify").fetch(FakeHttp({PAGE: page({"content": {}})}), {}, FetchContext())


# ---------------------------------------------------------------------------------------------
# sources added by the audit

@pytest.fixture(scope="module")
def real():
    return load(REPO)


def gh(*jobs):
    return json.dumps({"jobs": [{"id": i, "title": t, "location": {"name": "New York"}} for i, t in jobs],
                       "meta": {"total": len(jobs)}})


GH = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"


@pytest.mark.parametrize("key,boards", [("flow-traders", ["flowtraders", "ftsp27co-ops"]),
                                        ("akuna-capital", ["akunacapital", "akunacapitaloci"]),
                                        ("virtu", ["virtu", "virturecruitinghidden"])])
def test_second_boards_keep_the_first_boards_ids(real, key, boards):
    c = real.company(key)
    assert c.settings["boards"] == boards
    answers = {GH.format(boards[0]): gh((1, "Trader")), GH.format(boards[1]): gh((2, "Trading Operations Engineer Co-op"))}
    jobs = get_checker(c.checker).fetch(FakeHttp(answers), c.settings, FetchContext())
    assert [j.id for j in jobs] == ["1", "2"]


def test_visa_and_peak6_read_the_new_sites_with_ids_as_before(real):
    visa, peak6 = real.company("visa"), real.company("peak6")
    assert visa.settings["sites"] == ["Visa", "Visa_Early_Careers", "Visa_Talent_Portal"]
    assert peak6.settings["sites"] == ["PEAK6", "CapMan", "apexfintechsolutions"]
    # two sites before and three now: ids keep their "<site>:" prefix either way
    assert len(get_checker("workday").sites(visa.settings)) > 1 and len(get_checker("workday").sites(peak6.settings)) > 1


def test_fintern_counts_at_peak6_only(real):
    title = "2027 AFS Technology Fintern - Software Engineering"
    peak6, other = real.company("peak6"), real.company("virtu")
    m = evaluate(Job(id="x", title=title, location="Austin, TX"), real.rules, category=peak6.category,
                 locations=peak6.locations, extra_role_keywords=peak6.extra_role_re)
    assert m.matched and m.field == "SWE" and m.term == "2027"
    assert not evaluate(Job(id="x", title=title, location="Austin, TX"), real.rules, category=other.category,
                        extra_role_keywords=other.extra_role_re).matched


def test_mongodb_greenhouse_ids_and_simplify_links_survive_the_second_source(real):
    c = real.company("mongodb")
    assert c.checker == "multi" and [x["checker"] for x in c.settings["sources"]] == ["greenhouse", "ripplematch"]
    answers = {GH.format("mongodb"): gh((7, "Software Engineer Intern")),
               "https://app.ripplematch.com/api/v2/public/roles/825": json.dumps(
                   [{"public_id": "r1", "name": "MongoDB Learnathon: MongoDB Deep Dive (Global)"}])}
    ctx = FetchContext(state={"validators": {}})
    jobs = get_checker("multi").fetch(FakeHttp(answers), c.settings, ctx)
    assert [j.id for j in jobs] == ["7", "ripplematch:r1"]
    assert not jobs[1].extra.get("baseline")  # an existing company's new source: its first jobs are new, not baseline
    assert "greenhouse.io/mongodb/" in url_markers(c)


def test_a_role_on_a_second_site_arrives_once_as_a_repost(make_cfg):
    cfg = make_cfg([company("visa", checker="fake", name="Visa")])
    seen = job("Visa:/job/a", "Workforce Protection Intern - Summer 2027", location="US - Foster City, CA")
    twin = job("Visa_Talent_Portal:/job/b", "Workforce Protection Intern - Summer 2027", location="US - Foster City, CA")
    new = job("Visa_Talent_Portal:/job/c", "Cybersecurity Apprentice", location="US - Ashburn, VA")
    db = DB(cfg.settings.path("db"))
    r = Runner(cfg, db=db, checker_fn=FakeChecker({"visa": [[seen], [seen, twin, new], [seen, twin, new]]}))
    opts = RunOptions(crosscheck=False, send=False, scheduled_mail=False, force=True)
    r.run(opts)
    s = r.run(opts)
    assert s.new_matches == 2
    assert db.job("visa", twin.id)["repost_of"] == seen.id and db.job("visa", new.id)["repost_of"] is None
    assert r.run(opts).new_matches == 0
