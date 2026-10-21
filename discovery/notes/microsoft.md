# Microsoft — job feed discovery

**Status:** verified-feed
**Checked:** 2026-10-19, 18:47–18:53 CDT (23:47–23:53 UTC). 35 scripted requests (33 to apply.careers.microsoft.com, 3 to the legacy hosts incl. 2 robots.txt) + 1 Playwright page load (12 xhr/fetch/document requests to apply.careers.microsoft.com) + the robots_check.py run.

## Careers site
- Official careers URL (job search, no filters): https://apply.careers.microsoft.com/careers?domain=microsoft.com&hl=en (careers.microsoft.com "Search jobs" lands here)
- Hiring system / ATS: **Eightfold.ai "PCSX"** career site, hosted on Microsoft's domain behind Azure Front Door. Evidence: `/api/pcsx/*` XHRs, `x-ef-ns: pcsx_api` / `x-ef-req-endpoint: search` response headers, Eightfold fonts (static.vscdn.net) in the HTML, 16-digit Eightfold position ids. The Microsoft requisition number is `displayJobId` / `atsJobId` (e.g. 200062674).
- Public job detail URL: `https://apply.careers.microsoft.com/careers/job/<id>` (= `"https://apply.careers.microsoft.com" + positionUrl`, = `publicUrl` in position_details). Verified: HTTP 200, server-rendered, `<title>` = job title, contains a schema.org `JobPosting` JSON-LD block and `<link rel="canonical">` to the same URL.
- Apply URL: same page; the "Apply now" button is client-side and requires sign-in (`positionUserActions.applyAction.status = "log_in"`). There is no separate apply link in the data.
- Legacy `https://jobs.careers.microsoft.com/global/en/job/<displayJobId>` returns **301 → https://apply.careers.microsoft.com/** (the home page, not the job), so it can't be used as a deep link.

## Recommended feed
- **Request:** `GET https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query=&location=&start=0&sort_by=timestamp`
- **Query params:**

| Param | Value | Meaning | Required? |
|---|---|---|---|
| `domain` | `microsoft.com` | Eightfold tenant | yes (always sent) |
| `query` | `` (empty) | keyword search; empty = everything | no |
| `location` | `` (empty) | free-text location (`United States`, `Canada`, …). Empty or omitted = **all countries** (both give count 2411, same as the page). Setting a location auto-applies `includeRemote=1, includeRelocation=0`. | no |
| `start` | 0, 10, 20, … | offset | no (default 0) |
| `sort_by` | `timestamp` (newest first) or `distance` (relevance to location) | ordering only; counts are identical (31 vs 31 for US interns) | no (default with no location = timestamp, UI "Sort: Latest") |
| `page_size` | ≤ 10 | rows per page. **Max is 10**: 11, 15, 20, 100 → HTTP 400 `{"message": "Too many rows requested."}` | no (default 10) |
| `filter_employment_type` | `internship` (also `full-time`, `part-time`, `temp/contract`, `post doc research`) | employment type filter | no |
| `filter_seniority` | `Intern` (also `Entry`, `Mid-Level`, `Senior`, `Manager`, `Director`, `Vice President`, `CXO`) | "Experience level" filter | no |
| `filter_include_remote` | `0`/`1` | include remote-eligible jobs (made no difference for US interns: 31 either way) | no |
| `hl` | `en` | UI language (the page sends it; results identical without it) | no |

  Other filters exist in `data.filterDef.allFilters[].filterName` (`work_site`, `profession`, `career_discipline`, `roletype`, `skills`, `hiring_title`) and presumably map to `filter_<name>` the same way, but I didn't verify them. `num`, `limit`, `pageSize`, `count` and `size` are **silently ignored** (still 10 rows).
- **Headers:** a normal browser `User-Agent` and `Accept: application/json` are enough. No cookie, CSRF token or referer is needed for GET. The browser also sends `x-csrf-token`, `x-browser-request-time` and `sentry-trace`, but none is required. The server sets a `_vscidv2` cookie, which isn't needed either.
- **Body:** none (GET).
- **Pagination:** offset. Increment `start` by 10 until `start >= data.count` (or `positions` comes back short or empty). **No offset cap:** `start=2400` returned 10 rows and `start=2410` returned the last 1 of 2411. The page itself shows "Page 1 of 242".
- **Full enumeration cost:** ceil(2411 / 10) = **242 requests**. That's ≈ 4.5 min at 1.1 s/request, but use **≥ 3 s spacing (≈ 12 min)** because of the 429 seen at 1.1 s (see Anti-bot).
- **Detail/description endpoint:** `GET https://apply.careers.microsoft.com/api/pcsx/position_details?position_id=<id>&domain=microsoft.com&hl=en` returns `data.jobDescription` (HTML, ~7 KB), `data.efcustomTextEmploymentType` (e.g. `["Internship"]`), `data.publicUrl` and work-site, profession and discipline fields. It returned **404 for a closed job** (bookmarked pid 1970393556866710 in the capture), which makes it useful for closure checks.
- **Alternatives considered:**
  - Eightfold's legacy `GET /api/apply/v2/jobs?domain=microsoft.com&start=0&num=100` (robots-allowed) → **HTTP 403 `{"message": "Not authorized for PCSX"}`**, so it's unusable.
  - The `JobPosting` JSON-LD on the detail page duplicates position_details but reports `employmentType: "FULL_TIME"` even for internships, so don't use it for intern detection.
  - No XML/RSS feed or sitemap was found. The careers page HTML contains no job data (client-rendered).

## Field map (JSON paths relative to one item at `data.positions[]`)
| Field | Path | Example |
|---|---|---|
| id | `id` (int, 16 digits; < 2^53, so safe) | `1970393557043740` |
| requisition / job number | `displayJobId` (= `atsJobId`, string) | `"200062674"` |
| title | `name` | `"Research Intern - Algorithms Group: Generative Modeling"` |
| location(s) | `locations[]` ("Country, State, City"; may be `"United States, Multiple Locations, Multiple Locations"`); `standardizedLocations[]` ("City, ST, CC", or just `"US"`/`"IN"` for country-level) | `["United States, Washington, Redmond"]`, `["Redmond, WA, US"]` |
| detail URL | `"https://apply.careers.microsoft.com" + positionUrl` | `/careers/job/1970393557043740` |
| apply URL | same as the detail URL (sign-in required) | |
| posted date | `postedTs`: epoch **seconds**, UTC; shown as "Date posted" in the UI and as JSON-LD `datePosted`. It is **refreshed on repost** (e.g. created 2026-07-29, postedTs 2026-10-19). | `1792446696` = 2026-10-19T21:51:36Z |
| created date | `creationTs` (epoch seconds, original creation; always ≤ postedTs) | `1792444978` |
| description / snippet | not in the list → position_details `data.jobDescription` (HTML) | "<b>Overview</b><br><p>Research Internships at Microsoft…" |
| employment type / intern flag | not in the list → position_details `data.efcustomTextEmploymentType[0]` (`Internship`, `Full-Time`, …), or infer it from which `filter_employment_type` / `filter_seniority` query returned the item | `["Internship"]` |
| team / category | `department`; details add `efcustomTextCurrentProfession`, `efcustomTextTaDisciplineName`, `efcustomTextRoletype` | `"Research Sciences"` |
| work-site / remote | `workLocationOption` (`onsite`, …), `locationFlexibility`; details `efcustomTextWorkSite` | `"onsite"`, `["3 days / week in-office"]` |
| other | `isHot`, `stars`, `solrScore` (null) | |

List path: `data.positions`; total path: `data.count`. The response also echoes `data.sortBy` and `data.appliedFilters` (e.g. `{"employmentType": ["internship"]}`), and has `data.filterDef.facets.locations` (top-10 `[label, count]` plus a `["Remote", 999999]` sentinel). Envelope: `status` (200), `error.message` (""), `metadata` (null).

## Totals (observed 2026-10-19)
| Measure | Value | How observed |
|---|---|---|
| Feed total, no filters | **2411** | `data.count` of the recommended request at 18:47 CDT. Identical with `location` omitted and with only `domain=microsoft.com`. The unfiltered set spans all countries (IN, JP, FI, NZ, CN rows seen on the last pages). |
| Live careers page total, no filters | **2411** ("2411 jobs", "Page 1 of 242") | One Playwright load of https://apply.careers.microsoft.com/careers?domain=microsoft.com&hl=en at 18:52 CDT. The page's own XHR was `GET /api/pcsx/search?domain=microsoft.com&query=&location=&start=0&&hl=en`. |
| Interns, `filter_employment_type=internship`, worldwide | **86** | `data.count` |
| … United States (`location=United States`) | **31** | same with `filter_include_remote=1`, `=0` or omitted, and with `sort_by=distance` |
| … Canada (`location=Canada`) | **3** | with or without `filter_include_remote=1` |
| `filter_seniority=Intern`, worldwide | 50 | of which 40 are also employment-type internship |
| `filter_seniority=Intern` + `filter_employment_type=full-time` | 7 | 2 are genuine internships typed full-time: "Applied Science PhD Internship" (Reading, UK) and "Product Management Intern - CTJ - TS" (Redmond, US). The other 5 are noise ("Critical Environment Operations", "Software Engineer II - CTJ- POLY" ×2, …). |
| Union internship ∪ seniority=Intern | 96 | 86 + 50 − 40 |
| Keyword `query=intern` | 102 | keyword/fuzzy search (includes non-title matches); not recommended as the primary method |
| US total, no other filters (`location=United States`) | 1276 | `data.count` (API auto-applies includeRemote=1) |
| Top location facets (unfiltered) | Redmond 801, "United States" 283, Mountain View 253, Bengaluru 129, Atlanta 113, Tokyo 100, Hyderabad 99, New York 98, Austin 75, Singapore 72 | `data.filterDef.facets.locations` |

Discrepancies: none between the feed and the page (both 2411). Intern counting needs care: `employment_type=internship` (86) **misses at least 2 real internships** that are typed Full-Time (1 of them in the US). Counting US interns with those included gives ≥ 32.

## robots.txt
`apply.careers.microsoft.com/robots.txt`: `User-agent: *` / `Disallow: /` with `Allow: /$`, `/careers`, `/api/apply`, `/api/pcsx`, `/login`, `/candidate/login`, `/events/…`, `/api/events`, `/careerhub/explore/jobs`, `/api/career_hub`, `/static/gen`, `/gen`.

| URL | Verdict | Rule (from discovery/robots_check.py) |
|---|---|---|
| `https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query=&location=&start=0&sort_by=timestamp` | ALLOW | `Allow: /api/pcsx` |
| `…/api/pcsx/search?…&filter_employment_type=internship` | ALLOW | `Allow: /api/pcsx` |
| `…/api/pcsx/search?…&filter_seniority=Intern` | ALLOW | `Allow: /api/pcsx` |
| `…/api/pcsx/search?domain=microsoft.com&query=intern&…` | ALLOW | `Allow: /api/pcsx` |
| `https://apply.careers.microsoft.com/api/pcsx/position_details?position_id=1970393557043740&domain=microsoft.com&hl=en` | ALLOW | `Allow: /api/pcsx` |
| `https://apply.careers.microsoft.com/careers/job/1970393557043740` | ALLOW | `Allow: /careers` |
| `https://apply.careers.microsoft.com/careers?domain=microsoft.com&hl=en` | ALLOW | `Allow: /careers` |
| `https://apply.careers.microsoft.com/api/apply/v2/jobs?domain=microsoft.com&start=0&num=100` | ALLOW (but returns 403) | `Allow: /api/apply` |
| `https://apply.careers.microsoft.com/api/suggest?term=…` (location autocomplete used by the UI; not needed) | **BLOCK** | `Disallow: /` |
| `https://jobs.careers.microsoft.com/global/en/job/200062674` (legacy) | ALLOW | no robots.txt (HTML served at /robots.txt) |

## Anti-bot / gotchas
- **Rate limit:** HTTP **429** `Please try again later` (22-byte text/plain, **no Retry-After or rate-limit headers**) on the 10th request within 27 s at 1.1 s spacing. The next request 1 s later was served normally. About 25 more requests at ≥ 3 s spacing got no 429. Use **≥ 3 s between requests** to this host (override the project-wide `min_interval: 1.0`). On a 429, back off ≥ 60 s.
- `page_size` > 10 → HTTP 400 "Too many rows requested."; the other size params are silently ignored.
- Front door: Azure Front Door (`x-azure-ref`). `Cache-Control: private, no-store`, no ETag/Last-Modified, so there are no conditional requests and every poll pays full price (~21 KB per page of 10).
- Sort by `timestamp` is only **approximately** postedTs-descending (inversions of a few minutes between neighbours), and postedTs is bumped on reposts. An incremental newest-first scan therefore needs a safety margin (≥ 2 h) and dedup by `id`.
- Employment type and description are only in position_details (1 extra request per job). JSON-LD `employmentType` is wrong for internships (`FULL_TIME`).
- The `Intern` seniority facet is noisy (it includes some non-intern roles), and the internship employment type misses some intern-titled roles. Union both and run title rules.

## Recommended checker approach
1. Host pacing ≥ 3 s, browser UA, `Accept: application/json`, no cookies. Base: `https://apply.careers.microsoft.com/api/pcsx/search?domain=microsoft.com&query=&location=&sort_by=timestamp&start=N` (page_size defaults to the max of 10).
2. Every poll (30–60 min):
   a. `filter_employment_type=internship`: all pages (86 → 9 requests).
   b. `filter_seniority=Intern`: all pages (50 → 5 requests). This catches internships typed Full-Time; the project's title filters drop the noise.
   c. Incremental unfiltered newest-first scan: walk `start=0,10,…` until a whole page has `postedTs < high_water − 2 h` (typically 1–5 requests). This catches any new posting whose title says Intern/Student/Apprentice but isn't tagged.
   Union by `id`; keep `displayJobId` as the human job number. Location filtering (US/Canada) is done client-side from `locations`/`standardizedLocations`. Don't send `location` to the API: that keeps worldwide coverage, and the API's location matching is fuzzy and geocoded.
3. For new candidate ids only (≤ `detail_fetch_limit`): `GET /api/pcsx/position_details?position_id=<id>&domain=microsoft.com&hl=en` for `jobDescription`, `efcustomTextEmploymentType` and `publicUrl`. A 404 means the job was closed.
4. Once a day (off-peak): a full unfiltered sweep, 242 requests at 3 s ≈ 12 min, to refresh the inventory and closures and to cross-check `sum(len(positions)) == data.count`.
5. Health: `status == 200`, `data.count` > 0 and stable (2411 baseline on 2026-10-19), `len(positions) == min(10, count − start)`, and alert on 429 streaks or on 400 (an API param change).
6. Job URL to email: `https://apply.careers.microsoft.com/careers/job/<id>`.

## Sample
`discovery/samples/microsoft.json` (28.7 KB) contains:
- `search_unfiltered_page1`: the full response of `GET …/api/pcsx/search?domain=microsoft.com&query=&location=&start=0&sort_by=timestamp` (10 positions, count 2411; filter option lists trimmed to 8 entries each).
- `search_internship_worldwide_page1`: the `filter_employment_type=internship` response, trimmed to 5 positions with filterDef removed (count 86).
- `position_details`: `GET …/api/pcsx/position_details?position_id=1970393557043740&domain=microsoft.com&hl=en`, with `positionExtraDetails` (videos/blogs/perks) stubbed out and the full `jobDescription` kept.
