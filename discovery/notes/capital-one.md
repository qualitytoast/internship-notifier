# Capital One (`capital-one`)

**Status:** verified-feed (Workday covers three country career sites)   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://www.capitalonecareers.com/search-jobs (unfiltered). The bookmark adds `ascf=[{"key":"custom_fields.Campus","value":"Internships"}]` and today shows **0 jobs** ("Hmm we don't have any jobs that match…"). No job carries the Campus value `Internships`: the Campus facet only has `Graduates` (5) and `Full-Time` (1). The site's own "all internship jobs" link (`/all-internship-jobs`) redirects to the same empty filter. |
| Hiring system | **Workday** tenant `capitalone`, site `Capital_One` on `capitalone.wd12.myworkdayjobs.com`. Three **Radancy TalentBrew** career sites show slices of it, and every job's apply link goes to `https://capitalone.wd12.myworkdayjobs.com/Capital_One/job/…/apply`. The slices: **US/global** `www.capitalonecareers.com` (1841 jobs, also India, Mexico, Philippines, Singapore), **Canada** `www.capitalonecareers.ca` (52) and **UK** `jobs.capitalone.co.uk` (79). The campus/intern jobs are not on a separate Workday site. They sit in TalentBrew organisation "Cap One Campus" (org id 31238), and their apply links also go to `Capital_One` (checked on the PhD Applied Research Internship page). `capitalone.eightfold.ai` is used only for the talent network and events, not job listings. |
| Recommended adapter | shared `workday` adapter, one site |

## Recommended feed
- **Request:** `POST https://capitalone.wd12.myworkdayjobs.com/wday/cxs/capitalone/Capital_One/jobs`
- **Headers:** `Accept: application/json`, `Content-Type: application/json`. No cookies.
- **Body:** `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`
- **Pagination:** `offset` += 20. `total` only appears on the first page; later pages return `total: 0`. 1966 jobs means 99 pages.
- **Workday cap, read before trusting `total`:** on another wd tenant (T-Mobile, same day) `total` was capped at **2000** and every offset ≥ 2000 returned page 1 again. Capital One is at **1966**, 34 below the cap. If `total` ever reads exactly 2000, treat the list as truncated. In that case, split the requests by a facet whose values each stay under 2000. `timeType` does not work here: Full time is 1921. Use `jobFamilyGroup` instead: 28 values, the largest is `Software-Engineering` with 433. Verify that the partition totals add up to the facet sum.
- **Detail (optional):** `GET https://capitalone.wd12.myworkdayjobs.com/wday/cxs/capitalone/Capital_One<externalPath>`. It returns `jobPostingInfo` with `jobDescription`, `location` + `additionalLocations[]`, `startDate` (posting date, e.g. `2026-10-01`), `timeType`, `jobReqId` and `country`.
- **Useful facets** (first-page `facets[]`, use the `id` values in `appliedFacets`):
  - `workerSubType`: `Intern` id `a12c70bf789e10572aab83c4780919ad` (7), `Regular` (1956), two Fixed Term values (3)
  - `timeType`, `jobFamilyGroup`, `locations` (171 values)

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `jobPostings[].externalPath` (unique) | Requisition id in `bulletFields[0]` (`R244815`). The path often ends in a repost suffix `_R244815-1`. |
| title | `jobPostings[].title` | |
| location(s) | `jobPostings[].locationsText` | Says "3 Locations" when there are several; the full list is in the detail `additionalLocations`. |
| url | built: `https://capitalone.wd12.myworkdayjobs.com/en-US/Capital_One` + `externalPath` | The detail also has `externalUrl` without `/en-US`. |
| posted date | `postedOn` (relative: "Posted Today", "Posted 30+ Days Ago") | Exact date in the detail `startDate` |
| description / snippet | detail only (`jobPostingInfo.jobDescription`) | |
| employment type | `timeType` (in the list) | The intern flag is only a facet (`workerSubType=Intern`), not a per-job field in the list. |
| department / team | facet `jobFamilyGroup` only | |

## Totals (observed 2026-10-20 00:15 UTC)
- **Feed, no filters:** **1966**. That is the first-page `total`. The facets add up to the same number: timeType 1921 + 45; workerSubType 1956 + 7 + 2 + 1.
- **Live careers page, no filters:** **1841** on capitalonecareers.com. The server-rendered `/search-jobs` shows the heading "**1841 Jobs**", with `data-total-results="1841"` and 123 pages of 15. `jobs_sitemap.xml` lists 1841 job URLs: org 1732 "Capital One - US" 1835 + org 31238 "Cap One Campus" 6.
- **Why the feed is larger (+125):** Workday also feeds the Canada and UK TalentBrew sites.
  - Workday filtered to Toronto + Nottingham + London + Farnborough + Remote-London has **129** jobs; Toronto alone has 52.
  - `capitalonecareers.ca/search-jobs` shows **52**, and `jobs.capitalone.co.uk/search-jobs` shows **79**.
  - 1841 + 52 + 79 = **1972** against Workday's 1966. That leaves 6 jobs counted on two sites (US + UK/CA locations) or still syncing. 1966 − 129 = 1837 against 1841 tells the same story.
  - Workday is the complete source. capitalonecareers.com alone misses the 129 Canada/UK jobs, including 2 Toronto internships.
- **Intern/student: 7.** Method: Workday `workerSubType = Intern` (the facet count is 7, and the 7 jobs are listed below). All 7 titles contain intern/internship/summer associate. 5 are US and 2 are Canada:
  - R244815 MBA Product Intern - Summer 2027 (McLean + 3 other locations)
  - R246679 MBA, Investment Banking Summer Associate - Summer 2027 (McLean)
  - R244323 Current PhD, Applied Research Internship Program - Summer 2027 (NY + 2 other locations)
  - R249110 Current PhD, AI Engineering Internship Program - Summer 2027 (NY + 2 other locations)
  - R249109 Current Master's, AI Engineering Internship Program - Summer 2027 (NY + 2 other locations)
  - R247472 Intern, Process Management - Summer 2027 (Toronto)
  - R247476 Intern, Financial Analyst - January 2027 (4 Month) (Toronto)

  The list is not enumerated, so an intern title under another sub-type would not be counted. A Workday search for "summer 2027" returned 6, all inside the set above. `searchText: "intern"` is useless: 1185 hits, because it also matches "internal" and "international" in descriptions. On TalentBrew, the US site's employment-type facet "Internship" counts 4. The 6 "Cap One Campus" jobs are the 5 US interns above plus "Investment Banking Analyst - TripleTree 2027".

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://capitalone.wd12.myworkdayjobs.com/wday/cxs/capitalone/Capital_One/jobs` | ALLOW | no matching rule |
| `https://capitalone.wd12.myworkdayjobs.com/wday/cxs/capitalone/Capital_One/job/McLean-VA/MBA-Product-Intern---Summer-2027_R244815-1` | ALLOW | no matching rule |
| `https://capitalone.wd12.myworkdayjobs.com/en-US/Capital_One/job/…` (job link) | ALLOW | no matching rule (`/Capital_One/…` is `Allow: /Capital_One/`; only `/refreshFacet/` is disallowed) |
| `https://www.capitalonecareers.com/search-jobs` (also with the bookmark's `?ascf=…`) | ALLOW | no matching rule |
| `https://www.capitalonecareers.com/search-jobs/results?…` (TalentBrew AJAX pager) | **BLOCK** | `Disallow: /search-jobs/`. This rule also blocks keyword/category URLs such as `/search-jobs/intern/234/1`, so TalentBrew can only be read one page at a time. Another reason to use Workday. |
| `https://www.capitalonecareers.com/jobs_sitemap.xml` | ALLOW | no matching rule (also the robots `Sitemap:`) |
| `https://www.capitalonecareers.com/job/<city>/<slug>/<org>/<id>` | ALLOW | no matching rule |
| `https://jobs.capitalone.co.uk/search-jobs`, `https://www.capitalonecareers.ca/search-jobs` | ALLOW | no matching rule (same `Disallow: /search-jobs/` rule) |

## Anti-bot / quirks
- No bot challenge on Workday or TalentBrew. The TalentBrew HTML is server-rendered.
- TalentBrew country sites split one Workday site by country, and `capitalonecareers.com` is not "the whole site". Watch Workday, not any single TalentBrew site.
- The bookmark's Campus=Internships filter is empty even though 7 internships are open. Capital One tags them `Campus=Graduates`, or not at all. Rely on titles and `workerSubType`, not on TalentBrew campus tags.
- **Workday 2000 cap** (see Recommended feed). The current adapter loops to `offset >= total` and checks `got == total`. At a capped `total` of 2000 that check passes silently while jobs are missing. Add a health rule: `total == 2000` means truncated.
- `postedOn` is relative. Use the detail `startDate` when an exact date matters.

## Recommended checker
```yaml
- key: capital-one
  name: Capital One
  careers_url: https://www.capitalonecareers.com/search-jobs
  checker: workday
  settings: {host: capitalone.wd12.myworkdayjobs.com, tenant: capitalone, site: Capital_One}
  # health: alert if first-page total == 2000 (Workday cap); then partition by jobFamilyGroup
```

## Evidence
- Sample: `discovery/samples/capital-one.json` is the raw first CXS page: 20 jobs plus all facets, `total` 1966, 22 KB.
- Capture: `discovery/captures/capital-one/` (bookmark page, 0 results).
- Requests: 17 HTTP requests plus robots.txt fetches, at ≤1 request/second per host. That covers:
  - 7 Workday CXS calls: page 1, CA/UK filter, Toronto filter, intern facet, 2 searches, and 1 detail.
  - TalentBrew US `/search-jobs`, the jobs sitemap, the internship pages and one job page.
  - The UK and Canada home and `/search-jobs` pages.

## Update 2026-11-10: postings without a link (`unlinked_once`)
Both reads on the morning of 2026-11-10 stopped about 340 requests in with "4 postings without externalPath", and an
hour later the site read cleanly (2,055 jobs, none without a link). The reader counted every listing of a link-less
posting, and Capital One is read whole (capped at 2,000) and then once per location, a job under each of its places
(5,011 listings for 2,055 jobs), while the limit came from the size of the search it was in: 3 in a small location's
search. A posting or two listed for a moment without a link stopped the whole read. With `unlinked_once: true` each
such posting counts once, against 2% of the whole site; more than two still mark the poll degraded and name them.
