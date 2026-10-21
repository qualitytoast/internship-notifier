# Amazon (`amazon`)

**Status:** needs-custom (no shared adapter fits)   ·   **Checked:** 2026-10-19 23:47 – 2026-10-20 00:41 UTC (two sessions)

| | |
|---|---|
| Official careers URL | https://www.amazon.jobs/en/search (all jobs, no filters). The bookmark is a filtered landing page: https://www.amazon.jobs/content/en/career-programs/university/internships-for-students?country%5B%5D=US&employment-type%5B%5D=Intern |
| Hiring system | Amazon's own job site (amazon.jobs, "JobCreator" source system; ids are iCIMS-style `icimsJobId`). Two public JSON search endpoints on the same index: the **new** `POST /api/jobs/search?is_als=true` (used by the `/content/...` university pages) and the **classic** `GET /en/search.json` (used by `/en/search`). Applying happens on `account.amazon.jobs`, which robots.txt disallows (`Disallow: /`). |
| Recommended adapter | `custom:amazon`: a union of a few small "student slice" queries on the new endpoint (below). Optional weekly full-site audit by `category` partitions. |

## The 10,000 cap, and why reading only the student slice is safe
- Both endpoints cap the result count. The new endpoint returns `found: 10000` and the classic one `hits: 10000` for any query with more matches. Deep paging stops at the same point: classic `offset=9999&result_limit=1` works, but `offset=9995&result_limit=10` returns 0 jobs. The `/en/search` page shows the cap: its pager reads "1 2 3 … 1000" at 10 per page and it never prints a total.
- **Facet counts are not capped.** They give the real size of any query. With no filters, every single-valued facet sums to the same number: `scheduleTypeId`, `employeeClass`, `category` and `businessCategory` all give **22,117** (new endpoint, confidential jobs included, 00:33 UTC). The classic endpoint gave 22,110 at 23:49 UTC. `isIntern` sums to 20 fewer, because 20 jobs have no `isIntern` value.
- **The checker reads the student slice, not all 22k jobs.** Amazon tags student roles with structured fields. The checker unions those fields with a few keyword searches. This is complete for our filters, for these reasons (all measured 2026-10-20):
  1. **Structured slice.** `isIntern=1` OR `employeeClass ∈ {Intern, Apprentice}` (OR semantics inside `jobTypeFacets`) gives **606**. `businessCategory ∈ {studentprograms, university}` gives **599**. They overlap by 408, so the union is **797**. The complement query, which excludes all of those values, has facet sum **21,111**. Since 21,908 − 797 = 21,111, the exclude semantics are exact. Paging confirmed the slice: 606 unique ids in 4 pages of 200, plus 190 in the business-category-minus-flags query.
  2. **Keyword sweep of the complement.** I searched the other 21,111 jobs for every strong word in config/filters.yaml: intern, internship, co-op, apprentice, apprenticeship, student, working student, summer analyst, externship, placement, campus, university. Only **27 real student titles** sit outside the structured slice, and all are in the US:
     - "ASIC Engineer Intern, Annapurna Labs - 2027" (class Regular Full Time, hire type `campus_fte`)
     - **25** RME "Mechatronic Apprentice I…" / "Automation Engineer Apprentice" roles (class Regular Full Time)
     - "Software Development Engineer Apprentice - Military Veterans"; this one is in the slice through business category, though not through flags
     
     The two staff jobs "Apprentice Academy Centre Manager" also match. The `q=intern` and `q=apprentice` complement queries return only **10** and **37** rows, so they are cheap to run on every poll.
  3. **Keyword search matches title words reliably.** Inside the flagged set, `query=intern` returns 431 rows, against 305 titles that contain the word "intern". For the US subset, all **50/50** titled-intern ids came back (67 rows; the rest match on description). There is no stemming: `intern` does not match "internship", which gave 2,397 rows because it hits descriptions. The checker therefore uses only the precise words.
  4. **Every slice query is far below the cap** (at most 610 rows), so nothing is truncated. Facet sums double-check each query.
- **Confidential-flag trap.** The new endpoint's default body excludes `isConfidential=1`. That hides **209** jobs that `/en/search` shows publicly, including 2 internships: 10565312 "Operations & Logistics Intern - 2027" (CZ) and 10490133 "Praktikum im Bereich Logistik" (DE). Their detail pages are public and return 200. The checker must send only the `a-confidential-job` business-category exclusion. With it, the totals match the classic endpoint and `/en/search`.
- **Seeing every job when needed (audit or cross-check).** Partition by `category`. It has 37 values, every job has exactly one (they sum to the total), and the largest is "Operations, IT, & Support Engineering" with 3,225, far under 10,000. Page each category with `size=200`, which is about **130 requests and about 180 MB** (about 8 KB per job). The classic equivalent is `category[]=<name>&result_limit=100`, about 240 requests. Partitioning by country does not work alone: the USA has 12,999 jobs.

## Recommended feed
- **Request:** `POST https://www.amazon.jobs/api/jobs/search?is_als=true`
- **Headers:** `Content-Type: application/json`, `Accept: application/json`, `Origin: https://www.amazon.jobs`, and a normal browser UA. No cookies or CSRF. The browser's `cookieInfo` field is not needed.
- **Base body.** Every slice query uses it, with the per-query overrides in the next list:
  ```json
  {"accessLevel":"EXTERNAL","contentFilterFacets":[],"excludeFacets":[{"name":"businessCategory","values":[{"name":"a-confidential-job"}]}],
   "filterFacets":[],"includeFacets":[],"jobTypeFacets":[],"locationFacets":[[{"name":"country","requestedFacetCount":9999}]],
   "query":"","size":200,"start":0,"treatment":"OM","sort":{"sortOrder":"DESCENDING","sortType":"CREATED_DATE"}}
  ```
- **Slice queries.** Union them by `icimsJobId`. Let FLAGS = `[{"name":"isIntern","values":[{"name":"1"}]},{"name":"employeeClass","values":[{"name":"Intern"},{"name":"Apprentice"}]}]` and BIZ = `[{"name":"businessCategory","values":[{"name":"studentprograms"},{"name":"university"}]}]`.
  1. `jobTypeFacets: FLAGS`. 608 rows today, 4 pages.
  2. `filterFacets: BIZ` with `excludeFacets: base + FLAGS`. 192 rows, 1 page.
  3. `query: "intern"` with `excludeFacets: base + FLAGS + BIZ` and `sortType: "SCORE"`. 10 rows.
  4. Same as 3 with `query: "apprentice"`. 37 rows.
  5. Optional safety nets, same form: `"co-op"` (4), `"student"` (28), `"working student"` (20), `"summer analyst"` (1). Today none of them adds a student title.
  
  Downstream title filters drop the description-only matches from queries 3–5.
- **Pagination:** `start` and `size`. **`size` up to 200 works.** I did not test larger sizes; at 200 the response is about 1.8 MB. `found` is exact below 10,000. Stop when `start + size >= found`. Never request past `start + size > 10000`. A full slice read takes about 8–11 requests and about 10 MB, which suits every few hours. A quick poll reads page 1 of query 1, sorted by `CREATED_DATE` descending, plus queries 3 and 4: 3 requests.
- **Detail:** not needed. Each hit already has the full `description`, `basicQualifications` and `preferredQualifications`.
- **Classic alternative (equivalent data):** `GET https://www.amazon.jobs/en/search.json?offset=N&result_limit=100&sort=recent&is_intern[]=1&employee_class[]=Intern&employee_class[]=Apprentice`. Repeated `jobType` params are OR'ed (`is_intern[]=1&employee_class[]=Intern` gave 554 = 549 + 513 − 508), and filters of different groups are AND'ed. `business_category[]=…`, `category[]=…`, `normalized_country_code[]=USA` and `base_query=intern` also work, and `facets[]=<name>` adds facet counts. **`result_limit` is at most 100**; 101 returns `error: "Result limit cannot be greater than 100"`. This endpoint does not exclude confidential jobs. I found no way to exclude values on it, so the complement queries need the new endpoint.

## Field map (new endpoint)
Paths are relative to `searchHits[].fields`. Every value is a one-element list, so take `[0]`.

| Job field | Path | Notes |
|---|---|---|
| id | `icimsJobId` | e.g. `10580807`. Also `artJobId` (UUID). |
| title | `title` | may carry trailing spaces; trim |
| location(s) | `normalizedLocation` (`Arlington, Virginia, USA`), `location` (`US, VA, Arlington`) | `locations[]` holds one JSON **string** per location (parse it): `{"city","normalizedStateName","normalizedCountryCode","countryIso2a",…}`. `country` is ISO-2 (`US`). |
| url (detail) | built: `https://www.amazon.jobs/en/jobs/{icimsJobId}` | 302 to the canonical `/en/jobs/{id}/{slug}`, 200. The classic endpoint gives `job_path` with the slug. |
| url (apply) | `urlNextStep` = `https://account.amazon.jobs/jobs/{id}/apply` | **robots BLOCK: link only, never fetch** |
| posted date | `createdDate` (epoch seconds as a string, e.g. `"1791491418"`) | `updatedDate` is the same kind of value. The classic endpoint uses `posted_date` ("October 19, 2026"). |
| description | `description` (HTML with `<br/>`), `shortDescription` | plus `basicQualifications` and `preferredQualifications` |
| employment type | `employeeClass` (`Intern`, `Apprentice`, `Regular Full Time`, …), `isIntern` (`"1"`/`"0"`), `scheduleTypeId` (`Full-Time`/`Part-Time`) | `hireTypeId` (`campus_intern_dkltxz`, `campus_fte_5mjja1`, …) marks campus hiring |
| department / team | `category` (37 values), `businessCategory`, `teamCategory`, `primarySearchLabel`, `jobFamily`, `jobRole`, `companyName` | |

## Totals (observed 2026-10-20 00:33–00:41 UTC)
- **Whole site:** **22,117** jobs by facet sums, with only the `a-confidential-job` exclusion. This equals what `/en/search` lists: the classic endpoint gave 22,110 at 23:49 UTC. The new endpoint's default body (which also excludes `isConfidential=1`) gives 21,908. `found`/`hits` read 10,000 (the cap).
- **Live page, no filters:** `/en/search` shows no total. A Playwright render at 23:48 UTC showed the pager "1 2 3 … 1000" at 10 per page, i.e. the 10,000 cap. That matches the API's `hits: 10000`.
- **Bookmarked page:** "**37 OPEN JOBS**". That was the capture at 23:32 UTC, and the API with the page's own body returned `found: 37` at 23:47. The page shows only team `internships-for-students` + class Intern + US. Our US slice has 103 student roles, so **the bookmark misses about 64 US student roles**: Annapurna, AWS, fulfillment and RME apprenticeships.
- **Student slice (any location):**
  - structured union 797 + 6 confidential (2 flagged, 4 student business category) = **803**
  - keyword extras outside the structured slice: 27 student titles + 2 staff titles
- **intern_total = 635:** 608 typed intern/apprentice (606 + 2 confidential) + 27 title-only (1 intern + 26 apprentices). **103 are in the US:** 76 flagged + 27 title-only. The other 190–192 student-business-category jobs are mostly "Early Career"/new-grad full-time roles. Three of them have trainee/apprentice titles.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://www.amazon.jobs/api/jobs/search?is_als=true` | ALLOW | no matching rule (only `/internal` and `/<lang>/internal` are disallowed for `*`) |
| `https://www.amazon.jobs/en/search.json?…` (filters, `category[]`, offsets) | ALLOW | no matching rule |
| `https://www.amazon.jobs/en/jobs/10565312` and `/en/jobs/10565312/operations-logistics-intern-2027-amazon-logistics` | ALLOW | no matching rule |
| `https://www.amazon.jobs/en/search`, `/content/en/career-programs/university/internships-for-students` | ALLOW | no matching rule |
| `https://account.amazon.jobs/jobs/10580807/apply` | **BLOCK** | `Disallow: /` (the whole apply host) |
| `https://www.amazon.jobs/sitemap.xml` | n/a | 404. There is no sitemap, and robots.txt lists none. |

## Anti-bot / quirks
- There was no challenge for plain httpx with a browser UA on either endpoint. Responses are large because every hit carries its full description: about 8 KB per job, so 1.8 MB per 200-row page. Pace at 1 request per second or slower.
- The new endpoint ORs entries inside `jobTypeFacets`, ANDs `filterFacets`/`locationFacets` against them, and drops any job that has any value in `excludeFacets`. The complement arithmetic above checks these semantics exactly.
- A query that matches nothing returns `{"found":null,"start":null,"facets":null,"searchHits":null}` rather than `found: 0`. That happened for `query:"externship"`. Treat it as 0.
- `isIntern` is missing on 20 jobs, and 59 flagged jobs have `isIntern=0` (mostly German "Ausbildung" apprentices). Always use both flags.
- Non-English student titles are common in the slice: Ausbildung, Praktikum, Staż, Apprenti(e), Jovem Aprendiz. The structured slice catches them, but title-only filters would miss them, so the checker should pass `employeeClass`/`isIntern` as the employment type.
- Live churn is small but constant (`updatedDate` changes every few minutes). Union by id, and do not treat a single missing poll as a removal.

## Recommended checker
```yaml
- key: amazon
  name: Amazon
  adapter: custom:amazon
  careers_url: https://www.amazon.jobs/en/search
  settings:
    endpoint: https://www.amazon.jobs/api/jobs/search?is_als=true   # POST JSON, base body above
    exclude_base: [{name: businessCategory, values: [a-confidential-job]}]   # do NOT exclude isConfidential
    page_size: 200
    queries:                       # union by icimsJobId
      - {jobTypeFacets: {isIntern: ["1"], employeeClass: [Intern, Apprentice]}}
      - {filterFacets: {businessCategory: [studentprograms, university]}, exclude: [FLAGS]}
      - {query: intern, exclude: [FLAGS, BIZ], sort: SCORE}
      - {query: apprentice, exclude: [FLAGS, BIZ], sort: SCORE}
      - {query: co-op, exclude: [FLAGS, BIZ]}       # optional safety nets
      - {query: student, exclude: [FLAGS, BIZ]}
    employment_type_from: [employeeClass, isIntern]   # isIntern "1" -> "Intern"
    job_url: https://www.amazon.jobs/en/jobs/{icimsJobId}
  health:
    per_query: unique ids == found, found < 10000
    slice_size_range: [300, 3000]          # alert outside
    site_total: sum(facets.scheduleTypeId) on a size=1 request, expect > 15000
  audit (optional, weekly): partition by category (37 values, max 3,225), size 200, about 130 requests
```

## Evidence
- Sample: `discovery/samples/amazon.json` is the raw last page (`start=600, size=200`) of slice query 1: `found: 606`, 6 hits, full facets, 103 KB.
- Requests:
  - Session 1 (23:47–23:54 UTC): 28 API requests and 1 Playwright load of `/en/search`. That session covered the classic tests, the deep-offset edge, the `category[]` filter, the `is_intern`/`employee_class` union and the first slice counts.
  - Session 2 (00:09–00:41 UTC): 35 requests, including 2 robots.txt fetches and 1 sitemap 404. That session covered the confidential subset, the flag union pages, the complement and keyword sweeps, the keyword reliability check, page-size limits, the category partition test and one detail page.
  - All requests were at 1.15 s or more per host.
- Capture: `discovery/captures/amazon/` (bookmark page, "37 OPEN JOBS", and its `api/jobs/search` POST body).
