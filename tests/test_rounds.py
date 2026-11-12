"""Rounds: companies added later (round: added) are checked after the original ones' whole run, with their own config
view, cross-check and list check, and nothing about the original companies' run changes."""
import email.message
import json

import pytest

from internwatch import alerts, liveness, moves, watch
from internwatch.crosscheck import ADOPTED, CompanyIndex, CrossCheck, Result, backfill_shown
from internwatch.db import DB, iso
from internwatch.runner import RunOptions, Runner, RunSummary

from conftest import FakeChecker, company, job

DAILY = RunOptions(daily=True, retry_delay=0, crosscheck=False, send=False, scheduled_mail=False)
LATER = {"liveness": {"blocked": ["acme", "newco"], "job_lists": {"acme": {"url": "https://a/s.xml"},
                                                                    "newco": {"url": "https://n/s.xml"}},
                      "watch_boards": [{"company": "acme", "checker": "fake"}, {"company": "newco", "checker": "fake"}]},
         "schedule": {"rounds": {"added": {"workers": 12, "run_timeout_minutes": 40, "page_scan_seconds": 60}}}}


@pytest.fixture
def online(monkeypatch):
    monkeypatch.setattr(Runner, "online", lambda self: True)


def two_rounds(make_cfg, **kw):
    return make_cfg([company("acme"), company("newco", round="added", **kw)], **LATER)


def row(db, key, company_name, url, status="untracked", first_seen="2026-11-01T00:00:00Z", tracked=None, **kw):
    db.conn.execute("INSERT INTO simplify_rows(source, row_key, company, title, location, url, category, first_seen,"
                    " last_seen, tracked_company, status, digest_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (kw.get("source", "summer"), key, company_name, kw.get("title", "Software Engineer Intern"),
                     "New York, NY", url, "Software Engineering", first_seen, first_seen, tracked, status,
                     kw.get("digest_at")))


def test_with_no_added_company_the_first_round_is_the_config_itself(make_cfg):
    cfg = make_cfg([company("acme"), company("beta")])
    assert cfg.rounds == [""] and cfg.scoped("") is cfg


def test_each_round_sees_only_its_companies_and_their_settings(make_cfg):
    cfg = two_rounds(make_cfg)
    first, later = cfg.scoped(""), cfg.scoped("added")
    assert cfg.rounds == ["", "added"]
    assert [c.key for c in first.companies] == ["acme"] and [c.key for c in later.companies] == ["newco"]
    lv1, lv2 = first.settings["liveness"], later.settings["liveness"]
    assert lv1["blocked"] == ["acme"] and lv2["blocked"] == ["newco"]
    assert list(lv1["job_lists"]) == ["acme"] and list(lv2["job_lists"]) == ["newco"]
    assert [b["company"] for b in lv1["watch_boards"]] == ["acme"] and [b["company"] for b in lv2["watch_boards"]] == ["newco"]
    assert first.settings["schedule"]["workers"] == 8 and later.settings["schedule"]["workers"] == 12
    assert later.settings["schedule"]["run_timeout_minutes"] == 40 and lv2["page_scan_seconds"] == 60
    assert lv1["page_scan_seconds"] == cfg.settings["liveness"]["page_scan_seconds"]


def test_the_first_round_keeps_settings_of_companies_it_doesnt_know(make_cfg):
    cfg = make_cfg([company("acme"), company("newco", round="added")],
                   liveness={"blocked": ["acme", "newco", "gone"]})
    assert cfg.scoped("").settings["liveness"]["blocked"] == ["acme", "gone"]


def test_a_later_round_runs_after_the_first_rounds_whole_run(make_cfg, monkeypatch, online):
    cfg = two_rounds(make_cfg)
    order = []
    monkeypatch.setattr(liveness, "scan_pages", lambda c, *a, **kw: order.append(("pages", [x.key for x in c.active])) or [])
    monkeypatch.setattr(moves, "run", lambda c, *a, **kw: order.append(("moves", [x.key for x in c.active], a[5:])) or [])
    monkeypatch.setattr(watch, "run", lambda c, *a, **kw: order.append(("watch", [x.key for x in c.active])) or [])
    checker = FakeChecker({"acme": [[job("1", "Software Engineer Intern (Summer 2027)")]],
                           "newco": [[job("2", "Software Engineer Intern (Summer 2027)")]]})

    def logged(cfg_, c, **kw):
        order.append(c.key)
        return checker(cfg_, c, **kw)
    r = Runner(cfg, db=DB(cfg.settings.path("db")), checker_fn=logged)
    s = r.run(DAILY)
    assert order[:4] == ["acme", ("pages", ["acme"]), ("moves", ["acme"], ()), ("watch", ["acme"])]
    assert order[4] == "newco" and order[5:7] == [("pages", ["newco"]), ("moves", ["newco"], ("added", cfg))]
    assert sorted(s.seeded) == ["acme", "newco"] and r.cfg is cfg


def test_the_first_rounds_alerts_keep_their_numbers(make_cfg):
    cfg = two_rounds(make_cfg)
    db = DB(cfg.settings.path("db"))
    liveness.ensure_schema(db)

    def problem(key):
        return {"key": key, "name": key.title(), "kind": "error", "summary": "e", "detail": "", "since": iso(),
                "careers_url": f"https://{key}.example.com"}

    def miss(key):
        return {"company": key.title(), "key": key, "how": "never", "title": "SWE Intern", "url": f"https://{key}/1",
                "reason": "r", "source": "summer", "row_key": f"{key}-1"}
    s = RunSummary(problems=[problem("acme")], misses=[miss("acme")])
    s.later.append(([problem("newco")], [miss("newco")]))
    Runner(cfg, db=db)._update_alerts(s)
    by_id = [(a["id"], a["company"]) for a in db.q("SELECT * FROM alerts ORDER BY id")]
    assert by_id == [(1, "acme"), (2, "acme"), (3, "newco"), (4, "newco")]


def test_the_first_rounds_cross_check_leaves_a_later_rounds_rows_alone(make_cfg, memdb):
    cfg = two_rounds(make_cfg)
    row(memdb, "r1", "Newco", "https://newco.example.com/jobs/1", status="pending", tracked="newco")
    CrossCheck(cfg.scoped(""), memdb, others={"newco"}).resolve(Result())
    assert memdb.one("SELECT status FROM simplify_rows")["status"] == "pending"


def test_a_later_round_adopts_its_rows_and_never_emails_the_old_ones(make_cfg, memdb):
    cfg = two_rounds(make_cfg, status="blocked")
    later = cfg.scoped("added")
    row(memdb, "old", "Newco", "https://newco.example.com/jobs/1")                                   # before go-live
    row(memdb, "new", "Newco", "https://newco.example.com/jobs/2", first_seen="2026-11-12T08:00:00Z")  # after it
    row(memdb, "closed", "Newco", "https://newco.example.com/jobs/3")
    row(memdb, "first", "Newco", "https://newco.example.com/jobs/4", status="baseline")
    row(memdb, "theirs", "Acme", "https://acme.example.com/jobs/9")                                   # the first round's
    cc = CrossCheck(later, memdb, others={"acme"})
    n = cc.adopt(CompanyIndex(cfg.companies), {"summer": {"old", "new", "theirs"}}, {"newco": "2026-11-10T00:00:00Z"})
    got = {r["row_key"]: (r["tracked_company"], r["status"], r["note"]) for r in memdb.q("SELECT * FROM simplify_rows")}
    assert n == 4
    assert got["old"] == ("newco", "pending", ADOPTED) and got["new"] == ("newco", "pending", "")
    assert got["closed"][:2] == ("newco", "baseline") and got["first"][:2] == ("newco", "baseline")
    assert got["theirs"][:2] == (None, "untracked")
    res = cc.resolve(Result())
    after = {r["row_key"]: r["status"] for r in memdb.q("SELECT * FROM simplify_rows")}
    assert after["old"] == "seen" and after["new"] == "via_simplify" and res.via_simplify == 1
    assert [j["job_id"] for j in memdb.q("SELECT job_id FROM jobs")] == ["simplify:new"]


def test_an_adopted_row_of_a_failing_company_waits_for_a_healthy_poll(make_cfg, memdb):
    cfg = two_rounds(make_cfg)
    memdb.update_state("newco", consecutive_failures=1)
    row(memdb, "old", "Newco", "https://newco.example.com/jobs/1", status="pending", tracked="newco")
    memdb.conn.execute("UPDATE simplify_rows SET note=?", (ADOPTED,))
    CrossCheck(cfg.scoped("added"), memdb, others={"acme"}).resolve(Result())
    assert memdb.one("SELECT status FROM simplify_rows")["status"] == "pending"
    assert memdb.q("SELECT * FROM jobs") == []


def test_a_row_an_email_listed_counts_as_old_whenever_it_is_adopted(make_cfg, memdb):
    cfg = two_rounds(make_cfg)
    row(memdb, "shown", "Newco", "https://newco.example.com/jobs/1", first_seen="2026-11-12T08:00:00Z",
        digest_at="2026-11-12T13:00:00Z")
    CrossCheck(cfg.scoped("added"), memdb).adopt(CompanyIndex(cfg.companies), {"summer": {"shown"}},
                                                 {"newco": "2026-11-10T00:00:00Z"})
    assert memdb.one("SELECT note FROM simplify_rows")["note"] == ADOPTED


def test_rows_of_a_source_with_unknown_open_rows_wait(make_cfg, memdb):
    cfg = two_rounds(make_cfg)
    row(memdb, "r", "Newco", "https://newco.example.com/jobs/1")
    assert CrossCheck(cfg.scoped("added"), memdb).adopt(CompanyIndex(cfg.companies), {}, {}) == 0


def test_a_row_of_a_source_no_longer_read_is_adopted_by_its_key_in_todays_lists(make_cfg, memdb):
    cfg = two_rounds(make_cfg)  # the Off-Season README's rows, stored before listings.json held both lists
    row(memdb, "open", "Newco", "https://newco.example.com/jobs/1", source="offseason")
    row(memdb, "closed", "Newco", "https://newco.example.com/jobs/2", source="offseason")
    cc, golive = CrossCheck(cfg.scoped("added"), memdb), {"newco": "2026-11-10T00:00:00Z"}
    assert cc.adopt(CompanyIndex(cfg.companies), {}, golive) == 0  # today's open rows unknown: they wait
    assert cc.adopt(CompanyIndex(cfg.companies), {"summer": {"open"}}, golive) == 2
    assert {r["row_key"]: (r["status"], r["note"]) for r in memdb.q("SELECT * FROM simplify_rows")} == {
        "open": ("pending", ADOPTED), "closed": ("baseline", None)}


def test_a_later_round_reads_the_postings_its_rows_link_on_the_first_morning(make_cfg, monkeypatch, online):
    newco = company("newco", checker="ashby", round="added", settings={"board": "newco", "learn_ids": True})
    cfg = make_cfg([company("acme"), newco], **LATER)
    for mod in (moves, watch):
        monkeypatch.setattr(mod, "run", lambda *a, **kw: [])
    monkeypatch.setattr(liveness, "scan_pages", lambda *a, **kw: [])
    monkeypatch.setattr(CrossCheck, "fetch_and_store", lambda self, http: Result(open_keys={"summer": {"u"}}))
    db = DB(cfg.settings.path("db"))
    db.set("simplify_baselined:summer", "2026-11-01T00:00:00Z")  # the row below is in the latest download
    row(db, "u", "Newco", "https://jobs.ashbyhq.com/newco/0a1b2c3d-1111-2222-3333-444455556666")
    fake, asked = FakeChecker({"acme": [[]], "newco": [[]]}), {}

    def checker(cfg_, c, **kw):
        asked[c.key] = (c.settings or {}).get("watch_ids")
        return fake(cfg_, c, **kw)
    Runner(cfg, db=db, checker_fn=checker).run(RunOptions(daily=True, retry_delay=0, send=False, scheduled_mail=False))
    assert asked == {"acme": None, "newco": ["0a1b2c3d-1111-2222-3333-444455556666"]}  # a posting the board may leave out
    assert db.one("SELECT tracked_company, note FROM simplify_rows")["tracked_company"] == "newco"


def test_now_watching_leaves_out_roles_already_shown_and_is_sent_again(make_cfg, monkeypatch, online):
    cfg = two_rounds(make_cfg)
    monkeypatch.setattr(liveness, "scan_pages", lambda *a, **kw: [])
    monkeypatch.setattr(moves, "run", lambda *a, **kw: [])
    monkeypatch.setattr(watch, "run", lambda *a, **kw: [])
    db = DB(cfg.settings.path("db"))
    r = Runner(cfg, db=db, checker_fn=FakeChecker({
        "acme": [[job("1", "Software Engineer Intern (Summer 2027)")]],
        "newco": [[job("7", "Software Engineer Intern (Summer 2027)"), job("8", "Data Science Intern (Summer 2027)")]]}))
    r.run(DAILY)  # the first run: both are seeded, one summary
    sent = []
    monkeypatch.setattr(r.mailer, "send", lambda kind, subject, *a, **kw: sent.append((kind, subject)) or
                        (kind != "watching", "SMTP down", None))
    monkeypatch.setattr(r.mailer, "ready", lambda: (True, ""))
    db.update_state("newco", seeded_at=None)  # newco is read for the first time again: "Now watching"
    row(db, "s", "Newco", "https://jobs.example.com/8", tracked="newco", status="found", digest_at=iso(),
        title="Data Science Intern (Summer 2027)")
    r.run(RunOptions(daily=True, retry_delay=0, crosscheck=False, send=True, scheduled_mail=False))
    assert json.loads(db.get("watching_pending")) == ["newco"]
    watching = [s for k, s in sent if k == "watching"]
    assert watching and "1 matching role open" in watching[0]
    monkeypatch.setattr(r.mailer, "send", lambda kind, subject, *a, **kw: sent.append((kind, subject)) or (True, "", None))
    r.run(RunOptions(daily=True, retry_delay=0, crosscheck=False, send=True, scheduled_mail=False))
    assert [s for k, s in sent if k == "watching"][-1] == watching[0] and db.get("watching_pending") == ""


def test_a_later_rounds_list_check_reads_the_kept_lists_for_its_companies_only(make_cfg, memdb):
    cfg = make_cfg([company("acme", checker="greenhouse", settings={"board": "acme"}),
                    company("newco", checker="greenhouse", settings={"board": "newco"}, round="added")],
                   liveness={"blocked": ["acme", "newco"]})
    rows = [{"company": "Newco", "title": "SWE Intern", "url": "https://jobs.ashbyhq.com/newco/1"},
            {"company": "Acme", "title": "SWE Intern", "url": "https://jobs.lever.co/acme/1"}]
    for src in cfg.settings["liveness"]["listings"]:  # every list kept by the first round; one with the rows
        moves.keep_list(cfg, src["name"], json.dumps(rows) if src["name"] == "boardsweep" else "[]")
    ctx = moves.Ctx(cfg.scoped("added"), memdb, None, None, float("inf"), set())
    problems = moves.check_listings_later(ctx, "added", cfg)
    assert [p["key"] for p in problems] == ["newco"] and "ashby:board=newco" in problems[0]["summary"]
    assert memdb.get("lists:alerted") is None and json.loads(memdb.get("lists:added:alerted")) == ["newco|ashby:board=newco"]
    assert moves.check_listings_later(ctx, "added", cfg) == []  # told once


def test_emails_mark_the_untracked_rows_they_list(make_cfg, memdb):
    cfg = make_cfg([company("acme")])
    row(memdb, "u", "Somebody", "https://somebody.example.com/1", first_seen=iso())
    from internwatch.runner import build_digest
    shown = []
    build_digest(cfg, memdb, rows=[], shown=shown)
    assert [r["row_key"] for r in shown] == ["u"]
    Runner(cfg, db=memdb)._mark_shown(shown, "2026-11-12T13:00:00Z")
    assert memdb.one("SELECT digest_at FROM simplify_rows")["digest_at"] == "2026-11-12T13:00:00Z"


def test_earlier_emails_are_read_back_from_the_outbox(tmp_path, memdb):
    row(memdb, "a", "Somebody", "https://somebody.example.com/1")
    row(memdb, "b", "Other", "https://other.example.com/2?x=1&y=2")
    row(memdb, "c", "Never", "https://never.example.com/3")
    msg = email.message.EmailMessage()
    msg.set_content("text")
    msg.add_alternative('<h3>Untracked companies on the SimplifyJobs lists (2)</h3><table><tr><td>'
                        '<a href="https://other.example.com/2?x=1&amp;y=2">x</a></td></tr></table>', subtype="html")
    msg.add_attachment(b"company,title,location,category,url\nSomebody,SWE,NY,SWE,https://somebody.example.com/1\n",
                       maintype="text", subtype="csv", filename="untracked-roles.csv")
    (tmp_path / "20261105-091500-morning.eml").write_bytes(bytes(msg))
    assert backfill_shown(memdb, tmp_path) == 2
    got = {r["row_key"]: r["digest_at"] for r in memdb.q("SELECT * FROM simplify_rows")}
    assert got["a"] and got["a"] == got["b"] and got["c"] is None


def test_a_later_round_downloads_a_list_once_when_no_copy_is_kept(make_cfg, memdb):
    cfg = make_cfg([company("acme"), company("newco", checker="greenhouse", settings={"board": "newco"}, round="added")],
                   liveness={"blocked": ["acme", "newco"]})
    rows = [{"company": "Newco", "title": "SWE Intern", "url": "https://jobs.ashbyhq.com/newco/1"}]
    asked = []

    class Http:
        def get(self, url, **kw):
            asked.append(url)
            return type("R", (), {"text": json.dumps(rows) if "Boardsweep" in url else "[]"})()

        def close(self):
            pass
    ctx = moves.Ctx(cfg.scoped("added"), memdb, None, lambda *a, **kw: Http(), float("inf"), set())
    problems = moves.check_listings_later(ctx, "added", cfg)
    assert [p["key"] for p in problems] == ["newco"]
    assert len(asked) == len(cfg.settings["liveness"]["listings"])                   # each list once …
    assert (moves.kept_lists(cfg) / "boardsweep.txt").exists()
    moves.check_listings_later(ctx, "added", cfg)
    assert len(asked) == len(cfg.settings["liveness"]["listings"])                   # … and then from the copy


def test_a_list_robots_txt_closed_before_a_later_round_read_it_doesnt_keep_its_alerts_open(make_cfg, memdb):
    from internwatch.models import RobotsBlocked
    cfg = make_cfg([company("acme"), company("newco", checker="greenhouse", settings={"board": "newco"}, round="added")],
                   liveness={"blocked": ["acme", "newco"]})
    names = [src["name"] for src in cfg.settings["liveness"]["listings"]]
    rows = [{"company": "Newco", "title": "SWE Intern", "url": "https://jobs.ashbyhq.com/newco/1"}]
    for name in names[1:]:  # the first list was never kept: robots.txt closes it (Trackr's API, November 2026)
        moves.keep_list(cfg, name, json.dumps(rows) if name == "boardsweep" else "[]")

    class Http:
        def get(self, url, **kw):
            raise RobotsBlocked(f"robots.txt disallows {url}")

        def close(self):
            pass
    ctx = moves.Ctx(cfg.scoped("added"), memdb, None, lambda *a, **kw: Http(), float("inf"), set())
    problems = moves.check_listings_later(ctx, "added", cfg)
    alerts.record(memdb, problems, [])
    assert [a["company"] for a in alerts.live(memdb, rule="list_system")] == ["newco"]
    moves.keep_list(cfg, "boardsweep", "[]")  # the list stops linking the board
    assert moves.check_listings_later(ctx, "added", cfg) == []
    assert alerts.live(memdb, rule="list_system") == []



def test_a_read_the_rounds_share_that_went_dark_is_told_about_once(make_cfg, monkeypatch, online):
    from datetime import timedelta

    from internwatch.db import utcnow
    cfg = two_rounds(make_cfg)
    db = DB(cfg.settings.path("db"))
    for mod, fn in ((liveness, "scan_pages"), (moves, "run"), (watch, "run")):
        monkeypatch.setattr(mod, fn, lambda *a, **kw: [])
    name = cfg.settings["liveness"]["listings"][0]["name"]  # the first round downloads it: both rounds find it dark
    days = [(utcnow() - timedelta(days=n)).date().isoformat() for n in (3, 2, 1)]
    db.set(f"blocked:rate:listings:{name}", json.dumps([[days[0], 1], [days[1], 0, "failed"], [days[2], 0, "failed"]]))
    db.set("blocked:mornings", json.dumps(days))
    checker = FakeChecker({"acme": [[job("1", "Software Engineer Intern (Summer 2027)")]],
                           "newco": [[job("2", "Software Engineer Intern (Summer 2027)")]]})
    s = Runner(cfg, db=db, checker_fn=checker).run(DAILY)
    assert [p["alert"]["id"] for p in s.all_problems] == [f"dark:listings:{name}"] and s.later == [([], [])]
    assert [a["alert_key"] for a in alerts.live(db)] == [f"dark:listings:{name}"]
    assert [e for e in s.emails if e.startswith("health")][0].startswith("health: [InternWatch HEALTH] 1 problem:")


def test_a_later_round_keeps_the_alerts_that_are_its_own():
    def problem(key, alert=None):
        return {"key": key, "name": key, "kind": "check gone dark", "summary": "s", **({"alert": alert} if alert else {})}
    shared, own = {"id": "dark:workday:t.wd1.myworkdayjobs.com", "rule": "dark"}, {"id": "dark:careers:newco", "rule": "dark"}
    s = RunSummary(problems=[problem("acme", shared), problem("acme")])
    s.absorb(RunSummary(problems=[problem("newco", shared), problem("newco", own), problem("newco")]))
    assert s.later == [([problem("newco", own), problem("newco")], [])]
