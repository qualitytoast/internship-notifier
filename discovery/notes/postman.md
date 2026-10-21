# Postman (`postman`)

**Status:** verified-feed   ·   **Checked:** 2026-10-19 (US Central); Workday re-checked 2026-10-20 00:27 UTC

| | |
|---|---|
| Official careers URL | https://www.postman.com/company/careers/open-positions/ ("Current openings"). It is linked from https://www.postman.com/company/careers/. |
| Hiring system | **Workday**: tenant `postman`, site `careers`, data centre wd108 (`https://postman.wd108.myworkdayjobs.com/careers`). postman.com renders a **cached copy** of it: `GET https://www.postman.com/_mk-www-next/api-cache/careers-jobs.json` returns `{"jobs":[…], "meta":{"total":25, "updated_at":"2026-10-17T02:24:44Z", "source":"workday_cxs", "careersUrl":"https://postman.wd108.myworkdayjobs.com/careers"}}`. |
| Recommended adapter | shared `workday`: `{host: postman.wd108.myworkdayjobs.com, tenant: postman, site: careers}` |

The probe hit Greenhouse `postman`, but that is not an empty board: `boards-api.greenhouse.io/v1/boards/postman/jobs` returns **404** "Job not found". There is no Greenhouse board.

## Recommended feed
- **Request:** `POST https://postman.wd108.myworkdayjobs.com/wday/cxs/postman/careers/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}` and headers `Content-Type: application/json`, `Accept: application/json`. No cookies or CSRF token needed.
- **Pagination:** `offset` steps of 20. `total` is 25 at offset 0; 2 requests cover everything.
- **Detail (optional):** `GET https://postman.wd108.myworkdayjobs.com/wday/cxs/postman/careers/job/{externalPath without /job/}`. It has `jobPostingInfo.jobDescription` (HTML), `startDate` (2026-10-09), `timeType`, `jobReqId`, `location` and `country`.

## Field map
Paths are relative to `jobPostings[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | `bulletFields[0]` (`JR1000061`) | the requisition id. It also ends `externalPath` (`…_JR1000061`). |
| title | `title` | |
| location(s) | `locationsText` | Today: San Francisco, CA, US 12, Bangalore, India 9, Austin, TX, US 2, NYC, NY, US 2. All are single-location; Workday would show "N Locations" for a multi-location job, and the detail would then have the list. |
| url (detail/apply) | `https://postman.wd108.myworkdayjobs.com/careers` + `externalPath` | e.g. `/careers/job/Bangalore-India/Software-Engineer--Backend---Automation-Testing_JR1000061` |
| posted date | `postedOn` (relative, "Posted 10 Days Ago") | the detail `startDate` gives the absolute date |
| description / snippet | detail only | the postman.com cache has a one-line `description` |
| employment type | `timeType` ("Full time") | facet `workerSubType`: Regular 21, Management 4 |
| department / team | facet `jobFamilyGroup` (only "POSTMAN", 25) | the postman.com cache has `department` (Engineering, …) |

## Totals
- **Feed, no filters:** **25**. CXS `total: 25`, 25 unique JR ids, at 2026-10-19 23:50 UTC and again at 2026-10-20 00:27 UTC.
- **Live careers page, no filters:** **25**. A Playwright render of the open-positions page (2026-10-19 23:50 UTC) showed "**25 jobs found**". Its data file `careers-jobs.json` held the same 25 JR ids as Workday: none only in one source.
- **Intern/student:** **0**. Every posting is full time.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://postman.wd108.myworkdayjobs.com/wday/cxs/postman/careers/jobs | ALLOW | no matching rule |
| https://postman.wd108.myworkdayjobs.com/careers | ALLOW | no matching rule |
| https://www.postman.com/company/careers/open-positions/ | ALLOW | `Allow: /` |
| https://www.postman.com/_mk-www-next/api-cache/careers-jobs.json | ALLOW | `Allow: /` |

## Anti-bot / quirks
- No challenge on either host.
- The postman.com cache was **2.9 days old** (`meta.updated_at` 2026-10-17T02:24Z), so a new role would reach the website late. Poll Workday directly and use postman.com only as a cross-check.
- The usual Workday quirks apply: `total` is only reliable at offset 0, and `postedOn` is relative.

## Recommended checker
```yaml
- key: postman
  name: Postman
  adapter: workday
  careers_url: https://www.postman.com/company/careers/open-positions/
  settings:
    host: postman.wd108.myworkdayjobs.com
    tenant: postman
    site: careers
```

## Evidence
- Sample: `discovery/samples/postman.json`, the raw CXS response for offset 0 (20 postings, facets, total 25; 6 KB).
- Capture: `discovery/captures/postman/` (the /company/careers page).
- Requests: the previous run made 8 (robots, Greenhouse 404, the open-positions HTML and one Playwright render, CXS ×2, one detail). This run made 2 (robots and one CXS page).
