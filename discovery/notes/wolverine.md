# Wolverine Trading (`wolverine`)

**Status:** verified-feed. Use the company's Pinpoint custom domain: the default `*.pinpointhq.com` host is robots-disallowed.   ·   **Checked:** 2026-10-20 (00:15–00:30 UTC)

| | |
|---|---|
| Official careers URL | https://www.wolve.com/open-positions |
| Hiring system | Pinpoint. The page embeds the Pinpoint table widget (`div.pinpoint-external-jobs-table-widget[data-pinpoint-subdomain="wolve"]`). In the browser the widget calls `GET https://wolve.pinpointhq.com/postings.json`. Every job link on the page points to the custom domain `https://careers.wolve.com/en/postings/<uuid>`. |
| Recommended adapter | shared `pinpoint` with a **host override**: `{subdomain: wolve, host: careers.wolve.com}` → `GET https://careers.wolve.com/postings.json` |

## robots.txt (the reason for the host override)
| URL | Verdict | Deciding rule |
|---|---|---|
| https://wolve.pinpointhq.com/postings.json | **BLOCK** | `User-Agent: *` / `Disallow: /` (the whole host) |
| https://careers.wolve.com/postings.json | **ALLOW** | no matching rule. Its robots.txt disallows only `/mydata`, `/admin`, `/companies` and one posting `/postings/db1e2258-…`, and lists `Sitemap: https://careers.wolve.com/sitemap` |
| https://careers.wolve.com/en/postings/856f5215-88c8-4c1b-bd47-5106b33ed37f | ALLOW | no matching rule |
| https://www.wolve.com/open-positions | ALLOW | robots.txt is 404 |

`careers.wolve.com` is Wolverine's own careers domain on Pinpoint. All 19 job links on wolve.com go there, and it serves the same `postings.json`. Under RFC 9309 robots rules are per host, so this is the allowed route, not a workaround. **The shared adapter as written builds `https://<subdomain>.pinpointhq.com/postings.json`, which must not be fetched for wolve.** It needs an optional `host` (or `base_url`) setting.

## Recommended feed
- **Request:** `GET https://careers.wolve.com/postings.json`. HTTP 200 `application/json`, served through CloudFront, 132 KB, no auth, no pagination.
- **Same data as the page:** the 19 `data[].id`s equal the ids the widget fetched from wolve.pinpointhq.com in the 2026-10-19 capture.

## Field map
Paths are relative to `data[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | `id` | numeric, e.g. 446898 |
| title | `title` | |
| location(s) | `location.name` / `location.city` / `location.province` | "Chicago, IL" (18), "New York, NY" (1) |
| url | `url` | `https://careers.wolve.com/en/postings/<uuid>` (`path` holds the relative form) |
| posted date | none in the list | `deadline_at` is present (null) |
| description | `description`, `key_responsibilities`, `skills_knowledge_expertise` | HTML |
| employment type | `employment_type_text` | all "Full Time" today (`employment_type` "full_time") |
| department / team | `job.department.name`, `job.division.name`, `job.structure_custom_group_one.name` (Sub-Department) | e.g. Technology / Wolverine Trading / Engineering. The shared adapter reads a top-level `department`, which this feed does not have, so it should fall back to `job.department.name`. `job.requisition_id` is e.g. RID-0032. |
| other | `compensation_*`, `workplace_type_text`, `benefits` | |

## Totals (observed)
- **Feed, no filters:** **19** (careers.wolve.com, 2026-10-20).
- **Live careers page, no filters:** **19**. The rendered widget table in the 2026-10-19 Playwright capture (`discovery/captures/wolverine/page_0.html`) has 19 rows / 19 unique `careers.wolve.com/en/postings/<uuid>` links, and all 19 ids match.
- **Intern/student:** **0**. Several new-grad roles exist: "Entry Level C++ Software Engineer" (plus Spring 2027 and December 2026 graduate variants), "C++ Software Engineer (Early Career)".

## Recommended checker
```yaml
- key: wolverine
  name: Wolverine Trading
  adapter: pinpoint
  settings:
    subdomain: wolve
    host: careers.wolve.com        # REQUIRED: wolve.pinpointhq.com robots.txt is "Disallow: /"
  careers_url: https://www.wolve.com/open-positions
```

## Evidence
- Sample: `discovery/samples/wolverine.json` (raw careers.wolve.com/postings.json).
- Capture: `discovery/captures/wolverine/` (the widget's own call to wolve.pinpointhq.com, made by the page in a browser).
