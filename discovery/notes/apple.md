# Apple (`apple`)

**Status:** needs-custom (no shared adapter fits)   ·   **Checked:** 2026-10-19 23:47 – 2026-10-20 03:23 UTC (two sessions)

| | |
|---|---|
| Official careers URL | https://jobs.apple.com/en-us/search (all jobs). Note that the bare URL **301-redirects to `?location=united-states-USA`**, a geo default; the page's "Clear all" button gives the real unfiltered view. The bookmark is a filtered view: https://jobs.apple.com/en-us/search?location=united-states-USA&team=internships-STDNT-INTRN |
| Hiring system | Apple's own job site (React SSR app, server `Apple`). It has a JSON API under `https://jobs.apple.com/api/v1/` and no third-party ATS. |
| Recommended adapter | `custom:apple`. Each poll reads the **student slice** (the Students team plus four exact-keyword queries). A weekly full-site sweep is optional. |

## Recommended feed
- **Request:** `POST https://jobs.apple.com/api/v1/search`
- **Headers:** `Content-Type: application/json`, `Accept: */*`, `Origin: https://jobs.apple.com`, `Referer: https://jobs.apple.com/en-us/search`, a normal browser UA. The page also sends `locale: en_US` and `browserLocale: en-us`; I sent them too.
- **CSRF:** not needed. The page first calls `GET /api/v1/CSRFToken`, but every search without the token returned 200 with data, more than 50 calls across both sessions.
- **Body:**
  ```json
  {"query":"","filters":{},"page":1,"locale":"en-us","sort":"newest",
   "format":{"longDate":"MMMM D, YYYY","mediumDate":"MMM D, YYYY"}}
  ```
  - `filters` keys (from the bundle): `teams`, `locations`, `products`, `languages`, `keywords`, `homeOffice`, `hiringManagers`, `jobLevels`, `retailRoles`, `minimumHours`, `maximumHours`.
  - Students team: `"teams":[{"team":"teamsAndSubTeams-STDNT"}]`. A sub-team adds `"subTeam":"subTeam-INTRN"`. The team-only filter returns exactly the union of its 7 sub-teams (217 both ways).
  - `sort` is one of `newest` (the UI default), `relevance`, `teamAsc`, `teamDesc`, `locationAsc`, `locationDesc`. The page itself sends `""`, which behaves like `newest`.
- **Student slice queries.** Union them by `id`:
  1. `filters.teams=[{"team":"teamsAndSubTeams-STDNT"}]`. 217 rows, 11 pages.
  2. `query:"\"intern\""`, with the double quotes inside the string. That makes it **exact-token**: 116 rows, all with "intern" in the title, 6 pages.
  3. `query:"\"internship\""`. 153 rows, 8 pages. It also matches descriptions.
  4. `query:"\"student\""`. 42 rows, 3 pages.
  5. Optional: `query:"\"co-op\""`. 15 rows, 1 page, and no student titles outside 1–4 today.
  
  The union is **306 rows (251 positions)**, about 29 requests and about 1 MB. Today queries 2–4 add **38 student-titled rows that are not in the Students team**. None of them are in the US (see Totals).
- **Do not use the unquoted keyword.** `query:"intern"` is a prefix match: it returns 2,124 rows ("International…", "internal…"). With `sort: relevance`, real intern titles and "International …" rows are already mixed by page 2, so you cannot stop early.
- **Pagination:** `page` is 1-based with a **fixed 20 rows per page**. `pageSize`/`size`/`limit`/`rows`/`perPage` are ignored (prior test). Every page carries `res.totalRecords`. A page past the end returns an empty `searchResults` (page 307 of 6,108 did). There is no deep-paging cap: page 306 worked. Stop when you have `totalRecords` rows or a page is empty.
- **Full site (weekly audit, optional):** the same POST with `filters:{}` takes `ceil(6118/20)` = **306 requests**, about 30 KB each (about 9 MB), and about 6 minutes at 1.2 s spacing. This is the only way to catch a student role whose title uses none of the slice words. Today none were seen: the exact-token queries `"apprentice"`, `"werkstudent"` and `"praktikum"` return 0 rows, and `"placement"` has no student titles.
- **Detail (optional):** `GET https://jobs.apple.com/api/v1/jobDetails/{positionId}?locale=en-us` (200 JSON, about 18 KB). It has the full description plus `employmentType` (`"Intern"`), `teamNames` (e.g. `["Corporate Functions","Students"]`), `highJobTitle`, `postingDateMeta`, `jobType` and `pipelineType`.

## Field map
Paths are relative to `res.searchResults[]`.

| Job field | Path | Notes |
|---|---|---|
| id | `id` | **One row per posting × location**: `200686080-3715` (requisition plus location code) or `PIPE-114438210` (retail pipeline). It is unique per row. `positionId` (`200686080`) groups multi-location rows: the 306-row slice has 251 positions. The page counts rows. |
| title | `postingTitle` | `transformedPostingTitle` is the URL slug |
| location(s) | `locations[]`: `name` (city), `stateProvince`, `countryName`, `metro`, `region`, `postLocationId` | Each row has one location; `isMultiLocation` marks positions that have several rows. Country filter ids are irregular (`postLocation-USA`, but `postLocation-CANC`, `-CHNC`, `-INDC`), which matters only for server-side location filters, and we don't need them. |
| url (detail) | built: `https://jobs.apple.com/en-us/details/{h}/{transformedPostingTitle}?team={team.teamCode}`, where `h = positionId` if `id` contains `REQ` or `PIPE`, else `h = id` | This is the bundle's own rule. Verified 200: `/en-us/details/200686080-3715/manufacturing-design-program-manager-intern?team=STDNT` |
| url (apply) | `https://jobs.apple.com/app/en-us/apply/{positionId}` (needs login) | link only |
| posted date | `postDateInGMT` (ISO, e.g. `2026-10-19T20:46:40.638Z`) | `postingDate` is `"Oct 19, 2026"`. Retail pipeline rows are often re-dated in bulk, with identical timestamps across a page. |
| description | `jobSummary` (plain text, a few hundred characters) | full text via jobDetails |
| employment type | none in the list | `team.teamCode`/`teamName` (`STDNT`/`Students`), `standardWeeklyHours` (40, 20, …), `type` (`REQ`/`PIPE`), `managedPipelineRole`, `homeOffice`. The detail has `employmentType`. |
| department / team | `team.teamName` / `team.teamCode` | A row shows **one** team. A posting can belong to several teams (the detail's `teamNames`); the team filter matches any of them. |

## Totals (observed 2026-10-20 03:20–03:23 UTC)
- **Whole site, feed with no filters:** `totalRecords` **6,118** rows. It was 6,108 at 23:48 UTC. The US alone has 4,357.
- **Live page with no filters:** a Playwright render of `/en-us/search` followed by "Clear all" showed "**600+ Result(s)**". The bundle caps the displayed count at 600 (`be=600`). **The page's own XHR**, `POST /api/v1/search` with `{"query":"","filters":{},"page":1,…}`, returned `totalRecords: 6118`, which is the same number as the feed. Exact counts show below 600: the render of `/en-us/search?team=internships-STDNT-INTRN` (no location) showed "**113 Result(s)**", and the API gives 113. The bookmark page (US + Internships) showed "25 Result" in the capture, and the API gives 25.
- **Students team:** 217 rows (179 positions), 67 of them in the US. Its 7 sub-teams are Internships (113), Corporate, Apple Store, Apple Store Leader Program, Apple Retail Partner Store, Apple Support College Program and Apple Campus Leader. It also holds retail roles opened to students ("US-Lead", "US-Technical Expert", 20 h/week) and "UR Events Attendees" placeholders.
- **intern_total = 157 rows (130 positions):** 113 Students: Internships rows (type), plus 44 more rows titled intern/internship/student (6 inside the Students team, 38 outside it). **US: 25 rows (24 positions), all in Students: Internships.**
  - The 38 rows outside the Students team are in China 18, Singapore 5, Germany 3, India 2, Switzerland 2, UK 2, Taiwan 2, Vietnam, Australia, France and Israel 1 each.
  - Examples: "Software Engineering Intern, Apple Services Engineering" (UK, SFTWR), "PhD Intern, Apple Ads (Machine Learning)" (India), "Internship Computer Vision & Machine Learning Research" (DE/CH), "2027 Apple Internship - Information Systems and Technology" (China), "Hardware Technology Intern, Singapore".
  - **The Students team is therefore complete for the US but not worldwide.**
  - Seven Internships-sub-team rows have no student word in the title ("Formal Verification Engineer", "UR Events Attendees-FY27"), so pass `team.teamCode`/sub-team to the role filter as the employment type.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://jobs.apple.com/api/v1/search` | ALLOW | no robots.txt (404, so allow-all) |
| `https://jobs.apple.com/api/v1/jobDetails/200673612?locale=en-us` | ALLOW | no robots.txt |
| `https://jobs.apple.com/en-us/search`, `?team=internships-STDNT-INTRN` | ALLOW | no robots.txt |
| `https://jobs.apple.com/en-us/details/200686080-3715/manufacturing-design-program-manager-intern?team=STDNT` | ALLOW | no robots.txt |
| `https://jobs.apple.com/app/en-us/apply/200686080` | ALLOW | no robots.txt. It needs sign-in, so link to it only. |

## Anti-bot / quirks
- I saw no challenge in either session: about 80 API calls, at 1.15 s or more per host. The responses set an `AWSALBAPP-*` load-balancer cookie and a `jobs` cookie, and plain httpx needs neither.
- `/en-us/search` without a location parameter redirects to the visitor's country by IP. A checker must never rely on page HTML for the whole-site view; the API with empty filters is not geo-defaulted.
- The SSR HTML embeds the first 20 rows and `totalRecords` in `window.__staticRouterHydrationData.loaderData.search`. That works as a no-XHR cross-check, but it is geo-defaulted.
- The displayed count is "600+" for anything above 600. Health checks must use `totalRecords`.

## Recommended checker
```yaml
- key: apple
  name: Apple
  adapter: custom:apple
  careers_url: https://jobs.apple.com/en-us/search
  settings:
    endpoint: https://jobs.apple.com/api/v1/search      # POST, body above, 20 rows/page, page=1..N
    queries:                                             # union by id; group by positionId for alerts
      - {filters: {teams: [{team: teamsAndSubTeams-STDNT}]}}
      - {query: '"intern"'}
      - {query: '"internship"'}
      - {query: '"student"'}
      - {query: '"co-op"'}                               # optional safety net
    sort: newest
    job_url: https://jobs.apple.com/en-us/details/{h}/{transformedPostingTitle}?team={teamCode}   # h rule above
    employment_type_from: team.teamName                  # "Students" -> student hint
    full_sweep: weekly, filters {} (306 pages)           # optional audit
  health:
    per_query: rows == totalRecords, unique ids == rows
    slice_size_range: [100, 1500]
```

## Evidence
- Sample: `discovery/samples/apple.json` (from session 1). It is the raw `POST /api/v1/search` response for the bookmark's filter (US + Students: Internships): `totalRecords` 25, 20 rows, 39 KB.
- Session 1 (23:47–23:54 UTC): 30 requests. It covered the bundle and endpoint map, the CSRF test, the page-size probe, pages 306/307, the team ref data, the Internships sub-team enumeration, one detail page, jobDetails and one Playwright load.
- Session 2 (03:20–03:23 UTC): 47 API requests plus 1 robots.txt fetch and 2 Playwright loads. It covered fresh totals, the relevance test, the quoted-keyword tests, and full enumeration of the Students team (11 pages), `"intern"` (6), `"internship"` (8), `"student"` (3) and `"placement"` (4).
