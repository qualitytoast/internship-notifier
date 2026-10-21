# Brevan Howard (`brevan-howard`)

**Status:** verified-feed   ·   **Checked:** 2026-10-19

| | |
|---|---|
| Official careers URL | https://careers.brevanhoward.com/gb/en/home (https://www.brevanhoward.com/careers/ redirects here). Job search: https://careers.brevanhoward.com/gb/en/search-results |
| Hiring system | **Phenom People** career site (refNum `BHABHAGB`, CDN `cdn.phenompeople.com/CareerConnectResources/BHABHAGB`). It mirrors **Workday**: every job has `ats`/`source` = `"WORKDAY"` and an `applyUrl` on `wd3.myworkdaysite.com/recruiting/brevanhoward/BH_ExternalCareers/...` (tenant `brevanhoward`, site `BH_ExternalCareers`, data centre wd3). |
| Recommended adapter | `phenom` (shared adapter if other Phenom sites need one; otherwise a small custom checker). Workday CXS is a cross-check only (see robots). |

## Recommended feed
- **Request:** `POST https://careers.brevanhoward.com/widgets`
- **Headers:** `Content-Type: application/json`, `Accept: application/json, text/plain, */*`. No cookies, no session and no `x-csrf-token` needed. The browser sends a CSRF token, but plain httpx POSTs without one returned 200 JSON.
- **Body (tested):**
  ```json
  {"lang":"en_gb","deviceType":"desktop","country":"gb","pageName":"search-results",
   "ddoKey":"refineSearch","from":0,"size":100,"jobs":true,"counts":true,
   "all_fields":["category","country","state","city","type","timeType"],"selected_fields":{},
   "keywords":"","global":true,"sortBy":"","subsearch":"","clearAll":false,"jdsource":"facets",
   "isSliderEnable":false,"pageId":"page34","siteType":"external","refNum":"BHABHAGB"}
  ```
  The body above is the browser's body with `ddoKey` changed from `eagerLoadRefineSearchSession` to `refineSearch` and `size` changed from 10 to 100. A smaller body without `pageId`, with `"counts":false` and `"all_fields":[]`, also worked and leaves out `aggregations`. I did not test removing the other keys one at a time. Keep `refNum`, `ddoKey`, `lang`, `country`, `siteType`, `pageName`, `from`, `size`, `jobs`, `keywords`, `selected_fields`.
- **Pagination:** offset `from` plus page size `size`. `refineSearch.hits` is the number of jobs on this page and `refineSearch.totalHits` is the total for the query. `size=100` returned all 26 jobs in one call. The real maximum can't be measured with only 26 jobs, so use 100. Keep fetching until you have `totalHits` jobs or a page comes back empty.
  - The default (relevance) order is **not stable between calls**: the last 6 jobs came back in a different order with `from=20,size=10` than with `size=100`. `sortBy:"Most recent"` was ignored and gave the same order. Use one page with `size >= totalHits`. If you ever need to page, dedupe by `jobSeqNo` and check that the number of unique jobs equals `totalHits`.
- **Detail (optional, for the full description):** `GET https://careers.brevanhoward.com/gb/en/job/{jobId}/{slug}`. It is server-rendered, and `phApp.ddo.jobDetail.data.job.description` holds the full HTML description (about 7 KB). It also has `jobFamily` (`"Interns"`), `jobUpdatedDate`, `postingStatus` and `ai_summary`. Read it with `json.JSONDecoder().raw_decode(html, html.find('phApp.ddo = ') + 12)`.
- **No-XHR alternative:** `GET https://careers.brevanhoward.com/gb/en/search-results` embeds the first page (10 jobs plus `totalHits`) in `phApp.ddo.eagerLoadRefineSearch`, and `?from=10&s=1` gives the next page. `GET /gb/en/sitemap.xml` lists every job URL (26 on 2026-10-19).

## Field map
Paths are relative to `refineSearch.data.jobs[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | `jobId` (same as `reqId`, e.g. `JR101583`) | This is the Workday requisition id. `jobSeqNo` (`BHABHAGBJR101583EXTERNALENGB` = refNum + jobId + siteType + locale) is also unique. |
| title | `title` | Contains en-dashes, e.g. `2027 Summer Internship Program – Trading, New York` |
| location(s) | `multi_location[]` (strings, `"City, State, Country"`) | Primary location: `location` / `cityStateCountry`. Also `city`, `state`, `country`, and the `isMultiLocation` flag. Example: the off-cycle internship is `["Geneva, Geneva, Switzerland", "London, United Kingdom"]` |
| url (detail) | built: `https://careers.brevanhoward.com/gb/en/job/{jobId}/{slug}` with `slug = re.sub(r'[^A-Za-z0-9]+','-',title).strip('-')` | Matches all 26 sitemap slugs and all 10 links on the page. The sitemap uses the `{jobSeqNo}` form of the same URL. |
| url (apply) | `applyUrl` | Points to Workday: `https://wd3.myworkdaysite.com/recruiting/brevanhoward/BH_ExternalCareers/job/<City>/<slug>_JR…/apply`. `externalApply` is false. |
| posted date | `postedDate` (`2026-09-08T00:00:00.000+0000`) | Also `dateCreated` (full timestamp) |
| description / snippet | `descriptionTeaser` (plain text, about 300 chars) | Also `ml_job_parser.descriptionTeaser_first200`. The full HTML is only on the detail page (see above). |
| employment type | `type` (`Intern (Fixed Term) (Trainee)` / `Permanent`) | Also `timeType` (`Full time`) |
| department / team | `category` (`Graduate Group`, `Technology Group`, …) / `multi_category[]` | `department` is `Human Resources` for all internships because the programme is run by HR |

## Totals (observed 2026-10-19)
- **Feed, no filters:** **26**. The refineSearch POST above returned `totalHits: 26` and `hits: 26` with `size=100`.
- **Live careers page, no filters:** **26**. A Playwright render of `/gb/en/search-results` showed "Available jobs 26 results found" and "Showing 1 -10 of 26 results". The server-embedded `eagerLoadRefineSearch.totalHits` is also 26, and the country facet counts add up to 26 (UK 8, US 7, India 5, Singapore 2, Switzerland 2, UAE 2).
- **Other sources agree:** `sitemap.xml` has 26 `/job/` URLs. The Workday CXS `POST https://wd3.myworkdaysite.com/wday/cxs/brevanhoward/BH_ExternalCareers/jobs` returned `total: 26`, and its 26 `JR` ids are **exactly** the Phenom set: none only in Workday, none only in Phenom.
- **Intern/student:** **16**. All of them have `type` "Intern (Fixed Term) (Trainee)" and `category` "Graduate Group". The facet aggregation agrees: type Intern 16 / Permanent 10. The title regex (filters.yaml `role.strong`) also matches 16. There are 15 "2027 Summer Internship Program – …" postings:
  - Trading in Singapore, London, Abu Dhabi and New York
  - Systematic Execution Research NY, Systematic Data Strategy NY, Systematic Trading Technology Software NY
  - Systematic Trading in NY and London
  - AI & Quantitative Analyst in Abu Dhabi, London and NY
  - Venture Capital NY, Geneva, QIS London

  The 16th is "3 – 6 Month Off Cycle Internship" (Geneva; London). 7 of the 16 are in the US (New York).

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://careers.brevanhoward.com/widgets` | ALLOW | no matching rule. The disallows cover `*/px-widgets`, `*/apply`, `*/jobcart`, `*/chatbot`, … but not `/widgets` |
| `https://careers.brevanhoward.com/gb/en/search-results` (and `?from=10&s=1`) | ALLOW | no matching rule |
| `https://careers.brevanhoward.com/gb/en/job/JR101583/2027-Summer-Internship-Program-Trading-New-York` (and the `jobSeqNo` form) | ALLOW | no matching rule |
| `https://careers.brevanhoward.com/gb/en/sitemap.xml` | ALLOW | no matching rule (it is also listed as `Sitemap:` in robots.txt) |
| `https://careers.brevanhoward.com/gb/en/apply?jobSeqNo=…` | **BLOCK** | `Disallow: */apply`. Never fetch this. Use it only as a link in emails. |
| `https://wd3.myworkdaysite.com/wday/cxs/brevanhoward/BH_ExternalCareers/jobs` | ALLOW | `robots.txt` returns HTTP 422, which counts as 4xx, so allow-all under RFC 9309 |
| `https://brevanhoward.wd3.myworkdayjobs.com/wday/cxs/brevanhoward/BH_ExternalCareers/jobs` | ALLOW | no matching rule, but see the next row |
| `https://brevanhoward.wd3.myworkdayjobs.com/BH_ExternalCareers/...` | **BLOCK** | `Disallow: /BH_ExternalCareers/`. The tenant has hidden its Workday site from crawlers. |

## Anti-bot / quirks
- There was no bot challenge. `careers.brevanhoward.com` is behind CloudFront and returns `cache-control: no-cache, no-store`. The `/widgets` POST works from plain httpx without cookies or CSRF.
- The page itself does not call `refineSearch` on first load. It renders the first page on the server and calls `eagerLoadRefineSearchSession`, which only returns `{"refineSearch":{"tokenAvailable":false}}`. That is why the first capture saw only `leastAppliedJobs`. `ddoKey:"refineSearch"` is the call the page makes when you change pages or filters.
- Workday CXS quirks, if it is ever used as a cross-check:
  - `total` only appears at `offset=0` (`offset=20` returned `total: 0`).
  - `postedOn` is relative ("Posted 5 Days Ago").
  - `externalPath` slugs can be out of date: JR101585 is titled "Desktop Support Engineer" but its path is `Desktop-Support-Lead_JR101585`.
  - The host is behind Cloudflare.

  The company's robots.txt on `*.myworkdayjobs.com` disallows its Workday site, which tells us it wants traffic to go through Phenom. That is why Phenom is the primary feed, even though Workday is the system of record.
- Phenom job URLs work in both forms: `/job/{jobId}/{slug}` (links on the page) and `/job/{jobSeqNo}/{slug}` (sitemap).

## Recommended checker
```yaml
- key: brevan-howard
  name: Brevan Howard
  adapter: phenom
  careers_url: https://careers.brevanhoward.com/gb/en/search-results
  settings:
    base_url: https://careers.brevanhoward.com
    widgets_path: /widgets          # POST, JSON body as above with ddoKey "refineSearch"
    ref_num: BHABHAGB
    lang: en_gb
    country: gb
    site_type: external
    page_name: search-results
    job_path: /gb/en/job/{jobId}/{slug}   # slug = re.sub('[^A-Za-z0-9]+','-',title).strip('-')
    page_size: 100                  # one call today (26 jobs); page with `from` and dedupe by jobSeqNo if totalHits > 100
    detail_for_description: false   # descriptionTeaser is enough for filtering; detail pages hold the full HTML
  health:
    expect_total_field: refineSearch.totalHits   # alert if unique jobs != totalHits
  # cross-check (optional, sparingly): workday {host: wd3.myworkdaysite.com, tenant: brevanhoward, site: BH_ExternalCareers}
```

## Evidence
- Sample: `discovery/samples/brevan-howard.json` is the full raw `refineSearch` response (size=100): 26 jobs with facets, 84 KB.
- Capture: `discovery/captures/brevan-howard/` (home page: `leastAppliedJobs` widget only).
- I also captured the search-results page with Playwright and made direct calls: refineSearch with size 100, refineSearch with from=20 and size=10, sortBy test, one detail page, sitemap, and Workday CXS at offsets 0 and 20. That was about 10 logged requests plus robots fetches, at ≤1 request/second per host.
