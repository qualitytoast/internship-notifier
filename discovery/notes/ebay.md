# eBay (`ebay`)

**Status:** needs-custom (main board verified; student roles live on a second platform)   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://jobs.ebayinc.com/us/en/search-results (the bookmark `/us/en/jobs-in-california` is a Phenom landing page pre-filtered to `state=California`). The student landing page is https://careers.ebayinc.com/student-opportunities/ (`jobs.ebayinc.com/us/en/emerging-talent` redirects there). |
| Hiring system | **Phenom People** career site (refNum `EBAEBAUS`, one locale only: `us/en`, no other country sites). It mirrors **Workday** tenant `ebay`, site `apply` on `ebay.wd5.myworkdayjobs.com`: every job has `applyUrl` `https://ebay.wd5.myworkdayjobs.com/apply/job/...`. **Student and new-grad roles are on RippleMatch**, not Workday: the student page's "Opportunities in North America → Apply now" button goes to `https://app.ripplematch.com/t/b8c45472`, which redirects to eBay's RippleMatch company page (company id `865`). The EMEA student page (`/us/en/emerging-talent-europe-middleeast-asia`) also links to `app.ripplematch.com/company/ebay/`. |
| Recommended adapter | Two sources in one `custom:ebay` checker: (1) the `phenom` adapter for the main board (Workday CXS `ebay/apply` is an equal cross-check), (2) a small RippleMatch reader (one GET) for student roles. |

## Recommended feed

### Source 1: main board (Phenom)
- **Request:** `POST https://jobs.ebayinc.com/widgets`
- **Headers:** `Content-Type: application/json`, `Accept: application/json, text/plain, */*`. I also sent `Origin`/`Referer` (`https://jobs.ebayinc.com/us/en/search-results`). No cookies, no CSRF token.
- **Body (tested):**
  ```json
  {"lang":"en_us","deviceType":"desktop","country":"us","pageName":"search-results",
   "ddoKey":"refineSearch","sortBy":"","subsearch":"","from":0,"jobs":true,"counts":true,
   "all_fields":["remote","country","state","category"],"size":100,"clearAll":false,
   "jdsource":"facets","isSliderEnable":false,"pageId":"page15","siteType":"external",
   "keywords":"","global":true,"selected_fields":{},"locationData":{},"refNum":"EBAEBAUS"}
  ```
  The browser sends the same body with `ddoKey` `eagerLoadRefineSearchSession`, which only returns a 41-byte session reply (same as Brevan Howard). `refineSearch` returns the jobs.
- **Pagination:** offset `from` and page size `size`. `refineSearch.totalHits` is the total and `refineSearch.hits` the jobs on this page. `size=100` works. `from=0,100,200` returned 100 + 100 + 69 = **269 unique `jobId`s**, so paging was stable in this test. Still dedupe by `jobSeqNo` and check that the unique count equals `totalHits`.
- **Detail (optional):** `GET https://jobs.ebayinc.com/us/en/job/{jobId}`. The slug is optional: `/job/R0077030` and `/job/R0077030/x` both return 200 with the right job in `phApp.ddo.jobDetail.data.job`. That object holds `description` (full HTML), `workerSubType` (`Regular` / `Intern (Trainee)` / …), `workerType`, `jobFamilyGroup`, `postingStatus` and `jobUpdatedDate`.
- **No-XHR alternatives:** `GET /us/en/search-results` embeds the first 10 jobs and `totalHits` in `phApp.ddo.eagerLoadRefineSearch`. `GET /us/en/sitemap.xml` lists every job URL (269 on 2026-10-20).

### Source 2: student and new-grad roles (RippleMatch)
- **Request:** `GET https://app.ripplematch.com/api/v2/public/roles/865`. No auth, no cookies. The response is a JSON **list** of every public eBay role, with no pagination (4 roles on 2026-10-20).
- **Company id:** 865 is in `GET https://app.ripplematch.com/api/v2/company-branded-page/ebay` → `company.id`. Both calls are what the public company page `https://app.ripplematch.com/v2/public/company/ebay` makes when it loads.
- **TLS quirk (must handle):** the server sends the leaf certificate twice and leaves out the intermediate *Sectigo Public Server Authentication CA DV R36*. Browsers and macOS curl fill the gap through AIA. httpx with certifi fails with `CERTIFICATE_VERIFY_FAILED`, and that includes the project's own robots fetch. Fix: add the intermediate from `http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt` (DER; valid to 2036-03-21) to the SSL context, or use the OS trust store (`truststore`). I tested httpx + certifi + that intermediate and got 200 with JSON.
- **Job URL:** `https://app.ripplematch.com/v2/public/job/{public_id}` (the company page links it with `?from_page=tracking_link&tl=b8c45472`).

## Field map

Phenom: paths are relative to `refineSearch.data.jobs[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | `jobId` (= `reqId`, Workday requisition, e.g. `R0077030`) | `jobSeqNo` = `EBAEBAUS` + jobId + `EXTERNALENUS` is also unique. Phenom ids never carry the `-1` suffix; 39 Workday `externalPath`s do (`…_R0076947-1`). |
| title | `title` | Can contain `****…****`, em/en dashes and CJK text. |
| location(s) | `multi_location[]` ("City, State"), `cityStateCountry`, `country` | 15 jobs have more than one location. `isMultiLocation` is true for every job, so ignore it. |
| url (detail) | built: `https://jobs.ebayinc.com/us/en/job/{jobId}` | Do not rebuild Phenom's slug: its rules are irregular. It keeps em dashes, replaces en dashes and keeps a leading `-`, and 15 of 269 sitemap slugs did not match a simple rule. The slug is optional anyway. |
| url (apply) | `applyUrl` | `https://ebay.wd5.myworkdayjobs.com/apply/job/<City>/<slug>_R…/apply`. robots-disallowed (`/apply/`), so use it only as a link. |
| posted date | `postedDate` (`2026-10-01T00:00:00.000+0000`) | `dateCreated` is a full timestamp. Range on 2026-10-20: 2024-03-08 … 2026-10-19 |
| description / snippet | `descriptionTeaser`, `ml_job_parser.descriptionTeaser_first200` | Full HTML only on the detail page. |
| employment type | `type` (always `Full time` = Workday timeType) | The Workday worker sub-type (`Intern (Trainee)`) is **not** in the list response, only on the detail page (`workerSubType`). |
| department / team | `category` (14 values, e.g. `Engineering` 128, `Data Science` 20) | |

RippleMatch: paths are relative to the top-level list `[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | `public_id` (e.g. `7b3baea4`) | |
| title | `name` | e.g. `Financial Analyst Intern 2027`; `2027 Commercial Graduate Rotation Program \| UK ` has a trailing space |
| location(s) | `formatted_locations`, `role_locations[].city` | `San Jose, CA, USA`, `Richmond, UK` |
| url | built: `https://app.ripplematch.com/v2/public/job/{public_id}` | |
| employment type | `job_type` (`Internship` / `Full-Time Job`) | |
| posted date / description | none in this response | `start_date`, `end_date` are null |

## Totals (observed 2026-10-20 00:00–00:25 UTC)
- **Phenom feed, no filters:** **269**. `refineSearch.totalHits` = 269, with 269 unique jobIds fetched.
- **Live careers page, no filters:** **269**. The Playwright-rendered `/us/en/search-results` has `Showing <span class="result-count">269</span> results`, and the pager runs `1 … 10 Next` at 10 per page. The server-embedded `eagerLoadRefineSearch.totalHits` is also 269, and the facets add up to 269: country `India` 87, `United States of America` 74, `Canada` 43, `Ireland` 18, `Netherlands` 12, `Germany` 9, `Japan` 8, others 18.
- **Other sources agree exactly:**
  - Workday CXS `POST https://ebay.wd5.myworkdayjobs.com/wday/cxs/ebay/apply/jobs` gives `total` 269. I enumerated all 14 pages, and its 269 requisition ids are **identical** to Phenom's: none only in Workday, none only in Phenom.
  - `sitemap.xml` lists the same 269 ids.
  - The second Workday site in the tenant's robots.txt, `TCGPlayer_External_Career` (TCGplayer subsidiary), has `total` 0.
- **RippleMatch:** **4** public roles. The company page shows "Jobs (4)" and the API returns 4.
- **Total across both sources: 273.**
- **Intern/student: 3.**
  - The 269 Phenom/Workday jobs have **no** intern, co-op, apprentice, student or placement titles. I ran a title regex over all 269. The Workday `workerSubType` facet shows one `Intern (Trainee)`: **R0060042 "Rechtsreferendar\*in"** (German legal trainee, Kleinmachnow). It is also the only job on Phenom's "Global Internships" page `emerging-talent-europe-middleeast-asia`.
  - RippleMatch has 2 internships: **7b3baea4 "Financial Analyst Intern 2027"** (San Jose, CA; the only US one) and **94ae73fe "2027 eBay Industrial Placement Programme"** (Richmond, UK). It also has 2 new-grad full-time roles: "2027 Commercial Graduate Rotation Program | UK" and "Software Engineer - Recent Grad (Traffic)" (Austin, TX).
  - The RippleMatch "About" text says 2027 internship applications open in September/October and close in mid-April 2027. Expect more student roles to appear on RippleMatch, not on Workday.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://jobs.ebayinc.com/widgets` | ALLOW | no matching rule. Disallows cover `*/apply`, `*/px-widgets`, `*/jobcart`, `*/chatbot`, … |
| `https://jobs.ebayinc.com/us/en/search-results` (and `?from=10&s=1`) | ALLOW | no matching rule |
| `https://jobs.ebayinc.com/us/en/job/R0077030` (with or without slug) | ALLOW | no matching rule |
| `https://jobs.ebayinc.com/us/en/sitemap.xml` | ALLOW | no matching rule (also the robots `Sitemap:`) |
| `https://jobs.ebayinc.com/us/en/emerging-talent-europe-middleeast-asia` | ALLOW | no matching rule |
| `https://jobs.ebayinc.com/us/en/apply?jobSeqNo=…` | **BLOCK** | `Disallow: */apply`. Never fetch it. |
| `https://ebay.wd5.myworkdayjobs.com/wday/cxs/ebay/apply/jobs` (and `/wday/cxs/ebay/apply/job/…`) | ALLOW | no matching rule |
| `https://ebay.wd5.myworkdayjobs.com/apply/job/…` (Phenom `applyUrl`) | **BLOCK** | `Disallow: /apply/`. The tenant hides its Workday site from crawlers: link to it only. (`/en-US/apply/job/…` is literally allowed.) |
| `https://ebay.wd5.myworkdayjobs.com/wday/cxs/ebay/TCGPlayer_External_Career/jobs` | ALLOW | no matching rule (`Allow: /TCGPlayer_External_Career/`) |
| `https://app.ripplematch.com/api/v2/public/roles/865`, `/v2/public/job/7b3baea4` | ALLOW once TLS is fixed | robots.txt is `User-agent: *` / `Allow: /`, fetched with curl through the macOS trust store. `discovery/robots_check.py` prints **BLOCK (robots.txt unreachable)** only because httpx/certifi cannot verify the incomplete chain (see TLS quirk). |
| `https://careers.ebayinc.com/student-opportunities/` | ALLOW | no matching rule |

## Anti-bot / quirks
- No bot challenge on `jobs.ebayinc.com` (`cache-control: no-cache, no-store`) or on the Workday CXS host. Plain httpx POSTs work without cookies.
- Workday's robots.txt disallows the `apply` site path. As with Brevan Howard, that is why Phenom is the primary source and Workday is a cross-check only.
- RippleMatch pages log "viewed" analytics POSTs (`/api/v2/activity-logs/client`) when rendered in a browser. The checker must call only the JSON GET above, never render the page.
- RippleMatch shows only *public* roles. "Join RippleMatch to see personalized matches" suggests more roles are visible to logged-in candidates. I could not verify that without an account, which we must not create. The public list is what the company page shows to everyone.
- Health checks: the 269-job board may lose all student roles to RippleMatch at any time. Alert if the RippleMatch list is unreachable (TLS) or drops to 0 during recruiting season (Sep–Apr).

## Recommended checker
```yaml
- key: ebay
  name: eBay
  careers_url: https://jobs.ebayinc.com/us/en/search-results
  checker: custom:ebay            # = phenom adapter + RippleMatch reader, results merged
  settings:
    phenom:
      base_url: https://jobs.ebayinc.com
      ref_num: EBAEBAUS
      lang: en_us
      country: us
      site_type: external
      page_name: search-results
      page_id: page15
      all_fields: [remote, country, state, category]
      job_path: /us/en/job/{jobId}     # slug optional
      page_size: 100                   # 3 calls today; dedupe by jobSeqNo, expect unique == totalHits
    ripplematch:
      company_id: 865                  # GET https://app.ripplematch.com/api/v2/public/roles/865
      job_url: https://app.ripplematch.com/v2/public/job/{public_id}
      extra_ca_pem: Sectigo Public Server Authentication CA DV R36   # server omits it from the chain
  # cross-check (optional): workday {host: ebay.wd5.myworkdayjobs.com, tenant: ebay, site: apply} -> same 269 ids
```

## Evidence
- Sample: `discovery/samples/ebay.json` is the raw `refineSearch` response for `from=200,size=100` (69 jobs plus facets, `totalHits` 269, 210 KB).
- RippleMatch response from 2026-10-20 (1.5 KB, 4 roles: public_ids `9cad5207`, `94ae73fe`, `7b3baea4`, `20f54c3a`): kept in the scratchpad, summarised above.
- Capture: `discovery/captures/ebay/` (California landing page, `eagerLoadRefineSearchSession` only).
- Requests:
  - 27 HTTP requests to eBay, Workday, RippleMatch and Sectigo hosts. That covers: search-results HTML, sitemap, 3 refineSearch, 14 Workday CXS pages, the Workday intern facet, TCGplayer, 2 detail pages, the student and EMEA pages, the Sectigo intermediate and the RippleMatch API.
  - 2 Playwright page loads: `/us/en/search-results`, and the RippleMatch link.
  - robots.txt fetches.
  - All at ≤1 request/second per host.
