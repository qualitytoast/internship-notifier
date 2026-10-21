"""Decide whether a posting is an internship you want: role type, field, term and location.

All keyword lists live in config/filters.yaml. Every decision records a human-readable reason,
and anything the rules are unsure about is included and tagged "unsure".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .locations import location_decision
from .models import Job, Match

SEASONS = {"spring": "Spring", "summer": "Summer", "fall": "Fall", "autumn": "Fall", "winter": "Winter"}
MONTH_SEASON = {"jan": "Spring", "feb": "Spring", "mar": "Spring", "apr": "Spring", "may": "Summer",
                "jun": "Summer", "jul": "Summer", "aug": "Summer", "sep": "Fall", "oct": "Fall",
                "nov": "Fall", "dec": "Fall"}
_S = r"(?:spring|summer|fall|autumn|winter)"
_SEP = r"(?:\s*(?:/|&|\+|,|-|–|—)\s*|\s+(?:and|or|to|through|thru)\s+)+"
_SEASON_YEAR = re.compile(rf"\b({_S}(?:{_SEP}{_S})*)\s*[,\-–]?\s*(?:of\s+)?(?:(20\d\d)|['’](\d\d))(?!\d)", re.I)
_YEAR_SEASON = re.compile(rf"(?<!\d)(20\d\d)\s*[,\-–]?\s*({_S})\b(?!\s*[,\-–/]?\s*(?:20\d\d|['’]\d\d))", re.I)
_MONTH_YEAR = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*,?\s*(20\d\d)(?!\d)", re.I)
_BARE_YEAR = re.compile(r"(?<![\d/])(20\d\d)(?![\d/])")
_PHD = re.compile(r"\bph\.?\s?d\b|\bdoctoral\b", re.I)
_MASTERS = re.compile(r"\bmaster'?s\b|\bm\.s\.(?=\W|$)|\bmsc\b", re.I)
_MULTI_LOC = re.compile(r"^\s*(\d+\s+locations?|multiple locations?|various locations?)\s*$", re.I)
_CLASS_OF = re.compile(r"\bclass\s+of\s+(20\d\d)\b", re.I)
# a graduation year, not a term: "Class of 2029", "2029 grads", "graduating in 2029"
_GRAD_YEAR = re.compile(r"\bclass\s+of\s+(20\d\d)\b|\b(20\d\d)\s+grad(?:uate)?s?\b|"
                        r"\bgraduat(?:es?|ing|ion)\s+(?:in\s+|year\s+|date\s+)?(20\d\d)\b", re.I)
# a description saying freshmen/sophomores may apply
_UNDERCLASS_TEXT = re.compile(
    r"\b(?:freshm[ae]n|sophomores?|underclass(?:m[ae]n)?|rising (?:sophomores?|juniors?)|"
    r"(?:first|second|1st|2nd)[\s\-]+year (?:students?|undergrad\w*|college|university)|"
    r"(?:first|1st)[\s\-]*(?:and|or|&|/|\+)[\s\-]*(?:second|2nd)[\s\-]*years?)\b", re.I)
# "…, PhD Student Science Recruiting", "…, Amazon University Talent Acquisition" (Amazon), "… - Campus Recruiting
# 2027": the hiring program, not the job
_PROGRAM_LABEL = re.compile(
    r"(?<=[,\-–—|(/:])\s*(?:(?:(?:ph\.?d|undergrad\w*|graduate|master['’]?s?|mba)\s+)?(?:student\s+)?"
    r"(?:science|campus|university|college|early[\s\-]careers?|student|intern\w*)\s+recruit(?:ing|ment)"
    r"|(?:amazon\s+)?university\s+talent\s+(?:acquisition|attraction))\b", re.I)
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE = rf"(?:(?:{_S}|{_MONTH})\s*,?\s*)?(20\d\d)"
# a graduation date or year written like a term: "Graduating Spring 2029", "Expected Graduation: May 2029", "Grad
# Date Dec 2028 - Jun 2029", "May 2029 grads", "Grad 2029", "Class 2029", "Graduating in 2029 or 2030"
_GRAD_DATE = re.compile(
    rf"\b(?:class(?:\s+of)?|(?:expected\s+)?grad(?:uat(?:es?|ing|ion)|s)?(?:\s+(?:date|year))?)\s*(?:in\s+|:\s*|-\s*)?"
    rf"{_DATE}(?:\s*(?:-|–|—|/|&|to|through|or|and)\s*{_DATE})?|\b{_DATE}\s+grad(?:uate)?s?\b", re.I)
# an academic year written as a range: "2026-27", "Winter 2026/2027", "Fall 2026/27"
_ACADEMIC_YEAR = re.compile(rf"\b(?:({_S})\s*)?20(\d\d)\s*[-–/]\s*(?:20)?(\d\d)(?!\d)", re.I)
# where a title's first part ends: a spaced dash, a comma, a bracket, a bar or a colon (not the hyphen in "Co-op")
_FIRST_SEGMENT = re.compile(r"\s+[-–—]\s+|\s*[,(|:]")


def kw_regex(words: list[str]) -> re.Pattern | None:
    """Compile a keyword list (see filters.yaml syntax) into one whole-word regex."""
    parts = []
    for w in words or []:
        w = str(w).strip().lower()
        if not w:
            continue
        star = w.endswith("*")
        w = w.rstrip("*")
        tokens = [t for t in re.split(r"[\s\-]+", w) if t]
        pat = r"[\s\-]?".join(re.escape(t) for t in tokens)
        # "*" = any word ending; otherwise plurals match too ("controller" also matches "controllers"),
        # except for two-letter abbreviations ("hr" must not match "20 hrs/wk")
        parts.append(pat + (r"[\w]*" if star else r"(?:e?s)?" if len(w) > 2 else ""))
    if not parts:
        return None
    parts.sort(key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])", re.I)


def _search(rx: re.Pattern | None, text: str):
    return rx.search(text) if (rx is not None and text) else None


def _all(rx: re.Pattern | None, text: str) -> list[re.Match]:
    return list(rx.finditer(text)) if (rx is not None and text) else []


def _outside(m: re.Match, spans: list[re.Match]) -> bool:
    return all(m.end() <= s.start() or m.start() >= s.end() for s in spans)


@dataclass
class Rules:
    role_strong: re.Pattern
    underclass: re.Pattern | None
    class_years: set[int]
    underclass_years: set[int]
    role_weak: re.Pattern | None
    role_weak_not: re.Pattern | None
    new_grad: re.Pattern | None
    staff_about: re.Pattern | None
    staff_words: re.Pattern | None
    staff_context: re.Pattern | None
    employment_types: re.Pattern | None
    term_include: list[str]
    term_unsure: list[str]
    include_years: set[int]
    fields: list[tuple[str, re.Pattern]]
    dept_fields: list[tuple[str, re.Pattern]]
    exclude_strong: re.Pattern | None
    exclude: re.Pattern | None
    keep_unsure: re.Pattern | None
    default_locations: list[str]

    @classmethod
    def from_dict(cls, d: dict) -> "Rules":
        role, terms, fields, excl = d["role"], d["terms"], d["fields"], d["exclude"]
        dept = fields.get("departments", {}) or {}
        return cls(
            role_strong=kw_regex(role["strong"]),
            underclass=kw_regex(role.get("underclassmen", [])),
            class_years={int(y) for y in role.get("class_years", [])},
            underclass_years={int(y) for y in role.get("underclass_years", [])},
            role_weak=kw_regex(role.get("weak", [])),
            role_weak_not=kw_regex(role.get("weak_not", [])),
            new_grad=kw_regex(role.get("new_grad", [])),
            staff_about=kw_regex(role.get("staff_about_interns", [])),
            staff_words=kw_regex(role.get("staff_words", [])),
            staff_context=kw_regex(role.get("staff_context", [])),
            employment_types=kw_regex(role.get("employment_types", [])),
            term_include=[t.title() for t in terms["include"]],
            term_unsure=[t.title() for t in terms.get("unsure", [])],
            include_years={int(y) for y in terms.get("include_years", [])},
            fields=[(name, kw_regex(words)) for name, words in fields.items() if name != "departments"],
            dept_fields=[(name, kw_regex(words)) for name, words in dept.items()],
            exclude_strong=kw_regex(excl.get("strong", [])),
            exclude=kw_regex(excl.get("fields", [])),
            keep_unsure=kw_regex(excl.get("keep_unsure", [])),
            default_locations=list(d.get("location", {}).get("default", ["US"])),
        )


@lru_cache(maxsize=4)
def load_rules(path: str) -> Rules:
    return Rules.from_dict(yaml.safe_load(Path(path).read_text()))


# ---------------------------------------------------------------------------------------------
# terms

def extract_terms(text: str, *, title: bool) -> tuple[list[str], set[int]]:
    """Explicit terms ("Summer 2027") and, for titles, bare years ("2027 Intern")."""
    terms: list[str] = []
    years_in_terms: set[int] = set()
    for m in _SEASON_YEAR.finditer(text or ""):
        year = int(m.group(2)) if m.group(2) else 2000 + int(m.group(3))
        for s in re.findall(_S, m.group(1), re.I):
            terms.append(f"{SEASONS[s.lower()]} {year}")
        years_in_terms.add(year)
    for m in _YEAR_SEASON.finditer(text or ""):
        terms.append(f"{SEASONS[m.group(2).lower()]} {m.group(1)}")
        years_in_terms.add(int(m.group(1)))
    bare: set[int] = set()
    if title:
        for m in _MONTH_YEAR.finditer(text or ""):
            terms.append(f"{MONTH_SEASON[m.group(1).lower()[:3]]} {m.group(2)}")
            years_in_terms.add(int(m.group(2)))
        bare = {int(y) for y in _BARE_YEAR.findall(text or "")} - years_in_terms
    return list(dict.fromkeys(terms)), bare


@dataclass
class TermResult:
    ok: bool
    term: str = "unspecified"
    unsure: bool = False
    reason: str = ""


def decide_term(title: str, snippet: str, rules: Rules) -> TermResult:
    res = _decide_term(title, snippet, rules)
    if res.ok:
        return res
    # Before rejecting, read the title once more without what only looks like a term: a graduation date
    # ("Graduating Spring 2029") and an academic year written as a range ("Winter 2026/2027", "2026-27" →
    # both years). This can only rescue a title, never reject one the rule above accepts.
    alt = _ACADEMIC_YEAR.sub(_academic_years, _without_grad_dates(title, rules))
    if alt != title:
        again = _decide_term(alt, snippet, rules)
        if again.ok:
            return again
    return res


def _academic_years(m: re.Match) -> str:
    season, a, b = m.group(1), int(m.group(2)), int(m.group(3))
    if b != a + 1:  # "2026-12" is not an academic year
        return m.group(0)
    return f"{season} 20{a:02d} / {season} 20{b:02d}" if season else f"20{a:02d} 20{b:02d}"


def _without_grad_dates(title: str, rules: Rules) -> str:
    """Drop graduation dates in or after your window ("Graduating Spring 2029"); earlier ones ("Graduating Spring
    2026") stay and still reject, like "Class of 2026"."""
    first = min(rules.include_years, default=0)
    return _GRAD_DATE.sub(lambda m: " " if min(int(y) for y in m.groups() if y) >= first else m.group(0), title)


def _decide_term(title: str, snippet: str, rules: Rules) -> TermResult:
    terms, years = extract_terms(title, title=True)
    if rules.include_years:  # "Class of 2029" is a graduation year: it never rejects the role
        grad = {int(y) for m in _GRAD_YEAR.finditer(title) for y in m.groups() if y}
        years -= {y for y in grad if y >= min(rules.include_years)} - rules.include_years
    inc = [t for t in terms if t in rules.term_include]
    if inc:
        return TermResult(True, " / ".join(inc))
    good_years = sorted(y for y in years if y in rules.include_years)
    uns = [t for t in terms if t in rules.term_unsure]
    if uns and not good_years:
        return TermResult(True, " / ".join(uns), True, f"term {uns[0]} is outside your list but inside your window")
    if good_years:
        return TermResult(True, " / ".join(str(y) for y in good_years))
    if terms or years:
        shown = ", ".join(terms + [str(y) for y in sorted(years)])
        return TermResult(False, shown, reason=f"title term {shown} is not one of your terms")
    # nothing in the title: look at the description
    dterms, _ = extract_terms(snippet, title=False)
    dinc = [t for t in dterms if t in rules.term_include]
    if dinc:
        return TermResult(True, " / ".join(dinc[:2]) + " (from description)")
    duns = [t for t in dterms if t in rules.term_unsure]
    if duns:
        return TermResult(True, duns[0] + " (from description)", True, f"description mentions {duns[0]}")
    if dterms:
        return TermResult(True, "unclear", True, f"description mentions {', '.join(dterms[:3])} only")
    return TermResult(True, "unspecified")


# ---------------------------------------------------------------------------------------------
# role type and field

@dataclass
class Decision:
    ok: bool
    value: str = ""
    unsure: bool = False
    reason: str = ""


def decide_role(title: str, employment_type: str, rules: Rules, extra: re.Pattern | None = None) -> Decision:
    staff = _PROGRAM_LABEL.sub(" ", title)  # "Area Manager Intern …, University Recruiting" is not a recruiting job
    # A title that starts as a student role ("Software Engineer Intern, Partner Programs") is not a staff job running
    # a program ("Senior Program Specialist - Intern & Keep Warm Programs"); the explicit staff phrases still count.
    first = _FIRST_SEGMENT.split(title, 1)[0]
    if _search(rules.staff_about, staff) or (not (_search(rules.role_strong, first) or _search(extra, first))
                                             and _search(rules.staff_words, staff) and _search(rules.staff_context, staff)):
        return Decision(False, reason="staff role about internships")
    hit = _search(rules.role_strong, title) or _search(extra, title)
    if hit:
        return Decision(True, hit.group(0).lower())
    under = _search(rules.underclass, title)
    if under and not _search(rules.role_weak_not, title):  # "Discovery Program: Trading", not "… Program Manager"
        return Decision(True, under.group(0).lower())
    if _search(rules.employment_types, employment_type):
        return Decision(True, f"type:{employment_type.lower()}")
    if _search(rules.new_grad, title):
        return Decision(False, reason="new grad / full-time role")
    years = sorted({int(y) for y in _CLASS_OF.findall(title)} & rules.class_years)
    if years:
        return Decision(True, f"class of {years[0]}", True, f"'Class of {years[0]}' without the word intern")
    weak = _search(rules.role_weak, title)
    if weak and not _search(rules.role_weak_not, title):
        return Decision(True, weak.group(0).lower(), True, f"'{weak.group(0)}' role without the word intern")
    terms, _ = extract_terms(title, title=True)
    if terms:
        return Decision(True, "term", True, f"has a term ({terms[0]}) but no 'intern' word")
    return Decision(False, reason="not a student role")


def decide_field(title: str, department: str, category: str, rules: Rules) -> Decision:
    title = _PROGRAM_LABEL.sub(" ", title)
    strong = _search(rules.exclude_strong, title)
    if strong:
        return Decision(False, reason=f"excluded field '{strong.group(0)}'")
    for name, rx in rules.fields:
        if _search(rx, title):
            return Decision(True, name)
    ex = _all(rules.exclude, title)
    if ex:
        keep = next((m for m in _all(rules.keep_unsure, title) if _outside(m, ex)), None)
        if keep:  # "Policy Engineering Intern", "Finance Engineer Intern"
            return Decision(True, "unsure", True, f"title mentions '{ex[0].group(0)}' (excluded) and '{keep.group(0)}'")
        return Decision(False, reason=f"excluded field '{ex[0].group(0)}'")
    if department:
        for name, rx in rules.dept_fields:
            if _search(rx, department):
                return Decision(True, name)
        dex = _search(rules.exclude_strong, department) or _search(rules.exclude, department)
        if dex:
            return Decision(False, reason=f"excluded department '{department[:40]}'")
    if category == "quant":
        return Decision(True, "Quant", True, "field not clear from title (quant firm, so probably trading/research/dev)")
    return Decision(True, "unsure", True, "field not clear from title")


# ---------------------------------------------------------------------------------------------

def evaluate(job: Job, rules: Rules, *, category: str = "", locations: list[str] | None = None,
             extra_role_keywords: re.Pattern | None = None) -> Match:
    role = decide_role(job.title, job.employment_type, rules, extra_role_keywords)
    if not role.ok:
        return Match(False, reasons=[role.reason])
    field = decide_field(job.title, job.department, category, rules)
    if not field.ok:
        return Match(False, reasons=[field.reason])
    term = decide_term(job.title, job.snippet, rules)
    if not term.ok:
        return Match(False, term=term.term, reasons=[term.reason])
    loc_ok, loc_unsure, loc_reason = location_decision(job.location, locations or rules.default_locations)
    if not loc_ok:
        return Match(False, term=term.term, field=field.value, reasons=[loc_reason])

    if not field.unsure:
        tags = [field.value]
    else:  # "Quant?" when there is a best guess, "field?" when there is none
        tags = [f"{field.value}?" if field.value not in ("", "unsure") else "field?"]
    if (_search(rules.underclass, job.title) or _search(extra_role_keywords, job.title)
            or {int(y) for y in _CLASS_OF.findall(job.title)} & rules.underclass_years
            or _UNDERCLASS_TEXT.search(job.snippet or "")) and not (_PHD.search(job.title) or _MASTERS.search(job.title)):
        tags.append("freshman/sophomore")
    reasons = []
    for d, label in ((role, "role"), (field, "field"), (term, "term")):
        if d.unsure:
            reasons.append(f"{label}: {d.reason}")
    if loc_unsure:
        reasons.append(f"location: {loc_reason}")
        tags.append("location?")
    if role.unsure:
        tags.append("role?")
    if term.unsure:
        tags.append("term?")
    if _PHD.search(job.title):
        tags.append("PhD")
    elif _MASTERS.search(job.title):
        tags.append("Master's")
    unsure = role.unsure or field.unsure or term.unsure or loc_unsure
    needs_detail = (term.term == "unspecified" and not job.snippet) or (
        loc_unsure and (not job.location or bool(_MULTI_LOC.match(job.location))))
    shown_field = field.value if field.value not in ("", "unsure") else "unsure"
    return Match(True, unsure, term.term, shown_field, tags, reasons, needs_detail)


def vague_location(location: str) -> bool:
    """An empty location or a listing's placeholder ("3 Locations", "Multiple Locations")."""
    return not location or bool(_MULTI_LOC.match(location))


def is_student_role(job: Job, rules: Rules, extra_role_keywords: re.Pattern | None = None) -> bool:
    """Cheap pre-check used for counts ("intern roles seen") and to decide which jobs need details."""
    return decide_role(job.title, job.employment_type, rules, extra_role_keywords).ok
