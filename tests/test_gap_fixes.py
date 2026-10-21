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


def test_title_dedupe_keeps_roles_that_differ_by_place_or_year(monkeypatch):
    workday = _Src([job("w1", "Intern, Software Engineering (Canada)", "Toronto, ON, Canada"),
                    job("w2", "Co-op, Software Engineering (Summer 2026)", "Milwaukee, WI"),
                    job("w3", "Intern, Data Science", "Pune, India"),
                    job("w4", "Co-op, Delivery - Projects (LCS)", "Mayfield Heights, Ohio, United States")],
                   kind="workday", settings={"t": 1})
    ripple = _Src([job("r1", "Intern, Software Engineering", "Milwaukee, WI, USA"),
                   job("r2", "Co-op, Software Engineering (Summer 2027)", "Milwaukee, WI, USA"),
                   job("r3", "Intern, Data Science", "Milwaukee, WI, USA"),
                   job("r4", "Co-Op, Delivery - Projects", "Mayfield Heights, OH, USA")],    # the same role
                  kind="ripplematch", settings={"c": 2})
    jobs, _ = _multi(monkeypatch, [workday, ripple], s={"dedupe_titles": True})
    assert {j.id for j in jobs} == {"w1", "w2", "w3", "w4", "ripplematch:r1", "ripplematch:r2", "ripplematch:r3"}


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
