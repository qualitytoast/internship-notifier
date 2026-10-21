# Meta — job feed discovery

**Status:** verified-feed. It needs a small Meta-specific adapter: it extracts a token and uses a pinned GraphQL `doc_id`.
**Checked:** 2026-10-19, 18:47–18:53 CDT.

**Requests made, all to www.metacareers.com:**
- 17 direct HTTP requests. Five of these got HTTP 400: the first bare request, plus four deliberate header and token tests.
- 2 robots.txt fetches.
- 2 headless page loads, which returned about 26 responses from www.metacareers.com.

The browser loads also pulled about 20 JS/CSS files each from static.xx.fbcdn.net. See the robots section about that host.

## Careers site
- **Official careers URL** (job search, no filters): https://www.metacareers.com/jobsearch/
  - Bookmarked view: https://www.metacareers.com/jobsearch/?roles[0]=Internship
- **Hiring system:** Meta's own in-house "candidate portal". It is a Comet/Relay React app that reads jobs through `POST /graphql` using persisted queries (`doc_id`).
  - Evidence: `__crn=comet.candidateportal.CPXCareerProfileJobSearchRootPageRoute` and `fb_api_caller_class=RelayModern` in the captured POST body. The doc_id is defined in JS module `CareersJobSearchResultsV2DataQuery_candidate_portalRelayOperation`.
  - The JSON-LD `identifier.value` on detail pages looks like a Salesforce record id (e.g. `a1KiE0000003UftUAE`), so the back office is probably Salesforce-based. There is no public third-party ATS API.
  - The capture's "cornerstone" fingerprint (`facebook.csod.com`) is a false positive. It only appears in a click-ID blocklist config inside the page JS.
- **Public job detail URL:** `https://www.metacareers.com/jobs/{id}/`. This 301-redirects to the canonical `https://www.metacareers.com/profile/job_details/{id}/`, which is the form the sitemap uses.
- **Apply:** happens on the detail page (JSON-LD `directApply: true`). There is no separate apply URL in any feed.

## Recommended feed

**Request:** `POST https://www.metacareers.com/graphql`, preceded by one `GET https://www.metacareers.com/jobsearch/` to obtain the `lsd` token.

### Step 1: get the `lsd` token
`GET https://www.metacareers.com/jobsearch/` returns about 404 KB of HTML.

Headers:
- A normal Chrome User-Agent.
- `Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8`
- **`sec-fetch-dest: document`, `sec-fetch-mode: navigate`, `sec-fetch-site: none`, `sec-fetch-user: ?1`**

Without the `sec-fetch-*` headers the server returns **HTTP 400** with the generic "Sorry, something went wrong." HTML page. This was verified both ways. Client hints (`sec-ch-ua*`) and cookies are not needed.

Extract the token with this regex: `\["LSD",\[\],\{"token":"([^"]+)"\}` (e.g. `AdRsJ_4JMmC_Ya_NDoOnII9MccI`).

### Step 2: POST the search query
**Headers** (only these are needed):

| Header | Value |
|---|---|
| `User-Agent` | normal Chrome UA |
| `Accept` | `*/*` |
| `Content-Type` | `application/x-www-form-urlencoded` |
| `X-FB-LSD` | `<lsd>` |
| `sec-fetch-dest` | `empty` |
| `sec-fetch-mode` | `cors` |
| `sec-fetch-site` | `same-origin` |

Without the `sec-fetch-*` headers, the POST also returns HTTP 400 HTML. No cookies are needed: the test used a fresh client with an empty cookie jar.

**Body** (form-encoded). This is the minimal set that works; verified 200.

| Field | Value | Required? |
|---|---|---|
| `lsd` | token from step 1 | yes (without it: HTTP 400) |
| `doc_id` | `27129360303422352` (persisted query `CareersJobSearchResultsV2DataQuery`) | yes |
| `variables` | JSON below | yes |
| `fb_api_req_friendly_name` | `CareersJobSearchResultsV2DataQuery` | no (the browser sends it; useful for logs) |
| `fb_api_caller_class` | `RelayModern` | no |

The browser also sends about 20 other fields (`__a`, `__dyn`, `__csr`, `__hs`, `jazoest`, `__spin_*`, …). None of them are needed.

**`variables`, all jobs:**
```json
{"search_input":{"q":null,"divisions":[],"offices":[],"roles":[],"leadership_levels":[],"saved_jobs":[],"saved_searches":[],"sub_teams":[],"teams":[],"is_leadership":false,"is_remote_only":false,"sort_by_new":false,"results_per_page":null},"viewasUserID":null,"isLoggedIn":false}
```

**`variables`, internships:** the same JSON with `"roles":["Internship"]`.

- **Role values**, from the filter query `CareersJobSearchFiltersV3Query`, doc_id `25103492705924273`, `variables={}`: `"Full time employment"`, `"Internship"`, `"Short term employment"`.
- **Team values** include the student buckets:
  - `Internship - Business`
  - `Internship - Engineering, Tech & Design`
  - `Internship - PhD`
  - `University Grad - Business`
  - `University Grad - Engineering, Tech & Design`
  - `University Grad - PhD & Postdoc`

### Pagination
**There is none: one response contains every job.**
- `results_per_page:null` returned all 1,224 jobs in 264 KB.
- The website's "Page 1 of 123" is client-side, 10 per page.
- The response has no total field and no cursor. Note that robots.txt has `Disallow: /*cursor=`, but no cursor is needed.

### Full enumeration cost
**2 requests:** the page GET (for `lsd`) and one POST. Add a third POST with `roles:["Internship"]` for the official intern flag.
- **`lsd` lifetime:** a token taken from the capture about 5 hours earlier still worked, so it can be cached. Re-fetch the page when a POST returns 400.

### Detail and description
`GET https://www.metacareers.com/profile/job_details/{id}/`
- Uses the same navigation `sec-fetch-*` headers as step 1. About 430 KB of HTML per job.
- It contains one `<script type="application/ld+json">` JobPosting block with:
  - `datePosted`
  - `employmentType`
  - `description`, `responsibilities`, `qualifications`
  - `jobLocation[]`, including `addressCountry`
- Use it only for new ids.

### Alternatives considered
- **`GET https://www.metacareers.com/jobsearch/sitemap.xml`** (listed in robots.txt).
  - Allowed by robots, served gzip, 160 KB uncompressed. It holds **1,225** `<url>` entries of the form `/profile/job_details/{id}/`.
  - Its id set is **exactly** equal to the GraphQL `all_jobs ∪ featured_jobs`.
  - However: it has ids only (no title or location), no ETag or Last-Modified, and every `<lastmod>` is the sitemap generation time (all 1,225 identical: `2026-10-19T16:49:59-07:00`).
  - It is the best **doc_id-independent fallback and cross-check**.
- **`https://www.metacareers.com/sitemap/www_metacareers_com_sitemap.xml.gz`** (also listed in robots.txt) returned **HTTP 403** with an empty body.
- **`CPJobSearchQuery`** (doc_id `27808175508766384`): the only job-search query whose id appears in the page HTML. It returns just `{"xcp_is_logged_out_conversation_valid":false}`, with no jobs.
- **HTML scraping or Playwright:** not needed.

## Field map
Paths are relative to one item in `data.job_search_with_featured_jobs_v2.all_jobs[]`. The same item shape appears in `data.job_search_with_featured_jobs_v2.featured_jobs[]`.

| Field | Path | Example |
|---|---|---|
| id | `.id` (string, 15–16 digits) | `"4455569504707135"` |
| title | `.title` | `"Research Scientist Intern, On-Device AI Model Optimization (PhD)"` |
| location(s) | `.locations[]`: "City, ST", "City, Country" or "Remote, US". It can be `[]` (9 jobs) and has at most 30 entries. | `["Menlo Park, CA","Burlingame, CA"]` |
| detail URL | built: `https://www.metacareers.com/profile/job_details/{id}/` (or `/jobs/{id}/`, which 301-redirects to it) | `…/profile/job_details/4455569504707135/` |
| apply URL | none; apply is on the detail page (JSON-LD `directApply: true`) | n/a |
| posted date | **not in the list**. Detail-page JSON-LD `datePosted`, ISO 8601 with Pacific offset. | `"2026-10-19T15:06:11-07:00"`; an older job had `"2026-04-06T09:18:24-07:00"` |
| updated date | none (the sitemap `lastmod` is just its generation time) | n/a |
| description / snippet | **not in the list**. JSON-LD `description`, `responsibilities`, `qualifications` (text with `&nbsp;` separators). | about 0.3–1.5 K chars each |
| employment type / intern flag | **not in the list**. Use the `roles:["Internship"]` query (authoritative) or JSON-LD `employmentType` (`INTERN` / `FULL_TIME`). Today every intern also has "Intern" in its title. | `INTERN` |
| team / category | `.teams[]`, `.sub_teams[]` | `["Internship - PhD","Research"]`, `["Research"]` |
| other | JSON-LD `identifier.value` (internal req record id); `jobLocation[].address.{addressLocality, addressRegion, addressCountry}` | `a1KiE0000003UftUAE`, `US` |

**List and total paths:**
- List path: `data.job_search_with_featured_jobs_v2.all_jobs`
- There is **no total field.** Total = `len(all_jobs)` + the `featured_jobs` items not already in `all_jobs`.
- **`featured_jobs` is not filtered.** It returned the same "Critical Facility Engineer" (id 1690022942358388) for the Internship query too. When filtering, use only `all_jobs`.
- **Response format:** the body is plain JSON. It has no `for (;;);` prefix, even though the response is labelled `Content-Type: text/html`.

## Totals (observed 2026-10-19)
| Measure | Value | How observed |
|---|---|---|
| Feed total, no filters | **1,224** `all_jobs` + **1** featured (not included in `all_jobs`) = **1,225 distinct** | httpx POST at 18:48 CDT with all-empty `search_input`; ids are unique |
| Sitemap total | **1,225** (identical id set) | GET `/jobsearch/sitemap.xml` at 18:50 CDT |
| Live careers page total, no filters | **"1224 Items"**, plus the one "Featured Jobs" card shown above "All Jobs" ("Page 1 of 123") | Playwright load of https://www.metacareers.com/jobsearch/ at 18:51 CDT; body text read. The page's own GraphQL call used the same doc_id and returned 1,224. |
| Intern (`roles:["Internship"]`) | **62** | httpx POST at 18:48 and 18:51; the live page `?roles[0]=Internship` showed **"62 Items"** (Playwright, 18:52) |

**Intern breakdown:**
- 57 interns have at least one US location.
- 28 are "(PhD)" roles.
- Locations: Sunnyvale 24, Menlo Park 20, Redmond 18, New York 8, Seattle 7, Burlingame 6, Bellevue 5, Bangalore 4, plus a few in London, Paris, Dublin and US data-center towns.

**Student signals by team:**
- Internship teams: "Internship - PhD" 26 and "Internship - Engineering, Tech & Design" 25. Only 49 of the 62 interns carry an `Internship - *` team, so **use the role filter, not teams**.
- 15 jobs carry a `University Grad - *` team (new-grad, PhD and some interns).
- About 4 non-intern titles say "(University Grad)".

**Discrepancies:** none beyond the featured job.
- Page 1,224 = `all_jobs` 1,224.
- Sitemap 1,225 = `all_jobs` + the featured job.

## robots.txt
Results from `discovery/robots_check.py` (the `User-agent: *` group applies):

| URL | Verdict | Rule |
|---|---|---|
| https://www.metacareers.com/jobsearch/ | ALLOW | no matching rule |
| https://www.metacareers.com/graphql | ALLOW | no matching rule (re-verified) |
| https://www.metacareers.com/jobsearch/sitemap.xml | ALLOW | no matching rule |
| https://www.metacareers.com/sitemap/www_metacareers_com_sitemap.xml.gz | ALLOW | no matching rule (but it returns 403) |
| https://www.metacareers.com/jobs/4455569504707135/ | ALLOW | no matching rule |
| https://www.metacareers.com/profile/job_details/4455569504707135/ | ALLOW | no matching rule |
| https://www.metacareers.com/jobsearch/?roles[0]=Internship | ALLOW | no matching rule |
| https://www.metacareers.com/ajax/bulk-route-definitions/ | **BLOCK** | `Disallow: /ajax/` |
| https://static.xx.fbcdn.net/rsrc.php/…/x.js (page JS bundles) | **BLOCK** | `Disallow: /` (static.xx.fbcdn.net, `User-agent: *`) |

**Notes on robots and terms:**
- **Legal notice:** metacareers' robots.txt opens with "Collection of data on Facebook through automated means is prohibited unless you have express written permission from Facebook…" and links to its scraping terms. The machine-readable rules allow every path the recommended checker uses. Flagging the notice so the owner can decide.
- **`/ajax/` in a browser:** the checker never needs `/ajax/`. A real browser load of the page does call `/ajax/bulk-route-definitions/`, `/ajax/bz` and `/ajax/bootloader-endpoint/`. In a test with all `/ajax/*` requests aborted, the results query still fired and returned 62 jobs.
- **doc_id rediscovery:** the doc_id is defined in a hashed JS bundle on `static.xx.fbcdn.net` (`__d("CareersJobSearchResultsV2DataQuery_candidate_portalRelayOperation",[],…a.exports="27129360303422352")`). That host disallows everything for generic agents. So **do not fetch bundles to rediscover the doc_id**. A browser page load also pulls those bundles as subresources, which is why the checker should not depend on Playwright.

## Anti-bot / gotchas
- **Required headers:** missing `sec-fetch-*` headers produce HTTP 400 plus an HTML error page, on both the page GET and the GraphQL POST. A missing `lsd` produces the same 400. Treat any non-JSON body as failure.
- **No throttling observed:** no rate limiting, login wall or JS challenge at about 1 request every 1.1 s (around 20 direct requests).
- **`datr` cookie:** `Set-Cookie: datr=…` (400-day) is sent on the page GET but is not needed.
- **doc_id is a persisted-query id that can rotate** when Meta changes the query.
  - It was identical in the earlier capture (`__rev=1050849967`) and on the live page about 1.3 h later (`server_revision 1050889999`), so it survived a deploy.
  - The failure response for a stale doc_id was not tested (to save requests). Treat any of these as a feed break: HTTP 400, a non-JSON body, an `errors` key, or a missing `data.job_search_with_featured_jobs_v2`.
- **Response sizes:** about 264 KB for all jobs and 15 KB for interns. Detail pages are heavy, about 430 KB each.
- **Location strings** are display strings ("Menlo Park, CA", "London, UK", "Remote, US"), and 9 jobs have none. Use JSON-LD `addressCountry` for an exact country when needed.

## Recommended checker approach
1. **Get the token.** GET `/jobsearch/` with navigation `sec-fetch-*` headers and extract `lsd`. Cache it, and re-fetch only after a 400.
2. **Fetch all jobs.** POST `/graphql` with `doc_id=27129360303422352` and empty `search_input`. The job set is `all_jobs ∪ featured_jobs`, keyed by `id`. Store title, locations, teams and sub_teams. The detail URL is `https://www.metacareers.com/profile/job_details/{id}/`.
3. **Flag interns.** Make a second POST with `roles:["Internship"]` and mark those ids as student roles. Also keep the title regex as a backstop. Watch the `University Grad - *` teams for new-grad roles.
4. **Enrich new jobs.** For new matching ids only (cap per run), GET the detail page and parse the JSON-LD for `datePosted`, `employmentType`, description text and structured location.
5. **Run health checks.**
   - Alert if the GraphQL total drops more than 50% versus baseline.
   - Alert if the GraphQL response stops parsing; that indicates doc_id rotation.
   - Once a day, compare against `/jobsearch/sitemap.xml`. Expected: sitemap = `all_jobs` + featured.
6. **If the doc_id breaks,** fall back automatically to sitemap mode: diff ids, then JSON-LD detail pages for new ids (robots-allowed, plain HTTP). Send a health alert so a human can copy the new doc_id from browser devtools (POST `/graphql` with `fb_api_req_friendly_name=CareersJobSearchResultsV2DataQuery`). Do not automate rediscovery through fbcdn JS bundles (robots-disallowed).

## Sample
`discovery/samples/meta.json` (2.7 KB) is the real response of the all-jobs POST (step 2, empty `search_input`, 18:48 CDT), trimmed:
- `all_jobs` is cut from 1,224 to 6 representative items: 2 PhD interns, a "University Grad" role, a multi-location product manager, a job with `locations: []`, and a Paris full-time role.
- `featured_jobs`, `featured_jobs_title`, `all_jobs_title` and `extensions` are kept as returned.
