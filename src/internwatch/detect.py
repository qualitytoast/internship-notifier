"""`internwatch add`: detect a careers page's hiring system, test the checker live, save the entry.

Detection, cheapest first:
1. the URL itself (job-boards.greenhouse.io/<board>, <tenant>.wd5.myworkdayjobs.com/<site>, …)
2. links, iframes and scripts in the page HTML (and, with --browser, every request a real browser makes)
3. probing the public board APIs (Greenhouse, Lever, Ashby, Workable) with tokens guessed from the name/domain
Every candidate is run live; the one returning the most jobs wins (ties: the order above).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit

import yaml

from .adapters import all_types, get_checker
from .config import Company, Config, load_companies
from .filters import evaluate, is_student_role
from .http import Http
from .runner import http_settings, make_gate, run_checker

PATTERNS: list[tuple[str, str, callable]] = [
    ("greenhouse", r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/embed/job_board(?:/js)?\?for=([\w-]+)", lambda m: {"board": m[1]}),
    ("greenhouse", r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?!embed\b)([\w-]+)", lambda m: {"board": m[1]}),
    ("greenhouse", r"boards-api\.greenhouse\.io/v1/boards/([\w-]+)", lambda m: {"board": m[1]}),
    ("lever", r"jobs\.(eu\.)?lever\.co/([\w.-]+)", lambda m: {"site": m[2], **({"region": "eu"} if m[1] else {})}),
    ("lever", r"api\.(eu\.)?lever\.co/v0/postings/([\w.-]+)", lambda m: {"site": m[2], **({"region": "eu"} if m[1] else {})}),
    ("ashby", r"jobs\.ashbyhq\.com/([\w.%-]+)", lambda m: {"board": unquote(m[1])}),
    ("ashby", r"api\.ashbyhq\.com/posting-api/job-board/([\w.%-]+)", lambda m: {"board": unquote(m[1])}),
    ("workable", r"apply\.workable\.com/(?!api\b|j\b)([\w-]+)", lambda m: {"account": m[1]}),
    ("gem", r"jobs\.gem\.com/([\w-]+)", lambda m: {"board": m[1]}),
    ("pinpoint", r"([\w-]+)\.pinpointhq\.com", lambda m: {"subdomain": m[1]}),
    ("workday", r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:wday/cxs/[\w-]+/)?(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)",
     lambda m: {"host": f"{m[1]}.{m[2]}.myworkdayjobs.com", "tenant": m[1], "site": m[3]}),
    ("workday", r"(wd\d+)\.myworkdaysite\.com/(?:[a-z]{2}-[A-Z]{2}/)?recruiting/([\w-]+)/([\w-]+)",
     lambda m: {"host": f"{m[1]}.myworkdaysite.com", "tenant": m[2], "site": m[3]}),
    ("oracle", r"([\w.-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/[\w-]+/sites/([\w-]+)",
     lambda m: {"host": m[1], "site": m[2]}),
    ("icims", r"(https://[\w-]+\.icims\.com)", lambda m: {"portal": m[1]}),
    ("avature", r"(https://[\w.-]+\.avature\.net/[\w-]+)/", lambda m: {"list_url": m[1] + "/SearchJobs/"}),
]
SKIP_TOKENS = {"embed", "api", "v1", "js", "jobs", "careers", "j", "static", "assets", "posting-api", "wday", "en-us"}


@dataclass
class Candidate:
    checker: str
    settings: dict
    source: str


def from_text(text: str, source: str) -> list[Candidate]:
    out: list[Candidate] = []
    for checker, rx, build in PATTERNS:
        for m in re.finditer(rx, text):
            s = build(m)
            if any(str(v).lower() in SKIP_TOKENS for v in s.values()):
                continue
            c = Candidate(checker, s, source)
            if all((c.checker, c.settings) != (x.checker, x.settings) for x in out):
                out.append(c)
    return out


def eightfold_from(url: str, html: str) -> list[Candidate]:
    p = urlsplit(url)
    if "eightfold" not in html and "/api/pcsx" not in html and "eightfold.ai" not in p.netloc:
        return []
    domain = (parse_qs(p.query).get("domain") or [None])[0]
    if not domain:
        m = re.search(r'"domain"\s*:\s*"([\w.-]+\.\w+)"', html) or re.search(r"domain=([\w.-]+\.\w+)", html)
        domain = m.group(1) if m else ".".join(p.netloc.split(".")[-2:])
    return [Candidate("eightfold", {"host": p.netloc, "domain": domain, "api": "pcsx"}, "eightfold page"),
            Candidate("eightfold", {"host": p.netloc, "domain": domain, "api": "v2"}, "eightfold page")]


def phenom_from(url: str, html: str) -> list[Candidate]:
    m = re.search(r'"refNum"\s*:\s*"(\w+)"', html)
    if not m or "phenom" not in html.lower():
        return []
    p = urlsplit(url)
    loc = re.search(r'"locale"\s*:\s*"([a-z]{2})_([a-z]{2})"', html, re.I)
    lang = f"{loc.group(1)}_{loc.group(2)}".lower() if loc else "en_us"
    country = loc.group(2).lower() if loc else "us"
    return [Candidate("phenom", {"base_url": f"{p.scheme}://{p.netloc}", "ref_num": m.group(1), "lang": lang,
                                 "country": country}, "phenom page")]


def guess_tokens(name: str, url: str) -> list[str]:
    base = re.sub(r"[^a-z0-9]", "", name.lower())
    host = urlsplit(url).netloc.lower().removeprefix("www.").removeprefix("careers.").removeprefix("jobs.")
    dom = host.split(".")[0]
    words = re.findall(r"[a-z0-9]+", name.lower())
    toks = [base, dom, "-".join(words), words[0] if words else ""]
    return [t for t in dict.fromkeys(toks) if t and len(t) > 1]


def probe(name: str, url: str) -> list[Candidate]:
    out = []
    for t in guess_tokens(name, url):
        out += [Candidate("greenhouse", {"board": t}, "probe"), Candidate("ashby", {"board": t}, "probe"),
                Candidate("lever", {"site": t}, "probe"), Candidate("workable", {"account": t}, "probe")]
    return out


def browser_requests(url: str) -> str:
    """Every request URL a headless browser makes while loading the page (needs `pip install .[browser]`)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ""
    seen: list[str] = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page()
        page.on("request", lambda r: seen.append(r.url + " " + (r.post_data or "")[:300]))
        try:
            page.goto(url, wait_until="networkidle", timeout=45000)
            seen.append(page.content())
        except Exception:  # noqa: BLE001 — partial results are still useful
            pass
        b.close()
    return "\n".join(seen)


def detect(cfg: Config, name: str, url: str, use_browser: bool = False) -> tuple[list[Candidate], str]:
    cands = from_text(url, "url")
    html, note = "", ""
    http = Http(http_settings(cfg), gate=make_gate(cfg))
    try:
        html = http.get_text(url)
    except Exception as e:  # noqa: BLE001
        note = f"could not load the page ({e})"
    finally:
        http.close()
    cands += [c for c in from_text(html, "page html") if c not in cands]
    cands += eightfold_from(url, html) + phenom_from(url, html)
    if use_browser:
        cands += [c for c in from_text(browser_requests(url), "browser requests") if c not in cands]
    cands += probe(name, url)
    seen, uniq = set(), []
    for c in cands:
        k = (c.checker, json.dumps(c.settings, sort_keys=True))
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq, note


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def entry_yaml(c: Company, indent: str = "") -> str:
    d = {"key": c.key, "name": c.name, "category": c.category or "other", "careers_url": c.careers_url[0],
         "checker": c.checker}
    if c.settings:
        d["settings"] = c.settings
    if c.locations:
        d["locations"] = c.locations
    text = yaml.safe_dump([d], sort_keys=False, default_flow_style=None, width=120)
    return "".join(indent + line + "\n" for line in text.rstrip("\n").split("\n"))


def add_company(cfg: Config, a) -> int:
    key = a.key or slug(a.name)
    if any(c.key == key for c in cfg.companies):
        print(f"'{key}' is already in config/companies.yaml (use --key to pick another key)")
        return 1
    locations = [x.strip().upper() for x in a.locations.split(",")] if a.locations else None
    if a.checker:
        if a.checker not in all_types():
            print(f"unknown checker '{a.checker}'. Known: {', '.join(all_types())}")
            return 1
        cands, note = [Candidate(a.checker, json.loads(a.settings or "{}"), "given")], ""
    else:
        print(f"detecting the hiring system behind {a.url} …")
        cands, note = detect(cfg, a.name, a.url, a.browser)
        if note:
            print("  " + note)
    best = None
    gate = make_gate(cfg)
    for cand in cands:
        comp = Company(key=key, name=a.name, category=a.category, careers_url=[a.url], checker=cand.checker,
                       settings=cand.settings, locations=locations)
        o = run_checker(cfg, comp, gate=gate)
        n = len(o.jobs or []) if o.ok else -1
        label = f"{cand.checker} {json.dumps(cand.settings)} ({cand.source})"
        if cand.source != "probe" or n > 0:
            print(f"  {label}: {'%d jobs' % n if n >= 0 else 'failed: ' + (o.error or '')[:100]}")
        if n > 0 and (best is None or n > best[1]):
            best = (comp, n, o)
    if best is None:
        print("\nNo working checker found. What to do next:\n"
              "  • open the careers page in your browser's devtools (Network tab), find the request that returns the\n"
              "    job list, and add the company with --checker <type> --settings '<json>' if it is a supported system;\n"
              "  • otherwise write a custom checker in src/internwatch/checkers/ (see README, 'Adding a company').")
        return 2
    comp, n, o = best
    students = [j for j in o.jobs if is_student_role(j, cfg.rules, comp.extra_role_re)]
    matches = [j for j in o.jobs if evaluate(j, cfg.rules, category=comp.category, locations=comp.locations).matched]
    print(f"\nbest: {comp.checker} {json.dumps(comp.settings)} → {n} jobs, {len(students)} student roles, "
          f"{len(matches)} match your filters")
    for j in matches[:10]:
        print(f"  • {j.title} — {j.location}")
    print("\nCompare the job count with the careers page (filters off) before trusting it.")
    if not a.yes:
        try:
            ok = input("Save to config/companies.yaml? [y/N] ").strip().lower() == "y"
        except EOFError:
            ok = False
        if not ok:
            print("not saved")
            return 0
    path = cfg.root / "config" / "companies.yaml"
    text = path.read_text()
    m = re.search(r"^( *)- key:", text, re.M)  # follow the file's own list indentation
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text.rstrip("\n") + "\n" + entry_yaml(comp, m.group(1) if m else ""))
    try:
        load_companies(tmp)  # the file must still load before it replaces the real one
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)
    print(f"saved '{key}' to {path}. It will be seeded silently on its first run (you'll get a 'Now watching' email).")
    from .cli import record_one  # the offline test suite expects a fixture for every company
    _, fixture = record_one(cfg, comp, make_gate(cfg))
    print(f"recorded test fixture {fixture}" if fixture else "could not record a test fixture: run `internwatch record " + key + "`")
    return 0
