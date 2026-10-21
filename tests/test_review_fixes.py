"""Regression tests for the failure paths found in code review: undelivered emails, robots.txt outages,
duplicate notifications, multi-source baselines, and email size limits."""
import httpx
import pytest

from internwatch import emails
from internwatch.adapters.base import FetchContext
from internwatch.checkers.multi import Multi
from internwatch.config import Secrets
from internwatch.db import DB, iso
from internwatch.http import HostGate, Http, HttpSettings
from internwatch.mailer import Mailer
from internwatch.models import FetchError, Job, RobotsBlocked
from internwatch.runner import RunOptions, Runner

from conftest import FakeChecker, company, job

SEND = RunOptions(crosscheck=False, send=True, scheduled_mail=False)


@pytest.fixture(autouse=True)
def online(monkeypatch):
    monkeypatch.setattr(Runner, "online", lambda self: True)


class BrokenSmtp(Mailer):
    """Credentials configured, but every send fails (e.g. a revoked app password)."""

    def _smtp_send(self, msg):
        raise OSError("535 bad credentials")


def broken_runner(cfg, script):
    cfg.secrets = Secrets(smtp_user="me@example.com", smtp_password="app-password")
    db = DB(cfg.settings.path("db"))
    return Runner(cfg, db=db, mailer=BrokenSmtp(cfg, db), checker_fn=FakeChecker(script)), db


def test_undelivered_first_run_summary_is_retried_and_blocks_nothing(make_cfg, monkeypatch):
    monkeypatch.setattr("internwatch.mailer.time.sleep", lambda s: None)
    cfg = make_cfg([company("acme")])
    r, db = broken_runner(cfg, {"acme": [[job("1", "Software Engineer Intern")]]})
    s = r.run(SEND)
    assert db.get("first_run_done") and db.get("seed_email_pending") == "1"
    assert s.email_errors  # reported (the heartbeat turns this into a healthchecks.io failure)
    r.mailer = Mailer(cfg, db)
    monkeypatch.setattr(Mailer, "_smtp_send", lambda self, msg: None)
    r.run(RunOptions(crosscheck=False, send=True, scheduled_mail=False, force=True))
    assert db.get("seed_email_pending") == ""
    kinds = [e["kind"] for e in db.q("SELECT kind FROM emails WHERE sent_at IS NOT NULL")]
    assert kinds.count("seed") == 1


def test_undelivered_health_alert_is_raised_again(make_cfg, monkeypatch):
    monkeypatch.setattr("internwatch.mailer.time.sleep", lambda s: None)
    cfg = make_cfg([company("acme")])
    err = FetchError("HTTP 503")
    r, db = broken_runner(cfg, {"acme": [[job("1", "SWE")], err, err, err]})
    force = RunOptions(crosscheck=False, send=True, scheduled_mail=False, force=True)
    r.run(SEND)
    r.run(force)
    s = r.run(force)                       # alert due, but the email fails
    assert s.problems and db.state("acme")["alert_open"] == 0
    s = r.run(force)                       # so the next run alerts again instead of staying silent
    assert s.problems


def test_robots_unreachable_is_a_temporary_error_not_a_block():
    calls = {"robots": 0}

    def handler(req):
        if req.url.path == "/robots.txt":
            calls["robots"] += 1
            return httpx.Response(503)
        return httpx.Response(200, text="ok")

    h = Http(HttpSettings(retries=0, backoff_base=0, min_interval=0), gate=HostGate())
    h._client = httpx.Client(transport=httpx.MockTransport(handler))
    for _ in range(2):
        with pytest.raises(FetchError) as e:
            h.get("https://x.test/jobs")
        assert not isinstance(e.value, RobotsBlocked)
    assert calls["robots"] == 2  # not cached: the next poll asks again


def test_role_first_seen_via_simplify_is_not_emailed_twice(make_cfg):
    cfg = make_cfg([company("acme")])
    db = DB(cfg.settings.path("db"))
    from internwatch.filters import evaluate
    j = Job(id="simplify:abc", title="Software Engineer Intern", location="Austin, TX", url="https://x/1")
    db.add_external_job("acme", j, iso(), evaluate(j, cfg.rules), source="simplify")
    db.conn.execute("UPDATE jobs SET notified_at=? WHERE job_id='simplify:abc'", (iso(),))
    db.update_state("acme", seeded_at=iso())
    r = Runner(cfg, db=db, checker_fn=FakeChecker({"acme": [[job("77", "Software Engineer Intern", "Austin, TX")]]}))
    s = r.run(RunOptions(crosscheck=False, send=False, scheduled_mail=False, force=True))
    assert s.new_matches == 0 and db.job("acme", "77")["repost_of"] == "simplify:abc"
    assert db.job("acme", "simplify:abc")["removed_at"]


class _Src:
    def __init__(self, jobs=None, fail=False):
        self.jobs, self.fail = jobs or [], fail
        self.type = "fake"
        self.supports_detail = False

    def fetch(self, http, s, ctx=None):
        if self.fail:
            raise FetchError("down")
        return [Job(id=j.id, title=j.title) for j in self.jobs]


def test_multi_source_that_recovers_reports_its_backlog_as_baseline(monkeypatch):
    srcs = [_Src([job("a", "A")]), _Src(fail=True)]
    monkeypatch.setattr(Multi, "_sources", lambda self, s: [(i, x, {}) for i, x in enumerate(srcs)])
    ctx = FetchContext()
    jobs = Multi().fetch(None, {}, ctx)
    assert [j.id for j in jobs] == ["a"] and ctx.degraded and len(ctx.state["ok_source_ids"]) == 1
    srcs[1] = _Src([job("b", "B")])
    ctx2 = FetchContext(state=ctx.state)
    jobs = Multi().fetch(None, {}, ctx2)
    b = next(j for j in jobs if j.id == "fake:b")
    assert b.extra.get("baseline") and not ctx2.degraded


def test_multi_source_skips_a_later_sources_title_duplicate(monkeypatch):
    srcs = [_Src([job("w1", "Co-op, Delivery - Projects (LCS)"), job("w2", "Software Engineer Intern - Summer 2027")]),
            _Src([job("r1", "Co-Op, Delivery - Projects"),                       # the same role, title without "(LCS)"
                  job("r2", "Co-op, Embedded Software Engineer (Spring or Fall 2027)"),
                  job("r3", "Software Engineer Intern - Summer 2028")])]         # a term outside brackets still counts
    monkeypatch.setattr(Multi, "_sources", lambda self, s: [(i, x, {}) for i, x in enumerate(srcs)])
    jobs = Multi().fetch(None, {"dedupe_titles": True}, FetchContext())
    assert [j.id for j in jobs] == ["w1", "w2", "fake:r2", "fake:r3"]


def test_long_lists_are_attached_not_clipped(make_cfg):
    cfg = make_cfg([company("acme", name="Acme")])
    rows = [{"company": "acme", "job_id": str(i), "title": f"SWE Intern {i}", "location": "NY", "url": f"https://x/{i}",
             "term": "Summer 2027", "posted": None, "tags": '["SWE"]', "reasons": "[]", "unsure": i % 2,
             "repost_of": None, "source": "checker", "first_seen": iso()} for i in range(300)]
    built = emails.seed_summary(cfg, rows, 1, [])
    assert len(built) == 4 and {n for n, _, _ in built[3]} == {"matching-roles.html", "matching-roles.csv"}
    assert len(built[2]) < 100_000 and "SWE Intern 299" in built[3][1][1].decode()
    assert len(emails.new_postings(cfg, rows[:3])) == 3


def test_interrupted_processing_leaves_nothing_half_saved(make_cfg, monkeypatch):
    import internwatch.runner as runner_mod
    cfg = make_cfg([company("acme", name="Acme")])
    db = DB(cfg.settings.path("db"))
    base = [job("1", "Software Engineer Intern")]
    new = job("2", "Data Science Intern, Summer 2027")
    r = Runner(cfg, db=db, checker_fn=FakeChecker({"acme": [base, base + [new], base + [new]]}))
    force = RunOptions(crosscheck=False, send=False, scheduled_mail=False, force=True)
    r.run(force)
    real = runner_mod.evaluate
    monkeypatch.setattr(runner_mod, "evaluate", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        r.run(force)                                     # Ctrl-C while acme's new job is being filtered
    assert db.job("acme", "2") is None                  # nothing half-saved
    monkeypatch.setattr(runner_mod, "evaluate", real)
    s = r.run(force)
    assert s.new_matches == 1 and db.job("acme", "2")["notified_at"]   # picked up and emailed next run


def test_edited_posting_is_judged_again_and_never_loses_a_match(make_cfg):
    cfg = make_cfg([company("acme", name="Acme")])
    db = DB(cfg.settings.path("db"))
    swe, old = job("1", "Software Engineer Intern"), job("2", "Quant Research Intern - Summer 2026")
    r = Runner(cfg, db=db, checker_fn=FakeChecker({"acme": [
        [swe], [swe, old],
        [job("1", "Marketing Intern"), job("2", "Quant Research Intern - Summer 2027")]]}))  # both retitled
    force = RunOptions(crosscheck=False, send=False, scheduled_mail=False, force=True)
    r.run(force)                                    # seeds Acme
    r.run(force)                                    # job 2 appears for Summer 2026: rejected
    assert not db.job("acme", "2")["matched"]
    s = r.run(force)                                # the company edits it to Summer 2027
    assert s.new_matches == 1 and db.job("acme", "2")["matched"] and db.job("acme", "2")["notified_at"]
    assert db.job("acme", "1")["matched"]           # an edit never takes back a match


def test_edit_judged_with_the_known_location_not_the_listings_placeholder(make_cfg):
    cfg = make_cfg([company("acme", name="Acme")])
    db = DB(cfg.settings.path("db"))
    seed = job("0", "Data Analyst")
    r = Runner(cfg, db=db, checker_fn=FakeChecker({"acme": [
        [seed], [seed, job("2", "Software Engineer Intern - Summer 2026", location="London, UK")],
        [seed, job("2", "Software Engineer Intern - Summer 2027", location="3 Locations")]]}))
    force = RunOptions(crosscheck=False, send=False, scheduled_mail=False, force=True)
    r.run(force)
    r.run(force)
    s = r.run(force)                                # retitled, but still London: not one of your US roles
    assert s.new_matches == 0 and not db.job("acme", "2")["matched"]


@pytest.mark.parametrize("notify", [True, False])
def test_refilter_notify_emails_seeded_roles_that_match_after_a_filter_fix(make_cfg, notify):
    from argparse import Namespace
    from internwatch import cli
    cfg = make_cfg([company("acme", name="Acme")])
    db = DB(cfg.settings.path("db"))
    db.upsert_jobs("acme", [job("1", "2027 Applied Science Internship - United States, PhD Student Science Recruiting")], iso())
    # open when Acme was first seeded (so recorded as notified) and rejected by the old rules: in no email yet
    db.conn.execute("UPDATE jobs SET matched=0, notified_at=?, baseline=1 WHERE job_id='1'", (iso(),))
    cli.cmd_refilter(cfg, Namespace(notify=notify))
    assert db.job("acme", "1")["matched"] == 1
    assert [r["job_id"] for r in db.unnotified_matches()] == (["1"] if notify else [])


def test_refilter_never_takes_back_a_match(make_cfg, capsys):
    from argparse import Namespace
    from internwatch import cli
    cfg = make_cfg([company("acme", name="Acme")])
    db = DB(cfg.settings.path("db"))
    db.upsert_jobs("acme", [job("1", "Marketing Intern")], iso())      # matched under some earlier, looser rules
    db.conn.execute("UPDATE jobs SET matched=1, notified_at=NULL WHERE job_id='1'")
    cli.cmd_refilter(cfg, Namespace(notify=True))
    assert db.job("acme", "1")["matched"] == 1 and [r["job_id"] for r in db.unnotified_matches()] == ["1"]
    assert "1 existing matches the current filters would reject were kept" in capsys.readouterr().out


def test_emails_only_delivers_what_failed_without_checking(make_cfg, monkeypatch):
    monkeypatch.setattr("internwatch.mailer.time.sleep", lambda s: None)
    cfg = make_cfg([company("acme", name="Acme")])
    new = job("9", "Software Engineer Intern, Summer 2027", location="Austin, TX")
    r, db = broken_runner(cfg, {"acme": [[job("1", "Data Science Intern")], [job("1", "Data Science Intern"), new]]})
    daily = RunOptions(daily=True, retry_delay=0, crosscheck=False, send=True, scheduled_mail=False)
    r.run(daily)                                   # first run: summary fails to send
    r.run(daily)                                   # a new role: the morning email fails too
    assert db.get("seed_email_pending") == "1" and db.unnotified_matches()
    monkeypatch.setattr(Mailer, "_smtp_send", lambda self, msg: None)
    r.mailer = Mailer(cfg, db)
    calls = dict(r.checker_fn.calls)
    r.run(RunOptions(daily=True, send=True, checks=False))
    assert r.checker_fn.calls == calls             # no site was checked
    sent = [e["kind"] for e in db.q("SELECT kind FROM emails WHERE sent_at IS NOT NULL")]
    assert sent == ["seed", "morning"] and not db.unnotified_matches() and db.get("seed_email_pending") == ""
