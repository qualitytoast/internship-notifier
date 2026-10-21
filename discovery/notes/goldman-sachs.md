# Goldman Sachs (`goldman-sachs`)

**Status:** verified-feed (needs a small custom GraphQL adapter — no shared ATS adapter fits)   ·   **Checked:** 2026-10-19

| | |
|---|---|
| Official careers URL | Job search: **https://higher.gs.com/** ("Open Roles" link on goldmansachs.com/careers). Listing pages: `/results` (professional) and `/campus` (students). Role pages: `https://higher.gs.com/roles/<id>`. Old bookmark https://www.goldmansachs.com/careers/students/programs-and-internships lists programs only (marketing pages, not postings). |
| Hiring system | "Higher" — GS's in-house Next.js careers site backed by its own GraphQL API at `api-higher.gs.com`; every role is sourced from **Oracle Recruiting Cloud** (`externalSourceType: ORACLE`, applications go to `hdpc.fa.us2.oraclecloud.com`, site `LateralHiring` = `CX_3002`). The schema also has an `AVATURE` source type, but no current role uses it. |
| Recommended adapter | custom `gs_higher` (GraphQL POST + page loop); settings below |

## Recommended feed
- **Request:** `POST https://api-higher.gs.com/gateway/api/v1/graphql`
- **Headers:** `Content-Type: application/json` (required), `Accept: application/json`. That's all it needs: a request with only Content-Type and a browser UA returned 200. The site also sends `Origin/Referer: https://higher.gs.com` and random `x-higher-request-id` / `x-higher-session-id` UUIDs, but the API doesn't need them. No cookies, token or auth.
- **Body** (one query covers all external roles; `experiences` is required):
```json
{"operationName": "GetRoles",
 "variables": {"searchQueryInput": {
     "page": {"pageSize": 250, "pageNumber": 0},
     "sort": {"sortStrategy": "POSTED_DATE", "sortOrder": "DESC"},
     "experiences": ["PROFESSIONAL", "EARLY_CAREER", "CAMPUS"],
     "filters": [], "searchTerm": ""}},
 "query": "query GetRoles($searchQueryInput: RoleSearchQueryInput!) { roleSearch(searchQueryInput: $searchQueryInput) { totalCount page { pageSize pageNumber hasNext } items { roleId corporateTitle jobTitle jobFunction division status externalJobStatus locations { primary city state country corporateRegion } shortDescription lastPostedDate startDate compensation { minSalary maxSalary currency } externalSource { sourceId secondarySourceId externalSourceType } } } }"}
```
- **Pagination:** `pageNumber` starts at 0. **Max `pageSize` is 250**: a larger value returns `validationErrors: "roleSearch.searchQueryInput.page.pageSize": ["must be less than or equal to 250"]`. Stop when `data.roleSearch.page.hasNext == false`. The total is in `data.roleSearch.totalCount`. Today this takes 4 requests (250+250+250+141), about 1 MB in all without `descriptionHtml`.
- **Cheap health check (optional):** `query { roleSearchCount(searchCountInput: {experiences: [PROFESSIONAL, EARLY_CAREER, CAMPUS]}) }` returns `{"data":{"roleSearchCount":891}}`.
- **Detail (optional, for full description and apply URL):** same URL, `{"operationName":"GetRoleById","variables":{"externalSourceId":"<sourceId>","externalSourceFetch":true},"query":"query GetRoleById($externalSourceId: String!, $externalSourceFetch: Boolean) { role(externalSourceId: $externalSourceId, externalSourceFetch: $externalSourceFetch) { descriptionHtml applyActive status externalSource { externalApplicationUrl applyInExternalSource sourceId } } }"}`. This is the exact operation the role page itself sends.
  - Alternative: add `descriptionHtml` to the list query instead. It adds about 3 KB per role (all 219 campus roles came to 656 KB).
- **How the query was derived:** the site's own `GetRoles` / `GetCampusRoles` query text is in the `/results` and `/campus` page chunks, which robots.txt disallows, so I didn't fetch them. The query above uses argument, type and field names from the live schema; GraphQL introspection is enabled on api-higher.gs.com. The operation names (`GetRoles`, `GetCampusRoles`, `GetRoleFilters`, `GetRoleSearchFiltersCount`, `GetRoleById`) and the result shapes match the MSW mocks shipped in the site's `_app` bundle, which was loaded while rendering the allowed role page.
- Other enums: `experiences` ∈ PROFESSIONAL | EARLY_CAREER | CAMPUS | INTERNAL_MOBILITY. INTERNAL_MOBILITY is for internal candidates only; don't use it. `sortStrategy` ∈ RELEVANCE | POSTED_DATE. `filters` per the schema = `[{"filterCategoryType": "LOCATION", "filters": [{"filter": "United States", "subFilters": []}]}]` (untested). The valid categories for CAMPUS are EXPERIENCE_LEVEL, EDUCATION_LEVEL, GRADUATION_YEAR, DIVISION and LOCATION; RECRUITING_TYPE is rejected ("entity not valid for current tenant"). The checker should fetch everything and filter locally.

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `items[].externalSource.sourceId` | Oracle requisition number (e.g. `170705`). It is unique across all 891 roles and is also the public URL id. Don't use `roleId`: it's `<sourceId>_<GS_CAMPUS\|GS_MID_CAREER\|GS_EARLY_CAREER\|GS_EXECUTIVE\|GS_NOTICE_OF_FILING_LCA>` for 870 roles, but a UUID for 21 older ones. |
| title | `items[].jobTitle` | Campus titles look like `2027 \| Americas \| New York City Area \| Executive Office, Global Marketing \| Summer Analyst` (year \| region \| city \| division \| program). `corporateTitle` is the level: Summer Analyst / Summer Associate / Seasonal / Analyst / Associate / Vice President … |
| location(s) | `items[].locations[]` → `city`, `state`, `country`, `corporateRegion` (Americas / EMEA / Asia Except Japan / Japan / India), `primary` | 19 roles have several locations |
| url (detail/apply) | `https://higher.gs.com/roles/{externalSource.sourceId}` | robots allows it (`Allow: /roles/`). The apply URL is only in the detail query (`externalSource.externalApplicationUrl`), e.g. `https://hdpc.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/LateralHiring/job/170705/apply/email` |
| posted date | `items[].lastPostedDate` | ISO instant, e.g. `2026-10-19T21:54:14.722Z`. `startDate` is close to it. Don't use `createdDate`: it's the indexing time (118 roles show 2026-08-16). |
| description / snippet | `items[].shortDescription` | 889/891 non-empty; HTML entities; sometimes a placeholder (`"x"`). Full HTML is in `descriptionHtml` (list or detail). |
| employment type | none | `jobType` is null for all 891. Use `corporateTitle` instead: Summer Analyst, Summer Associate and Seasonal (off-cycle, apprentice, work placement) are student roles; campus Analyst/Associate are full-time "New Analyst/New Associate". The `roleId` suffix `_GS_CAMPUS` marks campus roles. |
| department / team | `items[].division` (+ `jobFunction` for professional roles) | |
| extra | `compensation{minSalary,maxSalary,currency}`, `status` (POSTED/SCHEDULED/OTHER), `externalJobStatus` | all 891 are POSTED today |

## Totals (observed 2026-10-19)
- **Feed, no filters:** **891** roles. That's `roleSearch.totalCount` for PROFESSIONAL+EARLY_CAREER+CAMPUS, and also equals `roleSearchCount`. I paged all of them: 4 pages, 891 unique `sourceId`s.
  - PROFESSIONAL 668 + EARLY_CAREER 4 = **672**. This is the professional set behind `/results`.
  - CAMPUS **219**. This is the student set behind `/campus`. It doesn't overlap the professional set (672 + 219 = 891).
  - INTERNAL_MOBILITY 672 (internal candidates only).
  - Campus by level: Summer Analyst 74, Summer Associate 17, Seasonal 87, Analyst 21, Associate 20.
  - Campus by region: EMEA 113, Americas 89, Asia Except Japan 10, Japan 6, India 1.
- **Live careers page, no filters:** I couldn't observe it. higher.gs.com's robots.txt disallows `/results`, `/campus` and everything else except `/roles/`, so no automated render was done. The UI's label `Showing 20 of {N} matches` comes from the same `roleSearch.totalCount`: component `c7({totalCount, pageSize})` in the `_app` bundle, fed by `getResultsParser(data)`. So the UI should show 672 on /results and 219 on /campus.
- **Oracle LateralHiring site (CX_3002) for comparison:** `TotalJobsCount` = **651**. It's an incomplete subset: campus roles are essentially missing (keyword "Summer Analyst" → 2 hits, no list), so it's not suitable as the feed.
- **Intern/student:**
  - **170** by title regex (all of them campus roles).
  - **178** campus internship/placement postings by `corporateTitle` ∈ {Summer Analyst, Summer Associate, Seasonal}. The regex misses 8 "One Year Work Placement" titles and 1 "Industrial Trainee".
  - **Americas: 60** internship postings: Summer Analyst 41, Summer Associate 13, Seasonal 6. That's US 54, plus 6 Seasonal-level roles in Sao Paulo, Santiago (2), Mexico City (2) and Lima. Americas campus total is 89, including 29 full-time New Analyst/Associate roles.
  - By year: 57 are 2027 and 3 are 2026.
- **Programs feed** (old bookmark): `GET https://www.goldmansachs.com/feeds/programs-and-internships.json`
  - A JSON array of **25** program pages; 14 have programType internship.
  - With the bookmark's filters (internship + Americas) it shows 2: "2027 Summer Analyst Program" and "2027 Summer Associate Program".
  - Fields: `title`, `path`/`slug` (goldmansachs.com page), `cmsPageProps.programType[].id` (`gscom:program-type/internship|full-time|undergrad-mba|apprenticeship`), `cmsPageProps.programLocation[].{id,title}`, `cmsPageProps.eligibilityDetails` (text), `lastModified`, `created`, `lastModifiedDate`.
  - It has **no deadlines, no application links and no requisition ids**, so it's useful at most as a weekly "program page changed" signal, not as a job feed.

## robots.txt
higher.gs.com robots.txt: `User-agent: * / Allow: /roles/` + `User-agent: * / Disallow: /`. api-higher.gs.com/robots.txt and hdpc.fa.us2.oraclecloud.com/robots.txt both return 404, which means no restrictions under RFC 9309.

| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://api-higher.gs.com/gateway/api/v1/graphql` | ALLOW | no robots.txt (404) |
| `https://higher.gs.com/roles/170705` (detail links) | ALLOW | `Allow: /roles/` |
| `https://higher.gs.com/`, `/results`, `/campus` | BLOCK | `Disallow: /` (don't fetch; only humans click these) |
| `https://www.goldmansachs.com/feeds/programs-and-internships.json` | ALLOW | no matching rule |
| `https://www.goldmansachs.com/careers/students/programs-and-internships` | ALLOW | no matching rule |
| `https://hdpc.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?...siteNumber=CX_3002...` | ALLOW | no robots.txt (404) |

Caveat for the reviewer: the data host has no robots.txt, so the recommended API is allowed. But the human-facing search pages on higher.gs.com are closed to crawlers. The checker must stay on api-higher.gs.com and `/roles/` links, and must never fetch `/results`, `/campus` or `/_next/` chunks directly.

## Anti-bot / quirks
- CloudFront sits in front of the API (`server: CloudFront`, `cache-control: no-store`). I saw no challenge, CAPTCHA, cookies or token requirement, and no 429 across 14 API calls at about 1 request per second.
- Errors come back as HTTP 200 with `{"errors":[...], "data": null}` (e.g. pageSize > 250). The checker should treat a non-empty `errors` array as a shape/fetch failure.
- Sort by `POSTED_DATE DESC`. With it, 4 pages gave 891 unique ids with no duplicates or gaps. I didn't test `RELEVANCE` paging.
- 8 roles with suffix `_GS_NOTICE_OF_FILING_LCA` are LCA notice postings (e.g. "Internal Audit - Dallas - Associate, Technology Audit - 10066859"). They're harmless; filters will drop them.
- The UI's facet hierarchy is country → state → city. The API exposes `corporateRegion` directly on locations, which is easier for "Americas" filtering.

## Recommended checker
```yaml
- key: goldman-sachs
  name: Goldman Sachs
  adapter: custom:gs_higher          # GraphQL POST; no shared ATS adapter applies
  careers_url: https://higher.gs.com/campus
  settings:
    endpoint: https://api-higher.gs.com/gateway/api/v1/graphql
    experiences: [PROFESSIONAL, EARLY_CAREER, CAMPUS]   # CAMPUS alone (219) is enough for internships
    page_size: 250                   # server max
    sort: {sortStrategy: POSTED_DATE, sortOrder: DESC}
    id: externalSource.sourceId
    url_template: https://higher.gs.com/roles/{sourceId}
    posted: lastPostedDate
    snippet: shortDescription        # detail query role(externalSourceId) for descriptionHtml when needed
    employment_type_from: corporateTitle   # Summer Analyst/Summer Associate/Seasonal => student role
  expect_min_total: 600              # health: alert if roleSearch.totalCount drops sharply
```

## Evidence
- Sample: `discovery/samples/goldman-sachs.json`. It has the recommended request body; the page-0 envelope (totalCount 891, pageSize 250) with 3 professional and 4 Americas campus items; the GetRoleById request and response for 170705 (apply URL, descriptionHtml); and the first 3 of 25 programs-feed entries.
- Capture of the allowed role page `https://higher.gs.com/roles/170705` (Playwright) showed the site calling `POST https://api-higher.gs.com/gateway/api/v1/graphql` with `GetRoleById`. It also called Contentful GraphQL for page chrome only.
- Original bookmark capture: `discovery/captures/goldman-sachs/` (programs feed only).
- Request budget: 22 requests in all (api-higher 14, Oracle 4, higher.gs.com 2 = one Playwright page + robots, goldmansachs.com 2).
