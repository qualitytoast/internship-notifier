"""A morning read through Chrome (tools/prove/morning.py record) against the last morning read before the refusals.

    python -I tools/prove/chrome_morning.py <chrome recording dir> <earlier recording dir> [<earlier run id>]

<earlier run id> is that morning's run in data/internwatch.db (Nov 15: 29); without it only the earlier recording is
used. Reports, and FAIL on the first:
- every Workday company's check whole in the Chrome morning (status ok: no error, nothing partial)
- Workday requests per site, against the earlier recording (sites more than 25% and 10 requests apart are listed)
- the wording of postedOn and of the places (locationsText) in the job lists: the forms used, and for postings both
  mornings list, how many say exactly the same
- minutes and requests per Workday company and per round, against the earlier run
- no Chrome left running and no InternWatch Chrome profile left on disk
"""
from __future__ import annotations

import gzip
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from internwatch import browser  # noqa: E402
from internwatch import config as configmod  # noqa: E402

CXS = re.compile(r"^https://(?P<host>[^/]+)/wday/cxs/(?P<tenant>[^/]+)/(?P<site>[^/]+)/")
WD = ("myworkdayjobs.com", "myworkdaysite.com")


def is_wd(url: str) -> bool:
    host = urlsplit(url).netloc
    return any(host == h or host.endswith("." + h) for h in WD)


def rows(db: Path, sql: str, *args):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


def load(rec: Path):
    with gzip.open(rec / "morning.json.gz", "rt") as f:
        return json.load(f)


def shape(text: str) -> str:
    return re.sub(r"\d+", "N", text or "")


def main(chrome_dir: Path, earlier_dir: Path, earlier_run: int | None) -> int:
    cfg = configmod.load(REPO)
    wd_companies = {}
    for c in cfg.companies:
        s = c.settings or {}
        n = sum(1 for x in s.get("sources") or [] if x.get("checker") == "workday") if c.checker == "multi" \
            else int(c.checker == "workday")
        if n:
            wd_companies[c.key] = c.round or ""
    after = chrome_dir / "home" / "data" / "internwatch.db"
    run = rows(after, "SELECT * FROM runs ORDER BY id DESC LIMIT 1")[0]
    checks = {}
    for r in rows(after, "SELECT * FROM checks WHERE run_id=? ORDER BY id", run["id"]):
        if r["company"] in wd_companies:
            checks[r["company"]] = r  # the last check (a retry's, if there was one)
    first_try = {}
    for r in rows(after, "SELECT * FROM checks WHERE run_id=? ORDER BY id DESC", run["id"]):
        if r["company"] in wd_companies:
            first_try[r["company"]] = r
    problems = []
    not_whole = {k: (r["status"], r["error_kind"], (r["error"] or "")[:160]) for k, r in checks.items()
                 if r["status"] != "ok" or r["error_kind"]}
    missing = sorted(set(wd_companies) - set(checks))
    retried = sorted(k for k in checks if first_try[k]["id"] != checks[k]["id"])
    print(f"Chrome morning: run {run['id']}, {run['started_at']} to {run['finished_at']}: {run['note'] or run['status']}")
    print(f"1. Workday companies checked: {len(checks)} of {len(wd_companies)}; whole: {len(checks) - len(not_whole)}; "
          f"second tries: {len(retried)} {retried[:10]}")
    for k, v in sorted(not_whole.items()):
        print(f"   NOT WHOLE {k}: {v}")
    if not_whole or missing:
        problems.append(f"{len(not_whole)} Workday checks not whole, {len(missing)} not checked {missing[:10]}")

    new, old = load(chrome_dir), load(earlier_dir)

    def per_site(ex):
        c = Counter()
        for e in ex:
            m = CXS.match(e["url"])
            if m:
                c[(m["host"], m["site"])] += 1
        return c
    a, b = per_site(new["exchanges"]), per_site(old["exchanges"])
    off = sorted((k, b.get(k, 0), a.get(k, 0)) for k in set(a) | set(b)
                 if abs(a.get(k, 0) - b.get(k, 0)) > max(10, 0.25 * max(a.get(k, 0), b.get(k, 0))))
    print(f"2. Workday requests: {sum(a.values())} to {len(a)} sites this morning, {sum(b.values())} to {len(b)} sites "
          f"on {old['local_date']}; sites more than 25% and 10 requests apart: {len(off)}")
    for (host, site), x, y in off:
        print(f"   {host}/{site}: {x} -> {y}")
    statuses = Counter(str(e.get("status") or e.get("error")) for e in new["exchanges"] if is_wd(e["url"]))
    print(f"   answers to Workday requests this morning: {dict(statuses)}")

    def postings(ex):
        out = {}
        for e in ex:
            m = CXS.match(e["url"])
            if not m or e["method"] != "POST" or str(e.get("status")) != "200":
                continue
            try:
                d = json.loads(e.get("text") or "")
            except ValueError:
                continue
            for p in d.get("jobPostings") or []:
                if p.get("externalPath"):
                    out[(m["host"], m["site"], p["externalPath"])] = (p.get("postedOn") or "", p.get("locationsText")
                                                                      or "", p.get("title") or "")
        return out
    pa, pb = postings(new["exchanges"]), postings(old["exchanges"])
    forms_a = Counter(shape(v[0]) for v in pa.values())
    forms_b = Counter(shape(v[0]) for v in pb.values())
    both = set(pa) & set(pb)
    same_place = sum(1 for k in both if pa[k][1] == pb[k][1])
    same_title = sum(1 for k in both if pa[k][2] == pb[k][2])
    print(f"3. postedOn forms this morning: {dict(forms_a)}")
    print(f"   postedOn forms on {old['local_date']}: {dict(forms_b)}")
    new_forms = set(forms_a) - set(forms_b)
    if new_forms:
        problems.append(f"postedOn forms never seen before: {sorted(new_forms)}")
    loc_a = Counter(shape(v[1]) for v in pa.values() if re.fullmatch(r"\d+ Locations", v[1] or ""))
    print(f"   postings listed both mornings: {len(both)}; same place text: {same_place}; same title: {same_title}; "
          f"'N Locations' this morning: {sum(loc_a.values())}")
    diff_place = [(k, pb[k][1], pa[k][1]) for k in sorted(both) if pa[k][1] != pb[k][1]][:8]
    for k, x, y in diff_place:
        print(f"   place changed: {k[0]}/{k[1]}{k[2][:60]}: {x!r} -> {y!r}")

    if earlier_run is not None:
        before = {r["company"]: r for r in rows(REPO / "data" / "internwatch.db",
                                                "SELECT * FROM checks WHERE run_id=? ORDER BY id", earlier_run)}
    else:
        before = {}
    print(f"4. minutes and requests per Workday company (this morning against run {earlier_run}):")
    for rnd in sorted(set(wd_companies.values())):
        ks = [k for k in checks if wd_companies[k] == rnd]
        mins = sum(checks[k]["duration"] or 0 for k in ks) / 60
        reqs = sum(checks[k]["requests"] or 0 for k in ks)
        bmins = sum((before.get(k) or {}).get("duration") or 0 for k in ks) / 60
        breqs = sum((before.get(k) or {}).get("requests") or 0 for k in ks)
        print(f"   round {rnd or 'the 198'}: {len(ks)} companies, {reqs} requests in {mins:.1f} check-minutes "
              f"(run {earlier_run}: {breqs} requests in {bmins:.1f})")
        rs = rows(after, "SELECT MIN(started_at) s FROM checks WHERE run_id=? AND company IN (%s)"
                  % ",".join("?" * len(ks)), run["id"], *ks) if ks else []
        if rs and rs[0]["s"]:
            print(f"      first Workday check of the round started {rs[0]['s']}")
    slow = sorted(((checks[k]["duration"] or 0) / 60, k, (before.get(k) or {}).get("duration")) for k in checks)[-12:]
    for m, k, bd in reversed(slow):
        print(f"   {k}: {m:.1f} min, {checks[k]['requests']} requests (run {earlier_run}: "
              f"{(bd or 0) / 60:.1f} min, {(before.get(k) or {}).get('requests')} requests)")

    left = sorted(Path(tempfile.gettempdir()).glob(browser.PROFILE_PREFIX + "*"))
    procs = subprocess.run(["pgrep", "-f", browser.PROFILE_PREFIX], capture_output=True, text=True).stdout.split()
    print(f"5. Chrome profiles left: {len(left)} {[p.name for p in left[:3]]}; InternWatch Chrome processes left: "
          f"{len(procs)}")
    if left or procs:
        problems.append("Chrome left behind")
    for p in problems:
        print("FAIL", p)
    print("PASS" if not problems else "FAIL")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(),
                  int(sys.argv[3]) if len(sys.argv) > 3 else None))
