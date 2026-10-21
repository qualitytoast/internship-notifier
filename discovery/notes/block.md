# Block (`block`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://block.xyz/careers/jobs. The bookmark `?employeeTypes[]=Intern` is a filtered view of it. |
| Hiring system | Greenhouse, **one board `block` for every Block brand**. block.xyz renders its own list and job pages (`https://block.xyz/careers/jobs/<gh id>`) from it, on the server. |
| Recommended adapter | shared `greenhouse` adapter, `board: block` |

## Brands (Square, Cash App, Afterpay, TIDAL, Bitkey, Proto)
- The board's metadata **"Brands"** splits the 219 jobs as: Square 125, Cash App 39, Block 31, Afterpay 20, TIDAL 3, Proto 1. **"Business Unit"** splits them as: Square 127, Cash 59, Centralized Block 28, TIDAL 3, null 2. Bitkey has no postings today.
- The brand careers pages all lead to this same list:
  - `squareup.com/us/en/careers` goes to `careers.squareup.com/us/en`, which links to `block.xyz/careers/jobs?businessUnits[]=square`.
  - `cash.app/careers` redirects to `block.xyz/careers/jobs?businessUnits[]=cashapp`.
  - `afterpay.com/en-US/careers` returns HTTP 404, but its HTML links to `block.xyz/careers/jobs?businessUnits[]=afterpay&locations[]=…`.
  - `tidal.com/careers` returns **403** to httpx and to headless Chromium (bot wall), so I did not pursue it. `block.xyz/careers/jobs?businessUnits[]=tidal` shows "3 OPEN JOBS", the same 3 TIDAL jobs that are on the board.
- The probe's other tokens are empty: Greenhouse `squareup` and `square`, and Workable `square`. There is no separate brand board.

## Recommended feed
- **Request:** `GET https://boards-api.greenhouse.io/v1/boards/block/jobs`. Use a normal UA; no auth is needed.
- **Pagination:** none. `meta.total` equals the number of jobs. The response is 475 KB without `content`, because the metadata includes pay-zone ranges.
- **Detail (optional):** `GET https://boards-api.greenhouse.io/v1/boards/block/jobs/<id>` adds the description, departments and offices.

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `jobs[].id` | e.g. 5411800008 |
| title | `jobs[].title` | |
| location(s) | `jobs[].location.name` | e.g. "Bay Area, CA, United States of America", "Toronto, Ontario , Canada" (note the stray space) |
| url | `jobs[].absolute_url` | `http://block.xyz/careers/jobs/<id>?gh_jid=<id>` uses **http**. The site itself links `https://block.xyz/careers/jobs/<id>`. |
| posted date | `jobs[].first_published` | |
| employment type | metadata **"Employee Type"** | "Regular" / "Intern" (null on 2 jobs). The shared adapter's `_employment_type` only reads names containing employment/job/worker/position/time type, so it **misses "Employee Type"**. Both of today's interns have "Intern" in the title anyway. Consider adding "employee type" to that list. |
| brand | metadata "Brands", "Business Unit" | see above |
| department / team | metadata "Career Site Function" (Sales, Software Engineering, …), "Job Family Group" | `departments[]` in the detail call |
| other | metadata "Position open to remote" (true/false), salary zones | `company_name` is always "Block" |

## Totals (observed 2026-10-20 ~00:05Z)
- **Feed, no filters:** **219**. The probe an hour earlier saw 218.
- **Live careers page, no filters:** **219**. A Playwright render of https://block.xyz/careers/jobs showed "219 OPEN JOBS" and "SHOWING 50 OF 219", with 50 job links rendered.
- **Intern/student:** **2**, both "Applied Research Intern, Proactive Intelligence & Customer World Models (PhD / Graduate Co-op)" with Employee Type "Intern":
  - 5108007008, Bay Area, CA
  - 5108009008, Toronto

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/block/jobs | ALLOW | no matching rule (only `/embed/` is disallowed) |
| https://block.xyz/careers/jobs | ALLOW | `Allow: /` |
| https://cash.app/careers | ALLOW | `Allow: /` |
| https://squareup.com/us/en/careers | ALLOW | no matching rule |
| https://www.afterpay.com/en-US/careers | ALLOW | `Allow: /` |
| https://tidal.com/careers | ALLOW | `Allow: /`. The server still returns 403 (bot wall), so it is not used. |

## Anti-bot / quirks
- block.xyz shows no challenge. The job list is rendered on the server; the browser makes no Greenhouse call.
- tidal.com is behind a bot wall. Its jobs are on the shared board, so nothing is lost.

## Recommended checker
```yaml
- key: block
  name: Block
  adapter: greenhouse
  settings:
    board: block
  careers_url: https://block.xyz/careers/jobs
```

## Evidence
- Sample: `discovery/samples/block.json` is the raw detail response for TIDAL job 5411800008 (14 KB). It shows the Brands, Business Unit and Employee Type metadata.
- Capture: `discovery/captures/block/` (the bookmark with the Intern filter: "2 OPEN JOBS").
