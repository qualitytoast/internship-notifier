# Oracle (`oracle`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20 (00:10–00:21 UTC)

| | |
|---|---|
| Official careers URL | https://careers.oracle.com/en/sites/jobsearch/jobs (unfiltered). www.oracle.com/careers/ and www.oracle.com/careers/students-grads/ only link to this site (`/en/sites/jobsearch/jobs?...`). The bookmark is a filtered view of the same site: `keyword=Internship`, flex field `AttributeChar13|Campus` and two locations (it showed 8 jobs). |
| Hiring system | **Oracle Recruiting Cloud** (Oracle HCM Candidate Experience). The page at careers.oracle.com is the ORC app; it calls the REST API on `eeho.fa.us2.oraclecloud.com`. Site number **`CX_45001`** (site URL name `jobsearch`, site name "Oracle"). |
| Recommended adapter | shared `oracle` adapter, one site: `{host: eeho.fa.us2.oraclecloud.com, site: CX_45001}` |

**Campus is not a separate site.** `GET /hcmRestApi/resources/latest/recruitingCESites?onlyData=true` (public) lists every career site on the pod: 6 sites, and only `CX_45001` is `ORA_ACTIVE`. The other 5 (`CX_1` "Oracle Modern FOR REFERENCE ONLY", `CX_41001` "Talent Network … NO LONGER USED", `CX_48001` "Baseline DO NOT UPDATE", `CX_77003` and `CX_78003` backups) are `ORA_INACTIVE`. Campus, intern and graduate roles are on `CX_45001`. They are marked with requisition flex fields: `AttributeChar13` "Experience Level" = `Campus` (shown as "Graduate") and `AttributeChar4` "Job Type" = `Student/Intern`.

## Recommended feed
- **Request (list):** `GET https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber=CX_45001,limit=200,offset={0,200,400,…},sortBy=POSTING_DATES_DESC`
  - This is exactly what `src/internwatch/adapters/oracle.py` sends. I tested the adapter's httpx-encoded form (`finder=findReqs%3BsiteNumber%3DCX_45001%2Climit%3D200…`) and it returned the same 200 rows with `SortBy: POSTING_DATES_DESC`.
- **Headers:** a normal browser UA and `Accept: application/json`. No cookies, CSRF token or session needed.
- **Pagination:** `offset` steps of 200. `limit` caps at 200 (as for Uber's ORC). `TotalJobsCount` is in `items[0]` and is repeated on every page. The outer `hasMore` is always false because it describes the one-item wrapper, not the job list. 2380 jobs took **12 requests** (11 × 200 + 177). Each 200-job page is about 390 KB.
- **Optional student tag (1 extra request):** the list rows do **not** carry the flex fields: `requisitionFlexFields` comes back empty even with `expand=…requisitionFlexFields`. To get the hiring system's own intern flag, also fetch the facet-filtered list:
  `…finder=findReqs;siteNumber=CX_45001,limit=200,offset=0,selectedFlexFieldsFacets=%22AttributeChar4%7CStudent%2FIntern%22` (18 jobs). `…selectedFlexFieldsFacets=%22AttributeChar13%7CCampus%22` gives the campus set (21 jobs). The current adapter has no facet option, so this would be a small addition. Without it, title matching still catches 16 of the 18.
- **Detail (optional):** `GET https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id=%22{Id}%22,siteNumber=CX_45001`. It gives `ExternalDescriptionStr`, `ExternalResponsibilitiesStr`, `ExternalQualificationsStr`, `RequisitionType` (`Campus` for the SDR interns), `Category`, `JobFunction`, and `requisitionFlexFields` with `{"Prompt":"Job Type","Value":"Student/Intern"}`, which the list leaves out.
- **Keyword search is useless for interns:** `keyword="intern"` returns **2229** of 2380 jobs, because it matches "internal", "international", etc.

## Field map
Paths are relative to `items[0].requisitionList[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | `Id` | numeric string, e.g. `345686`; 2377/2377 unique |
| title | `Title` | e.g. `Sales Development Rep Intern - Austin, TX- Summer 2027` |
| location(s) | `PrimaryLocation` + `secondaryLocations[].Name` | e.g. `Nashville, TN, United States`. `PrimaryLocationCountry` is the ISO-2 code (`US` 1978 of 2377). 814 jobs have secondary locations (up to 8). |
| url | built: `https://careers.oracle.com/en/sites/jobsearch/job/{Id}` | the exact link format of the job cards in the rendered search page. The adapter's default template would point at eeho's hcmUI, so set `job_url`. |
| posted date | `PostedDate` (`YYYY-MM-DD`) | range 2024-10-06 … 2026-10-19 |
| description / snippet | `ShortDescriptionStr` (plain text, about 600 chars) | full HTML only in the detail endpoint |
| employment type | none in the list | `WorkerType`, `JobType` and `ContractType` are null for all 2377 jobs. Use the title, or the Student/Intern facet request above. |
| department / team | none in the list | `Category` and `JobFunction` are detail-only. Facets: 18 categories such as "Product and Research" 824. |
| other | `HotJobFlag`, `TrendingFlag`, `WorkplaceType` (always "") | |

## Totals (observed 2026-10-20 00:10–00:20 UTC)
- **Feed, no filters:** `TotalJobsCount` **2380** (2381 ten minutes earlier). A full enumeration of 12 pages returned **2377 unique ids, with no duplicates**. The last page (offset 2200) held only 177 rows, so the server itself lists 3 fewer rows than its count. This is not pagination drift: there were no duplicates and the order was monotonic. It is within the adapter's `tolerance=3`, but only just (`got + 3 < total` is false at exactly 3). Consider tolerance 5–10 for this site.
- **Live careers page, no filters:** **2380**. A Playwright render of https://careers.oracle.com/en/sites/jobsearch/jobs showed "**2380 Job**", and the page's own API call (limit 14) returned `TotalJobsCount: 2380`.
- **Facets (no filter):** Job Type: Regular Employee 2342, **Student/Intern 18**, Contractor 14, Temporary 7. Experience Level: Professional 2358, **Campus ("Graduate") 21**, Executive 2.
- **Intern/student: 18** (Job Type = Student/Intern):
  - 5 × "Sales Development Rep Intern - {Austin, Nashville, Burlington, Denver, Santa Monica} - Summer 2027" (345686–345690, posted 2026-09-18)
  - "Financial Analyst Intern" (Nashville)
  - 10 "… Intern - OVIP" roles (posted 2026-05-19 to 2026-06-02, still open, no term in the title)
  - "Research Assistant - PFE 2027" (Casablanca; PFE is an end-of-studies internship)
  - "SkillBridge NetSuite Military Fellowship: September - November 2026"

  The title regex (filters.yaml `role.strong`) matches 16, all inside the 18. The Campus set (21) adds new-grad and trainee roles: Data Centre Technician Trainee Programs (MY, AU, TH), Catalyst data-center training programs, Sales Development Representative June 2027, "February 2027 - Undergrad Software Engineer - OCI", and "GBF Financial Analyst 1".

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?…siteNumber=CX_45001…` | ALLOW | robots.txt is 404, so allow-all |
| `…/recruitingCEJobRequisitions?…selectedFlexFieldsFacets=%22AttributeChar4%7CStudent%2FIntern%22` | ALLOW | same |
| `…/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id=%22345686%22,siteNumber=CX_45001` | ALLOW | same |
| `…/recruitingCESites?onlyData=true` | ALLOW | same |
| `https://careers.oracle.com/en/sites/jobsearch/jobs` | ALLOW | `/robots.txt` returns HTTP 200 with an HTML "Page not found" page, so there are no rules |
| `https://careers.oracle.com/en/sites/jobsearch/job/345686` | ALLOW | same |
| `https://www.oracle.com/careers/students-grads/` | ALLOW | `Allow: /` |

## Anti-bot / quirks
- No bot challenge on eeho or careers.oracle.com in about 25 plain-httpx requests.
- Facet lists in the response are **truncated to the top 18 values**, so they cannot be summed to a total.
- Responses are `application/vnd.oracle.adf.resourcecollection+json`, so parse them as JSON.
- Sorting is by posting **day**, and page boundaries fall inside same-day ties. No duplicates or gaps showed up across the 12 pages, but dedupe by `Id` anyway.
- The bookmark's location ids (`300000000106749`, `300000000149325`) and `lastSelectedFacet` are UI state only. The checker should use the plain site query.

## Recommended checker
```yaml
- key: oracle
  name: Oracle
  adapter: oracle
  careers_url: https://careers.oracle.com/en/sites/jobsearch/jobs
  settings:
    host: eeho.fa.us2.oraclecloud.com
    site: CX_45001
    job_url: https://careers.oracle.com/en/sites/jobsearch/job/{id}
  # optional (adapter extension): one extra request to tag students by the ATS flag
  #   selectedFlexFieldsFacets: '"AttributeChar4|Student/Intern"'   -> employment_type "Student/Intern"
  health:
    tolerance: 10      # server lists ~3 fewer rows than TotalJobsCount
```

## Evidence
- Sample: `discovery/samples/oracle.json` is the raw response of the Student/Intern facet query (18 jobs, with all facets, 45 KB).
- Calls made: site settings, site list (recruitingCESites), site pages, 12 list pages, 3 filtered lists (Student/Intern, Campus, keyword "intern"), 1 detail. Plus www.oracle.com/careers/ and /careers/students-grads/ (to look for other sites) and one Playwright render of the unfiltered search page. That is about 25 HTTP requests plus robots, at ≤1 request/second per host.
- Old capture: `discovery/captures/oracle/` (the bookmark view: 8 jobs, the same `CX_45001`).
