"""The list of open alerts (alerts.py): every alert repeats in each run's morning email until it clears or is dismissed."""
import json
import smtplib
from argparse import Namespace
from pathlib import Path

import pytest

from internwatch import alerts, cli, emails, liveness, moves
from internwatch.config import Secrets
from internwatch.db import DB, iso
from internwatch.health import Outcome, assess
from internwatch.models import FetchError
from internwatch.runner import RunOptions, Runner

from conftest import FakeChecker, company, job

DAILY = RunOptions(daily=True, retry_delay=0, crosscheck=False, send=False, scheduled_mail=False)


@pytest.fixture(autouse=True)
def quiet_daily_checks(monkeypatch):
    """No network: the run-level checks of a daily run are tested on their own."""
    monkeypatch.setattr(Runner, "online", lambda self: True)
    monkeypatch.setattr(liveness, "scan_pages", lambda *a, **kw: [])
    monkeypatch.setattr(moves, "run", lambda *a, **kw: [])


def runner(cfg, script):
    db = DB(cfg.settings.path("db"))
    return Runner(cfg, db=db, checker_fn=FakeChecker(script)), db


def mails(db, kind):
    return db.q("SELECT * FROM emails WHERE kind=? ORDER BY id", kind)


def body(row) -> str:
    return Path(row["path"]).with_suffix(".html").read_text()


def last_morning(db) -> str:
    return body(mails(db, "morning")[-1])


BASE = [job(str(i), f"Software Engineer {i}") for i in range(30)]
ERR = FetchError("HTTP 503 for GET https://acme.example.com/jobs")


def test_an_alert_repeats_in_every_morning_email_until_it_clears(make_cfg):
    cfg = make_cfg([company("acme", name="Acme")])
    r, db = runner(cfg, {"acme": [BASE, BASE, ERR, ERR, ERR, ERR, BASE, BASE]})   # a failing company is polled twice a run
    r.run(DAILY)                # seeds
    r.run(DAILY)                # healthy
    assert "Open alerts" not in last_morning(db)
    r.run(DAILY)                # two failing polls in one run: the alert
    first = last_morning(db)
    assert "Open alerts (1)" in first and "NEW Acme [error]" in first
    assert "1 open alert (1 new)" in mails(db, "morning")[-1]["subject"]
    assert len(mails(db, "health")) == 1
    r.run(DAILY)                # still failing: in the morning email again, marked new no more, no second HEALTH email
    again = last_morning(db)
    assert "Open alerts (1)" in again and "NEW" not in again and "Acme [error]" in again
    assert len(mails(db, "health")) == 1
    assert "1 open alert" in mails(db, "morning")[-1]["subject"]
    r.run(DAILY)                # jobs are read again: one "resolved" line
    fixed = last_morning(db)
    assert "Open alerts" not in fixed and "Resolved since the last run (1)" in fixed and "Acme [error]" in fixed
    r.run(DAILY)
    assert "Resolved" not in last_morning(db)
    assert len(mails(db, "health")) == 1


def test_an_alert_survives_a_missed_day_and_an_emails_only_run(make_cfg):
    cfg = make_cfg([company("acme", name="Acme")])
    r, db = runner(cfg, {"acme": [BASE, ERR, ERR]})
    r.run(DAILY)
    r.run(DAILY)
    assert alerts.for_email(db)[0]
    db.close()
    db = DB(cfg.settings.path("db"))    # days pass, nothing runs, the process is new
    r = Runner(cfg, db=db, checker_fn=FakeChecker({}))
    r.run(RunOptions(daily=True, send=False, checks=False))
    assert "Acme [error]" in last_morning(db)


def failing_smtp(monkeypatch, r, cfg):
    def boom(msg):
        raise smtplib.SMTPServerDisconnected("connection lost")
    monkeypatch.setattr(r.mailer, "_smtp_send", boom)
    monkeypatch.setattr(r.mailer, "ready", lambda: (True, ""))
    monkeypatch.setattr("internwatch.mailer.time.sleep", lambda s: None)


def test_an_alert_survives_a_failed_email(make_cfg, monkeypatch):
    cfg = make_cfg([company("acme", name="Acme")])
    r, db = runner(cfg, {"acme": [BASE, ERR, ERR, ERR, ERR]})
    send = RunOptions(daily=True, retry_delay=0, crosscheck=False, send=True, scheduled_mail=False)
    r.run(send)
    with monkeypatch.context() as m:
        failing_smtp(m, r, cfg)
        s = r.run(send)                     # every email fails
    assert s.email_errors and db.one("SELECT health_at FROM alerts")["health_at"] is None
    assert [a["kind"] for a in alerts.for_email(db)[0]] == ["error"]
    monkeypatch.setattr(r.mailer, "_smtp_send", lambda msg: None)
    monkeypatch.setattr(r.mailer, "ready", lambda: (True, ""))
    r.run(send)                             # the next run tells about it, in both emails, and the list stays one row
    assert len(db.q("SELECT * FROM alerts")) == 1
    assert mails(db, "health")[-1]["sent_at"] and "Acme [error]" in last_morning(db)
    assert db.one("SELECT health_at FROM alerts")["health_at"]


# ---------------------------------------------------------------------------------------------
# what clears each kind of alert

def problem(kind="error", key="acme", **kw):
    return {"key": key, "name": key.title(), "kind": kind, "summary": f"{kind} summary", "detail": "", "since": iso(),
            "careers_url": "https://acme.example.com", **kw}


def is_open(db) -> list:
    return [a["alert_key"] for a in db.q("SELECT * FROM alerts WHERE state='open'")]


def raised(cfg, db, p):
    liveness.ensure_schema(db)
    alerts.record(db, [p], [])
    alerts.sweep(cfg, db)
    assert is_open(db), "the problem is still there: the alert must stay"


def src(db, source="s", **kw):
    liveness._save(db, "acme", source, "label", **kw)


CASES = {
    "health": ({"id": "health:acme", "rule": "health"},
               lambda db: db.update_state("acme", consecutive_failures=2, failing_since=iso()),
               lambda db: db.update_state("acme", consecutive_failures=0, failing_since=None)),
    "zero": ({"id": "zero:acme", "rule": "zero"}, lambda db: db.set("zero_open:acme", iso()),
             lambda db: db.set("zero_open:acme", "")),
    "count": ({"id": "drop:acme", "rule": "count", "need": 15}, lambda db: db.update_state("acme", last_count=9),
              lambda db: db.update_state("acme", last_count=15)),
    "full": ({"id": "full:acme", "rule": "full"}, lambda db: db.set("full_fail:acme", "2"),
             lambda db: db.set("full_fail:acme", "0")),
    "unchecked": ({"id": "u", "rule": "unchecked"}, lambda db: db.set("unchecked_runs:acme", "2"),
                  lambda db: db.set("unchecked_runs:acme", "")),
    "source_empty": ({"id": "e", "rule": "source_empty", "source": "s"}, lambda db: src(db, empty_since=iso()),
                     lambda db: src(db, empty_since=None)),
    "source_count": ({"id": "d", "rule": "source_count", "source": "s", "need": 12}, lambda db: src(db, last_count=7),
                     lambda db: src(db, last_count=12)),
    "quiet": ({"id": "q", "rule": "quiet", "source": "s"}, lambda db: src(db, stale_since=iso()),
              lambda db: src(db, stale_since=None)),
}


@pytest.mark.parametrize("rule", CASES)
def test_an_alert_stays_open_until_its_rule_says_it_cleared(make_cfg, memdb, rule):
    item, before, after = CASES[rule]
    cfg = make_cfg([company("acme")])
    liveness.ensure_schema(memdb)
    before(memdb)
    raised(cfg, memdb, problem(alert=item))
    alerts.sweep(cfg, memdb)
    assert is_open(memdb)
    after(memdb)
    alerts.sweep(cfg, memdb)
    assert not is_open(memdb) and memdb.one("SELECT state FROM alerts")["state"] == "resolved"


def test_new_page_and_new_label_end_only_by_dismissing(make_cfg, memdb):
    cfg = make_cfg([company("acme")])
    alerts.record(memdb, [problem("new page", alerts=[{"id": "p", "rule": "manual", "summary": "a page"}]),
                          problem("new label", alerts=[{"id": "l", "rule": "manual", "summary": "a label"}])], [])
    for _ in range(3):
        alerts.sweep(cfg, memdb)
    assert sorted(is_open(memdb)) == ["l", "p"]
    alerts.dismiss(memdb, kind="new page")
    assert is_open(memdb) == ["l"]


def test_a_new_system_clears_when_configured_or_after_two_reads_without_it(make_cfg, memdb):
    gh = company("acme", checker="greenhouse", settings={"board": "acme"})
    cfg = make_cfg([gh])
    item = {"id": "m", "rule": "system_new", "item": "greenhouse:board=new", "scope": "page"}
    alerts.record(memdb, [problem("moved?", alert=item)], [])
    alerts.seen(memdb, "acme", "system_new", {"greenhouse:board=new"}, scope="page", needed=2)
    alerts.seen(memdb, "acme", "system_new", set(), scope="page", needed=2)        # gone once: could be a flip
    assert is_open(memdb)
    alerts.seen(memdb, "acme", "system_new", {"greenhouse:board=new"}, scope="page", needed=2)   # back: the count restarts
    alerts.seen(memdb, "acme", "system_new", set(), scope="page", needed=2)
    assert is_open(memdb)
    alerts.seen(memdb, "acme", "system_new", set(), scope="page", needed=2)        # two reads in a row
    assert not is_open(memdb)
    alerts.record(memdb, [problem("moved?", alert={**item, "id": "m2", "item": "greenhouse:board=acme"})], [])
    alerts.sweep(cfg, memdb)                                                       # it is the configured board
    assert not is_open(memdb)


def test_a_mentioned_system_going_quiet_clears_when_named_again_or_unconfigured(make_cfg, memdb):
    gh = company("acme", checker="greenhouse", settings={"board": "acme"})
    item = {"id": "g", "rule": "system_gone", "item": "greenhouse:board=acme", "scope": "page"}
    alerts.record(memdb, [problem("moved?", alert=item)], [])
    alerts.sweep(make_cfg([gh]), memdb)
    assert is_open(memdb)
    alerts.back(memdb, "acme", "system_gone", {"greenhouse:board=acme"}, scope="page")
    assert not is_open(memdb)
    alerts.record(memdb, [problem("moved?", alert={**item, "id": "g2"})], [])
    alerts.sweep(make_cfg([company("acme", checker="greenhouse", settings={"board": "other"})]), memdb)
    assert not is_open(memdb)


def test_a_new_site_clears_when_configured_or_gone_from_robots(make_cfg, memdb):
    two = company("acme", checker="workday", settings={"host": "h", "tenant": "t", "sites": ["Ext", "new"]})
    one = company("acme", checker="workday", settings={"host": "h", "tenant": "t", "site": "Ext"})
    item = {"id": "s", "rule": "site", "item": "new", "scope": "h"}
    alerts.record(memdb, [problem("new site", alert=item)], [])
    alerts.sweep(make_cfg([one]), memdb)
    alerts.seen(memdb, "acme", "site", {"Ext", "new"}, scope="h")
    assert is_open(memdb)
    alerts.sweep(make_cfg([two]), memdb)
    assert not is_open(memdb)
    alerts.record(memdb, [problem("new site", alert={**item, "id": "s2"})], [])
    alerts.seen(memdb, "acme", "site", {"Ext"}, scope="h")
    assert not is_open(memdb)


def test_a_posting_elsewhere_clears_when_stored_or_gone_from_where_it_was_seen(make_cfg, memdb):
    cfg = make_cfg([company("acme")])
    item = {"id": "p", "rule": "posting", "item": "7654321", "scope": "joblist"}
    alerts.record(memdb, [problem("posting elsewhere?", alert=item)], [])
    alerts.sweep(cfg, memdb)
    alerts.seen(memdb, "acme", "posting", {"7654321"}, scope="joblist")
    assert is_open(memdb)
    memdb.upsert_jobs("acme", [job("7654321", "Intern")], iso())
    alerts.sweep(cfg, memdb)
    assert not is_open(memdb)
    alerts.record(memdb, [problem("posting elsewhere?", alert={**item, "id": "p2", "item": "999999"})], [])
    alerts.seen(memdb, "acme", "posting", set(), scope="joblist")
    assert not is_open(memdb)


def simplify_row(db, key="r1", title="ML Intern", url="https://acme.example.com/jobs/4242"):
    now = iso()
    db.conn.execute("INSERT INTO simplify_rows(source, row_key, company, title, url, first_seen, last_seen, tracked_company,"
                    " status) VALUES('summer',?,?,?,?,?,?,?,'missed')", (key, "Acme", title, url, now, now, "acme"))


def miss(how="never", key="r1"):
    return {"company": "Acme", "key": "acme", "how": how, "title": "ML Intern", "url": "u", "reason": "why", "source": "summer",
            "row_key": key}


def test_a_miss_the_checker_never_saw_clears_when_stored(make_cfg, memdb):
    cfg = make_cfg([company("acme")])
    simplify_row(memdb)
    assert alerts.record(memdb, [], [miss()]) == ([], [miss()])
    alerts.sweep(cfg, memdb)
    assert is_open(memdb) == ["miss:summer:r1"]
    memdb.upsert_jobs("acme", [job("4242", "ML Intern")], iso())
    alerts.sweep(cfg, memdb)
    assert not is_open(memdb)


def test_a_miss_the_filters_rejected_clears_when_it_matches_or_closes(make_cfg, memdb):
    cfg = make_cfg([company("acme")])
    simplify_row(memdb)
    memdb.upsert_jobs("acme", [job("4242", "ML Intern")], iso())
    alerts.record(memdb, [], [miss("filtered")])
    alerts.sweep(cfg, memdb)
    assert is_open(memdb)                                              # stored, and still rejected
    memdb.conn.execute("UPDATE jobs SET matched=1 WHERE job_id='4242'")
    alerts.sweep(cfg, memdb)
    assert not is_open(memdb)
    memdb.conn.execute("UPDATE jobs SET matched=0, removed_at=?", (iso(),))
    alerts.record(memdb, [], [miss("filtered")])
    alerts.sweep(cfg, memdb)
    assert not is_open(memdb)


def test_a_miss_clears_when_its_role_closes_on_the_list(make_cfg, memdb):
    alerts.record(memdb, [], [miss()])
    alerts.seen(memdb, "acme", "miss", {"other"}, scope="summer")
    assert not is_open(memdb)


# ---------------------------------------------------------------------------------------------
# one row per thing wrong

def test_one_problem_covering_two_things_gives_two_lines_that_clear_apart(make_cfg, memdb):
    p = problem("new site", summary="two sites", alerts=[
        {"id": "s:a", "rule": "site", "item": "a", "scope": "h", "summary": "new site a"},
        {"id": "s:b", "rule": "site", "item": "b", "scope": "h", "summary": "new site b"}])
    assert alerts.record(memdb, [p], [])[0] == [p]
    assert [a["summary"] for a in alerts.for_email(memdb)[0]] == ["new site a", "new site b"]
    alerts.seen(memdb, "acme", "site", {"a"}, scope="h")
    assert [a["summary"] for a in alerts.for_email(memdb)[0]] == ["new site a"]


def test_the_same_problem_again_is_one_row_brought_up_to_date(memdb):
    a = problem(alert={"id": "health:acme", "rule": "health"})
    b = {**a, "kind": "shape", "summary": "unexpected data shape"}
    alerts.record(memdb, [a], [])
    alerts.mark_sent(memdb)
    assert alerts.record(memdb, [b], []) == ([], [])      # no second HEALTH email
    rows = memdb.q("SELECT * FROM alerts")
    assert len(rows) == 1 and (rows[0]["kind"], rows[0]["summary"]) == ("shape", "unexpected data shape")


# ---------------------------------------------------------------------------------------------
# dismissing

def test_a_dismissed_alert_stays_off_until_its_problem_clears_and_comes_back(make_cfg):
    cfg = make_cfg([company("acme", name="Acme")])
    r, db = runner(cfg, {"acme": [BASE, ERR, ERR, ERR, ERR, ERR, ERR, BASE, ERR, ERR]})
    r.run(DAILY)
    r.run(DAILY)
    assert [a["id"] for a in alerts.dismiss(db, ids=[1])] == [1]
    r.run(DAILY)
    assert "Acme [error]" not in last_morning(db) and "Resolved" not in last_morning(db)
    r.run(DAILY)                                 # still failing: raised again by nobody, and quiet
    assert "Acme [error]" not in last_morning(db)
    r.run(DAILY)                                 # it clears, with no "resolved" line for something dismissed
    assert "Resolved" not in last_morning(db)
    assert db.one("SELECT state FROM alerts WHERE id=1")["state"] == "cleared"
    r.run(DAILY)                                 # it comes back: a new alert
    assert "NEW Acme [error]" in last_morning(db)
    assert len(mails(db, "health")) == 2


def test_a_dismissed_board_drop_falling_to_zero_is_a_new_alert(make_cfg, memdb):
    c = company("acme", checker="greenhouse", settings={"boards": ["main", "campus"]})
    cfg = make_cfg([c])
    jobs = lambda n: [job(f"m{i}", "Engineer", extra={"board": "main"}) for i in range(30)] + [
        job(f"c{i}", "Intern", extra={"board": "campus"}) for i in range(n)]

    def poll(n):
        o = Outcome(company=c, jobs=jobs(n))
        problems = liveness.observe(cfg, memdb, c, o, assess(cfg, memdb, o), set())[0]
        alerts.record(memdb, problems, [])
        alerts.sweep(cfg, memdb)

    for n in (20, 3, 3):
        poll(n)
    assert [a["kind"] for a in alerts.for_email(memdb)[0]] == ["board drop"]
    alerts.dismiss(memdb, kind="board drop")
    assert alerts.for_email(memdb)[0] == []
    poll(3)
    assert alerts.for_email(memdb)[0] == []
    poll(0)
    poll(0)
    assert [a["kind"] for a in alerts.for_email(memdb)[0]] == ["board empty"]


def test_dismiss_kind_stops_a_whole_type_and_only_that_type(memdb):
    alerts.record(memdb, [problem("new job site?", key=f"c{i}", alert={"id": f"j{i}", "rule": "list_system"}) for i in range(3)]
                  + [problem(alert={"id": "health:x", "rule": "health"})], [])
    assert len(alerts.dismiss(memdb, kind="new job site?")) == 3
    assert [a["kind"] for a in alerts.for_email(memdb)[0]] == ["error"]


def test_the_commands(make_cfg, capsys):
    cfg = make_cfg([company("acme", name="Acme")])
    db = DB(cfg.settings.path("db"))
    alerts.record(db, [problem(alert={"id": "health:acme", "rule": "health"})], [])
    assert cli.cmd_alerts(cfg, Namespace()) == 0
    assert "#1" in capsys.readouterr().out
    assert cli.cmd_dismiss(cfg, Namespace(ids=[], kind=None)) == 2
    assert cli.cmd_dismiss(cfg, Namespace(ids=[99], kind=None)) == 1
    assert cli.cmd_dismiss(cfg, Namespace(ids=[1], kind=None)) == 0
    assert alerts.for_email(DB(cfg.settings.path("db")))[0] == []


# ---------------------------------------------------------------------------------------------
# drops

def test_a_drop_repeats_until_jobs_return_and_never_says_working_again(make_cfg):
    cfg = make_cfg([company("acme", name="Acme")])
    low, half = BASE[:9], BASE[:15]
    r, db = runner(cfg, {"acme": [BASE, low, low, low, low, half]})
    r.run(DAILY)
    r.run(DAILY)                                  # the drop, seen twice in one run: the alert
    assert "fell 70%" in last_morning(db)
    for _ in range(2):                            # a steady lower count: repeated, and no "recovered" anywhere
        r.run(DAILY)
        assert "fell 70%" in last_morning(db)
        assert "working again" not in last_morning(db)
    assert db.job("acme", "20")["removed_at"]     # closed postings are still recorded as closed
    assert len(mails(db, "health")) == 1
    r.run(DAILY)                                  # back at half the old count: the level where it wouldn't have fired
    text = last_morning(db)
    assert "Open alerts" not in text and "Resolved since the last run (1)" in text


# ---------------------------------------------------------------------------------------------
# the list going wrong, or getting long

def test_an_error_updating_the_list_costs_no_email(make_cfg, monkeypatch):
    cfg = make_cfg([company("acme", name="Acme")])
    r, db = runner(cfg, {"acme": [BASE, ERR, ERR]})
    r.run(DAILY)

    def boom(*a):
        raise RuntimeError("no such table")
    monkeypatch.setattr(alerts, "record", boom)
    s = r.run(DAILY)
    assert not s.email_errors and mails(db, "morning") and "Acme (error)" in mails(db, "health")[-1]["subject"]


def test_an_error_reading_the_list_says_so_in_the_email(make_cfg, monkeypatch):
    cfg = make_cfg([company("acme", name="Acme")])
    r, db = runner(cfg, {"acme": [BASE, BASE]})
    r.run(DAILY)

    def boom(*a):
        raise RuntimeError("no such table")
    monkeypatch.setattr(alerts, "for_email", boom)
    r.run(DAILY)
    assert "could not be read" in last_morning(db)


def test_a_long_list_stays_small_in_the_email(make_cfg, memdb):
    cfg = make_cfg([company("acme", name="Acme")])
    alerts.record(memdb, [problem("internships vanished", key=f"c{i}", name=f"Company {i}", alert={"id": f"a{i}", "rule": "manual"},
                                  summary="student roles fell 100% (40 → 0)") for i in range(115)], [])
    subject, text, html = emails.digest(cfg, [], [], *alerts.for_email(memdb), morning=True)
    assert "115 open alerts (115 new)" in subject and "Open alerts (115)" in html
    assert html.count("<li>") == 115 and text.count("• #") == 115
    assert len(html) < 20_000


def test_the_problems_open_before_the_list_existed_are_put_on_it(make_cfg, memdb):
    cfg = make_cfg([company("acme", name="Acme"), company("beta", name="Beta")])
    memdb.update_state("acme", alert_open=1, last_error_kind="shape", last_error="unexpected data shape: shopify",
                       failing_since=iso(), consecutive_failures=2)
    memdb.update_state("beta", alert_open=1, last_error_kind="zero", last_error="returned 0 jobs: x", failing_since=iso())
    memdb.set("zero_open:beta", iso())
    alerts.start(cfg, memdb)
    alerts.start(cfg, memdb)
    rows = alerts.for_email(memdb)[0]
    assert [(a["name"], a["kind"], a["summary"]) for a in rows] == [("Acme", "shape", "unexpected data shape"),
                                                                     ("Beta", "zero", "returned 0 jobs")]
    assert all(a["health_at"] for a in rows)  # told about before: not new
