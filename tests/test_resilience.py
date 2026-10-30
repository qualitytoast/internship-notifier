"""A slow or dead source must never stop the run or the morning email: a failing list, a failing site, or the list of
alerts itself going wrong. Each case checks the run ends, the email goes out with the failure named, healthchecks.io
gets its end ping, and the next run picks up cleanly."""
import json
import time

import pytest

from internwatch import alerts, crosscheck, liveness, moves, runner as runner_mod
from internwatch.db import DB
from internwatch.heartbeat import Heartbeat
from internwatch.http import Resp
from internwatch.models import CheckTimeout, FetchError, ShapeError
from internwatch.runner import RunOptions, Runner, RunSummary

from conftest import FakeChecker, company, job

DAILY = RunOptions(daily=True, retry_delay=0, crosscheck=True, send=False, scheduled_mail=False)
BASE = [job(str(i), f"Software Engineer {i}") for i in range(10)]


class Pings(Heartbeat):
    def __init__(self):
        self.url = ""
        self.seen: list[str] = []

    def start(self):
        self.seen.append("start")

    def success(self, summary=""):
        self.seen.append("success")

    def fail(self, summary=""):
        self.seen.append(f"fail: {summary}")


class FakeListHttp:
    """Stands in for the cross-check's client: a raise, or the list's text."""
    answer: object = "[]"
    deadlines: list = []

    def __init__(self, *a, **kw):
        FakeListHttp.deadlines.append(kw.get("deadline"))

    def get(self, url, **kw):
        if isinstance(self.answer, Exception):
            raise self.answer
        return Resp(200, url, {}, self.answer.encode())

    def close(self):
        pass


ROWS = json.dumps([{"id": f"r{i}", "company_name": "Someone", "title": "Intern", "url": f"https://x.example/{i}",
                    "category": "Software", "locations": ["Austin, TX"], "active": True} for i in range(60)])


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(Runner, "online", lambda self: True)
    monkeypatch.setattr(liveness, "scan_pages", lambda *a, **kw: [])
    monkeypatch.setattr(moves, "run", lambda *a, **kw: [])
    monkeypatch.setattr(runner_mod, "Http", FakeListHttp)
    FakeListHttp.answer = ROWS


def setup(cfg, script):
    db = DB(cfg.settings.path("db"))
    pings = Pings()
    return Runner(cfg, db=db, checker_fn=FakeChecker(script), heartbeat=pings), db, pings


def morning(db) -> str:
    rows = db.q("SELECT path FROM emails WHERE kind='morning' ORDER BY id")
    return open(rows[-1]["path"].replace(".eml", ".html")).read()


@pytest.mark.parametrize("answer,named", [
    (CheckTimeout("timeout (ReadTimeout) for GET list (after 4 attempts)"), "timeout"),
    (FetchError("HTTP 500 for GET list"), "HTTP 500"),
    ('[{"id": "1", "company_name": "Tru', "JSONDecodeError"),   # a truncated file
    ('[{"id": "1"}]', "only 1 rows parsed"),                    # almost no rows
    ('{"format": "changed"}', "only 0 rows parsed"),            # valid JSON, not a list of rows
])
def test_a_failing_list_costs_no_email_and_is_named(make_cfg, answer, named):
    cfg = make_cfg([company("acme", name="Acme")])
    r, db, pings = setup(cfg, {"acme": [BASE, BASE, BASE, BASE]})
    r.run(DAILY)                         # the list answers: the baseline
    assert pings.seen == ["start", "success"]
    FakeListHttp.answer = answer
    r.run(DAILY)
    s = r.run(DAILY)                     # two failing polls of the list: the alert
    assert "SimplifyJobs cross-check" in morning(db)
    assert named in db.one("SELECT last_error FROM company_state WHERE company='_simplify'")["last_error"]
    assert pings.seen[-1] == "success" and not s.email_errors
    FakeListHttp.answer = ROWS           # and the next run picks up cleanly
    r.run(DAILY)
    assert "Open alerts" not in morning(db) and "SimplifyJobs cross-check" in morning(db)  # listed as resolved


def test_the_list_gets_a_time_limit(make_cfg):
    cfg = make_cfg([company("acme")])
    r, db, _ = setup(cfg, {"acme": [BASE]})
    FakeListHttp.deadlines = []
    r.run(DAILY)
    assert FakeListHttp.deadlines[0] is not None   # the cross-check's client is the first of the run


def test_a_crash_while_judging_the_list_costs_no_email(make_cfg, monkeypatch):
    cfg = make_cfg([company("acme", name="Acme")])
    r, db, pings = setup(cfg, {"acme": [BASE, BASE, BASE]})
    r.run(DAILY)

    def boom(self, res):
        raise RuntimeError("a bug in the cross-check")
    monkeypatch.setattr(crosscheck.CrossCheck, "resolve", boom)
    r.run(DAILY)
    r.run(DAILY)
    assert "SimplifyJobs cross-check" in morning(db) and pings.seen[-1] == "success"


@pytest.mark.parametrize("failure", [CheckTimeout("timed out (time budget)"), FetchError("HTTP 403 for GET jobs"),
                                     FetchError("HTTP 429 for GET jobs"), FetchError("HTTP 500 for GET jobs"),
                                     ShapeError("jobs missing")])
def test_a_failing_site_costs_no_email_and_is_named(make_cfg, failure):
    cfg = make_cfg([company("acme", name="Acme"), company("beta", name="Beta")])
    r, db, pings = setup(cfg, {"acme": [BASE, failure, failure, BASE], "beta": [BASE, BASE, BASE]})
    r.run(DAILY)
    r.run(DAILY)
    assert "Acme [" in morning(db) and pings.seen[-1] == "success"
    assert db.state("beta")["last_success"]        # the others were read
    r.run(DAILY)
    assert "Open alerts" not in morning(db)


def test_every_late_check_failing_at_once_costs_no_email(make_cfg, monkeypatch):
    def boom(*a, **kw):
        raise TimeoutError("everything is slow")
    monkeypatch.setattr(liveness, "scan_pages", boom)
    monkeypatch.setattr(liveness, "scan_workday_sites", boom)
    monkeypatch.setattr(moves, "run", boom)
    monkeypatch.setattr(alerts, "record", boom)
    FakeListHttp.answer = FetchError("HTTP 500 for GET list")
    cfg = make_cfg([company("acme", name="Acme")])
    r, db, pings = setup(cfg, {"acme": [BASE, FetchError("HTTP 503"), FetchError("HTTP 503")]})
    r.run(DAILY)
    s = r.run(DAILY)
    assert s.checked and not s.email_errors and pings.seen[-1] == "success"
    assert len(db.q("SELECT * FROM emails WHERE kind='morning'")) == 1 and db.q("SELECT * FROM emails WHERE kind='health'")


def test_the_late_checks_are_skipped_once_the_run_is_out_of_time(make_cfg, monkeypatch):
    """The run's limit is what keeps the email on time: nothing slow starts in its last five minutes."""
    pages, budgets = [], []
    monkeypatch.setattr(liveness, "scan_pages", lambda *a, **kw: pages.append(1) or [])
    monkeypatch.setattr(moves, "run", lambda cfg, db, gate, http, budget_end, healthy: budgets.append(budget_end) or [])
    cfg = make_cfg([company("acme")])
    r, db, _ = setup(cfg, {"acme": [BASE]})
    r._liveness_finish([], DAILY, RunSummary(), time.monotonic() + 100)     # under five minutes left
    assert pages == [] and budgets[0] < time.monotonic()                    # moves.py's checks won't start a read
    r._liveness_finish([], DAILY, RunSummary(), time.monotonic() + 3000)
    assert pages == [1] and budgets[1] > time.monotonic()
