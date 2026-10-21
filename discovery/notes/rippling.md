# Rippling (`rippling`)

**Status:** verified-feed   ·   **Checked:** 2026-10-19 (US Central) = 2026-10-20 00:08–00:31 UTC

| | |
|---|---|
| Official careers URL | https://www.rippling.com/careers/open-roles (the bookmark adds `?search=intern`; track the unfiltered page). `https://ats.rippling.com/rippling/jobs` redirects here (307 → 308). |
| Hiring system | **Rippling Recruiting (own ATS)**, public job board `rippling` on `ats.rippling.com`. The detail JSON calls it `board.boardType: "CUSTOM"` with `boardURL: http://www.rippling.com/careers/open-roles`. The marketing page reads an Algolia copy of the same board. |
| Recommended adapter | new shared **`rippling`** adapter, `{board: rippling}`. The API is generic across Rippling customers: verified on a second board, `framework` (3 jobs). |

## Recommended feed (spec for the shared `rippling` adapter)
- **List (primary):** `GET https://ats.rippling.com/api/v2/board/{board}/jobs?page={p}&pageSize={n}`
  - Returns `{"items":[…], "page":0, "pageSize":1000, "totalItems":656, "totalPages":1}`.
  - `page` is **0-based**. `totalPages = ceil(totalItems / pageSize)`. `pageSize=1000` was accepted and returned all 656 rows in one call. `page=1&pageSize=500` returned exactly rows 500–655 of the full list, so the order is stable between pages.
  - Loop `page = 0 … totalPages-1`, or stop on an empty `items`.
- **Rows are per job × location, not per job.** Each item has exactly one entry in `locations[]`, and a job in 3 cities appears 3 times with the same `id`. Group by `id` and merge `locations`. Today the API returns 656 rows for 377 unique jobs.
- **List (alternative, one call):** `GET https://api.rippling.com/platform/api/ats/v1/board/{board}/jobs` returns a bare JSON array with the same 656 job × location rows. Its fields: `uuid`, `name`, `department{id,label}`, `url`, `workLocation{id,label}`. It has no pagination and less structured locations. Both endpoints returned identical id sets.
- **Detail (optional):** `GET https://ats.rippling.com/api/v2/board/{board}/jobs/{id}`. The same JSON is at `https://api.rippling.com/platform/api/ats/v1/board/{board}/jobs/{id}`; the two responses were byte-identical. Keys:
  - `uuid`, `name`, `companyName`, `createdOn` (ISO with tz), `url`
  - `description{company,role}` (HTML)
  - `workLocations[]` (strings)
  - `department{name, base_department, department_tree[]}`
  - `employmentType{label,id}`, e.g. `{"label":"TEMP","id":"Temporary / Intern"}` on the intern posting
  - `payRangeDetails[]`, `board{…}`, `unlistedFromSearch`, `activeJobApplication` (application form questions)
  - `jsonLd` (null here)
- **Unknown board:** the API returns HTTP 404 `{"error_code":"RESOURCE_NOT_FOUND","message":"Job Board not found","resource":null}`. Treat this as a configuration error.
- **Headers:** a normal browser UA. No auth, cookies or tokens.

## Field map (v2 list rows)
| Job field | Response path | Notes |
|---|---|---|
| id | `items[].id` (UUID) | the same as `uuid` in v1/detail; repeated once per location |
| title | `items[].name` | **trim**: 93 of 656 rows have leading or trailing spaces (e.g. `" Account Executive, Broker Channel (Arkansas) "`) |
| location(s) | `items[].locations[0]`: `{name, city, state, stateCode, country, countryCode, workplaceType}` | `workplaceType` ∈ ON_SITE / REMOTE / HYBRID. Merge across the rows of one id, e.g. "San Francisco, CA" + "New York, NY" + "Seattle, WA". |
| url (detail/apply) | `items[].url` | `https://ats.rippling.com/{board}/jobs/{id}`. It serves the job page (200) even though the board root redirects. |
| posted date | not in list | detail `createdOn` |
| description / snippet | not in list | detail `description.role` (HTML) |
| employment type | not in list | detail `employmentType` ("Temporary / Intern" for interns). Titles are enough for filtering. |
| department / team | `items[].department.name` | e.g. Engineering, Sales. The detail also has a `department_tree` (e.g. Engineering > Eng Interns). |
| other | `items[].language` (`en-US` 637 rows, `en-GB` 19) | |

## Totals (observed 2026-10-20 00:08–00:31 UTC)
- **Feed, no filters:** **377** unique jobs. v2 `totalItems` is 656 rows; the v1 array is also 656 rows; both have the same 377 ids.
- **Live careers page, no filters:** a Playwright render of `/careers/open-roles` showed "**656 roles** across all departments in all locations". The page lists one card per job × location from Algolia index `careers_en-US_production`: `nbHits` 656, 50 hits per page, 14 pages. That is the same 656 rows, i.e. **377 jobs**.
  - Earlier (23:53 UTC) Algolia had 660 rows / 378 jobs. The extra was closed job `789e158e…` "Manager, Strategic Enterprise Sales", whose URL already redirected to open-roles. It had dropped out by 00:08. So the board API is the fresher source.
- **Intern/student:** **5** (all Engineering):
  - f255bf03 Data Science Intern - Summer 2027 (San Francisco)
  - f64b6158 Full Stack Software Engineer Intern - Summer 2027 (SF, NY, Seattle)
  - f9de04c3 Machine Learning Software Engineer Intern - Summer 2027 (SF)
  - 82c13e8f Machine Learning Software Engineer Intern - Winter 2027 (SF)
  - a07e4e46 Software Engineer Intern - Backend Focused - Summer 2027 (NY, SF, Seattle)

  The bookmark search "intern" showed "11 roles". That is 11 job × location cards: the 5 interns plus 2 "Internal Posting — Senior Software Engineer, Backend — …" jobs, which only match the substring.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://ats.rippling.com/api/v2/board/rippling/jobs?page=0&pageSize=1000 | ALLOW | no matching rule (ats.rippling.com only disallows `/internal/`) |
| https://ats.rippling.com/api/v2/board/rippling/jobs/{id} | ALLOW | no matching rule |
| https://ats.rippling.com/rippling/jobs/{id} | ALLOW | no matching rule |
| https://api.rippling.com/platform/api/ats/v1/board/rippling/jobs (+ `/{id}`) | ALLOW | robots.txt is 404, so allow-all |
| https://www.rippling.com/careers/open-roles | ALLOW | `Allow: /` |

## Anti-bot / quirks
- There was no bot challenge on ats.rippling.com, api.rippling.com or www.rippling.com (about 23 requests in total across two runs).
- Match intern words as whole words. "Internal Posting — …" titles (2 today) contain "Intern" as a substring.
- The Algolia search key on the marketing page is a public search-only key. The board API is the hiring system's own feed and was fresher, so do not use Algolia.
- Other Rippling customers' boards live at `https://ats.rippling.com/{slug}/jobs` (e.g. `framework`). The same two API paths work with their slug, and the v2 rows had the same shape there.

## Recommended checker
```yaml
- key: rippling
  name: Rippling
  adapter: rippling
  careers_url: https://www.rippling.com/careers/open-roles
  settings:
    board: rippling
    page_size: 1000          # v2 pageSize; loop page=0..totalPages-1
  # adapter: group rows by id, merge locations[], strip titles; url = items[].url
  # health: unique ids should be > 0; totalItems counts rows, not jobs
```

## Evidence
- Sample: `discovery/samples/rippling.json` is the raw v2 response for `page=1&pageSize=500` (156 rows, 61 KB). It shows the pagination envelope and the per-location rows.
- Capture: `discovery/captures/rippling/` (the bookmark render with Algolia `feed_0_*.json`).
- Requests: the previous run made 16 (v1/v2 list, Algolia once, detail ×2, framework ×2, bad slug, robots). This run made 6 (v1 list, v2 list, v2 page=1, robots ×3) plus one Playwright render.
