# Workday (`workday`)

**Status:** verified-feed (3 Workday career sites)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://www.workday.com/en-us/company/careers/overview.html links "Search jobs" to `https://workday.wd5.myworkdayjobs.com/Workday/?source=Careers_Website`. The early-career page https://www.workday.com/en-us/company/careers/early-career.html links `…/Workday_Early_Career/?source=Careers_Website_ec`, which is the bookmark. |
| Hiring system | Workday (tenant `workday`, data centre wd5). robots.txt lists 4 public sites: `Workday`, `Workday_Early_Career`, `Workday_Executive_Site`, `Workday_Jobs`. |
| Recommended adapter | shared `workday`, `sites: [Workday, Workday_Early_Career, Workday_Jobs]` |

## Recommended feed
- `POST https://workday.wd5.myworkdayjobs.com/wday/cxs/workday/<site>/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}` and headers `Content-Type: application/json`, `Accept: application/json`. No cookies.
- Pagination: offset/limit 20. `total` is only in the offset-0 response. Full run: 20 + 1 + 2 = 23 requests.
- Detail: `GET /wday/cxs/workday/<site><externalPath>` returns `jobPostingInfo` (`jobDescription`, `jobReqId`, `location`, `timeType`, `startDate`).

## Field map (`jobPostings[]`)
| Job field | Path | Notes |
|---|---|---|
| id | `externalPath` | differs per site for the same requisition |
| requisition id (dedupe key) | `bulletFields[0]` (e.g. `JR-0110193`) | also `jobPostingInfo.jobReqId` in the detail |
| title / location | `title` / `locationsText` | |
| url | `https://workday.wd5.myworkdayjobs.com/en-US/<site><externalPath>` | |
| posted | `postedOn` (relative) | detail `startDate` is an ISO date |

## Totals (observed 2026-10-20 UTC)
| Site | Feed `total` | Page (Playwright) | Unique to this site | Interns |
|---|---|---|---|---|
| `Workday` (main) | 386 | "386 JOBS FOUND" | 384 | 1 ("Technical Support Delivery Intern", also on Early_Career) |
| `Workday_Early_Career` | 12 | "12 JOBS FOUND" | 10 | 10 (9 only here) |
| `Workday_Jobs` | 22 | "22 JOBS FOUND" | 22 (no overlap with any site) | 0 |
| `Workday_Executive_Site` (not watched) | 1 | – | 1 ("Vice President of Engineering, Data Cloud") | 0 |
| **Watched, deduped** | **418 requisitions** (420 postings) | 420 | | **10** |

- `Workday_Jobs` holds 22 US engineering, consulting and analytics roles in Pleasanton, Atlanta, Mason and Frisco. None of them is on the main site, so it is watched. It costs 2 requests.
- **False positives:** the title rule (`student`) matches 4 main-site roles about Workday's *Student* product, for example "Principal Functional Consultant - Higher Education (Workday Student Financials)" and "Student Financial Aid Consultant, Higher Education & Nonprofit". They are not internships. Consider a company-level exclusion for "Workday Student".
- No site is near Workday's 2000-result cap.

## robots.txt
| URL | Verdict | Rule |
|---|---|---|
| `https://workday.wd5.myworkdayjobs.com/wday/cxs/workday/{Workday,Workday_Early_Career,Workday_Jobs}/jobs` | ALLOW | no matching rule. The file has `Allow: /Workday/`, `/Workday_Early_Career/`, `/Workday_Executive_Site/`, `/Workday_Jobs/` and `Disallow: /refreshFacet/`. |
| `https://workday.wd5.myworkdayjobs.com/Workday_Early_Career` (page) | ALLOW | no matching rule |

## Quirks
- The same requisition gets a different `externalPath` on each site. The adapter's `site:path` id would therefore alert twice for the 2 shared requisitions, so dedupe by `bulletFields[0]`.
- Every posting is `timeType` "Full Time", including the internships, so type facets cannot be used to find interns. Use titles.

## Recommended checker
```yaml
- key: workday
  name: Workday
  careers_url: https://www.workday.com/en-us/company/careers/overview.html
  checker: workday
  settings:
    host: workday.wd5.myworkdayjobs.com
    tenant: workday
    sites: [Workday, Workday_Early_Career, Workday_Jobs]   # Workday_Executive_Site skipped (VP roles only)
```

## Evidence
- Sample: `discovery/samples/workday.json` holds first-page excerpts and facets for the 3 sites, including the "Student" false positives.
- Requests: 29 to workday.wd5 (full enumeration of 4 sites plus 3 Playwright renders), plus 5 to www.workday.com pages.
