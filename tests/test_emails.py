"""Email builders: subjects carry company + count and a filterable prefix; every row has an apply link."""
from internwatch import emails
from internwatch.db import iso

from conftest import company


def row(company_key, title, **kw):
    base = {"company": company_key, "job_id": title, "title": title, "location": "New York, NY", "url": "https://x/1",
            "term": "Summer 2027", "posted": "2026-10-19", "tags": '["SWE"]', "reasons": "[]", "unsure": 0,
            "repost_of": None, "source": "checker", "first_seen": iso()}
    base.update(kw)
    return base


def test_new_postings_subject_and_body(make_cfg):
    cfg = make_cfg([company("stripe", name="Stripe"), company("jane", name="Jane Street")])
    rows = [row("stripe", "SWE Intern"), row("stripe", "ML Intern"), row("jane", "Quant Trader Intern",
                                                                         tags='["Quant", "location?"]', unsure=1,
                                                                         reasons='["location: no location given"]')]
    subject, text, html = emails.new_postings(cfg, rows)
    assert subject == "[InternWatch] 3 new: Stripe (2), Jane Street (1)"
    assert "https://x/1" in text and "unsure: location" in html and "Summer 2027" in html


def test_prefixes_are_distinct(make_cfg):
    cfg = make_cfg([company("acme")])
    assert emails.digest(cfg, [], [], [], [])[0].startswith("[InternWatch Digest]")
    p = {"name": "Acme", "kind": "error", "summary": "could not fetch jobs", "detail": "", "since": iso(),
         "careers_url": "https://a"}
    assert emails.health(cfg, [p], [], [])[0].startswith("[InternWatch HEALTH]")
    assert "TEST ALERT" in emails.health(cfg, [p], [], [], test=True)[0]
    rows = [{"name": "Acme", "checker": "greenhouse", "status": "ok", "last_success": "Oct 19 10:00", "jobs": 5,
             "students": 1, "matched": 1, "errors": 0, "last_error": ""}]
    assert emails.coverage(cfg, rows)[0].startswith("[InternWatch COVERAGE]")


def test_digest_lists_untracked_companies(make_cfg):
    cfg = make_cfg([company("acme")])
    u = [{"company": "Foo Labs", "title": "SWE Intern", "url": "https://foo/1", "location": "SF", "category": "Software"}]
    subject, text, html = emails.digest(cfg, [row("acme", "SWE Intern")], u, [], [])
    assert "1 from untracked companies" in subject and "Foo Labs" in html and "internwatch add" in html
