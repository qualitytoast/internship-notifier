# Sierra (`sierra`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://sierra.ai/careers. The job list is the "Open roles" section. https://sierra.ai/early-career-program only links back to `https://sierra.ai/careers?department=early-career`, a filtered view of the same list. |
| Hiring system | Ashby, **two boards**, both listed on the careers page with no filter: **`Sierra`** (main board, 187 jobs, links `jobs.ashbyhq.com/Sierra/<id>`) and **`sierra-jp`** (Japan board, 10 Tokyo jobs with Japanese titles, links `jobs.ashbyhq.com/sierra-jp/<id>`). The page is server-rendered (Next.js), so the browser makes no Ashby API call. |
| Recommended adapter | shared `ashby` adapter, run once per board. The adapter only takes `board` today, so it needs `boards: [...]` support (as `greenhouse` has), or the config needs two entries. |

The probe found only `sierra` (187). The lower-case `sierra` and the page's `Sierra` return the same 187 ids, so the posting API is case-insensitive here. Use `Sierra` to match the page and every `jobUrl`. The GH tokens `sierra` and `sierraai` return 0.

## Recommended feed
- **Request 1 (main):** `GET https://api.ashbyhq.com/posting-api/job-board/Sierra?includeCompensation=false`
- **Request 2 (Japan):** `GET https://api.ashbyhq.com/posting-api/job-board/sierra-jp?includeCompensation=false`
- **Headers:** a normal browser UA. No auth needed.
- **Pagination:** none. Each response is `{"apiVersion": "1", "jobs": [...]}` with every posting, including descriptions. The main board response is 3.3 MB and sierra-jp is 234 KB. Every posting has `isListed: true`, so none are unlisted.
- Do **not** use `jobs.ashbyhq.com/api/non-user-graphql`. robots.txt disallows `/api/` there.

## Field map
Paths are relative to `jobs[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | `id` (UUID) | unique across both boards (no overlap) |
| title | `title` | sierra-jp titles are Japanese, sometimes with an English gloss, e.g. `パートナーセールス (Partnerships Sales)` |
| location(s) | `location` + `secondaryLocations[].location` | e.g. `San Francisco, CA` + `New York, NY`. Country: `address.postalAddress.addressCountry`. `isRemote`, `workplaceType` (OnSite 160 / Remote 26 / Hybrid 1 on the main board) |
| url (detail) | `jobUrl` | `https://jobs.ashbyhq.com/Sierra/<id>` or `https://jobs.ashbyhq.com/sierra-jp/<id>` |
| url (apply) | `applyUrl` | `<jobUrl>/application` |
| posted date | `publishedAt` (ISO with offset) | the oldest is from 2024-01 (evergreen roles) |
| description | `descriptionPlain` / `descriptionHtml` | full text inline, so no detail call is needed |
| employment type | `employmentType` | main board: FullTime 182, Contract 3, Intern 2. sierra-jp: FullTime 10 |
| department / team | `department` / `team` | interns are in `Early Career` / `Intern` |

## Totals (observed 2026-10-20 ~00:15 UTC)
- **Feed, no filters:** `Sierra` **187** + `sierra-jp` **10** = **197**, deduped (no shared ids).
- **Live careers page, no filters:** **197**. A Playwright render of https://sierra.ai/careers listed 197 unique job links: 187 to `jobs.ashbyhq.com/Sierra/<id>` and 10 to `jobs.ashbyhq.com/sierra-jp/<id>`. They match the two feeds id for id. The page shows no count text, so I counted the links.
- **Intern/student:** **2**, both "Software Engineer Intern, Agent (Summer 2027)": one in San Francisco, CA (secondary location New York, NY) and one in Singapore. The early-career page says internships are year-round, for students graduating in 2028.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://api.ashbyhq.com/posting-api/job-board/Sierra?includeCompensation=false | ALLOW | robots.txt answers HTTP 401, which counts as no robots.txt |
| https://api.ashbyhq.com/posting-api/job-board/sierra-jp?includeCompensation=false | ALLOW | same |
| https://sierra.ai/careers | ALLOW | no matching rule |
| https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams | **BLOCK** | `Disallow: /api/`. Never fetch it. |

## Anti-bot / quirks
- No bot challenge on sierra.ai or the Ashby API.
- A checker that watches only `Sierra` misses the 10 Japan roles, and any future Japan internships with them. Keep both boards. A 404 or zero-after-nonzero on `sierra-jp` should raise an alert, because it can mean the board was renamed or merged.

## Recommended checker
```yaml
- key: sierra
  name: Sierra
  adapter: ashby
  settings:
    boards: [Sierra, sierra-jp]     # needs boards-list support in adapters/ashby.py; otherwise two entries with board: Sierra / board: sierra-jp
  careers_url: https://sierra.ai/careers
```

## Evidence
- Sample: `discovery/samples/sierra.json` is the raw `sierra-jp` posting-API response (10 jobs, 234 KB). The main board response is 3.3 MB, too large for a sample.
- Capture: `discovery/captures/sierra/` (careers page; it shows only `jobs.ashbyhq.com/Sierra/...` links among the first signatures).
- I rendered https://sierra.ai/careers and https://sierra.ai/early-career-program with Playwright, and called the posting API for `sierra`, `Sierra` and `sierra-jp`.
