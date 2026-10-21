# AMD (`amd`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://careers.amd.com/careers-home/jobs (all jobs). The bookmark https://careers.amd.com/students/jobs is the **same Jibe site and API**: the `/students` landing page adds `categories=Student / Intern / Temp` to its `/api/jobs` call. |
| Hiring system | **iCIMS Jibe** over **iCIMS**, with 6 portals: `careers-amd` (US, 594), `global-external-amd` (482), `canadacareers-amd` (94), `campus-amd` (67), `campuscanada-amd` (29) and `globalcampus-amd` (15). The three campus portals hold the 111 student jobs. |
| Recommended adapter | shared **`jibe`** (spec in `docusign.md`), settings `{host: careers.amd.com}`. One feed covers the main site and the students site. Do **not** add the category filter. |

## Recommended feed
- `GET https://careers.amd.com/api/jobs?page=<N>&limit=100&internal=false` with N = 1…13 today. `totalCount` is 1281, and the last page has 81. Max limit is 100 (see docusign.md).
- The students page sends `GET /api/jobs?page=1&sortBy=posted_date&descending=true&internal=false&categories=Student%20/%20Intern%20/%20Temp`, which gives `totalCount` 110. It is a filtered view of the same data, so the unfiltered feed already contains all 110.
- **robots.txt sets Crawl-delay 5**, so a full run is 13 requests ≈ 65 s.
- **Payload:** ≈ 3.3 MB per 100 jobs (descriptions included), about 42 MB per full run. If that is too heavy, use the `sortBy=posted_date&descending=true` order and stop once a page holds only known slugs. Then do a full pass, for example daily, to detect removals and check `totalCount`.

## Field map
Same as the jibe spec in `docusign.md`. AMD specifics:

| Job field | Path | Notes |
|---|---|---|
| id | `slug` = `req_id` (e.g. `93338`) | 1281 unique |
| url | `meta_data.canonical_url` = `https://careers.amd.com/jobs/{slug}?lang=en-us` | Redirects to `/careers-home/jobs/{slug}?lang=en-us`. The students page links `/students/jobs/{slug}?lang=en-us`, and both work. |
| department | `categories[].name` | `Engineering` 984, `Student / Intern / Temp` 110, `Sales / Marketing` 79, … |
| employment type | `employment_type` | `FULL_TIME` 1135, `TEMPORARY` 29, `PART_TIME` 6, null 111. It does not mark interns, so use title + category. |
| portal | `tags4` | `US Careers (External)`, `Global Careers (do not use for US or Canada)`, `Canada Careers (External)`, `Campus US`, `Campus Canada`, `Campus Global` |
| pay range | `tags2`/`tags3`/`tags5`/`tags6` | salary strings such as `USD $175,000.00/Yr.` |
| other | `tags1` `Yes`/`No` (42 Yes) | meaning not documented |

## Totals (observed 2026-10-20 00:12–00:18 UTC)
- **Feed, no filters:** **1281**. 13 pages, 1281 unique slugs; `totalCount` was 1281 on every page.
- **Live careers page, no filters:** **1281**. A Playwright render of https://careers.amd.com/careers-home/jobs showed "1281 Results" and "of 1281".
- **Students site:** a Playwright render of https://careers.amd.com/students/jobs showed "110 Results" and "1 – 10 of 110". This equals the API with `categories=Student / Intern / Temp` (110) and the category count in the unfiltered facets.
- **Intern/student:** **111**. All 110 in `Student / Intern / Temp` have intern, co-op or student titles. One more is outside that category: 93338 "Engineering Placement Intern - 2027/2028" (Belfast, category `Engineering`). Campus portals (`tags4`): Campus US 67 + Campus Canada 29 + Campus Global 15 = 111.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `https://careers.amd.com/api/jobs?page=1&limit=100&internal=false` | ALLOW | `Allow: /` (crawl-delay: 5) |
| `https://careers.amd.com/careers-home/jobs`, `/students/jobs`, `/jobs/<id>?lang=en-us` | ALLOW | `Allow: /` |

## Anti-bot / quirks
- There was no challenge, and plain httpx works.
- The page also loads TextRecruit chat and OneTrust. Ignore them.
- City facet values mix case (`CALGARY`, `MARKHAM`, `Austin`).

## Recommended checker
```yaml
- key: amd
  name: AMD
  adapter: jibe
  careers_url: https://careers.amd.com/careers-home/jobs
  settings:
    host: careers.amd.com          # covers /careers-home and /students (same API, no category filter)
    use_employment_type: false     # null for interns; rely on title/category
```

## Evidence
- Sample: `discovery/samples/amd.json` is the raw body of the students page's own call `GET /api/jobs?page=1&sortBy=relevance&descending=false&internal=false&categories=Student%20/%20Intern%20/%20Temp`: 10 jobs, totalCount 110, 257 KB. The unfiltered page-1 body is 314 KB, over the sample limit, and has the same shape.
- Capture: `discovery/captures/amd/` (students bookmark, 110 results).
- Requests: 16 to careers.amd.com (2 probe calls, 13 pages, 1 job URL) plus 2 Playwright renders, at ≥5 s per request.
