"""Turn each check result into health state, and decide when an alert email is due.

A company's problem is alerted only after `alert_after_failures` consecutive bad polls (each
poll already retried every request with backoff), so a single blip never emails you. Problems:

  error     network error / timeout / HTTP error after retries
  shape     the site answered with data in an unexpected structure
  blocked   robots.txt now disallows the feed
  zero      0 jobs returned after previously returning some
  drop      job count fell by more than `drop_threshold` (e.g. 50 %)

While a problem stays open you get a reminder every `reminder_hours`; when it clears you get a
"recovered" line in the next health email.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from .config import Company, Config
from .db import DB, iso, parse_iso, utcnow


@dataclass
class Outcome:
    company: Company
    mode: str = "full"
    jobs: list | None = None
    error_kind: str | None = None
    error: str | None = None
    duration: float = 0.0
    requests: int = 0
    details_fetched: int = 0
    detail_errors: list[str] = field(default_factory=list)
    unchanged: bool = False            # source answered 304 Not Modified
    reported_total: int | None = None  # total the source reports (quick scans)
    state: dict | None = None          # checker memory to persist (validators, tokens)
    started_at: str = ""
    degraded: str | None = None        # jobs came from the checker's fallback source (see FetchContext)

    @property
    def ok(self) -> bool:
        return self.error_kind is None

    @property
    def count(self) -> int | None:
        """Job count to judge (None when it can't be known from this poll)."""
        if not self.ok or self.unchanged:
            return None
        if self.mode == "full":
            return len(self.jobs or [])
        return self.reported_total


@dataclass
class Verdict:
    healthy: bool                    # safe to trust the job list (mark removed jobs, update baseline)
    problem: dict | None = None      # alert to send now (new or reminder)
    recovered: dict | None = None    # problem that just cleared
    status: str = "ok"               # ok | error | anomaly | blocked


def _problem(c: Company, kind: str, summary: str, detail: str, since: str | None) -> dict:
    return {"key": c.key, "name": c.name, "checker": c.checker, "kind": kind, "summary": summary,
            "detail": detail, "since": since or iso(), "careers_url": (c.careers_url or [""])[0]}


def assess(cfg: Config, db: DB, o: Outcome) -> Verdict:
    c = o.company
    st = db.state(c.key)
    now = utcnow()
    h = cfg.settings.get("health", default={}) or {}
    after = int(h.get("alert_after_failures", 2))
    remind = timedelta(hours=float(h.get("reminder_hours", 24)))
    threshold = float(h.get("drop_threshold", 0.5))
    min_base = int(h.get("drop_min_baseline", 6))

    kind = summary = detail = None
    count = o.count
    if o.ok and o.degraded:
        kind, summary, detail = "shape", "part of the feed is failing (the rest is still read)", o.degraded
    elif not o.ok:
        kind = {"blocked": "blocked", "shape": "shape", "timeout": "timeout"}.get(o.error_kind or "", "error")
        summary = {"blocked": "robots.txt disallows the feed", "shape": "unexpected data shape",
                   "timeout": "timed out"}.get(o.error_kind or "", "could not fetch jobs")
        detail = o.error or ""
    elif count is not None:
        base = st["baseline_count"]
        if base and count == 0:
            kind, summary = "zero", f"returned 0 jobs (previously {base})"
            detail = "The site may have changed how it loads jobs, or every posting was taken down."
        elif base and base >= min_base and count < base * (1 - threshold):
            kind = "drop"
            summary = f"job count fell {100 * (base - count) / base:.0f}% ({base} → {count})"
            detail = "More than the allowed drop since the last healthy check."

    if kind is None:  # healthy
        verdict = Verdict(True)
        if st["alert_open"]:
            shown = f"{count} jobs" if count is not None else "feed unchanged"
            verdict.recovered = _problem(c, "recovered", f"working again ({shown})", "", st["failing_since"])
        fields = dict(consecutive_failures=0, anomaly_streak=0, failing_since=None, last_error=None,
                      last_error_kind=None, alert_open=0, last_success=iso(now))
        if count is not None:
            fields.update(baseline_count=count, last_count=count)
        if o.mode == "full" and not o.unchanged:
            fields["last_full"] = iso(now)
        db.update_state(c.key, **fields)
        return verdict

    anomaly = kind in ("zero", "drop")
    streak_field = "anomaly_streak" if anomaly else "consecutive_failures"
    streak = (st[streak_field] or 0) + 1
    since = st["failing_since"] or iso(now)
    fields = {streak_field: streak, "failing_since": since, "last_error": f"{summary}: {detail}"[:1000],
              "last_error_kind": kind}
    if anomaly:
        fields["last_count"] = count
    verdict = Verdict(False, status="anomaly" if anomaly else ("blocked" if kind == "blocked" else "error"))
    last_alert = parse_iso(st["last_alert_at"])
    if streak >= after:
        if not st["alert_open"] or (last_alert and now - last_alert >= remind):
            verdict.problem = _problem(c, kind, summary + (" (reminder: still failing)" if st["alert_open"] else ""),
                                       detail, since)
            fields.update(alert_open=1, last_alert_at=iso(now))
        if anomaly:
            # Alerted once; accept the new count as the baseline so a real shrink doesn't alert forever.
            verdict.healthy = True
            fields.update(baseline_count=count, anomaly_streak=0, last_success=iso(now))
            if o.mode == "full":
                fields["last_full"] = iso(now)
    db.update_state(c.key, **fields)
    return verdict
