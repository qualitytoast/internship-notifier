"""Open each careers page in headless Chromium and record how it really loads jobs.

For every company in companies_seed.yaml this saves, under discovery/captures/<key>/:
  summary.json   final URL, title, hiring-system fingerprints, job-like JSON feeds, visible counts
  requests.jsonl every request the page made (method, URL, status, type, size, post data)
  page.html      rendered DOM (for embedded JSON such as __NEXT_DATA__)
  feed_*.json    response bodies that look like job lists

Usage: python discovery/capture.py [key ...] [--concurrency 6]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "captures"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

_U = r"[^\s\"'<>\\)]*"
SIGNATURES = {
    "greenhouse": [rf"boards(?:-api)?\.greenhouse\.io/{_U}", rf"job-boards\.greenhouse\.io/{_U}",
                   rf"api\.greenhouse\.io/{_U}"],
    "lever": [rf"jobs\.(?:eu\.)?lever\.co/{_U}", rf"api\.(?:eu\.)?lever\.co/{_U}"],
    "ashby": [rf"jobs\.ashbyhq\.com/{_U}", rf"api\.ashbyhq\.com/{_U}"],
    "workday": [rf"[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com/{_U}", rf"[a-z0-9-]+\.myworkdaysite\.com/{_U}"],
    "eightfold": [rf"[a-z0-9.-]*eightfold\.ai{_U}", rf"/api/pcsx/{_U}", rf"/api/apply/v2/jobs{_U}"],
    "oracle": [rf"[a-z0-9.-]+\.oraclecloud\.com/hcmRestApi{_U}", rf"hcmRestApi/resources/{_U}",
               rf"hcmUI/CandidateExperience{_U}"],
    "smartrecruiters": [rf"[a-z0-9.-]*smartrecruiters\.com/{_U}"],
    "workable": [rf"apply\.workable\.com/{_U}"],
    "icims": [rf"[a-z0-9.-]+\.icims\.com{_U}"],
    "phenom": [rf"cdn\.phenompeople\.com{_U}", rf"phenompeople{_U}", r"phApp\.ddo"],
    "avature": [rf"[a-z0-9.-]+\.avature\.net{_U}"],
    "gem": [rf"jobs\.gem\.com/{_U}", rf"api\.gem\.com{_U}"],
    "radancy": [rf"tbcdn\.talentbrew\.com{_U}", rf"talentbrew{_U}", rf"radancy{_U}"],
    "jibe": [rf"jibecdn\.com{_U}", rf"jibeapply\.com{_U}"],
    "successfactors": [rf"[a-z0-9.-]*successfactors\.[a-z]+{_U}"],
    "taleo": [rf"[a-z0-9.-]*taleo\.net{_U}"],
    "jobvite": [rf"[a-z0-9.-]*jobvite\.com{_U}"],
    "bamboohr": [rf"[a-z0-9.-]*bamboohr\.com{_U}"],
    "recruitee": [rf"[a-z0-9.-]*recruitee\.com{_U}"],
    "rippling": [rf"ats\.rippling\.com{_U}"],
    "pinpoint": [rf"[a-z0-9.-]*pinpointhq\.com{_U}"],
    "ukg-ultipro": [rf"recruiting\d*\.ultipro\.com{_U}", rf"rec\.pro\.ukg\.net{_U}"],
    "paylocity": [rf"recruiting\.paylocity\.com{_U}"],
    "adp": [rf"workforcenow\.adp\.com{_U}", rf"myjobs\.adp\.com{_U}"],
    "teamtailor": [rf"[a-z0-9.-]*teamtailor\.com{_U}"],
    "dover": [rf"app\.dover\.(?:com|io){_U}"],
    "comeet": [rf"comeet\.(?:co|com){_U}"],
    "clinch": [rf"clinchtalent{_U}"],
    "cornerstone": [rf"[a-z0-9.-]*csod\.com{_U}"],
    "breezy": [rf"[a-z0-9.-]*breezy\.hr{_U}"],
    "personio": [rf"jobs\.personio\.[a-z]+{_U}"],
    "beamery": [rf"[a-z0-9.-]*beamery\.com{_U}"],
}
SIG_RES = {k: [re.compile(p, re.I) for p in v] for k, v in SIGNATURES.items()}
COUNT_RES = [
    re.compile(r"(\d[\d,]*)\s+(?:open\s+|current\s+|available\s+)?(?:jobs?|positions?|roles?|results?|openings?|opportunities)\b", re.I),
    re.compile(r"\bof\s+(\d[\d,]*)\s+(?:jobs?|results?|positions?)?", re.I),
]
TITLE_KEYS = {"title", "jobtitle", "job_title", "name", "text", "postingtitle", "positiontitle", "requisitiontitle", "externaltitle", "position", "role", "jobname", "job_name", "postingname", "display_name", "posting_name"}
JOBISH_KEYS = {"location", "locations", "locationname", "absolute_url", "hostedurl", "jobid", "job_id",
               "requisitionid", "externalpath", "applyurl", "postedon", "posteddate", "department",
               "departments", "jobpostingurl", "joburl", "req_id", "reqid", "primarylocation", "city"}


def jobness(data, depth=0):
    """Return (score, list_len, path) for the most job-like list inside a JSON document."""
    best = (0, 0, "")
    if depth > 6:
        return best
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data[:5]):
        keys = {k.lower() for x in data[:5] for k in x.keys()}
        score = (2 if keys & TITLE_KEYS else 0) + len(keys & JOBISH_KEYS)
        if keys & TITLE_KEYS and score >= 3:
            best = (score, len(data), "")
    if isinstance(data, dict):
        items = data.items()
    elif isinstance(data, list):
        items = list(enumerate(data[:3]))
    else:
        items = []
    for k, v in items:
        s = jobness(v, depth + 1)
        if (s[0], s[1]) > (best[0], best[1]):
            best = (s[0], s[1], f"{k}/{s[2]}".rstrip("/"))
    return best


def totals_in(data, depth=0, found=None):
    """Collect numeric fields that look like result totals (total, totalCount, hits, count …)."""
    found = found if found is not None else {}
    if depth > 5:
        return found
    if isinstance(data, dict):
        for k, v in data.items():
            kl = k.lower()
            if isinstance(v, int) and not isinstance(v, bool) and any(t in kl for t in ("total", "count", "hits", "numfound", "found")):
                found.setdefault(k, v)
            elif isinstance(v, (dict, list)):
                totals_in(v, depth + 1, found)
    elif isinstance(data, list):
        for v in data[:2]:
            totals_in(v, depth + 1, found)
    return found


async def capture(browser, company, sem):
    key = company["key"]
    outdir = OUT / key
    outdir.mkdir(parents=True, exist_ok=True)
    summary = {"key": key, "name": company["name"], "pages": []}
    async with sem:
        for idx, url in enumerate(company["urls"]):
            ctx = await browser.new_context(user_agent=UA, viewport={"width": 1366, "height": 900}, locale="en-US")
            page = await ctx.new_page()

            async def block(route):
                if route.request.resource_type in ("image", "media", "font"):
                    await route.abort()
                else:
                    await route.continue_()
            await page.route("**/*", block)
            reqs, feeds, pending = [], [], []
            sigs: dict[str, set] = {}

            def note_sigs(text):
                for name, res in SIG_RES.items():
                    for r in res:
                        for m in r.findall(text or "")[:5]:
                            sigs.setdefault(name, set()).add(m[:160] if isinstance(m, str) else str(m)[:160])

            async def on_response(resp):
                req = resp.request
                rec = {"method": req.method, "url": req.url, "status": resp.status, "type": req.resource_type,
                       "ctype": resp.headers.get("content-type", "")}
                if req.post_data:
                    rec["post"] = req.post_data[:2000]
                note_sigs(req.url)
                if req.resource_type in ("xhr", "fetch", "document") or "json" in rec["ctype"]:
                    try:
                        body = await asyncio.wait_for(resp.body(), 15)
                        rec["size"] = len(body)
                        if ("json" in rec["ctype"] or body[:1] in (b"{", b"[")) and len(body) < 8_000_000:
                            data = json.loads(body)
                            score, n, path = jobness(data)
                            if score:
                                fn = f"feed_{idx}_{len(feeds)}.json"
                                (outdir / fn).write_bytes(body)
                                feeds.append({**rec, "file": fn, "score": score, "items": n, "path": path,
                                              "totals": totals_in(data)})
                        elif req.resource_type in ("xhr", "fetch", "document"):
                            note_sigs(body[:400_000].decode("utf-8", "ignore"))
                    except Exception as e:  # body unavailable for redirects etc.
                        rec["err"] = type(e).__name__
                reqs.append(rec)

            page.on("response", lambda r: pending.append(asyncio.ensure_future(on_response(r))))
            info = {"url": url}
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                info["status"] = resp.status if resp else None
                try:
                    await page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:
                    pass
                for _ in range(4):
                    await page.mouse.wheel(0, 4000)
                    await page.wait_for_timeout(1200)
                try:
                    await page.wait_for_load_state("networkidle", timeout=8_000)
                except Exception:
                    pass
                info["final_url"] = page.url
                info["title"] = await page.title()
                html = await page.content()
                (outdir / f"page_{idx}.html").write_text(html)
                note_sigs(html)
                for fr in page.frames:
                    note_sigs(fr.url)
                text = await page.inner_text("body", timeout=10_000)
                counts = []
                for r in COUNT_RES:
                    counts += [m.group(0) for m in r.finditer(text)][:6]
                info["count_texts"] = counts[:10]
                info["text_head"] = re.sub(r"\s+", " ", text)[:600]
            except Exception as e:
                info["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            if pending:
                done, still = await asyncio.wait(pending, timeout=20)
                for t in still:
                    t.cancel()
            info["signatures"] = {k: sorted(v)[:8] for k, v in sigs.items()}
            info["feeds"] = sorted(feeds, key=lambda f: (-f["score"], -f["items"]))[:12]
            info["n_requests"] = len(reqs)
            info["xhr"] = [f'{r["method"]} {r["status"]} {r["url"][:220]}' for r in reqs
                           if r["type"] in ("xhr", "fetch") and not re.search(
                               r"google-analytics|googletagmanager|doubleclick|segment|hotjar|onetrust|cookielaw|"
                               r"facebook|linkedin\.com/px|bing\.com|clarity|sentry|datadoghq-browser|newrelic|"
                               r"optimizely|fullstory|amplitude|mixpanel|heap|intercom|drift|hubspot|recaptcha|"
                               r"cloudflareinsights|adsrvr|demdex|omtrdc|everesttech|qualtrics|ketch", r["url"], re.I)][:80]
            with open(outdir / f"requests_{idx}.jsonl", "w") as fh:
                for r in reqs:
                    fh.write(json.dumps(r) + "\n")
            summary["pages"].append(info)
            await ctx.close()
    (outdir / "summary.json").write_text(json.dumps(summary, indent=1))
    pg = summary["pages"][0]
    print(f"{key:24s} {pg.get('status')} sigs={','.join(pg.get('signatures', {}).keys())[:60]:60s} "
          f"feeds={len(pg.get('feeds', []))} {pg.get('error', '')[:80]}", flush=True)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()
    seed = yaml.safe_load((ROOT / "companies_seed.yaml").read_text())["companies"]
    if args.keys:
        seed = [c for c in seed if c["key"] in args.keys]
    else:
        seed = [c for c in seed if not (OUT / c["key"] / "summary.json").exists()]
    print(f"capturing {len(seed)} companies", flush=True)
    sem = asyncio.Semaphore(args.concurrency)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        await asyncio.gather(*(capture(browser, c, sem) for c in seed))
        await browser.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
