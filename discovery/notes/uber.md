# Uber (`uber`)

**Status:** verified (shared `oracle` adapter)   ·   **Checked:** 2026-10-19 23:47 – 2026-10-20 03:27 UTC (two sessions)

| | |
|---|---|
| Official careers URL | https://jobs.uber.com/en/jobs/ (all jobs). The bookmark is a filtered view: `?team=University&countries=Canada&countries=United+States`. |
| Hiring system | **Oracle Recruiting Cloud** (Oracle HCM Candidate Experience) on `iaziqy.fa.ocs.oraclecloud.com`, site number **`UberCareers`**. jobs.uber.com is a Next.js front end that keeps a synced copy (its "Sign in" and "Apply" links go to `…/hcmUI/CandidateExperience/en/sites/UberCareers/…`). |
| Recommended adapter | shared `oracle` adapter: `{host: iaziqy.fa.ocs.oraclecloud.com, site: UberCareers}` |

## Why ORC and not jobs.uber.com
- **jobs.uber.com's JSON API is behind Cloudflare bot management.** For plain HTTP clients with a browser UA, `GET /api/jobs/search/…` returns **403 "Just a moment…"** with `cf-mitigated: challenge`. We do not work around that. Its static chunks and sitemaps are not challenged.
- **The jobs.uber.com API also pages unreliably** (session 1, from the page's own calls): page 2 at `pagesize=100` started at index 113 of the full list. Thirteen jobs from the first 200 were in neither page 1 nor page 2.
- **ORC is the system of record and openly reachable.** robots.txt is a 404, the REST API returns plain JSON, and 4 pages of 200 gave **703 unique ids = `TotalJobsCount` 703**, in both sessions.
- **The front end is a lagging copy.** Its SSR `totalJobs` and its sitemap are a subset of ORC, apart from a stale leftover:
  - ORC-only: **301657** "Sr Technical Sourcer" (posted 2026-09-21) and **302569** "Customer Success Manager, Enterprise Partnerships" (posted 2026-10-08). Both were missing from jobs.uber.com in both sessions, 3.5 h apart.
  - Sitemap-only: **160314** "Legal Counsel, South Korea". ORC's detail endpoint still knows it, but with `ExternalPostedStartDate: null`, so it is no longer posted. jobs.uber.com still lists it.
  - In session 1, two other ids (301656, 302172) were sitemap-only, with lastmod one minute old. By session 2 both systems agreed on them. The front end syncs about hourly: lastmod values cluster at `:05`.

## Recommended feed
- **Request (list):** `GET https://iaziqy.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber=UberCareers,limit=200,offset=N,sortBy=POSTING_DATES_DESC`
- **Headers:** `Accept: application/json` and a normal browser UA. No cookies or tokens.
- **Pagination:** `offset` in steps of 200. **`limit` caps at 200** (500 returned 200 in session 1). `items[0].TotalJobsCount` appears on every page. Today that is 4 pages (200 + 200 + 200 + 103), about 1.1 MB in total. Stop when `offset + 200 >= TotalJobsCount` or a page is empty.
- **Detail (optional):** `GET https://iaziqy.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id="303104",siteNumber=UberCareers` returns 200 JSON, about 23 KB. It has `ExternalDescriptionStr` (HTML), `RequisitionType` (`University` for the internships, `Hiring` otherwise), `Category`, `JobSchedule`, `JobShift` and `ExternalPostedStartDate`/`EndDate`.
- **Facets are top-10 only.** `categoriesFacet` and `locationsFacet` carry no University category, and `flexFieldsFacet` is empty. The bookmark's "University" team exists only on the jobs.uber.com copy, so filter by title, plus `RequisitionType` from the detail call for new ids if needed.

## Field map
Paths are relative to `items[0].requisitionList[]`.

| Job field | Path | Notes |
|---|---|---|
| id | `Id` | e.g. `303104`. It is the same id jobs.uber.com uses (`/en/jobs/303104/`). |
| title | `Title` | e.g. `2027 Account Management Intern, Madrid, Spain` |
| location(s) | `PrimaryLocation` (`Madrid, Spain`), `secondaryLocations[].Name` | also `PrimaryLocationCountry` (ISO-2) |
| url (detail/apply) | built: `https://iaziqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/UberCareers/job/{Id}` (the adapter's default; 200, title "Uber") | The pretty alternative `https://jobs.uber.com/en/jobs/{Id}/` works for people, but can 404 for the ORC-only or newest ids until the hourly sync. |
| posted date | `PostedDate` (`2026-10-16`) | |
| description / snippet | `ShortDescriptionStr` (often null in the list) | full HTML via the detail call |
| employment type | none in the list (`WorkerType`, `JobType`, `ContractType` and `JobSchedule` are all null on all 703 rows) | the detail has `RequisitionType`; the title says "Intern" |
| department / team | none in the list (`Department`/`JobFamily` are null) | the detail has `Category` (e.g. `Sales Incentive Plan`, `Engineer`) |

## Totals (observed 2026-10-20 03:24–03:27 UTC)
- **Feed, no filters:** **703** (`TotalJobsCount` 703; 703 rows, 703 unique ids). The count was the same, 703, at 23:48 UTC.
- **Live careers page, no filters:** **702**. A Playwright render of https://jobs.uber.com/en/jobs/ showed the pager "Prev 1 2 3 4 … **71** Next" at 10 per page. The page prints no count. Its SSR payload has `"totalPages":71,"totalJobs":702,"page":1,"pageSize":10`, and `/en/jobs/sitemap.xml` lists 702 job URLs (`Cache-Control: public, max-age=86400`).
- **The 702 vs 703 gap is explained id by id** (see above): ORC has 2 jobs the front end lacks, and the front end keeps 1 job ORC no longer posts. ORC is the complete, current source.
- **Intern/student: 11**, all with "Intern"/"Internship" titles and all posted 2026-09-30 to 2026-10-16:
  - Germany 5: Berlin and Munich, Sales, Operations, Account Management and Business Development U4B
  - France 2, Spain 1, Portugal 1, Poland 1, Japan 1
  - **None are in the US or Canada.**
  
  The jobs.uber.com copy agrees: its `WorkPattern` is Intern (10) or Intern to FTE (1) on exactly these 11 ids, and every one is titled. Its "University" team has only 6 jobs: 4 of these interns, a "Graduate 2026 PhD Software Engineer II" (new grad) and a BDR. ORC's keyword search is useless for interns: `keyword=intern` returns 324 rows (it matches "internal" and "international").

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `https://iaziqy.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?…siteNumber=UberCareers…` | ALLOW | no robots.txt (404, so allow-all) |
| `https://iaziqy.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?…` | ALLOW | no robots.txt |
| `https://iaziqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/UberCareers/job/303104` | ALLOW | no robots.txt |
| `https://jobs.uber.com/en/jobs/`, `/en/jobs/303104/`, `/en/jobs/sitemap.xml`, `/api/jobs/search/` | ALLOW | `Allow: /`. robots allows these, but Cloudflare challenges scripted API calls, so we don't use the API. |

## Anti-bot / quirks
- **jobs.uber.com:** Cloudflare challenges non-browser clients on its API and pages. Static assets and sitemaps are served without challenge. The checker never needs this host, only links to it.
- **ORC:** I saw no rate limiting at 1.15 s spacing. Responses are 300 KB per 200 rows, about 2 s each.
- **Ids:** jobs.uber.com and ORC share ids, so a later cross-check through the sitemap (702 URLs, one request, not challenged) is cheap. Alert if more than about 5 ORC ids are missing from the sitemap for more than a day.
- The site-level `TotalJobsCount` equals the unique rows, so the adapter's `check_total` (tolerance 3) passes.

## Recommended checker
```yaml
- key: uber
  name: Uber
  adapter: oracle
  careers_url: https://jobs.uber.com/en/jobs/
  settings:
    host: iaziqy.fa.ocs.oraclecloud.com
    site: UberCareers
    # job_url default: https://iaziqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/UberCareers/job/{id}
  # optional cross-check: GET https://jobs.uber.com/en/jobs/sitemap.xml (ids = ORC Id)
```

## Evidence
- Sample: `discovery/samples/uber.json`. It is the raw ORC list response (siteNumber UberCareers, `limit=200, offset=0`) from 03:24 UTC. `requisitionList` is trimmed from 200 to 60 rows to stay under 300 KB, and all facets and counts are unchanged.
- Session 1 (23:47–23:55 UTC):
  - About 20 requests: ORC pages, a limit-500 test, details, keyword, the sitemap index and the jobs sitemap.
  - Two Playwright sessions on jobs.uber.com, which made the page's own and in-page API calls (those observations are where the pagination problem was found).
  - Plain-httpx attempts on the jobs.uber.com API got Cloudflare 403s.
- Session 2 (03:24–03:27 UTC): 11 requests (4 ORC pages, 1 ORC detail, 1 ORC job page, 1 jobs sitemap, 2 robots.txt) plus 1 Playwright load of https://jobs.uber.com/en/jobs/ with no API calls of my own.
