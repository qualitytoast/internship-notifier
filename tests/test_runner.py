"""A polling run end to end, with scripted checkers: seeding, new-posting emails, health alerts, schedule."""
import json

import pytest

from internwatch.db import DB
from internwatch.models import FetchError
from internwatch.runner import RunOptions, Runner

from conftest import FakeChecker, company, job

OFFLINE_OK = RunOptions(crosscheck=False, send=False, scheduled_mail=False)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(Runner, "online", lambda self: True)


def runner(cfg, script):
    db = DB(cfg.settings.path("db"))
    return Runner(cfg, db=db, checker_fn=FakeChecker(script)), db


def emails(db, kind=None):
    rows = db.q("SELECT * FROM emails ORDER BY id")
    return [r for r in rows if kind is None or r["kind"] == kind]


BASE = [job("1", "Software Engineer Intern (Summer 2027)"), job("2", "Senior Software Engineer"),
        job("3", "Marketing Intern"), job("4", "Data Science Intern", location="London, UK")]


def test_first_run_seeds_without_flooding(make_cfg):
    cfg = make_cfg([company("acme"), company("beta")])
    r, db = runner(cfg, {"acme": [BASE], "beta": [[job("b1", "ML Intern")]]})
    s = r.run(OFFLINE_OK)
    assert sorted(s.seeded) == ["acme", "beta"] and s.new_matches == 0
    assert [e["kind"] for e in emails(db)] == ["seed"]
    seed = emails(db, "seed")[0]
    assert "2 matching roles" in seed["subject"]
    assert db.get("first_run_done")
    assert not db.unnotified_matches()


def test_new_matching_posting_is_emailed_once(make_cfg):
    cfg = make_cfg([company("acme", name="Acme")])
    new = job("5", "Machine Learning Intern, Fall 2027", location="Seattle, WA")
    r, db = runner(cfg, {"acme": [BASE, BASE + [new], BASE + [new]]})
    r.run(OFFLINE_OK)
    s = r.run(RunOptions(crosscheck=False, send=False, scheduled_mail=False, force=True))
    assert s.new_matches == 1
    mail = emails(db, "new")
    assert len(mail) == 1 and "1 new: Acme (1)" in mail[0]["subject"]
    assert db.job("acme", "5")["term"] == "Fall 2027" and json.loads(db.job("acme", "5")["tags"]) == ["ML/AI"]
    r.run(RunOptions(crosscheck=False, send=False, scheduled_mail=False, force=True))
    assert len(emails(db, "new")) == 1  # never twice


def test_non_matching_new_jobs_are_stored_not_emailed(make_cfg):
    cfg = make_cfg([company("acme")])
    r, db = runner(cfg, {"acme": [BASE, BASE + [job("9", "Account Executive")]]})
    r.run(OFFLINE_OK)
    s = r.run(RunOptions(crosscheck=False, send=False, scheduled_mail=False, force=True))
    assert s.new_jobs == 1 and s.new_matches == 0 and not emails(db, "new")
    assert db.job("acme", "9")["matched"] == 0


def test_failures_alert_after_retry_then_recover(make_cfg):
    cfg = make_cfg([company("acme")])
    err = FetchError("HTTP 503 for GET https://acme.example.com/jobs")
    r, db = runner(cfg, {"acme": [BASE, err, err, BASE]})
    force = RunOptions(crosscheck=False, send=False, scheduled_mail=False, force=True)
    r.run(OFFLINE_OK)
    assert not r.run(force).problems          # one blip: no email
    s = r.run(force)                          # still failing: alert
    assert s.problems and s.problems[0]["kind"] == "error"
    assert "[InternWatch HEALTH]" in emails(db, "health")[-1]["subject"]
    s = r.run(force)
    assert s.recovered and "recovered" in emails(db, "health")[-1]["subject"]


def test_removed_jobs_and_reposts(make_cfg):
    cfg = make_cfg([company("acme")])
    repost = job("1b", "Software Engineer Intern (Summer 2027)")
    r, db = runner(cfg, {"acme": [BASE, BASE[1:], BASE[1:] + [repost]]})
    force = RunOptions(crosscheck=False, send=False, scheduled_mail=False, force=True)
    r.run(OFFLINE_OK)
    r.run(force)
    assert db.job("acme", "1")["removed_at"]
    r.run(force)
    assert db.job("acme", "1b")["repost_of"] == "1"


def test_schedule_polls_each_company_every_30_to_60_minutes(make_cfg):
    cfg = make_cfg([company("acme")])
    r, db = runner(cfg, {"acme": [BASE]})
    r.run(OFFLINE_OK)
    assert r.due(RunOptions()) == []          # just polled
    from internwatch.db import parse_iso, utcnow
    gap = (parse_iso(db.state("acme")["next_due"]) - utcnow()).total_seconds() / 60
    assert 29 <= gap <= 46


def test_company_added_later_gets_watching_email(make_cfg):
    cfg = make_cfg([company("acme")])
    r, db = runner(cfg, {"acme": [BASE], "newco": [[job("n1", "Software Engineer Intern")]]})
    r.run(OFFLINE_OK)
    cfg.companies.append(company("newco", name="NewCo"))
    r.run(RunOptions(crosscheck=False, send=False, scheduled_mail=False, companies=["newco"]))
    w = emails(db, "watching")
    assert len(w) == 1 and "NewCo" in w[0]["subject"] and not emails(db, "new")


def test_blocked_companies_are_never_polled(make_cfg):
    blocked = company("walled", status="blocked", blocked_reason="robots.txt disallows")
    cfg = make_cfg([company("acme"), blocked])
    r, db = runner(cfg, {"acme": [BASE]})
    s = r.run(OFFLINE_OK)
    assert s.checked == 1 and "walled" not in r.checker_fn.calls


def test_digest_does_not_repeat_the_seeded_baseline(make_cfg):
    from internwatch.runner import build_digest
    cfg = make_cfg([company("acme", name="Acme")])
    new = job("7", "Data Engineer Intern", location="Austin, TX")
    r, db = runner(cfg, {"acme": [BASE, BASE + [new]]})
    r.run(OFFLINE_OK)
    assert "0 new roles" in build_digest(cfg, db)[0]
    r.run(RunOptions(crosscheck=False, send=False, scheduled_mail=False, force=True))
    assert "1 new role," in build_digest(cfg, db)[0]


DAILY = RunOptions(daily=True, retry_delay=0, crosscheck=False, send=False, scheduled_mail=False)


def test_daily_mode_sends_one_morning_email(make_cfg):
    cfg = make_cfg([company("acme", name="Acme")])
    new = job("8", "ML Engineer Intern, Summer 2027", location="Boston, MA")
    r, db = runner(cfg, {"acme": [BASE, BASE + [new], BASE + [new]]})
    r.run(DAILY)
    assert [e["kind"] for e in emails(db)] == ["seed"]
    r.run(DAILY)
    mail = emails(db, "morning")
    assert len(mail) == 1 and "1 new: Acme (1)" in mail[0]["subject"] and not emails(db, "new")
    r.run(DAILY)
    assert "no new roles" in emails(db, "morning")[-1]["subject"]   # still emailed: silence would hide breakage


def test_daily_mode_rechecks_failures_before_alerting(make_cfg):
    cfg = make_cfg([company("acme"), company("beta")])
    err = FetchError("HTTP 503")
    r, db = runner(cfg, {"acme": [BASE, err, BASE], "beta": [BASE, err, err]})
    r.run(DAILY)
    s = r.run(DAILY)
    assert [p["key"] for p in s.problems] == ["beta"]          # failed twice in the same morning: alerted
    assert db.state("acme")["consecutive_failures"] == 0       # one blip, fine on the re-check: no alert
    assert "acme" not in s.failed and "beta" in s.failed


def test_reseed_after_switching_checkers_does_not_flood(make_cfg):
    cfg = make_cfg([company("acme", name="Acme")])
    migrated = [job("gh-1", "Software Engineer Intern"), job("gh-2", "Data Science Intern")]  # same roles, new ids
    r, db = runner(cfg, {"acme": [BASE, migrated]})
    r.run(OFFLINE_OK)
    db.update_state("acme", seeded_at=None)            # what `internwatch reseed acme` does
    s = r.run(RunOptions(crosscheck=False, send=False, scheduled_mail=False, force=True))
    assert s.new_matches == 0 and s.seeded == ["acme"] and not emails(db, "new")
