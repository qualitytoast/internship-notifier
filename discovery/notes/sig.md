# Susquehanna / SIG (`sig`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://careers.sig.com/jobs (all jobs). The bookmark https://careers.sig.com/intern-co-op/jobs?categories=Interns%20%2B%20Co-ops&city=… is a filtered landing page of the same Jibe site. |
| Hiring system | **iCIMS Jibe** over **iCIMS**, a single portal `careers-sig.icims.com` (all 286 jobs apply there) |
| Recommended adapter | shared **`jibe`** (spec in `docusign.md`), settings `{host: careers.sig.com, use_employment_type: false}` |

## Recommended feed
- `GET https://careers.sig.com/api/jobs?page=<N>&limit=100&internal=false` with N = 1…3. `totalCount` is 286; the pages hold 100 + 100 + 86 jobs, and every slug is unique.
- robots.txt has `crawl-delay: 5`.
- The intern landing page sends `categories=Interns%20%252B%20Co-ops`. The `+` is double-encoded, which is the site's own quirk. With no filter, the feed already holds all 63 of those jobs.

## Field map
Same as the jibe spec in `docusign.md`. SIG specifics:

| Job field | Path | Notes |
|---|---|---|
| id | `slug` = `req_id` (e.g. `11681`) | |
| url | `meta_data.canonical_url` = `https://careers.sig.com/jobs/{slug}?lang=en-us` | served directly, no redirect |
| program / audience | `categories[].name` (= `tags2`) | `Experienced Professionals` 173, `Interns + Co-ops` 63, `New Graduates` 37, `Student Discovery Program` 13 |
| team | `tags1` | `Technology - Software Engineering` 64, `Quantitative Trading + Strategy` 35, `Quantitative Research` 20, … |
| start term | `tags3` | `Immediate Start`, `June 2027 Start`, `March 2027 Start`, `Discovery Program 2027`, … Useful for the term filter. |
| office | `tags4` | Bala Cynwyd 125, Dublin 52, Sydney 28, New York 27, Hong Kong 26, London 19, … |
| employment type | `employment_type` | **Unreliable. Do not use it.** It is `INTERN` on 48 jobs:<br>• 20 are internships.<br>• 6 are Student Discovery events.<br>• 22 are experienced or new-grad roles, e.g. 10434 "Quantitative Systematic Trader - Experienced Hire", 11325 "Equity Research Sales Associate, Mid Level", 11031 "Quantitative Trader - Graduate: 2027".<br>Meanwhile 43 of the 63 real internships have null (33), `PER_DIEM` (8) or `CONTRACT_TO_HIRE` (2). If the adapter passes this field through, our filter (filters.yaml `role.employment_types` includes `intern`) would wrongly tag experienced roles as internships. |
| other | `brand` / `hiring_organization` = "Susquehanna International Group, LLP", `tags5` `F`/`P`, `posting_expiry_date` | |

## Totals (observed 2026-10-20 00:13 UTC)
- **Feed, no filters:** **286**. 3 pages, 286 unique.
- **Live careers page, no filters:** **286**. A Playwright render of https://careers.sig.com/jobs showed "286 Results" and "1 – 10 of 286". The page's own `/api/jobs` call returned `totalCount` 286.
- **Intern/student:** **63**. That is category `Interns + Co-ops`, and every one of the 63 has an intern or co-op title, e.g. many "… Co-op with Drexel University" and "Quantitative Trader Internship: June 2027 Start".
  - The title regex finds 64, because it also catches 11571 "Discovery Event: High School + First Year College Students (Virtual)".
  - The 13 `Student Discovery Program` postings are short student events and programmes, not internships. The filter will tag them only when "student(s)" is in the title.
  - The bookmark view (Interns + Co-ops in Chicago, New York, Richmond and Bala Cynwyd) showed 36 in the capture.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `https://careers.sig.com/api/jobs?page=1&limit=100&internal=false` | ALLOW | `Allow: /` (crawl-delay: 5) |
| `https://careers.sig.com/jobs`, `/jobs/<id>?lang=en-us` | ALLOW | `Allow: /` |

## Anti-bot / quirks
- There was no challenge. The page also loads an iubenda cookie script, which can be ignored.
- Always set `use_employment_type: false`. Classify interns from the title, `categories` and `tags3`.

## Recommended checker
```yaml
- key: sig
  name: Susquehanna (SIG)
  adapter: jibe
  careers_url: https://careers.sig.com/jobs
  settings:
    host: careers.sig.com
    use_employment_type: false     # INTERN is set on experienced/new-grad roles here
    extra_fields: [categories, tags3]   # program + start term are the useful signals
```

## Evidence
- Sample: `discovery/samples/sig.json` is the raw body of the page's own unfiltered call `GET /api/jobs?page=1&sortBy=relevance&descending=false&internal=false`: 10 jobs, totalCount 286, 139 KB.
- Capture: `discovery/captures/sig/` (bookmark, 36 results).
- Requests: 4 to careers.sig.com (3 pages and 1 job URL) plus 1 Playwright render, at ≥5 s per request.
