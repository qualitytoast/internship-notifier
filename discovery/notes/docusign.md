# DocuSign (`docusign`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20 (UTC)

This note also defines the shared **`jibe`** adapter. AMD, SIG and Booking.com use the same API (see `amd.md`, `sig.md`, `booking.md`).

| | |
|---|---|
| Official careers URL | https://careers.docusign.com/careers-home/jobs (unfiltered). The bookmark `?categories=University%20%26%20New%20Grad` now shows **0 results**: the category was renamed to `University`. |
| Hiring system | **iCIMS Jibe** ("iCIMS Career Site", CDN `jibecdn.com/prod/docusign`). It sits over **iCIMS**, with 6 regional portals: `uscareers-` (134 jobs), `emeacareers-` (41), `latamcareers-` (31), `indiacareers-` (28), `apjcareers-` (23) and `canadacareers-docusign.icims.com` (3). Jibe merges all six portals, so one feed covers every region. |
| Recommended adapter | shared **`jibe`**, settings `{host: careers.docusign.com}` |

## Recommended feed (the `jibe` adapter)
- **Request:** `GET https://<host>/api/jobs?page=<N>&limit=100&internal=false`. Add `sortBy=relevance&descending=false` if you want the page's exact query (optional).
  - Headers: `Accept: application/json`. No cookies, session or token. The page also calls `/api/jasession` and `/api/trackcdn/safe`, but `/api/jobs` does not need them.
- **Pagination:** `page` is 1-based and `limit` is the page size.
  - Default `limit` is 10 (`filter.displayLimit` = 10). **Maximum is 100**: `limit=101`, `200` and `1000` each return **HTTP 422** `{"data":{"error":"An unexpected error occurred"}}`.
  - `totalCount` (and `count`, same value) comes on **every** page.
  - Stop when you have `totalCount` unique jobs or a page returns `jobs: []`. Asking past the end (page 4 here) returns 200 with an empty list and the same `totalCount`.
  - Today: 3 requests (100 + 100 + 60).
  - The default order is stable across pages with no keyword: 260 rows gave 260 unique `req_id`. This also held for AMD (1281), SIG (286) and Booking (131). Still, dedupe by `slug` and compare with `totalCount`.
  - `sortBy=posted_date&descending=true` also works (newest first) if an incremental early-stop is ever wanted.
- **Never send `internal=true`.** It returns the employee view: 269 here, which is the 260 external jobs plus 9 internal-only postings. `internal=false` and omitting the parameter both give 260.
- **Filters the site uses** (do not send them; filter in our code): `categories=<name>` (pipe `|` = OR), `tags1=…`, `city=…`, `keywords=…`, `location=…`. The bookmark's `categories=University & New Grad` returns 0 today.
- **Response size:** about 17 KB per job because the full `description` is included (1.7 MB per 100). There is no field selector.
- **Detail:** not needed. The list already carries the full plain-text `description`, `qualifications` and `responsibilities`.

## Field map
Paths are relative to `jobs[].data`.

| Job field | Response path | Notes |
|---|---|---|
| id | `slug` (= `req_id`, the iCIMS job id, e.g. `30521`) | slug == req_id on all 260 (also on AMD, SIG, Booking) |
| title | `title` | |
| location(s) | `full_location` (`"Seattle, Washington; San Francisco, California"`, `;`-separated) | Primary: `city`, `state`, `country`, `country_code`, `short_location`. Extras: `additional_locations[]` (`{city,state,country,country_code,…}`, null when single). `multipleLocations` flag. `location_name` is an internal office code (`US-Seattle-3rd`). |
| url | `meta_data.canonical_url` (`https://careers.docusign.com/jobs/30521?lang=en-us`) | Fallback: `https://<host>/jobs/{slug}?lang={language}`. That URL redirects to the site's landing path where there is one: DocuSign and AMD go to `/careers-home/jobs/<id>?lang=en-us` (the page's `<link rel=canonical>`), Booking goes to `/booking/jobs/<id>`, and SIG serves `/jobs/<id>` directly. Tested on all four tenants. At Booking, `canonical_url` also picks the right brand site. |
| apply url | `apply_url` | iCIMS `https://<portal>.icims.com/jobs/<id>/login` (login flow; link only, never fetch) |
| posted date | `posted_date` (`2026-10-13T20:38:00+0000`) | also `create_date`, `update_date`, `meta_data.last_mod` |
| description / snippet | `description` (plain text, about 7 KB average) | also `qualifications`, `responsibilities` |
| employment type | `employment_type` (`FULL_TIME`, `INTERN`, `TEMPORARY`, null) | DocuSign: the 17 `INTERN` are exactly the interns. **Tenant-dependent: SIG sets `INTERN` on experienced roles** (see sig.md), so the adapter must not treat it as authoritative everywhere. |
| department / team | `categories[].name` (`Engineering`, `University`, …) | `category[]` has the same names with a leading space |
| other | `tags1` (DocuSign: worker type `Regular`/`Intern`), `tags2` (`Hybrid`/`Remote`), `tags3` (recruiter name), `language` (`en-us`), `brand`/`hiring_organization` (Booking, SIG), `ats_code` (`icims`), `internal`/`searchable`/`applyable` flags | `tagsN` meaning is per tenant |

Top level: `totalCount`, `count`, `jobs[]`, `filter.categories.all[]` (`{category, numJobs}`), `filter.facetList` (`tags1`, `tags2`, `city`, … term counts), `filter.brands`, and `languageCounts` (`{"en-us": {count: 260}}`, one language only, so there are no translated duplicates).

## Totals (observed 2026-10-20 00:08–00:20 UTC)
- **Feed, no filters:** **260**. `totalCount` was 260 on 7 calls. 3 pages at limit 100 gave 260 unique slugs.
- **Live careers page, no filters:** **259**. A Playwright render of https://careers.docusign.com/careers-home/jobs showed "259 Results" and "1 – 10 of 259". The page's own `/api/jobs?page=1&sortBy=relevance&descending=false&internal=false` call returned `totalCount: 259`, with Engineering at 46 instead of 47. API calls made before and after it returned 260. This is live churn or replica lag of 1 job.
- **Sitemap:** `/sitemap.xml` points to `/sitemap1.xml`, which has 258 `/jobs/<id>?lang=en-us` URLs. It is missing 30561, posted 23:40 UTC today, and 30236, so it lags slightly. It is not a feed.
- **Intern/student:** **17**. Category `University` = tags1 `Intern` = `employment_type` `INTERN` = title regex, the same 17 jobs in each case:
  - 11 × Software Engineer(ing) Intern (Seattle, 1 Chicago)
  - 3 × Program Manag(ement/er) Intern (Seattle, San Francisco)
  - 4 × Solution Consultant Intern
  - 1 × GTM Enablement Intern (Seattle)

  All 17 are in the US.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `https://careers.docusign.com/api/jobs?page=1&limit=100&internal=false` | ALLOW | `Allow: /` |
| `https://careers.docusign.com/careers-home/jobs`, `/jobs/<id>?lang=en-us` | ALLOW | `Allow: /` |

robots.txt sets **`crawl-delay: 5`** (the same on careers.amd.com, careers.sig.com and jobs.booking.com). The adapter must space its requests 5 s apart. `internwatch.http` already honours Crawl-delay.

## Anti-bot / quirks
- There was no bot challenge. Plain httpx with a browser UA works, with no cookies.
- Category names drift: the bookmark's `University & New Grad` no longer exists and is now `University`. This is one more reason not to filter server-side.
- `slug` is numeric here. Keep the adapter generic: use `slug` as the id, because other Jibe tenants can have non-numeric slugs.

## Recommended checker
```yaml
- key: docusign
  name: DocuSign
  adapter: jibe
  careers_url: https://careers.docusign.com/careers-home/jobs
  settings:
    host: careers.docusign.com
    # adapter defaults: GET /api/jobs?page=N&limit=100&internal=false; id = slug;
    # url = meta_data.canonical_url or https://<host>/jobs/{slug}?lang={language}; honour Crawl-delay 5
    use_employment_type: true      # reliable here (INTERN = the 17 interns); false for SIG
  health:
    expect_total_field: totalCount   # alert if unique slugs != totalCount
```

## Evidence
- Sample: `discovery/samples/docusign.json` is the raw body of the page's own call `GET /api/jobs?page=1&sortBy=relevance&descending=false&internal=false`: 10 jobs, facets, 158 KB.
- Capture: `discovery/captures/docusign/` (bookmark view: `categories=University & New Grad` → 0 results).
- Requests: 15 to careers.docusign.com. That covers 9 API calls (limit 1/10/100/101/200/1000, pages 1–4, internal true/false, posted_date sort), sitemap and sitemap1, and 1 job page. Also 1 Playwright render, at ≥5 s per request.
