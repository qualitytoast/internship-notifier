"""Coverage: the weekly report rows and COVERAGE.md.

COVERAGE.md merges three sources:
  config/companies.yaml        what is watched and how (checker, settings, blocked reason, fallback)
  discovery/results/<key>.json discovery evidence (hiring system, feed, feed total, careers-page total)
  discovery/verify.json        the last `internwatch verify --write` (what each checker returns live)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Company, Config
from .db import DB, iso, parse_iso, utcnow

# A checker count within this many jobs (or this fraction) of the careers page counts as equal (live churn).
CHURN_ABS, CHURN_REL = 3, 0.02


def _local(cfg: Config, iso_utc: str | None) -> str:
    dt = parse_iso(iso_utc)
    if dt is None:
        return ""
    tz = ZoneInfo(cfg.settings.get("email", "timezone", default="America/Chicago"))
    return dt.astimezone(tz).strftime("%b %d %H:%M")


def company_status(c: Company, st: dict) -> str:
    if c.status != "active":
        return c.status
    if st.get("alert_open") or (st.get("consecutive_failures") or 0) > 0 or (st.get("anomaly_streak") or 0) > 0:
        return "failing"
    return "ok" if st.get("last_success") else "never run"


def coverage_rows(cfg: Config, db: DB, window_days: int = 7) -> list[dict]:
    since = iso(utcnow() - timedelta(days=window_days))
    rows = []
    for c in cfg.companies:
        st = db.state(c.key)
        cov = db.coverage_row(c.key)
        errs = db.errors_since(c.key, since)
        rows.append({
            "key": c.key, "name": c.name,
            "checker": c.checker if c.status == "active" else f"{c.status}",
            "status": company_status(c, st), "last_success": _local(cfg, st.get("last_success")),
            "jobs": cov["open_jobs"], "students": cov["open_student"], "matched": cov["open_matched"],
            "errors": len(errs),
            "last_error": (c.blocked_reason if c.status == "blocked" else (st.get("last_error") or
                           (errs[-1]["error"] if errs else ""))) or "",
        })
    order = {"failing": 0, "never run": 1, "ok": 2, "blocked": 3, "disabled": 4}
    rows.sort(key=lambda r: (order.get(r["status"], 5), r["name"].lower()))
    return rows


# ---------------------------------------------------------------------------------------------
# discovery + verification records

def results_dir(root: Path) -> Path:
    return root / "discovery" / "results"


def load_results(root: Path) -> dict[str, dict]:
    out = {}
    d = results_dir(root)
    if d.exists():
        for p in sorted(d.glob("*.json")):
            try:
                out[p.stem] = json.loads(p.read_text())
            except ValueError:
                continue
    return out


def verify_path(root: Path) -> Path:
    return root / "discovery" / "verify.json"


def load_verify(root: Path) -> dict[str, dict]:
    p = verify_path(root)
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except ValueError:
        return {}


def save_verify(root: Path, data: dict[str, dict]) -> None:
    verify_path(root).write_text(json.dumps(dict(sorted(data.items())), indent=1) + "\n")


def fixture_path(cfg: Config, key: str) -> Path:
    return cfg.settings.path("fixtures") / f"{key}.json.gz"


def counts_agree(a: int | None, b: int | None) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(CHURN_ABS, CHURN_REL * max(a, b))


def verification_status(cfg: Config, c: Company, res: dict, ver: dict) -> tuple[str, str]:
    """(status, why) for COVERAGE.md: verified | blocked | mismatch | unverified | failing."""
    if c.status == "blocked":
        return "blocked", c.blocked_reason or res.get("blocked_reason", "")
    if c.status == "disabled":
        return "disabled", c.notes
    if not ver:
        return "unverified", "not yet run through `internwatch verify --write`"
    if ver.get("error"):
        return "failing", ver["error"][:160]
    if ver.get("degraded"):
        return "degraded", "part of the feed is failing (the rest is still read): " + ver["degraded"][:160]
    page = (c.verified or {}).get("page_total", res.get("page_total"))
    explained = (c.verified or {}).get("explained") or res.get("explained") or ""
    checker = ver.get("jobs")
    if not fixture_path(cfg, c.key).exists():
        return "unverified", "no recorded test fixture yet"
    if counts_agree(checker, page):
        return "verified", ""
    if explained:
        return "verified", explained
    return "mismatch", f"checker {checker} vs careers page {page}"


def _md(s) -> str:
    return str(s if s is not None else "—").replace("|", "\\|").replace("\n", " ")


def write_coverage_md(cfg: Config, path: Path | None = None) -> Path:
    root = cfg.root
    path = path or root / "COVERAGE.md"
    results, verify = load_results(root), load_verify(root)
    tz = ZoneInfo(cfg.settings.get("email", "timezone", default="America/Chicago"))
    lines, blocked, notes = [], [], []
    tally: dict[str, int] = {}
    for c in sorted(cfg.companies, key=lambda c: c.name.lower()):
        res, ver = results.get(c.key, {}), verify.get(c.key, {})
        status, why = verification_status(cfg, c, res, ver)
        tally[status] = tally.get(status, 0) + 1
        url = (c.careers_url or [res.get("careers_url", "")])[0]
        system = res.get("hiring_system") or c.checker
        feed = (c.verified or {}).get("feed") or res.get("feed") or ""
        page = (c.verified or {}).get("page_total", res.get("page_total"))
        interns = ver.get("students", res.get("intern_total"))
        checker_jobs = ver.get("jobs") if not ver.get("error") else None
        lines.append(f"| {_md(c.name)} | [{_md(url.split('//')[-1][:48])}]({url}) | {_md(system)} | "
                     f"`{_md(c.checker)}`: {_md(feed[:110])} | {_md(res.get('feed_total'))} | {_md(page)} | "
                     f"{_md(checker_jobs)} | {_md(interns)} | {status} |")
        if status == "blocked":
            blocked.append(f"| {_md(c.name)} | {_md(why)} | {_md(c.fallback or res.get('fallback'))} |")
        elif why:
            notes.append(f"- **{c.name}** ({status}): {why}")
    stamp = datetime.now(tz).strftime("%Y-%m-%d %H:%M %Z")
    summary = " · ".join(f"{n} {k}" for k, n in sorted(tally.items(), key=lambda kv: -kv[1]))
    out = [
        "# Coverage", "",
        f"Generated by `internwatch coverage` on {stamp}. One row per company in `config/companies.yaml` "
        f"({len(cfg.companies)} companies: {summary}).", "",
        "- **Feed jobs**: jobs in the hiring system's feed with no filters, measured during discovery.",
        "- **Page jobs**: jobs the live careers page showed with no filters (how it was observed is in "
        "`discovery/results/<company>.json` and `discovery/notes/`).",
        "- **Checker jobs**: what InternWatch's checker returned in the last `internwatch verify --write`.",
        "- **Intern roles**: intern / co-op / student / apprentice titles among them (any location, before your field and term filters).",
        "- **Status**: `verified` = the checker count equals the careers page (within live churn of "
        f"±{CHURN_ABS} jobs / {CHURN_REL:.0%}, or the difference is explained below) and a recorded test fixture exists; "
        "`degraded` = one of the company's sources is failing (details in the notes); "
        "`blocked` = automated access is not allowed, covered by the SimplifyJobs cross-check and the fallback listed below.",
        "",
        "| Company | Careers page | Hiring system | Checker: feed endpoint | Feed jobs | Page jobs | Checker jobs | Intern roles | Status |",
        "|---|---|---|---|--:|--:|--:|--:|---|",
        *lines, "",
    ]
    if blocked:
        out += ["## Blocked companies", "", "| Company | Why | Fallback |", "|---|---|---|", *blocked, ""]
    if notes:
        out += ["## Notes", "", *notes, ""]
    path.write_text("\n".join(out))
    return path
