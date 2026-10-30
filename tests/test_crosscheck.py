"""SimplifyJobs cross-check: reading listings.json, diffing against the previous version, possible misses."""
import json
from datetime import timedelta

from internwatch.crosscheck import CompanyIndex, CrossCheck, clean_url, norm_company, parse_listings
from internwatch.db import iso, utcnow
from internwatch.http import Resp

from conftest import company, job

FILLER = [{"id": f"f{i}", "company_name": "Filler Inc", "title": f"Intern {i}", "url": f"https://filler.example/{i}",
           "category": "Software", "locations": ["Austin, TX"], "terms": ["Summer 2027"], "active": True, "is_visible": True}
          for i in range(60)]


def listing(*rows) -> str:
    return json.dumps(FILLER + list(rows))


def test_reads_the_list():
    rows = parse_listings(json.dumps([
        {"id": "11111111-2222", "company_name": "Acme", "title": "ML Intern", "url": "https://x.example/1?utm_source=Simplify",
         "category": "AI/ML/Data", "locations": ["Austin, TX", "Remote in USA"], "terms": ["Summer 2027", "N/A"],
         "active": True, "is_visible": True},
        {"id": "closed", "company_name": "Acme", "title": "Closed Intern", "url": "u", "category": "Software", "active": False},
        {"id": "hidden", "company_name": "Acme", "title": "Hidden", "url": "u", "is_visible": False, "active": True},
        {"title": "no id"}]), "summer")
    assert [r.key for r in rows] == ["11111111-2222", "closed"]
    r = rows[0]
    assert (r.company, r.url, r.location, r.terms) == ("Acme", "https://x.example/1", "Austin, TX; Remote in USA", "Summer 2027")
    assert r.category == "Data Science, AI & Machine Learning" and r.simplify_url == "https://simplify.jobs/p/11111111-2222"
    assert not r.closed and rows[1].closed and rows[1].category == "Software Engineering"


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
    srcs = cfg.settings.get("crosscheck", "sources")
    texts = {s["url"]: listing() for s in srcs}
    cc = CrossCheck(cfg, memdb)
    res = cc.fetch_and_store(FakeHttp(texts))
    assert res.baseline and res.new_rows == 0   # first download is only a baseline
    # a new EA row appears on Simplify
    row = {"id": "11111111-2222-3333-4444-555555555555", "company_name": "Electronic Arts", "title": "Data Engineer Intern",
           "url": "https://jobs.ea.com/en_US/careers/JobDetail/x/999999", "category": "AI/ML/Data", "locations": ["Austin, TX"],
           "terms": ["Summer 2027"], "active": True, "is_visible": True}
    texts = {s["url"]: listing(row) for s in srcs}
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


def row_for(key, title="Data Engineer Intern", location="Austin, TX", **kw):
    return {"id": key, "company_name": "Electronic Arts", "title": title, "url": f"https://jobs.ea.com/x/{key}",
            "category": "AI/ML/Data", "locations": [location], "terms": ["Summer 2027"], "active": True, "is_visible": True, **kw}


def _ready(make_cfg, memdb, *first):
    ea = company("electronic-arts", name="Electronic Arts")
    cfg = make_cfg([ea])
    url = cfg.settings.get("crosscheck", "sources")[0]["url"]
    cc = CrossCheck(cfg, memdb)
    cc.fetch_and_store(FakeHttp({url: listing(*first)}))
    return cc, url


def _after_a_poll(cc, memdb, url, *rows):
    res = cc.fetch_and_store(FakeHttp({url: listing(*rows)}))
    memdb.conn.execute("UPDATE simplify_rows SET first_seen=? WHERE status='pending'", (iso(utcnow() - timedelta(hours=3)),))
    memdb.update_state("electronic-arts", last_success=iso())
    return cc.resolve(res)


def test_the_first_read_of_the_list_is_a_baseline_even_after_the_readmes(make_cfg, memdb):
    ea = company("electronic-arts", name="Electronic Arts")
    cfg = make_cfg([ea])
    url = cfg.settings.get("crosscheck", "sources")[0]["url"]
    old = iso(utcnow() - timedelta(days=2))
    memdb.set("simplify_baselined:summer", old)            # the READMEs were read before
    memdb.set("simplify_baselined:offseason", old)
    memdb.conn.execute("INSERT INTO simplify_rows(source, row_key, company, title, first_seen, last_seen, status)"
                       " VALUES('offseason', 'kept', 'Electronic Arts', 'Co-op', ?, ?, 'found')", (old, old))
    cc = CrossCheck(cfg, memdb)
    res = cc.fetch_and_store(FakeHttp({url: listing(row_for("kept"), row_for("older"))}))
    assert res.baseline and res.new_rows == 0
    assert memdb.one("SELECT status FROM simplify_rows WHERE row_key='older'")["status"] == "baseline"
    assert len(memdb.q("SELECT * FROM simplify_rows WHERE row_key='kept'")) == 1          # one row per role, not two
    now = memdb.get("simplify_baselined:summer")
    assert memdb.get("simplify_baselined:offseason") == now                               # learned ids still read
    assert memdb.one("SELECT last_seen FROM simplify_rows WHERE row_key='kept'")["last_seen"] == now
    assert cc.fetch_and_store(FakeHttp({url: listing(row_for("newer"))})).new_rows == 1   # from now on new rows are new


def test_a_broken_list_is_named_and_breaks_nothing(make_cfg, memdb):
    cc, url = _ready(make_cfg, memdb)
    for text in ('[{"id": "1"', "[]", '{"not": "a list"}'):
        res = cc.fetch_and_store(FakeHttp({url: text}))
        assert res.errors and "summer" in res.errors[0]


def test_a_foreign_role_is_no_possible_miss_when_simplify_says_so_too(make_cfg, memdb):
    cc, url = _ready(make_cfg, memdb)
    memdb.upsert_jobs("electronic-arts", [job("r1", "Data Engineer Intern", location="London, UK")], iso())
    memdb.conn.execute("UPDATE jobs SET reasons=? WHERE job_id='r1'", (json.dumps(["location outside US: London, UK"]),))
    res = _after_a_poll(cc, memdb, url, row_for("r1", location="London, UK"), row_for("r2", title="Never Seen", location="Toronto, ON, Canada"))
    assert res.misses == []
    assert {r["status"] for r in memdb.q("SELECT status FROM simplify_rows WHERE row_key IN ('r1', 'r2')")} == {"abroad"}


def test_a_us_role_rejected_as_foreign_is_still_flagged(make_cfg, memdb):
    cc, url = _ready(make_cfg, memdb)
    memdb.upsert_jobs("electronic-arts", [job("r3", "Data Engineer Intern", location="London, UK")], iso())
    res = _after_a_poll(cc, memdb, url, row_for("r3", location="Austin, TX"))
    assert [(m["title"], m["how"], m["key"]) for m in res.misses] == [("Data Engineer Intern", "filtered", "electronic-arts")]


def test_a_title_match_prefers_a_posting_in_a_compatible_place(memdb):
    from internwatch.crosscheck import Row, find_in_db
    memdb.upsert_jobs("x", [job("7", "Software Engineer Intern", location="Paris, France"),
                            job("8", "Software Engineer Intern", location="Boston, MA")], iso())
    row = Row("s", "k", "X", "Software Engineer Intern", "Boston, MA", "https://x.example/none", "", "Software")
    assert find_in_db(memdb, "x", row)[0]["job_id"] == "8"
    abroad = Row("s", "k", "X", "Software Engineer Intern", "Lyon, France", "https://x.example/none", "", "Software")
    assert find_in_db(memdb, "x", abroad)[0]["job_id"] == "7"
    none_there = Row("s", "k", "X", "Software Engineer Intern", "Tokyo, Japan", "https://x.example/none", "", "Software")
    memdb.conn.execute("UPDATE jobs SET location='Boston, MA'")
    assert find_in_db(memdb, "x", none_there)[1] == "title"   # no better twin: still the title match
