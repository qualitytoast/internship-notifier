"""Role-by-role checks of a morning recorded through Chrome (tools/prove/morning.py record), against the database as it
was before that morning.

    python -I tools/prove/chrome_roles.py <chrome recording dir> <earlier recording dir> [--no-pages]
        [--reuse <earlier roles dir>]...

(--no-pages: no job page is asked, each counts as not asked: to try the checks on a recording without any request.
--reuse, once or more, oldest first: a page an earlier run of this check answered open or closed (its
roles/pages.json, or the page fields of its previously_seen.json and reopened.json) is taken from the latest of
them; every other page is asked again. Workday's own searches are always asked again.)

<chrome recording dir> holds base.db (the database before the morning), home/data/internwatch.db (after it) and
morning.json.gz. <earlier recording dir> is the last morning recorded before the refusals (Nov 15), whose list answers
tell an unlisted role from a missed one.

Scope: the roles of stored Workday checks that ran in the morning (a company's configured Workday sites). Left out,
with their counts: watched and dismissed boards (never stored), and roles of companies or sites no longer checked.

A role's requisition is the last part of its address after "_", without a "-1"-style repost suffix (R-584369-1:
R-584369). Workday's own search for it is a job-list request with that requisition as searchText, on the role's site.
A site's walk is short when one of its searches (under Workday's 2,000 cap) listed fewer distinct postings than the
total its first page reported; a site's read is complete when none of its searches is short.

1. Every previously seen role: each Workday role open in the database must appear in the morning (its id or one of
   its alt_ids seen by the morning's read). For one that doesn't, its job page (the reader's own detail request,
   through Chrome) must confirm it closed: 404 or 410, a 403 whose JSON errorCode is S22 ("permission denied":
   Workday's answer for a removed posting at most tenants, the same through httpx; approved 2026-11-18), or a page
   that no longer accepts applications (canApply or posted false). A role whose page answers open is explained by
   (in this order):
   - same requisition, new address: the morning lists its requisition on the company's Workday sites at another
     address (a moved location, or a requisition left on only one of the company's sites);
   - unlisted: the earlier recording's list didn't show it either;
   - relisted: Workday's own search now dates it on or after the morning's day, and either the morning's read of its
     site was complete without it, or an earlier run of this check (--reuse, asked after the morning) found its page
     removed (a 403 recorded before the error codes were kept counts: every 403 asked again since was S22);
   - slipped past a walk: Workday's own search finds it now, and the morning's walk of its site was short by at
     least as many postings as the roles explained this way there, each short search within the reader's tolerance
     (check_total: 1.5%, at least 2).
   Any other missing role fails.
2. Every new role: each Workday role the morning found that isn't in the database (by id or alt_ids) must have been
   posted after its site's last complete read before the morning (its company's last check with status ok). Its date
   comes from postedOn; where that is vague ("30+ Days Ago"), from its page's startDate. A role posted on the same day
   as that read is accepted: the database records everything a complete read listed. A role dated before that read is
   explained as listed late if the earlier recording's read of its site was complete without its requisition and the
   database never had that requisition. Anything else fails.
3. Reopened roles: a role closed in the database that the morning found open is explained if its page confirms it is
   open, or as closed since the morning if its page answers closed and Workday's own search no longer finds it.
4. Same filter results: the filters over the morning's postings must give the database's matched Workday roles, plus
   or minus only the roles opened or closed above. A posting is judged as the runner judges it: the morning's title,
   and where the role's stored decision used its job page (a stored description), that page's location and job type
   and the description (a list says "2 Locations" where the page names them); otherwise the morning's list values.
   A role the morning lists at a new address (same requisition, the old address no longer listed) is compared as one
   role, judged on its new listing. To explain a difference, the same filters also run over the database's own rows:
   a difference they share comes from a stored decision older than a filter change; one where they give the
   database's decision and the morning's row differs in title, place or job type comes from the posting itself
   changing. Neither comes from the Chrome read. Any other difference fails.
   Shown too: the decisions the runner itself stored that morning against the database's.

Pages and searches are asked through Chrome with the config's own settings (robots.txt, the Workday group's pace):
each thread asks one site's pages at a time, the sites with most pages first, so up to 12 sites are read at once and
their tabs stay open. Chrome is closed and its profile deleted at the end. Lists go to <chrome recording dir>/roles/,
every page answer to roles/pages.json.
"""
from __future__ import annotations

import gzip
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
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
PAGE_FIELDS = ("page", "status", "code", "canApply", "posted", "startDate", "endDate", "detail_url", "site", "error",
               "body")


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


def req_of(s: str | None) -> str | None:
    """A Workday address's requisition: the last part after "_", without a "-1"-style repost suffix. A bare id (an
    alt_id that is a requisition already) is its own requisition."""
    last = (s or "").rstrip("/").rsplit("/", 1)[-1]
    if "_" not in last:
        return None if "/" in (s or "") or not last else re.sub(r"-\d{1,2}$", "", last)
    return re.sub(r"-\d{1,2}$", "", last.rsplit("_", 1)[1]) or None


def reqs_of(r) -> set[str]:
    return {q for q in (req_of(x) for x in ids_of(r)) if q}


def walks(rec: Path) -> tuple[dict, dict]:
    """A recording's Workday list answers: (host, site) -> [(total, distinct postings)] for each search under the
    2,000 cap, and (host, site) -> the requisitions listed."""
    with gzip.open(rec / "morning.json.gz", "rt") as f:
        ex = json.load(f)["exchanges"]
    searches: dict[tuple, dict] = {}
    for e in ex:
        m = CXS.match(e["url"]) if e["method"] == "POST" else None
        if not m or str(e.get("status")) != "200":
            continue
        try:
            body, d = json.loads(e.get("body") or ""), json.loads(e.get("text") or "")
        except ValueError:
            continue
        key = (m["host"], m["site"].lower(), json.dumps(body.get("appliedFacets"), sort_keys=True),
               body.get("searchText") or "")
        s = searches.setdefault(key, {"total": None, "paths": set()})
        if body.get("offset") == 0 and s["total"] is None:
            s["total"] = d.get("total")
        s["paths"].update(p["externalPath"] for p in d.get("jobPostings") or [] if p.get("externalPath"))
    counts: dict[tuple, list] = {}
    reqs: dict[tuple, set] = {}
    for (host, site, _, _), s in searches.items():
        reqs.setdefault((host, site), set()).update(q for q in map(req_of, s["paths"]) if q)
        if isinstance(s["total"], int) and s["total"] < 2000:
            counts.setdefault((host, site), []).append((s["total"], len(s["paths"])))
    return counts, reqs


def kind(cause: str) -> str:
    """A filter difference's cause without its details."""
    return "same requisition, new address" if cause.startswith("same requisition") else cause.split(":")[0]


def tolerance(total: int) -> int:
    return max(2, int(total * 0.015))  # adapters.base.check_total's


def main(chrome_dir: Path, earlier_dir: Path, ask: bool = True, reuse: tuple[Path, ...] = ()) -> int:
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

    # the morning's and the earlier morning's walks: each site's searches and the requisitions they listed
    now_counts, now_reqs = walks(chrome_dir)
    earlier_counts, earlier_reqs = walks(earlier_dir)

    def short_by(counts: dict, hs: tuple) -> tuple[int, bool]:
        """By how many postings the site's searches came short, and whether each short one was within tolerance."""
        cs = counts.get(hs) or []
        return sum(max(0, t - n) for t, n in cs), all(t - n <= tolerance(t) for t, n in cs)

    def complete_read(counts: dict, hs: tuple) -> bool:
        cs = counts.get(hs)
        return bool(cs) and all(n >= t for t, n in cs)

    def listed_reqs(reqs: dict, company: str) -> set:
        return set().union(*(reqs.get(hs, set()) for hs in sites.get(company, set())))

    ever_reqs: dict[str, set] = {}
    for r in before:
        ever_reqs.setdefault(r["company"], set()).update(reqs_of(r))

    def day_of(text: str, ref: date) -> date | None:
        m = POSTED.search(text or "")
        if not m or "+" in text:
            return None  # none, or "30+ Days Ago": vague
        word = m.group(1).lower()
        return ref if word == "today" else ref - timedelta(days=1 if word == "yesterday" else int(m.group(2)))

    def posted_day(r):
        text = now_listed.get(place(r["url"])) or ""
        return day_of(text, morning_day), text

    # pages and searches through Chrome
    robots_copy = Path(tempfile.mkdtemp(prefix="chrome-roles-robots-"))
    if (REPO / "data" / "robots").exists():
        shutil.copytree(REPO / "data" / "robots", robots_copy, dirs_exist_ok=True)
    gate = httpmod.HostGate(robots_copy)
    http = httpmod.Http(http_settings(cfg), gate=gate)

    def parts(r):
        p = place(r["url"])
        return p[0], tenant_of.get((p[0], p[1])), PUBLIC.match(r["url"])["site"], p[2]  # the site's own spelling

    def page(r) -> dict:
        if not ask:
            return {"page": "not asked"}
        host, tenant, real_site, path = parts(r)
        url = f"https://{host}/wday/cxs/{tenant}/{real_site}{path}"
        try:
            resp = http.get(url, headers=WD_HEADERS, ok_statuses=(403, 404, 410))
        except Exception as e:  # noqa: BLE001 - an unconfirmed page
            return {"page": "error", "error": f"{type(e).__name__}: {str(e)[:200]}", "detail_url": url}
        if resp.status in (403, 404, 410):
            try:
                code = (resp.json() or {}).get("errorCode")
            except Exception:  # noqa: BLE001
                code = None
            if resp.status == 403 and code != "S22":
                return {"page": "error", "status": 403, "code": code, "body": resp.text[:200], "detail_url": url}
            return {"page": "closed", "status": resp.status, "code": code, "detail_url": url}
        try:
            info = (resp.json() or {}).get("jobPostingInfo") or {}
        except Exception:  # noqa: BLE001
            return {"page": "unreadable", "status": resp.status, "body": resp.text[:200], "detail_url": url}
        state = "closed" if info.get("canApply") is False or info.get("posted") is False else "open"
        if not info:
            state = "unreadable"
        return {"page": state, "status": resp.status, "canApply": info.get("canApply"), "posted": info.get("posted"),
                "startDate": info.get("startDate"), "endDate": info.get("endDate"), "detail_url": url,
                "site": place(r["url"])[1]}

    def search(r) -> dict:
        """Workday's own search on the role's site for its requisition, now."""
        q = req_of(r["job_id"])
        if not ask:
            return {"search": "not asked", "requisition": q}
        host, tenant, real_site, _ = parts(r)
        try:
            resp = http.post(f"https://{host}/wday/cxs/{tenant}/{real_site}/jobs", headers=WD_HEADERS,
                             json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q})
            found = [{"path": x["externalPath"], "postedOn": x.get("postedOn") or ""}
                     for x in (resp.json() or {}).get("jobPostings") or [] if req_of(x.get("externalPath")) == q]
        except Exception as e:  # noqa: BLE001 - an unanswered search
            return {"search": "error", "requisition": q, "search_error": f"{type(e).__name__}: {str(e)[:200]}"}
        today = datetime.now(TZ).date()
        days = [d for d in (day_of(x["postedOn"], today) for x in found) if d]
        return {"search": "found" if found else "not found", "requisition": q, "search_found": found,
                "search_posted": str(max(days)) if days else None}

    def ask_by_site(items: dict, fn) -> dict:
        """fn over items, each thread asking one site's items at a time (the sites with most items first): up to 12
        sites at once, each at its own pace, with their tabs kept open."""
        by_host: dict[str, list] = {}
        for k, r in items.items():
            by_host.setdefault(place(r["url"])[0], []).append((k, r))
        out: dict = {}
        with ThreadPoolExecutor(12) as pool:
            for res in pool.map(lambda pairs: [(k, fn(r)) for k, r in pairs],
                                sorted(by_host.values(), key=len, reverse=True)):
                out.update(res)
        return out

    reused: dict = {}  # the latest earlier answer of each page that answered open or closed
    removed_earlier: set = set()  # pages an earlier run (asked after the morning) found removed
    bare_403: set = set()  # … with a 403 recorded before the error codes were kept
    for d in reuse:
        src = [d / "pages.json"] if (d / "pages.json").exists() else [d / "previously_seen.json", d / "reopened.json"]
        for f in src:
            for x in json.loads(f.read_text()):
                k = (x["company"], x["job_id"])
                if x.get("page") in ("open", "closed"):
                    reused[k] = {k2: x[k2] for k2 in PAGE_FIELDS if k2 in x} | {"asked": "earlier run"}
                if x.get("page") == "closed":
                    removed_earlier.add(k)
                elif re.match(r"FetchError: HTTP 403 ", x.get("error") or ""):
                    bare_403.add(k)
    vague = [r for r in new if posted_day(r)[0] is None]
    to_ask = {(r["company"], r["job_id"]): r for r in missing + reopened + vague}
    asking = {k: r for k, r in to_ask.items() if k not in reused}
    print(f"job pages: {len(to_ask)} ({len(missing)} missing, {len(reopened)} reopened, {len(vague)} new with a vague "
          f"date); {len(to_ask) - len(asking)} answered by the earlier run, {len(asking)} asked now through Chrome",
          flush=True)
    t0 = datetime.now()
    try:
        pages = {k: reused[k] for k in to_ask if k in reused} | {
            k: v | {"asked": "this run"} for k, v in ask_by_site(asking, page).items()}
        ask_minutes = (datetime.now() - t0).total_seconds() / 60
        codes_403 = Counter(v.get("code") for v in pages.values() if v.get("status") == 403)
        if codes_403 and set(codes_403) == {"S22"}:  # every 403 with a recorded code was S22: so were the bare ones
            removed_earlier |= bare_403

        # 1. a missing role: its page, then (if open) what explains it
        rows1, pending = [], {}
        now_by_company = {c: listed_reqs(now_reqs, c) for c in {r["company"] for r in missing}}
        for r in missing:
            k = (r["company"], r["job_id"])
            pg = pages[k]
            if pg["page"] == "closed":
                verdict = "closed (page)"
            elif pg["page"] != "open":
                verdict = f"FAIL: page {pg['page']}"
            elif reqs_of(r) & now_by_company[r["company"]]:
                verdict = "same requisition, new address"
            elif place(r["url"]) not in earlier_listed:
                verdict = "unlisted (open, not on the earlier recording's list either)"
            else:
                verdict, pending[k] = None, r
            rows1.append({"company": r["company"], "job_id": r["job_id"], "title": r["title"], "url": r["url"],
                          "verdict": verdict, **pg, "morning_check": (last_check.get(r["company"]) or {}).get("status")})
        closed_again = {(r["company"], r["job_id"]): r for r in reopened
                        if pages[(r["company"], r["job_id"])]["page"] == "closed"}
        t1 = datetime.now()
        found = ask_by_site(pending | closed_again, search)
        search_minutes = (datetime.now() - t1).total_seconds() / 60
    finally:
        gate.close()
        shutil.rmtree(robots_copy, ignore_errors=True)
    (out / "pages.json").write_text(json.dumps([{"company": k[0], "job_id": k[1], **v} for k, v in pages.items()],
                                               indent=1, default=str))

    slipped: dict[tuple, list] = {}
    for x in rows1:
        k = (x["company"], x["job_id"])
        if k not in pending:
            continue
        s = found[k]
        x.update(s)
        p = place(x["url"])
        hs = (p[0], p[1])
        since = s["search"] == "found" and bool(s["search_posted"]) \
            and date.fromisoformat(s["search_posted"]) >= morning_day
        if since and complete_read(now_counts, hs):
            x["verdict"] = "relisted (the morning's read of its site was complete without it; posted again since)"
        elif since and k in removed_earlier:
            x["verdict"] = "relisted (an earlier run of this check found its page removed after the morning; " \
                           "posted again since)"
        elif s["search"] == "found" and short_by(now_counts, hs)[0] > 0:
            slipped.setdefault(hs, []).append(x)
        else:
            x["verdict"] = "FAIL: open, listed on the earlier recording, not listed this morning" + (
                f" (Workday's search: {s['search']})" if s["search"] != "found" else "")
    for hs, xs in slipped.items():
        short, within = short_by(now_counts, hs)
        for x in xs:
            x["walk_short_by"] = short
            x["verdict"] = (f"slipped past a walk (its site's searches {short} short, within tolerance)"
                            if within and len(xs) <= short else
                            f"FAIL: found by Workday's search; {len(xs)} such roles at its site, its walk {short} short"
                            + ("" if within else ", beyond tolerance"))
    fails = {"previously seen": [x for x in rows1 if x["verdict"].startswith("FAIL")]}
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
        p = place(r["url"])
        if day is None:
            verdict = "FAIL: no date"
        elif last is None or day > last:
            verdict = "after the last complete read"
        elif day == last:
            verdict = "same day as the last complete read"
        elif complete_read(earlier_counts, (p[0], p[1])) \
                and not reqs_of(r) & listed_reqs(earlier_reqs, r["company"]) \
                and not reqs_of(r) & ever_reqs.get(r["company"], set()):
            verdict = "listed late (not on the earlier recording's complete read, never in the database)"
        else:
            verdict = "FAIL: posted before the last complete read"
        rows2.append({"company": r["company"], "job_id": r["job_id"], "title": r["title"], "url": r["url"],
                      "postedOn": text, "posted_day": str(day), "from": source, "last_complete_read": str(last),
                      "verdict": verdict})
    fails["new"] = [x for x in rows2 if x["verdict"].startswith("FAIL")]
    # 3.
    rows3 = []
    for r in reopened:
        k = (r["company"], r["job_id"])
        pg = pages[k]
        s = found.get(k) or {}
        if pg["page"] == "open":
            verdict = "reopened (page open)"
        elif pg["page"] == "closed" and s.get("search") == "not found":
            verdict = "closed since the morning (page closed, Workday's search no longer finds it)"
        else:
            verdict = f"FAIL: page {pg['page']}" + (f", Workday's search: {s['search']}" if s else "")
        rows3.append({"company": r["company"], "job_id": r["job_id"], "title": r["title"], "url": r["url"],
                      "verdict": verdict, **pg, **s})
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
    # a role the morning lists at a new address: its old row (open before, not seen under its own id) and the
    # morning's row (new under its own id) share an id or the requisition; compared as one role, on the new listing
    gone: dict[tuple, set] = {}
    for b in open_before:
        if (b["company"], b["job_id"]) not in a_by:
            for i in ids_of(b) | reqs_of(b):
                gone.setdefault((b["company"], i), set()).add((b["company"], b["job_id"]))
    moved: dict[tuple, tuple] = {}
    for a in seen_now:
        if (a["company"], a["job_id"]) not in b_by:
            olds = set().union(*(gone.get((a["company"], i), set()) for i in ids_of(a) | reqs_of(a)))
            if len(olds) == 1:
                moved[(a["company"], a["job_id"])] = next(iter(olds))
    new_address = {v: k for k, v in moved.items()}

    def canon(keys) -> set:
        return {moved.get(k, k) for k in keys}
    chrome_c, runner_c = canon(chrome_match), canon(runner_match)
    opened = canon({(r["company"], r["job_id"]) for r in new} | {(r["company"], r["job_id"]) for r in reopened})
    closed = {(x["company"], x["job_id"]) for x in rows1 if not x["verdict"].startswith("FAIL")}
    fields = ("title", "location", "employment_type")
    rows4 = []
    for key in sorted((chrome_c ^ db_match) - opened - closed):
        side = "matched now, not in the database's matches" if key in chrome_c else \
            "in the database's matches, not matched now"
        b, a = b_by.get(key), a_by.get(new_address.get(key, key))
        a = as_judged(a) if a else None
        db_now = verdict(b) if b else None
        changes = ", ".join(f"{f} {b[f]!r} -> {a[f]!r}" for f in fields if (a[f] or "") != (b[f] or "")) \
            if a and b else ""
        if key in new_address:
            cause = f"same requisition, new address {new_address[key][1]!r}, judged on its new listing" + (
                f": {changes}" if changes else "")
        elif b and db_now == (key in chrome_c):
            cause = "stored decision older than a filter change (the filters give the same on the database's row)"
        elif b and changes and db_now == (key in db_match):
            cause = "the posting itself changed: " + changes
        else:
            cause = "unexplained"
        rows4.append({"company": key[0], "job_id": key[1], "title": (a or b or {}).get("title"), "side": side,
                      "cause": cause})
    fails["filters"] = [x for x in rows4 if x["cause"] == "unexplained"]

    for name, data in (("previously_seen", rows1), ("new", rows2), ("reopened", rows3), ("filters", rows4)):
        (out / f"{name}.json").write_text(json.dumps(data, indent=1, default=str))
    print(f"morning: run {run['id']} from {start}; {len(last_check)} checks ran")
    print(f"scope: {len(open_before)} Workday roles open in the database at {len({r['company'] for r in b_scope})} "
          f"companies; left out (open roles or counts): {report['out of scope']}")
    print(f"1. previously seen: {len(open_before) - len(missing)} appeared, {len(missing)} missing: "
          f"{dict(Counter(x['verdict'] for x in rows1))}")
    print(f"2. new: {len(new)}: {dict(Counter(x['verdict'] for x in rows2))}")
    print(f"3. reopened: {len(reopened)}: {dict(Counter(x['verdict'] for x in rows3))}")
    print(f"4. filters: {len(chrome_match)} matched in the morning, {len(db_match)} in the database; "
          f"{len(moved)} roles at a new address compared as one; {len(chrome_c - db_match)} more and "
          f"{len(db_match - chrome_c)} fewer, of which {len((chrome_c ^ db_match) & (opened | closed))} opened or "
          f"closed above; others: {dict(Counter(kind(x['cause']) for x in rows4))}")
    unexplained_runner = sorted((runner_c ^ db_match) - opened - closed)
    print(f"   the runner's own stored decisions that morning: {len(runner_match)} matched against "
          f"{len(db_match)}; differences beyond the roles opened, closed or moved: {len(unexplained_runner)}"
          + (f" {unexplained_runner[:10]}" if unexplained_runner else ""))
    print(f"pages: {len(asking)} asked in {ask_minutes:.1f} min, {len(to_ask) - len(asking)} from the earlier run; "
          f"Workday's own search asked for {len(found)} roles in {search_minutes:.1f} min; Chrome closed")
    print(f"   403 answers by Workday's error code: {dict(codes_403)}; pages an earlier run found removed: "
          f"{len(removed_earlier)}")
    bad = {k: v for k, v in fails.items() if v}
    for k, v in bad.items():
        print(f"FAIL {k}: {len(v)}")
        for x in v[:15]:
            print("   ", json.dumps(x, default=str)[:300])
    print("PASS" if not bad else "FAIL")
    return 0 if not bad else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    reuse = tuple(Path(args[i + 1]).resolve() for i, a in enumerate(args) if a == "--reuse")
    sys.exit(main(Path(args[0]).resolve(), Path(args[1]).resolve(), ask="--no-pages" not in args, reuse=reuse))
