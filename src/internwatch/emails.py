"""Email bodies. Every builder returns (subject, text, html).

Subject prefixes (filterable):
  [InternWatch]           new postings, first-run summary
  [InternWatch Digest]    daily digest
  [InternWatch HEALTH]    checker problems, possible misses, test alerts
  [InternWatch COVERAGE]  weekly coverage report
"""
from __future__ import annotations

import csv
import io
import json
from collections import OrderedDict
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from .config import Config

STYLE_TABLE = "border-collapse:collapse;width:100%;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:13px"
STYLE_TH = "text-align:left;padding:6px 8px;border-bottom:2px solid #d0d7de;background:#f6f8fa;color:#24292f"
STYLE_TD = "padding:6px 8px;border-bottom:1px solid #eaeef2;vertical-align:top;color:#24292f"
STYLE_H = "font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#24292f;margin:18px 0 6px"
STYLE_P = "font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:13px;color:#57606a"
TAG = "display:inline-block;padding:1px 6px;margin:0 3px 2px 0;border-radius:10px;font-size:11px;"
TAG_FIELD = TAG + "background:#ddf4ff;color:#0969da"
TAG_UNSURE = TAG + "background:#fff8c5;color:#7d4e00"
TAG_OTHER = TAG + "background:#eaeef2;color:#57606a"


def _prefix(cfg: Config, kind: str = "") -> str:
    p = cfg.settings.get("email", "subject_prefix", default="InternWatch")
    return f"[{p}{(' ' + kind) if kind else ''}]"


def _tz(cfg: Config) -> ZoneInfo:
    return ZoneInfo(cfg.settings.get("email", "timezone", default="America/Chicago"))


def _local(cfg: Config, iso_utc: str | None, fmt: str = "%b %d %H:%M") -> str:
    if not iso_utc:
        return ""
    dt = datetime.strptime(iso_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(_tz(cfg)).strftime(fmt)


def _today(cfg: Config) -> str:
    return datetime.now(_tz(cfg)).strftime("%a %b %d")


def _names(cfg: Config) -> dict[str, str]:
    return {c.key: c.name for c in cfg.companies}


def _tags(row) -> list[str]:
    try:
        return json.loads(row["tags"] or "[]")
    except (ValueError, TypeError):
        return []


def _reasons(row) -> list[str]:
    try:
        return json.loads(row["reasons"] or "[]")
    except (ValueError, TypeError):
        return []


def _group(rows) -> "OrderedDict[str, list]":
    out: OrderedDict[str, list] = OrderedDict()
    for r in sorted(rows, key=lambda r: (r["company"], r["title"])):
        out.setdefault(r["company"], []).append(r)
    return out


def _tag_html(t: str) -> str:
    style = TAG_UNSURE if t.endswith("?") or t.startswith("unsure") else (
        TAG_OTHER if t in ("PhD", "Master's", "repost", "via Simplify", "reopened", "new term") else TAG_FIELD)
    label = {"field?": "unsure: field", "location?": "unsure: location", "term?": "unsure: term", "role?": "unsure: role type"}.get(t, t)
    return f'<span style="{style}">{escape(label)}</span>'


def _job_rows_html(rows) -> str:
    out = [f'<table style="{STYLE_TABLE}"><tr>'
           + "".join(f'<th style="{STYLE_TH}">{h}</th>' for h in ("Role", "Location", "Term", "Posted", "Tags"))
           + "</tr>"]
    for r in rows:
        tags = _tags(r)
        if r["repost_of"]:
            tags.append("repost")
        if r["source"] != "checker":
            tags.append("via Simplify")
        why = "; ".join(_reasons(r))
        out.append(
            "<tr>"
            f'<td style="{STYLE_TD}"><a href="{escape(r["url"] or "#")}" style="color:#0969da;font-weight:600;text-decoration:none">{escape(r["title"])}</a>'
            + (f'<div style="color:#7d4e00;font-size:11px;margin-top:2px">{escape(why)}</div>' if why else "")
            + "</td>"
            f'<td style="{STYLE_TD}">{escape((r["location"] or "—")[:120])}</td>'
            f'<td style="{STYLE_TD}">{escape(r["term"] or "unspecified")}</td>'
            f'<td style="{STYLE_TD}">{escape(r["posted"] or "—")}</td>'
            f'<td style="{STYLE_TD}">{"".join(_tag_html(t) for t in tags)}</td>'
            "</tr>")
    out.append("</table>")
    return "".join(out)


def _job_rows_text(rows) -> str:
    lines = []
    for r in rows:
        tags = _tags(r) + (["repost"] if r["repost_of"] else []) + (["via Simplify"] if r["source"] != "checker" else [])
        lines.append(f"  • {r['title']}\n    {r['location'] or '—'} | term: {r['term'] or 'unspecified'} | posted: {r['posted'] or '—'}"
                     f" | {', '.join(tags)}\n    {r['url']}")
        for why in _reasons(r):
            lines.append(f"    unsure: {why}")
    return "\n".join(lines)


def _wrap(title: str, body: str, footer: str = "") -> str:
    return (f'<html><body style="margin:0;padding:16px;background:#ffffff">'
            f'<h2 style="{STYLE_H}">{escape(title)}</h2>{body}'
            f'<p style="{STYLE_P};margin-top:24px;border-top:1px solid #eaeef2;padding-top:8px">{footer or "InternWatch"}</p>'
            f"</body></html>")


def _company_sections(cfg: Config, rows) -> tuple[str, str]:
    names = _names(cfg)
    html, text = [], []
    for company, rs in _group(rows).items():
        name = names.get(company, company)
        html.append(f'<h3 style="{STYLE_H}">{escape(name)} <span style="color:#57606a;font-weight:400">({len(rs)})</span></h3>')
        html.append(_job_rows_html(rs))
        text.append(f"{name} ({len(rs)})\n{_job_rows_text(rs)}\n")
    return "".join(html), "\n".join(text)


def _subject_companies(cfg: Config, rows, limit: int = 4) -> str:
    names = _names(cfg)
    groups = _group(rows)
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), names.get(kv[0], kv[0])))
    parts = [f"{names.get(k, k)} ({len(v)})" for k, v in ordered[:limit]]
    if len(ordered) > limit:
        parts.append(f"+{len(ordered) - limit} more")
    return ", ".join(parts)


MAX_BODY_ROWS = 50  # Gmail clips messages over ~100 KB of HTML, so longer lists travel as attachments


def _cell(v) -> str:
    """Job data comes from outside: never let a cell start a spreadsheet formula."""
    s = str(v or "")
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _csv(cfg: Config, rows) -> str:
    names = _names(cfg)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["company", "title", "location", "term", "posted", "tags", "unsure", "why unsure", "url"])
    for r in sorted(rows, key=lambda r: (names.get(r["company"], r["company"]).lower(), r["title"])):
        w.writerow([_cell(x) for x in (names.get(r["company"], r["company"]), r["title"], r["location"],
                                        r["term"] or "unspecified", r["posted"] or "", ", ".join(_tags(r)),
                                        "yes" if r["unsure"] else "", "; ".join(_reasons(r)), r["url"])])
    return buf.getvalue()


def _already_open(rows) -> tuple[list, list]:
    """(new, already open). Already open: recorded as a baseline, so open before InternWatch could judge it, and
    not emailed yet: a multi-source company's newly read source, or a role that matches after a filter change
    (`refilter --notify`)."""
    new, old = [], []
    for r in rows:
        (old if "baseline" in r.keys() and r["baseline"] else new).append(r)
    return new, old


ALREADY_OPEN_NOTE = ("Open before InternWatch could judge them (a source read for the first time, or your filters "
                     "changed), so not new, but never emailed before.")


def _sections_capped(cfg: Config, rows, what: str = "matching roles", stem: str = "matching-roles"):
    """Company sections for the email body (at most MAX_BODY_ROWS, surest first) + attachments with everything."""
    if len(rows) <= MAX_BODY_ROWS:
        h, t = _company_sections(cfg, rows)
        return h, t, None
    names = _names(cfg)
    shown = sorted(rows, key=lambda r: (bool(r["unsure"]), r["company"], r["title"]))[:MAX_BODY_ROWS]
    h, t = _company_sections(cfg, shown)
    groups = sorted(_group(rows).items(), key=lambda kv: names.get(kv[0], kv[0]).lower())
    counts = ", ".join(f"{escape(names.get(k, k))} ({len(v)})" for k, v in groups)
    note = (f'<p style="{STYLE_P}"><b>{len(rows)} {what}</b> is too many for one email: the {MAX_BODY_ROWS} surest are below, '
            f"and the complete list is attached (<b>{stem}.html</b> opens in a browser, <b>{stem}.csv</b> "
            f"in a spreadsheet).</p><p style=\"{STYLE_P}\"><b>By company:</b> {counts}</p>"
            f'<h3 style="{STYLE_H}">The {MAX_BODY_ROWS} surest</h3>')
    full_html, _ = _company_sections(cfg, rows)
    files = [(f"{stem}.html", _wrap(f"All {len(rows)} {what}", full_html).encode(), "text/html"),
             (f"{stem}.csv", _csv(cfg, rows).encode(), "text/csv")]
    text_note = (f"{len(rows)} {what}: the {MAX_BODY_ROWS} surest are listed below; the complete list is attached "
                 f"({stem}.html / {stem}.csv).\n\n")
    return note + h, text_note + t, files


UNTRACKED_BODY_ROWS = 25  # the morning email lists this many roles at untracked companies; the rest are attached


def _untracked_table(rows) -> str:
    trs = "".join(
        f'<tr><td style="{STYLE_TD}"><b>{escape(u["company"])}</b></td>'
        f'<td style="{STYLE_TD}"><a href="{escape(u["url"] or "#")}" style="color:#0969da">{escape(u["title"])}</a></td>'
        f'<td style="{STYLE_TD}">{escape(u.get("location") or "")}</td><td style="{STYLE_TD}">{escape(u.get("category") or "")}</td></tr>'
        for u in rows)
    return (f'<table style="{STYLE_TABLE}"><tr><th style="{STYLE_TH}">Company</th><th style="{STYLE_TH}">Role</th>'
            f'<th style="{STYLE_TH}">Location</th><th style="{STYLE_TH}">Category</th></tr>{trs}</table>')


def _untracked_csv(rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["company", "title", "location", "category", "url"])
    for u in rows:
        w.writerow([_cell(u.get(k)) for k in ("company", "title", "location", "category", "url")])
    return buf.getvalue()

def _with_files(built: tuple[str, str, str], files) -> tuple:
    return built + (files,) if files else built


# ---------------------------------------------------------------------------------------------

def new_postings(cfg: Config, rows) -> tuple[str, str, str]:
    rows, opened = _already_open(rows)
    n = len(rows)
    subject = (f"{_prefix(cfg)} {n} new: {_subject_companies(cfg, rows)}" + (f" (+{len(opened)} already open)" if opened else "")
               if rows else f"{_prefix(cfg)} {len(opened)} already open: {_subject_companies(cfg, opened)}")
    body_html, body_text, files = _sections_capped(cfg, rows, "new matching roles")
    unsure = sum(1 for r in rows if r["unsure"])
    note = (f'<p style="{STYLE_P}">{n} new matching role{"s" if n != 1 else ""} found just now'
            + (f", {unsure} tagged <b>unsure</b> (included because a rule could not decide)" if unsure else "") + ".</p>")
    text = f"{n} new matching role(s).\n\n{body_text}"
    if opened:
        h, t, more = _sections_capped(cfg, opened, "already-open roles", "already-open-roles")
        body_html += (f'<h3 style="{STYLE_H}">Already open ({len(opened)})</h3><p style="{STYLE_P}">{ALREADY_OPEN_NOTE}</p>' + h)
        text += f"\n\nALREADY OPEN ({len(opened)}): {ALREADY_OPEN_NOTE}\n{t}"
        files = (files or []) + (more or [])
    html = _wrap(f"{n} new internship posting{'s' if n != 1 else ''}" if n else "Already-open internship postings",
                 (note if n else "") + body_html)
    return _with_files((subject, text, html), files)


def seed_summary(cfg: Config, rows, checked: int, failed: list[str]) -> tuple[str, str, str]:
    n, companies = len(rows), len({r["company"] for r in rows})
    subject = f"{_prefix(cfg)} Now watching {checked} companies: {n} matching roles open at {companies}"
    body_html, body_text, files = _sections_capped(cfg, rows)
    fail_html = ""
    if failed:
        fail_html = (f'<p style="{STYLE_P}"><b>{len(failed)} checker(s) could not be read on the first run</b> '
                     f"and will be retried (you will get a HEALTH email if they keep failing): {escape(', '.join(failed))}</p>")
    intro = (f'<p style="{STYLE_P}">First run complete. Every job currently posted was recorded so you will only be emailed '
             f"about postings that appear from now on. These {n} roles match your filters today:</p>")
    html = _wrap("InternWatch is running", intro + fail_html + body_html)
    text = (f"First run complete: watching {checked} companies. {n} matching roles open now"
            + (f"\nCould not read yet: {', '.join(failed)}" if failed else "") + f"\n\n{body_text}")
    return _with_files((subject, text, html), files)


def watching_summary(cfg: Config, rows, keys: list[str]) -> tuple[str, str, str]:
    """Sent when companies are seeded after the first run (newly added, or first readable now)."""
    names = _names(cfg)
    who = ", ".join(names.get(k, k) for k in keys[:4]) + (f" +{len(keys) - 4} more" if len(keys) > 4 else "")
    n = len(rows)
    subject = f"{_prefix(cfg)} Now watching {who}: {n} matching role{'s' if n != 1 else ''} open"
    body_html, body_text, files = _sections_capped(cfg, rows)
    intro = (f'<p style="{STYLE_P}">These companies were read successfully for the first time. Their current postings '
             f"were recorded, so only new ones will be emailed from now on. Matching roles open today:</p>")
    html = _wrap(f"Now watching {who}", intro + (body_html or f'<p style="{STYLE_P}">None right now.</p>'))
    return _with_files((subject, f"Now watching {who}. {n} matching roles open now.\n\n{body_text}", html), files)


def digest(cfg: Config, new_rows, untracked: list[dict], misses: list[dict], open_problems: list[dict], *,
           morning: bool = False) -> tuple[str, str, str]:
    """The daily digest, or with morning=True the single email of `internwatch run --daily` (new since last run)."""
    new_rows, opened = _already_open(new_rows)
    n = len(new_rows)
    if morning:
        subject = (f"{_prefix(cfg)} {_today(cfg)}: " + (f"{n} new: {_subject_companies(cfg, new_rows)}" if n else "no new roles")
                   + (f"; {len(opened)} already open" if opened else "")
                   + (f"; {len(untracked)} at untracked companies" if untracked else ""))
        window, title = "since the last check", f"Your morning check — {_today(cfg)}"
    else:
        subject = f"{_prefix(cfg, 'Digest')} {_today(cfg)}: {n} new role{'s' if n != 1 else ''}, {len(untracked)} from untracked companies"
        window, title = "in the last 24 hours", f"Daily digest — {_today(cfg)}"
    parts_html, parts_text, files = [], [], None
    if new_rows:
        h, t, files = _sections_capped(cfg, new_rows, "new matching roles")
        parts_html.append(f'<h3 style="{STYLE_H}">New {window} ({n})</h3>' + h)
        parts_text.append(f"NEW {window.upper()} ({n})\n{t}")
    else:
        parts_html.append(f'<p style="{STYLE_P}">No new matching roles {window}.</p>')
        parts_text.append(f"No new matching roles {window}.")
    if opened:
        h, t, more = _sections_capped(cfg, opened, "already-open roles", "already-open-roles")
        parts_html.append(f'<h3 style="{STYLE_H}">Already open ({len(opened)})</h3><p style="{STYLE_P}">{ALREADY_OPEN_NOTE}</p>' + h)
        parts_text.append(f"ALREADY OPEN ({len(opened)}): {ALREADY_OPEN_NOTE}\n{t}")
        files = (files or []) + (more or [])
    if untracked:
        shown, more = untracked[:UNTRACKED_BODY_ROWS], len(untracked) - UNTRACKED_BODY_ROWS
        parts_html.append(f'<h3 style="{STYLE_H}">Untracked companies on the SimplifyJobs lists ({len(untracked)})</h3>'
                          f'<p style="{STYLE_P}">New roles from companies you do not track yet. Add one with '
                          f'<code>internwatch add "&lt;name&gt;" &lt;careers-url&gt;</code>.</p>' + _untracked_table(shown)
                          + (f'<p style="{STYLE_P}">… and {more} more in the attached <b>untracked-roles.html</b> / '
                             f'<b>untracked-roles.csv</b>.</p>' if more > 0 else ""))
        parts_text.append("UNTRACKED COMPANIES (SimplifyJobs)\n" + "\n".join(
            f"  • {u['company']}: {u['title']} — {u.get('location') or ''}\n    {u['url']}" for u in shown)
            + (f"\n  … and {more} more in untracked-roles.html / untracked-roles.csv" if more > 0 else ""))
        if more > 0:  # a long list would push the email past Gmail's ~102 KB clipping
            files = (files or []) + [
                ("untracked-roles.html", _wrap(f"All {len(untracked)} roles at untracked companies",
                                               _untracked_table(untracked)).encode(), "text/html"),
                ("untracked-roles.csv", _untracked_csv(untracked).encode(), "text/csv")]
    if misses or open_problems:
        items = [f"{m['company']}: possible miss “{m['title']}”" for m in misses] + \
                [f"{p['name']}: {p['summary']}" for p in open_problems]
        parts_html.append(f'<h3 style="{STYLE_H}">Still-open health issues</h3><ul style="{STYLE_P}">'
                          + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul>")
        parts_text.append("STILL-OPEN HEALTH ISSUES\n" + "\n".join(f"  • {i}" for i in items))
    html = _wrap(title, "".join(parts_html))
    return _with_files((subject, "\n\n".join(parts_text), html), files)


def health(cfg: Config, problems: list[dict], recovered: list[dict], misses: list[dict], *, test: bool = False) -> tuple[str, str, str]:
    """problems: [{name, kind, summary, detail, since, careers_url}], misses: [{company, title, url, reason, source}]"""
    bits = [f"{p['name']} ({p['kind']})" for p in problems[:4]] + [f"possible miss at {m['company']}" for m in misses[:3]]
    more = len(problems) + len(misses) - len(bits)
    count = len(problems) + len(misses)
    label = "TEST ALERT — " if test else ""
    subject = (f"{_prefix(cfg, 'HEALTH')} {label}{count} problem{'s' if count != 1 else ''}: {', '.join(bits)}"
               + (f" +{more} more" if more > 0 else "")) if count else f"{_prefix(cfg, 'HEALTH')} {label}all recovered"
    html_parts, text_parts = [], []
    if test:
        html_parts.append(f'<p style="{STYLE_P}"><b>This is a deliberate test alert</b> (internwatch alert-test). '
                          f"It went through the same code path as a real failure, so real alerts will reach you.</p>")
        text_parts.append("THIS IS A DELIBERATE TEST ALERT (internwatch alert-test).")
    if problems:
        rows = "".join(
            f'<tr><td style="{STYLE_TD}"><b>{escape(p["name"])}</b><br><span style="color:#57606a">{escape(p.get("checker", ""))}</span></td>'
            f'<td style="{STYLE_TD}">{escape(p["kind"])}</td><td style="{STYLE_TD}">{escape(p["summary"])}'
            f'<div style="color:#57606a;font-size:11px;margin-top:3px">{escape(p.get("detail", "")[:400])}</div></td>'
            f'<td style="{STYLE_TD}">{escape(p.get("since", ""))}</td>'
            f'<td style="{STYLE_TD}"><a href="{escape(p.get("careers_url", "#"))}" style="color:#0969da">careers page</a></td></tr>'
            for p in problems)
        html_parts.append(f'<h3 style="{STYLE_H}">Checker problems</h3>'
                          f'<p style="{STYLE_P}">Until fixed, check these careers pages yourself. Each was retried with backoff before this alert.</p>'
                          f'<table style="{STYLE_TABLE}"><tr><th style="{STYLE_TH}">Company</th><th style="{STYLE_TH}">Problem</th>'
                          f'<th style="{STYLE_TH}">Details</th><th style="{STYLE_TH}">Since</th><th style="{STYLE_TH}">Check by hand</th></tr>{rows}</table>')
        text_parts.append("CHECKER PROBLEMS (retried with backoff before alerting)\n" + "\n".join(
            f"  • {p['name']} [{p['kind']}] {p['summary']} (since {p.get('since', '')})\n    {p.get('detail', '')[:300]}\n    {p.get('careers_url', '')}"
            for p in problems))
    if misses:
        rows = "".join(
            f'<tr><td style="{STYLE_TD}"><b>{escape(m["company"])}</b></td>'
            f'<td style="{STYLE_TD}"><a href="{escape(m["url"] or "#")}" style="color:#0969da">{escape(m["title"])}</a></td>'
            f'<td style="{STYLE_TD}">{escape(m["reason"])}</td></tr>' for m in misses)
        html_parts.append(f'<h3 style="{STYLE_H}">Possible misses (SimplifyJobs cross-check)</h3>'
                          f'<p style="{STYLE_P}">These roles appeared on the SimplifyJobs lists for companies you track, but the checker did '
                          f"not report them. Apply from the link, and treat it as a checker bug to fix.</p>"
                          f'<table style="{STYLE_TABLE}"><tr><th style="{STYLE_TH}">Company</th><th style="{STYLE_TH}">Role</th>'
                          f'<th style="{STYLE_TH}">Why flagged</th></tr>{rows}</table>')
        text_parts.append("POSSIBLE MISSES (SimplifyJobs cross-check)\n" + "\n".join(
            f"  • {m['company']}: {m['title']} — {m['reason']}\n    {m['url']}" for m in misses))
    if recovered:
        html_parts.append(f'<h3 style="{STYLE_H}">Recovered</h3><ul style="{STYLE_P}">'
                          + "".join(f"<li>{escape(r['name'])}: {escape(r['summary'])}</li>" for r in recovered) + "</ul>")
        text_parts.append("RECOVERED\n" + "\n".join(f"  • {r['name']}: {r['summary']}" for r in recovered))
    html = _wrap("InternWatch health alert" if count else "InternWatch: problems recovered", "".join(html_parts))
    return subject, "\n\n".join(text_parts), html


def coverage(cfg: Config, rows: list[dict], window_days: int = 7) -> tuple[str, str, str]:
    """rows: [{name, checker, status, last_success, jobs, students, matched, errors, last_error}]"""
    healthy = sum(1 for r in rows if r["status"] == "ok")
    subject = f"{_prefix(cfg, 'COVERAGE')} Weekly report {_today(cfg)}: {healthy}/{len(rows)} checkers healthy"
    def color(st):
        return {"ok": "#1a7f37", "blocked": "#57606a", "failing": "#cf222e", "never run": "#9a6700"}.get(st, "#9a6700")
    trs = "".join(
        f'<tr><td style="{STYLE_TD}"><b>{escape(r["name"])}</b></td><td style="{STYLE_TD}">{escape(r["checker"])}</td>'
        f'<td style="{STYLE_TD};color:{color(r["status"])};font-weight:600">{escape(r["status"])}</td>'
        f'<td style="{STYLE_TD}">{escape(r["last_success"] or "never")}</td>'
        f'<td style="{STYLE_TD};text-align:right">{r["jobs"]}</td><td style="{STYLE_TD};text-align:right">{r["students"]}</td>'
        f'<td style="{STYLE_TD};text-align:right">{r["matched"]}</td>'
        f'<td style="{STYLE_TD};text-align:right">{r["errors"]}</td>'
        f'<td style="{STYLE_TD};color:#57606a;font-size:11px">{escape((r.get("last_error") or "")[:160])}</td></tr>'
        for r in rows)
    head = "".join(f'<th style="{STYLE_TH}">{h}</th>' for h in
                   ("Company", "Checker", "Status", "Last success", "Jobs", "Intern roles", "Matching", f"Errors ({window_days}d)", "Last error"))
    html = _wrap(f"Weekly coverage report — {_today(cfg)}",
                 f'<p style="{STYLE_P}">{healthy} of {len(rows)} checkers healthy. "Jobs" and "Intern roles" are what each checker '
                 f"currently sees on the live site; blocked companies are covered by the SimplifyJobs cross-check.</p>"
                 f'<table style="{STYLE_TABLE}"><tr>{head}</tr>{trs}</table>')
    text = f"{healthy}/{len(rows)} checkers healthy\n\n" + "\n".join(
        f"{r['name']:32} {r['checker']:14} {r['status']:9} last ok {r['last_success'] or 'never':17} jobs {r['jobs']:5} "
        f"intern {r['students']:4} match {r['matched']:4} errors {r['errors']:3} {(r.get('last_error') or '')[:80]}"
        for r in rows)
    return subject, text, html
