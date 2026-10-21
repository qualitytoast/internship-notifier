"""Fixes from the October 2026 coverage audit: roles that could miss the inbox although they were posted."""
import pytest

from internwatch.filters import evaluate
from internwatch.models import Job


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
    from pathlib import Path
    from internwatch.config import load_companies
    c = next(c for c in load_companies(Path(__file__).resolve().parents[1] / "config" / "companies.yaml") if c.key == key)
    m = evaluate(Job(id="x", title=title, location="New York, NY"), rules, category=c.category, locations=c.locations,
                 extra_role_keywords=c.extra_role_re)
    assert m.matched and "freshman/sophomore" in m.tags, m.reasons
