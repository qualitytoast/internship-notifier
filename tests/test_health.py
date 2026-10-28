"""Health rules: alert only after retries/repeat failures, zero-after-nonzero, >50% drops, shape errors."""
from internwatch.health import Outcome, assess

from conftest import company, job


def jobs(n):
    return [job(str(i), f"Engineer {i}") for i in range(n)]


def test_single_failure_does_not_alert(make_cfg, memdb):
    c = company("acme")
    cfg = make_cfg([c])
    v = assess(cfg, memdb, Outcome(company=c, error_kind="fetch", error="HTTP 503"))
    assert not v.healthy and v.problem is None
    v = assess(cfg, memdb, Outcome(company=c, error_kind="fetch", error="HTTP 503"))
    assert v.problem and v.problem["kind"] == "error"
    # still failing: no new alert until the reminder interval
    v = assess(cfg, memdb, Outcome(company=c, error_kind="fetch", error="HTTP 503"))
    assert v.problem is None
    # recovery is reported once
    v = assess(cfg, memdb, Outcome(company=c, jobs=jobs(10)))
    assert v.healthy and v.recovered


def test_timeout_and_shape_kinds(make_cfg, memdb):
    c = company("acme")
    cfg = make_cfg([c])
    for _ in range(2):
        v = assess(cfg, memdb, Outcome(company=c, error_kind="timeout", error="time budget exhausted"))
    assert v.problem["kind"] == "timeout" and v.problem["summary"] == "timed out"
    d = company("beta")
    for _ in range(2):
        v = assess(cfg, memdb, Outcome(company=d, error_kind="shape", error="'jobs' missing"))
    assert v.problem["kind"] == "shape"


def test_zero_after_nonzero(make_cfg, memdb):
    c = company("acme")
    cfg = make_cfg([c])
    assert assess(cfg, memdb, Outcome(company=c, jobs=jobs(12))).healthy
    v = assess(cfg, memdb, Outcome(company=c, jobs=[]))
    assert not v.healthy and v.problem is None  # first anomaly: retry before alerting
    v = assess(cfg, memdb, Outcome(company=c, jobs=[]))
    assert v.problem and v.problem["kind"] == "zero"


def test_zero_on_first_ever_poll_is_not_an_anomaly(make_cfg, memdb):
    c = company("acme")
    assert assess(make_cfg([c]), memdb, Outcome(company=c, jobs=[])).healthy


def test_drop_over_half(make_cfg, memdb):
    c = company("acme")
    cfg = make_cfg([c])
    assess(cfg, memdb, Outcome(company=c, jobs=jobs(40)))
    assert assess(cfg, memdb, Outcome(company=c, jobs=jobs(25))).healthy  # 37% drop is fine
    assess(cfg, memdb, Outcome(company=c, jobs=jobs(40)))
    assess(cfg, memdb, Outcome(company=c, jobs=jobs(12)))
    v = assess(cfg, memdb, Outcome(company=c, jobs=jobs(12)))
    assert v.problem and v.problem["kind"] == "drop" and "40 → 12" in v.problem["summary"]
    # after alerting, the new size becomes the baseline (no endless alerts for a real shrink)
    assert assess(cfg, memdb, Outcome(company=c, jobs=jobs(12))).healthy


def test_quick_mode_uses_reported_total(make_cfg, memdb):
    c = company("big")
    cfg = make_cfg([c])
    assess(cfg, memdb, Outcome(company=c, jobs=jobs(100)))
    v = assess(cfg, memdb, Outcome(company=c, mode="quick", jobs=jobs(3), reported_total=98))
    assert v.healthy  # only 3 pages read, but the site still reports 98
    assess(cfg, memdb, Outcome(company=c, mode="quick", jobs=jobs(3), reported_total=10))
    v = assess(cfg, memdb, Outcome(company=c, mode="quick", jobs=jobs(3), reported_total=10))
    assert v.problem and v.problem["kind"] == "drop"


def test_unchanged_feed_is_healthy(make_cfg, memdb):
    c = company("acme")
    cfg = make_cfg([c])
    assess(cfg, memdb, Outcome(company=c, jobs=jobs(50)))
    assert assess(cfg, memdb, Outcome(company=c, unchanged=True)).healthy
    assert memdb.state("acme")["baseline_count"] == 50


def test_degraded_fallback_alerts_but_keeps_jobs(make_cfg, memdb):
    c = company("acme")
    cfg = make_cfg([c])
    for _ in range(2):
        v = assess(cfg, memdb, Outcome(company=c, jobs=jobs(5), degraded="doc_id rotated"))
    assert not v.healthy and v.problem["kind"] == "shape"


def _zero_alerted(cfg, memdb, c):
    assess(cfg, memdb, Outcome(company=c, jobs=jobs(12)))
    assess(cfg, memdb, Outcome(company=c, jobs=[]))
    v = assess(cfg, memdb, Outcome(company=c, jobs=[]))
    assert v.problem["kind"] == "zero"


def test_zero_alert_stays_open_until_jobs_come_back(make_cfg, memdb):
    c = company("acme")
    cfg = make_cfg([c])
    _zero_alerted(cfg, memdb, c)
    v = assess(cfg, memdb, Outcome(company=c, jobs=[]))  # still 0: never "working again (0 jobs)"
    assert v.healthy and v.recovered is None and v.problem is None
    memdb.update_state("acme", last_alert_at="2000-01-01T00:00:00Z")  # a day later: a reminder
    v = assess(cfg, memdb, Outcome(company=c, jobs=[]))
    assert v.problem["kind"] == "zero" and v.problem["summary"] == "still returns 0 jobs (reminder)"
    v = assess(cfg, memdb, Outcome(company=c, jobs=jobs(3)))  # jobs are back
    assert v.recovered and v.recovered["summary"] == "working again (3 jobs)"
    assert assess(cfg, memdb, Outcome(company=c, jobs=jobs(3))).recovered is None


def test_zero_alert_survives_an_error_and_an_unsent_email(make_cfg, memdb):
    c = company("acme")
    cfg = make_cfg([c])
    _zero_alerted(cfg, memdb, c)
    for _ in range(2):
        assess(cfg, memdb, Outcome(company=c, error_kind="fetch", error="HTTP 503"))
    v = assess(cfg, memdb, Outcome(company=c, jobs=[]))  # the error cleared, but the board is still empty
    assert v.recovered is None
    memdb.update_state("acme", alert_open=0, last_alert_at=None)  # what _reopen_alerts does after a failed email
    v = assess(cfg, memdb, Outcome(company=c, jobs=[]))
    assert v.problem and v.problem["summary"] == "still returns 0 jobs"
    v = assess(cfg, memdb, Outcome(company=c, mode="quick", jobs=[], unchanged=True))  # 304: no count, still 0
    assert v.recovered is None
