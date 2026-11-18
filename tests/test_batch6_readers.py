"""The readers built in batch 6 (2026-11-18), replayed from their recorded fixtures, some with edited responses:
SuccessFactors (NetApp, Paramount, Qorvo), Taleo Business Edition (Costco's IT jobs), Oleeo (Bank of America's and
Morgan Stanley's campus sites), job sitemaps (Sandisk, ADP), ServiceNow (Best Buy) and the Jibe slice (Costco)."""
import copy
import json
import re

import pytest

from internwatch.adapters import get_checker
from internwatch.adapters.base import FetchContext
from internwatch.adapters.successfactors import place
from internwatch.config import Company
from internwatch.crosscheck import CompanyIndex, Row
from internwatch.http import Cassette, Http
from internwatch.models import ShapeError
from internwatch.moves import system_key_v2

from conftest import REPO

CAS = REPO / "tests" / "fixtures" / "cassettes"


def cassette(key: str, edit=None) -> Cassette:
    cas = Cassette.load(CAS / f"{key}.json.gz")
    ex = copy.deepcopy(cas.exchanges)
    for e in ex:
        if edit:
            edit(e)
    return Cassette(exchanges=ex, meta=cas.meta)


def source(key: str, checker: str) -> dict:
    """The settings of a multi company's source of one checker (Costco's Taleo site, Best Buy's US site …)."""
    s = Cassette.load(CAS / f"{key}.json.gz").meta["settings"]
    return next(x["settings"] for x in s["sources"] if x["checker"] == checker) if "sources" in s else s


def replay(key, checker=None, settings=None, edit=None, ctx=None):
    cas = cassette(key, edit)
    return get_checker(checker or cas.meta["checker"]).fetch(Http(replay=cas), settings or cas.meta["settings"], ctx)


def where(part: str, change):
    def edit(e):
        if part in e["url"]:
            change(e)
    return edit


# SuccessFactors ---------------------------------------------------------------------------------------------

def test_successfactors_reads_every_page_of_the_table_layout():
    ctx = FetchContext()
    jobs = replay("netapp", ctx=ctx)
    assert len(jobs) == len({j.id for j in jobs}) == ctx.reported_total == 332 and ctx.degraded is None
    assert all(re.fullmatch(r"https://jobs\.netapp\.com/job/[^/]+/\d+/", j.url) for j in jobs)
    assert not any(re.search(r", \d{4,}|, DE$", j.location) for j in jobs)  # postal codes gone, "DE" written out


def test_successfactors_reads_the_tile_layout_with_dates_and_functions():
    jobs = replay("paramount")
    assert len(jobs) == 199 and all(j.posted and re.fullmatch(r"\d{4}-\d\d-\d\d", j.posted) for j in jobs)
    assert sum(1 for j in jobs if j.department) > 150


def test_successfactors_places_are_written_for_the_filters():
    assert place("Dusseldorf, DE, 40472 +1 more…") == "Dusseldorf, Germany; +1 more"
    assert place("Windsor, GB, SL4 1RS") == "Windsor, United Kingdom"
    assert place("Indianapolis, IN, US, 46204") == "Indianapolis, IN, US"
    assert place("Bangalore, Karnataka, IN") == "Bangalore, Karnataka, IN"


def test_successfactors_short_walk_is_degraded_and_keeps_its_jobs():
    def drop_rows(e):  # the second page lost its jobs (a cap or a broken page) while the total still says 332
        e["text"] = re.sub(r'<tr class="data-row".*?</tr>', "", e["text"], flags=re.S)
    ctx = FetchContext()
    jobs = replay("netapp", edit=where("startrow=25", drop_rows), ctx=ctx)
    assert 25 <= len(jobs) < 332 and "pagination incomplete" in ctx.degraded and ctx.partial


def test_successfactors_page_without_a_total_fails():
    def no_total(e):
        e["text"] = re.sub(r"Results\s*<b>[^<]*</b>\s*of\s*<b>\s*[\d,]+", "", e["text"])
    with pytest.raises(ShapeError, match="no job total"):
        replay("qorvo", edit=where("startrow=0", no_total))


def test_successfactors_job_page_gives_date_description_and_every_place():
    cas = cassette("qorvo")
    ck, s = get_checker("successfactors"), cas.meta["settings"]
    jobs = ck.fetch(Http(replay=cas), s)
    job = next(j for j in jobs if j.id == "1421951500")
    ck.detail(Http(replay=cas), s, job)
    assert job.posted and job.snippet and job.location.startswith("Hillsboro")


# Taleo Business Edition ------------------------------------------------------------------------------------

def test_taleo_feed_lists_every_job_with_its_own_page():
    s = source("costco", "taleo_tbe")
    jobs = replay("costco", "taleo_tbe", s)
    assert len(jobs) == 16 and all(j.url.endswith(f"&rid={j.id}") and "viewRequisition?org=COSTCO&cws=41" in j.url
                                   for j in jobs)
    assert all(j.location and j.posted for j in jobs)  # a place with its country when the feed gives one ("…, WA, US")
    assert sum(j.location.endswith(", US") for j in jobs) >= 10


def test_taleo_answer_that_is_not_a_feed_fails():
    def error_page(e):
        e["text"] = "<html><title>Come Back Soon | Taleo Business Edition</title></html>"
    with pytest.raises(ShapeError):
        replay("costco", "taleo_tbe", source("costco", "taleo_tbe"), edit=where("servlet/Rss", error_page))


def test_taleo_item_without_its_requisition_fails():
    def no_rid(e):
        e["text"] = re.sub(r"<taleo:reqId>\d+</taleo:reqId>", "", e["text"], count=1)
    with pytest.raises(ShapeError, match="without reqId"):
        replay("costco", "taleo_tbe", source("costco", "taleo_tbe"), edit=where("servlet/Rss", no_rid))


def test_taleo_site_is_known_by_its_org_never_by_the_shared_server():
    s = source("costco", "taleo_tbe")
    assert "host" not in s and system_key_v2("taleo_tbe", s) == "taleo_tbe:cws=41,org=costco"
    costco = Company(key="costco", name="Costco", category="retail", careers_url=[], checker="multi",
                     settings={"match_urls": ["careers.costco.com", "org=costco&cws=41"], "sources": []})
    index = CompanyIndex([costco])
    ours = Row("s", "1", "Someone", "Intern", "", "https://phf.tbe.taleo.net/phf02/ats/careers/v2/viewRequisition?"
                                                  "org=COSTCO&cws=41&rid=11010", "", "", "")
    theirs = Row("s", "2", "Someone", "Intern", "", "https://phf.tbe.taleo.net/phf02/ats/careers/v2/viewRequisition?"
                                                    "org=OTHERCO&cws=1&rid=5", "", "", "")
    assert index.match(ours) == "costco" and index.match(theirs) is None


# Oleeo ---------------------------------------------------------------------------------------------------

def test_oleeo_feeds_merge_a_program_listed_on_two_boards():
    s = source("bank-of-america", "oleeo")
    jobs = replay("bank-of-america", "oleeo", s)
    entries = sum(e["text"].count("<entry") for e in cassette("bank-of-america").exchanges if e["url"].endswith("/feed"))
    assert len(jobs) == len({j.id for j in jobs}) < entries
    assert all(j.url.startswith("https://bankcampuscareers.tal.net/") and "/opp/" in j.url for j in jobs)


def test_oleeo_pages_are_read_to_the_last_one():
    jobs = replay("morgan-stanley", "oleeo", source("morgan-stanley", "oleeo"))
    assert len(jobs) == 68 and all(j.title for j in jobs) and sum(1 for j in jobs if j.location) >= 60


def test_oleeo_feed_that_is_not_atom_fails():
    def html(e):
        e["text"] = "<!DOCTYPE html><html><title>Candidate System</title></html>"
    with pytest.raises(ShapeError):
        replay("bank-of-america", "oleeo", source("bank-of-america", "oleeo"), edit=where("vacancy/2/feed", html))


# job sitemaps --------------------------------------------------------------------------------------------

def test_sitemap_jobs_take_their_titles_from_their_addresses():
    jobs = replay("sandisk")
    assert len(jobs) == 523 and any(j.title.startswith("Summer 2027 Intern") for j in jobs)


def test_sitemap_job_listed_in_twenty_languages_is_one_job():
    jobs = replay("adp")
    assert len(jobs) == len({j.id for j in jobs}) == 855 and all("/en/jobs/" in j.url for j in jobs)


def test_sitemap_whose_addresses_changed_fails():
    def renamed(e):
        e["text"] = e["text"].replace("/JobDetail/", "/Job/")
    with pytest.raises(ShapeError, match="no address matches"):
        replay("sandisk", edit=renamed)


def test_avature_job_page_gives_the_real_title_place_and_date():
    page = ('<script type="application/ld+json">{"@type":"JobPosting","title":"Summer 2027 Intern - VLSI, Memory",'
            '"datePosted":"2026-11-17"}</script>'
            + "".join(f'<div class="article__content__view__field"><div class="article__content__view__field__label">'
                      f'{k}</div><div class="article__content__view__field__value">{v}</div></div>'
                      for k, v in (("City", "Milpitas"), ("State", "California"),
                                   ("Country/Region", "United States of America"), ("Business Function", "Design")))
            + '<div class="article__content__view__field"><div>We are seeking an intern.</div></div>')
    s = cassette("sandisk").meta["settings"]
    job = next(j for j in replay("sandisk") if "Intern" in j.title)
    cas = Cassette(exchanges=[{"method": "GET", "url": job.url, "body": "", "status": 200, "headers": {}, "text": page}])
    get_checker("job_sitemap").detail(Http(replay=cas), s, job)
    assert (job.title, job.location, job.posted, job.department) == (
        "Summer 2027 Intern - VLSI, Memory", "Milpitas, California, United States of America", "2026-11-17", "Design")
    assert "seeking an intern" in job.snippet


# ServiceNow (Best Buy) -------------------------------------------------------------------------------------

def test_servicenow_list_is_the_whole_site_by_its_own_count():
    ctx = FetchContext()
    jobs = replay("best-buy", "servicenow", source("best-buy", "servicenow"), ctx=ctx)
    assert len(jobs) == ctx.reported_total and len(jobs) > 1000
    assert all(j.url.endswith(f"req_id={j.id}") and j.location.endswith("United States") for j in jobs)


def test_servicenow_portal_page_without_its_token_fails():
    def no_token(e):
        e["text"] = re.sub(r"g_ck\s*=\s*['\"][0-9a-f]+['\"]", "", e["text"])
    with pytest.raises(ShapeError, match="session token"):
        replay("best-buy", "servicenow", source("best-buy", "servicenow"), edit=where("bby?id=all_jobs", no_token))


def test_servicenow_list_shorter_than_its_count_fails():
    def more(e):
        d = json.loads(e["text"])
        d["result"]["data"]["total_count"] = int(d["result"]["data"]["total_count"]) + 1
        e["text"] = json.dumps(d)
    with pytest.raises(ShapeError, match="pagination incomplete"):
        replay("best-buy", "servicenow", source("best-buy", "servicenow"), edit=where("/api/now/sp/widget/", more))


# Jibe: a giant site's slice ------------------------------------------------------------------------------

def test_jibe_slice_reads_each_query_and_merges_them():
    s = source("costco", "jibe")
    jobs = replay("costco", "jibe", s)
    assert len(s["queries"]) == 2 and len(jobs) == 72


def test_jibe_slice_query_short_of_its_own_total_fails():
    """The categories' listing loses 10 of its 70 jobs and its next page is empty: that query is short of its own
    total, whatever the other query adds."""
    cas = cassette("costco")
    first = next(e for e in cas.exchanges if "categories=" in e["url"])
    d = json.loads(first["text"])
    d["jobs"] = d["jobs"][:-10]
    first["text"] = json.dumps(d)
    cas.exchanges.append({**first, "url": first["url"].replace("page=1", "page=2"),
                          "text": json.dumps({"jobs": [], "totalCount": 70})})
    with pytest.raises(ShapeError, match="pagination incomplete"):
        get_checker("jibe").fetch(Http(replay=cas), source("costco", "jibe"))
