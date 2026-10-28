"""Small pure helpers inside checkers (slug titles, turbo-stream decoding, Workday cap partitions, …)."""
from internwatch.adapters.recruiterbox import sluggify
from internwatch.adapters.workday import CAP, Workday
from internwatch.checkers.citadel import region_hint, title_from_slug
from internwatch.checkers.shopify import decode_turbo_stream


def test_citadel_titles_keep_years_and_drop_wordpress_suffixes():
    assert title_from_slug("equities-citadel-associate-program-summer-internship-2028") == \
        "Equities Citadel Associate Program Summer Internship 2028"
    assert title_from_slug("c-software-engineer-2") == "C Software Engineer"
    assert title_from_slug("quantitative-research-phd-intern-us") == "Quantitative Research PhD Intern US"
    assert title_from_slug("head-of-trading-for-the-americas") == "Head of Trading for the Americas"


def test_citadel_region_hints():
    assert region_hint("software-engineer-intern-us") == "United States"
    assert region_hint("quant-researcher-london") == "London"
    assert region_hint("operations-analyst") == ""


def test_turbo_stream_decoding():
    # root {loaderData: {"r": {jobs: [{title: "SWE Intern"}]}}}, keys are "_<index of the key name>"
    flat = [{"_1": 2}, "loaderData", {"_3": 4}, "r", {"_5": 6}, "jobs", [7], {"_8": 9}, "title", "SWE Intern"]
    assert decode_turbo_stream(flat) == {"loaderData": {"r": {"jobs": [{"title": "SWE Intern"}]}}}


def test_turbo_stream_tags_longer_than_a_letter_stay_opaque():
    # shopify.com/careers sometimes carries pricingSite = ["SingleFetchClassInstance", n]; read as a list of
    # indices it crashed the whole poll (Wayback captures of Aug 6, Oct 12 and Oct 16 2026)
    flat = [{"_1": 2, "_3": 4, "_5": 6}, "pricingSite", ["SingleFetchClassInstance", 0], "jobs", [7], "published",
            ["D", "2026-08-06"], "SWE Intern"]
    assert decode_turbo_stream(flat) == {"pricingSite": None, "jobs": ["SWE Intern"], "published": "2026-08-06"}


def test_workday_partitions_pick_a_facet_below_the_cap():
    first = {"facets": [
        {"facetParameter": "locations", "values": [{"id": "a", "count": 2400}]},
        {"facetParameter": "timeType", "values": [{"id": "ft", "count": 641}, {"id": "pt", "count": 1893}]},
    ]}
    assert Workday()._partitions({}, first) == [{"timeType": ["ft"]}, {"timeType": ["pt"]}]
    assert Workday()._partitions({"partitions": [{"x": ["1"]}]}, first) == [{"x": ["1"]}]
    too_big = {"facets": [{"facetParameter": "timeType", "values": [{"id": "ft", "count": CAP + 5}]}]}
    assert Workday()._partitions({}, too_big) == []


def test_recruiterbox_slug_matches_widget():
    assert sluggify("Senior Applications Engineer, Data Science & Machine Learning—Linköping, Sweden") == \
        "senior-applications-engineer-data-science--machine-learninglinkping-sweden"


def test_quick_scans_stop_only_after_two_known_pages_per_listing():
    from internwatch.adapters.base import FetchContext
    ctx = FetchContext(mode="quick", known=frozenset({"a", "b", "c", "d"}))
    assert not ctx.page_is_old(["a", "b"], key="main")      # first known page: keep reading
    assert not ctx.page_is_old(["c", "x"], key="main")      # something new: streak resets
    assert not ctx.page_is_old(["c", "d"], key="main")
    assert ctx.page_is_old(["a", "b"], key="main")          # two known pages in a row: stop
    assert not ctx.page_is_old(["a", "b"], key="interns")   # other listings keep their own streak
    assert not FetchContext().page_is_old(["a"])           # full scans never stop early
