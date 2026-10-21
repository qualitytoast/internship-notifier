# ServiceNow (`servicenow`), and the shared SmartRecruiters adapter

**Status:** verified-feed (superset; see Totals)   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://careers.servicenow.com/jobs/ (bookmark: the same page with `?search=intern&pagesize=20`). It is an Umbraco "jobboard" marketing site. Its job ids are SmartRecruiters posting ids (`/jobs/744000156376629/federal-field-marketing-manager/`). |
| Hiring system | **SmartRecruiters**, company identifier `ServiceNow` (`company-name-lookup` → `{"identifier":"ServiceNow","name":"ServiceNow"}`). Postings live at `https://jobs.smartrecruiters.com/ServiceNow/<postingId>-<slug>`. |
| Recommended adapter | new shared `smartrecruiters` adapter, `{company: ServiceNow}`. The spec is below. |

## Which SmartRecruiters routes are allowed
| Route | robots.txt | Usable? |
|---|---|---|
| `api.smartrecruiters.com/v1/companies/<c>/postings` (official Posting API, JSON, paged) | **BLOCK**: `User-agent: *` / `Disallow: /` (only LinkedInBot is allowed `/v1/companies/`) | **No.** Never call it. The search results below even contain `actions.details` links to it, so ignore those. |
| `careers.smartrecruiters.com/<c>` + `/<c>/api/groups` + `/<c>/api/more` (hosted career page, HTML) | ALLOW. `/robots.txt` returns 200 with the SR Jobs HTML app, so it has no rules. | **Yes. This is the complete list.** |
| `jobs.smartrecruiters.com/sr-jobs/search` (SmartRecruiters' public job search "SR Jobs", JSON) | ALLOW (`/robots.txt` is 404) | Yes, but it returns **at most 100 (newest) postings**. `offset`, `page` and `limit>100` are ignored. It is useful for `totalFound`, for picking up postings that the HTML paging misses, and for `keyword` searches. |
| `jobs.smartrecruiters.com/<c>/<id>-<slug>` (posting page, HTML with schema.org microdata) | ALLOW | Yes, for details |
| `jobs.smartrecruiters.com/<c>` | ALLOW | It serves the same hosted career page as `careers.smartrecruiters.com/<c>` (identical 111 KB response). |
| `careers.servicenow.com/jobs/`, `/umbraco/jobboard/CandidateJobs/GetJobs` | ALLOW | **No.** Plain clients get a Cloudflare "Just a moment..." challenge (403). The list is server-rendered, 20 per page. Only a real browser render was used, to read its count. |

## Shared `smartrecruiters` adapter: exact requests
Use a browser UA. No cookies, tokens or JS are needed. Pace requests to 1/s per host.

1. **First page:** `GET https://careers.smartrecruiters.com/<Company>` returns text/html (111 KB for ServiceNow).
   - Loader: `div.js-openings-load[data-groups-pages="17"][data-page="0"][data-more="/ServiceNow/api/groups"]`. `data-groups-pages` is the number of group pages.
   - Groups: `section.js-group[data-qty="5"]`, 6 per page. Each group has:
     - Name (the location string): `header .opening-title` (e.g. "Addison, Texas", "Santa Clara, CALIFORNIA"). Casing varies, so "Austin, Texas" and "Austin, TEXAS" are separate groups.
     - Jobs: `ul.js-group-list > li.opening-job > a.js-job-ad-link[href]`. `href` = `https://jobs.smartrecruiters.com/ServiceNow/744000155802209-principal-customer-success-executive`, the title is in `h4.job-title`, and `aria-label` = "<title> - JB0075662". The requisition `JB…` appears only on first-page items; "more" items say "- undefined".
     - At most **9** jobs are shown per group. When `data-qty` > 9, there is a "Show more jobs" link: `a.js-more[data-more="/ServiceNow/api/more"][data-type="location"][data-value="Bangalore%2C%20IN"][data-page="0"]`. Its non-JS fallback `href` is `?search=&page=0&location=Bangalore%2C%20IN`.
   - The page says "Browse by: Location". For ServiceNow every `data-type` is `location`. Other companies may group differently, so read `data-type` and do not hard-code it.
2. **Remaining groups:** `GET https://careers.smartrecruiters.com<data-more>?page=N` for N = 1 … `data-groups-pages`−1. This returns an HTML fragment of 6 more `section.js-group` elements, with the same markup.
3. **Rest of each large group:** `GET https://careers.smartrecruiters.com<a.js-more data-more>?type=<data-type>&value=<data-value as given, already %-encoded>&page=N` for N = 1, 2, … This returns a fragment of up to **10** `li.opening-job` items. Stop when the group has `data-qty` unique jobs, or when a page returns no items.
4. **Union** with `GET https://jobs.smartrecruiters.com/sr-jobs/search?limit=100&company=<Company>`, which returns JSON `{"offset":0,"limit":100,"totalFound":677,"content":[…98-100 items…]}`. Each item has `id` (same posting id), `name`, `releasedDate` (ISO), `location{city,region,country,remote,hybrid}`, `shortLocation`, `applyUrl` (= the jobs.smartrecruiters.com posting URL) and `company.identifier`. The items are the newest postings. `typeOfEmployment`, `department` and `function` are empty `{}`.
5. **Dedupe by posting id.** Then run two health checks: unique ≈ Σ`data-qty` (±2%), and unique ≈ `totalFound` (±2%). See the quirks.
6. **Detail (optional):** `GET https://jobs.smartrecruiters.com/<Company>/<id>-<slug>` (125 KB). The schema.org microdata has `[itemprop=title]`, `[itemprop=employmentType]` ("Intern" for internships), `meta[itemprop=datePosted]`, `meta[itemprop=addressLocality|addressRegion|addressCountry]`, `[itemprop=description]`, `[itemprop=responsibilities]` and `[itemprop=qualifications]`.

**Cost for ServiceNow:** 1 first page + 16 group pages + 40 "more" pages (16 groups have more than 9 jobs; Santa Clara alone needs 13) + 1 search = **58 requests**.

## Field map
| Job field | Source | Notes |
|---|---|---|
| id | the digits in the href, `/ServiceNow/(\d+)-` | e.g. 744000155345889. It is the same id the official site and `sr-jobs/search` use. |
| title | `h4.job-title` text, or `name` in the search JSON | Some have double spaces |
| location | the group header (hosted page), or `location.city/region/country` (search) | One posting per location. ServiceNow posts multi-city requisitions as separate postings, e.g. JB0074869 has 8 postings. |
| url | the anchor `href` | `https://jobs.smartrecruiters.com/ServiceNow/<id>-<slug>`. Public copy: `https://careers.servicenow.com/jobs/<id>/<slug>/` |
| posted date | search `releasedDate`, or detail `datePosted` | Not on the hosted list page |
| employment type | detail `[itemprop=employmentType]` | "Intern", "Full-time", … |
| department | not exposed on the list | |

## Totals (observed 2026-10-19/20)
- **Feed (hosted career page + search union):** **688**. 99 location groups, Σ`data-qty` = 688. My crawl collected 688 entries, which were 687 unique: one posting (744000153806180) appeared twice and one (744000155824702, released 2026-10-15) was missing. Both were in the "New York, New York" group, and the missing one came in through the `sr-jobs/search` union.
- **Live careers page, no filters:** **676**, "Displaying 1 to 20 of 676 matching jobs" in a Playwright render of careers.servicenow.com/jobs/.
- **SmartRecruiters search index:** `totalFound` **677** (678 once) the same hour.
- **Difference (+12, 1.7%):** the hosted page is a superset. All 20 postings on the site's first page and 98 of the 99 newest search postings were in the crawl (the 99th is the paging miss above). I could not identify the ~11 postings that are on the hosted page but not counted by the site or the search index without crawling the site's 34 pages (a browser was needed). I tested one candidate, an odd "Copy of Strategic Partner Manager – GSI –KPMG…" posting, and it is in the search index, so that is not the explanation. The hosted page is SmartRecruiters' own public list for the company, so treat it as complete. Expect a few extra postings compared with the marketing site.
- **Intern/student:** **5** by the title rule:
  - AI Engineering - Assoc Software Engineer Internships - Summer 2027 (Bachelors), Santa Clara
  - AI Engineering - Software Engineer Internships - Summer 2027 (Masters), Santa Clara
  - Finance Intern - Undergrad Summer 2027, Santa Clara and West Palm Beach (2 postings)
  - Intern – Business Development Representative (languages), Dublin

  `sr-jobs/search?keyword=intern` returns these plus a "Staff Research Scientist" (full-text match). The bookmark page showed "of 5", which matches.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://careers.smartrecruiters.com/ServiceNow | ALLOW | /robots.txt is the HTML job-search app (200 text/html), so no rules |
| https://careers.smartrecruiters.com/ServiceNow/api/groups?page=1 | ALLOW | same |
| https://careers.smartrecruiters.com/ServiceNow/api/more?type=location&value=Bangalore%2C%20IN&page=1 | ALLOW | same |
| https://jobs.smartrecruiters.com/sr-jobs/search?limit=100&company=ServiceNow | ALLOW | /robots.txt is 404 |
| https://jobs.smartrecruiters.com/ServiceNow/744000155345889-… | ALLOW | /robots.txt is 404 |
| https://api.smartrecruiters.com/v1/companies/ServiceNow/postings | **BLOCK** | `Disallow: /` |
| https://careers.servicenow.com/jobs/ (+ umbraco GetJobs) | ALLOW (`Allow: /`) | allowed, but behind a Cloudflare challenge for plain clients |

## Anti-bot / quirks
- **Unstable ordering inside a group across calls.** The first group page and its `api/more` pages are generated separately. Within minutes the same `api/more?…&page=1` started at different postings, which can duplicate one posting and drop another. That is why step 4, the newest-100 union, exists. A second remedy is to re-request a group's "more" pages when unique < `data-qty`.
- Location groups are case-sensitive strings ("Austin, Texas" vs "Austin, TEXAS", "New York City, New York" vs "New York, New York").
- The hosted page responses are `cf-cache-status: DYNAMIC` (not CDN-cached). No challenge was seen on careers.smartrecruiters.com or jobs.smartrecruiters.com across about 60 requests.
- The site's `/umbraco/jobboard/CandidateJobs/GetRecentJobs` returns only the "recently viewed" widget (2 bytes). The job list itself is server-rendered.

## Recommended checker
```yaml
- key: servicenow
  name: ServiceNow
  adapter: smartrecruiters
  settings:
    company: ServiceNow          # identifier for careers.smartrecruiters.com/<company> and sr-jobs search
  careers_url: https://careers.servicenow.com/jobs/
  health:
    expect_total: sum of group data-qty (tolerance 2%) and sr-jobs totalFound (tolerance 2%)
```

## Evidence
- Sample: `discovery/samples/servicenow.html` is the hosted career page `https://careers.smartrecruiters.com/ServiceNow` (first 6 groups and the loader, 111 KB).
- Capture: `discovery/captures/servicenow/` (bookmark render: "of 5").
- Requests (this run): 57 crawl requests, 12 `sr-jobs` calls (lookup, paging tests and keyword tests), 1 detail, the JS bundle, 2 header checks and 1 Playwright render. The earlier agent made 9 requests.
