# Salesforce (`salesforce`)

**Status:** blocked (HTTP 429 from the hiring system on this network)   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://www.salesforce.com/company/careers/jobs/ (bookmark: the same page with `jobtype=Intern`, US+Canada). The Playwright capture got **403 "Access Denied"** (Akamai). |
| Hiring system | **Workday**, tenant `salesforce`, host `salesforce.wd12.myworkdayjobs.com`. robots.txt lists 9 career sites: `External_Career_Site` (main), `Futureforce_Internships`, `Futureforce_NewGradRoles`, `Mulesoft_Careersite`, `Salesforce_Research`, `Tableau`, `Datorama`, `Heroku`, `Slack`. |
| Recommended adapter | shared `workday` adapter with `sites: [External_Career_Site, Futureforce_Internships]`, **if the 429s stop** (see below) |

## What happened
| Time (local) | Request | Result |
|---|---|---|
| 18:42:57, 18:43:15, 18:44:47 (earlier agent) | `POST …/External_Career_Site/jobs` unfiltered | 429 ×3. A site page load in between, which set `PLAY_SESSION`/`CALYPSO_CSRF_TOKEN` cookies, did not help. |
| 18:44:37 (earlier agent) | `POST …/Futureforce_Internships/jobs` unfiltered | **200**, `total: 25` (first title "Summer 2027 Intern - Software Engineer (Security/Government)") |
| 18:45:09 (earlier agent) | `GET …/External_Career_Site/siteMap.xml` | 429 |
| 18:45:13 (earlier agent) | `POST …/External_Career_Site/jobs` with `searchText: "intern"` | **200**, `total: 803` (a fuzzy match, so the site has at least 803 jobs) |
| 18:45:35 (earlier agent) | `POST …/Futureforce_Internships/jobs` | 429 |
| 19:22:45 (me, after 37 min with no traffic to the host) | `POST …/External_Career_Site/jobs` unfiltered | 429 |
| 19:23:22 (me) | Playwright render of `https://salesforce.wd12.myworkdayjobs.com/en-US/External_Career_Site` | The page loaded, but its own `POST …/jobs` got 429 and it showed "**0 JOBS FOUND**" |
| 19:23:59 (me) | `POST …/Futureforce_Internships/jobs` | 429 |

Every 429 has the Workday JSON body `{"errorCode":"HTTP_429","errorCaseId":"…","httpStatus":429,…}` behind Cloudflare (`server: cloudflare`, no `Retry-After`). The pattern (200s mixed with 429s on the same endpoint, and a real browser refused too) points to per-IP rate limiting on this tenant. It is not a robots rule, a missing cookie or a header problem. Following the rules, I did not try to get around it (no facet-split queries, no browser automation of the list).

## If it opens up (re-test from the deployment host)
- **Request:** `POST https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/<site>/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}` and headers `Content-Type: application/json`, `Accept: application/json`.
- **Pacing:** keep it well under 1 request/second for this host (e.g. 1 per 5 s). External_Career_Site probably has more than 1,000 jobs, so 50+ pages.
- **Sites:** `External_Career_Site` is the complete list. Include `Futureforce_Internships` (25 jobs on 2026-10-19) because the intern postings may live only there. Whether they are also on External could not be checked. The brand sites (Mulesoft, Tableau, Slack, Heroku, Datorama, Research) and Futureforce_NewGradRoles are probably filtered views of External, also unchecked.
- **Health:** a 429 from the first page should mark the company "blocked today" rather than "0 jobs".

## Totals (observed 2026-10-19)
- **Feed, no filters:** not obtainable from this network. Partial data from the earlier agent's one-off 200s: Futureforce_Internships `total: 25`, and External_Career_Site with `searchText:"intern"` `total: 803`.
- **Live careers page:** not observable. salesforce.com answered 403, and the Workday site showed "0 JOBS FOUND" because of the 429.
- **Intern/student:** unknown. Futureforce_Internships held 25 postings, which are presumably all interns.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/External_Career_Site/jobs` | ALLOW | no matching rule |
| `POST https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/Futureforce_Internships/jobs` | ALLOW | no matching rule |
| `https://salesforce.wd12.myworkdayjobs.com/en-US/External_Career_Site` | ALLOW | no matching rule (`Allow:` for all 9 sites, `Disallow: /refreshFacet/`) |

## Fallback
1. Re-test the Workday settings above from the deployment host. If they answer 200, mark the company verified with `sites: [External_Career_Site, Futureforce_Internships]`.
2. Otherwise use Workday job alerts ("Get email alerts" on the External_Career_Site and Futureforce_Internships sites) and the SimplifyJobs cross-check.

## Evidence
- Sample: `discovery/samples/salesforce.json` is the 429 body the browser render received.
- Capture: `discovery/captures/salesforce/` (403 Access Denied on salesforce.com).
- Requests (this run): 2 CXS POSTs, 1 robots.txt and 1 Playwright render. The earlier agent made 6 CXS/sitemap requests and 1 site page load.
