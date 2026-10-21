"""Build config/companies.yaml from discovery: companies_seed.yaml + results/<key>.json + the overrides below.

    .venv/bin/python discovery/build_config.py

Run once after discovery; afterwards config/companies.yaml is the file you edit (and `internwatch add`
appends to it). Re-running regenerates it from discovery, so hand edits made since would be lost.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SEED = yaml.safe_load((ROOT / "discovery" / "companies_seed.yaml").read_text())["companies"]
RESULTS = {p.stem: json.loads(p.read_text()) for p in sorted((ROOT / "discovery" / "results").glob("*.json"))}

# discovery's "custom:<name>" recommendations → the checker that implements them
CHECKER_MAP = {
    "custom:recruiterbox": "recruiterbox", "custom:jobvite": "jobvite", "custom:ashby-hosted": "ashby",
    "custom:shopify-careers": "shopify", "custom:epic-careers": "epic-careers", "custom:talentbrew_sitemap": "talentbrew",
    "custom:ebay": "multi", "custom:panw": "multi", "custom:hubspot": "multi", "custom:amazon": "amazon", "custom:apple": "apple", "custom:uber": "uber",
    "custom:citadel": "citadel", "custom:wordpress_sitemap": "citadel", "custom:citadel-careers": "citadel",
}

# Bookmarks that include Canada (or "North America"): watch Canada too for these companies.
US_CA = {"microsoft", "uber", "procore", "general-motors", "salesforce", "veeva", "autodesk", "stripe"}

ALIASES = {
    "sig": ["Susquehanna International Group", "Susquehanna", "SIG", "Susquehanna International Group (SIG)"],
    "hudson-river-trading": ["HRT"], "imc": ["IMC", "IMC Financial Markets"], "jane-street": ["Jane Street Capital"],
    "two-sigma": ["Two Sigma Investments"], "epic-systems": ["Epic", "Epic Systems"], "block": ["Square", "Cash App", "Afterpay", "TIDAL"],
    "meta": ["Facebook"], "google": ["Alphabet", "YouTube", "DeepMind", "Google DeepMind"],
    "amazon": ["Amazon Web Services", "AWS", "Amazon.com"], "coreweave": ["Weights & Biases", "Weights and Biases"],
    "grubhub": ["Grubhub"], "american-family": ["AmFam", "American Family"], "general-motors": ["GM"],
    "chan-zuckerberg": ["CZI", "Chan Zuckerberg Biohub", "Biohub"], "fidelity": ["Fidelity", "Fidelity Investments"],
    "john-deere": ["Deere", "Deere & Company"], "scale-ai": ["Scale"], "mistral-ai": ["Mistral"], "c3-ai": ["C3.ai", "C3 AI"],
    "xai": ["X.AI"], "together-ai": ["Together"], "ccc": ["CCC"], "capstone": ["Capstone"],
    "point72": ["Cubist Systematic Strategies", "Point72 Asset Management"], "voleon": ["Voleon"], "dv-trading": ["DV Group"],
    "radix": ["Radix"], "wolverine": ["Wolverine"], "squarepoint": ["Squarepoint"], "xtx-markets": ["XTX"],
    "walleye": ["Walleye"], "aqr": ["AQR Capital Management"], "graviton": ["Graviton"], "jump-trading": ["Jump"],
    "voloridge": ["Voloridge"], "transmarket-group": ["TMG"], "gts": ["Global Trading Systems"],
    "electronic-arts": ["EA"], "hugging-face": ["HuggingFace"], "liberty-mutual": ["Liberty Mutual Insurance"],
    "booking": ["Booking Holdings"], "expedia": ["Expedia"], "pitchbook": ["PitchBook Data"], "veeva": ["Veeva"],
    "rocket": ["Rocket Mortgage", "Rocket"], "unity": ["Unity Technologies"], "temporal": ["Temporal Technologies"],
    "bloomberg": ["Bloomberg LP"], "procore": ["Procore Technologies"], "akamai": ["Akamai Technologies"],
    "dell": ["Dell"], "capital-one": ["Capital One"], "paypal": ["Venmo"], "citadel-securities": [],
    "nvidia": ["Nvidia"], "t-mobile": ["TMobile"], "palo-alto-networks": [], "applied-intuition": [],
}

# Freshman/sophomore program names that can appear in a posting title without a student word (UNDERCLASSMEN.md
# lists every program found and where it is posted). Generic markers (sophomore, discovery program, …) are in
# config/filters.yaml; these are each company's own program names.
PROGRAM_KEYWORDS: dict[str, list[str]] = {
    "nvidia": ["ignite"],
    "microsoft": ["explore"],
    "google": ["student training in engineering", "associate software developer"],
    "meta": ["meta university"],
    "amazon": ["propel"],
    "uber": ["uber star"],
    "duolingo": ["thrive"],
    "capital-one": ["teip", "first gen focus"],
    "salesforce": ["tech launchpad"],
    "paypal": ["career academy"],
    "goldman-sachs": ["possibilities", "emerging leaders"],
    "citadel": ["discover citadel", "launch"],
    "citadel-securities": ["discover citadel", "ignite"],
    "jane-street": ["fttp", "jsip", "insight", "focus", "bridge"],
    "two-sigma": ["mentor connect"],
    "hudson-river-trading": ["witti", "women in trading"],
    "five-rings": ["link"],
    "liberty-mutual": ["claim your career"],
    "linkedin": ["first play"],
    "electronic-arts": ["pathfinder"],
}

# Hand-tuned settings on top of discovery (each comes from a discovery note).
OVERRIDES: dict[str, dict] = {
    "microsoft": {"big": True, "timeout_minutes": 30, "settings": {
        "host": "apply.careers.microsoft.com", "domain": "microsoft.com", "api": "pcsx", "min_interval": 3.0,
        "quick_queries": [{"filter_employment_type": "internship"}, {"filter_seniority": "Intern"}],
        "count_tolerance": 0.05}},  # Microsoft re-dates postings all day; a 13-minute walk drifts (see notes)
    "nvidia": {"big": True, "timeout_minutes": 30, "settings": {"host": "jobs.nvidia.com", "domain": "nvidia.com",
               "api": "pcsx", "min_interval": 3.0, "quick_queries": [{"filter_job_type": "intern (fixed term)"}],
               "count_tolerance": 0.05}},
    "two-sigma": {"settings": {"list_url": "https://careers.twosigma.com/careers/OpenRoles/", "page_size": 10,
                               "fields": ["location", "department", "employment_type"]}},
    "bloomberg": {"settings": {"list_url": "https://bloomberg.avature.net/careers/SearchJobs/", "page_size": 12,
                               "fields": {"location": ".list-item-location"},
                               "total_regex": r'list-controls__text__legend"\s+aria-label="(\d+) results"'}},
    "synopsys": {"big": True, "timeout_minutes": 10, "settings": {
        "list_url": "https://synopsys.avature.net/careers/SearchJobs/", "page_size": 6,
        "fields": {"employment_type": ".list-item-hireType", "posted": ".list-item-posted"},
        "total_regex": r'list-controls__text__legend"\s+aria-label="(\d+) results"',
        "newest_first_query": "jobSort=postedDate&jobSortDirection=DESC"}},
    "electronic-arts": {"settings": {"list_url": "https://jobs.ea.com/en_US/careers/Home/", "page_size": 20,
                                     "params": {"jobRecordsPerPage": 20}, "total_regex": r'aria-label="(\d+) results"',
                                     "fields": {"location": "span.list-item-location", "employment_type": "span.list-item-workerType",
                                                "department": "span.list-item-department"}}},
    "whatnot": {"settings": {"board": "whatnot", "mode": "hosted"}},
    "wolfram": {"settings": {"client_id": 42716,
                             "job_url": "https://www.wolfram.com/company/careers/opportunities/#op-{id}-{slug}"}},
    "nutanix": {"settings": {"company_id": "qKr9VfwZ", "slug": "nutanix",
                             "job_url": "https://careers.nutanix.com/en/jobs/{requisitionid}/{slug}/"}},
    "intuit": {"settings": {"sitemap_url": "https://jobs.intuit.com/sitemap.xml", "org_id": 27595, "detail_limit": 40}},
    "ebay": {"checker": "multi", "settings": {"sources": [
        {"checker": "phenom", "settings": {"base_url": "https://jobs.ebayinc.com", "ref_num": "EBAEBAUS", "lang": "en_us",
                                           "country": "us", "page_id": "page15",
                                           "all_fields": ["remote", "country", "state", "category"],
                                           "job_path": "/us/en/job/{jobId}"}},
        {"checker": "ripplematch", "settings": {"company_id": 865}}]}},
    # Workday's robots.txt for this tenant disallows the HTML site (/panwexternalcareers/) but not the CXS JSON
    # API, the only complete source (the Radancy front drops every intern posting); see notes/palo-alto-networks.md
    "palo-alto-networks": {"checker": "multi", "settings": {"sources": [
        {"checker": "workday", "settings": {"host": "paloaltonetworks.wd5.myworkdayjobs.com",
                                            "tenant": "paloaltonetworks", "site": "panwexternalcareers"}},
        {"checker": "ripplematch", "settings": {"company_id": 676}}]}},
    "instabase": {"settings": {"board": "instabase", "missing_ok": True}},
    "c3-ai": {"settings": {"boards": ["c3iot", "c3ascend"], "dedupe_requisitions": True}},
    "salesforce": {"settings": {"host": "salesforce.wd12.myworkdayjobs.com", "tenant": "salesforce",
                                                    "sites": ["External_Career_Site", "Futureforce_Internships"],
                                                    "min_interval": 5.0}, "timeout_minutes": 15},
    "t-mobile": {"big": True, "timeout_minutes": 15},
    # linkedin.com disallows all crawlers, but LinkedIn's hiring account on SmartRecruiters has a public career page
    # whose robots.txt allows reading (found in an open list of employer job boards). linkedin.com is never fetched.
    "linkedin": {"checker": "smartrecruiters", "status": "active", "settings": {"company": "LinkedIn3"},
                 "verified": {"feed": "careers.smartrecruiters.com/LinkedIn3", "explained":
                              "LinkedIn's SmartRecruiters career page; linkedin.com, which also lists its jobs, disallows "
                              "all crawlers, so the two can't be compared"}},
    # Phenom copies backed by the real hiring system as the first source (fresher, and either keeps working alone)
    "rocket": {"checker": "multi", "settings": {"dedupe": True, "sources": [
        {"checker": "workday", "settings": {"host": "quickenloans.wd5.myworkdayjobs.com", "tenant": "quickenloans",
                                            "site": "rocket_careers"}},
        {"checker": "phenom", "settings": {"base_url": "https://careers.rocket.com", "ref_num": "RCARCAUS",
                                           "lang": "en_us", "country": "us", "job_path": "/us/en/job/{jobSeqNo}/{slug}"}}]}},
    "yelp": {"checker": "multi", "settings": {"dedupe": True, "sources": [
        {"checker": "icims", "settings": {"portal": "https://uscareers-yelp.icims.com"}},
        {"checker": "phenom", "settings": {"base_url": "https://www.yelp.careers", "ref_num": "YELPUS", "lang": "en_us",
                                           "country": "us", "job_path": "/us/en/job/{jobId}/{slug}"}}]}},
    "autodesk": {"checker": "multi", "verified": {"explained":
        "union of both systems: Workday's 347 postings plus the 88 requisitions only on Eightfold; the Eightfold "
        "careers page (jobs.autodesk.com) shows 386"}, "settings": {"dedupe": True, "sources": [
        {"checker": "workday", "settings": {"host": "autodesk.wd1.myworkdayjobs.com", "tenant": "autodesk", "sites": ["uni", "Ext"]}},
        {"checker": "eightfold", "settings": {"host": "jobs.autodesk.com", "domain": "autodesk.com", "api": "pcsx",
                                              "min_interval": 2.5, "count_tolerance": 0.04}}]}},
    # Campus boards next to the main Greenhouse board (found by probing <board>campus, <board>students, …);
    # the careers pages list only the main board. Toast's and Twilio's are empty between seasons.
    "klaviyo": {"settings": {"boards": ["klaviyo", "klaviyocampus"], "missing_ok": True}, "verified": {
        "feed": "GET https://boards-api.greenhouse.io/v1/boards/{klaviyo,klaviyocampus}/jobs", "explained":
        "the careers page lists the main board (159); internships and co-ops are on a second board, klaviyocampus"}},
    "toast": {"settings": {"boards": ["toast", "toastcampus"], "missing_ok": True},
              "verified": {"feed": "GET https://boards-api.greenhouse.io/v1/boards/{toast,toastcampus}/jobs"}},
    "twilio": {"settings": {"boards": ["twilio", "twiliostudents"], "missing_ok": True},
               "verified": {"feed": "GET https://boards-api.greenhouse.io/v1/boards/{twilio,twiliostudents}/jobs"}},
    # Expedia posts some roles (2027 internships among them) only on a second Workday site, "private", which
    # SimplifyJobs links to; robots.txt allows it. A second source keeps the public site's job ids unchanged.
    "expedia": {"checker": "multi", "verified": {
        "feed": "POST https://expedia.wd108.myworkdayjobs.com/wday/cxs/expedia/{search,private}/jobs", "explained":
        "public Workday site 'search' (the careers page's 166) plus the postings only on the Workday site 'private'"},
        "settings": {"dedupe": True, "sources": [
            {"checker": "workday", "settings": {"host": "expedia.wd108.myworkdayjobs.com", "tenant": "expedia", "site": "search"}},
            {"checker": "workday", "settings": {"host": "expedia.wd108.myworkdayjobs.com", "tenant": "expedia", "site": "private"}}]}},
    "hubspot": {"checker": "multi", "settings": {"sources": [
        {"checker": "hubspot", "settings": {}}, {"checker": "ripplematch", "settings": {"company_id": 708}}]}},
    # Rockwell posts some co-ops and internships only on RippleMatch (found by checking every company's RippleMatch
    # page); many others are on both under slightly different titles, so title duplicates are skipped.
    "rockwell-automation": {"checker": "multi", "verified": {"explained":
        "both Workday career sites plus the co-ops and internships Rockwell posts only on RippleMatch"},
        "settings": {"dedupe": True, "dedupe_titles": True, "sources": [
            {"checker": "workday", "settings": {"host": "rockwellautomation.wd1.myworkdayjobs.com",
                                                "tenant": "rockwellautomation",
                                                "sites": ["External_Rockwell_Automation",
                                                          "External-Rockwell-Automation-Early-Careers"]}},
            {"checker": "ripplematch", "settings": {"company_id": 671}}]}},
    # Plaid posts its student roles (the Summer 2027 SWE internship) only on RippleMatch, linked from its careers page
    "plaid": {"checker": "multi", "verified": {"explained":
        "Ashby board (no student roles) plus the student roles Plaid posts only on RippleMatch"}, "settings": {"sources": [
        {"checker": "ashby", "settings": {"board": "plaid"}}, {"checker": "ripplematch", "settings": {"company_id": 718}}]}},
    "apple": {"checker": "apple", "settings": {}, "big": True, "verified": {"page_total": None, "explained":
        "reads the complete student slice (Students team + exact-word searches; 306 rows = 251 postings), grouped "
        "by posting; the whole site is ~6,100 posting x location rows and the page shows only '600+'"}},
    "citadel": {"checker": "citadel", "settings": {"base_url": "https://www.citadel.com", "min_interval": 10.0}},
    "citadel-securities": {"checker": "citadel", "settings": {"base_url": "https://www.citadelsecurities.com",
                                                              "min_interval": 10.0}},
    "wolverine": {"settings": {"subdomain": "wolve", "host": "careers.wolve.com"}},
    "amazon": {"settings": {}, "big": True, "verified": {"page_total": None, "explained":
        "reads the complete student slice (intern/apprentice flags + student business categories + keyword sweep, "
        "~1,900 jobs, ~650 of them student roles); the site's 22,117 jobs exceed its 10,000-hit search cap and the page "
        "shows no total"}},
}


def clean_settings(checker: str, s: dict) -> dict:
    """Keep only the settings our adapters read (discovery notes add descriptive keys)."""
    s = dict(s or {})
    drop = {"content", "dedupe_by", "loader_key", "list_path", "json_var", "org_slug", "url_template", "id",
            "posted", "snippet", "employment_type_from", "card", "title", "id_from_url", "offset_param",
            "detail_for_location", "newest_first", "detail", "detail_only_new", "title_from", "job_url_regex",
            "total_check_url", "never_fetch_prefix", "use_employment_type_note", "health", "page_size_note"}
    if checker == "jibe":
        drop -= {"use_employment_type"}
    return {k: v for k, v in s.items() if k not in drop}


def first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.;])(\s|$)", text or "")
    return (m.group(1) if m else (text or ""))[:240]


def entry(seed: dict) -> dict | None:
    key = seed["key"]
    res = RESULTS.get(key)
    if res is None:
        return None
    ov = OVERRIDES.get(key, {})
    checker = ov.get("checker") or CHECKER_MAP.get(res.get("checker"), res.get("checker"))
    settings = ov.get("settings") or clean_settings(checker, res.get("settings"))
    urls = [res.get("careers_url")] + [u for u in seed.get("urls", []) if u != res.get("careers_url")]
    e = {"key": key, "name": seed["name"], "category": seed.get("category", "")}
    if ALIASES.get(key):
        e["aliases"] = ALIASES[key]
    e["careers_url"] = [u for u in urls if u][:3]
    e["checker"] = checker
    if settings:
        e["settings"] = settings
    if key in US_CA:
        e["locations"] = ["US", "CA"]
    status = ov.get("status") or ("blocked" if res.get("status") == "blocked" else "active")
    if status != "active":
        e["status"] = status
        e["blocked_reason"] = res.get("blocked_reason") or res.get("notes", "")
        e["fallback"] = res.get("fallback") or "SimplifyJobs cross-check; sign up for the company's own job alerts"
    if PROGRAM_KEYWORDS.get(key):
        e["role_keywords"] = PROGRAM_KEYWORDS[key]
    for k in ("big", "timeout_minutes", "full_scan_hours"):
        if k in ov:
            e[k] = ov[k]
    if res.get("settings", {}).get("big") or res.get("big"):
        e.setdefault("big", True)
    ft, pt = res.get("feed_total"), res.get("page_total")
    ver = {"page_total": pt}
    if isinstance(ft, int) and isinstance(pt, int) and ft != pt and res.get("status") == "verified":
        ver["explained"] = first_sentence(res.get("notes", ""))
    ver.update(ov.get("verified") or {})
    e["verified"] = ver
    return e


def main() -> None:
    out, missing = [], []
    for seed in SEED:
        e = entry(seed)
        if e is None:
            missing.append(seed["key"])
            continue
        out.append(e)
        # discovery found a second, separate employer behind this bookmark (e.g. Capstone DC vs Capstone)
        for extra in RESULTS[seed["key"]].get("additional_entries") or []:
            RESULTS[extra["key"]] = {**extra, "status": extra.get("status", "verified")}
            sub = entry({"key": extra["key"], "name": extra["name"], "category": "other",
                         "urls": [u for u in seed.get("urls", []) if extra.get("settings", {}).get("host", "~") in u]})
            if sub:
                out.append(sub)
    header = ("# Every company InternWatch watches. One entry per company; see README.md, 'Adding a company'.\n"
              "#   key, name, category      identity (category 'quant' makes generic titles count as quant roles)\n"
              "#   careers_url              official careers page first (health emails link it), then your bookmarks\n"
              "#   checker + settings       which adapter reads the site, and how (src/internwatch/adapters, checkers)\n"
              "#   locations                countries to match (default from filters.yaml: US)\n"
              "#   status: blocked          not polled (automated access disallowed); covered by the SimplifyJobs cross-check\n"
              "#   role_keywords            the company's freshman/sophomore program names (NVIDIA Ignite …): student roles\n"
              "#   big: true                huge site: newest-first quick scans every poll, a full scan once a day\n"
              "#   verified                 discovery evidence: the careers page's own job count (and why it differs)\n")
    text = yaml.safe_dump({"companies": out}, sort_keys=False, allow_unicode=True, width=130, default_flow_style=None)
    (ROOT / "config" / "companies.yaml").write_text(header + text)
    print(f"wrote {len(out)} companies; no discovery result yet for {len(missing)}: {' '.join(missing)}")


if __name__ == "__main__":
    main()
