"""IBM: the search service behind ibm.com/careers/search (the same requests the page makes).

POST https://www-api.ibm.com/search/api/v2 {"appId": "careers", "scopes": ["careers2"], "size": 100, "from": N,
     "sort": [{"_id": "asc"}], "_source": [...]} → hits.total.value, hits.hits[]._source:
     url ("https://careers.ibm.com/careers/JobDetail?jobId=<id>"), title, description (an excerpt),
     field_keyword_08 (department), field_keyword_17 (Hybrid / Remote), field_keyword_18 (Internship / Entry Level /
     Professional), field_keyword_19 ("City, CC" with a two-letter country code, or "Multiple Cities")
The whole site, ~2,200 jobs at 100 a request (the service's maximum). Sorted by _id: the page's own order (score,
then page views) ties on every hit, so its pages could repeat or skip jobs.
"City, CC" is written out with the country's name ("Ehningen, DE" → "Ehningen, Germany"); the bare codes would read
as US states (DE Delaware, IN Indiana, CO Colorado, ID Idaho). careers.ibm.com answers automated clients with an
empty 202, so job pages are linked, never read. See discovery/notes/ibm.md.
"""
from __future__ import annotations

import re

from ..adapters.base import Checker, check_total, need, need_list, register, report_skipped
from ..models import Job

API = "https://www-api.ibm.com/search/api/v2"
FIELDS = ["_id", "title", "url", "description", "language", "entitled", "field_keyword_17", "field_keyword_08",
          "field_keyword_18", "field_keyword_19"]
PAGE = 100
# ISO 3166 two-letter codes → names the location rules (locations.py) read as that country (a test checks)
COUNTRIES = {
    "US": "United States", "CA": "Canada", "GB": "United Kingdom", "IE": "Ireland", "DE": "Germany", "FR": "France",
    "NL": "Netherlands", "BE": "Belgium", "LU": "Luxembourg", "CH": "Switzerland", "AT": "Austria", "IT": "Italy",
    "ES": "Spain", "PT": "Portugal", "DK": "Denmark", "SE": "Sweden", "NO": "Norway", "FI": "Finland", "IS": "Iceland",
    "PL": "Poland", "CZ": "Czech Republic", "SK": "Slovakia", "HU": "Hungary", "RO": "Romania", "BG": "Bulgaria",
    "GR": "Greece", "CY": "Cyprus", "MT": "Malta", "SI": "Slovenia", "HR": "Croatia", "RS": "Serbia", "EE": "Estonia",
    "LV": "Latvia", "LT": "Lithuania", "UA": "Ukraine", "TR": "Turkey", "IL": "Israel", "AE": "United Arab Emirates",
    "SA": "Saudi Arabia", "QA": "Qatar", "KW": "Kuwait", "BH": "Bahrain", "OM": "Oman", "JO": "Jordan", "EG": "Egypt",
    "MA": "Morocco", "TN": "Tunisia", "NG": "Nigeria", "KE": "Kenya", "ZA": "South Africa", "IN": "India",
    "PK": "Pakistan", "BD": "Bangladesh", "LK": "Sri Lanka", "CN": "China", "HK": "Hong Kong", "TW": "Taiwan",
    "JP": "Japan", "KR": "South Korea", "SG": "Singapore", "MY": "Malaysia", "ID": "Indonesia", "TH": "Thailand",
    "VN": "Vietnam", "PH": "Philippines", "AU": "Australia", "NZ": "New Zealand", "MX": "Mexico", "CR": "Costa Rica",
    "PA": "Panama", "CO": "Colombia", "EC": "Ecuador", "PE": "Peru", "BR": "Brazil", "AR": "Argentina", "CL": "Chile",
    "UY": "Uruguay", "PY": "Paraguay", "BO": "Bolivia", "VE": "Venezuela", "DO": "Dominican Republic",
    "GT": "Guatemala", "KZ": "Kazakhstan", "PR": "Puerto Rico",
}
JOB_ID = re.compile(r"[?&]jobId=(\d+)")


def place(location: str) -> str:
    """'Ehningen, DE' → 'Ehningen, Germany'; anything else ('Multiple Cities', an unknown code) as it is."""
    if "Ã" in location:  # UTF-8 the source decoded as Latin-1 ("SÃ£o Paulo")
        try:
            location = location.encode("latin-1").decode("utf-8")
        except UnicodeError:
            pass
    m = re.fullmatch(r"(.+?),\s*([A-Z]{2})", location.strip())
    return f"{m.group(1)}, {COUNTRIES[m.group(2)]}" if m and m.group(2) in COUNTRIES else location


@register
class IBM(Checker):
    type = "ibm"

    def describe(self, s):
        return f"POST {API} (appId careers, every job, {PAGE} a request, sorted by _id)"

    def fetch(self, http, s, ctx=None):
        jobs: dict[str, Job] = {}
        total, skipped, start, read = None, 0, 0, 0
        while total is None or start < total:
            body = {"appId": "careers", "scopes": ["careers2"], "query": {"bool": {"must": []}}, "size": PAGE,
                    "from": start, "sort": [{"_id": "asc"}], "lang": "zz", "localeSelector": {},
                    "sm": {"query": "", "lang": "zz"}, "_source": FIELDS}
            hits = (http.post_json(API, json=body, headers={"Content-Type": "application/json"}) or {}).get("hits")
            items = need_list(hits, "hits", "ibm")
            total = (hits.get("total") or {}).get("value")
            need(isinstance(total, int), "ibm: hits.total.value missing")
            read += len(items)
            for h in items:
                src = h.get("_source") or {}
                m = JOB_ID.search(src.get("url") or "")
                if not (m and src.get("title")):
                    skipped += 1
                    continue
                jobs.setdefault(m.group(1), Job(
                    id=m.group(1), title=src["title"], location=place(src.get("field_keyword_19") or ""),
                    url=src["url"], snippet=src.get("description") or "", department=src.get("field_keyword_08") or "",
                    employment_type=src.get("field_keyword_18") or "",
                    extra={"workplace": src.get("field_keyword_17") or ""},
                ))
            start += PAGE
            if not items or start >= 10_000:  # the service pages no deeper than 10,000 hits
                break
        report_skipped(ctx, skipped, len(jobs), f"ibm: {skipped} search hits without a jobId link or title")
        check_total(read, total, "ibm")
        return list(jobs.values())
