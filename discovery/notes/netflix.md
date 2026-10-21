# Netflix (`netflix`)

**Status:** verified-feed (Eightfold, legacy v2 API; paging drops jobs at random)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://jobs.netflix.com/ (Next.js). "View roles" and the team pages, including `/careers/internships`, link `https://explore.jobs.netflix.net/careers`. |
| Hiring system | **Eightfold v2** career site (`explore.jobs.netflix.net`, domain `netflix.com`). The ATS ids are Workday-style (`JR43080`), but no public Workday tenant exists: `netflix.wd1` and `netflix.wd5` return 422. |
| Second site | **Netflix House**: jobs.netflixhouse.com goes to `https://apply.netflixhouse.com/careers` (Eightfold v2, domain `netflixhouse.com`). It has 21 venue jobs (crew, retail, show roles, facilities), 0 internships, and none of them is on the main site. jobs.netflix.com links it. It is optional, as a second entry `netflix-house` with `{host: apply.netflixhouse.com, domain: netflixhouse.com, api: v2}`. |
| Recommended adapter | shared `eightfold`, `api: v2` |

## Recommended feed
- **Request:** `GET https://explore.jobs.netflix.net/api/apply/v2/jobs?domain=netflix.com&start=N&num=10`, with a browser UA and `Accept: application/json`. No cookies.
- **Pagination:** 10 per page. `num=25` and `num=100` are ignored. Step `start` by 10 to `count`: 40 requests for 397 jobs.
- **PCSX** (`/api/pcsx/search?domain=netflix.com`) returns 403 "PCSX is not enabled for this user."
- **Order:** `sort_by` is ignored: `timestamp` gives the same order as the default. The default is `t_create` descending, except that one old pinned job (`AJRT30201`, created 2024-07-23) always comes first. `t_create` is **day-granular** (always midnight UTC).
- **Detail:** `GET /api/apply/v2/jobs/<id>?domain=netflix.com`. The list already includes `job_description`.

## Field map (`positions[]`)
| Job field | Path | Example |
|---|---|---|
| id | `id` | 790318904468 |
| requisition | `display_job_id` = `ats_job_id` | `JR42989` |
| title | `name` | "Software Engineer Intern - Summer 2027" |
| locations | `locations[]` ("City,State,Country") | `["Los Gatos,California,United States of America"]` |
| url | `canonicalPositionUrl` (`https://explore.jobs.netflix.net/careers/job/<id>`) | |
| posted | `t_create` (day) / `t_update` (seconds) | |
| team | `department` | Engineering 85, Data & Insights 51, Feature Animation 45, Advertising 36, … |

## Totals (observed 2026-10-20 UTC)
- **Feed:** `count` 397 during both scans, 395 at the 03:19Z recheck.
- **Page:** a Playwright render of https://explore.jobs.netflix.net/careers?domain=netflix.com showed "397 open jobs".
- **Unique ids per full scan:**
  - Scan 1: 396, with 1 id twice (positions 248 and 251) and 1 job never returned.
  - Scan 2, about an hour later: 395, with 2 ids twice (positions 78–81).
  - The union of the two scans is exactly 397.
- **Interns: 3.** "Software Engineer Intern - Summer 2027", "Machine Learning/AI Infrastructure Engineering Intern (AI Platform) PhD, Winter 2027" and "Video Algorithms Intern, Video Coding (Gaussian Splatting), Fall 2026".

## Anti-bot / quirks
- **Jobs that share a day swap places between page requests**, so a single full scan sees duplicates and misses 0.25–0.5% of jobs. The shared adapter's `check_total(tolerance=3)` passes such a scan, which hides the gap. Two rules follow:
  - Do not mark a job removed until it is missing from two consecutive full scans.
  - Do not send a "new" alert for a job id that was seen before.

  Optionally, when the unique count is below `count`, re-read the pages around the duplicated positions.
- No 429 in about 55 requests at ≥2.6 s spacing. Use `min_interval: 2.5`.
- The job page calls ipapi.co for geolocation, which returned 429 to the browser. The API does not need it.

## robots.txt
| URL | Verdict | Rule |
|---|---|---|
| `https://explore.jobs.netflix.net/api/apply/v2/jobs?domain=netflix.com&start=0&num=10` | ALLOW | `Allow: /api/apply` (Eightfold standard file) |
| `https://explore.jobs.netflix.net/careers/job/<id>` | ALLOW | `Allow: /careers` |
| `https://apply.netflixhouse.com/api/apply/v2/jobs?domain=netflixhouse.com&…` | ALLOW | `Allow: /api/apply` |
| `https://jobs.netflix.com/careers/internships` | ALLOW | no robots.txt |

## Recommended checker
```yaml
- key: netflix
  name: Netflix
  careers_url: https://jobs.netflix.com/
  checker: eightfold
  settings: {host: explore.jobs.netflix.net, domain: netflix.com, api: v2, min_interval: 2.5}
# optional: key netflix-house, checker eightfold, settings {host: apply.netflixhouse.com, domain: netflixhouse.com, api: v2}
```

## Evidence
- Sample: `discovery/samples/netflix.json` holds v2 page 1 of the main site and of Netflix House, trimmed.
- Requests: about 55 to explore.jobs.netflix.net (2 full scans, a 4-page re-read, num and PCSX tests, 1 render), 5 to apply.netflixhouse.com, and 3 page loads on jobs.netflix.com.
