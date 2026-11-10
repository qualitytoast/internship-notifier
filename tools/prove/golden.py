"""Golden comparison of two versions of InternWatch on the same inputs, no network.

    python -I tools/prove/golden.py <old ref> [<new dir>]      (e.g. main; the new version defaults to this tree)

Each version (a git ref is exported to a temporary folder; a directory is used as it is) is run in a process of its
own and dumps, for the companies of its config:
  cassettes  every recorded fixture through run_checker, with the company's config settings and with the settings
             saved in the fixture: jobs (every field), the requests made, the health flags
  filters    the filter verdict of every posting in data/internwatch.db (read-only)
  matching   the company every stored SimplifyJobs row and every row of the lists kept by the last run goes to
             (CompanyIndex, moves.company_of)
  workday    the sites each cached robots.txt lists (liveness.workday_sites) and hides (moves.workday_robots_sites)
Then the two dumps are compared. Allowed differences: rows that went from no company to a company with `round: added`
in the new config, and every entry of such a company. Anything else is listed and the result is FAIL.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def dump(src: Path, root: Path, data: Path) -> dict:
    """Run in a fresh interpreter whose `internwatch` is src/internwatch, with config from root/config."""
    sys.path.insert(0, str(src))
    import gzip  # noqa: F401
    from dataclasses import asdict
    from internwatch import config as configmod
    from internwatch import http as httpmod
    from internwatch import liveness, moves
    from internwatch.crosscheck import CompanyIndex, Row
    from internwatch.filters import evaluate
    from internwatch.models import Job
    from internwatch.runner import run_checker
    import sqlite3

    cfg = configmod.load(root)
    out: dict = {"code": str(httpmod.__file__), "cassettes": {}, "filters": {}, "matching": {}, "workday": {}}
    calls: list = []
    find = httpmod.Cassette.find

    def logged(self, method, url, body):
        calls.append([method, url, body])
        return find(self, method, url, body)
    httpmod.Cassette.find = logged
    by_key = {c.key: c for c in cfg.companies}
    for path in sorted((REPO / "tests" / "fixtures" / "cassettes").glob("*.json.gz")):
        key = path.name.split(".")[0]
        c = by_key.get(key)
        if c is None:
            continue
        for label, settings in (("config", c.settings), ("fixture", httpmod.Cassette.load(path).meta.get("settings"))):
            calls.clear()
            comp = configmod.Company(**{**c.__dict__, "settings": settings or {}})
            o = run_checker(cfg, comp, replay=httpmod.Cassette.load(path))
            out["cassettes"][f"{key} [{label}]"] = {
                "error_kind": o.error_kind, "error": o.error, "degraded": o.degraded, "partial": o.partial,
                "reported_total": o.reported_total, "unchanged": o.unchanged, "requests": list(calls),
                "jobs": [asdict(j) for j in (o.jobs or [])]}
    db = sqlite3.connect(f"file:{data / 'internwatch.db'}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    for r in db.execute("SELECT company, job_id, title, location, department, employment_type, snippet FROM jobs"):
        c = by_key.get(r["company"])
        j = Job(id=r["job_id"], title=r["title"], location=r["location"], department=r["department"],
                employment_type=r["employment_type"], snippet=r["snippet"])
        m = evaluate(j, cfg.rules, category=c.category if c else "", locations=c.locations if c else None,
                     extra_role_keywords=c.extra_role_re if c else None)
        out["filters"][f"{r['company']}|{r['job_id']}"] = [m.matched, m.unsure, m.term, m.field, m.tags, m.reasons]
    index = CompanyIndex(cfg.companies)
    for r in db.execute("SELECT source, row_key, company, url FROM simplify_rows"):
        out["matching"][f"simplify|{r['source']}|{r['row_key']}"] = index.match(
            Row(r["source"], r["row_key"], r["company"] or "", "", "", r["url"] or "", "", ""))
    comps = {c.key: c for c in cfg.active}
    lists = data / "lists" if (data / "lists").exists() else data / "stage1" / "raw" / "lists"  # Stage 1's download
    for src in (cfg.settings.get("liveness", "listings", default=[]) or []):
        path = lists / f"{src['name']}.txt"
        if not path.exists():
            continue
        text = path.read_text()
        rows = moves.ripplematch_rows(text) if src["format"] == "ripplematch" else moves.list_rows(src["format"], text)
        for i, (company, title, url, system) in enumerate(rows):
            c = moves.company_of(index, comps, company, url, slug=src["format"] in ("ripplematch", "trackr"))
            out["matching"][f"list|{src['name']}|{i}|{url}"] = c.key if c else None
    robots = data / "robots"
    for p in sorted(robots.glob("*.json")) if robots.exists() else []:
        d = json.loads(p.read_text())
        if "myworkdayjobs.com" in d.get("origin", ""):
            allow, hidden = moves.workday_robots_sites(d.get("text") or "")
            out["workday"][d["origin"]] = [sorted(liveness.workday_sites(d.get("text") or "")), sorted(allow),
                                           sorted(hidden)]
    return out


def export(ref: str, into: Path) -> Path:
    """A git ref's src/ and config/ in a folder of their own."""
    into.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(["git", "-C", str(REPO), "archive", ref, "src", "config"], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(into)], input=tar, check=True)
    return into


def run_version(where: Path, data: Path, out: Path) -> dict:
    code = (f"import json, sys; sys.path.insert(0, {str(REPO / 'tools' / 'prove')!r}); import golden; "
            f"json.dump(golden.dump(__import__('pathlib').Path({str(where / 'src')!r}), "
            f"__import__('pathlib').Path({str(where)!r}), __import__('pathlib').Path({str(data)!r})), "
            f"open({str(out)!r}, 'w'), sort_keys=True, default=str)")
    subprocess.run([sys.executable, "-I", "-c", code], check=True)
    return json.loads(out.read_text())


def added_keys(where: Path) -> set[str]:
    import yaml
    return {c["key"] for c in yaml.safe_load((where / "config" / "companies.yaml").read_text())["companies"]
            if c.get("round")}


def compare(old: dict, new: dict, added: set[str]) -> list[str]:
    problems = []
    for part in ("cassettes", "filters", "workday"):
        for k in sorted(set(old[part]) | set(new[part])):
            if k.split(" [")[0].split("|")[0] in added:
                continue
            if old[part].get(k) != new[part].get(k):
                problems.append(f"{part}: {k} differs")
    for k in sorted(set(old["matching"]) | set(new["matching"])):
        a, b = old["matching"].get(k), new["matching"].get(k)
        if a != b and not (a is None and b in added):
            problems.append(f"matching: {k}: {a} -> {b}")
    return problems


def main() -> int:
    old_ref = sys.argv[1]
    new_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO
    data = REPO / "data" if (REPO / "data" / "internwatch.db").exists() else Path(
        subprocess.run(["git", "-C", str(REPO), "worktree", "list"], capture_output=True, text=True).stdout.split()[0]) / "data"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        old_dir = Path(old_ref) if Path(old_ref).is_dir() else export(old_ref, tmp / "old")
        old = run_version(old_dir, data, tmp / "old.json")
        new = run_version(new_dir, data, tmp / "new.json")
    added = added_keys(new_dir)
    problems = compare(old, new, added)
    counts = {p: (len(old[p]), len(new[p])) for p in ("cassettes", "filters", "matching", "workday")}
    moved = sum(1 for k, v in new["matching"].items() if v in added and old["matching"].get(k) is None)
    print(f"golden: old {old['code']}\n        new {new['code']}\n        {counts}; rows given to added companies: {moved}")
    for p in problems[:200]:
        print("  ", p)
    print("PASS" if not problems else f"FAIL ({len(problems)} differences)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
