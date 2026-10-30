"""Independent cross-check against the SimplifyJobs Summer 2027 lists (README.md + README-Off-Season.md).

Every run:
1. download both READMEs (conditional GET with ETag) and parse every listing row
2. rows never seen before are "new"; the very first download is only a baseline
3. new row for a tracked company:
     - company blocked / checker currently failing → stored and emailed as a new posting "via Simplify"
     - otherwise wait until the checker has polled the company after the row appeared (plus a grace
       period); if the checker never saw the job → "possible miss" health alert (a bug to fix);
       if it saw it but the filters rejected it (and it's one of your fields) → also reported
4. new row for an untracked company → listed in the daily digest
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .config import Company, Config
from .db import DB, iso, parse_iso, utcnow
from .filters import evaluate
from .models import Job

log = logging.getLogger(__name__)

YOUR_CATEGORIES = ("software engineering", "data science", "quantitative")
SUFFIXES = {"inc", "llc", "ltd", "corp", "corporation", "co", "company", "technologies", "technology", "group",
            "holdings", "lp", "llp", "plc", "the", "incorporated", "limited"}
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "ref", "source", "gh_src", "lever-source"}


@dataclass
class Row:
    source: str
    key: str
    company: str
    title: str
    location: str
    url: str
    simplify_url: str
    category: str
    terms: str = ""
    age: str = ""
    closed: bool = False


@dataclass
class Result:
    new_rows: int = 0
    misses: list[dict] = field(default_factory=list)       # → HEALTH email
    via_simplify: int = 0                                   # stored as jobs, go out with new-posting email
    untracked: int = 0
    baseline: bool = False
    errors: list[str] = field(default_factory=list)


def clean_url(url: str) -> str:
    if not url:
        return ""
    p = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    path = p.path
    for tail in ("/application", "/apply"):
        if path.endswith(tail):
            path = path[: -len(tail)]
    return urlunsplit((p.scheme, p.netloc.lower(), path, urlencode(q), ""))


def norm_company(name: str) -> str:
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)
    words = [w for w in re.findall(r"[a-z0-9]+", s) if w not in SUFFIXES]
    return " ".join(words)


def parse_readme(text: str, source: str) -> list[Row]:
    rows: list[Row] = []
    sections = re.split(r"(?m)^## ", text)
    for sec in sections[1:]:
        heading = sec.split("\n", 1)[0]
        category = re.sub(r"[^\w&,\s-]", "", heading).replace("Internship Roles", "").strip()
        if "<table" not in sec:
            continue
        soup = BeautifulSoup(sec, "html.parser")
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if "company" not in headers or "role" not in headers:
                continue
            col = {h: i for i, h in enumerate(headers)}
            company = ""
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) < len(headers):
                    continue
                ctext = tds[col["company"]].get_text(" ", strip=True)
                if ctext and ctext != "↳":
                    company = ctext
                title = tds[col["role"]].get_text(" ", strip=True)
                loc_cell = tds[col["location"]] if "location" in col else None
                if loc_cell is not None:
                    det = loc_cell.find("details")
                    if det and det.find("summary"):
                        det.find("summary").decompose()
                    location = "; ".join(x.strip() for x in loc_cell.get_text("\n").split("\n") if x.strip())
                else:
                    location = ""
                app = tds[col["application"]] if "application" in col else tds[-2]
                links = [a.get("href", "") for a in app.find_all("a")]
                apply = next((u for u in links if "simplify.jobs" not in u), "")
                simplify = next((u for u in links if "simplify.jobs/p/" in u), "")
                closed = "🔒" in app.get_text() or not links
                m = re.search(r"simplify\.jobs/p/([0-9a-f-]{36})", simplify)
                key = m.group(1) if m else hashlib.sha1(f"{company}|{title}|{location}|{clean_url(apply)}".encode()).hexdigest()[:20]
                rows.append(Row(source=source, key=key, company=company, title=title, location=location,
                                url=clean_url(apply), simplify_url=simplify.split("?")[0], category=category,
                                terms=tds[col["terms"]].get_text(" ", strip=True) if "terms" in col else "",
                                age=tds[col["age"]].get_text(strip=True) if "age" in col else "", closed=closed))
    return rows


# ---------------------------------------------------------------------------------------------
# company matching

def url_markers(c: Company) -> list[str]:
    s = c.settings or {}
    marks = []
    for b in [s.get("board")] + list(s.get("boards") or []):
        if b and c.checker == "greenhouse":
            marks += [f"greenhouse.io/{b.lower()}/", f"greenhouse.io/embed/job_app?for={b.lower()}"]
        if b and c.checker == "ashby":
            marks.append(f"ashbyhq.com/{b.lower()}/")
        if b and c.checker == "gem":
            marks.append(f"jobs.gem.com/{b.lower()}/")
    if c.checker == "lever" and s.get("site"):
        marks.append(f"lever.co/{s['site'].lower()}/")
    if c.checker == "workable" and s.get("account"):
        marks.append(f"apply.workable.com/{s['account'].lower()}/")
    for k in ("host",):
        if s.get(k) and not str(s[k]).startswith(("wd1.myworkdaysite", "wd5.myworkdaysite")):
            marks.append(str(s[k]).lower())
    if c.checker == "workday" and "myworkdaysite.com" in str(s.get("host", "")):
        marks.append(f"/recruiting/{s.get('tenant', '').lower()}/")
    marks += [m.lower() for m in s.get("match_urls", [])]
    return [m for m in marks if m]


class CompanyIndex:
    def __init__(self, companies: list[Company]):
        self.by_name: dict[str, str] = {}
        self.markers: list[tuple[str, str]] = []
        for c in companies:
            for n in c.all_names:
                self.by_name.setdefault(norm_company(n), c.key)
            for m in url_markers(c):
                self.markers.append((m, c.key))
        self.markers.sort(key=lambda x: -len(x[0]))

    def match(self, row: Row) -> str | None:
        u = row.url.lower()
        for marker, key in self.markers:
            if marker in u:
                return key
        return self.by_name.get(norm_company(row.company))


# ---------------------------------------------------------------------------------------------

_TITLE_NOISE = re.compile(r"\b(?:spring|summer|fall|autumn|winter|20\d\d|with|and|the|of|for|in|at|a|an)\b|[^a-z0-9\s]")
_YEARS = re.compile(r"\b20\d\d\b")
TITLE_MATCH_DAYS = 30   # a posting closed longer ago than this is an earlier round, not the one Simplify lists


def _id_in_url(ident: str, url: str) -> bool:
    """The id appears in the URL as a whole token: …/jobs/7989364003, …-Intern_JR2027429, …_R-110379-1."""
    if len(ident) < (5 if ident.isdigit() else 4):
        return False
    before = r"(?<![a-z0-9])" if ident[0].isalnum() else ""
    after = r"(?![a-z0-9])" if ident[-1].isalnum() else ""
    return re.search(before + re.escape(ident) + after, url) is not None


def _stem(w: str) -> str:
    w = w[:-1] if len(w) > 3 and w.endswith("s") else w
    return re.sub(r"(?:ing|ship)$", "", w) if len(w) > 5 else w


def title_key(title: str) -> frozenset[str]:
    """Title words without the term, emoji, punctuation or word endings. Simplify rewrites titles slightly
    ("Technology Co-op - Drexel University 🎓" for "Technology Co-op with Drexel University")."""
    return frozenset(_stem(w) for w in _TITLE_NOISE.sub(" ", title.lower()).split())


def find_in_db(db: DB, company: str, row: Row):
    """Locate the Simplify row among the jobs the checker has seen. Returns (db_row, how) or (None, '').
    Simplify often links another front end of the same hiring system (NVIDIA's Workday behind its Eightfold
    site, an iCIMS portal behind Jibe), so requisition ids (alt_ids) count as well as the job id."""
    url = row.url.lower()
    candidates = db.q("SELECT * FROM jobs WHERE company=? AND source='checker'", company)
    for j in candidates:
        jid = re.sub(r"^[a-z]+:", "", j["job_id"].lower())  # "<checker>:<id>" / "<site>:<path>" prefixes
        ids = [jid, jid.strip("/").split("/")[-1], *(str(a).lower() for a in json.loads(j["alt_ids"] or "[]"))]
        if any(_id_in_url(i, url) for i in ids):
            return j, "id"
        if j["url"] and clean_url(j["url"]).lower() == url:
            return j, "url"
    # By title only a current posting counts: the database keeps every job ever seen, and last cycle's closed
    # "Software Engineer Intern - Summer 2027" must not stand in for a "Summer 2028" posting the checker missed.
    t = title_key(row.title)
    years = set(_YEARS.findall(f"{row.title} {row.terms}"))
    closed_before = iso(utcnow() - timedelta(days=TITLE_MATCH_DAYS))
    for j in candidates:
        if title_key(j["title"]) != t or (j["removed_at"] and j["removed_at"] < closed_before):
            continue
        if years and set(_YEARS.findall(j["title"])) and not years & set(_YEARS.findall(j["title"])):
            continue
        return j, "title"
    return None, ""


class CrossCheck:
    def __init__(self, cfg: Config, db: DB):
        self.cfg, self.db = cfg, db
        self.index = CompanyIndex(cfg.companies)
        self.grace = timedelta(minutes=int(cfg.settings.get("crosscheck", "grace_minutes", default=90)))

    def fetch_and_store(self, http) -> Result:
        res = Result()
        now = iso()
        for src in self.cfg.settings.get("crosscheck", "sources", default=[]):
            name = src["name"]
            etag_key = f"simplify_etag:{name}"
            headers = {}
            if self.db.get(etag_key) and self.db.get(f"simplify_baselined:{name}"):
                headers["If-None-Match"] = self.db.get(etag_key)
            try:
                resp = http.get(src["url"], headers=headers, ok_statuses=(304,), timeout=60)
            except Exception as e:  # noqa: BLE001 — reported as a health problem by the caller
                res.errors.append(f"{name}: {type(e).__name__}: {e}")
                continue
            if resp.status == 304:
                continue
            rows = parse_readme(resp.text, name)
            if len(rows) < 50:
                res.errors.append(f"{name}: only {len(rows)} rows parsed — README format may have changed")
                continue
            if resp.headers.get("etag"):
                self.db.set(etag_key, resp.headers["etag"])
            baseline = not self.db.get(f"simplify_baselined:{name}")
            res.baseline = res.baseline or baseline
            existing = {r["row_key"] for r in self.db.q("SELECT row_key FROM simplify_rows WHERE source=?", name)}
            with self.db.tx() as c:
                for r in rows:
                    if r.key in existing:
                        c.execute("UPDATE simplify_rows SET last_seen=? WHERE source=? AND row_key=?", (now, name, r.key))
                        continue
                    if r.closed:
                        continue
                    tracked = self.index.match(r)
                    status = "baseline" if baseline else ("pending" if tracked else "untracked")
                    c.execute(
                        "INSERT OR IGNORE INTO simplify_rows(source, row_key, company, title, location, url, category, terms, age,"
                        " first_seen, last_seen, tracked_company, status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (name, r.key, r.company, r.title, r.location, r.url or r.simplify_url, r.category, r.terms, r.age,
                         now, now, tracked, status))
                    if not baseline:
                        res.new_rows += 1
            self.db.set(f"simplify_baselined:{name}", now)
        return res

    def resolve(self, res: Result) -> Result:
        """Decide what each pending row means. Safe to call every run."""
        now = utcnow()
        companies = {c.key: c for c in self.cfg.companies}
        for r in self.db.q("SELECT * FROM simplify_rows WHERE status='pending'"):
            comp = companies.get(r["tracked_company"])
            if comp is None:
                self.db.conn.execute("UPDATE simplify_rows SET status='untracked' WHERE source=? AND row_key=?",
                                     (r["source"], r["row_key"]))
                continue
            row = Row(r["source"], r["row_key"], r["company"], r["title"], r["location"] or "", r["url"] or "", "",
                      r["category"] or "", r["terms"] or "")
            st = self.db.state(comp.key)
            failing = bool(st["alert_open"]) or (st["consecutive_failures"] or 0) > 0
            if comp.status != "active" or failing:
                self._store_via_simplify(comp, row, r, why="blocked" if comp.status != "active" else "checker failing")
                res.via_simplify += 1
                continue
            hit, how = find_in_db(self.db, comp.key, row)
            if hit is not None:
                in_fields = any(k in (r["category"] or "").lower() for k in YOUR_CATEGORIES)
                if not hit["matched"] and in_fields and hit["removed_at"] is None:
                    reasons = json.loads(hit["reasons"] or "[]")
                    res.misses.append({"company": comp.name, "key": comp.key, "how": "filtered", "title": r["title"],
                                       "url": hit["url"] or r["url"],
                                       "reason": f"seen by the checker but rejected by your filters ({'; '.join(reasons) or 'no reason'})",
                                       "source": r["source"], "row_key": r["row_key"]})
                    self._set(r, "filtered", f"matched by {how}")
                else:
                    self._set(r, "found", f"matched by {how}")
                continue
            first_seen = parse_iso(r["first_seen"])
            last_ok = parse_iso(st["last_success"])
            if first_seen and now - first_seen >= self.grace and last_ok and last_ok >= first_seen + timedelta(minutes=30):
                res.misses.append({"company": comp.name, "key": comp.key, "how": "never", "title": r["title"], "url": r["url"],
                                   "reason": f"listed on Simplify {r['first_seen']}; the checker polled since "
                                             f"({st['last_success']}) and never saw it", "source": r["source"],
                                   "row_key": r["row_key"]})
                self._set(r, "missed", "")
        return res

    def _set(self, r, status: str, note: str) -> None:
        self.db.conn.execute("UPDATE simplify_rows SET status=?, note=?, resolved_at=? WHERE source=? AND row_key=?",
                             (status, note, iso(), r["source"], r["row_key"]))

    def _store_via_simplify(self, comp: Company, row: Row, r, why: str) -> None:
        job = Job(id=f"simplify:{row.key}", title=row.title, location=row.location, url=row.url, snippet=row.terms,
                  employment_type="Intern")  # Simplify only lists internships
        m = evaluate(job, self.cfg.rules, category=comp.category, locations=comp.locations,
                     extra_role_keywords=comp.extra_role_re)
        if not m.matched and any(k in row.category.lower() for k in YOUR_CATEGORIES):
            m.matched, m.unsure = True, True
            m.reasons.append(f"listed by Simplify ({row.category}); our filter said: {'; '.join(m.reasons) or 'no'}")
        self.db.add_external_job(comp.key, job, iso(), m, source="simplify")
        self._set(r, "via_simplify", why)

    def untracked_for_digest(self, since_iso: str) -> list[dict]:
        """Untracked-company rows first seen since `since_iso`, filtered to your fields and locations."""
        out = []
        for r in self.db.q("SELECT * FROM simplify_rows WHERE status='untracked' AND first_seen>=? ORDER BY company, title",
                           since_iso):
            if not any(k in (r["category"] or "").lower() for k in YOUR_CATEGORIES):
                continue
            job = Job(id=r["row_key"], title=r["title"], location=r["location"] or "", snippet=r["terms"] or "",
                      employment_type="Intern")
            m = evaluate(job, self.cfg.rules, category="quant" if "quant" in (r["category"] or "").lower() else "")
            if m.matched:
                out.append({**dict(r), "unsure": m.unsure})
        return out
