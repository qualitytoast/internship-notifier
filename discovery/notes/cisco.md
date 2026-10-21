# Cisco (`cisco`)

**Status:** verified-feed (Workday). The Phenom front-end shows fewer jobs; see Totals.   ·   **Checked:** 2026-10-19 19:23–19:30 CDT (2026-10-20 00:23–00:30 UTC)

| | |
|---|---|
| Official careers URL | https://careers.cisco.com/global/en/search-results (job search, no filters). The bookmark https://careers.cisco.com/global/en/internships-and-co-ops is a filtered landing page (`selected_fields: {"raasJobRequisitionType": ["Co-Op","Intern"]}`, 51 jobs). |
| Hiring system | **Phenom People** career site (refNum **`CISCISGLOBAL`**, locale `en_global`, siteType `external`) over **Workday**. The tenant is `cisco`, site `Cisco_Careers`, on `cisco.wd5.myworkdayjobs.com`. Every Phenom job has `applyUrl` = `https://cisco.wd5.myworkdayjobs.com/Cisco_Careers/job/<loc>/<slug>_<req>/apply` and `externalApply: false`, and Phenom `jobId` = `reqId` = the Workday requisition number (e.g. `2026802`). |
| Recommended adapter | shared **`workday`** adapter, `{host: cisco.wd5.myworkdayjobs.com, tenant: cisco, site: Cisco_Careers}`. Workday has 29 more postings than Phenom, including 5 intern postings Phenom doesn't show. Phenom settings are listed below as an alternative. |

## Recommended feed
- **Request:** `POST https://cisco.wd5.myworkdayjobs.com/wday/cxs/cisco/Cisco_Careers/jobs`
- **Headers:** `Content-Type: application/json`, `Accept: application/json`, normal UA. No cookies or CSRF token.
- **Body:** `{"appliedFacets":{},"limit":20,"offset":0,"searchText":""}`
- **Pagination:** `offset` += 20 (Workday max) until `offset >= total`. `total` (1455) appears only on the first page; later pages say `total: 0`. A full read is **73 requests** (~75 s at 1 req/s). It's still under Workday's 2000-total cap, but alert if `total` reaches 2000: beyond that the CXS API stops reporting the real total and `offset ≥ 2000` wraps back to page 1 (seen on NVIDIA's tenant).
- **Detail (optional):** `GET https://cisco.wd5.myworkdayjobs.com/wday/cxs/cisco/Cisco_Careers<externalPath>` returns `jobPostingInfo` with `jobDescription`, `location` + `additionalLocations`, `country`, `startDate` (posting date), `endDate` / `timeLeftToApply`, `remoteType`, `jobReqId` and `externalUrl`.
- **Intern slice (cheap health check, 3 requests):** `appliedFacets: {"workerSubType": ["a5e1942e7b2c01c6907030106001b700"]}` (Intern (Fixed Term) (Seasonal) (Trainee)) → 58. `jobFamilyGroup` "Apprentice & Intern" `2101eee3ea96010675b0a474fc015c29` → 57, a subset of the 58.
- **Job URL:** `https://cisco.wd5.myworkdayjobs.com/en-US/Cisco_Careers` + `externalPath` (what the shared adapter builds). The Phenom page for the same job is `https://careers.cisco.com/global/en/job/<req>/<slug>`, with `slug = re.sub('[^A-Za-z0-9]+','-',title).strip('-')` (matched 6/6 links on the rendered page). It exists only if Phenom has the job.
- **Alternative: Phenom `refineSearch`** (if Workday ever becomes unavailable)
  - `POST https://careers.cisco.com/widgets`, `Content-Type: application/json`, no cookies, body:
    ```json
    {"lang":"en_global","deviceType":"desktop","country":"global","pageName":"search-results",
     "ddoKey":"refineSearch","from":0,"size":500,"jobs":true,"counts":true,
     "all_fields":["category","raasJobRequisitionType","country","state","city","type","RemoteType"],
     "selected_fields":{},"keywords":"","global":true,"sortBy":"","subsearch":"","clearAll":false,
     "jdsource":"facets","isSliderEnable":false,"siteType":"external","refNum":"CISCISGLOBAL"}
    ```
  - `size=500` is accepted. 3 requests returned all 1426 jobs (1.8 + 1.6 + 1.4 MB), with 1426 unique `jobSeqNo` (`CISCISGLOBAL<req>EXTERNALENGLOBAL`).
  - Total: `refineSearch.totalHits`. Facets: `refineSearch.data.aggregations` when `counts:true`.

## Field map (Workday CXS list `jobPostings[]`)
| Job field | Response path | Notes |
|---|---|---|
| id | `externalPath` (unique per posting) | `/job/San-Jose-California-US/Machine-Learning-Engineer-II--Intern----United-States_2026802`. Some requisitions are re-posted with a `-1` suffix (`…_2024535-1`), 21 of 115 sampled rows. |
| requisition no. | `bulletFields[0]` (`"2026802"`) | = Phenom `reqId`/`jobId` |
| title | `title` | |
| location(s) | `locationsText` (`"San Jose, California, US"` or `"4 Locations"`) | detail: `location`, `additionalLocations[]`, `country.descriptor` |
| url | `https://cisco.wd5.myworkdayjobs.com/en-US/Cisco_Careers` + `externalPath` | detail `externalUrl` has no `/en-US` |
| posted date | `postedOn` (relative: "Posted 25 Days Ago", "Posted 30+ Days Ago") | detail `startDate` (ISO date). Closing date in `endDate`. |
| description / snippet | detail `jobDescription` (HTML) | |
| employment type | `timeType` (`Full time` / `Part time`); worker sub-type only through the facet | |
| department / team | facet `jobFamilyGroup` only | |
| other | detail `remoteType` (`Hybrid` …), `canApply`, `timeLeftToApply` | |

## Totals (observed 2026-10-19)
| Measure | Value | How observed |
|---|---|---|
| Feed (Workday CXS), no filters | **1455** | `total` on page 1. The facet sums agree: workerSubType 1378 + 58 + 19, timeType 1454 + 1, jobFamilyGroup 1455. |
| Workday careers page, no filters | **1455** | Playwright render of https://cisco.wd5.myworkdayjobs.com/en-US/Cisco_Careers: "**1455 JOBS**", "of 1455 jobs" |
| Phenom careers page, no filters | **1426** | Playwright render of https://careers.cisco.com/global/en/search-results: "**1426 results**", "Showing 1 -10 of 1426". `refineSearch.totalHits` = 1426, and all 1426 were read. |
| Phenom vs Workday | Phenom lacks 29 Workday postings. They're spread across ages: 2 of the 60 newest Workday rows (posted 5 and 14 days ago) and 0 of the 55 oldest are missing from Phenom. | 1426 Phenom ids vs Workday intern slice + 6 sampled Workday pages |
| **Intern/student** | **58** = Workday workerSubType "Intern (Fixed Term) (Seasonal) (Trainee)". Its union with jobFamilyGroup "Apprentice & Intern" (57), Phenom category "Internships, Apprenticeships, and Co-Ops" (52) and a Phenom title regex (53) is still 58. **41 are in the US.** | both Workday slices fully listed (3 + 3 requests) |
| Phenom "Internships & Co-ops" page | **51** = raasJobRequisitionType Intern 37 + Co-Op 14 | It **misses 8 of the 58**. 5 aren't on Phenom at all: 2024535-1 Hardware Engineer I, 2024552-1 Business Analyst I, 2024561-1 Data Analyst I and 2024569-1 Product Lifecycle Supply Chain Project Specialist I (all "(Intern) – United States", Workday re-postings "Posted 30+ Days Ago"; 2024535-1 is still open until 2026-10-30), plus 2028776 Amplify Marketing Specialist Intern, Singapore (posted today). 3 are on Phenom but tagged with another requisition type: 2023625 Software Engineer – Intern (UK), 2026269 Critical Accounts Manager I (Intern) – Mexico and 2028084 Splunk Solutions Engineer (Intern) – US. The page also includes 1 non-intern, 2027802 "FLEX Emerging Leaders I (Full Time)". |

Choice: **Workday is complete** (1455 = its page) and robots-allowed. Phenom misses about 2% of postings, including 5 interns (4 of them US), so use it only as a fallback.

## robots.txt
cisco.wd5.myworkdayjobs.com: `Allow: /Cisco_Careers/`, `Disallow: /refreshFacet/`, and a Sitemap line. careers.cisco.com (Phenom) disallows `*/apply`, `*/applythankyou`, `*/jobcart`, `*/chatbot`, `*/px-widgets`, `*/socialAut`, `*/iauth`, `*/pxhome…`, `*/glassdoor` and others, but not `/widgets`.

| URL | Verdict | Deciding rule |
|---|---|---|
| `https://cisco.wd5.myworkdayjobs.com/wday/cxs/cisco/Cisco_Careers/jobs` | ALLOW | no matching rule |
| `https://cisco.wd5.myworkdayjobs.com/wday/cxs/cisco/Cisco_Careers/job/San-Jose-California-US/Machine-Learning-Engineer-II--Intern----United-States_2026802` | ALLOW | no matching rule |
| `https://cisco.wd5.myworkdayjobs.com/en-US/Cisco_Careers` and `/en-US/Cisco_Careers/job/…_2026802` | ALLOW | no matching rule |
| `https://cisco.wd5.myworkdayjobs.com/refreshFacet/…` | **BLOCK** | `Disallow: /refreshFacet/` |
| `https://careers.cisco.com/widgets` (POST) | ALLOW | no matching rule |
| `https://careers.cisco.com/global/en/search-results`, `/global/en/internships-and-co-ops`, `/global/en/job/2026802/Machine-Learning-Engineer-II-Intern-United-States`, `/global/en/sitemap_index.xml` | ALLOW | no matching rule |
| `https://careers.cisco.com/global/en/apply?jobSeqNo=…` | **BLOCK** | `Disallow: */apply`. Never fetch it. |

## Anti-bot / quirks
- No bot challenge on either host. 12 Workday POSTs, 3 Workday GETs and 5 Phenom POSTs ran at ≥ 1.15 s spacing with no errors.
- Workday `postedOn` is relative. Use the detail `startDate` if an exact date is needed.
- Re-posted requisitions get a `-1` suffix in `externalPath`, and the same requisition number can appear in two postings over time, so dedupe alerts by `externalPath`. 4 of the 5 Phenom-missing interns are such re-postings.
- Phenom's `raasJobRequisitionType` (shown as a facet) and its category don't line up exactly with Workday's worker sub-type. Our code should classify by title and keep the Workday intern facet as a health check.
- The internships landing page sends `ddoKey: eagerLoadRefineSearchSession`, which returns only a token flag; `refineSearch` is the call that returns jobs (same as Brevan Howard).

## Recommended checker
```yaml
- key: cisco
  name: Cisco
  category: big-tech
  careers_url: https://careers.cisco.com/global/en/search-results
  checker: workday
  settings: {host: cisco.wd5.myworkdayjobs.com, tenant: cisco, site: Cisco_Careers}
  # 73 pages of 20 per full read (1455 jobs). Alert if total reaches 2000 (CXS cap).
  # fallback / cross-check (3 requests of size 500, but misses ~2% of postings):
  # phenom {base_url: https://careers.cisco.com, ref_num: CISCISGLOBAL, lang: en_global, country: global,
  #         site_type: external, page_name: search-results, job_path: /global/en/job/{jobId}/{slug}, page_size: 500}
```

## Evidence
- Sample: `discovery/samples/cisco.json` (196 KB): the raw Workday CXS unfiltered page 1 with facets (total 1455), the raw Workday job detail for 2026802, and the raw Phenom `refineSearch` unfiltered response (size 10, totalHits 1426, aggregations).
- Requests: 21 scripted requests (Workday: unfiltered, intern sub-type 3 pages, Apprentice & Intern family 3 pages, 5 sampled pages, 2 details, plus robots; Phenom: unfiltered, intern+co-op slice, 3 × size-500 pages, plus robots), 3 Playwright page loads (2 Phenom, 1 Workday), and 2 `robots_check.py` runs.
- Old capture: `discovery/captures/cisco/` (Internships & Co-ops page: 51 results).
