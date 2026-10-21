"""SimplifyJobs cross-check: README parsing, diffing against the previous version, possible misses."""
from datetime import timedelta
from pathlib import Path

from internwatch.crosscheck import CompanyIndex, CrossCheck, clean_url, norm_company, parse_readme
from internwatch.db import iso, utcnow
from internwatch.http import Resp

from conftest import REPO, company, job

FIX = REPO / "tests" / "fixtures" / "simplify"


def test_parses_both_lists():
    for name in ("README.md", "README-Off-Season.md"):
        rows = parse_readme((FIX / name).read_text(), name)
        assert len(rows) > 200
        r = next(r for r in rows if not r.closed)
        assert r.company and r.title and r.url.startswith("http") and r.key
    rows = parse_readme((FIX / "README.md").read_text(), "README.md")
    assert {r.category for r in rows} >= {"Software Engineering"}


def test_url_and_name_normalisation():
    assert clean_url("https://boards.greenhouse.io/x/jobs/1?utm_source=Simplify&gh_src=a") == "https://boards.greenhouse.io/x/jobs/1"
    assert clean_url("https://jobs.lever.co/acme/123/apply") == "https://jobs.lever.co/acme/123"
    assert norm_company("Jane Street Capital, LLC") == "jane street capital"
    assert norm_company("Two Sigma Investments (TSI)") == "two sigma investments"


def test_company_matching_by_url_marker_and_name():
    idx = CompanyIndex([company("stripe", checker="greenhouse", settings={"board": "stripe"}, name="Stripe"),
                        company("ea", checker="avature", name="Electronic Arts", aliases=["EA"])])
    from internwatch.crosscheck import Row
    r = Row("s", "k", "Stripe, Inc.", "SWE Intern", "SF", "https://job-boards.greenhouse.io/stripe/jobs/1", "", "SWE")
    assert idx.match(r) == "stripe"
    r2 = Row("s", "k2", "Electronic Arts", "SWE Intern", "Orlando", "https://jobs.ea.com/x/1", "", "SWE")
    assert idx.match(r2) == "ea"


class FakeHttp:
    def __init__(self, texts):
        self.texts = texts

    def get(self, url, **kw):
        return Resp(200, url, {"etag": "v1"}, self.texts[url].encode())


def test_new_row_missed_by_checker_alerts(make_cfg, memdb):
    ea = company("electronic-arts", name="Electronic Arts", aliases=["EA"])
    cfg = make_cfg([ea])
    readme = (FIX / "README.md").read_text()
    srcs = cfg.settings.get("crosscheck", "sources")
    texts = {s["url"]: readme for s in srcs}
    cc = CrossCheck(cfg, memdb)
    res = cc.fetch_and_store(FakeHttp(texts))
    assert res.baseline and res.new_rows == 0   # first download is only a baseline
    # a new EA row appears on Simplify
    row = ('<tr><td><strong><a href="https://simplify.jobs/c/EA">Electronic Arts</a></strong></td><td>Data Engineer Intern</td>'
           '<td>Austin, TX</td><td><div align="center"><a href="https://jobs.ea.com/en_US/careers/JobDetail/x/999999">'
           '<img alt="Apply"></a> <a href="https://simplify.jobs/p/11111111-2222-3333-4444-555555555555">'
           '<img alt="Simplify"></a></div></td><td>0d</td></tr>')
    texts = {s["url"]: readme.replace("<tbody>", "<tbody>\n" + row, 1) for s in srcs}
    memdb.set("simplify_etag:summer", "")
    res = cc.fetch_and_store(FakeHttp(texts))
    assert res.new_rows >= 1
    # the checker polled after the row appeared and never saw it → possible miss (after the grace period)
    memdb.conn.execute("UPDATE simplify_rows SET first_seen=? WHERE status='pending'", (iso(utcnow() - timedelta(hours=3)),))
    memdb.update_state("electronic-arts", last_success=iso())
    res = cc.resolve(res)
    assert any(m["title"] == "Data Engineer Intern" for m in res.misses)


def test_row_found_by_checker_is_not_a_miss(make_cfg, memdb):
    ea = company("electronic-arts", name="Electronic Arts")
    cfg = make_cfg([ea])
    memdb.upsert_jobs("electronic-arts", [job("999999", "Data Engineer Intern")], iso())
    from internwatch.crosscheck import Row, find_in_db
    r = Row("s", "k", "Electronic Arts", "Data Engineer Intern", "Austin, TX",
            "https://jobs.ea.com/en_US/careers/JobDetail/x/999999", "", "Data Science")
    hit, how = find_in_db(memdb, "electronic-arts", r)
    assert hit is not None and how == "id"


def test_row_found_through_another_link_to_the_same_posting(memdb):
    from internwatch.crosscheck import Row, find_in_db
    from internwatch.models import Job
    memdb.upsert_jobs("x", [
        Job(id="893398124010", title="Sparse Linear Algebra Libraries Intern - Summer 2027", extra={"alt_ids": ["JR2027429"]}),
        Job(id="greenhouse:7989364003", title="Software Engineer Co-op (Spring 2027)"),
        Job(id="/job/Austin/Applied-Science-Intern---2027_R-110379-1", title="Applied Science Intern - 2027",
            extra={"alt_ids": ["R-110379"]}),
        Job(id="11654", title="Technology Co-op with Drexel University"),
        Job(id="116601", title="Research Intern, Robotics - Summer 2027"),
    ], iso())

    def find(title, url):
        hit, how = find_in_db(memdb, "x", Row("s", "k", "X", title, "", url, "", "Software Engineering"))
        return (hit["job_id"] if hit else None), how

    # Workday link to a posting read from Eightfold: the requisition id is the end of the Workday slug
    assert find("Sparse Linear Algebra Libraries Intern 🎓", "https://nvidia.wd5.myworkdayjobs.com/External/job/"
                "US-CA-Santa-Clara/Sparse-Linear-Algebra-Libraries-Intern---Summer-2027_JR2027429") == ("893398124010", "id")
    # a multi-source company's second source, and another Workday site of the same requisition
    assert find("Software Engineer Co-op", "https://job-boards.greenhouse.io/klaviyocampus/jobs/7989364003")[1] == "id"
    assert find("Applied Science Intern 🎓", "https://expedia.wd108.myworkdayjobs.com/private/job/Austin/"
                "Applied-Science-Intern_R-110379-2")[0].endswith("R-110379-1")
    # an older posting id for the same role, title slightly rewritten
    assert find("Technology Co-op - Drexel University", "https://careers-sig.icims.com/jobs/11422/job") == ("11654", "title")
    # ids only count as whole tokens, and a shortened title is not enough
    assert find("Research Intern 🎓", "https://x.example.com/jobs/11660") == (None, "")
