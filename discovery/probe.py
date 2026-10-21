"""Probe public hiring-system feeds with candidate board tokens.

Candidates come from the company name, a hand-written hint list, and tokens found in the
Playwright captures (discovery/captures/<key>/summary.json). Results → discovery/probe_results.json.

Usage: python discovery/probe.py [key ...]
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
INTERN_RE = re.compile(r"\b(intern(ship)?s?|co-?op|apprentice(ship)?|student|campus|off-cycle|summer analyst)\b", re.I)

# Extra token guesses (verified or rejected by the probe itself).
HINTS = {
    "databricks": ["databricks"], "scale-ai": ["scaleai"], "pinecone": ["pinecone"], "temporal": ["temporal", "temporaltechnologies"],
    "pinterest": ["pinterest"], "duolingo": ["duolingo"], "stripe": ["stripe"], "roblox": ["roblox"], "dropbox": ["dropbox"],
    "toast": ["toast"], "procore": ["procoretechnologies", "procore"], "applied-intuition": ["appliedintuition"],
    "twitch": ["twitch"], "figma": ["figma"], "chan-zuckerberg": ["chanzuckerberginitiative", "czi", "chanzuckerberg"],
    "coinbase": ["coinbase"], "rippling": ["rippling"], "ramp": ["ramp"], "squarespace": ["squarespace"],
    "wayfair": ["wayfair"], "c3-ai": ["c3iot", "c3ai"], "notion": ["notion"], "waymo": ["waymo"], "spotify": ["spotify"],
    "cloudflare": ["cloudflare"], "block": ["block", "squareup", "square"], "plaid": ["plaid"], "nuro": ["nuro"],
    "verkada": ["verkada"], "hubspot": ["hubspot", "hubspotjobs"], "klaviyo": ["klaviyo"], "smartsheet": ["smartsheet"],
    "pitchbook": ["pitchbookdata"], "nutanix": ["nutanix"], "veeva": ["veeva"], "remitly": ["remitly"],
    "doordash": ["doordashusa", "doordash"], "benchling": ["benchling"], "lyft": ["lyft"], "unity": ["unity3d", "unity"],
    "zoox": ["zoox"], "qualtrics": ["qualtrics"], "samsara": ["samsara"], "aurora": ["aurorainnovation", "aurora"],
    "datadog": ["datadog"], "airbnb": ["airbnb"], "atlassian": ["atlassian"], "mongodb": ["mongodb"], "okta": ["okta"],
    "affirm": ["affirm"], "robinhood": ["robinhood"], "snowflake": ["snowflake", "snowflakecomputing"],
    "squarepoint": ["squarepointcapital", "squarepoint"], "wolverine": ["wolverinetrading", "wolverine"],
    "radix": ["radixuniversity", "radix", "radixtrading"], "xtx-markets": ["xtxmarketstechnologies", "xtxmarkets", "xtx"],
    "instabase": ["instabase"], "yext": ["yext"], "immuta": ["immuta"], "jane-street": ["janestreet"],
    "two-sigma": ["twosigma"], "imc": ["imc", "imctrading"], "hudson-river-trading": ["wehrtyou", "hudsonrivertrading", "hrt"],
    "five-rings": ["fiveringsllc", "fiverings"], "dv-trading": ["dvtrading", "dvtradingllc"], "point72": ["point72"],
    "voleon": ["thevoleongroup", "voleon"], "brevan-howard": ["brevanhoward"], "walleye": ["walleyecapital", "walleye"],
    "aqr": ["aqr", "aqrcapitalmanagement"], "graviton": ["gravitonresearchcapital", "graviton"],
    "geneva-trading": ["genevatrading", "genevatradingusa"], "jump-trading": ["jumptrading"], "seven-research": ["sevenresearch"],
    "voloridge": ["voloridge", "voloridgeinvestmentmanagement"], "transmarket-group": ["transmarketgroup", "tmg"],
    "gts": ["gts", "globaltradingsystems", "gtsllc"], "kirin": ["kirin"], "electronic-arts": ["electronicarts", "ea"],
    "epic-games": ["epicgames"], "riot-games": ["riotgames"], "shopify": ["shopify"], "red-hat": ["redhat"],
    "the-trade-desk": ["thetradedesk"], "xai": ["xai"], "together-ai": ["togetherai", "together"], "glean": ["gleanwork", "glean"],
    "decagon": ["decagon", "decagonai"], "sierra": ["sierra", "sierraai"], "abridge": ["abridge"], "harvey": ["harvey", "harveyai"],
    "waabi": ["waabi"], "mistral-ai": ["mistral", "mistralai"], "deepgram": ["deepgram"], "sigma-computing": ["sigmacomputing"],
    "semgrep": ["semgrep", "r2c"], "tanium": ["tanium"], "whatnot": ["whatnot"], "seatgeek": ["seatgeek"],
    "talos": ["talostrading", "talos"], "brex": ["brex"], "mercury": ["mercury"], "postman": ["postman"],
    "cockroach-labs": ["cockroachlabs"], "1password": ["1password", "onepassword"], "ccc": ["cccis", "cccintelligentsolutions"],
    "uber-freight": ["uberfreight"], "openai": ["openai"], "cohere": ["cohere"], "anyscale": ["anyscale"], "groq": ["groq"],
    "grafana-labs": ["grafanalabs"], "hugging-face": ["huggingface"], "coreweave": ["coreweave", "wandb", "weightsandbiases"],
    "citadel": ["citadel"], "citadel-securities": ["citadelsecurities"], "linkedin": ["linkedin"], "uber": ["uber"],
    "intuit": ["intuit"], "twilio": ["twilio"], "docusign": ["docusign"], "expedia": ["expedia", "expediagroup"],
    "booking": ["booking", "bookingcom"], "servicenow": ["servicenow"], "epic-systems": [],
}

TOKEN_RES = {
    "greenhouse": [r"boards\.greenhouse\.io/embed/job_board(?:/js)?\?for=([\w-]+)", r"job-boards\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)",
                   r"boards\.greenhouse\.io/([\w-]+)", r"boards-api\.greenhouse\.io/v1/boards/([\w-]+)"],
    "lever": [r"jobs\.(?:eu\.)?lever\.co/([\w-]+)", r"api\.(?:eu\.)?lever\.co/v0/postings/([\w-]+)"],
    "ashby": [r"jobs\.ashbyhq\.com/([\w.%-]+)", r"posting-api/job-board/([\w.%-]+)"],
    "workable": [r"apply\.workable\.com/(?!api\b|j\b)([\w-]+)"],
    "gem": [r"jobs\.gem\.com/([\w-]+)"],
}
BAD_TOKENS = {"embed", "api", "v1", "js", "static", "assets", "images", "favicon.ico", "j", "jobs", "careers", "posting-api"}


def tokens_from_capture(key):
    found = {k: [] for k in TOKEN_RES}
    p = ROOT / "captures" / key / "summary.json"
    if not p.exists():
        return found
    s = json.loads(p.read_text())
    blob = json.dumps(s)
    for ats, res in TOKEN_RES.items():
        for r in res:
            for m in re.findall(r, blob, re.I):
                t = m.strip().lower()
                if t and t not in BAD_TOKENS and t not in found[ats]:
                    found[ats].append(t)
    return found


def name_tokens(name):
    base = re.sub(r"\(.*?\)", "", name).strip().lower()
    words = re.findall(r"[a-z0-9]+", base)
    out = ["".join(words)]
    if len(words) > 1:
        out += ["-".join(words), words[0]]
    return out


async def get_json(client, method, url, **kw):
    try:
        r = await client.request(method, url, **kw)
        if r.status_code != 200:
            return None, r.status_code
        return r.json(), 200
    except Exception as e:  # noqa: BLE001
        return None, type(e).__name__


async def probe_one(client, sem, ats, token):
    async with sem:
        if ats == "greenhouse":
            data, st = await get_json(client, "GET", f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
            jobs = (data or {}).get("jobs") if isinstance(data, dict) else None
            titles = [j.get("title", "") for j in jobs or []]
            url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        elif ats == "lever":
            url = f"https://api.lever.co/v0/postings/{token}?mode=json"
            data, st = await get_json(client, "GET", url)
            if data is None:
                url = f"https://api.eu.lever.co/v0/postings/{token}?mode=json"
                data, st = await get_json(client, "GET", url)
            titles = [j.get("text", "") for j in data] if isinstance(data, list) else None
        elif ats == "ashby":
            url = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
            data, st = await get_json(client, "GET", url)
            titles = [j.get("title", "") for j in (data or {}).get("jobs", [])] if isinstance(data, dict) and "jobs" in data else None
        elif ats == "workable":
            url = f"https://apply.workable.com/api/v1/widget/accounts/{token}"
            data, st = await get_json(client, "GET", url)
            titles = [j.get("title", "") for j in (data or {}).get("jobs", [])] if isinstance(data, dict) and "jobs" in data else None
        elif ats == "gem":
            url = f"https://api.gem.com/job_board/v0/{token}/job_posts/"
            data, st = await get_json(client, "GET", url)
            titles = [j.get("title", "") for j in data] if isinstance(data, list) else None
        elif ats == "recruitee":
            url = f"https://{token}.recruitee.com/api/offers/"
            data, st = await get_json(client, "GET", url)
            titles = [j.get("title", "") for j in (data or {}).get("offers", [])] if isinstance(data, dict) else None
        else:
            return None
        if titles is None:
            return None
        return {"ats": ats, "token": token, "url": url, "total": len(titles),
                "intern": sum(1 for t in titles if INTERN_RE.search(t or "")),
                "sample_interns": [t for t in titles if INTERN_RE.search(t or "")][:6]}


async def main(keys):
    seed = yaml.safe_load((ROOT / "companies_seed.yaml").read_text())["companies"]
    if keys:
        seed = [c for c in seed if c["key"] in keys]
    out_path = ROOT / "probe_results.json"
    results = json.loads(out_path.read_text()) if out_path.exists() else {}
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30, follow_redirects=True) as client:
        async def do_company(c):
            cap = tokens_from_capture(c["key"])
            cands = {ats: list(dict.fromkeys(cap.get(ats, []) + HINTS.get(c["key"], []) + name_tokens(c["name"])))
                     for ats in ("greenhouse", "lever", "ashby", "workable", "gem")}
            tasks = [probe_one(client, sem, ats, t) for ats, toks in cands.items() for t in toks[:6]]
            hits = [h for h in await asyncio.gather(*tasks) if h]
            results[c["key"]] = {"hits": hits, "capture_tokens": cap}
            line = "; ".join(f"{h['ats']}:{h['token']} total={h['total']} intern={h['intern']}" for h in hits) or "-"
            print(f"{c['key']:24s} {line}", flush=True)
        await asyncio.gather(*(do_company(c) for c in seed))
    out_path.write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
