# Whatnot (`whatnot`)

**Status:** needs-custom (Ashby, but the public posting API is off for this org; read the hosted board page)   ·   **Checked:** 2026-10-19 (US Central); board re-checked 2026-10-20 00:27 UTC

| | |
|---|---|
| Official careers URL | https://www.whatnot.com/careers/discover is the job list ("See additional opportunities" on /careers). `/careers` itself lists no jobs. Each job is at `https://www.whatnot.com/careers/roles/{ashbyPostingId}`. |
| Hiring system | **Ashby**, org "Whatnot" (`organizationId 9a8c595d-…`, `hostedJobsPageSlug: "whatnot"`, `customJobsPageUrl: null`). Apply links on whatnot.com go to `https://jobs.ashbyhq.com/whatnot/{id}`. |
| Recommended adapter | `custom:ashby-hosted`. Alternatively, extend the shared `ashby` adapter with a hosted-page mode. `GET https://api.ashbyhq.com/posting-api/job-board/whatnot` returns **404 "Not Found"**; `Whatnot` and `?includeCompensation=true` were also tried. A control org (`openai`) returned 200 at the same time, so the shared adapter cannot read this board as it is. |

## Recommended feed
- **Request:** `GET https://jobs.ashbyhq.com/whatnot` with a browser UA and `Accept: text/html`. The response is about 103 KB of HTML, with no cookies.
- **Parse:** find `window.__appData = ` and run `json.JSONDecoder().raw_decode(html, idx)`. Read:
  - `appData.jobBoard.jobPostings[]`: **149** postings, all of them in one response.
  - `appData.jobBoard.teams[]`: 48 teams, `{id, name, externalName, parentTeamId}`.
  - `appData.organization`: name, slug, theme.
- **Pagination:** none.
- **Never use** anything under `https://jobs.ashbyhq.com/api/` (Ashby's front-end API, e.g. `/api/non-user-graphql`). It is robots-blocked (`Disallow: /api/`).
- **Detail (optional):** `GET https://jobs.ashbyhq.com/whatnot/{id}` (about 56 KB). `window.__appData.posting` has `descriptionHtml`, `departmentName`, `locationName`, `workplaceType`, `employmentType` and compensation. The page also has JSON-LD `JobPosting` with `datePosted`, `jobLocation` and `baseSalary`.

## Field map
Paths are relative to `jobBoard.jobPostings[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | `id` (UUID) | the same id is used on whatnot.com (`/careers/roles/{id}`) |
| title | `title` | |
| location(s) | `locationName` + `secondaryLocations[].locationName` | e.g. "San Francisco, CA" + "New York, NY", "Los Angeles, CA". `workplaceType`: Remote 57, Hybrid 42, null 50. |
| url (detail/apply) | built: `https://jobs.ashbyhq.com/whatnot/{id}` (or `https://www.whatnot.com/careers/roles/{id}` for display) | |
| posted date | not in the list | detail JSON-LD `datePosted` |
| description / snippet | not in the list | detail `posting.descriptionHtml` |
| employment type | `employmentType` (`FullTime` for all 149, **including the intern**) | use the title |
| department / team | `teamId` → `jobBoard.teams[].name` | |
| other | `compensationTierSummary` (often null) | |

## Totals
- **Feed, no filters:** **149** postings with unique ids. That was the count at 2026-10-19 23:48 UTC, and again at 2026-10-20 00:27 UTC with the same 149 ids (0 added, 0 removed).
- **Live careers page, no filters:** **149**. A Playwright render of https://www.whatnot.com/careers/discover in the previous run (2026-10-19 23:48 UTC) showed "**Showing 149 matching jobs**" with 149 unique `/careers/roles/{id}` links. Those were exactly the 149 Ashby ids: none only on whatnot.com, none only on Ashby. The jobs are in the page's RSC payload, in the same Ashby shape with `applyLink` → jobs.ashbyhq.com.
- **Intern/student:** **1**: `Software Engineer Intern (Summer 2027)`, San Francisco, CA. There are also 4 new-grad roles: "Software Engineer, 2027 New Grad", "Category Associate - New Grad Business Program", and two "2025-27 New Grad" agent roles.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://jobs.ashbyhq.com/whatnot | ALLOW | no matching rule (disallows only `/meeting/`, `/b/`, `/api/`) |
| https://jobs.ashbyhq.com/whatnot/{id} | ALLOW | no matching rule |
| https://jobs.ashbyhq.com/api/non-user-graphql | **BLOCK** | `Disallow: /api/` |
| https://api.ashbyhq.com/posting-api/job-board/whatnot | ALLOW | no robots.txt (but 404 for this org) |
| https://www.whatnot.com/careers/discover | allowed by its robots.txt as served to a browser (`Allow: /`; disallows only account, dashboard, inbox, … paths) | plain HTTP gets a 403 challenge page even for /robots.txt |

## Anti-bot / quirks
- **www.whatnot.com is bot-protected.** Cloudflare sends plain HTTP clients a JS challenge ("Just a moment…", 403), and the page also loads Kasada (`x-kpsdk-*`) and returned 429s on some sub-requests. The checker must **not** poll whatnot.com. Ashby's hosted board is the openly reachable feed underneath, and it had no challenge (3 page requests across two runs).
- The org's `allowJobPostIndexing: true` means the hosted board is intended to be public.
- If Ashby later enables the public posting API for `whatnot`, switch to the shared `ashby` adapter (`{board: whatnot}`). The ids are the same.

## Recommended checker
```yaml
- key: whatnot
  name: Whatnot
  adapter: custom:ashby-hosted         # or: ashby {board: whatnot, source: hosted_page}
  careers_url: https://www.whatnot.com/careers/discover
  settings:
    url: https://jobs.ashbyhq.com/whatnot
    json_var: 'window.__appData = '    # raw_decode from here
    list_path: jobBoard.jobPostings
    teams_path: jobBoard.teams
    job_url: 'https://jobs.ashbyhq.com/whatnot/{id}'
  health:
    min_jobs: 20                       # alert if appData has no jobBoard (page change)
```

## Evidence
- Sample: `discovery/samples/whatnot.html`, the raw hosted board page (103 KB) with `window.__appData` and all 149 postings.
- Capture: `discovery/captures/whatnot/` (/careers, no jobs).
- Requests: the previous run made 17 (whatnot.com robots and pages via one Playwright load, Ashby board, API 404 ×3, the openai control, one detail). This run made 1 (the board).
