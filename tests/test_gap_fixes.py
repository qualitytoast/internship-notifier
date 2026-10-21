"""Fixes from the October 2026 coverage audit: roles that could miss the inbox although they were posted."""
import json
from datetime import timedelta
from pathlib import Path

import pytest

from conftest import FakeChecker, company, job
from internwatch.adapters.base import FetchContext
from internwatch.checkers.multi import Multi
from internwatch.db import DB, iso, utcnow
from internwatch.filters import evaluate
from internwatch.models import FetchError, Job
from internwatch.runner import RunOptions, Runner


def ev(rules, title, location="New York, NY", **kw):
    return evaluate(Job(id="x", title=title, location=location, **kw), rules, category=kw.pop("category", ""))


# ---------------------------------------------------------------------------------------------
# filters: what only looks like a term, misleading departments and program labels

@pytest.mark.parametrize("title,term", [
    ("Software Engineering Intern (Graduating Spring 2029)", "unspecified"),     # a graduation date, not the term
    ("Software Engineer Intern - Expected Graduation: May 2029", "unspecified"),
    ("Software Engineer Intern (May 2029 grads)", "unspecified"),
    ("Software Engineering Co-op (Winter 2026/2027)", "Winter 2027"),            # an academic year: both years
    ("Software Engineer Co-op 2026-27", "2027"),
])
def test_dates_that_only_look_like_another_term_do_not_reject(rules, title, term):
    m = ev(rules, title)
    assert m.matched, m.reasons
    assert m.term == term


@pytest.mark.parametrize("title", [
    "Software Engineer Intern (Graduating Spring 2026)",   # graduates before your window, like "Class of 2026"
    "Software Engineer Intern - Winter 2026",
    "Software Engineer Intern - Summer 2026",
])
def test_earlier_terms_still_reject(rules, title):
    assert not ev(rules, title).matched


def test_the_rescue_never_rejects_what_was_accepted(rules):
    assert ev(rules, "Software Engineer Intern 2025/26").matched   # no term read before, none now


@pytest.mark.parametrize("title,department,field", [
    # Liberty Mutual files these under "Finance & Accounting"; the title decides
    ("Cybersecurity Co-op (January - June 2027)", "Finance & Accounting", "SWE"),
    ("Catastrophe Modeling & GIS Research Co-op (January - June 2027)", "Finance & Accounting", "Research"),
    ("Summer 2027 Internships - Marketing, Public Relations/Communications, Accounting, or Information Technology",
     "", "SWE"),
])
def test_security_it_and_research_coops_are_in_field(rules, title, department, field):
    m = ev(rules, title, department=department)
    assert m.matched, m.reasons
    assert m.field == field


@pytest.mark.parametrize("title", [
    "Technical Program Manager Intern - Summer 2027, University Recruiting",   # program label, not a staff job
    "Product Manager Intern, Amazon University Talent Acquisition",
])
def test_program_labels_neither_make_a_staff_job_nor_exclude(rules, title):
    m = ev(rules, title)
    assert m.matched, m.reasons


def test_real_staff_jobs_about_interns_still_reject(rules):
    assert not ev(rules, "Senior Program Specialist - Intern & Keep Warm Programs").matched
    assert not ev(rules, "University Recruiter, Campus Recruiting").matched


@pytest.mark.parametrize("key,title", [
    ("linkedin", "LinkedIn First Play Program - Software Engineering"),
    ("citadel", "Launch: Software Engineering (US)"),
    ("uber", "2027 Uber STAR Program, Software Engineering"),
    ("uber", "UberSTAR Software Engineering"),
    ("microsoft", "Explore - Software Engineering"),
])
def test_named_sophomore_programs_count_without_the_word_intern(rules, key, title):
    from internwatch.config import load_companies
    c = next(c for c in load_companies(Path(__file__).resolve().parents[1] / "config" / "companies.yaml") if c.key == key)
    m = evaluate(Job(id="x", title=title, location="New York, NY"), rules, category=c.category, locations=c.locations,
                 extra_role_keywords=c.extra_role_re)
    assert m.matched and "freshman/sophomore" in m.tags, m.reasons


# ---------------------------------------------------------------------------------------------
# runner, multi-source baselines and re-used ids

DAILY = RunOptions(daily=True, send=False, crosscheck=False, scheduled_mail=False, retry_delay=0)


def _runner(cfg, script):
    db = DB(cfg.settings.path("db"))
    r = Runner(cfg, db=db, checker_fn=FakeChecker(script))
    r.online = lambda: True
    return r, db


def _morning_html(db) -> str:
    path = db.one("SELECT path FROM emails WHERE kind='morning' ORDER BY id DESC LIMIT 1")["path"]
    return Path(path).with_suffix(".html").read_text()


def test_a_sources_first_answer_is_shown_once_as_already_open(make_cfg):
    cfg = make_cfg([company("acme")])
    seed = [job("1", "Ops Analyst")]
    later = seed + [job("ripplematch:9", "Software Engineering Intern, Summer 2027", extra={"baseline": True})]
    r, db = _runner(cfg, {"acme": [seed, later]})
    r.run(DAILY)
    r.run(DAILY)
    row = db.job("acme", "ripplematch:9")
    assert row["baseline"] == 1 and row["notified_at"] is not None          # in this morning's email, once
    html = _morning_html(db)
    assert "Already open (1)" in html and "Software Engineering Intern, Summer 2027" in html
    assert "no new roles" in db.q("SELECT subject FROM emails WHERE kind='morning' ORDER BY id")[-1]["subject"]


class _Src:
    def __init__(self, jobs=(), fail=False, kind="fake", settings=None):
        self.jobs, self.fail, self.type, self.supports_detail, self.settings = list(jobs), fail, kind, False, settings or {}

    def fetch(self, http, s, ctx=None):
        if self.fail:
            raise FetchError("down")
        return [job(j.id, j.title, j.location) for j in self.jobs]


def _multi(monkeypatch, srcs, state=None, s=None):
    monkeypatch.setattr(Multi, "_sources", lambda self, _: [(i, x, x.settings) for i, x in enumerate(srcs)])
    ctx = FetchContext(state=dict(state or {}))
    return Multi().fetch(None, s or {}, ctx), ctx


def test_sources_are_remembered_by_identity_not_position(monkeypatch):
    workday = _Src([job("w1", "Software Engineer Intern")], kind="workday", settings={"tenant": "x"})
    ripple = _Src([job("r1", "Data Intern")], kind="ripplematch", settings={"company_id": 1})
    _, ctx = _multi(monkeypatch, [workday, ripple])
    # a source inserted in front: the two known sources keep answering as known, only the new one is a baseline
    phenom = _Src([job("p1", "ML Intern")], kind="phenom", settings={"ref": "y"})
    jobs, ctx2 = _multi(monkeypatch, [phenom, workday, ripple], ctx.state)
    flagged = {j.id for j in jobs if j.extra.get("baseline")}
    assert flagged == {"p1"}, flagged
    assert len(ctx2.state["ok_source_ids"]) == 3


def test_state_saved_by_position_is_migrated(monkeypatch):
    a = _Src([job("a", "A")], kind="workday", settings={"t": 1})
    b = _Src([job("b", "B")], kind="ripplematch", settings={"c": 2})
    jobs, ctx = _multi(monkeypatch, [a, b], {"ok_sources": [0, 1]})
    assert not any(j.extra.get("baseline") for j in jobs)
    assert "ok_sources" not in ctx.state and len(ctx.state["ok_source_ids"]) == 2



def test_a_matched_id_reused_for_the_next_cycle_is_emailed_again(make_cfg):
    cfg = make_cfg([company("acme")])
    seed = [job("1", "Ops Analyst")]
    y1 = seed + [job("42", "Software Engineer Intern - Summer 2027")]
    y2 = seed + [job("42", "Software Engineer Intern - Summer 2028")]
    r, db = _runner(cfg, {"acme": [seed, y1, y2]})
    r.run(DAILY)
    r.run(DAILY)
    s = r.run(DAILY)
    row = db.job("acme", "42")
    assert s.new_matches == 1 and row["term"] == "Summer 2028" and "new term" in json.loads(row["tags"])
    assert "Software Engineer Intern - Summer 2028" in _morning_html(db)


def test_a_matched_posting_reopened_after_weeks_is_emailed_again(make_cfg):
    cfg = make_cfg([company("acme")])
    seed = [job("1", "Ops Analyst")]
    open_ = seed + [job("42", "Software Engineer Intern")]
    r, db = _runner(cfg, {"acme": [seed, open_, seed, open_, seed, open_]})
    r.run(DAILY)
    r.run(DAILY)                                       # emailed
    r.run(DAILY)                                       # closed
    s = r.run(DAILY)                                   # back the next day: a scan that missed it, not a reopening
    assert s.new_matches == 0
    r.run(DAILY)                                       # closed again …
    db.conn.execute("UPDATE jobs SET removed_at=? WHERE job_id='42'", (iso(utcnow() - timedelta(days=20)),))
    s = r.run(DAILY)                                   # … and open again three weeks later
    assert s.new_matches == 1 and "reopened" in json.loads(db.job("acme", "42")["tags"])


def test_a_retitle_without_a_new_term_is_not_emailed_again(make_cfg):
    cfg = make_cfg([company("acme")])
    seed = [job("1", "Ops Analyst")]
    a = seed + [job("42", "Software Engineer Intern - Summer 2027")]
    b = seed + [job("42", "Software Engineer Intern – Summer 2027 (NYC)")]
    r, db = _runner(cfg, {"acme": [seed, a, b]})
    r.run(DAILY)
    r.run(DAILY)
    assert r.run(DAILY).new_matches == 0


def test_an_old_simplify_twin_does_not_swallow_a_new_posting(make_cfg):
    from internwatch.models import Match
    cfg = make_cfg([company("acme")])
    t = "Software Engineer Intern - Summer 2027"
    seen = [job("10", t, "Seattle, WA")]
    r, db = _runner(cfg, {"acme": [seen, seen + [job("11", t, "New York, NY")]]})
    r.run(DAILY)
    db.add_external_job("acme", Job(id="simplify:abc", title=t, url="https://simplify.jobs/p/abc"),
                        iso(utcnow() - timedelta(days=60)), Match(True, field="SWE"), source="simplify")
    db.conn.execute("UPDATE jobs SET notified_at=first_seen WHERE job_id='simplify:abc'")
    s = r.run(DAILY)
    assert s.new_matches == 1 and db.job("acme", "11")["repost_of"] != "simplify:abc"


def test_a_detail_page_the_parser_cannot_handle_does_not_hide_the_job(make_cfg, monkeypatch):
    from internwatch.adapters import base
    from internwatch.runner import run_checker

    class Crashy(base.Checker):
        type, supports_detail = "crashy-test", True

        def fetch(self, http, s, ctx=None):
            return [job("1", "Software Engineer Intern", "")]   # vague location → its job page is read

        def detail(self, http, s, j):
            raise AttributeError("'str' object has no attribute 'get'")

    monkeypatch.setitem(base.REGISTRY, "crashy-test", Crashy)
    cfg = make_cfg([company("acme", checker="crashy-test")])
    o = run_checker(cfg, cfg.companies[0], detail_limit=5)
    assert o.ok and [j.id for j in o.jobs] == ["1"] and o.detail_errors


# ---------------------------------------------------------------------------------------------
# cross-check: a Simplify row is only "found" by title when a current posting has that title

def _stored(db, jid, title, removed_days_ago=None):
    from internwatch.models import Match
    db.upsert_jobs("acme", [job(jid, title)], iso(utcnow() - timedelta(days=200)))
    db.set_match("acme", jid, Match(True, field="SWE"), True)
    if removed_days_ago is not None:
        db.conn.execute("UPDATE jobs SET removed_at=? WHERE job_id=?", (iso(utcnow() - timedelta(days=removed_days_ago)), jid))


@pytest.mark.parametrize("stored,removed_days_ago,listed,found", [
    ("Software Engineer Intern - Summer 2027", 60, "Software Engineer Intern (Summer 2028)", False),  # last cycle
    ("Software Engineer Intern - Summer 2027", None, "Software Engineer Intern (Summer 2028)", False),  # other year
    ("Software Engineer Intern", None, "Software Engineer Intern", True),
    ("Software Engineer Intern - Summer 2028", 5, "Software Engineer Intern (Summer 2028)", True),     # just closed
])
def test_crosscheck_title_match_needs_a_current_posting(memdb, stored, removed_days_ago, listed, found):
    from internwatch.crosscheck import Row, find_in_db
    _stored(memdb, "111", stored, removed_days_ago)
    hit, how = find_in_db(memdb, "acme", Row("summer", "k", "Acme", listed, "New York, NY", "https://x/jobs/999", "",
                                             "Software Engineering"))
    assert (hit is not None) == found and (how == "title" if found else how == "")


@pytest.mark.parametrize("title,kept", [
    ("Data Engineer Internship - 2027 (US)", True),         # unflagged, outside the student categories
    ("Mechatronic Apprentice I, RIC6 RME", True),
    ("2027 Discovery-Program: Software Engineering", True),
    ("Senior Vendor Manager, US Apparel", False),           # "discovery events" only in its description
])
def test_amazon_keyword_hits_are_kept_by_their_title(title, kept):
    from internwatch.checkers.amazon import KEYWORDS, title_words
    assert bool(title_words(KEYWORDS).search(title)) == kept


# ---------------------------------------------------------------------------------------------
# second audit (October 21)

@pytest.mark.parametrize("title,matched", [
    ("Software Engineer Intern, Partner Programs", True),          # starts as a student role
    ("Co-op Student, Partner Programs", True),                     # "Co-op" is not split at its hyphen
    ("Data Science Intern (Partner Programs)", True),
    ("Senior Program Specialist - Intern & Keep Warm Programs", False),   # a staff job running a program
    ("Principal Programs Lead - Intern Program", False),
    ("Intern Program Manager, University Programs", False),        # explicit staff phrase
    ("University Recruiter, Campus Recruiting", False),
])
def test_staff_rule_only_applies_when_the_title_does_not_start_as_a_student_role(rules, title, matched):
    assert ev(rules, title).matched == matched


@pytest.mark.parametrize("title,matched", [
    ("Software Engineer Intern (Grad 2029)", True),
    ("Software Engineer Intern - Expected Graduation: 2029", True),
    ("Software Engineer Intern, Class 2029", True),
    ("Software Engineer Intern (Graduating in 2029 or 2030)", True),
    ("Software Engineer Intern (Graduating 2029-2030)", True),
    ("Software Engineer Intern (Graduating in 2026)", False),     # graduates before your window: still rejects
    ("Software Engineer Intern, Class 2026", False),
])
def test_more_graduation_wordings_are_not_read_as_terms(rules, title, matched):
    assert ev(rules, title, "Austin, TX").matched == matched


@pytest.mark.parametrize("location,country", [
    # US places that read as foreign before
    ("Hunt Valley, Cockeysville, MD", "US"), ("University Park, State College, PA", "US"), ("Malta, NY", "US"),
    ("Lebanon, NH", "US"), ("West Jordan, UT", "US"), ("Panama City, FL", "US"), ("Jamaica, Queens, NY", "US"),
    ("Carmel, Hamilton County, IN", "US"), ("Pleasanton, Alameda County, CA", "US"),
    # guards: these must not move
    ("Chisinau, Chisinau Municipality, MD", "MD"), ("Tel Aviv-Yafo, Tel Aviv District, IL", "IL"),
    ("Bengaluru, Karnataka, IN", "IN"), ("London, ON", "CA"), ("Dublin, CA", "US"), ("Paris, TX", "US"),
    ("Toronto, Ontario, CA", "CA"), ("Vancouver, British Columbia, CA", "CA"), ("Valletta, Malta, MT", "MT"),
    ("Panama City, Panama, PA", "PA"), ("Doha, Doha Municipality, QA", "QA"),
])
def test_us_state_codes_that_are_also_country_codes(location, country):
    from internwatch.locations import countries
    assert sorted(countries(location)[0]) == [country]


def _rate_limited_client(monkeypatch, retry_after=None, deadline=None):
    import httpx
    import internwatch.http as hmod
    sleeps = []
    monkeypatch.setattr(hmod.time, "sleep", lambda s: sleeps.append(round(s, 2)))
    monkeypatch.setattr(hmod.random, "random", lambda: 0.5)          # backoff jitter factor 1.0
    calls = []

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        calls.append(req.url.path)
        return httpx.Response(429, headers={"retry-after": str(retry_after)} if retry_after else {})

    h = hmod.Http(hmod.HttpSettings(backoff_base=2, min_interval=0, retries=3), gate=hmod.HostGate(), deadline=deadline)
    h._client = httpx.Client(transport=httpx.MockTransport(handler))
    return h, calls, sleeps


def test_429_keeps_every_wait_between_attempts_but_not_after_the_last(monkeypatch):
    from internwatch.models import FetchError
    h, calls, sleeps = _rate_limited_client(monkeypatch)
    with pytest.raises(FetchError, match="429"):
        h.get("https://x.test/jobs")
    assert len(calls) == 4                                   # the same 4 attempts
    assert sleeps == [30, 2.0, 60, 6.0, 90, 18.0]            # waits before attempts 2-4; none after the 4th


def test_retry_after_is_honoured_except_after_the_last_attempt(monkeypatch):
    from internwatch.models import FetchError
    h, calls, sleeps = _rate_limited_client(monkeypatch, retry_after=5)
    with pytest.raises(FetchError):
        h.get("https://x.test/jobs")
    assert len(calls) == 4 and sleeps == [5, 2.0, 5, 6.0, 5, 18.0]


def test_a_429_wait_never_runs_past_the_check_deadline(monkeypatch):
    import time as _t
    from internwatch.models import CheckTimeout, FetchError
    h, calls, sleeps = _rate_limited_client(monkeypatch, deadline=_t.monotonic() + 10)
    with pytest.raises((FetchError, CheckTimeout)):
        h.get("https://x.test/jobs")
    assert sleeps and max(sleeps) <= 10


class _Crashy(_Src):
    def fetch(self, http, s, ctx=None):
        raise ValueError("unexpected page shape")


def test_a_crashing_source_keeps_the_other_sources_jobs(monkeypatch):
    workday = _Src([job("w1", "Software Engineer Intern")], kind="workday", settings={"t": 1})
    jobs, ctx = _multi(monkeypatch, [workday, _Crashy(kind="ripplematch", settings={"c": 2})])
    assert [j.id for j in jobs] == ["w1"] and "ripplematch: crashed: ValueError" in ctx.degraded
    jobs, ctx = _multi(monkeypatch, [_Crashy(kind="ripplematch", settings={"c": 2}), workday])
    assert [j.id for j in jobs] == ["workday:w1"] and "crashed" in ctx.degraded   # first source crashing too


def test_every_source_crashing_still_fails_the_check(monkeypatch):
    with pytest.raises(ValueError):
        _multi(monkeypatch, [_Crashy(kind="a", settings={"x": 1}), _Crashy(kind="b", settings={"y": 2})])


def test_each_source_is_read_at_its_own_pace(monkeypatch):
    class FakeHttp:
        min_interval = None
    seen = {}

    class Paced(_Src):
        def fetch(self, http, s, ctx=None):
            seen[self.type] = http.min_interval
            return super().fetch(http, s, ctx)

    srcs = [Paced([job("w1", "A")], kind="workday", settings={"t": 1}),
            Paced([job("e1", "B")], kind="eightfold", settings={"host": "jobs.autodesk.com", "min_interval": 2.5})]
    http = FakeHttp()
    monkeypatch.setattr(Multi, "_sources", lambda self, _: [(i, x, x.settings) for i, x in enumerate(srcs)])
    Multi().fetch(http, {}, FetchContext())
    assert seen == {"workday": None, "eightfold": 2.5} and http.min_interval is None   # restored afterwards


def test_a_short_microsoft_scan_keeps_its_jobs_and_is_reported():
    from internwatch.models import ShapeError
    from test_adapter_fixes import cassette, replay

    def cut(e):  # the full listing's page at start=500 comes back empty: the walk stops there
        if "query=&" in e["url"] and e["url"].endswith("&start=500"):
            e["text"] = '{"status": 200, "data": {"positions": [], "count": 2411}}'
    ctx = FetchContext()
    jobs = replay("microsoft", cut, ctx=ctx)
    total = cassette("microsoft").meta["count"]
    assert 500 <= len(jobs) < total * 0.9 and "pagination incomplete" in ctx.degraded
    assert any("intern" in j.title.lower() for j in jobs)          # the internship filters were kept
    with pytest.raises(ShapeError):                                # without a context: fails as before
        replay("microsoft", cut)


def _drop_first_path():
    """An edit for replay(): the first listed posting comes back without its path (caught mid-edit)."""
    done = []

    def edit(e):
        if "/jobs" in e["url"] and '"offset":0' in (e.get("body") or "").replace(" ", "") and not done:
            d = json.loads(e["text"])
            if d.get("jobPostings"):
                d["jobPostings"][0].pop("externalPath", None)
                e["text"] = json.dumps(d)
                done.append(1)
    return edit


def test_workday_reports_postings_it_had_to_skip():
    from test_adapter_fixes import cassette, replay
    ctx = FetchContext()
    jobs = replay("crowdstrike", _drop_first_path(), ctx=ctx)
    assert len(jobs) == cassette("crowdstrike").meta["count"] - 1 and "skipped 1 postings" in ctx.degraded
    assert len(replay("crowdstrike", _drop_first_path())) == len(jobs)   # no context: silent, as before


class _TimesOut:
    """An Http that runs out of time after `after` searches."""
    def __init__(self, inner, after):
        self.inner, self.after, self.n = inner, after, 0

    def post_json(self, *a, **kw):
        from internwatch.models import CheckTimeout
        self.n += 1
        if self.n > self.after:
            raise CheckTimeout("check ran past its time budget")
        return self.inner.post_json(*a, **kw)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def test_workday_out_of_time_keeps_what_it_read():
    from internwatch.adapters import get_checker
    from internwatch.http import Http
    from internwatch.models import CheckTimeout
    from test_adapter_fixes import cassette
    cas = cassette("crowdstrike")
    ctx = FetchContext()
    jobs = get_checker("workday").fetch(_TimesOut(Http(replay=cas), 3), cas.meta["settings"], ctx)
    assert len(jobs) == 60 and "ran out of time after 60 jobs" in ctx.degraded and ctx.partial
    with pytest.raises(CheckTimeout):                                  # no context: fails as before
        get_checker("workday").fetch(_TimesOut(Http(replay=cas), 3), cas.meta["settings"], None)


def test_after_a_cut_short_first_read_the_rest_comes_once_as_already_open(make_cfg):
    from internwatch.health import Outcome
    cfg = make_cfg([company("acme")])
    first = [job("1", "Ops Analyst"), job("2", "Software Engineer Intern")]
    full = first + [job("3", "Data Science Intern")]                    # open all along, missed by the first read
    later = full + [job("4", "Machine Learning Intern")]                 # genuinely new
    script = iter([(first, True), (full, False), (later, False)])

    def checker_fn(cfg, c, **kw):
        jobs, partial = next(script)
        return Outcome(company=c, mode="full", jobs=list(jobs), started_at=iso(), state={},
                       degraded="ran out of time" if partial else None, partial=partial)
    db = DB(cfg.settings.path("db"))
    r = Runner(cfg, db=db, checker_fn=checker_fn)
    r.online = lambda: True
    once = RunOptions(force=True, send=False, crosscheck=False, scheduled_mail=False)   # one pass, no same-run retry
    r.run(once)                                            # seeded from a cut-short read
    assert db.get("partial_seed:acme")
    r.run(once)                                            # the complete read
    html = Path(db.one("SELECT path FROM emails WHERE kind='new' ORDER BY id DESC")["path"]).with_suffix(".html").read_text()
    assert db.job("acme", "3")["baseline"] == 1 and "Already open (1)" in html
    assert not db.get("partial_seed:acme")
    s = r.run(once)
    assert s.new_matches == 1 and db.job("acme", "4")["baseline"] == 0


def _tmobile_facets(change):
    """An edit for replay(): rewrite the timeType facet on each partition's first page."""
    def edit(e):
        if '"offset":0' in (e.get("body") or "").replace(" ", ""):
            d = json.loads(e["text"])
            for f in d.get("facets") or []:
                if f.get("facetParameter") == "timeType":
                    change(f["values"])
            e["text"] = json.dumps(d)
    return edit


def test_tmobile_partitions_that_miss_a_new_time_type_are_reported():
    from test_adapter_fixes import replay
    ctx = FetchContext()
    jobs = replay("t-mobile", _tmobile_facets(lambda v: v.append({"id": "seasonal", "descriptor": "Seasonal",
                                                                     "count": 15})), ctx=ctx)
    assert len(jobs) == 2533 and "no partition reads timeType Seasonal (15 jobs)" in ctx.degraded


def test_tmobile_partitions_short_of_the_counts_are_reported_but_normal_drift_is_not():
    from test_adapter_fixes import replay

    def bump(by):
        def change(vals):
            vals[0]["count"] += by
        return change
    ctx = FetchContext()
    replay("t-mobile", _tmobile_facets(bump(30)), ctx=ctx)             # within the 1.5% tolerance: normal churn
    assert not ctx.degraded
    replay("t-mobile", _tmobile_facets(bump(200)), ctx=ctx)            # 200 jobs nobody read
    assert "partitioned by timeType" in ctx.degraded
    replay("t-mobile", _tmobile_facets(bump(200)))                     # no context: silent, as before


def test_amazon_stuck_paging_is_reported_and_stops():
    import copy
    from internwatch.adapters import get_checker
    from internwatch.http import Cassette, Http
    from test_adapter_fixes import cassette
    cas = cassette("amazon")
    ex = copy.deepcopy(cas.exchanges)
    flags = [e for e in ex if '"jobTypeFacets":[{"name":"isIntern"' in (e.get("body") or "")]
    by_start = {json.loads(e["body"])["start"]: e for e in flags}
    by_start[200]["text"] = by_start[0]["text"]                  # page 2 of the flagged-intern search repeats page 1
    ctx = FetchContext()
    jobs = get_checker("amazon").fetch(Http(replay=Cassette(exchanges=ex)), cas.meta["settings"] or {}, ctx)
    assert "returned the same page twice" in ctx.degraded and ctx.partial
    assert len(jobs) < cas.meta["count"]


def test_apple_rows_short_of_the_total_are_reported():
    import copy
    from internwatch.adapters import get_checker
    from internwatch.http import Cassette, Http
    from test_adapter_fixes import cassette
    cas = cassette("apple")
    ex = copy.deepcopy(cas.exchanges)
    team = [e for e in ex if '"subTeam":"subTeam-INTRN"' in (e.get("body") or "")]
    by_page = {json.loads(e["body"])["page"]: e for e in team}
    by_page[3]["text"] = by_page[1]["text"]       # page 3 repeats page 1 (not in a row): 20 rows never read
    ctx = FetchContext()
    get_checker("apple").fetch(Http(replay=Cassette(exchanges=ex)), cas.meta["settings"] or {}, ctx)
    assert "apple: internships rows" in ctx.degraded and "same page twice" not in ctx.degraded and ctx.partial


def test_student_search_words_cover_every_strong_student_word_in_filters_yaml():
    import re as _re
    import yaml
    from internwatch.adapters.base import STUDENT_SEARCH_WORDS
    from internwatch.checkers import amazon, apple
    norm = lambda w: _re.sub(r"[\s\-*]+", "", w.lower())                      # noqa: E731
    strong = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "filters.yaml").read_text())["role"]["strong"]
    missing = [w for w in strong if norm(w) not in {norm(x) for x in STUDENT_SEARCH_WORDS}]
    assert not missing, f"add a search word for {missing} to STUDENT_SEARCH_WORDS in adapters/base.py"
    assert set(STUDENT_SEARCH_WORDS) <= set(amazon.KEYWORDS)
    assert {f"keyword:{w}" for w in STUDENT_SEARCH_WORDS} <= {name for name, _ in apple.QUERIES}


def test_a_keyword_search_over_amazons_cap_is_skipped_not_fatal():
    from internwatch.adapters import get_checker

    class Capped:
        def post_json(self, url, json=None, headers=None):
            if json["query"] == "students":
                return {"found": 10000, "searchHits": [{"fields": {"icimsJobId": ["1"], "title": ["Students Intern"]}}]}
            return {"found": 0, "searchHits": None}
    ctx = FetchContext()
    get_checker("amazon").fetch(Capped(), {"keywords": ["students", "intern"]}, ctx)
    assert "keyword search keyword:students matches 10000+ jobs" in ctx.degraded
    with pytest.raises(Exception):                                   # no context: fails as before
        get_checker("amazon").fetch(Capped(), {"keywords": ["students"]}, None)


def test_a_long_untracked_list_is_capped_in_the_body_and_attached(make_cfg):
    from internwatch import emails
    cfg = make_cfg([company("acme")])
    untracked = [{"company": f"Co{i:02d}", "title": f"SWE Intern {i}", "location": "NYC", "category": "Software Engineering",
                  "url": f"https://x/{i}"} for i in range(40)]
    subject, text, html, files = emails.digest(cfg, [], untracked, [], [], morning=True)
    assert "SWE Intern 24" in html and "SWE Intern 25" not in html and "and 15 more" in html and "and 15 more" in text
    names = {f[0]: f[1] for f in files}
    assert "SWE Intern 39" in names["untracked-roles.html"].decode()
    assert names["untracked-roles.csv"].decode().count("\n") == 41            # header + every role
    short = emails.digest(cfg, [], untracked[:10], [], [], morning=True)
    assert len(short) == 3                                                    # no attachment for a short list
