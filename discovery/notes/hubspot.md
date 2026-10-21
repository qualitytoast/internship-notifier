# HubSpot (`hubspot`)

**Status:** needs-custom. The official list is currently **empty** (HubSpot's job source is broken or migrating).   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://www.hubspot.com/careers/jobs (bookmark: the same page with `?q=intern&page=1`). Job pages are `https://www.hubspot.com/careers/jobs/<id>`. |
| Hiring system | HubSpot's own careers front end (HubSpot CMS) calls its own GraphQL API `https://wtcfns.hubspot.com/careers/graphql`. The server's stack trace (`JobsApi … apollo-datasource-rest`) and its upstream error `{"status":404,"error":"Job not found"}` show that this API proxies a **Greenhouse** job board, and `boards-api.greenhouse.io/v1/boards/hubspot` now answers **404 "Job board not found"**. The talent community form is on **Gem** (`www.gem.com/form?formID=56b05c22-…`). North American intern applications go to **RippleMatch** (`app.ripplematch.com/v2/public/company/hubspot`). |
| Recommended adapter | `custom:hubspot`, one GraphQL POST (below). It follows whatever board HubSpot's site uses, so it starts working again when HubSpot fixes its backend. |

## What the site does
- `POST https://wtcfns.hubspot.com/careers/graphql` with header `Content-Type: application/json` and this body, copied from the page:
  ```json
  {"operationName":"Jobs",
   "variables":{"departmentIds":[],"officeIds":[],"languages":[],"roleTypes":[]},
   "query":"query Jobs($departmentIds: [Int], $officeIds: [Int], $languages: [String], $roleTypes: [String], $searchQuery: String) { jobs(departmentIds: $departmentIds, officeIds: $officeIds, languages: $languages, roleTypes: $roleTypes, searchQuery: $searchQuery) { id title department { name id } office { id location } location { name } } }"}
  ```
  The bookmark adds `"searchQuery":"intern"`. The page reads `#roleType=intern` for its intern view. There is no pagination: one response holds the whole list.
- **Today the response is** `{"errors":[{"message":"404: Not Found","path":["jobs"],"extensions":{"code":"INTERNAL_SERVER_ERROR","response":{"status":404,"body":{"status":404,"error":"Job not found"}}}}],"data":{"jobs":null}}` (867 bytes). It was the same in the 2026-10-19 capture and in my httpx call, so the page renders "No jobs are currently listed."
- **Expected fields when it works** (from the query): `id` (the Greenhouse-style id used in `/careers/jobs/<id>`), `title`, `department{id,name}`, `office{id,location}` and `location{name}`. The job URL is `https://www.hubspot.com/careers/jobs/<id>`.

## Totals (observed 2026-10-19/20)
- **Feed, no filters:** **0**, a GraphQL error (see above). It must be treated as "feed broken", **not** as zero jobs.
- **Live careers page, no filters:** **0**. A Playwright render of `/careers/jobs` showed "No jobs are currently listed. Waiting for the perfect fit? Join our Talent Community!"
- **Intern/student:** 0 visible. Aggregators (Getro/General Catalyst, builtindublin.ie) still show HubSpot's 2027 EMEA co-op and internship postings dated 2026-10-05, but marked "no longer accepting applications". The postings evidently disappeared when the board was removed.

## Other sources checked
| Source | Result |
|---|---|
| `GET https://boards-api.greenhouse.io/v1/boards/hubspot/jobs` | 404 `{"status":404,"error":"Job not found"}`. Board info: 404 "Job board not found". `hubspotjobs` is also 0 (probe). |
| Gem `jobs.gem.com/api/public/graphql/batch`, `boardId: hubspot` | 200 with `jobPostings: []`, i.e. empty (or not a real board) |
| `https://www.hubspot.com/careers/emerging-talent` | "North America: Apply" goes to RippleMatch. "EMEA & LATAM: Apply" goes back to `/careers/jobs#roleType=intern`, which is empty. |
| `https://app.ripplematch.com/v2/public/company/hubspot` | **BLOCK**. The robots.txt fetch failed TLS verification ("unable to get local issuer certificate"), so robots is unreachable and treated as disallow. Not used. |

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://wtcfns.hubspot.com/careers/graphql` | ALLOW | robots.txt answers 403 `{"message":"Forbidden"}`, which counts as 4xx, so no robots |
| https://www.hubspot.com/careers/jobs | ALLOW | no matching rule |
| https://app.ripplematch.com/v2/public/company/hubspot | BLOCK | robots.txt unreachable |

## Recommended checker
```yaml
- key: hubspot
  name: HubSpot
  adapter: custom:hubspot
  settings:
    endpoint: https://wtcfns.hubspot.com/careers/graphql
    operation: Jobs            # body above; job URL https://www.hubspot.com/careers/jobs/{id}
  careers_url: https://www.hubspot.com/careers/jobs
  health:
    graphql_errors: fail       # errors[] / data.jobs == null means "source broken", alert, keep the previous jobs
```
**Follow-up:** re-run discovery for HubSpot in about a week. If the GraphQL starts answering again, compare its `id`s with Greenhouse/Gem/Ashby boards to learn the new token, and consider the shared adapter instead.

## Evidence
- Sample: `discovery/samples/hubspot.json` is today's GraphQL error response from the page itself.
- Capture: `discovery/captures/hubspot/` (2026-10-19, same 867-byte error and "No jobs are currently listed").
- Requests: 1 GraphQL POST, 2 Greenhouse calls, 1 Gem call, 1 Emerging Talent page, and 1 Playwright render. Third-party pages were read only through web search and fetch tools.
