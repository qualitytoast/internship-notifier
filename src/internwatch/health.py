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

A zero alert stays open until jobs come back (kv zero_open:<key>): 0 is accepted as the baseline after the alert,
so the polls that still return 0 are healthy (closed jobs are marked removed), but they never count as "recovered";
they remind you instead, and raise the alert again if the email about it could not be sent.
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
    partial: bool = False              # the walk was cut short (see FetchContext)
    source_counts: dict | None = None  # jobs per sub-listing the jobs don't name (see FetchContext, liveness.py)

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


def _problem(c: Company, kind: str, summary: str, detail: str, since: str | None,
             restore_state: dict | None = None) -> dict:
    p = {"key": c.key, "name": c.name, "checker": c.checker, "kind": kind, "summary": summary,
         "detail": detail, "since": since or iso(), "careers_url": (c.careers_url or [""])[0]}
    if restore_state:  # company_state put back if the health email fails (runner._reopen_alerts)
        p["restore_state"] = restore_state
    return p


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

    zero_since = db.get(f"zero_open:{c.key}")
    if kind is None and zero_since:
        if count == 0 or (count is None and st["last_count"] == 0):
            return _still_zero(db, c, o, st, count, zero_since, remind, now)
        db.set(f"zero_open:{c.key}", "")  # jobs are back: recovered below
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
            # a drop is accepted as the new baseline right below: if this alert's email fails, the next poll must
            # still see the drop, so the alert carries the counts to put back
            restore = {"baseline_count": st["baseline_count"], "anomaly_streak": st["anomaly_streak"],
                       "last_count": st["last_count"]} if kind == "drop" else None
            verdict.problem = _problem(c, kind, summary + (" (reminder: still failing)" if st["alert_open"] else ""),
                                       detail, since, restore)
            fields.update(alert_open=1, last_alert_at=iso(now))
        if anomaly:
            # Alerted once; accept the new count as the baseline so a real shrink doesn't alert forever.
            verdict.healthy = True
            fields.update(baseline_count=count, anomaly_streak=0, last_success=iso(now))
            if o.mode == "full":
                fields["last_full"] = iso(now)
            if kind == "zero":
                db.set(f"zero_open:{c.key}", since)  # but 0 jobs never counts as recovered (_still_zero)
    db.update_state(c.key, **fields)
    return verdict


def _still_zero(db: DB, c: Company, o: Outcome, st, count, since: str, remind: timedelta, now) -> Verdict:
    """A healthy poll of a company whose zero alert is open and that still returns 0 jobs: no "recovered" line;
    a reminder every `reminder_hours`, or at once if the alert's email did not go out (alert_open was reset)."""
    verdict = Verdict(True)
    fields = dict(consecutive_failures=0, anomaly_streak=0, last_success=iso(now))
    last_alert = parse_iso(st["last_alert_at"])
    if not st["alert_open"] or last_alert is None or now - last_alert >= remind:
        verdict.problem = _problem(c, "zero", "still returns 0 jobs" + (" (reminder)" if st["alert_open"] else ""),
                                   "The site may have changed how it loads jobs, or every posting was taken down.",
                                   since)
        fields.update(alert_open=1, last_alert_at=iso(now), last_error_kind="zero",
                      last_error="returned 0 jobs: the site may have changed how it loads jobs")
    if count is not None:
        fields.update(baseline_count=count, last_count=count)
    if o.mode == "full" and not o.unchanged:
        fields["last_full"] = iso(now)
    db.update_state(c.key, **fields)
    return verdict
