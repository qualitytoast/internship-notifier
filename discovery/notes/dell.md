# Dell Technologies (`dell`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20 (00:15–00:21 UTC)

| | |
|---|---|
| Official careers URL | https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/careers/jobs (unfiltered). Dell's public careers address `https://jobs.dell.com/search-jobs` now **redirects** to `…/sites/careers`. The bookmark (`…/sites/careers/jobs?keyword=intern&mode=location`) is a keyword-filtered view of the same site. |
| Hiring system | **Oracle Recruiting Cloud** behind Dell's vanity host `enterpriseplatform.dell.com`, which serves both `/hcmUI` and `/hcmRestApi`. The site URL name `careers` maps to site number **`CX_1001`** (site name "Dell"). |
| Recommended adapter | shared `oracle` adapter: `{host: enterpriseplatform.dell.com, site: CX_1001}` |

**Only one site.** `GET /hcmRestApi/resources/latest/recruitingCESites?onlyData=true` returns `count: 1`: `CX_1001`, `ORA_ACTIVE`, URL name `careers`. There is no separate university site; student roles are on `CX_1001`. The old Workday tenant (`POST https://dell.wd1.myworkdayjobs.com/wday/cxs/dell/External/jobs`) returns **HTTP 422**, so it is not in use.

## Recommended feed
- **Request (list):** `GET https://enterpriseplatform.dell.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber=CX_1001,limit=200,offset={0,200,400},sortBy=POSTING_DATES_DESC`. This is the oracle adapter's own request.
- **Headers:** a normal browser UA and `Accept: application/json`. No cookies or tokens needed.
- **Pagination:** `offset` steps of 200, with a `limit` cap of 200. `TotalJobsCount` is in `items[0]` on every page. 453 jobs took **3 requests** (200 + 200 + 53). The pages are 293 KB, 305 KB and 85 KB.
- **Optional student tag (1 extra request):** the job-function facet `…,selectedTitlesFacet=INTERNS` returns the **23** jobs Dell files under job function "Interns". This includes non-English internships that a title regex misses. `…,selectedCategoriesFacet=300000036350059` ("Undergraduate Intern" category) returns 18. Both sets are inside the 23.
- **Detail (optional):** `GET https://enterpriseplatform.dell.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id=%22{Id}%22,siteNumber=CX_1001`. It gives `ExternalDescriptionStr`, `RequisitionType` (`Intern`), `Category` (`Undergraduate Intern`), `JobFunction` (`Interns`) and `JobSchedule` (`Full time`).

## Field map
Paths are relative to `items[0].requisitionList[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | `Id` | **mixed formats**: 396 numeric (`300404`), 46 `R` + 6 digits (`R281639`) and 11 `D` + 5 digits (`D11261`). Unique (453/453). Use the value verbatim in URLs. |
| title | `Title` | |
| location(s) | `PrimaryLocation` + `secondaryLocations[].Name` | e.g. `Round Rock, TX, United States`. `PrimaryLocationCountry` is ISO-2 (`US` 199 of 453). 63 jobs have secondary locations. |
| url | built: `https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/careers/job/{Id}` | the exact href format of the job cards in the rendered page (e.g. `…/job/R281639`) |
| posted date | `PostedDate` (`YYYY-MM-DD`) | |
| description / snippet | `ShortDescriptionStr` | **empty for 439 of 453**. The description is only in the detail endpoint. |
| employment type | none in the list | `WorkerType`, `JobType` and `ContractType` are null for all jobs. The flex facet "Full Time or Part Time" exists only as a facet. |
| department / team | none in the list | `Category` and `JobFunction` are detail-only (facets: categories, `titlesFacet` = job function) |
| other | `WorkplaceType` (`On-site` 288, `Field` 142, empty 23) | |

## Totals (observed 2026-10-20 00:15–00:17 UTC)
- **Feed, no filters:** `TotalJobsCount` **453**. A full enumeration of 3 pages gave **453 unique ids**.
- **Live careers page, no filters:** **453**. A Playwright render of https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/careers/jobs showed "**453 JOB**", and the page's own API call returned `TotalJobsCount: 453`.
- **Intern/student: 23** (job function "Interns"):
  - 19 titles match the title regex. **13 are in the US**, mostly TX (Round Rock / Austin):
    - Cloud Software Security (CSS) Summer Internship, Undergraduate Intern
    - Data Science Undergraduate Intern
    - Corporate Strategy Undergraduate Intern
    - Global Operations Supply Chain Undergraduate Intern - Summer 2027
    - Global Operations Supply Chain Graduate Intern
    - CSG Hardware Engineering Intern
    - Services Sales Undergraduate Intern
    - Dell Technologies Services General Business / Undergraduate Analytics / Undergraduate Engineering Intern (3 roles)
    - Dell Technologies Presales Intern
    - NextGen Sales Academy Intern (Hopkinton, MA)
    - Global Operations Supplier Process Engineer Co-Op
  - **6 are abroad:** Graduate Intern ×2 and Undergraduate Intern in Singapore, Presales Intern (2027) in Bucharest, and Data & AI Intern and Finance Internship Program for University Students in Bratislava.
  - Plus 4 without an English intern word: "Estágio em Vendas" (Brazil), "Becario(a) de soporte de ventas" (Mexico), "Schülerpraktikum (schulisches Pflichtpraktikum)" (Germany), and "STEM Aspire Mentoring Program" (Slovakia).

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `https://enterpriseplatform.dell.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?…siteNumber=CX_1001…` | ALLOW | robots.txt is 404, so allow-all |
| `…/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id=%22300404%22,siteNumber=CX_1001` | ALLOW | same |
| `…/recruitingCESites?onlyData=true` | ALLOW | same |
| `https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/careers/jobs` | ALLOW | same |
| `https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/careers/job/300404` | ALLOW | same |
| `https://jobs.dell.com/search-jobs` (redirects to the ORC site) | ALLOW | no matching rule |

## Anti-bot / quirks
- No bot challenge on the vanity host in about 13 plain-httpx requests.
- The site number and URL name differ: use **`CX_1001`** in API finders and `careers` in public URLs. I did not test `siteNumber=careers`.
- The list rows have almost no description (`ShortDescriptionStr` is empty). Fetch the detail only for new student-looking jobs.
- The list facets are top-10 only.

## Recommended checker
```yaml
- key: dell
  name: Dell Technologies
  adapter: oracle
  careers_url: https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/careers/jobs
  settings:
    host: enterpriseplatform.dell.com
    site: CX_1001
    job_url: https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/careers/job/{id}
  # optional (adapter extension): selectedTitlesFacet=INTERNS (1 extra request) tags the 23 ATS "Interns"
  #   jobs, including Estágio / Becario / Praktikum titles a regex misses
```

## Evidence
- Sample: `discovery/samples/dell.json` is the raw response of the `selectedTitlesFacet=INTERNS` query (23 jobs, with facets, 55 KB).
- Calls made: 1 list page with facets, the site list, 3 list pages (full enumeration), 2 facet lists, 1 detail, `jobs.dell.com/search-jobs` (redirect check), 1 Workday CXS probe (422), and one Playwright render of the unfiltered page. That is about 13 HTTP requests plus robots, at ≤1 request/second per host.
- Old capture: `discovery/captures/dell/`. The bookmark view (`keyword=intern`) had `TotalJobsCount` 159, against 23 real intern jobs, so ORC's keyword search matches far more than intern titles.
