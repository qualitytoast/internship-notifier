# Akamai (`akamai`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://jobs.akamai.com/en/sites/CX_1/jobs (bookmark: the same page with `?keyword=intern&mode=location`). It is a vanity domain: DNS `jobs.akamai.com` → `jobs.akamai.com.edgesuite.net` → `a1428.q.akamai.net` (Akamai's own CDN, `Oracle API Gateway` behind it). |
| Hiring system | **Oracle Recruiting Cloud** (Oracle HCM Candidate Experience), site `CX_1`, pod **`fa-extu-saasfaprod1.fa.ocs.oraclecloud.com`** |
| Recommended adapter | shared `oracle` adapter, `host: fa-extu-saasfaprod1.fa.ocs.oraclecloud.com`, `site: CX_1` |

## How the REST host was found
1. `jobs.akamai.com` refuses automated clients. The Playwright capture got **403 "Access Denied"**, and even `/robots.txt` returns that Akamai error page. The capture was not retried.
2. `GET https://jobs.akamai.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?...` returned 200 from `server: Oracle API Gateway`, but with the CE app's HTML **"Page not found"** page. The vanity domain does not proxy `/hcmRestApi`. That 404 page's "home" button links to `https://fa-extu-saasfaprod1.fa.ocs.oraclecloud.com:443/hcmUI/CandidateExperience`.
3. On the pod, the site's `siteSettings` say `"apiBaseUrl" : "https://fa-extu-saasfaprod1.fa.ocs.oraclecloud.com:443"` and reference `https://jobs.akamai.com/`. This confirms the pod is the API host that Akamai's career site uses.

## Recommended feed
- **Request:** `GET https://fa-extu-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber=CX_1,limit=200,offset=N,sortBy=POSTING_DATES_DESC` (this is exactly the shared `oracle` adapter's request)
- **Headers:** `Accept: application/json`, browser UA. No auth or cookies needed. Plain httpx got 200.
- **Pagination:** `offset` in steps of 200 until `TotalJobsCount` (281 means 2 requests). The response is `items[0].requisitionList[]`, and `items[0].TotalJobsCount` is the total.
- **Detail:** the adapter's `recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id="<id>",siteNumber=CX_1` on the same host
- **Job links for emails:** `https://jobs.akamai.com/en/sites/CX_1/job/<Id>`. This is for people. Bots get 403 on that host. The pod form `https://fa-extu-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/<Id>` also works.

## Field map
| Job field | Path (`requisitionList[]`) | Notes |
|---|---|---|
| id | `Id` | e.g. 4252 |
| title | `Title` | |
| location(s) | `PrimaryLocation` + `secondaryLocations[].Name` | Often only the country ("United States", "Poland"). `PrimaryLocationCountry` is the ISO code. |
| posted date | `PostedDate` | "2026-10-19" |
| description | `ShortDescriptionStr`, `ExternalQualificationsStr`, `ExternalResponsibilitiesStr` | |
| employment type | `WorkerType` / `JobType` / `ContractType` | **all empty** for Akamai, so use titles |
| department | `Department` / `JobFamily` | `JobFamily` is empty for all 281 |
| workplace | `WorkplaceType` | |

## Totals (observed 2026-10-19/20)
- **Feed, no filters:** **281** (`TotalJobsCount` 281, 281 unique `Id`, 2 requests).
- **Live careers page, no filters:** **281**. A Playwright render of the same CE site on its pod host, `https://fa-extu-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs` (`/requisitions` redirects there), showed "JOBS 281 / JOB SEARCH RESULTS 281". The page's own REST call (limit 25, with facets) returned `TotalJobsCount: 281`. The vanity page itself could not be observed (403).
- **By country:** US 96, Poland 62, Canada 22, India 19, Japan 12, Costa Rica 10, Israel 9, …
- **Intern/student:** **4** by title:
  - 4252 Intern - Corporate Sustainability (United States, 2026-10-19)
  - 3978 Field Marketing Intern (Poland)
  - 4108 Emerging Talent Intern - Part-Time Remote (Spain)
  - 3114 Intern - Business Operations Analyst (UAE Nationals Only)

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://fa-extu-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?… | ALLOW | robots.txt is 404, so no robots |
| https://fa-extu-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/… | ALLOW | same |
| https://jobs.akamai.com/en/sites/CX_1/jobs | (robots.txt answers 403 Access Denied, which counts as 4xx, so allowed) | The host refuses automated clients, so it is not used. |

## Anti-bot / quirks
- The vanity host is protected by Akamai's edge (403 "Access Denied", with a reference number). The Oracle pod host is reachable directly and did not challenge in 4 requests plus 1 render.
- Akamai leaves `WorkerType`, `JobType` and `JobFamily` empty, so the intern decision rests on titles.

## Recommended checker
```yaml
- key: akamai
  name: Akamai
  adapter: oracle
  settings:
    host: fa-extu-saasfaprod1.fa.ocs.oraclecloud.com
    site: CX_1
    job_url: https://jobs.akamai.com/en/sites/CX_1/job/{id}
  careers_url: https://jobs.akamai.com/en/sites/CX_1/jobs
```

## Evidence
- Sample: `discovery/samples/akamai.json` is the career page's own REST response (limit 25, with facets, 67 KB).
- Capture: `discovery/captures/akamai/` (403 Access Denied).
- Requests: 2 REST pages, 2 vanity-host REST probes (the CE 404 page), 1 Playwright render on the pod host, and robots.txt fetches.
