"""Independent cross-check against the SimplifyJobs Summer 2027 list (listings.json, what its READMEs are built from).

Every run:
1. download the list (conditional GET with ETag) and read every row
2. rows never seen before are "new"; the very first download is only a baseline
3. new row for a tracked company:
     - company blocked / checker currently failing → stored and emailed as a new posting "via Simplify"
     - otherwise wait until the checker has polled the company after the row appeared (plus a grace
       period); if the checker never saw the job → "possible miss" health alert (a bug to fix);
       if it saw it but the filters rejected it (and it's one of your fields) → also reported;
       neither when Simplify's own location is outside the company's locations too
4. new row for an untracked company → listed in the daily digest
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import alerts
from .config import Company, Config
from .db import DB, iso, parse_iso, utcnow
from .filters import evaluate
from .locations import location_decision
from .models import Job

log = logging.getLogger(__name__)

YOUR_CATEGORIES = ("software engineering", "data science", "quantitative")
SUFFIXES = {"inc", "llc", "ltd", "corp", "corporation", "co", "company", "technologies", "technology", "group",
            "holdings", "lp", "llp", "plc", "the", "incorporated", "limited"}
# listings.json's categories, as its READMEs head them
CATEGORIES = {"software": "Software Engineering", "ai/ml/data": "Data Science, AI & Machine Learning",
              "quant": "Quantitative Finance", "hardware": "Hardware Engineering", "product": "Product Management"}
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
    open_keys: dict = field(default_factory=dict)           # source → keys of the rows this download lists open


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


def parse_listings(text: str, source: str) -> list[Row]:
    """Simplify's listings.json: the same rows as its READMEs and more (roles without a term, early-season roles)."""
    rows: list[Row] = []
    for x in json.loads(text):
        if not (isinstance(x, dict) and x.get("id")) or x.get("is_visible") is False:
            continue
        category = x.get("category") or ""
        rows.append(Row(source=source, key=str(x["id"]), company=x.get("company_name") or "", title=x.get("title") or "",
                        location="; ".join(x.get("locations") or []), url=clean_url(x.get("url") or ""),
                        simplify_url=f"https://simplify.jobs/p/{x['id']}", category=CATEGORIES.get(category.lower(), category),
                        terms=" ".join(t for t in x.get("terms") or [] if t != "N/A"), closed=not x.get("active")))
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
    twins = []
    for j in candidates:
        if title_key(j["title"]) != t or (j["removed_at"] and j["removed_at"] < closed_before):
            continue
        if years and set(_YEARS.findall(j["title"])) and not years & set(_YEARS.findall(j["title"])):
            continue
        twins.append(j)
    if not twins:
        return None, ""
    # the same title abroad must not stand in for this one: "Software Engineer Intern" in Paris for the one in Boston
    in_us = location_decision(row.location, ["US"])[0]
    return next((j for j in twins if not row.location or location_decision(j["location"], ["US"])[0] == in_us), twins[0]), "title"


def abroad(cfg: Config, comp: Company, location: str) -> bool:
    """Simplify's own location for a role is outside the company's locations: not a role you want, whatever happened."""
    return bool(location) and not location_decision(location, comp.locations or cfg.rules.default_locations)[0]


def _data(alert) -> dict:
    return json.loads(alert["data"])


# the note of a row given to a company added later (round: added), at its go-live or once a morning email had listed
# it as untracked: it is checked like any row from then on, but no path emails it again (never "via Simplify")
ADOPTED = "adopted"


class CrossCheck:
    def __init__(self, cfg: Config, db: DB, others=()):
        self.cfg, self.db = cfg, db
        self.others = set(others)  # companies of another round of the run (Config.scoped): their rows are left alone
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
                if resp.status == 304:
                    continue
                rows = parse_listings(resp.text, name)
            except Exception as e:  # noqa: BLE001 — reported as a health problem by the caller
                res.errors.append(f"{name}: {type(e).__name__}: {e}")
                continue
            if len(rows) < 50:
                res.errors.append(f"{name}: only {len(rows)} rows parsed — the list's format may have changed")
                continue
            if resp.headers.get("etag"):
                self.db.set(etag_key, resp.headers["etag"])
            # the first read of listings.json is a baseline too: it holds roles the READMEs left out, older than today
            baseline = not self.db.get(f"simplify_baselined:{name}") or not self.db.get("simplify_listings_read")
            res.baseline = res.baseline or baseline
            existing = {r["row_key"] for r in self.db.q("SELECT row_key FROM simplify_rows")}  # the READMEs' rows too
            with self.db.tx() as c:
                for r in rows:
                    if r.key in existing:
                        c.execute("UPDATE simplify_rows SET last_seen=? WHERE row_key=?", (now, r.key))
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
            self.db.conn.execute("UPDATE kv SET value=? WHERE key LIKE 'simplify_baselined:%'", (now,))  # the READMEs' rows
            self.db.set("simplify_listings_read", now)
            still_open = {r.key for r in rows if not r.closed}
            res.open_keys[name] = still_open
            for scope in {a["scope"] for a in map(_data, alerts.live(self.db, rule="miss"))}:
                alerts.seen(self.db, None, "miss", still_open, scope=scope)  # a role that closed is no longer a miss
        return res

    def resolve(self, res: Result) -> Result:
        """Decide what each pending row means. Safe to call every run."""
        now = utcnow()
        companies = {c.key: c for c in self.cfg.companies}
        for r in self.db.q("SELECT * FROM simplify_rows WHERE status='pending'"):
            if r["tracked_company"] in self.others:
                continue
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
                if r["note"] == ADOPTED:  # never emailed again: known for a company never checked, else judged later
                    if comp.status != "active":
                        self._set(r, "seen", "given to the company at its go-live; it is never checked")
                    continue
                self._store_via_simplify(comp, row, r, why="blocked" if comp.status != "active" else "checker failing")
                res.via_simplify += 1
                continue
            hit, how = find_in_db(self.db, comp.key, row)
            if abroad(self.cfg, comp, r["location"] or ""):
                self._set(r, "abroad", f"matched by {how}" if hit is not None else "not seen")
                continue
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

    def adopt(self, index: CompanyIndex, open_keys: dict, golive: dict) -> int:
        """Rows with no company that belong to this round's companies, by the whole config's index (the earlier rounds'
        companies first, so a row of theirs stays theirs), become theirs. One that Simplify lists open is checked from
        now on (pending); if it was first seen before the company went live (golive: key → ISO time), or a morning
        email already listed it as untracked, it is ADOPTED, so no path emails it again. One Simplify doesn't list open
        (closed, or from Simplify's first download) is recorded as known (baseline). Rows of a source whose open
        rows are unknown wait. Returns how many rows were given a company."""
        mine = {c.key for c in self.cfg.companies}
        n = 0
        for r in self.db.q("SELECT * FROM simplify_rows WHERE tracked_company IS NULL"):
            k = index.match(Row(r["source"], r["row_key"], r["company"] or "", r["title"] or "", r["location"] or "",
                                r["url"] or "", "", r["category"] or "", r["terms"] or ""))
            if k not in mine or (r["status"] == "untracked" and r["source"] not in open_keys):
                continue
            if r["status"] == "untracked" and r["row_key"] in open_keys[r["source"]]:
                old = r["first_seen"] < golive.get(k, "") or r["digest_at"] is not None
                status, note = "pending", ADOPTED if old else ""
            else:
                status, note = "baseline", r["note"]
            self.db.conn.execute("UPDATE simplify_rows SET tracked_company=?, status=?, note=? WHERE source=? AND row_key=?",
                                 (k, status, note, r["source"], r["row_key"]))
            n += 1
        return n

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


def backfill_shown(db: DB, outbox) -> int:
    """Untracked companies' rows that morning emails and digests listed before digest_at was kept (Nov 2026), read
    from their copies in the outbox: the untracked-roles.csv attachment, or the email's own table when it had none,
    matched by link. Each gets the email's time as digest_at. Returns how many rows were marked."""
    import csv
    import email
    import html as htmllib
    from datetime import datetime, timezone
    pending: dict[str, list] = {}
    for r in db.q("SELECT source, row_key, url FROM simplify_rows WHERE tracked_company IS NULL AND digest_at IS NULL "
                  "AND url IS NOT NULL"):
        pending.setdefault(r["url"].strip(), []).append(r)
    marked = 0
    for path in sorted([*outbox.glob("*-morning*.eml"), *outbox.glob("*-digest*.eml")]):
        try:
            when = datetime.strptime(path.name[:15], "%Y%m%d-%H%M%S").astimezone(timezone.utc)
        except ValueError:
            continue
        urls: set[str] = set()
        msg = email.message_from_bytes(path.read_bytes())
        for part in msg.walk():
            if part.get_filename() == "untracked-roles.csv":
                text = part.get_payload(decode=True).decode("utf-8", "replace")
                urls |= {row.get("url", "").strip() for row in csv.DictReader(text.splitlines())}
            elif part.get_content_type() == "text/html" and not part.get_filename():
                page = part.get_payload(decode=True).decode("utf-8", "replace")
                i = page.find("Untracked companies on the SimplifyJobs lists")
                if i >= 0:
                    table = page[i:page.find("</table>", i)]
                    urls |= {htmllib.unescape(u).strip() for u in re.findall(r'<a href="([^"]+)"', table)}
        for u in urls:
            for r in pending.pop(u, []):
                db.conn.execute("UPDATE simplify_rows SET digest_at=? WHERE source=? AND row_key=?",
                                (when.strftime("%Y-%m-%dT%H:%M:%SZ"), r["source"], r["row_key"]))
                marked += 1
    return marked
