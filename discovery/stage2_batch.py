"""Stage 2: one batch of the companies added in November 2026, from the Stage 1 evidence in discovery/candidates/.

    .venv/bin/python discovery/stage2_batch.py render <batch>   count each company page that draws its job list in
                                                                the browser: headless Chromium, every request it
                                                                makes checked against its site's robots.txt first
                                                                (a disallowed one is never sent). → renders.json
    .venv/bin/python discovery/stage2_batch.py sitecopies <batch>   Workday companies whose sites list one requisition
                                                                more than once, from the last reads → site_copies.yaml
    .venv/bin/python discovery/stage2_batch.py apply <batch>    seed entries (round: added), discovery/results/<key>.json,
                                                                aliases in build_config.py, settings.liveness entries
                                                                (backup checks, side pages); then run build_config.py
    .venv/bin/python discovery/stage2_batch.py listcheck <batch>   after build_config.py: job systems the lists and
                                                                careers pages link that the config doesn't know

Batches follow the plan: 1 Greenhouse, 2 Ashby/Lever/Rippling/RippleMatch, 3 Workday ≤ 2,000 jobs, 4 Workday > 2,000,
5 Oracle/Eightfold/SmartRecruiters/Jibe/Phenom/Radancy/Jobvite/iCIMS, 6 new readers (discovery/candidates/plan.json).
"""
from __future__ import annotations

import asyncio
import gzip
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
C = REPO / "discovery" / "candidates"
MAIN_DATA = REPO / "data" if (REPO / "data" / "stage1").exists() else REPO.parent / "internship-notifier" / "data"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


def load(name):
    return json.loads((C / name).read_text())


def batch(n: int) -> dict:
    return {k: v for k, v in load("plan.json").items() if v["batch"] == n and v["sources"]}


def all_reads() -> dict:
    """The planned reads: reads.yaml, and the second boards found later (reads_subs.yaml)."""
    return {**yaml.safe_load((C / "reads.yaml").read_text())["reads"],
            **yaml.safe_load((C / "reads_subs.yaml").read_text())["reads"]}


def all_results() -> dict:
    return {**load("read_results.json"), **load("read_results_extra.json"), **load("read_results_subs.json")}


def read_jobs(entry: str) -> list[dict]:
    p = MAIN_DATA / "stage1" / "raw" / "jobs" / f"{entry}.json.gz"
    return json.load(gzip.open(p, "rt")) if p.exists() else []


def read_ids(entry: str) -> set[str]:
    return {str(j["id"]) for j in read_jobs(entry)}


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


# render -------------------------------------------------------------------------------------------------------------

def needs_render(k: str, p: dict) -> str | None:
    """The company page to count, when nothing else counted it (the hosted board redirects to a page that draws its
    list in the browser)."""
    main = p["sources"][0]
    if main["checker"] == "rippling":  # its API states no total: the hosted board is the page
        reads = all_reads()
        return f"https://ats.rippling.com/{reads[main['entry']]['settings']['board']}/jobs"
    gh = load("ghpages.json").get(k)
    if not gh or gh["shown"] >= gh["read"] - max(3, 0.02 * gh["read"]):
        return None
    page = next((x for x in gh["pages"] if x.get("status") == 200 and "greenhouse.io" not in (x.get("final_url") or "")),
                None)
    return page["final_url"] if page else None


def render(n: int) -> None:
    from playwright.async_api import async_playwright
    from internwatch import config
    from internwatch.http import Http, HostGate
    from internwatch.runner import http_settings
    cfg = config.load(REPO)
    gate = HostGate(MAIN_DATA / "stage2" / "robots")
    http = Http(http_settings(cfg), gate=gate)
    verdicts: dict[str, bool] = {}

    def allowed(url: str) -> bool:
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        try:
            verdicts[url] = gate.robots(origin, http._fetch_robots, http.s.robots_ttl_hours).allowed(url)
        except Exception:  # noqa: BLE001 — RFC 9309: an unreachable robots.txt means nothing is fetched there
            verdicts[url] = False
        return verdicts[url]

    todo = {k: u for k, p in batch(n).items() if (u := needs_render(k, p))}
    out = load("renders.json") if (C / "renders.json").exists() else {}

    async def one(browser, k, url):
        jobs = [j for s in batch(n)[k]["sources"] for j in read_jobs(s["entry"])]
        ids = {str(j["id"]) for j in jobs}
        refused: list[str] = []
        if not allowed(url):
            return k, {"url": url, "robots": "disallowed: not opened"}
        context = await browser.new_context(user_agent=UA)
        page = await context.new_page()

        async def route(r):
            u = r.request.url
            if u.startswith(("http://", "https://")) and not allowed(u):
                refused.append(u)
                await r.abort()
            else:
                await r.continue_()
        await page.route("**/*", route)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:  # noqa: BLE001 — a page that keeps polling still shows its list
                pass
            for _ in range(6):  # lazy lists load as the page scrolls
                await page.mouse.wheel(0, 5000)
                await page.wait_for_timeout(700)
            html = await page.content()
            if os.environ.get("STAGE2_SAVE"):  # the rendered page, for a closer look
                (MAIN_DATA / "stage2" / "renders").mkdir(parents=True, exist_ok=True)
                (MAIN_DATA / "stage2" / "renders" / f"{k}.html").write_text(html)
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
        except Exception as e:  # noqa: BLE001 — a page that doesn't load is a finding
            return k, {"url": url, "error": str(e)[:200]}
        finally:
            await context.close()
        shown = {i for i in ids if i in html}
        page_text = " " + norm(text) + " "
        titles = {norm(j["title"]) for j in jobs}
        by_title = {x for x in titles if x and f" {x} " in page_text}
        stated = re.findall(r"(\d[\d,]*)\s+(?:open\s+)?(?:jobs|positions|roles|openings|results)\b", text, re.I)[:3]
        links = sorted({urlsplit(h).netloc for h in re.findall(r'href="(https?://[^"]+)"', html)
                        if re.search(r"/jobs?/|gh_jid|/positions?/|/careers?/.+\d", h)})[:8]
        return k, {"url": url, "read": len(ids), "shown": len(shown), "titles_read": len(titles),
                   "titles_shown": len(by_title), "stated": stated, "job_link_hosts": links,
                   "requests_not_sent": len(refused), "robots": "allowed",
                   "not_sent_sample": sorted({u.split("?")[0][:90] for u in refused if "greenhouse" in u or "job" in u})[:4]}

    async def main():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            for k, url in sorted(todo.items()):  # one page at a time: no site sees two renders at once
                k, res = await one(browser, k, url)
                out[k] = res
                print(f"{k:20} read {res.get('read', '-'):>4} ids {res.get('shown', '-'):>4} titles "
                      f"{res.get('titles_shown', '-')}/{res.get('titles_read', '-')} stated {res.get('stated')} "
                      f"links {res.get('job_link_hosts')} "
                      f"{res.get('error') or res.get('robots')} ({res.get('requests_not_sent', 0)} disallowed requests not sent)",
                      flush=True)
            await browser.close()
    asyncio.run(main())
    (C / "renders.json").write_text(json.dumps(dict(sorted(out.items())), indent=1) + "\n")
    http.close()


# apply --------------------------------------------------------------------------------------------------------------

def site_copies() -> dict:
    """Companies whose Workday sites list one requisition more than once (written by `sitecopies`)."""
    path = C / "site_copies.yaml"
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


def sites_read(p: dict) -> dict[str, list[dict]]:
    """The jobs of the last read of each Workday site of a company, in the order its sources name them."""
    reads, out = all_reads(), {}
    for x in p["sources"]:
        if x["checker"] != "workday":
            continue
        st = reads[x["entry"]].get("settings") or {}
        names = st.get("sites") or [st["site"]]
        for site in names:
            out.setdefault(site, [])
        for j in read_jobs(x["entry"]):
            out[str(j["id"]).split(":", 1)[0] if len(names) > 1 else names[0]].append(j)
    return out


def sitecopies(n: int) -> None:
    """Which companies of the batch list a requisition on more than one of their Workday sites, counted in the last
    read of each site (data/stage1/raw/jobs). → site_copies.yaml: such a company is read one site per source with
    `dedupe`, so the copy on a later site is dropped instead of being stored and emailed as a second job."""
    found = {k: v for k, v in site_copies().items() if k not in batch(n)}
    res = all_results()
    for k, p in sorted(batch(n).items()):
        seen: set[str] = set()
        rows = {}
        for site, jobs in sites_read(p).items():
            reqs = [set(map(str, j.get("alt_ids") or [])) for j in jobs]
            rows[site] = {"postings": len(jobs), "copies": sum(1 for r in reqs if r & seen)}
            seen |= set().union(*reqs) if reqs else set()
        if sum(x["copies"] for x in rows.values()):
            at = max(res.get(x["entry"], {}).get("started", "")[:10] for x in p["sources"] if x["checker"] == "workday")
            found[k] = {"at": at, "copies": sum(x["copies"] for x in rows.values()), "sites": rows}
            print(f"{k:22} " + ", ".join(f"{s} {x['copies']}/{x['postings']}" for s, x in rows.items()))
    (C / "site_copies.yaml").write_text(
        "# Companies whose Workday sites list one requisition on more than one site, from the last read of each site\n"
        "# (stage2_batch.py sitecopies): postings on each site, and how many repeat a requisition of an earlier site.\n"
        "# Each is configured one site per source (multi, dedupe), so a copy is not stored as a second job.\n"
        + yaml.safe_dump(found, sort_keys=True, width=120))
    print(f"batch {n}: {sum(1 for k in found if k in batch(n))} companies whose Workday sites repeat each other")


def settings_of(p: dict) -> tuple[str, dict]:
    """The company's checker and settings. Each Workday site is a source of its own: the sites of one tenant repeat
    each other's requisitions on and off (Copart's NPA site and Vanguard's contractor site listed none of the main
    site's on 2026-11-09 and one each on 11-12; KLA's Israel site lists only copies), and `dedupe` drops a later
    site's copy instead of storing it as a second job."""
    reads = all_reads()
    srcs: list[tuple[str, dict]] = []
    for x in p["sources"]:
        if x.get("new_reader"):
            continue
        ck, st = x["checker"], dict(reads[x["entry"]].get("settings") or {})
        if ck != "workday":
            srcs.append((ck, st))
            continue
        base = {k: v for k, v in st.items() if k not in ("site", "sites")}
        for site in st.get("sites") or [st["site"]]:
            if ("workday", {**base, "site": site}) not in srcs:
                srcs.append(("workday", {**base, "site": site}))
    if len(srcs) == 1:
        return srcs[0]
    from internwatch.config import Company
    from internwatch.crosscheck import url_markers
    marks = [m for ck, st in srcs for m in url_markers(Company(key="x", name="x", category="", careers_url=[],
                                                               checker=ck, settings=st))]
    marks += [m.replace(" ", "%20") for m in marks if " " in m]  # a board name with spaces, as links spell it
    # SmartRecruiters links carry the company's name on a shared host: careers. and jobs.smartrecruiters.com/<name>/
    marks += [f"smartrecruiters.com/{st['company'].lower()}/" for ck, st in srcs if ck == "smartrecruiters"]
    marks = list(dict.fromkeys(marks))
    # dedupe_titles (a later board's job with a title already read is a copy) fitted the first two batches' second
    # boards, which only repeat the first. From batch 3 on it is left out: the rule also drops a board's own openings
    # that share a title (Northwestern Mutual's SmartRecruiters page lists "Sr Software Engineer" three times: 11 jobs
    # lost on 2026-11-12, 2 at Snyk), a subsidiary's (NBCUniversal has 14 titles Comcast also uses, each a different
    # job) and another site's of the same Workday tenant. There only an id or requisition both list is a copy.
    titles = {"dedupe_titles": True} if p["batch"] < 3 else {}
    return "multi", {"dedupe": True, **titles, "twin_ids": True, "match_urls": marks,
                     "sources": [{"checker": ck, "settings": st} for ck, st in srcs]}


def feed_of(checker: str, s: dict) -> str:
    if checker == "multi":
        return " + ".join(feed_of(x["checker"], x["settings"]) for x in s["sources"])
    if checker == "greenhouse":
        boards = s.get("boards") or [s["board"]]
        return f"GET https://boards-api.greenhouse.io/v1/boards/{boards[0] if len(boards) == 1 else '{' + ','.join(boards) + '}'}/jobs"
    if checker == "ashby":
        return f"GET https://api.ashbyhq.com/posting-api/job-board/{s.get('board')}"
    if checker == "lever":
        return f"GET https://api.lever.co/v0/postings/{s.get('site')}?mode=json"
    if checker == "rippling":
        return f"GET https://ats.rippling.com/api/v2/board/{s.get('board')}/jobs"
    if checker == "ripplematch":
        return f"GET https://app.ripplematch.com/api/v2/public/roles/{s.get('company_id')}"
    if checker == "workday":
        sites = s.get("sites") or [s["site"]]
        return f"POST https://{s['host']}/wday/cxs/{s['tenant']}/{sites[0] if len(sites) == 1 else '{' + ','.join(sites) + '}'}/jobs"
    if checker == "smartrecruiters":
        return f"GET https://careers.smartrecruiters.com/{s.get('company')}"
    return checker


def counted(v: dict) -> str:
    """The day a page count was taken (Stage 1's, before recounts were dated, were all taken on 2026-11-09)."""
    return v.get("at", "2026-11-09")


def page_count(k: str, p: dict, jobs: int) -> tuple[int | None, str, str]:
    """(page_total, how it was counted, explanation of a difference)."""
    pc, gh, rd = load("pagecounts.json"), load("ghpages.json"), load("renders.json") if (C / "renders.json").exists() else {}
    main = p["sources"][0]["entry"]
    v = pc.get(main) or {}
    others = [(pc.get(s["entry"]) or {}).get("page_total") for s in p["sources"][1:]]
    if others and all(x == 0 for x in others) and isinstance(v.get("page_total"), int) \
            and abs(v["page_total"] - jobs) <= max(3, 0.02 * jobs):  # a second board that lists nothing
        return v["page_total"], v["how"] + "; " + ", ".join(s["entry"].split("~")[-1] + " lists none"
                                                            for s in p["sources"][1:]) + f" ({counted(v)})", ""
    if isinstance(v.get("page_total"), int) and (v["page_total"] or not jobs) and abs(v["page_total"] - jobs) <= max(3, 0.02 * jobs):
        return v["page_total"], v["how"] + f" ({counted(v)})", ""
    each = [(s["entry"], pc.get(s["entry"]) or {}) for s in p["sources"] if not s.get("new_reader")]
    if len(each) > 1 and all(isinstance(x.get("page_total"), int) for _, x in each) \
            and abs(sum(x["page_total"] for _, x in each) - jobs) <= max(3, 0.02 * jobs):  # several sites or boards
        return sum(x["page_total"] for _, x in each), "each read's own count, added up: " + " + ".join(
            f"{x['page_total']} ({e.split('~site-')[-1].split('~')[-1]}: {x['how']})" for e, x in each) + f" ({counted(v)})", ""
    g = gh.get(main)
    if g and g["shown"] >= g["read"] - max(3, 0.02 * g["read"]):
        url = next((x.get("final_url") for x in g["pages"] if x.get("status") == 200), "")
        return g["shown"], f"{url} links {g['shown']} of the {g['read']} jobs read (2026-11-09)", ""
    r = rd.get(k)
    n = (r or {}).get("page_links") or (r or {}).get("shown")
    if r and n and abs(n - r["read"]) <= max(3, 0.02 * r["read"]):
        return n, f"headless render of {r['url']} (robots.txt checked for every request) shows {n} jobs; " \
                  f"{r['read']} read (2026-11-10){'; ' + r['note'] if r.get('note') else ''}", ""
    if r and r.get("explained"):
        return None, f"headless render of {r['url']} (2026-11-10)", r["explained"]
    if g and any("redirects" in (x.get("error") or "") for x in g["pages"]):
        return None, "the hosted board and the careers page redirect in a loop for scripts", \
            "the board's own API is the only list a script can read"
    if g and any(x.get("status") == 403 for x in g["pages"]):
        return None, "the careers page refuses scripts and the hosted board redirects to it", \
            "the board's own API is the only list a script can read"
    if r and r.get("shown") is not None:
        return r["shown"], f"headless render of {r['url']} shows {r['shown']} of the {r['read']} jobs read (2026-11-10)", \
            "the page lists part of the board at a time (pages or a 'more' button)"
    if p["sources"][0]["checker"] == "ripplematch":
        return None, "RippleMatch's page for the company draws its roles from the API that is read", \
            "the company's own careers site refuses scripts, so its RippleMatch page is what is read"
    return None, "not counted on the company page", "the board's own API is the list"


def result(k: str, p: dict, cand: dict) -> dict:
    res = all_results()
    checker, s = settings_of(p)
    jobs = sum(res.get(x["entry"], {}).get("jobs", 0) for x in p["sources"])
    students = sum(res.get(x["entry"], {}).get("students", 0) for x in p["sources"])
    pages = load("pages.json").get(k, {})
    careers = pages.get("final_url") if pages.get("outcome") == "ok" else cand["urls"][0]
    pt, how, why = page_count(k, p, jobs)
    notes = []
    copies = site_copies().get(k)
    if copies:  # read one site per source: a requisition an earlier site lists is dropped
        jobs -= copies["copies"]
        notes.append(f"Its {len(copies['sites'])} Workday sites listed {jobs + copies['copies']} postings on {copies['at']}, "
                     f"{copies['copies']} of them a requisition an earlier site already lists, which is read once.")
    elif isinstance(pt, int) and pt != jobs:  # build_config.py explains a difference with the notes' first sentence
        day = counted(load("pagecounts.json").get(p["sources"][0]["entry"]) or {})
        notes.append(f"The page showed {pt} jobs and the board {jobs} on {day} (a posting or two opened or "
                     f"closed in between).")
    if p["blocked_page"]:
        notes.append(f"The careers page {('is closed by robots.txt' if p['page'] == 'robots' else 'refuses scripts')}: "
                     f"the company is in liveness.blocked, with backup checks (backup_table.md).")
    subs = [x["subsidiary"] for x in p["sources"] if x.get("subsidiary")]
    if subs:
        notes.append("Read with it, as part of the company: " + "; ".join(subs) + ".")
    if checker == "multi":
        notes.append(("Two boards: " if len(s["sources"]) == 2 else f"{len(s['sources'])} boards: ")
                     + " + ".join(feed_of(x["checker"], x["settings"]) for x in s["sources"]) +
                     ("; a later board's posting with an earlier one's id or title is skipped." if s.get("dedupe_titles")
                      else "; a later board's posting with an earlier one's id or requisition is skipped."))
    notes += [f"Not read: {d['entry']}: {d['why']}." for d in p["dropped"]]
    notes += [f"Watched, not stored: {x['entry']} ({x.get('jobs', 0)} jobs)." for x in p["side"]]
    if why:
        notes.append(f"Page count: {why}.")
    host = urlsplit(feed_of(checker, s).split(" ")[1] if " " in feed_of(checker, s) else "").netloc
    return {"key": k, "name": cand["name"], "careers_url": careers, "hiring_system": checker, "checker": checker,
            "settings": s, "feed": feed_of(checker, s), "feed_total": jobs, "page_total": pt, "page_total_how": how,
            "intern_total": students, "status": "verified", "blocked_reason": "", "fallback": "",
            "robots": f"{host}/robots.txt checked before every request (discovery/robots/{host}.txt)" if host else "",
            "notes": " ".join(notes),
            "checked_at": max(res.get(x["entry"], {}).get("started", "2026-11-09")[:10] for x in p["sources"]),
            "source": "added", "round": "added",
            **({"explained": f"{why[0].upper()}{why[1:]} ({how})."} if pt is None and why else {})}


def add_seed(entries: list[dict]) -> None:
    path = REPO / "discovery" / "companies_seed.yaml"
    text = path.read_text()
    have = set(re.findall(r"key: ([a-z0-9-]+)", text))
    lines = [f"  - {{key: {e['key']}, name: {json.dumps(e['name'])}, category: {e['category']}, source: added, "
             f"round: added, urls: {json.dumps(e['urls'])}}}\n" for e in entries if e["key"] not in have]
    if lines:
        path.write_text(text.rstrip("\n") + "\n" + "".join(lines))


def add_aliases(entries: list[dict]) -> None:
    path = REPO / "discovery" / "build_config.py"
    text = path.read_text()
    head, rest = text.split("ALIASES = {", 1)
    body, tail = rest.split("\n}", 1)  # the dict's own closing brace
    adds = [e for e in entries if e.get("aliases") and f'"{e["key"]}": ' not in body]
    if adds:
        marker = "    # added in November 2026 (round: added)"
        body += ("" if marker in body else "\n" + marker) + "".join(
            f'\n    "{e["key"]}": {json.dumps(e["aliases"])},' for e in adds)
        path.write_text(head + "ALIASES = {" + body + "\n}" + tail)


def add_settings(n: int, plan: dict) -> None:
    """settings.liveness entries of the batch's companies, appended to each list or map (the 198's untouched)."""
    path = REPO / "config" / "settings.yaml"
    text = path.read_text()
    bp = load("backup_probe.json")
    blocked = [k for k, p in plan.items() if p["blocked_page"]]
    m = re.search(r"(  blocked: \[)(.*?)(\])", text, re.S)
    have = {x.strip() for x in m.group(2).replace("\n", " ").split(",")}
    new = [k for k in blocked if k not in have]
    if new:
        text = text[:m.end(2)] + ",\n            " + ", ".join(new) + text[m.end(2):]

    def append(section: str, lines: list[str]) -> None:
        nonlocal text
        lines = [x for x in lines if x not in text]  # already there from an earlier run of this batch
        if not lines:
            return
        start = text.index(f"\n  {section}:") + 1
        nxt = re.compile(r"^(?:\S|  [a-z_]+:)", re.M)  # the next sibling key or top-level section ends the block
        end = nxt.search(text, text.index("\n", start) + 1)
        end = end.start() if end else len(text)
        body = text[start:end].rstrip("\n")  # after the block's last line, before any blank lines
        at = start + len(body) + 1
        text = text[:at] + "".join(x + "\n" for x in lines) + text[at:]

    jobs, wp, prog, arch, watch, al = [], [], [], [], [], []
    for k in blocked:
        v = bp.get(k) or {}
        maps = {u: x for u, x in (v.get("sitemaps") or {}).items() if isinstance(x, dict)}
        job_map = next((u for u, x in maps.items() if x.get("jobs")), None)
        if job_map:
            jobs.append(f'    {k}: {{url: "{job_map}"}}')
        if v.get("wordpress"):
            wp.append(f"    {k}: https://{v['wordpress'][0]['host']}")
        progs = [u for u, x in maps.items() if x.get("student_pages")] + [f"wp:https://{w['host']}" for w in v.get("wordpress") or []]
        if progs:
            prog.append(f"    {k}: {json.dumps(progs)}")
        if isinstance(v.get("archive_copies"), int) and v["archive_copies"] > 0:
            arch.append(f'    {k}: {{pages: ["{v["careers_url"]}"]}}')
    rm = load("ripplematch.json")
    reads = all_reads()
    for k, p in plan.items():
        for s in p["side"]:
            if s["checker"] == "ripplematch" and k in rm:
                cid = rm[k]["company_id"]
                watch.append(f"    - {{company: {k}, name: RippleMatch, checker: ripplematch, settings: {{company_id: {cid}}}}}")
                main = p["sources"][0]
                st = reads[main["entry"]].get("settings") or {}
                if main["checker"] == "workday":
                    from internwatch.moves import system_key_v2
                    target = system_key_v2("workday", {**st, "site": (st.get("sites") or [st.get("site")])[0]})
                else:
                    target = f"{main['checker']}:board={(st.get('board') or st.get('boards', [''])[0]).lower()}"
                al.append(f"    ripplematch:company={rm[k]['slug']}: '{target}'   # {k}: its RippleMatch page, watched")
    mirrors, cant = yaml.safe_load((C / "mirrors.yaml").read_text()), []
    for k in sorted(plan):
        for m in mirrors.get(k) or []:
            if m.get("unreadable"):  # a site its careers page names that no script may read: listed, never read
                cant.append(f'    - {{company: {k}, board: "{m["system"]}", why: {m["unreadable"]}}}')
            else:
                al.append(f"    {m['system']}: '{m['as']}'   # {k}: {m['why'].split(';')[0]}")
    append("watch_unreadable", cant)
    append("watch_boards", watch)
    append("job_lists", jobs)
    append("wp_pages", wp)
    append("program_pages", prog)
    append("archive_paths", arch)
    append("aliases", al)
    path.write_text(text)


def apply(n: int) -> None:
    plan = batch(n)
    cands = {c["key"]: c for c in yaml.safe_load((C / "candidates.yaml").read_text())["companies"]}
    for k, p in sorted(plan.items()):
        (REPO / "discovery" / "results" / f"{k}.json").write_text(json.dumps(result(k, p, cands[k]), indent=2) + "\n")
    order = sorted(plan, key=lambda k: -sum(s.get("seconds", 0) for s in plan[k]["sources"]))  # longest first
    add_seed([cands[k] for k in order])
    add_aliases([cands[k] for k in order])
    add_settings(n, plan)
    print(f"batch {n}: {len(plan)} companies; now run discovery/build_config.py")


def listcheck(n: int) -> None:
    """Before a batch's go-live morning is recorded: the job systems linked for its companies that the final config
    doesn't count as known (its own boards, parallel boards, liveness.aliases). The lists the last morning kept
    (data/lists) are matched with the final config, as the round's list check will match them (names and aliases
    included): such a link would raise `new job site?` on the first morning, so read it, record it in mirrors.yaml,
    or expect the alert. Then the systems each careers page named when it was last read (pages.json), as the page
    check names them: one that isn't configured sits in that check's silent first look for good, so explain it."""
    from types import SimpleNamespace
    from internwatch import config, liveness, moves
    from internwatch.crosscheck import CompanyIndex
    cfg = config.load(REPO)
    ctx = SimpleNamespace(cfg=cfg.scoped("added"))
    al, keys = moves.aliases(ctx.cfg), set(batch(n))
    comps = {c.key: c for c in ctx.cfg.active}
    index = CompanyIndex(cfg.companies)
    seen: dict[tuple[str, str], str] = {}
    for src in moves.opts(cfg).get("listings") or []:
        path = MAIN_DATA / "lists" / f"{src['name']}.txt"
        if not path.exists():
            print(f"(no kept copy of the list {src['name']}: not checked)")
            continue
        text = path.read_text()
        rows = moves.ripplematch_rows(text) if src["format"] == "ripplematch" else moves.list_rows(src["format"], text)
        for company, title, url, system in rows:
            c = moves.company_of(index, comps, company, url, slug=src["format"] in ("ripplematch", "trackr"))
            if c is not None and c.key in keys:
                for k in ([al.get(system, system)] if system else moves.systems_in(url, "", c, al)):
                    seen.setdefault((c.key, k), f"list: {src.get('label', src['name'])} ({company!r} {url})")
    found = 0
    for (k, system), where in sorted(seen.items()):
        if system not in moves.known_systems(ctx, cfg.company(k)) and not system.startswith("other:"):
            found += 1
            print(f"{k:22} {system:50} {where[:150]}")
    print(f"batch {n}: {found} job systems the lists link that the config doesn't know")
    pages, named = load("pages.json"), 0
    for k in sorted(keys):
        c = cfg.company(k)
        mine = liveness.config_keys(c) | liveness.config_keys(c, liveness.page_key)
        for system in sorted((pages.get(k) or {}).get("systems") or []):
            if system not in mine and al.get(system, system) not in moves.known_systems(ctx, c):
                named += 1
                print(f"{k:22} {system:50} its careers page names it (silent first look)")
    print(f"batch {n}: {named} job systems the careers pages name that the config doesn't read")


if __name__ == "__main__":
    cmd, n = sys.argv[1], int(sys.argv[2])
    {"render": render, "apply": apply, "listcheck": listcheck, "sitecopies": sitecopies}[cmd](n)
