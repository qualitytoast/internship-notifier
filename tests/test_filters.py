"""The matching rules: role type, term, field and location, with the bias toward including unsure roles."""
import pytest

from internwatch.filters import decide_term, evaluate, extract_terms, is_student_role, kw_regex
from internwatch.models import Job


def ev(rules, title, location="New York, NY", **kw):
    category = kw.pop("category", "")
    locations = kw.pop("locations", None)
    return evaluate(Job(id="x", title=title, location=location, **kw), rules, category=category, locations=locations)


@pytest.mark.parametrize("title,term,field", [
    ("Software Engineer Intern (Summer 2027)", "Summer 2027", "SWE"),
    ("Software Engineering Internship - Fall 2027", "Fall 2027", "SWE"),
    ("Machine Learning Co-op, Spring 2028", "Spring 2028", "ML/AI"),
    ("Data Science Intern", "unspecified", "Data"),
    ("Quantitative Trader Intern", "unspecified", "Quant"),
    ("Research Engineer Intern, Summer 2028", "Summer 2028", "Research"),
    ("Student Researcher, BS/MS, Winter-Summer 2027", "Summer 2027", "Research"),
    ("2027 Summer Internship Program – Systematic Trading, New York", "Summer 2027", "Quant"),
    ("Off-Cycle Quantitative Research Intern", "unspecified", "Quant"),
    ("Apprentice Software Developer", "unspecified", "SWE"),
    ("Thrive Program - Software Engineer", "unspecified", "SWE"),
    ("Software Engineer Intern - Summer 2026 / Summer 2027", "Summer 2027", "SWE"),
    ("Software Engineer Intern 2027", "2027", "SWE"),
    # program labels are not the job's function (Amazon, Coinbase)
    ("2027 Applied Science Internship - Computer Vision - United States, PhD Student Science Recruiting", "2027", "ML/AI"),
    ("2027 Research Science Internship - United States, PhD Student Science Recruiting", "2027", "Research"),
    ("2027 Applied Science Internship - United States - Master's Student Science Recruiting", "2027", "Research"),
    ("Forward Deployed Engineer Intern - Campus Recruiting 2027", "2027", "SWE"),
    ("Forward Deployed Engineer Intern (HR Technology)", "unspecified", "SWE"),
    ("Talent Acquisition Data Engineering & Analytics Intern", "unspecified", "Data"),
])
def test_matches(rules, title, term, field):
    m = ev(rules, title)
    assert m.matched, m.reasons
    assert m.term == term
    assert m.field == field


@pytest.mark.parametrize("title,why", [
    ("Software Engineer, New Grad 2027", "new grad"),
    ("Software Engineer II", "not a student role"),
    ("Software Engineer Intern - Summer 2026", "Summer 2026"),
    ("Marketing Intern, Summer 2027", "excluded field"),
    ("HR Intern", "excluded field"),
    ("Legal Intern", "excluded field"),
    ("Sales Engineering Intern", "excluded field"),
    ("International Tax Intern", "excluded field"),
    ("Controllers Summer Analyst 2027", "excluded field"),
    ("University Recruiter", "staff role"),
    ("Internship Program Manager", "staff role"),
    ("Area Project Controls Lead, Mega Campus", "not a student role"),
    ("Internal Audit Associate", "not a student role"),
    ("UX Research Intern", "excluded field"),
    ("Campus Recruiting Intern", "excluded field"),
    ("Mechanical Engineering Intern", "excluded field"),
    ("Sales Engineer - Intern, Cloud Security", "excluded field"),
])
def test_rejects(rules, title, why):
    m = ev(rules, title)
    assert not m.matched
    assert why.lower() in " ".join(m.reasons).lower()


@pytest.mark.parametrize("title,category", [
    ("Discovery Program: Quantitative Trading and Quantitative Strategy Development (On-site)", "quant"),  # SIG
    ("Career Discovery Program 2027 – Software Development - Seattle", ""),                       # Expedia
    ("Explore Program (Second-Year Students)", ""),                                               # Microsoft
    ("First Year Trading and Technology Program", "quant"),                                       # Jane Street
    ("Sophomore Summit - Technology", ""),
    ("Point72 Academy Coffee Chats — Class of 2029 (US)", "quant"),
])
def test_freshman_sophomore_programs_are_student_roles_and_tagged(rules, title, category):
    m = ev(rules, title, category=category)
    assert m.matched and "freshman/sophomore" in m.tags, m.reasons


def test_company_program_names_and_descriptions_tag_freshman_sophomore(rules):
    ignite = kw_regex(["ignite"])
    m = evaluate(Job(id="1", title="NVIDIA Ignite Program - Software Engineering", location="Santa Clara, CA"), rules,
                 extra_role_keywords=ignite)
    assert m.matched and m.field == "SWE" and "freshman/sophomore" in m.tags
    m = ev(rules, "Software Engineer Intern", snippet="Open to first- and second-year students.")
    assert "freshman/sophomore" in m.tags
    assert "freshman/sophomore" not in ev(rules, "Software Engineer Intern").tags
    assert "freshman/sophomore" not in ev(rules, "PhD Discovery Summit", category="quant").tags


@pytest.mark.parametrize("title,why", [
    ("Product Discovery Program Manager", "not a student role"),        # a staff job, not a program
    ("Applied Scientist - Class of 2028 / Full-Time", "new grad"),
    ("Software Engineer - Class of 2026", "not a student role"),
])
def test_program_words_in_staff_or_full_time_titles_do_not_count(rules, title, why):
    m = ev(rules, title)
    assert not m.matched and why in " ".join(m.reasons)


def test_graduation_year_is_not_a_term(rules):
    m = ev(rules, "Software Engineer Intern (Class of 2029)")
    assert m.matched and m.term == "unspecified"
    assert ev(rules, "Software Engineer Intern - 2029 Grads").matched
    assert not ev(rules, "Software Engineer Intern - Class of 2026").matched   # a past class still rejects
    assert ev(rules, "2027 Software Engineer Intern (Class of 2029)").term == "2027"


@pytest.mark.parametrize("title", ["Policy Engineering Intern", "Finance Engineer Intern"])
def test_engineering_role_in_an_excluded_area_is_included_but_unsure(rules, title):
    m = ev(rules, title)
    assert m.matched and m.unsure, m.reasons


def test_unclear_field_is_included_and_tagged_unsure(rules):
    m = ev(rules, "Product Management Intern")
    assert m.matched and m.unsure and "field?" in m.tags


def test_quant_firm_generic_title_is_quant_but_unsure(rules):
    m = ev(rules, "Summer Intern", category="quant")
    assert m.matched and m.unsure and m.tags[0] == "Quant?"


def test_department_decides_generic_titles(rules):
    assert ev(rules, "Summer Intern", department="Engineering").field == "SWE"
    assert not ev(rules, "Intern", department="Marketing").matched


def test_weak_campus_hint_is_unsure(rules):
    m = ev(rules, "Campus Hire - Software Engineer")
    assert m.matched and m.unsure and "role?" in m.tags


def test_employment_type_from_hiring_system_counts(rules):
    j = Job(id="1", title="Student Researcher", location="Mountain View, CA, USA", employment_type="INTERN")
    assert is_student_role(j, rules)
    j2 = Job(id="2", title="Business Analyst", employment_type="Intern (Summer Analyst)")
    assert is_student_role(j2, rules)


def test_intern_does_not_match_internal_or_international(rules):
    assert not is_student_role(Job(id="1", title="Internal Tools Engineer"), rules)
    assert not is_student_role(Job(id="2", title="International Payments Engineer"), rules)


# terms -------------------------------------------------------------------------------------

def test_missing_term_never_rejects(rules):
    m = ev(rules, "Software Engineer Intern")
    assert m.matched and m.term == "unspecified"


def test_winter_term_is_included_but_unsure(rules):
    m = ev(rules, "Software Engineering Intern (Winter 2027)")
    assert m.matched and m.unsure and "term?" in m.tags


def test_description_term_never_rejects(rules):
    t = decide_term("Software Engineer Intern", "Join us for Summer 2026 in Seattle.", rules)
    assert t.ok and t.unsure
    t = decide_term("Software Engineer Intern", "This is a Fall 2027 internship.", rules)
    assert t.ok and not t.unsure and t.term.startswith("Fall 2027")


@pytest.mark.parametrize("text,terms", [
    ("Fall 2027 / Spring 2028", ["Fall 2027", "Spring 2028"]),
    ("Summer & Fall 2027", ["Summer 2027", "Fall 2027"]),
    ("Intern - Summer '27", ["Summer 2027"]),
    ("2027 Summer Analyst", ["Summer 2027"]),
    ("Co-op (January 2028)", ["Spring 2028"]),
])
def test_term_extraction(text, terms):
    found, _ = extract_terms(text, title=True)
    assert found == terms


# locations ---------------------------------------------------------------------------------

@pytest.mark.parametrize("location,ok,unsure", [
    ("San Francisco, CA", True, False),
    ("Remote - US", True, False),
    ("New York, NY; London, UK", True, False),
    ("London, UK", False, False),
    ("Bengaluru, Karnataka, India", False, False),
    ("Toronto, ON", False, False),
    ("Remote", True, True),
    ("", True, True),
    ("3 Locations", True, True),
])
def test_location_default_us(rules, location, ok, unsure):
    m = ev(rules, "Software Engineer Intern", location=location)
    assert m.matched is ok
    if ok:
        assert m.unsure is unsure


def test_location_configurable_per_company(rules):
    assert ev(rules, "Software Engineer Intern", location="Toronto, ON", locations=["US", "CA"]).matched
    assert ev(rules, "Software Engineer Intern", location="London, UK", locations=["ANY"]).matched


# keyword syntax -----------------------------------------------------------------------------

def test_keyword_syntax():
    rx = kw_regex(["co op", "scien*", "controller"])
    assert rx.search("Co-op Student") and rx.search("coop") and rx.search("co op")
    assert rx.search("Data Scientist") and rx.search("science")
    assert rx.search("Controllers")  # plurals match automatically
    assert not rx.search("cooperative") and not rx.search("controllership")
    assert kw_regex(["hr"]).search("HR Intern") and not kw_regex(["hr"]).search("Student Worker (20 hrs/wk)")
