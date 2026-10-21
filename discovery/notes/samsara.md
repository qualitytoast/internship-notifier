# Samsara (`samsara`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://www.samsara.com/company/careers/roles (the bookmark adds `?type=Intern`) |
| Hiring system | Greenhouse, **two boards merged on the page**: `samsara` and `samsaradach` (DACH region). The page is Nuxt, rendered on the server. Every job links to `/company/careers/roles/<id>?gh_jid=<id>&gh_board=<board>`. |
| Recommended adapter | shared `greenhouse` adapter, `boards: [samsara, samsaradach]` |

The probe found only `samsara`. The second board shows up only in the `gh_board` parameter of the job links: 266 links had `gh_board=samsara` and 1 had `gh_board=samsaradach` on 2026-10-20. The page source holds no board list, so a future regional board would appear only as a new `gh_board` value.

## Recommended feed
- **Request 1:** `GET https://boards-api.greenhouse.io/v1/boards/samsara/jobs`
- **Request 2:** `GET https://boards-api.greenhouse.io/v1/boards/samsaradach/jobs`
- **Headers and pagination:** a normal UA, no pagination. `meta.total` equals the number of jobs on each board.

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `jobs[].id` | |
| title | `jobs[].title` | Some titles have trailing spaces (e.g. "Software Engineering Internship - San Francisco "), so trim. |
| location(s) | `jobs[].location.name` | e.g. "San Francisco - SF9", "Atlanta, Georgia, United States", "Munich, Germany" |
| url | `jobs[].absolute_url` | samsara: `https://www.samsara.com/company/careers/roles/<id>?gh_jid=<id>`. samsaradach: `https://job-boards.greenhouse.io/samsaradach/jobs/<id>` (the site links it as `/company/careers/roles/<id>?gh_jid=<id>&gh_board=samsaradach`). |
| posted date | `jobs[].first_published` | |
| employment type | metadata "Employment Type" | "Full-Time" on 52 jobs and null on the rest, including all interns. Match on the title. |
| department / team | metadata "Job Family Group" | `departments[]` in the detail call |

## Totals (observed 2026-10-20)
- **Feed, no filters:** 266 + 1 = **267** at 00:19Z, when I rendered the page. At the final fetch (00:40Z) it was 265 + 1 = **266**.
- **Live careers page, no filters:** **267**. A Playwright render showed "267 roles" and 267 job links: 266 with `gh_board=samsara` and 1 with `gh_board=samsaradach`.
- **Intern/student:** **5**, all on `samsara`:
  - 8103119 Account Development Representative Intern - Atlanta
  - 8099799 Account Development Representative Intern - Phoenix
  - 8163118 Electrical Engineering Co-Op (San Francisco - SF9)
  - 8226602 Firmware Engineer Co-Op (San Francisco - SF9)
  - 8082091 Software Engineering Internship - San Francisco
- The `samsaradach` board has one job: 8260180 "Account Development Representative - DACH", Munich, first published 2026-10-07.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/samsara/jobs | ALLOW | no matching rule |
| https://boards-api.greenhouse.io/v1/boards/samsaradach/jobs | ALLOW | no matching rule |
| https://www.samsara.com/company/careers/roles | ALLOW | no matching rule |

## Anti-bot / quirks
- None seen. The page makes no Greenhouse call from the browser; the list comes in the server-rendered HTML.

## Recommended checker
```yaml
- key: samsara
  name: Samsara
  adapter: greenhouse
  settings:
    boards: [samsara, samsaradach]
  careers_url: https://www.samsara.com/company/careers/roles
```

## Evidence
- Sample: `discovery/samples/samsara.json` is the raw `samsaradach` board response (1 job, 0.8 KB).
- Capture: `discovery/captures/samsara/` (the bookmark with the Intern filter).
