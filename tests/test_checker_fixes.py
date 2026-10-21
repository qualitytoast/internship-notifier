"""Regression tests for the checker gaps found in the coverage audit: Amazon's unstemmed searches, the
freshman/sophomore search words, Intuit's stale sitemap, JSON-LD location shapes, and Meta's fallbacks."""
import json
import re

import httpx
import yaml

from internwatch.adapters.base import UNDERCLASS_SEARCH_WORDS, FetchContext
from internwatch.checkers import amazon, apple
from internwatch.checkers.amazon import Amazon
from internwatch.http import HostGate, Http, HttpSettings

from conftest import REPO


def mock_http(handler) -> Http:
    """A real Http client whose requests `handler(request)` answers (no network, no robots.txt)."""
    h = Http(HttpSettings(retries=0, backoff_base=0, min_interval=0, respect_robots=False), gate=HostGate())
    h._client = httpx.Client(transport=httpx.MockTransport(handler))
    return h


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
