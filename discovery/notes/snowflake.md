# Snowflake (`snowflake`)

**Status:** verified-feed (Phenom)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://careers.snowflake.com/us/en/search-results (the bookmark adds `?keywords=intern`) |
| Hiring system | **Phenom People** site (refNum `SNCOUS`) over **Ashby** (board `snowflake`). Every Phenom job's `applyUrl` is `https://jobs.ashbyhq.com/snowflake/<posting-id>`. |
| Recommended adapter | shared **`phenom`**, one call with a large `size`. The Ashby public board API is **not** complete; see below. |

## Phenom vs Ashby
- Phenom refineSearch `totalHits` is **368**, and the page shows "368 Jobs".
- The Ashby posting API `GET https://api.ashbyhq.com/posting-api/job-board/snowflake` returns **361** jobs, all `isListed: true`.
- Matching each Phenom `applyUrl` posting id against the Ashby board:
  - 361 match.
  - **0** are only on Ashby.
  - **7 are only on Phenom.** Their Ashby posting pages load, but `window.__appData.posting.isListed` is **false**. I checked 2 of the 7:
    - 3e1d38d8… "Solutions Architect, Frontier Engineering" (Tokyo)
    - b6fed204… "Software Engineer - Ingestion Execution Platform" (Bellevue, posted 2026-10-14)

  Snowflake posts these as *unlisted* on Ashby but shows them on its own careers site. The Ashby posting API never returns unlisted postings.
- **Use Phenom**: it matches the official page exactly, and Ashby misses 7 current jobs. The Ashby board is still a useful subset cross-check.

## Recommended feed
- **Request:** `POST https://careers.snowflake.com/widgets` with headers `Content-Type: application/json` and `Accept: application/json`. No cookies or CSRF.
- **Body (tested):**
  ```json
  {"lang":"en_us","deviceType":"desktop","country":"us","pageName":"search-results","ddoKey":"refineSearch",
   "from":0,"size":1000,"jobs":true,"counts":true,"all_fields":["category","country","state","city","type"],
   "selected_fields":{},"keywords":"","global":true,"sortBy":"","subsearch":"","clearAll":false,
   "jdsource":"facets","isSliderEnable":false,"siteType":"external","refNum":"SNCOUS"}
  ```
  - `size=1000` returned all 368 (`hits` 368) in one 1.2 MB response.
  - `size=100` with `from` 0…300 also gave 368 unique jobs here. Phenom's order can still reshuffle between calls (Adobe gave 62 duplicates), so keep using one call.

## Field map
Paths are relative to `refineSearch.data.jobs[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | **`jobSeqNo`** (`SNCOUS<jobId hex>EXTERNALENUS<posting id hex>`) | **`jobId` is NOT unique**: 356 unique across 368 rows. `jobId` is the Ashby *job*, and one job can have several postings. Examples: REQ21099 has 3 "Senior Compliance Analyst …" postings, and REQ20050 has 2. The Ashby posting id is the last 32 hex digits of `jobSeqNo`, or the tail of `applyUrl`. |
| req id | `reqId` (`REQ19908`, `ASHREQ-5362`) | shared by sibling postings |
| title | `title` | |
| location(s) | `multi_location[]` | Primary: `location` (`Chuo-ku, Tokyo, Japan`), plus `city`, `state`, `country` |
| url | built: `https://careers.snowflake.com/us/en/job/{jobSeqNo}/{slug}`, `slug = re.sub('[^A-Za-z0-9]+','-',title).strip('-')` | The page truncates the slug to 37 characters (`…/Senior-Technical-Support-Engineer-Obs`). Any slug works: the full slug gave 200 with jobDetail. |
| apply url | `applyUrl` | `https://jobs.ashbyhq.com/snowflake/<posting-id>` |
| posted date | `postedDate` | also `dateCreated` |
| description | `descriptionTeaser` | |
| employment type | `type` | `FullTime` 364, `Intern` 4. Two "Software Engineer Intern - Berlin" postings are typed `FullTime`, so rely on the title. |
| department | `category` | Engineering 118, Sales 53, Solution Engineering 50, … |

## Totals (observed 2026-10-20 00:31–00:40 UTC; re-checked 03:2x UTC: still 368)
- **Feed, no filters:** **368**. `size=1000` gave 368 rows and 368 unique `jobSeqNo`.
- **Live careers page, no filters:** **368**. A Playwright render of https://careers.snowflake.com/us/en/search-results showed "368 Jobs".
- **Ashby board:** 361. The difference is the 7 unlisted postings above.
- **Intern/student:** **6**:
  - REQ20508 SDR Intern - London
  - REQ20320 SDR Intern - Munich
  - ASHREQ-4292 Software Engineer Intern - Berlin (2026)
  - ASHREQ-8182 Software Engineer Intern - Berlin (2027)
  - REQ19494 Software Engineer Intern - Zurich (2026)
  - REQ21214 Product Marketing, AI-Powered Data Engineering Intern (Spring 2027), Menlo Park

  Only the last one is in the US.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://careers.snowflake.com/widgets` | ALLOW | no matching rule (`*/apply`, `*/px-widgets`, `*/jobcart` … are disallowed) |
| `https://careers.snowflake.com/us/en/search-results`, `/us/en/job/…` | ALLOW | no matching rule |
| `https://api.ashbyhq.com/posting-api/job-board/snowflake` | ALLOW | no robots.txt (cross-check only) |
| `https://jobs.ashbyhq.com/snowflake/<id>` | ALLOW | no matching rule (`/api/`, `/b/`, `/meeting/` are disallowed). Link only. |

## Anti-bot / quirks
- There was no challenge.
- The capture's `7993` "Job" text is a Phenom widget artefact, not a count.
- `isListed: false` postings are real, open roles. Never "fix" the feed by intersecting it with the Ashby board.

## Recommended checker
```yaml
- key: snowflake
  name: Snowflake
  adapter: phenom
  careers_url: https://careers.snowflake.com/us/en/search-results
  settings:
    base_url: https://careers.snowflake.com
    ref_num: SNCOUS
    lang: en_us
    country: us
    site_type: external
    page_name: search-results
    job_path: /us/en/job/{jobSeqNo}/{slug}
    id_field: jobSeqNo              # jobId repeats across sibling postings
    page_size: 1000                 # one call
  health:
    expect_total_field: refineSearch.totalHits
  # cross-check (optional): ashby {board: snowflake} -> listed postings only (361 today)
```

## Evidence
- Sample: `discovery/samples/snowflake.json` is a raw refineSearch response (size=20): 20 jobs plus facets, totalHits 368, 65 KB.
- Capture: `discovery/captures/snowflake/` (bookmark `keywords=intern`, 8 results).
- Requests:
  - careers.snowflake.com: 6 refineSearch calls (`size=100` ×4, `size=1000`, `size=20`) and 2 loads of one job page.
  - api.ashbyhq.com: 1.
  - jobs.ashbyhq.com: 4 posting pages.
  - 1 Playwright render.
  - All at ≤1 request/second per host.
