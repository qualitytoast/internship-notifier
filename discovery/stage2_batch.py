"""Stage 2: one batch of the companies added in November 2026, from the Stage 1 evidence in discovery/candidates/.

    .venv/bin/python discovery/stage2_batch.py render <batch>   count each company page that draws its job list in
                                                                the browser: headless Chromium, every request it
                                                                makes checked against its site's robots.txt first
                                                                (a disallowed one is never sent). → renders.json
    .venv/bin/python discovery/stage2_batch.py apply <batch>    seed entries (round: added), discovery/results/<key>.json,
                                                                aliases in build_config.py, settings.liveness entries
                                                                (backup checks, side pages); then run build_config.py

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

def settings_of(p: dict) -> tuple[str, dict]:
    reads = yaml.safe_load((C / "reads.yaml").read_text())["reads"]
    srcs = [(s["checker"], reads[s["entry"]].get("settings") or {}) for s in p["sources"] if not s.get("new_reader")]
    if len(srcs) == 1:
        return srcs[0]
    from internwatch.config import Company
    from internwatch.crosscheck import url_markers
    marks = [m for ck, st in srcs for m in url_markers(Company(key="x", name="x", category="", careers_url=[],
                                                               checker=ck, settings=st))]
    return "multi", {"dedupe": True, "dedupe_titles": True, "match_urls": marks,
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
    return checker


def page_count(k: str, p: dict, jobs: int) -> tuple[int | None, str, str]:
    """(page_total, how it was counted, explanation of a difference)."""
    pc, gh, rd = load("pagecounts.json"), load("ghpages.json"), load("renders.json") if (C / "renders.json").exists() else {}
    main = p["sources"][0]["entry"]
    v = pc.get(main) or {}
    if isinstance(v.get("page_total"), int) and v["page_total"] and abs(v["page_total"] - jobs) <= max(3, 0.02 * jobs):
        return v["page_total"], v["how"] + " (2026-11-09)", ""
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
    if g and any(x.get("status") == 403 for x in g["pages"]):
        return None, "the careers page refuses scripts and the hosted board redirects to it", \
            "the board's own API is the only list a script can read"
    if r and r.get("shown") is not None:
        return r["shown"], f"headless render of {r['url']} shows {r['shown']} of the {r['read']} jobs read (2026-11-10)", \
            "the page lists part of the board at a time (pages or a 'more' button)"
    return None, "not counted on the company page", "the board's own API is the list"


def result(k: str, p: dict, cand: dict) -> dict:
    res = {**load("read_results.json"), **load("read_results_extra.json")}
    checker, s = settings_of(p)
    jobs = sum(res.get(x["entry"], {}).get("jobs", 0) for x in p["sources"])
    students = sum(res.get(x["entry"], {}).get("students", 0) for x in p["sources"])
    pages = load("pages.json").get(k, {})
    careers = pages.get("final_url") if pages.get("outcome") == "ok" else cand["urls"][0]
    pt, how, why = page_count(k, p, jobs)
    notes = []
    if isinstance(pt, int) and pt != jobs:  # build_config.py explains a difference with the notes' first sentence
        notes.append(f"The page showed {pt} jobs and the board {jobs} on 2026-11-09 (a posting or two opened or "
                     f"closed in between).")
    if p["blocked_page"]:
        notes.append(f"The careers page {('is closed by robots.txt' if p['page'] == 'robots' else 'refuses scripts')}: "
                     f"the company is in liveness.blocked, with backup checks (backup_table.md).")
    if checker == "multi":
        notes.append("Two boards: " + " + ".join(feed_of(x["checker"], x["settings"]) for x in s["sources"]) +
                     "; a later board's posting with an earlier one's id or title is skipped.")
    notes += [f"Not read: {d['entry']}: {d['why']}." for d in p["dropped"]]
    notes += [f"Watched, not stored: {x['entry']} ({x.get('jobs', 0)} jobs)." for x in p["side"]]
    if why:
        notes.append(f"Page count: {why}.")
    host = urlsplit(feed_of(checker, s).split(" ")[1] if " " in feed_of(checker, s) else "").netloc
    return {"key": k, "name": cand["name"], "careers_url": careers, "hiring_system": checker, "checker": checker,
            "settings": s, "feed": feed_of(checker, s), "feed_total": jobs, "page_total": pt, "page_total_how": how,
            "intern_total": students, "status": "verified", "blocked_reason": "", "fallback": "",
            "robots": f"{host}/robots.txt checked before every request (discovery/robots/{host}.txt)" if host else "",
            "notes": " ".join(notes), "checked_at": "2026-11-09", "source": "added", "round": "added"}


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
    adds = [e for e in entries if e.get("aliases") and f'"{e["key"]}": ' not in text.split("ALIASES = {", 1)[1].split("\n}", 1)[0]]
    if adds:
        block = "".join(f'    "{e["key"]}": {json.dumps(e["aliases"])},\n' for e in adds)
        text = text.replace('    "ibm": ["International Business Machines"],\n}',
                            '    "ibm": ["International Business Machines"],\n    # added in November 2026 (round: added)\n'
                            + block + "}", 1)
        path.write_text(text)


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
    reads = yaml.safe_load((C / "reads.yaml").read_text())["reads"]
    for k, p in plan.items():
        for s in p["side"]:
            if s["checker"] == "ripplematch" and k in rm:
                cid = rm[k]["company_id"]
                watch.append(f"    - {{company: {k}, name: RippleMatch, checker: ripplematch, settings: {{company_id: {cid}}}}}")
                main = p["sources"][0]
                st = reads[main["entry"]].get("settings") or {}
                target = f"{main['checker']}:board={(st.get('board') or st.get('boards', [''])[0]).lower()}"
                al.append(f"    ripplematch:company={rm[k]['slug']}: '{target}'   # {k}: its RippleMatch page, watched")
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


if __name__ == "__main__":
    cmd, n = sys.argv[1], int(sys.argv[2])
    {"render": render, "apply": apply}[cmd](n)
