# Remitly (`remitly`)

**Status:** verified-feed (Workday is the complete source; the marketing site lags it)   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://careers.remitly.com/job-search-results/ (bookmark: the same page with `?keyword=intern&category=`). It is a WordPress site built by **Symphony Talent** (the "CWS" plugin `cws.jobs.js`, the Hodes pixel). Job pages are `/job/<symphonyId>/<slug>/`, e.g. `/job/23935109/intern/`. |
| Hiring system | **Workday**, tenant `remitly`, host `remitly.wd5.myworkdayjobs.com`. robots.txt lists two sites: `Remitly_Careers` (main) and `Friends_Family_Intern`. The job pages' JSON-LD `identifier` is the Workday requisition (`R_106984`). The site's job API filters on `is_internal="Remitly_Careers"` and tags jobs `ats_portalid: "Workday-External"`. |
| Recommended adapter | shared `workday` adapter, `sites: [Remitly_Careers, Friends_Family_Intern]` |

## Recommended feed
- **Request:** `POST https://remitly.wd5.myworkdayjobs.com/wday/cxs/remitly/<site>/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}` and headers `Content-Type: application/json`, `Accept: application/json`
- **Pagination:** offset in steps of 20 up to `total`. Remitly_Careers: 156 means 8 pages. Friends_Family_Intern: `total: 0`, 1 page.
- No cookies needed. Plain httpx got 200 on every page.

## How the marketing site gets its list (for reference, not for the checker)
- The page's HTML holds no jobs. `cws.jobs.js` loads them via JSONP from Symphony Talent's Google Cloud Talent Solution proxy:
  `GET https://jobsapi-google.m-cloud.io/api/job/search?callback=CWS.jobs.jobCallback&pageSize=10&offset=0&companyName=companies%2Fc9a5233b-7164-44d2-98df-974dcaa42789&query=<kw>&customAttributeFilter=is_internal%3D%22Remitly_Careers%22&orderBy=relevance%20desc&histogramfacets=…`
- Without `callback` it returns plain JSON: `{"totalHits":147,"nextPageToken":"…","searchResults":[{"job":{…}}]}`. `pageSize=100` and `offset=100` both worked, so 147 rows took 2 calls. Each `job` has `ref` (Workday requisition, e.g. R_106974), `id` (the site's job id, e.g. 23924713), `title`, `primary_city/state/country`, `job_type` (Regular/Intern/Fixed Term), `employment_type`, `open_date`, `url` and `description`.
- robots.txt for `jobsapi-google.m-cloud.io` is 404, so it is allowed. It is a usable cross-check, but it is not the complete list (see Totals).

## Field map (Workday CXS)
| Job field | Response path | Notes |
|---|---|---|
| id | `jobPostings[].externalPath` | e.g. `/job/Manila-Phillippines/Intern_R_106984`. `bulletFields` holds `R_106984`. |
| title | `title` | |
| location | `locationsText` | "Seattle, Washington United States", "2 Locations". Workday spells "Phillippines" with two l's. |
| url | `https://remitly.wd5.myworkdayjobs.com/en-US/Remitly_Careers` + `externalPath` | Marketing copy: `https://careers.remitly.com/job/<site id>/<slug>/` (the site id comes only from the m-cloud API) |
| posted date | `postedOn` | relative |

## Totals (observed 2026-10-20)
- **Feed, no filters:** **156** (Remitly_Careers 156, 156 unique paths) + Friends_Family_Intern **0**.
- **Live careers page, no filters:** **147**, the `totalHits` of the page's own job API (the request the Playwright capture recorded, run without a keyword). The page shows no count text of its own.
- **Difference (+9), by requisition id:**
  - **10 Workday postings are missing from the marketing index.** All of them are "Posted 30+ Days Ago", e.g. R_106647 Principal Program Manager (Seattle), R_105960/R_105958/R_105964 AI Native Software Engineer (2 locations), R_106044 SDE II (Burnaby) and R_105279 Data Scientist II.
  - **1 site posting is no longer in Workday:** R_106784 Operations Manager, Remitly Business (B2B). It is stale.

  Workday is the system of record and is current, so the checker should use it.
- **Intern/student:** **2** by title, which matches the site's `job_type: Intern` count of 2:
  - R_106984 Intern (Customer Success, Emerging Talent Program), Manila, Philippines
  - R_107018 People Operations Intern, Managua, Nicaragua

  Friends_Family_Intern (an intern referral site) is empty today.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://remitly.wd5.myworkdayjobs.com/wday/cxs/remitly/Remitly_Careers/jobs` | ALLOW | no matching rule (`Allow: /Remitly_Careers/`, `Allow: /Friends_Family_Intern/`, `Disallow: /refreshFacet/`) |
| `POST https://remitly.wd5.myworkdayjobs.com/wday/cxs/remitly/Friends_Family_Intern/jobs` | ALLOW | no matching rule |
| `https://jobsapi-google.m-cloud.io/api/job/search?…` | ALLOW | robots.txt is 404 |
| https://careers.remitly.com/job-search-results/ and `/job/…` | ALLOW | `Allow: /` (it disallows only `/wp-admin/` and two `/job/job-description_header_*` paths) |

## Anti-bot / quirks
- careers.remitly.com answered plain httpx with 200 (1.4 MB pages). Workday and m-cloud had no challenge.
- The marketing index drops some older postings and keeps some closed ones, so do not use it as the source.

## Recommended checker
```yaml
- key: remitly
  name: Remitly
  adapter: workday
  settings:
    host: remitly.wd5.myworkdayjobs.com
    tenant: remitly
    sites: [Remitly_Careers, Friends_Family_Intern]
  careers_url: https://careers.remitly.com/job-search-results/
```

## Evidence
- Sample: `discovery/samples/remitly.json` is the first CXS page of Remitly_Careers (20 postings plus facets, 12 KB).
- Capture: `discovery/captures/remitly/` (page plus the m-cloud JSONP calls for `query=intern`).
- Requests: 8+1 CXS pages, 3 Workday robots probes (wd5/wd1/wd12), 2 m-cloud calls, 1 job page and 1 search page.
