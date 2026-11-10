"""Replayed `run --daily` mornings: record one live morning once, replay it through two versions of InternWatch on
copies of the same database, and compare everything they wrote, sent and asked for.

    python -I tools/prove/morning.py record <dir>                    a live daily run (no email sent, no heartbeat) on
                                                                     a copy of data/: <dir>/base.db (the database
                                                                     before it), <dir>/lists and <dir>/outbox (the kept
                                                                     lists and the emails it reads) and
                                                                     <dir>/morning.json.gz (every HTTP exchange, errors
                                                                     and robots.txt refusals included)
    python -I tools/prove/morning.py replay <version> <dir> <out> [edits]
                                                                     the recorded morning through <version> (a folder
                                                                     with src/ and config/) on a copy of base.db: one
                                                                     worker, the clock frozen at the recording's start,
                                                                     no email sent. Writes <out>/db.json, emails/,
                                                                     requests.json
    python -I tools/prove/morning.py compare <old out> <new out> [added keys…]

edits (comma-separated, for the plan's morning 2 and 3): after:<out> starts from the database an earlier replay
left; day:<n> sets the clock n days after the recording; new:<company>[;<company>…] gives each a new matching
posting; fail:<company>[;…] makes each fail; mailfail makes every email fail to send (with sending on).
A replay that needs a request the recording doesn't have gets an error for it, as an outage would, and the request
is listed. Allowed differences in compare: the added companies' own rows and keys (round: added), rows that went
from no company to one of them, and digest_at on untracked rows (set by the new code when an email lists them).
"""
from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
import sys
import threading
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MAIN = REPO if (REPO / "data" / "internwatch.db").exists() else REPO.parent / "internship-notifier"
TABLES = {  # table → (key columns, columns left out of the comparison)
    "jobs": (("company", "job_id"), ()),
    "company_state": (("company",), ()),
    "checks": (("run_id", "company"), ("id", "duration")),
    "source_health": (None, ()),
    "alerts": (("id",), ()),
    "kv": (("key",), ()),
    "simplify_rows": (("source", "row_key"), ()),
    "runs": (("id",), ()),
    "emails": (("id",), ("path",)),
}
ADDED = {  # with added companies, rows that take a number (alerts, emails) are matched by what they are, and a run's
    # totals count the added round too: those differences are printed for review, not counted
    "alerts": (("alert_key", "raised_at"), ("id",)),
    "emails": (("created_at", "kind"), ("id", "path", "subject")),
    "runs": (("id",), ("checked", "failed", "new_matches")),
}
SNAPSHOTS = {"lists": ("*.txt",), "outbox": ("*-morning*.eml", "*-digest*.eml")}  # what a morning reads from data/
# besides the database: the lists the first round kept, and the emails crosscheck.backfill_shown reads


def snapshot(out: Path) -> None:
    """The real data/ files a morning reads, as they were when it was recorded."""
    for name, globs in SNAPSHOTS.items():
        (out / name).mkdir(exist_ok=True)
        for g in globs:
            for p in (MAIN / "data" / name).glob(g):
                shutil.copy2(p, out / name / p.name)


def restore(src: Path, h: Path) -> set[str]:
    """Copy a snapshot (or an earlier replay's data/) into a home. Returns the emails already in its outbox."""
    for name in SNAPSHOTS:
        if (src / name).exists():
            shutil.copytree(src / name, h / "data" / name, dirs_exist_ok=True)
    return {p.name for p in (h / "data" / "outbox").glob("*.eml")}


def home(where: Path, version: Path, db: Path) -> Path:
    """A home with the version's config and a copy of the database."""
    if where.exists():
        shutil.rmtree(where)
    (where / "data").mkdir(parents=True)
    shutil.copytree(version / "config", where / "config")
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dst = sqlite3.connect(where / "data" / "internwatch.db")
    src.backup(dst)
    dst.close()
    src.close()
    return where


def record(out: Path) -> None:
    sys.path.insert(0, str(REPO / "src"))
    out.mkdir(parents=True, exist_ok=True)
    h = home(out / "home", REPO, MAIN / "data" / "internwatch.db")
    shutil.copy(h / "data" / "internwatch.db", out / "base.db")
    if (MAIN / "data" / "robots").exists():
        shutil.copytree(MAIN / "data" / "robots", h / "data" / "robots")
    snapshot(out)
    restore(out, h)
    from internwatch import config as configmod, heartbeat, http as httpmod
    from internwatch.db import iso
    from internwatch.runner import RunOptions, Runner
    heartbeat.Heartbeat._ping = lambda self, *a, **kw: None  # the real morning's monitor must not hear of this one
    exchanges, lock, request = [], threading.Lock(), httpmod.Http.request

    def recorded(self, method, url, **kw):
        full, body = httpmod.canonical_url(url, kw.get("params")), httpmod.body_key(kw.get("json"), kw.get("data"))
        e = {"method": method, "url": full, "body": body}
        try:
            r = request(self, method, url, **kw)
        except Exception as err:  # noqa: BLE001 — replayed as the same failure
            e.update(error=type(err).__name__, message=str(err), kind=getattr(err, "kind", None))
            with lock:
                exchanges.append(e)
            raise
        e.update(status=r.status, final_url=r.url, headers=dict(r.headers), text=r.content.decode("utf-8", "replace"))
        with lock:
            exchanges.append(e)
        return r
    httpmod.Http.request = recorded
    cfg = configmod.load(h)
    started = iso()
    s = Runner(cfg).run(RunOptions(daily=True, send=False))
    with gzip.open(out / "morning.json.gz", "wt") as f:
        json.dump({"started": started, "local_date": datetime.now().date().isoformat(), "line": s.line(),
                   "exchanges": exchanges}, f)
    print(f"recorded {len(exchanges)} exchanges: {s.line()} -> {out}")


def replay(version: Path, rec: Path, out: Path, edits: str = "") -> None:
    sys.path.insert(0, str(version / "src"))
    import random
    from internwatch import config as configmod, heartbeat, http as httpmod, mailer, models
    import internwatch
    from internwatch.db import parse_iso
    from internwatch.runner import RunOptions, Runner
    import importlib
    import pkgutil
    for m in pkgutil.walk_packages(internwatch.__path__, "internwatch."):  # modules imported later get the clock too
        if not m.name.endswith("__main__"):  # that one runs the command line
            importlib.import_module(m.name)
    morning = json.load(gzip.open(rec / "morning.json.gz", "rt"))
    edit = dict(e.split(":", 1) if ":" in e else (e, "") for e in edits.split(",") if e)
    from datetime import timedelta
    frozen = parse_iso(morning["started"]) + timedelta(days=float(edit.get("day") or 0))
    import internwatch.db as dbmod

    class Frozen(dbmod.datetime):  # utcnow itself, wherever a reference to it was kept (moves.Ctx's default)
        @classmethod
        def now(cls, tz=None):
            return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)
    dbmod.datetime = Frozen
    for mod in list(sys.modules.values()):  # the clock of every module that took utcnow from internwatch.db
        if getattr(mod, "__name__", "").startswith("internwatch") and hasattr(mod, "utcnow"):
            mod.utcnow = lambda: frozen
    random.uniform = lambda lo, hi: (float(lo) + float(hi)) / 2
    heartbeat.Heartbeat._ping = lambda self, *a, **kw: None
    Runner.online = lambda self: True
    queues: dict[tuple, list] = {}
    for e in morning["exchanges"]:
        queues.setdefault((e["method"], e["url"], e["body"]), []).append(e)
    asked, missing = [], []

    def served(self, method, url, *, params=None, json=None, data=None, headers=None, timeout=None, ok_statuses=(),
               check_robots=True):
        full, body = httpmod.canonical_url(url, params), httpmod.body_key(json, data)
        asked.append([method, full, body])
        q = queues.get((method, full, body)) or []
        if not q:
            missing.append([method, full, body])
            raise models.FetchError(f"replay: no recorded response for {method} {full[:160]}")
        e = q.pop(0) if len(q) > 1 else q[0]
        if "error" in e:
            cls = getattr(models, e["error"], None) or getattr(httpmod, e["error"], None) or models.FetchError
            err = cls(e["message"])
            if e.get("kind") and not getattr(err, "kind", None):
                err.kind = e["kind"]
            raise err
        resp = httpmod.Resp(e["status"], e.get("final_url") or full, dict(e["headers"]), e["text"].encode("utf-8"))
        if resp.status >= 400 and resp.status not in ok_statuses:
            raise models.FetchError(f"HTTP {resp.status} for {method} {url[:160]}")
        return resp
    httpmod.Http.request = served
    import logging
    out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=out / "run.log", level=logging.INFO, force=True,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    h = home(out / "home", version, Path(edit["after"]) / "home" / "data" / "internwatch.db" if "after" in edit
             else rec / "base.db")
    already = restore(Path(edit["after"]) / "home" / "data" if "after" in edit else rec, h)
    cfg = configmod.load(h)
    checker_fn = None
    if "new" in edit or "fail" in edit:
        from internwatch.runner import run_checker
        from internwatch.models import Job
        new, fail = set(filter(None, edit.get("new", "").split(";"))), set(filter(None, edit.get("fail", "").split(";")))

        def checker_fn(cfg_, c, **kw):
            o = run_checker(cfg_, c, **kw)
            if c.key in fail:
                o.jobs, o.error_kind, o.error = None, "error", "HTTP 503 (injected)"
            elif c.key in new and o.jobs is not None:
                o.jobs = o.jobs + [Job(id=f"injected-{c.key}", title="Software Engineer Intern (Summer 2027)",
                                       location="New York, NY", url=f"https://example.com/{c.key}/injected")]
            return o
    send = "mailfail" in edit
    if send:
        mailer.Mailer.ready = lambda self: (True, "")
        mailer.Mailer.send = lambda self, kind, subject, text, html, attachments=None: (False, "SMTP down (injected)", None)
    r = Runner(cfg, checker_fn=checker_fn) if checker_fn else Runner(cfg)
    s = r.run(RunOptions(daily=True, send=send, workers=1, retry_delay=0))
    db = sqlite3.connect(h / "data" / "internwatch.db")
    db.row_factory = sqlite3.Row
    dumped = {t: [dict(x) for x in db.execute(f"SELECT * FROM {t}")] for t in TABLES}
    (out / "db.json").write_text(json.dumps(dumped, sort_keys=True, default=str))
    (out / "requests.json").write_text(json.dumps({"asked": asked, "missing": missing}))
    mails = out / "emails"
    mails.mkdir(exist_ok=True)
    for i, p in enumerate(sorted(p for p in (h / "data" / "outbox").glob("*.eml") if p.name not in already)):
        shutil.copy(p, mails / f"{i:02d}-{p.name.split('-', 2)[-1]}")
        shutil.copy(p.with_suffix(".html"), mails / f"{i:02d}-{p.with_suffix('.html').name.split('-', 2)[-1]}")
    print(f"replayed with {internwatch.__file__}: {s.line()}; {len(asked)} requests, {len(missing)} not recorded")


def links(html_path: Path) -> set[str]:
    """Every link in an email: its HTML body and its attachments (the .eml next to it)."""
    import email
    import html as htmllib
    import re
    eml = html_path.with_suffix(".eml")
    texts = [html_path.read_text()]
    if eml.exists():
        for part in email.message_from_bytes(eml.read_bytes()).walk():
            if part.get_content_type() in ("text/html", "text/csv"):
                texts.append(part.get_payload(decode=True).decode("utf-8", "replace"))
    return {htmllib.unescape(u) for t in texts for u in re.findall(r'(?:href="|,)(https?://[^"\s,]+)', t)}


def compare(old_out: Path, new_out: Path, added: set[str]) -> int:
    old, new = json.loads((old_out / "db.json").read_text()), json.loads((new_out / "db.json").read_text())
    problems, review = [], []
    for table, (keys, skip) in TABLES.items():
        if added and table in ADDED:
            keys, skip = ADDED[table]
            for x in sorted((r for r in new[table] if r.get("kind") != "watching" and r.get("company") not in added),
                            key=lambda r: r["id"]):
                y = next((r for r in old[table] if all(r[c] == x[c] for c in keys)), {})
                review += [f"{table} {x['id']} {c}: {y.get(c)} -> {x[c]}" for c in skip
                           if c not in ("id", "path") and y.get(c) != x[c]]

        def keyed(rows):
            out = {}
            for r in rows:
                r = {k: v for k, v in r.items() if k not in skip}
                k = tuple(r[c] for c in keys) if keys else json.dumps(r, sort_keys=True)
                out[k] = r
            return out
        a, b = keyed(old[table]), keyed(new[table])
        for k in sorted(set(a) | set(b), key=str):
            ra, rb = a.get(k), b.get(k)
            if ra == rb:
                continue
            ours = rb or ra
            if table == "kv" and any(x in k[0] for x in [*(f":{c}" for c in added), "lists:added:", "golive:",
                                                           "simplify_open:", "digest_backfilled"]):
                continue
            if isinstance(ours, dict) and (ours.get("company") in added or ours.get("tracked_company") in added):
                if table != "simplify_rows" or (ra or {}).get("tracked_company") in (None, *added):
                    continue
            if added and table == "emails" and ours.get("kind") == "watching":
                continue
            if table == "simplify_rows" and ra and rb and {c for c in ra if ra[c] != rb[c]} == {"digest_at"} \
                    and ra["digest_at"] is None and ra["tracked_company"] is None:
                continue
            problems.append(f"{table} {k}: {ra} -> {rb}")
    ea = sorted(p.name for p in (old_out / "emails").glob("*.html"))
    eb = sorted(p.name for p in (new_out / "emails").glob("*.html"))
    if not added:  # nothing added: every email byte for byte
        if [n[3:] for n in ea] != [n[3:] for n in eb]:
            problems.append(f"emails: {ea} -> {eb}")
        else:
            for x, y in zip(ea, eb):
                if (old_out / "emails" / x).read_text() != (new_out / "emails" / y).read_text():
                    problems.append(f"emails: {x} differs")
    else:  # the same emails apart from "Now watching", and every link of the old ones still there (but the rows
        # that went to an added company); which jobs were emailed is in the jobs table, compared above
        kinds = lambda names: [n[3:] for n in names if "watching" not in n]  # noqa: E731
        if kinds(ea) != kinds(eb):
            problems.append(f"emails: {ea} -> {eb}")
        theirs = {r["url"] for r in new["simplify_rows"] if r.get("tracked_company") in added and r.get("url")}
        for x, y in zip([n for n in ea if "watching" not in n], [n for n in eb if "watching" not in n]):
            lost = links(old_out / "emails" / x) - links(new_out / "emails" / y) - theirs
            if lost:
                problems.append(f"emails: {x}: {len(lost)} links gone, e.g. {sorted(lost)[:3]}")
    if added:  # a run records the 198's alerts first, so each keeps the number the old code gives it that morning
        for t in sorted({a["raised_at"] for a in new["alerts"]}):
            ours = [a["id"] for a in new["alerts"] if a["raised_at"] == t and a["company"] not in added]
            theirs = [a["id"] for a in new["alerts"] if a["raised_at"] == t and a["company"] in added]
            if ours and theirs and max(ours) > min(theirs):
                problems.append(f"alerts raised {t}: an added company's alert is numbered before one of the 198's")
    ra = json.loads((old_out / "requests.json").read_text())
    rb = json.loads((new_out / "requests.json").read_text())
    if rb["asked"][:len(ra["asked"])] != ra["asked"]:
        problems.append("requests: the old version's requests are not the start of the new version's, in order")
    for p in review:
        print("   review:", p)
    for p in problems[:100]:
        print("  ", p)
    print("PASS" if not problems else f"FAIL ({len(problems)} differences)")
    return 0 if not problems else 1


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "record":
        record(Path(sys.argv[2]))
    elif cmd == "replay":
        replay(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5] if len(sys.argv) > 5 else "")
    elif cmd == "compare":
        sys.exit(compare(Path(sys.argv[2]), Path(sys.argv[3]), set(sys.argv[4:])))
