# Autodesk (`autodesk`)

**Status:** verified-feed (two systems; watch both)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://jobs.autodesk.com/careers. The "Search jobs" button on https://www.autodesk.com/careers goes there, and the students page https://www.autodesk.com/careers/students links `https://jobs.autodesk.com/careers?filter_job_category=intern+fg`. |
| Hiring system | **Eightfold PCSX** career site (`jobs.autodesk.com`, domain `autodesk.com`). The ATS behind it is **Workday** (tenant `autodesk`, wd1). The tenant's robots.txt lists two public sites: **`uni`** (University Recruiting, the bookmark) and **`Ext`** (Careers). |
| Recommended adapter | Both shared adapters, merged: `eightfold` (jobs.autodesk.com) **and** `workday` (sites `uni`, `Ext`), deduped by requisition id. No composite exists yet. Either add a small shared `multi` wrapper (settings below), or configure two company entries (`autodesk` → eightfold, `autodesk-workday` → workday). |

The bookmark (`autodesk.wd1.myworkdayjobs.com/uni?locationCountry=US,CA`, 13 jobs) is a filtered view of `uni`. `uni` itself has 37 jobs, but Autodesk's own careers page is the Eightfold site, and the three sources do not hold the same jobs.

## Recommended feeds
1. **Eightfold:** `GET https://jobs.autodesk.com/api/pcsx/search?domain=autodesk.com&query=&location=&start=N&sort_by=timestamp`
   - **Headers:** browser UA and `Accept: application/json`. No cookie or CSRF token needed.
   - **Pagination:** 10 per page, fixed. `page_size=20` returns HTTP 400 `{"message": "Too many rows requested."}`, and `num` is ignored. Step `start` by 10 until `start >= data.count`: 39 requests for 386 jobs.
   - **Detail:** `GET /api/pcsx/position_details?position_id=<id>&domain=autodesk.com&hl=en` returns `data.jobDescription` (HTML) and `publicUrl`. There is no Workday apply link: applying happens on Eightfold.
   - **Intern filter** (the students page link): `&filter_job_category=intern fg` returns 28. That is 23 title matches plus 5 "PhD Researcher, …" roles. It misses "Software Development Internship (Summer 2027)", so union it with the title rule.
   - The v2 API (`/api/apply/v2/jobs`) returns 403 on this host.
2. **Workday:** `POST https://autodesk.wd1.myworkdayjobs.com/wday/cxs/autodesk/{uni|Ext}/jobs` with `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`
   - `total` is on the first page only. 20 per page. 37 + 310 jobs means 2 + 16 requests.
   - Intern facet: `workerSubType` "Intern/Co-op" (Ext id `39f5af07b0c54bc588b1a47788da7f81`) has 24 on Ext. It includes 2 PhD Researcher roles whose titles do not say intern.

## Field map
| Job field | Eightfold (`data.positions[]`) | Workday (`jobPostings[]`) |
|---|---|---|
| id | `id` (13 digits, e.g. 1443153604440) | `externalPath`. It differs per site for the same requisition (`…_26WD100617-1` on uni). |
| requisition id (**dedupe key**) | `displayJobId` = `atsJobId` (e.g. `26WD100617`) | `bulletFields[0]` (e.g. `26WD100617`) |
| title | `name` | `title` |
| locations | `locations[]` (Workday names such as "AMER - Canada - Ontario - Toronto - University Ave", plus a normalised city) / `standardizedLocations[]` | `locationsText` ("8 Locations" when there are several; the detail has the full list) |
| url | `https://jobs.autodesk.com` + `positionUrl` (`/careers/job/<id>`) | `https://autodesk.wd1.myworkdayjobs.com/en-US/<site><externalPath>` |
| posted | `postedTs`: epoch seconds, **always midnight UTC** (day granularity). `creationTs` also exists. | `postedOn`, relative ("Posted 30+ Days Ago") |
| team | `department` (noisy, e.g. "Canada - Time Tracking" on interns) | facets only |

## Totals (observed 2026-10-20 UTC)
| Source | Count | How |
|---|---|---|
| Eightfold feed (`data.count`) | **386** (386 unique ids and requisitions after the gap fill below) | full enumeration plus a re-read of pages 0–40 |
| Eightfold page | **386** | Playwright render of https://jobs.autodesk.com/careers: "386 jobs", "Page 1 of 39" |
| Workday `uni` / `Ext` feed | **37 / 310** (347 postings, **313** requisitions; 34 requisitions are on both sites) | full CXS enumeration |
| Workday pages | **37 / 310** | Playwright: "37 JOBS FOUND" / "310 JOBS FOUND" |
| Union of all three (unique requisitions) | **401** | 386 + 15 |
| Only on Eightfold | **88** requisitions, mostly posted 10–19 Oct. Includes 2 interns: `26WD101095` "Intern, Software Engineer" (Kraków) and `26WD101082` "Intern, AI Data Developer (Winter)" (Toronto). A Workday `searchText` query for those ids returns 0. | set difference |
| Only on Workday | **15** requisitions: `23WD73769` "Apprentice, Talent Acquisition & People Experience" (Ext), `26WD100499` "Senior Machine Learning Operations Developer" (**uni only**, posted 11 days ago), 2 "Product Manager (Contractor)" roles, and 11 old evergreen requisitions (21WD…–25WD…) | set difference |
| Interns (title or type), deduped | **30** | 24 Eightfold title matches, plus 5 Eightfold "Intern FG" PhD Researcher roles, plus 1 Workday-only apprentice |

Neither source is a superset. Eightfold is the official page and has the newest postings. Workday still holds roles that Eightfold does not show, and `uni` has at least one role that is nowhere else. Watching both costs about 57 requests per full run.

## robots.txt
| URL | Verdict | Rule |
|---|---|---|
| `https://jobs.autodesk.com/api/pcsx/search?domain=autodesk.com&…` | ALLOW | `Allow: /api/pcsx` (Eightfold standard file: `Disallow: /` plus allows for `/careers`, `/api/pcsx`, `/api/apply`, …) |
| `https://jobs.autodesk.com/api/pcsx/position_details?…` | ALLOW | `Allow: /api/pcsx` |
| `https://jobs.autodesk.com/careers…` | ALLOW | `Allow: /careers` |
| `https://autodesk.wd1.myworkdayjobs.com/wday/cxs/autodesk/uni/jobs` (and `/Ext/jobs`) | ALLOW | no matching rule. The file has `Allow: /Ext/`, `Allow: /uni/` and `Disallow: /refreshFacet/`. |

## Anti-bot / quirks
- **Unstable Eightfold paging.** All 386 `postedTs` values fall on midnight, so about 30 jobs share each day's timestamp, and their order changed between page requests. The first full scan returned 386 rows with only 378 unique ids: 8 jobs from page 0 came back again on pages 1–2, and 8 others were never returned. Re-reading pages 0–40 a few minutes later filled the gap, giving 386. A checker should:
  - dedupe by `id`;
  - if the unique count is below `data.count`, re-read the first pages of each tie group, or rescan once;
  - never mark a job removed after a single miss.

  The shared adapter's `check_total(..., tolerance=3)` would have raised on that scan.
- No 429 in about 60 requests at ≥2.6 s spacing. Use `min_interval: 2.5`.
- Without location parameters the Eightfold search returns all countries. The page adds nothing location-based by default here, unlike PayPal.
- Workday: the same requisition has a different `externalPath` on `uni` and `Ext` (suffix `-1`), so the workday adapter's `site:path` ids give two jobs for one requisition. Dedupe on `alt_ids` (`bulletFields`).

## Recommended checker
```yaml
- key: autodesk
  name: Autodesk
  careers_url: https://jobs.autodesk.com/careers
  checker: multi            # proposed thin wrapper: run each child adapter, merge, dedupe by alt_ids (req id 26WD…)
  settings:
    dedupe_by: alt_ids
    checkers:
      - checker: eightfold
        settings: {host: jobs.autodesk.com, domain: autodesk.com, api: pcsx, min_interval: 2.5}
      - checker: workday
        settings: {host: autodesk.wd1.myworkdayjobs.com, tenant: autodesk, sites: [uni, Ext]}
  # without a multi wrapper: two entries, autodesk (eightfold) + autodesk-workday (workday, sites [uni, Ext]);
  # the shared req id lets the mailer collapse duplicates.
```

## Evidence
- Sample: `discovery/samples/autodesk.json` (87 KB). It contains Eightfold search page 1 (filter lists trimmed), one `position_details` response, and the first 4 postings plus facets of the Workday `uni` and `Ext` first pages.
- Requests: about 60 to jobs.autodesk.com, including 2 full scans' worth of pages, the experiments (v2 403, page_size 400, order stability) and 3 Playwright loads. About 33 to autodesk.wd1: full enumerations, 5 requisition searches, an intern-facet query and 2 renders.
