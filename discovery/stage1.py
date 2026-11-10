"""Stage 1 discovery for the companies added in November 2026 (discovery/candidates/candidates.yaml).

    INTERNWATCH_HOME=<scratch home> .venv/bin/python -I discovery/stage1.py pages [keys]

Everything goes through the project's own HTTP client, so robots.txt is checked before every request and each host
gets at least 1 s between requests. INTERNWATCH_HOME must point at a scratch copy of config/ and data/ (never the real
database); nothing here writes to config/ or src/.

pages: one plain GET of each careers page, as the `moved?` check reads it. Records the answer (ok, refused, failed,
       robots), where it redirected, and every job system the page names (detect.from_text and liveness.page_systems),
       with Eightfold and Phenom hints. Writes discovery/candidates/pages.json and each host's robots.txt to
       discovery/robots/<host>.txt.
lists: one download of each third-party list the `new job site?` check reads (settings liveness.listings), kept in
       $STAGE1_RAW/lists/, then moves.py's own parsing and matching (list_rows, company_of, systems_in) with the 198
       ahead of the candidates, as the config will order them. Writes discovery/candidates/lists.json: the job systems
       each list links for each candidate, with an example posting.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from internwatch import config  # noqa: E402
from internwatch.detect import eightfold_from, from_text, phenom_from  # noqa: E402
from internwatch.http import Http  # noqa: E402
from internwatch.liveness import page_systems  # noqa: E402
from internwatch.moves import outcome  # noqa: E402
from internwatch.runner import http_settings, make_gate  # noqa: E402

CANDIDATES = REPO / "discovery" / "candidates"
ROBOTS = REPO / "discovery" / "robots"
# a 200 answer that is really a bot check or an empty shell: worth a look by hand
CHALLENGE = re.compile(r"just a moment|captcha|access denied|_incapsula_|px-captcha|cf-chl|datadome|"
                       r"request unsuccessful|are you a robot|verify you are human", re.I)


def load_candidates(keys: list[str]) -> list[dict]:
    rows = yaml.safe_load((CANDIDATES / "candidates.yaml").read_text())["companies"]
    return [r for r in rows if not keys or r["key"] in keys]


def home_config():
    home = os.environ.get("INTERNWATCH_HOME")
    if not home or Path(home).resolve() == REPO:
        sys.exit("set INTERNWATCH_HOME to a scratch copy of config/ and data/, never the repo itself")
    return config.load(Path(home))


def read_page(http: Http, c: dict) -> dict:
    url = c["urls"][0]
    out = {"url": url}
    t0 = time.monotonic()
    try:
        # */* too, as the page check sends it (Wolfram's server answers 406 to text/html alone)
        r = http.get(url, headers={"Accept": "text/html,*/*;q=0.8"})
    except Exception as e:  # noqa: BLE001 — every failure is a finding
        out.update(outcome=outcome(e), error=str(e)[:300], seconds=round(time.monotonic() - t0, 1))
        return out
    text = r.text
    found = from_text(text, url)
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    out.update(outcome="ok", status=r.status, final_url=r.url, bytes=len(r.content),
               seconds=round(time.monotonic() - t0, 1),
               title=re.sub(r"\s+", " ", title.group(1)).strip()[:120] if title else "",
               challenge=bool(CHALLENGE.search(text[:20000])) and len(r.content) < 60000,
               systems=sorted(page_systems(text, found)),
               candidates=[{"checker": x.checker, "settings": x.settings} for x in found],
               eightfold=[x.settings for x in eightfold_from(r.url, text)][:1],
               phenom=[x.settings for x in phenom_from(r.url, text)])
    return out


def save_robots(cache_dir: Path) -> int:
    """The robots.txt of every host this script touched, in robots_check.py's format. An existing snapshot is the
    evidence of an earlier discovery and is left as it is."""
    ROBOTS.mkdir(exist_ok=True)
    n = 0
    for p in sorted(cache_dir.glob("*.json")):
        d = json.loads(p.read_text())
        out = ROBOTS / f"{urlsplit(d['origin']).netloc}.txt"
        if not out.exists():
            out.write_text(f"# status {d['status']}\n{d['text']}")
            n += 1
    return n


def pages(keys: list[str]) -> None:
    cfg = home_config()
    hs = http_settings(cfg)
    hs.retries = 1  # a careers page gets one retry, as moves.py's reads do
    gate = make_gate(cfg)
    rows = load_candidates(keys)
    path = CANDIDATES / "pages.json"
    results = json.loads(path.read_text()) if path.exists() else {}

    def one(c):
        with Http(hs, gate=gate) as http:
            return c["key"], read_page(http, c)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for key, res in pool.map(one, rows):
            results[key] = res
            print(f"{key:24} {res['outcome']:8} {res.get('status', ''):>3} {res.get('seconds', '')}s "
                  f"{(res.get('final_url') or res.get('error') or '')[:90]}", flush=True)
    path.write_text(json.dumps(dict(sorted(results.items())), indent=1) + "\n")
    print(f"saved {len(results)} pages to {path.relative_to(REPO)}; robots.txt of {save_robots(gate.cache_dir)} hosts "
          f"to discovery/robots/")


CAREER_LINK = re.compile(r'href="((?:https?:)?//[^"]*|/[^"]*)"[^>]*>', re.I)
CAREER_WORD = re.compile(r"career|jobs|join|work-with-us|work-at|opportunit|open-roles|openings", re.I)


def homes(keys: list[str]) -> None:
    """For pages that failed: the careers links on the company's home page (one GET each), to correct the URL."""
    cfg = home_config()
    hs = http_settings(cfg)
    hs.retries = 1
    gate = make_gate(cfg)
    for c in load_candidates(keys):
        p = urlsplit(c["urls"][0])
        host = p.netloc.removeprefix("careers.").removeprefix("jobs.")
        home = f"https://{host if '.' in host else p.netloc}/"
        try:
            with Http(hs, gate=gate) as http:
                r = http.get(home, headers={"Accept": "text/html,*/*;q=0.8"})
        except Exception as e:  # noqa: BLE001
            print(f"{c['key']:22} {home} {outcome(e)}: {str(e)[:100]}")
            continue
        links = []
        for m in CAREER_LINK.finditer(r.text):
            u = m.group(1)
            if CAREER_WORD.search(u):
                u = u if u.startswith("http") else ("https:" + u if u.startswith("//") else
                                                   f"https://{urlsplit(r.url).netloc}{u}")
                if u not in links:
                    links.append(u)
        print(f"{c['key']:22} {r.url[:50]:50} {' '.join(links[:6])[:250]}")
    save_robots(gate.cache_dir)


FINGERPRINTS = {
    "radancy/talentbrew": r"tbcdn\.talentbrew\.com|radancy|talentbrew", "phenom": r"phenompeople|cdn\.phenompeople",
    "jibe": r"jibeapply|jibecdn", "avature": r"avature\.net", "successfactors": r"successfactors|jobs\.sap\.com|rmkcdn",
    "taleo": r"taleo\.net", "brassring": r"brassring", "dayforce": r"dayforcehcm", "ukg": r"ultipro|recruiting\.ukg|ukg\.net",
    "paylocity": r"paylocity", "bamboohr": r"bamboohr\.com", "workable": r"workable\.com", "smartrecruiters": r"smartrecruiters",
    "icims": r"icims\.com", "jobvite": r"jobvite", "greenhouse": r"greenhouse\.io", "lever": r"lever\.co",
    "ashby": r"ashbyhq", "rippling": r"ats\.rippling", "careerpuck": r"careerpuck", "eightfold": r"eightfold",
    "workday": r"myworkday(?:jobs|site)", "oracle": r"oraclecloud\.com", "gem": r"jobs\.gem\.com", "pinpoint": r"pinpointhq",
    "breezy": r"breezy\.hr", "recruitee": r"recruitee", "teamtailor": r"teamtailor", "jazzhr": r"applytojob|jazzhr",
    "dover": r"dover\.com|app\.dover", "personio": r"personio", "comeet": r"comeet", "welcome": r"welcometothejungle",
}
JOB_LINK = re.compile(r'href="([^"]*(?:job|career|position|opening|apply)[^"]*)"', re.I)


def hints(keys: list[str]) -> None:
    """For pages that name no job system: which hiring systems' fingerprints the page carries, and its job-ish links."""
    cfg = home_config()
    hs = http_settings(cfg)
    hs.retries = 1
    gate = make_gate(cfg)
    given = dict(k.split("=", 1) for k in keys if "=" in k)  # key=url reads that page instead
    for c in load_candidates([k.split("=", 1)[0] for k in keys]):
        try:
            with Http(hs, gate=gate) as http:
                r = http.get(given.get(c["key"]) or c["urls"][0], headers={"Accept": "text/html,*/*;q=0.8"})
        except Exception as e:  # noqa: BLE001
            print(f"{c['key']:22} {outcome(e)}: {str(e)[:120]}")
            continue
        marks = [n for n, rx in FINGERPRINTS.items() if re.search(rx, r.text, re.I)]
        links = []
        for m in JOB_LINK.finditer(r.text):
            u = m.group(1)
            if u.startswith(("http", "/")) and u not in links and not u.endswith((".css", ".js", ".png", ".svg")):
                links.append(u)
        print(f"{c['key']:22} [{', '.join(marks)}] {' '.join(links[:5])[:220]}")
    save_robots(gate.cache_dir)


PROBES = {  # one cheap request per token and system; 404 means no such board
    "greenhouse": ("https://boards-api.greenhouse.io/v1/boards/{t}/jobs", lambda d: len(d.get("jobs") or [])),
    "ashby": ("https://api.ashbyhq.com/posting-api/job-board/{t}", lambda d: len(d.get("jobs") or [])),
    "lever": ("https://api.lever.co/v0/postings/{t}?mode=json", lambda d: len(d) if isinstance(d, list) else 0),
}


def probe(args: list[str]) -> None:
    """key=token1,token2 …: which Greenhouse, Ashby and Lever boards exist under each token, with their job counts."""
    cfg = home_config()
    hs = http_settings(cfg)
    hs.retries = 1
    gate = make_gate(cfg)
    jobs = [(a.split("=", 1)[0], t, system) for a in args for t in a.split("=", 1)[1].split(",") for system in PROBES]

    def one(item):
        key, t, system = item
        url, count = PROBES[system]
        with Http(hs, gate=gate) as http:
            try:
                r = http.get(url.format(t=t), ok_statuses=(404,))
                return key, t, system, (count(json.loads(r.text)) if r.status == 200 else None)
            except Exception as e:  # noqa: BLE001
                return key, t, system, f"error {str(e)[:80]}"

    with ThreadPoolExecutor(max_workers=6) as pool:
        for key, t, system, n in pool.map(one, jobs):
            if n is not None:
                print(f"{key:22} {system:10} {t:28} {n}")
    save_robots(gate.cache_dir)


SLOW = {"workday", "oracle", "eightfold", "phenom", "jibe", "icims", "smartrecruiters", "avature", "talentbrew"}
ORDER = ["workday", "oracle", "eightfold", "phenom", "jibe", "icims", "smartrecruiters"]  # longest reads start first


def read(keys: list[str]) -> None:
    """One full read of every entry in discovery/candidates/reads.yaml through the project's own checker: jobs,
    student roles, roles matching the filters (default locations), seconds, requests and partial/degraded flags.
    Each read's jobs go to $STAGE1_RAW/jobs/<entry>.json.gz for the coverage checks."""
    import gzip
    from internwatch.config import Company
    from internwatch.filters import evaluate, is_student_role
    from internwatch.runner import run_checker
    cfg = home_config()
    reads = yaml.safe_load((CANDIDATES / "reads.yaml").read_text())["reads"]
    names = {r["key"]: r for r in load_candidates([])}
    done = set(json.loads((CANDIDATES / "read_results.json").read_text())) if "--new" in keys else set()
    keys = [k for k in keys if k != "--new"]
    todo = [(k, v) for k, v in reads.items() if k not in done and (not keys or k in keys or k.split("~")[0] in keys)]
    todo.sort(key=lambda kv: ORDER.index(kv[1]["checker"]) if kv[1]["checker"] in ORDER else len(ORDER))
    gate = make_gate(cfg)
    store = raw_dir() / "jobs"
    store.mkdir(exist_ok=True)
    path = CANDIDATES / os.environ.get("STAGE1_RESULTS", "read_results.json")
    results = json.loads(path.read_text()) if path.exists() else {}

    def one(kv):
        entry, spec = kv
        base = names[entry.split("~")[0]]
        c = Company(key=entry, name=base["name"], category=base.get("category", ""), careers_url=base["urls"],
                    checker=spec["checker"], settings=spec.get("settings") or {},
                    timeout_minutes=spec.get("timeout_minutes") or (45 if spec["checker"] in SLOW else 8))
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        o = run_checker(cfg, c, gate=gate)
        jobs = o.jobs or []
        students = [j for j in jobs if is_student_role(j, cfg.rules)]
        matched = [j for j in jobs if evaluate(j, cfg.rules, category=c.category, locations=c.locations).matched]
        with gzip.open(store / f"{entry}.json.gz", "wt") as f:
            json.dump([{"id": j.id, "title": j.title, "location": j.location, "url": j.url, "posted": j.posted,
                        "department": j.department, "employment_type": j.employment_type,
                        "alt_ids": (j.extra or {}).get("alt_ids") or []} for j in jobs], f)
        return entry, {"checker": c.checker, "ok": o.ok if hasattr(o, "ok") else not o.error, "error": o.error,
                       "error_kind": o.error_kind, "jobs": len(jobs), "students": len(students),
                       "matched": len(matched), "seconds": round(o.duration, 1), "requests": o.requests,
                       "partial": o.partial, "degraded": o.degraded, "reported_total": o.reported_total,
                       "started": started}

    with ThreadPoolExecutor(max_workers=8) as pool:
        for entry, res in pool.map(one, todo):
            results[entry] = res
            path.write_text(json.dumps(dict(sorted(results.items())), indent=1) + "\n")
            print(f"{entry:28} {res['checker']:15} jobs {res['jobs']:6} students {res['students']:4} matched "
                  f"{res['matched']:4} {res['seconds']:7}s {res['requests']:5} req "
                  f"{'PARTIAL ' if res['partial'] else ''}{'DEGRADED ' if res['degraded'] else ''}"
                  f"{(res['error'] or '')[:100]}", flush=True)
    save_robots(gate.cache_dir)


def read_settings() -> dict[str, tuple[str, dict]]:
    """Each candidate's checker + settings for matching: its reads in reads.yaml, several as a multi."""
    reads = yaml.safe_load((CANDIDATES / "reads.yaml").read_text())["reads"]
    by: dict[str, list] = {}
    for entry, spec in reads.items():
        by.setdefault(entry.split("~")[0], []).append((spec["checker"], spec.get("settings") or {}))
    return {k: v[0] if len(v) == 1 else ("multi", {"sources": [{"checker": c, "settings": s} for c, s in v]})
            for k, v in by.items()}


def sites(keys: list[str]) -> None:
    """Every site in each candidate Workday tenant's robots.txt (cached by the reads; no request): the public ones
    the `new site` alert watches and the hidden ones (Disallow), against the sites read."""
    from internwatch.http import HostGate
    from internwatch.moves import workday_robots_sites
    from internwatch.liveness import workday_sites
    cfg = home_config()
    gate = HostGate(cfg.settings.path("robots_cache"))
    reads = yaml.safe_load((CANDIDATES / "reads.yaml").read_text())["reads"]
    out = {}
    for entry, spec in reads.items():
        s = spec.get("settings") or {}
        if spec["checker"] != "workday" or (keys and entry.split("~")[0] not in keys):
            continue
        disk = gate._disk_get(f"https://{s['host']}")
        if not disk:
            print(f"{entry:24} {s['host']}: robots.txt not cached")
            continue
        public = workday_sites(disk[1])
        allow, hidden = workday_robots_sites(disk[1])
        read_sites = {x.lower() for x in (s.get("sites") or [s.get("site")])}
        if "myworkdaysite.com" in s["host"]:  # robots.txt there answers for every tenant (422 or generic)
            public, allow, hidden = set(), set(), set()
        out[entry] = {"host": s["host"], "read": sorted(read_sites),
                      "public_unread": sorted(x for x in public | allow if x.lower() not in read_sites),
                      "hidden_unread": sorted(x for x in hidden if x.lower() not in read_sites)}
        print(f"{entry:24} read {','.join(sorted(read_sites))[:40]:40} public+ {','.join(out[entry]['public_unread'])[:60]:60}"
              f" hidden+ {','.join(out[entry]['hidden_unread'])[:80]}")
    (CANDIDATES / "workday_sites.json").write_text(json.dumps(out, indent=1) + "\n")


def _read_jobs(entry: str) -> list[dict]:
    import gzip
    p = raw_dir() / "jobs" / f"{entry}.json.gz"
    return json.loads(gzip.open(p, "rt").read()) if p.exists() else []


def _find(jobs: list[dict], url: str, title: str, terms: str, location: str):
    """crosscheck.find_in_db against a read's jobs instead of the database (open postings only)."""
    from internwatch.crosscheck import _YEARS, _id_in_url, clean_url, title_key
    from internwatch.locations import location_decision
    u = url.lower()
    for j in jobs:
        jid = re.sub(r"^[a-z]+:", "", str(j["id"]).lower())
        ids = [jid, jid.strip("/").split("/")[-1], *(str(a).lower() for a in j.get("alt_ids") or [])]
        if any(_id_in_url(i, u) for i in ids):
            return j, "id"
        if j.get("url") and clean_url(j["url"]).lower() == u:
            return j, "url"
    t, years = title_key(title), set(_YEARS.findall(f"{title} {terms}"))
    twins = [j for j in jobs if title_key(j["title"]) == t and not (
        years and set(_YEARS.findall(j["title"])) and not years & set(_YEARS.findall(j["title"])))]
    if not twins:
        return None, ""
    in_us = location_decision(location, ["US"])[0]
    return next((j for j in twins if not location or location_decision(j["location"], ["US"])[0] == in_us), twins[0]), "title"


def _index(cfg, rows):
    from internwatch.crosscheck import CompanyIndex
    cands = candidate_companies(cfg, rows, read_settings())
    return cands, CompanyIndex(cfg.companies + cands)


def coverage(keys: list[str]) -> None:
    """Every row today's SimplifyJobs list holds open for a candidate (matched as the cross-check will match it, with
    the 198 first) must be found in that candidate's reads; prints the ones that aren't."""
    from internwatch.crosscheck import parse_listings
    cfg = home_config()
    rows = load_candidates(keys)
    cands, index = _index(cfg, rows)
    keyset = {c.key for c in cands}
    reads = yaml.safe_load((CANDIDATES / "reads.yaml").read_text())["reads"]
    jobs = {k: [j for e in reads if e.split("~")[0] == k for j in _read_jobs(e)] for k in keyset}
    listing = parse_listings((raw_dir() / "lists" / "simplify.txt").read_text(), "summer")
    out: dict[str, dict] = {}
    for r in listing:
        if r.closed:
            continue
        k = index.match(r)
        if k not in keyset:
            continue
        hit, how = _find(jobs[k], r.url, r.title, r.terms, r.location)
        d = out.setdefault(k, {"open": 0, "found": 0, "missing": []})
        d["open"] += 1
        if hit:
            d["found"] += 1
        else:
            d["missing"].append([r.title, r.location, r.url])
    (CANDIDATES / "simplify_coverage.json").write_text(json.dumps(dict(sorted(out.items())), indent=1) + "\n")
    for k, d in sorted(out.items()):
        if d["missing"]:
            print(f"{k:22} open {d['open']:3} found {d['found']:3} MISSING {len(d['missing'])}: "
                  + "; ".join(f"{t[:40]} <{u[:70]}>" for t, _, u in d["missing"][:2]))
    print(f"{sum(d['open'] for d in out.values())} open rows at {len(out)} candidates, "
          f"{sum(len(d['missing']) for d in out.values())} not found in the reads")


def clashes(keys: list[str]) -> None:
    """For each candidate name: stored and current Simplify rows that match it by name alone (their link is none of
    the candidate's boards), and the raw company names behind them, so a clash with an outside company shows."""
    import sqlite3
    from internwatch.crosscheck import norm_company, parse_listings, url_markers
    cfg = home_config()
    rows = load_candidates(keys)
    cands, _ = _index(cfg, rows)
    taken = {norm_company(n) for c in cfg.companies for n in c.all_names}  # the 198 keep these names
    db = sqlite3.connect(f"file:{cfg.settings.path('db')}?mode=ro", uri=True)
    stored = [(r[0] or "", (r[1] or "").lower(), "stored") for r in db.execute("SELECT company, url FROM simplify_rows")]
    listing = parse_listings((raw_dir() / "lists" / "simplify.txt").read_text(), "summer")
    current = [(r.company, r.url.lower(), "current") for r in listing if not r.closed]
    out = {}
    for c in cands:
        names = {norm_company(n) for n in c.all_names} - taken
        marks = url_markers(c)
        hits = {"stored": [0, 0], "current": [0, 0]}
        outside: dict[str, int] = {}
        for comp, url, where in stored + current:
            if norm_company(comp) not in names:
                continue
            own = any(m in url for m in marks)
            hits[where][0 if own else 1] += 1
            if not own:
                outside[comp] = outside.get(comp, 0) + 1
        out[c.key] = {"stored_own": hits["stored"][0], "stored_other_link": hits["stored"][1],
                      "current_own": hits["current"][0], "current_other_link": hits["current"][1],
                      "names_with_other_links": outside}
        if outside:
            print(f"{c.key:22} stored own/other {hits['stored'][0]}/{hits['stored'][1]}  current own/other "
                  f"{hits['current'][0]}/{hits['current'][1]}  {outside}")
    (CANDIDATES / "name_clashes.json").write_text(json.dumps(out, indent=1) + "\n")


def rematch(keys: list[str]) -> None:
    """Go-live dry run on the database copy: the stored rows with no company that each candidate would take, how many
    Simplify still lists open (they get possible-miss checks), how many an untracked list already showed (passing
    the filters, in a software/data/quant category), and how many open ones its reads don't have (day-one misses)."""
    import sqlite3
    from internwatch.crosscheck import YOUR_CATEGORIES, Row, parse_listings
    from internwatch.filters import evaluate
    from internwatch.models import Job
    cfg = home_config()
    rows = load_candidates(keys)
    cands, index = _index(cfg, rows)
    keyset = {c.key for c in cands}
    reads = yaml.safe_load((CANDIDATES / "reads.yaml").read_text())["reads"]
    listing = {r.key: r for r in parse_listings((raw_dir() / "lists" / "simplify.txt").read_text(), "summer")}
    db = sqlite3.connect(f"file:{cfg.settings.path('db')}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    out: dict[str, dict] = {}
    jobs_cache: dict[str, list] = {}
    for r in db.execute("SELECT * FROM simplify_rows WHERE tracked_company IS NULL"):
        k = index.match(Row("", "", r["company"] or "", "", "", r["url"] or "", "", ""))
        if k not in keyset:
            continue
        d = out.setdefault(k, {"rows": 0, "untracked": 0, "baseline": 0, "open": 0, "shown": 0, "day_one_misses": []})
        d["rows"] += 1
        d[r["status"]] = d.get(r["status"], 0) + 1
        lr = listing.get(r["row_key"])
        is_open = lr is not None and not lr.closed
        infield = any(x in (r["category"] or "").lower() for x in YOUR_CATEGORIES)
        if r["status"] == "untracked" and infield and evaluate(
                Job(id=r["row_key"], title=r["title"] or "", location=r["location"] or "", snippet=r["terms"] or "",
                    employment_type="Intern"), cfg.rules,
                category="quant" if "quant" in (r["category"] or "").lower() else "").matched:
            d["shown"] += 1
        if is_open and r["status"] == "untracked":
            d["open"] += 1
            if k not in jobs_cache:
                jobs_cache[k] = [j for e in reads if e.split("~")[0] == k for j in _read_jobs(e)]
            hit, _ = _find(jobs_cache[k], r["url"] or "", r["title"] or "", r["terms"] or "", r["location"] or "")
            if hit is None:
                d["day_one_misses"].append([r["title"], r["url"]])
    (CANDIDATES / "rematch.json").write_text(json.dumps(dict(sorted(out.items())), indent=1) + "\n")
    for k, d in sorted(out.items()):
        print(f"{k:22} rows {d['rows']:3} (untracked {d['untracked']:3}, baseline {d['baseline']:3}) open {d['open']:3} "
              f"shown {d['shown']:3} day-one misses {len(d['day_one_misses'])}")
    tot = lambda f: sum(f(d) for d in out.values())  # noqa: E731
    print(f"total: {tot(lambda d: d['rows'])} rows to {len(out)} candidates; {tot(lambda d: d['open'])} open untracked "
          f"rows get checks; {tot(lambda d: d['shown'])} were shown in untracked lists; "
          f"{tot(lambda d: len(d['day_one_misses']))} day-one possible misses")


JOB_URL = re.compile(r"/jobs?/[^/]*\d{3,}|/job/|gh_jid=|/positions?/|/careers?/[\w-]*\d{4,}", re.I)
STUDENT_URL = re.compile(r"intern|student|universit|campus|early[-_]?career|graduate|emerging|program|co-?op|apprentic",
                         re.I)


def backup(keys: list[str]) -> None:
    """For each candidate whose careers page refuses scripts: what its backup checks could read. Its sitemaps (job
    pages and student or program pages in them), a WordPress page API on the careers and main hosts, and archive.org
    copies of the careers page from the last 45 days. Writes discovery/candidates/backup_probe.json."""
    cfg = home_config()
    hs = http_settings(cfg)
    hs.retries = 0
    gate = make_gate(cfg)
    pages_seen = json.loads((CANDIDATES / "pages.json").read_text())
    rows = [r for r in load_candidates(keys) if keys or pages_seen.get(r["key"], {}).get("outcome") in ("refused", "robots")]
    path = CANDIDATES / "backup_probe.json"
    out = json.loads(path.read_text()) if path.exists() else {}

    def one(c):
        url = c["urls"][0]
        host = urlsplit(url).netloc
        parts = host.split(".")
        main = "www." + ".".join(parts[-2:]) if len(parts) >= 2 else host
        res = {"careers_url": url, "sitemaps": {}, "wordpress": [], "archive_copies": None}
        with Http(hs, gate=gate) as http:
            maps = []
            for h in dict.fromkeys([host, main]):
                try:
                    rules_text = http.get(f"https://{h}/robots.txt", check_robots=False, ok_statuses=(403, 404)).text
                    maps += re.findall(r"(?im)^sitemap:\s*(\S+)", rules_text)
                except Exception:  # noqa: BLE001
                    pass
                maps.append(f"https://{h}/sitemap.xml")
            seen = set()
            for sm in list(dict.fromkeys(maps))[:8]:
                if sm in seen:
                    continue
                seen.add(sm)
                try:
                    text = http.get(sm, headers={"Accept": "application/xml,*/*"}, timeout=40).text
                except Exception as e:  # noqa: BLE001
                    res["sitemaps"][sm] = outcome(e)
                    continue
                locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)
                children = [x for x in locs if x.endswith(".xml") or "sitemap" in x.lower()]
                res["sitemaps"][sm] = {"urls": len(locs), "jobs": sum(bool(JOB_URL.search(x)) for x in locs),
                                       "student_pages": sorted(x for x in locs if STUDENT_URL.search(x))[:8],
                                       "children": children[:12]}
            for h in dict.fromkeys([host, main]):
                try:
                    r = http.get(f"https://{h}/wp-json/wp/v2/pages", params={"per_page": 1, "_fields": "link"},
                                 headers={"Accept": "application/json"})
                    if r.text.lstrip().startswith("["):
                        res["wordpress"].append({"host": h, "pages": int(r.headers.get("x-wp-total") or 0)})
                except Exception:  # noqa: BLE001
                    pass
            try:
                r = http.get("https://web.archive.org/cdx/search/cdx", timeout=45,
                             params={"url": url, "output": "json", "from": time.strftime("%Y%m%d", time.gmtime(
                                 time.time() - 45 * 86400)), "limit": 50, "fl": "timestamp,statuscode"})
                res["archive_copies"] = max(0, len(json.loads(r.text or "[]")) - 1)
            except Exception as e:  # noqa: BLE001
                res["archive_copies"] = outcome(e)
        return c["key"], res

    with ThreadPoolExecutor(max_workers=4) as pool:
        for key, res in pool.map(one, rows):
            out[key] = res
            maps = {u: (v if isinstance(v, str) else f"{v['urls']} urls/{v['jobs']} jobs/{len(v['student_pages'])} student")
                    for u, v in res["sitemaps"].items()}
            print(f"{key:20} wp={res['wordpress']} archive={res['archive_copies']} " +
                  " ".join(f"{urlsplit(u).netloc}{urlsplit(u).path}={v}" for u, v in maps.items())[:220], flush=True)
    path.write_text(json.dumps(dict(sorted(out.items())), indent=1) + "\n")
    save_robots(gate.cache_dir)


def pagecount(keys: list[str]) -> None:
    """The job count the live job site itself shows with filters off, per read: the hosted Greenhouse board's stated
    count, the postings on the hosted Lever page, the hosted Ashby page's own list (the adapter's parser); for the
    other systems the total their own API reported during the read (the careers page shows that same number)."""
    from internwatch.adapters.ashby import Ashby
    cfg = home_config()
    hs = http_settings(cfg)
    hs.retries = 1
    gate = make_gate(cfg)
    reads = yaml.safe_load((CANDIDATES / "reads.yaml").read_text())["reads"]
    results = json.loads((CANDIDATES / "read_results.json").read_text())
    extra = CANDIDATES / "read_results_extra.json"
    if extra.exists():
        results.update(json.loads(extra.read_text()))
    path = CANDIDATES / "pagecounts.json"
    out = json.loads(path.read_text()) if path.exists() else {}
    todo = [(e, s) for e, s in reads.items() if (not keys or e.split("~")[0] in keys) and e in results]

    def one(item):
        entry, spec = item
        s, checker = spec.get("settings") or {}, spec["checker"]
        with Http(hs, gate=gate) as http:
            try:
                if checker == "greenhouse":
                    n = 0
                    for b in s.get("boards") or [s["board"]]:
                        r = http.get(f"https://job-boards.greenhouse.io/{b}", headers={"Accept": "text/html"},
                                     ok_statuses=(404,))
                        m = re.search(r"(\d[\d,]*)\s+jobs?\b", r.text) if r.status == 200 else None
                        n += int(m.group(1).replace(",", "")) if m else 0
                    return entry, {"page_total": n, "how": "hosted Greenhouse board's stated count"}
                if checker == "lever":
                    r = http.get(f"https://jobs.lever.co/{s['site']}", headers={"Accept": "text/html"})
                    return entry, {"page_total": len(re.findall(r'class="posting"', r.text)),
                                   "how": "postings on the hosted Lever page"}
                if checker == "ashby":
                    n = sum(len(Ashby()._hosted(http, {"board": b})) for b in s.get("boards") or [s["board"]])
                    return entry, {"page_total": n, "how": "the hosted Ashby page's job list"}
            except Exception as e:  # noqa: BLE001
                return entry, {"page_total": None, "how": f"not read: {str(e)[:120]}"}
        rt = results[entry].get("reported_total")
        return entry, {"page_total": rt, "how": f"{checker}'s own reported total (the careers page shows it)"
                       if rt else f"{checker}: no total reported; the read's count stands"}

    with ThreadPoolExecutor(max_workers=6) as pool:
        for entry, res in pool.map(one, todo):
            out[entry] = res
    path.write_text(json.dumps(dict(sorted(out.items())), indent=1) + "\n")
    off = []
    for entry, res in sorted(out.items()):
        jobs, pt = results[entry]["jobs"], res["page_total"]
        if isinstance(pt, int) and abs(jobs - pt) > max(3, 0.02 * pt):
            off.append(entry)
            print(f"{entry:30} checker {jobs:6} page {pt:6}  ({res['how'][:60]})")
    print(f"{len(out)} reads compared; {len(off)} differ by more than 3 jobs and 2%")
    save_robots(gate.cache_dir)


def candidate_companies(cfg, rows: list[dict], settings: dict | None = None) -> list:
    """The candidates as Company entries, after the 198 (settings: key -> (checker, settings) where known)."""
    from internwatch.config import Company
    out = []
    for r in rows:
        checker, s = (settings or {}).get(r["key"], ("blocked", {}))
        out.append(Company(key=r["key"], name=r["name"], category=r.get("category", ""), careers_url=r["urls"],
                           checker=checker, settings=s, aliases=r.get("aliases") or []))
    return out


def raw_dir() -> Path:
    d = Path(os.environ.get("STAGE1_RAW") or Path(os.environ["INTERNWATCH_HOME"]).parent / "raw")
    d.mkdir(parents=True, exist_ok=True)
    return d


def lists(keys: list[str]) -> None:
    from internwatch import moves
    from internwatch.crosscheck import CompanyIndex
    cfg = home_config()
    rows = load_candidates(keys)
    cands = candidate_companies(cfg, rows, read_settings() if (CANDIDATES / "reads.yaml").exists() else None)
    index = CompanyIndex(cfg.companies + cands)  # the 198 first: a row of theirs is never taken for a candidate
    comps = {c.key: c for c in cands}
    al = moves.aliases(cfg)
    hs = http_settings(cfg)
    hs.retries = 1
    store = raw_dir() / "lists"
    store.mkdir(exist_ok=True)
    linked: dict[str, dict[str, list]] = {}
    with Http(hs, gate=make_gate(cfg)) as http:
        for src in moves.opts(cfg).get("listings") or []:
            path = store / f"{src['name']}.txt"
            if not path.exists():
                try:
                    path.write_text(http.get(src["url"], timeout=90).text)
                except Exception as e:  # noqa: BLE001
                    print(f"{src['name']}: not read: {str(e)[:160]}")
                    continue
            text = path.read_text()
            parsed = (moves.ripplematch_rows(text) if src["format"] == "ripplematch"
                      else moves.list_rows(src["format"], text))
            n = 0
            for company, title, url, system in parsed:
                c = moves.company_of(index, comps, company, url, slug=src["format"] in ("ripplematch", "trackr"))
                if c is None:
                    continue
                for k in ([al.get(system, system)] if system else moves.systems_in(url, "", c, al)):
                    linked.setdefault(c.key, {}).setdefault(k, [src.get("label", src["name"]), company, title, url])
                    n += 1
            print(f"{src['name']:22} {len(parsed):6} rows, {n} links to candidates")
    path = CANDIDATES / "lists.json"
    path.write_text(json.dumps(dict(sorted(linked.items())), indent=1) + "\n")
    print(f"{len(linked)} candidates linked by some list; saved {path.relative_to(REPO)}")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["help"]
    if cmd == "pages":
        pages(args)
    elif cmd == "lists":
        lists(args)
    elif cmd == "homes":
        homes(args)
    elif cmd == "hints":
        hints(args)
    elif cmd == "probe":
        probe(args)
    elif cmd == "read":
        read(args)
    elif cmd == "sites":
        sites(args)
    elif cmd == "coverage":
        coverage(args)
    elif cmd == "clashes":
        clashes(args)
    elif cmd == "rematch":
        rematch(args)
    elif cmd == "backup":
        backup(args)
    elif cmd == "pagecount":
        pagecount(args)
    else:
        print(__doc__)
