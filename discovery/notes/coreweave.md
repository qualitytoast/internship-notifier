# CoreWeave, incl. Weights & Biases (`coreweave`)

**Status:** verified-feed   ·   **Checked:** 2026-10-19

| | |
|---|---|
| Official careers URL | https://coreweave.com/careers (US openings). The careers sub-nav on every careers page links "Openings in the US / Europe / Canada / APAC / at Weights & Biases": https://coreweave.com/careers, https://coreweave.com/careers/eu, https://coreweave.com/careers/ca, https://coreweave.com/careers/apac, https://coreweave.com/careers/weights-biases (the bookmark). The nav hrefs use a `/archive26/careers/...` path that resolves to the same pages. |
| Hiring system | Greenhouse, **five boards**, one per page. Each page calls `boards-api.greenhouse.io/v1/boards/<board>/jobs?content=true` from the browser: `coreweave`, `coreweaveu` (Europe, not "coreweaveeu"), `coreweaveca`, `coreweaveapac`, `weights_and_biases`. |
| Recommended adapter | shared `greenhouse` adapter with `boards: [coreweave, coreweaveu, coreweaveca, coreweaveapac, weights_and_biases]` |

The probe found only `coreweave` (315) and `weights_and_biases` (7). Tracking only those two would miss 106 jobs.

## Recommended feed
- **Requests:** `GET https://boards-api.greenhouse.io/v1/boards/<board>/jobs` for each of the 5 boards. The site adds `?content=true`, which is optional.
- **Headers:** a normal browser UA. No auth.
- **Pagination:** none. `meta.total` equals the job count on every board.
- **Detail:** `GET .../boards/<board>/jobs/<id>` if a description is needed.

## Field map
This is the standard Greenhouse job-board list (see notes/walleye.md). CoreWeave specifics:

| Job field | Response path | Notes |
|---|---|---|
| id | `jobs[].id` | unique across the 5 boards |
| title | `jobs[].title` | |
| location(s) | `jobs[].location.name` | free text |
| url | `jobs[].absolute_url` | `https://coreweave.com/careers/job?<id>&board=<board>&gh_jid=<id>`. The site's own links are `/careers/job?gh_jid=<id>&board=<board>`. |
| posted date | `jobs[].first_published` | |
| company | `jobs[].company_name` | `CoreWeave`, `CoreWeave Europe`, `CoreWeave Canada`, `CoreWeave APAC`, `Weights & Biases`. This is a handy board label. |
| requisition | `jobs[].requisition_id` | Requisitions 1853 and 2160 appear on both `coreweave` and `coreweaveca` with different job ids and locations, so they are distinct postings. Keep both. |

## Totals (observed 2026-10-19)
- **Feed, no filters:** 315 + 81 + 2 + 23 + 7 = **428** postings (428 unique ids, 426 unique requisitions).
- **Live careers pages, no filters (Playwright):** `/careers` showed "315 Jobs", `/careers/eu` "81 Jobs", `/careers/ca` "2 Jobs", `/careers/apac` "23 Jobs", `/careers/weights-biases` "7 Jobs". On every page, the set of `gh_jid` values in the job links equals that board's feed ids exactly.
- **Intern/student:** **0** on all five boards (no intern, co-op, student or new-grad titles).

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/{coreweave,coreweaveu,coreweaveca,coreweaveapac,weights_and_biases}/jobs | ALLOW | no matching rule (only `/embed/` is disallowed) |
| https://coreweave.com/careers, /careers/eu, /careers/weights-biases | ALLOW | no matching rule |

## Anti-bot / quirks
- No bot protection was seen. The board list lives only in the careers sub-nav. If CoreWeave adds a region, a new board token will appear there, and the probe-by-guess approach would not find it (the Europe token is `coreweaveu`).

## Recommended checker
```yaml
- key: coreweave
  name: CoreWeave (Weights & Biases)
  adapter: greenhouse
  settings:
    boards: [coreweave, coreweaveu, coreweaveca, coreweaveapac, weights_and_biases]
  careers_url: https://coreweave.com/careers
```

## Evidence
- Sample: `discovery/samples/coreweave.json` is the raw `coreweaveapac` list (23 jobs, 21 KB).
- Capture: `discovery/captures/coreweave/` (W&B page). I made Playwright renders of all 5 careers pages and one GET per board.
