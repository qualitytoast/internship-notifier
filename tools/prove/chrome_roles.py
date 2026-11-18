"""Role-by-role checks of a morning recorded through Chrome (tools/prove/morning.py record), against the database as it
was before that morning.

    python -I tools/prove/chrome_roles.py <chrome recording dir> <earlier recording dir> [--no-pages]

(--no-pages: no job page is asked, each counts as not asked: to try the checks on a recording without any request.)

<chrome recording dir> holds base.db (the database before the morning), home/data/internwatch.db (after it) and
morning.json.gz. <earlier recording dir> is the last morning recorded before the refusals (Nov 15), whose list answers
tell an unlisted role from a missed one.

Scope: the roles of stored Workday checks that ran in the morning (a company's configured Workday sites). Left out,
with their counts: watched and dismissed boards (never stored), and roles of companies or sites no longer checked.

1. Every previously seen role: each Workday role open in the database must appear in the morning (its id or one of
   its alt_ids seen by the morning's read). For one that doesn't, its job page (the reader's own detail request,
   through Chrome) must confirm it closed: 404 or 410, or a page that no longer accepts applications (canApply or
   posted false). A role whose page answers open but that the list doesn't show is explained if the earlier
   recording's list didn't show it either (an unlisted role). Any other missing role fails.
2. Every new role: each Workday role the morning found that isn't in the database (by id or alt_ids) must have been
   posted after its site's last complete read before the morning (its company's last check with status ok). Its date
   comes from postedOn; where that is vague ("30+ Days Ago"), from its page's startDate. A role posted on the same day
   as that read is accepted: the database records everything a complete read listed. Anything else fails.
3. Reopened roles: a role closed in the database that the morning found open is explained only if its page confirms
   it is open.
4. Same filter results: the filters over the morning's postings must give the database's matched Workday roles, plus
   or minus only the roles opened or closed above. A posting is judged as the runner judges it: the morning's title,
   and where the role's stored decision used its job page (a stored description), that page's location and job type
   and the description (a list says "2 Locations" where the page names them); otherwise the morning's list values.
   To explain a difference, the same filters also run over the database's own rows: a difference they share comes
   from a stored decision older than a filter change, not from the Chrome read. Any other difference fails.
   Shown too: the decisions the runner itself stored that morning against the database's.

Pages are asked through Chrome with the config's own settings (robots.txt, the Workday group's pace), several at a
time; Chrome is closed and its profile deleted at the end. Lists go to <chrome recording dir>/roles/.
"""
from __future__ import annotations

import gzip
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from internwatch import config as configmod  # noqa: E402
from internwatch import http as httpmod  # noqa: E402
from internwatch.filters import evaluate  # noqa: E402
from internwatch.models import Job  # noqa: E402
from internwatch.runner import http_settings  # noqa: E402

TZ = ZoneInfo("America/Chicago")
WD_HOSTS = ("myworkdayjobs.com", "myworkdaysite.com")
WD_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
PUBLIC = re.compile(r"^https://(?P<host>[^/]+)/en-US/(?:recruiting/(?P<tenant>[^/]+)/)?(?P<site>[^/]+)(?P<path>/.+)$")
CXS = re.compile(r"^https://(?P<host>[^/]+)/wday/cxs/(?P<tenant>[^/]+)/(?P<site>[^/]+)/jobs$")
POSTED = re.compile(r"Posted (Today|Yesterday|(\d+)\+? Days? Ago)", re.I)


def is_wd(url: str) -> bool:
    host = urlsplit(url or "").netloc
    return any(host == h or host.endswith("." + h) for h in WD_HOSTS)


def place(url: str):
    """(host, site, path) of a stored Workday role's public link."""
    m = PUBLIC.match(url or "")
    return (m["host"], m["site"].lower(), m["path"]) if m else None


def local_day(iso: str) -> date:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ).date()


def rows(db: Path, sql: str, *args):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


def ids_of(r) -> set[str]:
    return {r["job_id"], *json.loads(r.get("alt_ids") or "[]")}


def main(chrome_dir: Path, earlier_dir: Path, ask: bool = True) -> int:
    before_db, after_db = chrome_dir / "base.db", chrome_dir / "home" / "data" / "internwatch.db"
    out = chrome_dir / "roles"
    out.mkdir(exist_ok=True)
    cfg = configmod.load(REPO)
    comps = {c.key: c for c in cfg.companies}

    # the companies' Workday sites (not the watched boards), and each site's tenant
    sites: dict[str, set] = {}
    tenant_of: dict[tuple, str] = {}
    for c in cfg.companies:
        s = c.settings or {}
        srcs = [x.get("settings") or {} for x in s.get("sources") or [] if x.get("checker") == "workday"] \
            if c.checker == "multi" else ([s] if c.checker == "workday" else [])
        for st in srcs:
            for site in st.get("sites") or [st.get("site")]:
                sites.setdefault(c.key, set()).add((st["host"], site.lower()))
                tenant_of[(st["host"], site.lower())] = st["tenant"]

    run = rows(after_db, "SELECT * FROM runs ORDER BY id DESC LIMIT 1")[0]
    start = run["started_at"]
    morning_day = local_day(start)
    last_check = {}
    for r in rows(after_db, "SELECT company, status, error_kind, error FROM checks WHERE run_id=? ORDER BY id",
                  run["id"]):
        last_check[r["company"]] = r
    complete = {r["company"]: r["day"] for r in rows(
        before_db, "SELECT company, MAX(started_at) day FROM checks WHERE status='ok' GROUP BY company")}

    # the morning's and the earlier morning's list answers: (host, site, path) -> postedOn
    def listed(rec: Path) -> dict:
        with gzip.open(rec / "morning.json.gz", "rt") as f:
            ex = json.load(f)["exchanges"]
        found = {}
        for e in ex:
            m = CXS.match(e["url"]) if e["method"] == "POST" else None
            if not m or str(e.get("status")) != "200":
                continue
            try:
                d = json.loads(e.get("text") or "")
            except ValueError:
                continue
            for p in d.get("jobPostings") or []:
                if p.get("externalPath"):
                    found[(m["host"], m["site"].lower(), p["externalPath"])] = p.get("postedOn") or ""
        return found
    now_listed, earlier_listed = listed(chrome_dir), listed(earlier_dir)

    def scoped(r):
        if r.get("source", "checker") != "checker" or not is_wd(r["url"]):
            return None
        p = place(r["url"])
        if r["company"] not in comps or p is None or (p[0], p[1]) not in sites.get(r["company"], set()):
            return "no longer checked"
        if r["company"] not in last_check:
            return "check did not run"
        return "in scope"

    before = rows(before_db, "SELECT * FROM jobs")
    after = rows(after_db, "SELECT * FROM jobs")
    report: dict = {"out of scope": {}}
    for r in before:
        k = scoped(r)
        if k and k != "in scope" and r["removed_at"] is None:
            report["out of scope"][k] = report["out of scope"].get(k, 0) + 1
    b_scope = [r for r in before if scoped(r) == "in scope"]
    a_scope = [r for r in after if scoped(r) == "in scope"]
    seen_now = [r for r in a_scope if r["last_seen"] >= start and r["removed_at"] is None]
    seen_ids: dict[str, set] = {}
    for r in seen_now:
        seen_ids.setdefault(r["company"], set()).update(ids_of(r))
    before_ids: dict[str, set] = {}
    for r in b_scope:
        before_ids.setdefault(r["company"], set()).update(ids_of(r))
    watched = [b for b in cfg.settings.get("liveness", "watch_boards", default=[]) or []
               if b.get("checker") == "workday"]
    watched_sites = {(b["settings"]["host"], b["settings"]["site"].lower()) for b in watched}
    company_sites = set().union(*sites.values()) if sites else set()
    report["out of scope"]["watched Workday boards (never stored)"] = len(watched)
    report["out of scope"]["postings listed only on watched or dismissed boards"] = sum(
        1 for (h, s, _) in now_listed if (h, s) not in company_sites)

    # 1. every previously seen role
    open_before = [r for r in b_scope if r["removed_at"] is None]
    missing = [r for r in open_before if not (ids_of(r) & seen_ids.get(r["company"], set()))]
    # 2. new roles, 3. reopened roles
    new = [r for r in seen_now if not (ids_of(r) & before_ids.get(r["company"], set()))]
    closed_before = {(r["company"], r["job_id"]): r for r in b_scope if r["removed_at"] is not None}
    reopened = [r for r in seen_now if (r["company"], r["job_id"]) in closed_before]

    # pages through Chrome
    robots_copy = Path(tempfile.mkdtemp(prefix="chrome-roles-robots-"))
    if (REPO / "data" / "robots").exists():
        shutil.copytree(REPO / "data" / "robots", robots_copy, dirs_exist_ok=True)
    gate = httpmod.HostGate(robots_copy)
    http = httpmod.Http(http_settings(cfg), gate=gate)

    def page(r) -> dict:
        if not ask:
            return {"page": "not asked"}
        p = place(r["url"])
        tenant = tenant_of.get((p[0], p[1]))
        site = next(s for (h, s) in sites[r["company"]] if (h, s) == (p[0], p[1]))
        real_site = PUBLIC.match(r["url"])["site"]  # the site's own spelling
        url = f"https://{p[0]}/wday/cxs/{tenant}/{real_site}{p[2]}"
        try:
            resp = http.get(url, headers=WD_HEADERS, ok_statuses=(404, 410))
        except Exception as e:  # noqa: BLE001 - an unconfirmed page
            return {"page": "error", "error": f"{type(e).__name__}: {str(e)[:200]}", "detail_url": url}
        if resp.status in (404, 410):
            return {"page": "closed", "status": resp.status, "detail_url": url}
        try:
            info = (resp.json() or {}).get("jobPostingInfo") or {}
        except Exception:  # noqa: BLE001
            return {"page": "unreadable", "status": resp.status, "body": resp.text[:200], "detail_url": url}
        state = "closed" if info.get("canApply") is False or info.get("posted") is False else "open"
        if not info:
            state = "unreadable"
        return {"page": state, "status": resp.status, "canApply": info.get("canApply"), "posted": info.get("posted"),
                "startDate": info.get("startDate"), "endDate": info.get("endDate"), "detail_url": url, "site": site}

    def posted_day(r):
        p = place(r["url"])
        text = now_listed.get(p) or ""
        m = POSTED.search(text)
        if not m:
            return None, text
        word = m.group(1).lower()
        if word == "today":
            return morning_day, text
        if word == "yesterday":
            return morning_day - timedelta(days=1), text
        if "+" in text:
            return None, text  # "30+ Days Ago": vague
        return morning_day - timedelta(days=int(m.group(2))), text

    vague = [r for r in new if posted_day(r)[0] is None]
    to_ask = {(r["company"], r["job_id"]): r for r in missing + reopened + vague}
    print(f"asking {len(to_ask)} job pages through Chrome ({len(missing)} missing, {len(reopened)} reopened, "
          f"{len(vague)} new with a vague date)", flush=True)
    t0 = datetime.now()
    try:
        with ThreadPoolExecutor(12) as pool:
            pages = dict(zip(to_ask, pool.map(page, to_ask.values())))
    finally:
        gate.close()
        shutil.rmtree(robots_copy, ignore_errors=True)
    ask_minutes = (datetime.now() - t0).total_seconds() / 60

    fails = {}
    # 1.
    rows1 = []
    for r in missing:
        pg = pages[(r["company"], r["job_id"])]
        p = place(r["url"])
        if pg["page"] == "closed":
            verdict = "closed (page)"
        elif pg["page"] == "open" and p not in earlier_listed:
            verdict = "unlisted (open, not listed on Nov 15 either)"
        else:
            verdict = "FAIL: " + ("open and listed on Nov 15" if pg["page"] == "open" else f"page {pg['page']}")
        rows1.append({"company": r["company"], "job_id": r["job_id"], "title": r["title"], "url": r["url"],
                      "verdict": verdict, **pg, "morning_check": (last_check.get(r["company"]) or {}).get("status")})
    fails["previously seen"] = [x for x in rows1 if x["verdict"].startswith("FAIL")]
    # 2.
    rows2 = []
    for r in new:
        day, text = posted_day(r)
        source = "postedOn"
        if day is None:
            pg = pages.get((r["company"], r["job_id"])) or {}
            day = date.fromisoformat(pg["startDate"][:10]) if pg.get("startDate") else None
            source = "startDate"
        last = local_day(complete[r["company"]]) if complete.get(r["company"]) else None
        if day is None:
            verdict = "FAIL: no date"
        elif last is None or day > last:
            verdict = "after the last complete read"
        elif day == last:
            verdict = "same day as the last complete read"
        else:
            verdict = "FAIL: posted before the last complete read"
        rows2.append({"company": r["company"], "job_id": r["job_id"], "title": r["title"], "url": r["url"],
                      "postedOn": text, "posted_day": str(day), "from": source, "last_complete_read": str(last),
                      "verdict": verdict})
    fails["new"] = [x for x in rows2 if x["verdict"].startswith("FAIL")]
    # 3.
    rows3 = []
    for r in reopened:
        pg = pages[(r["company"], r["job_id"])]
        rows3.append({"company": r["company"], "job_id": r["job_id"], "title": r["title"], "url": r["url"],
                      "verdict": "reopened (page open)" if pg["page"] == "open" else f"FAIL: page {pg['page']}",
                      **pg})
    fails["reopened"] = [x for x in rows3 if x["verdict"].startswith("FAIL")]

    # 4. the filters
    b_by = {(r["company"], r["job_id"]): r for r in b_scope}
    a_by = {(r["company"], r["job_id"]): r for r in seen_now}

    def verdict(r) -> bool:
        c = comps[r["company"]]
        j = Job(id=r["job_id"], title=r["title"], location=r["location"], url=r["url"], posted=r["posted"],
                snippet=r["snippet"], department=r["department"], employment_type=r["employment_type"])
        return evaluate(j, cfg.rules, category=c.category, locations=c.locations,
                        extra_role_keywords=c.extra_role_re).matched

    def as_judged(a) -> dict:
        """The morning's posting with the best details known (the runner's rule, db.upsert_jobs' recheck)."""
        b = b_by.get((a["company"], a["job_id"]))
        if b is None or not (b["snippet"] or "").strip():
            return a
        return {**a, "location": b["location"] or a["location"], "employment_type": b["employment_type"]
                or a["employment_type"], "snippet": b["snippet"]}
    chrome_match = {(r["company"], r["job_id"]) for r in seen_now if verdict(as_judged(r))}
    db_match = {(r["company"], r["job_id"]) for r in open_before if r["matched"]}
    runner_match = {(r["company"], r["job_id"]) for r in seen_now if r["matched"]}
    opened = {(r["company"], r["job_id"]) for r in new} | {(r["company"], r["job_id"]) for r in reopened}
    closed = {(x["company"], x["job_id"]) for x in rows1 if not x["verdict"].startswith("FAIL")}
    rows4 = []
    for key in sorted((chrome_match ^ db_match) - opened - closed):
        side = "matched now, not in the database's matches" if key in chrome_match else \
            "in the database's matches, not matched now"
        b, a = b_by.get(key), a_by.get(key)
        a = as_judged(a) if a else None
        db_now = verdict(b) if b else None
        changed = b and a and any((a[f] or "") != (b[f] or "") for f in ("title", "location", "employment_type"))
        if b and db_now == (key in chrome_match):
            cause = "stored decision older than a filter change (the filters give the same on the database's row)"
        elif changed:
            cause = "the posting itself changed: " + ", ".join(
                f"{f} {b[f]!r} -> {a[f]!r}" for f in ("title", "location", "employment_type")
                if (a[f] or "") != (b[f] or ""))
        else:
            cause = "unexplained"
        rows4.append({"company": key[0], "job_id": key[1], "title": (a or b or {}).get("title"), "side": side,
                      "cause": cause})
    fails["filters"] = [x for x in rows4 if not x["cause"].startswith("stored decision")]

    for name, data in (("previously_seen", rows1), ("new", rows2), ("reopened", rows3), ("filters", rows4)):
        (out / f"{name}.json").write_text(json.dumps(data, indent=1, default=str))
    from collections import Counter
    print(f"morning: run {run['id']} from {start}; {len(last_check)} checks ran")
    print(f"scope: {len(open_before)} Workday roles open in the database at {len({r['company'] for r in b_scope})} "
          f"companies; left out (open roles or counts): {report['out of scope']}")
    print(f"1. previously seen: {len(open_before) - len(missing)} appeared, {len(missing)} missing: "
          f"{dict(Counter(x['verdict'] for x in rows1))}")
    print(f"2. new: {len(new)}: {dict(Counter(x['verdict'] for x in rows2))}")
    print(f"3. reopened: {len(reopened)}: {dict(Counter(x['verdict'] for x in rows3))}")
    print(f"4. filters: {len(chrome_match)} matched in the morning, {len(db_match)} in the database; "
          f"{len(chrome_match - db_match)} more and {len(db_match - chrome_match)} fewer, of which "
          f"{len((chrome_match ^ db_match) & (opened | closed))} opened or closed; others: "
          f"{dict(Counter(x['cause'].split(':')[0] for x in rows4))}")
    unexplained_runner = sorted((runner_match ^ db_match) - opened - closed)
    print(f"   the runner's own stored decisions that morning: {len(runner_match)} matched against "
          f"{len(db_match)}; differences beyond the roles opened or closed: {len(unexplained_runner)}"
          + (f" {unexplained_runner[:10]}" if unexplained_runner else ""))
    print(f"pages asked: {len(to_ask)} in {ask_minutes:.1f} min; Chrome closed")
    bad = {k: v for k, v in fails.items() if v}
    for k, v in bad.items():
        print(f"FAIL {k}: {len(v)}")
        for x in v[:15]:
            print("   ", json.dumps(x, default=str)[:300])
    print("PASS" if not bad else "FAIL")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), ask="--no-pages" not in sys.argv))
