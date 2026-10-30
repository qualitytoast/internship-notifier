"""The list of open alerts: every alert stays in each run's morning email until its problem clears or you dismiss it.

Every check still raises its problems as before (a dict in RunSummary.problems or .misses). The runner puts them on this
list, one row per thing wrong (`alert_key`), and asks each row whether its problem has cleared. Because the list is
kept in the database, a day without a run or a failed email can't lose an alert. A problem carries how it resolves in
p["alert"] = {id, rule, …}, or in p["alerts"] = [{id, rule, summary, …}, …] when one line of a HEALTH email covers
several things (two new sites of a tenant) that clear one by one.

  rule          resolved when
  health        the company's next fully healthy poll
  zero          the company lists jobs again
  count         its job count is back at `need` or more (the level at which the alert would not have fired)
  full          a full scan of a big site succeeds
  unchecked     the company is processed in a run
  source_empty  the board lists jobs again
  source_count  the board's count is back at `need` or more
  quiet         a new job id appears on the board
  students      student roles are back at `need` or more
  system_new    the job system is added to the config, or the page stops naming it (seen())
  system_gone   the page names it again (back()), or it is removed from the config
  site          the Workday site is added to the config, or leaves robots.txt (seen())
  list_system   the job system is added to the config, or no list links it any more (seen())
  posting       InternWatch stores the posting, or it leaves the place it was seen (seen())
  miss          the checker stores the role, the role matches, or it closes (seen())
  dark          the list or check answers again
  manual        only dismissing ends it: nothing can tell when you have looked at a new page or label

state: open → resolved (its problem cleared), or open → dismissed → cleared (dismissed, then its problem cleared).
Only open and dismissed rows hold their key, so a problem that clears and comes back later is a new alert.
"""
from __future__ import annotations

import json
import logging
import re

from .config import Company, Config
from .db import DB, iso, utcnow

log = logging.getLogger(__name__)

LIVE = ("open", "dismissed")


def alert_key(p: dict, item: dict) -> str:
    return item.get("id") or p.get("reset_kv") or f"{p['kind']}:{p.get('key', '')}"


def _items(p: dict) -> list[dict]:
    return p.get("alerts") or [p.get("alert") or {}]


def _row(db: DB, key: str):
    return db.one("SELECT * FROM alerts WHERE alert_key=? AND state IN ('open', 'dismissed')", key)


def _upsert(db: DB, p: dict, item: dict, now: str, told: str | None = None) -> bool:
    """One thing wrong: a new row, or the open row brought up to date. True while no HEALTH email has told about it."""
    key = alert_key(p, item)
    data = {k: v for k, v in item.items() if k not in ("id", "rule", "summary")}
    summary = item.get("summary") or p["summary"]
    row = _row(db, key)
    if row is None:
        db.conn.execute(
            "INSERT INTO alerts(alert_key, company, name, kind, summary, detail, url, rule, data, since, raised_at, health_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (key, p.get("key", ""), p.get("name", ""), p["kind"], summary, p.get("detail", ""), p.get("careers_url", ""),
             item.get("rule", "manual"), json.dumps(data), p.get("since") or now, now, told))
        return told is None
    if row["state"] == "dismissed":
        return False
    db.conn.execute("UPDATE alerts SET kind=?, summary=?, detail=? WHERE id=?",
                    (p["kind"], summary, p.get("detail", ""), row["id"]))
    return row["health_at"] is None


def record(db: DB, problems: list[dict], misses: list[dict]) -> tuple[list[dict], list[dict]]:
    """Put a run's problems and misses on the list. Returns the ones no HEALTH email has told about yet."""
    now = iso()
    fresh = [p for p in problems if any([_upsert(db, p, i, now) for i in _items(p)])]
    return fresh, [m for m in misses if _upsert(db, *_miss(m), now)]


def _miss(m: dict) -> tuple[dict, dict]:
    """A possible miss as a problem and its alert. `how`: "never" seen by the checker, or "filtered" out."""
    return ({"key": m.get("key", ""), "name": m["company"], "kind": "possible miss", "careers_url": m.get("url", ""),
             "summary": f"{m['title']}: {m['reason']}"},
            {"id": f"miss:{m.get('source')}:{m.get('row_key')}", "rule": "miss", "item": m.get("row_key"),
             "scope": m.get("source", ""), "how": m.get("how", "never")})


def live(db: DB, company: str | None = None, rule: str | None = None):
    """The rows holding their key, of one company and/or one rule."""
    where = ["state IN ('open', 'dismissed')"]
    args = []
    if company is not None:
        where.append("company=?")
        args.append(company)
    if rule is not None:
        where.append("rule=?")
        args.append(rule)
    return db.q(f"SELECT * FROM alerts WHERE {' AND '.join(where)} ORDER BY id", *args)


def _close(db: DB, a, now: str) -> None:
    db.conn.execute("UPDATE alerts SET state=?, closed_at=? WHERE id=?",
                    ("resolved" if a["state"] == "open" else "cleared", now, a["id"]))


def seen(db: DB, company: str, rule: str, present: set, scope: str = "", needed: int = 1) -> None:
    """A check has just read what an alert points at, and `present` is what it found: an alert whose item is missing
    from it `needed` reads in a row has cleared."""
    now = iso()
    for a in live(db, company, rule):
        d = json.loads(a["data"])
        if d.get("scope", "") != scope:
            continue
        misses = 0 if d.get("item") in present else int(d.get("misses", 0)) + 1
        if misses >= needed:
            _close(db, a, now)
        elif misses != d.get("misses", 0):
            db.conn.execute("UPDATE alerts SET data=? WHERE id=?", (json.dumps({**d, "misses": misses}), a["id"]))


def back(db: DB, company: str, rule: str, present: set, scope: str = "") -> None:
    """The opposite of seen(): an alert about something gone clears when the thing is there again."""
    now = iso()
    for a in live(db, company, rule):
        d = json.loads(a["data"])
        if d.get("scope", "") == scope and d.get("item") in present:
            _close(db, a, now)


# what clears an alert, judged from what the run stored ----------------------------------------------------------------

def _source(db: DB, a, d: dict):
    return db.one("SELECT * FROM source_health WHERE company=? AND source=?", a["company"], d["source"])


def _configured(cfg: Config, c: Company) -> set[str]:
    """Every name a company's configured job systems go by (aliases resolved), lower case."""
    from . import liveness, moves  # they import this module
    al = moves.aliases(cfg)
    keys = liveness.config_keys(c) | liveness.config_keys(c, liveness.page_key) | moves.config_keys_v2(c)
    return {k.lower() for k in keys} | {al.get(k, k).lower() for k in keys}


def _cfg_system(cfg: Config, a, d: dict) -> bool:
    from . import moves  # moves imports this module
    c = next((x for x in cfg.companies if x.key == a["company"]), None)
    system = d.get("system", d.get("item", "")).lower()
    return c is None or system in _configured(cfg, c) or moves.aliases(cfg).get(system, system) in _configured(cfg, c)


def _site(cfg: Config, a, d: dict) -> bool:
    c = next((x for x in cfg.companies if x.key == a["company"]), None)
    if c is None:
        return True
    s = c.settings or {}
    sources = [x.get("settings") or {} for x in s.get("sources") or []] or [s]
    return d.get("item", "").lower() in {str(x).lower() for st in sources for x in (st.get("sites") or [st.get("site")]) if x}


def _posting(cfg: Config, db: DB, a, d: dict) -> bool:
    from . import moves  # moves imports this module
    item = d.get("item", "")
    if item.startswith("title:"):
        titles = {re.sub(r"[^a-z0-9]", "", t) for t in moves.stored_titles(db, a["company"], days=3650)}
        return moves.title_stored(item[len("title:"):], titles)
    return moves.is_stored(item, moves.stored_tokens(db, a["company"]))


def _miss_cleared(db: DB, a, d: dict) -> bool:
    from .crosscheck import Row, find_in_db  # crosscheck imports the filters; this keeps the import graph simple
    r = db.one("SELECT * FROM simplify_rows WHERE source=? AND row_key=?", d.get("scope", ""), d.get("item", ""))
    if r is None:
        return True
    hit, _ = find_in_db(db, a["company"], Row(r["source"], r["row_key"], r["company"], r["title"], r["location"] or "",
                                              r["url"] or "", "", r["category"] or "", r["terms"] or ""))
    if hit is None:
        return False
    return d.get("how") != "filtered" or bool(hit["matched"]) or hit["removed_at"] is not None


def cleared(cfg: Config, db: DB, a) -> bool:
    d = json.loads(a["data"])
    rule, c = a["rule"], a["company"]
    if rule == "health":
        st = db.state(c)
        return not st["consecutive_failures"] and not st["failing_since"]
    if rule == "zero":
        return not db.get(f"zero_open:{c}")
    if rule == "count":
        return (db.state(c)["last_count"] or 0) >= d["need"]
    if rule == "full":
        return not int(db.get(f"full_fail:{c}") or 0)
    if rule == "unchecked":
        return not db.get(f"unchecked_runs:{c}")
    if rule == "source_empty":
        r = _source(db, a, d)
        return r is None or not r["empty_since"]
    if rule == "source_count":
        r = _source(db, a, d)
        return r is None or (r["last_count"] or 0) >= d["need"]
    if rule == "quiet":
        r = _source(db, a, d)
        return r is None or not r["stale_since"]
    if rule == "students":
        r = db.one("SELECT students FROM checks WHERE company=? ORDER BY id DESC LIMIT 1", c)
        return r is not None and (r["students"] or 0) >= d["need"]
    if rule in ("system_new", "list_system"):
        return _cfg_system(cfg, a, d)
    if rule == "system_gone":
        return next((x for x in cfg.companies if x.key == a["company"]), None) is None or not _cfg_system(cfg, a, d)
    if rule == "site":
        return _site(cfg, a, d)
    if rule == "posting":
        return _posting(cfg, db, a, d)
    if rule == "miss":
        return _miss_cleared(db, a, d)
    if rule == "dark":
        from . import moves  # moves imports this module
        return moves.dark(db, d["check"], d["item"], utcnow()) is None
    return False


def sweep(cfg: Config, db: DB) -> None:
    """Close every alert whose problem has cleared."""
    now = iso()
    for a in live(db):
        if cleared(cfg, db, a):
            _close(db, a, now)


def start(cfg: Config, db: DB) -> None:
    """Once: put the problems open before this list existed on it. They were emailed then, so none counts as new."""
    if db.get("alerts_started"):
        return
    from . import liveness  # liveness imports this module
    liveness.ensure_schema(db)
    now = iso()
    names = {c.key: c for c in cfg.companies}

    def add(key: str, kind: str, summary: str, since: str | None, item: dict, name: str = "") -> None:
        c = names.get(key)
        p = {"key": key, "name": name or (c.name if c else key), "kind": kind, "summary": summary, "since": since,
             "careers_url": (c.careers_url or [""])[0] if c else ""}
        _upsert(db, p, item, now, told=now)

    for r in db.q("SELECT * FROM company_state WHERE alert_open=1"):
        summary = (r["last_error"] or "").split(":")[0]
        if r["last_error_kind"] == "zero":
            add(r["company"], "zero", summary, r["failing_since"], {"id": f"zero:{r['company']}", "rule": "zero"})
        elif r["last_error_kind"] != "drop":  # a drop's earlier count is gone: only new ones can be judged
            add(r["company"], r["last_error_kind"] or "error", summary, r["failing_since"],
                {"id": f"health:{r['company']}", "rule": "health"})
    for r in db.q("SELECT * FROM source_health WHERE empty_since IS NOT NULL"):
        add(r["company"], "board empty", f"{r['label'] or r['source']} lists 0 jobs", r["empty_since"],
            {"id": f"live_alert:{r['company']}:{r['source']}:empty", "rule": "source_empty", "source": r["source"]})
    from .crosscheck import abroad  # crosscheck imports this module
    for r in db.q("SELECT * FROM simplify_rows WHERE status IN ('filtered', 'missed')"):
        c = names.get(r["tracked_company"])
        if c is not None and not abroad(cfg, c, r["location"] or ""):
            how = "filtered" if r["status"] == "filtered" else "never"
            _upsert(db, *_miss({"company": c.name, "key": c.key, "how": how, "title": r["title"], "url": r["url"] or "",
                                "source": r["source"], "row_key": r["row_key"],
                                "reason": "rejected by your filters" if how == "filtered" else "the checker never saw it"}),
                    now, told=now)
    db.set("alerts_started", now)


# the emails and the commands ---------------------------------------------------------------------------------------

def for_email(db: DB) -> tuple[list, list]:
    """(open alerts, alerts resolved since the last email that listed them)."""
    return (db.q("SELECT * FROM alerts WHERE state='open' ORDER BY health_at IS NOT NULL, id"),
            db.q("SELECT * FROM alerts WHERE state='resolved' AND told_at IS NULL ORDER BY id"))


def mark_told(db: DB) -> None:
    db.conn.execute("UPDATE alerts SET told_at=? WHERE state='resolved' AND told_at IS NULL", (iso(),))


def mark_sent(db: DB) -> None:
    db.conn.execute("UPDATE alerts SET health_at=? WHERE state='open' AND health_at IS NULL", (iso(),))


def dismiss(db: DB, ids: list[int] | None = None, kind: str | None = None) -> list:
    """Stop repeating these open alerts. Returns them; each stays off until its problem clears."""
    rows = [a for a in db.q("SELECT * FROM alerts WHERE state='open' ORDER BY id")
            if (ids and a["id"] in ids) or (kind and a["kind"] == kind)]
    now = iso()
    for a in rows:
        db.conn.execute("UPDATE alerts SET state='dismissed', dismissed_at=? WHERE id=?", (now, a["id"]))
    return rows
