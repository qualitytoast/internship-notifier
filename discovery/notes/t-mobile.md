# T-Mobile (`t-mobile`)

**Status:** needs-custom (Workday feed is complete only with partitioned requests: `total` is capped at 2000)   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://careers.t-mobile.com/jobs (unfiltered: "Showing 1 - 10 of 2510 jobs"). The bookmark `https://careers.t-mobile.com/internship?keyword=intern` is the same index with the keyword `intern` and shows **1 job**. |
| Hiring system | **Workday** tenant `tmobile`, site **`External`** on `tmobile.wd1.myworkdayjobs.com`. The front end `careers.t-mobile.com` is a **Paradox** career site (assets on `cdn.sites.paradox.ai`, `companyName` "T-Mobile Career Site PROD", companyID `158871-53568`) that copies Workday on a schedule. Every Paradox job has `applyURL` `https://tmobile.wd1.myworkdayjobs.com/External/job/…/apply` and a Workday `requisitionID` (`REQ…`). |
| Other Workday sites | The tenant's robots.txt names three audience-specific sites: `Alumni` (1893 jobs for former employees; a sub-board of External postings), `ContractorConversion` (3) and `MergersandAcquisitions` (1). None is a student board, and careers.t-mobile.com links none of them. **There is no early-career/university site**: the internship page only filters the same index, and the guesses `University` and `EarlyCareers` return 404. |
| Recommended adapter | `workday`, **extended with facet partitions** (two requests sets, Full time + Part time). The unpartitioned adapter silently stops at 2000 of 2534 jobs. |

## Recommended feed
- **Request (two partitions, same URL):** `POST https://tmobile.wd1.myworkdayjobs.com/wday/cxs/tmobile/External/jobs`
  - Partition A, Full time (641): `{"appliedFacets":{"timeType":["00e635b327af1034ee747b165ed6005c"]},"limit":20,"offset":N,"searchText":""}`
  - Partition B, Part time (1893): `{"appliedFacets":{"timeType":["00e635b327af1034ee747b132575005b"]},"limit":20,"offset":N,"searchText":""}`
- **Headers:** `Accept: application/json`, `Content-Type: application/json`. No cookies.
- **Why partitions — the 2000 cap:** the unfiltered first page returns `total: 2000`, but its facets add up to **2534** (timeType 641 + 1893, workerSubType 2532 + 2, locationCountry USA 2533). Offsets 1980 return real jobs, but offsets **2000, 2020 and 2520 return page 1 again** with `total: 2000`. The current adapter loops until `offset >= total` and then checks `got == total`. That check passes with 2000 == 2000 and silently loses 534 jobs.
- **Each partition is below the cap and pages cleanly to its end.** Part time at offset 1880 returned 13 jobs (= 1893). Full time at offset 640 returned 1 (= 641). One full scan is 33 + 95 = 128 requests of about 5–20 KB each; the first page with facets is 116 KB.
- **Adapter rule:** read the first unfiltered page and take the `timeType` facet values and counts. Fetch each value as its own partition and assert:
  - every partition `total` < 2000
  - the partition totals add up to the facet sum
  - the unique `externalPath`s add up to the same sum

  If a partition ever reaches 2000 (retail hiring season could push Part time there), split it further by `locationRegionStateProvince` (52 states, largest California 270).
- **Order:** newest first. All of page 1 is "Posted Today", which suits quick scans for new postings.
- **Detail (optional):** `GET https://tmobile.wd1.myworkdayjobs.com/wday/cxs/tmobile/External<externalPath>`. It returns `jobPostingInfo` with `jobDescription`, `location`, `additionalLocations`, `startDate` (posting date), `endDate`, `timeLeftToApply` and `timeType`. Internship windows can be short: REQ375880 was posted 2026-10-19 with `endDate` 2026-10-26 ("6 days left to apply").
- **Student facet:** `Job_Family_Group` "Intern - Group" id `426b19690b7b1036f85c59a787b10a19` (2 jobs). It is a cheap extra quick query, but not a proof of completeness: the full scan stays authoritative.

### Why not the Paradox front end
- The server-rendered pages (`/jobs`, `/jobs/page/N`, 10 jobs per page, 251 pages of about 230 KB) are reachable. They embed `window.__PRELOAD_STATE__.jobSearch` (`totalJob`, `jobs[]`, `facets[]`).
- Their JSON API `POST https://careers.t-mobile.com/api/get-jobs?radius=15&page_number=N&enable_kilometers=false` (body `{"disable_switch_search_mode":false,"site_available_languages":["en","en-us"]}`) returns **403 "Access Denied"** (Akamai, `ak_bmsc` cookie) unless the client first loads `/jobs` and sends back that page's `ct` session cookie (a signed token). With the cookie it returns 200.
- `page_size` is ignored, so the API always returns 10 jobs per page, with full descriptions (about 185 KB per page). A full scan would be 251 heavy requests that depend on a session cookie.
- **Paradox lags Workday.** REQ375880 "2027 Summer Human Resources & Workplace Experience Internship" was posted on Workday on 2026-10-19 and was not on Paradox's internship page an hour later. That posting's apply window is 7 days.
- Workday CXS is the openly reachable system of record, so it is the primary feed. Paradox is a cross-check only: compare `totalJob` with the Workday facet sum.

## Field map
Paths are relative to `jobPostings[]` in the Workday CXS list.

| Job field | Response path | Notes |
|---|---|---|
| id | `externalPath` (unique per posting) | Requisition `bulletFields[0]` (`REQ368322`). Reposts carry suffixes (`REQ375014-1`). |
| title | `title` | |
| location(s) | `locationsText` | "3 Locations" when multiple; the detail has `location` + `additionalLocations[]`. |
| url | built: `https://tmobile.wd1.myworkdayjobs.com/en-US/External` + `externalPath` | Use `/en-US/…`: the bare `/External/…` path is robots-disallowed (it is only a link anyway). |
| posted date | `postedOn` (relative) | Exact date in the detail `startDate`, plus `endDate` |
| description / snippet | detail only | |
| employment type | partition (`timeType` Full/Part time) | `workerSubType`: `Regular` / `Temporary`. Interns are found by title or by Job_Family_Group "Intern - Group". |
| department / team | facet `Job_Family_Group` only | 21 groups. `Sales - Group` has 2351 jobs: T-Mobile is mostly retail. |
| Paradox cross-ref | `__PRELOAD_STATE__.jobSearch.jobs[]` | `requisitionID` (= Workday REQ), `uniqueID` (32-hex id in the careers.t-mobile.com URL `/<slug>/job/<uniqueID>`), `employmentType` (`["Intern","Full Time"]`), `customFields[cf_date_posted]` |

## Totals (observed 2026-10-20 00:15–00:30 UTC)
- **Feed, no filters:** **2534**. That is the sum of the timeType facets and of the partition totals (641 + 1893). The unfiltered `total` field reads 2000 (cap).
- **Live careers page, no filters:** **2510**. The server-rendered `careers.t-mobile.com/jobs` shows "Showing 1 - 10 of 2510 jobs" (`__PRELOAD_STATE__.jobSearch.totalJob` 2510, Brand facet T-Mobile 2505 + Mint 5). After a click on Next, the Playwright render showed "Showing 11-20 of 2510".
- **Why the feed is larger (+24, 1%):** Paradox is a copy that syncs on a schedule. Its state counts differ from Workday's in **both** directions: CA 272 vs 270, FL 98 vs 100, MA 56 vs 59, MN 35 vs 41, IL 107 vs 106, KS 109 vs 108. That pattern is sync lag, not a filtered subset. A posting that is live in Workday is missing from Paradox (REQ375880 above). Workday is the complete, current source.
- **Intern/student: 2.** Method: Workday `Job_Family_Group = Intern - Group` (count 2), checked against the top of the relevance-sorted Workday `searchText: intern`. Both internships rank first there; the next 18 results are "Internal…" or "International…" jobs. Paradox `keyword=intern` (46 hits) also has only one intern title.
  - REQ368322 "Summer 2027 Software Engineering Intern", Bellevue, WA. Posted 2026-10-15 and visible on Paradox (`employmentType` Intern).
  - REQ375880 "2027 Summer Human Resources & Workplace Experience Internship", Overland Park KS / Bellevue WA / Frisco TX. Posted 2026-10-19 and closes 2026-10-26. Not yet on Paradox.

  I did not enumerate all 2534 titles, which would take 128 requests. An intern posted under another job family would only be caught by the full scan.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://tmobile.wd1.myworkdayjobs.com/wday/cxs/tmobile/External/jobs` | ALLOW | no matching rule |
| `https://tmobile.wd1.myworkdayjobs.com/wday/cxs/tmobile/External/job/…_REQ375880` (detail) | ALLOW | no matching rule |
| `https://tmobile.wd1.myworkdayjobs.com/External/job/…` (Paradox `applyURL`) | **BLOCK** | `Disallow: /External/`. The tenant hides its Workday UI from crawlers. Never fetch it; link `/en-US/External/job/…` (no matching rule) or the Paradox job page. |
| `https://tmobile.wd1.myworkdayjobs.com/wday/cxs/tmobile/Alumni/jobs` | ALLOW | no matching rule (`/Alumni/`, `/ContractorConversion/` and `/MergersandAcquisitions/` site paths are disallowed) |
| `https://careers.t-mobile.com/jobs`, `/jobs/page/2`, `/internship?keyword=intern` | ALLOW | robots.txt is just `User-agent: *` (no rules) |
| `https://careers.t-mobile.com/api/get-jobs?…` | ALLOW | no rules (but Akamai/session-cookie gated, see above) |
| `https://careers.t-mobile.com/summer-2027-software-engineering-intern/job/F9EEFE5CE6031CEFCEC39A69DF82225F` | ALLOW | no rules |

## Anti-bot / quirks
- No challenge on Workday CXS. On careers.t-mobile.com, the HTML is served to plain httpx. The JSON API is Akamai-gated (403 "Access Denied" without the page's `ct` cookie). I did not try to work around this beyond the normal page-then-XHR order a browser uses.
- **Workday's 2000 cap is the main trap.** Any adapter health check must treat `total == 2000` as "truncated". Capital One (1966, same day) is close to the same cap.
- T-Mobile is mostly retail: 2140 of 2510 Paradox jobs are "Retail Sales". Corporate and student roles are a small slice, so a newest-first quick scan of the Full time partition catches new internships fastest.
- The Paradox job URL uses a 32-hex `uniqueID` that is not in Workday. Use Workday `externalPath` as the id and link the Workday `/en-US/External…` URL.

## Recommended checker
```yaml
- key: t-mobile
  name: T-Mobile
  careers_url: https://careers.t-mobile.com/jobs
  checker: workday            # needs a small extension: settings.partitions (see note)
  settings:
    host: tmobile.wd1.myworkdayjobs.com
    tenant: tmobile
    site: External
    partitions:               # each must stay < 2000; sum must equal the timeType facet sum (2534 today)
      - {timeType: ["00e635b327af1034ee747b165ed6005c"]}   # Full time (641)
      - {timeType: ["00e635b327af1034ee747b132575005b"]}   # Part time (1893)
    quick_queries:
      - {Job_Family_Group: ["426b19690b7b1036f85c59a787b10a19"]}   # "Intern - Group" (2)
  big: true                   # 128 requests per full scan; newest-first order allows quick scans
```

## Evidence
- Sample: `discovery/samples/t-mobile.json` is the raw unfiltered first CXS page: `total` 2000 (capped), 20 jobs and all facets summing to 2534. 116 KB.
- Capture: `discovery/captures/t-mobile/` (bookmark internship page, "1 job").
- Requests: 27 HTTP requests plus 3 robots.txt fetches, at ≤1 request/second per host. That covers:
  - 17 Workday CXS calls: page 1, 4 offset-cap probes, 2 partition totals, 2 partition tails, the intern group, the intern search, 1 detail, and 5 site checks (3 real sites + 2 guesses).
  - 5 Paradox HTML pages: `/jobs` ×3, the internship page and the keyword page.
  - 1 Paradox JS bundle.
  - 4 Paradox API calls (2 × 403, 2 × 200 after loading the page).
  - 1 Playwright page load of `/jobs` with one click on Next.
