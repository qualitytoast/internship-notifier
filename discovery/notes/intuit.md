# Intuit (`intuit`)

**Status:** needs-custom (Radancy TalentBrew site; its sitemap is the complete, robots-allowed list)   ·   **Checked:** 2026-10-20 (00:17–00:21 UTC)

| | |
|---|---|
| Official careers URL | https://jobs.intuit.com/search-jobs (unfiltered, 593 jobs). The bookmark `https://jobs.intuit.com/search-jobs/intern/27595/1` is a keyword view ("43 jobs found for intern"), and **robots.txt disallows it** (see robots). |
| Hiring system | Front end: **Radancy TalentBrew** (company/org id `27595`, assets on `tbcdn.talentbrew.com`). ATS: **Avature**. Every job page's Apply button points to `https://intuit.avature.net/externalCareers/JobApplication?pipelineId=<Job ID>`. **Avature has no public job list**: `/en_US/externalCareers/SearchJobs` and `/JobDetail/<id>` return 404, and its sitemap (`/en_US/externalCareers/sitemap.xml`) lists only 15 portal pages (Login, Register, Profile…). The pages have no Workday links. |
| Recommended adapter | **custom** `talentbrew` sitemap checker (none of the shared adapters fits). It could be shared with other Radancy sites that publish a full sitemap. |

## Recommended feed
- **Request 1 (list, every run):** `GET https://jobs.intuit.com/sitemap.xml`. This is one request of 374 KB, `text/xml` with a UTF-8 BOM.
  - It has 1660 `<url>` entries. **593** of them are job URLs of the form `https://jobs.intuit.com/job/<city-slug>/<title-slug>/27595/<tbJobId>`. That is exactly the site's own total, with no duplicates.
  - Keep only `<loc>` values that match `^https://jobs\.intuit\.com/job/([^/]+)/([^/]+)/27595/(\d+)$`. The other entries are `/business/…` (715), `/employment/…` (225), `/location/…` (83), `/category/…` (23) and a few pages.
  - `<lastmod>` is the sitemap build time (2026-10-19T22:03:39Z on every job), **not** a per-job date.
- **Request 2 (detail, only for new ids):** `GET https://jobs.intuit.com/job/<city>/<slug>/27595/<tbJobId>` (HTML, about 600 KB). It contains one `<script type="application/ld+json">` **JobPosting** with:
  - `title`, `datePosted` (`2026-09-11`), `jobLocation[].address` (locality/region/country; several places for multi-location jobs) and `description` (HTML)
  - `employmentType` (`Full-Time` even for interns, so ignore it) and `identifier.value` = the Avature **Job ID** (`24123`)
  - `<span class="job-location">` and `<span class="job-id">` hold the same values.
  - Fetch details only for new ids. Fetching every job on each run would be about 360 MB. A first full run is 593 detail requests (about 10 minutes at 1 request/second), or the checker can fetch details only for slugs that look like student roles (see below).
- **Fallback list (allowed, heavier):** `GET https://jobs.intuit.com/search-jobs?p={1..40}` is server-rendered with 15 cards per page. `data-total-results="593"`, `data-total-pages="40"`, `data-current-page`. Each page is about 2 MB, so 40 pages come to about 80 MB per run. Use it only if the sitemap ever falls behind the page total.
  - Each card is `ul.search-list > li[data-intuit-jobid=<Avature Job ID>]` containing `a.sr-item[href=/job/…/27595/<tbJobId>][data-title]`, an `h2` title and `span.job-location` ("Multiple Locations" for multi-site jobs).
  - The page's own AJAX pager (`/search-jobs/results`, `/search-jobs/resultspost`) is robots-disallowed and must not be used.
- **Health check (optional):** compare the sitemap job count with `data-total-results` of `GET /search-jobs` (page 1). They were equal today: 593 = 593, and all 15 page-1 jobs were in the sitemap.

## Field map
| Job field | Source | Notes |
|---|---|---|
| id | last path segment of the job URL (`100620927632`, the TalentBrew job id) | stable per posting. Keep the Avature Job ID (`identifier.value` / `data-intuit-jobid`, e.g. `24123`) as an `alt_id`. |
| title | JSON-LD `title` (`Summer 2027: Product Manager Intern`); before the detail fetch, the URL `<title-slug>` with `-` → space | the slug is lowercase without punctuation (`&` → `and`), which is enough for intern/term matching |
| location(s) | JSON-LD `jobLocation[].address` → `"<addressLocality>, <addressRegion>, <addressCountry>"`; before the detail fetch, `<city-slug>` from the URL (primary city only) | cities: mountain-view 294, san-diego 74, new-york 36, bengaluru 28, atlanta 25, oakland 24, toronto 18, … |
| url | the sitemap `<loc>` itself | the Apply link (`intuit.avature.net/externalCareers/JobApplication?pipelineId=<JobID>`) is only for emails |
| posted date | JSON-LD `datePosted` | not in the sitemap |
| description / snippet | JSON-LD `description` (HTML) | |
| employment type | none useful | `employmentType` is always "Full-Time" |
| department / team | card `data-category` (e.g. `Customer Success-- Customer Experience`) on the fallback list | not in JSON-LD |

## Totals (observed 2026-10-20 00:18–00:20 UTC)
- **Feed (sitemap), no filters:** **593** job URLs, 593 unique ids.
- **Live careers page, no filters:** **593**. `GET https://jobs.intuit.com/search-jobs` (the server-rendered page itself, robots-allowed) shows `<h1>593 jobs found</h1>`, `data-total-results="593"` and `data-total-pages="40"` × 15 per page. `?p=2` gave 15 different jobs with the same total.
- **Intern/student: 37** by title slug (filters.yaml `role.strong` words):
  - 35 "Intern" and 2 "Co-op" (Toronto: "Winter 2027 Product Research Co-op (8 months)" and "Winter 2027 Event Marketing Coordinator Co-op (4 months)")
  - by term: Summer 2027 33, Spring 2027 2 (Washington D.C. public affairs/policy), Winter 2027 2
  - by city: Mountain View 27, San Diego 6, Toronto 2, Washington D.C. 2. 16 of the 37 are MBA internships.

  The bookmark's keyword search reported 43 because TalentBrew's keyword search also matches description text. That page is robots-disallowed, so I took the 43 from the old capture and did not refetch it.

## robots.txt
jobs.intuit.com/robots.txt is exactly `User-agent: *` / `Disallow:/search-jobs/`. That rule blocks every path **under** `/search-jobs/`, but not `/search-jobs` itself or `/search-jobs?…`.

| URL | Verdict | Deciding rule |
|---|---|---|
| `https://jobs.intuit.com/sitemap.xml` | ALLOW | no matching rule |
| `https://jobs.intuit.com/job/mountain-view/summer-2027-product-manager-intern/27595/100620927632` | ALLOW | no matching rule |
| `https://jobs.intuit.com/search-jobs` | ALLOW | no matching rule |
| `https://jobs.intuit.com/search-jobs?p=2` | ALLOW | no matching rule |
| `https://jobs.intuit.com/search-jobs/intern/27595/1` (the bookmark) | **BLOCK** | `Disallow: /search-jobs/` |
| `https://jobs.intuit.com/search-jobs/results?ActiveFacetID=0&CurrentPage=2&RecordsPerPage=15` (the page's AJAX pager) | **BLOCK** | `Disallow: /search-jobs/` |
| `https://intuit.avature.net/externalCareers/JobApplication?pipelineId=24123` | ALLOW | `Allow: /externalCareers` (use it only as a link) |
| `https://intuit.avature.net/en_US/externalCareers/SearchJobs` | ALLOW | `Allow: /*/externalCareers`, but it is a 404 page, with no list |

## Anti-bot / quirks
- No bot challenge on jobs.intuit.com or intuit.avature.net with plain httpx and a browser UA.
- The search and job pages are very large (about 2 MB and 600 KB) for little data. Keep detail fetches incremental.
- There are two id spaces. The TalentBrew job id is in the URL (12 digits, e.g. `100620927632`). The Avature Job ID is shown on the page (5 digits, e.g. `24123`); `data-job-id` on the card's `<a>` is the Avature id, while the "Save" button's `data-job-id` is the TalentBrew id.
- The sitemap is a periodic build: all job `lastmod` values were 2026-10-19T22:03:39Z, about 2 hours before the check. A job posted after the last build appears on the next build, so the sitemap can lag a few hours. The live list is the `/search-jobs?p=N` pager, but it is about 80 MB per full read, and its default sort (`data-sort-criteria="0"`) is relevance, not newest-first. So page 1 alone cannot catch new jobs. Use the sitemap, plus the total check to spot lag.

## Recommended checker
```yaml
- key: intuit
  name: Intuit
  adapter: custom:talentbrew_sitemap
  careers_url: https://jobs.intuit.com/search-jobs
  settings:
    sitemap_url: https://jobs.intuit.com/sitemap.xml
    job_url_regex: '^https://jobs\.intuit\.com/job/(?P<city>[^/]+)/(?P<slug>[^/]+)/27595/(?P<id>\d+)$'
    title_from: slug            # '-' -> ' ' until the detail is fetched
    detail: jsonld_jobposting   # GET the job URL, parse <script type="application/ld+json"> JobPosting
    detail_only_new: true
    total_check_url: https://jobs.intuit.com/search-jobs   # data-total-results="593" (allowed; not /search-jobs/…)
  never_fetch: ['https://jobs.intuit.com/search-jobs/']    # robots Disallow (bookmark + AJAX pager)
```

## Evidence
- Sample: `discovery/samples/intuit.xml` is the raw `jobs.intuit.com/sitemap.xml` with only the 593 `/job/` `<url>` entries kept. The non-job entries were removed to stay under 300 KB, and an XML comment says so. 134 KB.
- Calls made: jobs.intuit.com sitemap, `/search-jobs`, `/search-jobs?p=2` and one job page; intuit.avature.net externalCareers home, sitemap index, en_US sitemap, SearchJobs and JobDetail. That is about 10 HTTP requests plus robots, at ≤1 request/second per host. No Playwright render was needed because the count is server-rendered. I did not render `/search-jobs` in a browser because its scripts call the disallowed `/search-jobs/results`.
- Old capture: `discovery/captures/intuit/` (the bookmark page, 43 keyword hits, all TalentBrew).
