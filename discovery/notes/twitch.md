# Twitch (`twitch`)

**Status:** verified-feed   ·   **Checked:** 2026-10-19

| | |
|---|---|
| Official careers URL | https://careers.twitch.com/en/careers ("Open Roles" in the site nav). The bookmark https://careers.twitch.com/en/early-career is an info page with no listings; its only amazon.jobs link is a "STAR method" interview tip. `/en/jobs` is a 404. |
| Hiring system | **Greenhouse** board `twitch`. The Open Roles page embeds the Greenhouse job-board iframe (`boards.greenhouse.io/embed/job_board/js?for=twitch` → frame `job-boards.greenhouse.io/embed/job_board?for=twitch&validityToken=…`). Twitch is an Amazon subsidiary, and the same requisitions are **also on amazon.jobs** (see below). |
| Recommended adapter | shared `greenhouse` adapter, `board: twitch` |

## Recommended feed
- `GET https://boards-api.greenhouse.io/v1/boards/twitch/jobs` returns 54 jobs, `meta.total` 54, no pagination.
- `absolute_url` = `https://job-boards.greenhouse.io/twitch/jobs/<id>`.
- Twitch posts **one Greenhouse job per location**. For example, Tax Manager appears 5 times (NYC, SF, Irvine, Seattle, LA), and Customer Success Manager 4 times. So 54 postings are 22 distinct titles. Expect several alerts per role if an internship is posted for several cities.
- Do **not** use `boards.greenhouse.io/embed/...`: robots.txt has `Disallow: /embed/` on boards.greenhouse.io. The page uses it, but the checker does not need it.

## Twitch on amazon.jobs
- `GET https://www.amazon.jobs/en/search.json?base_query=twitch&result_limit=100&offset=0|100` (allowed by robots) returned 163 hits. Of those, **30** have `company_name` "Twitch Interactive, Inc. - D48" (27), "Twitch Interactive, Inc.", "Twitch Australia Pty Ltd - J16" or "Twitch Interactive Spain, S.L.U. - J89". The other 133 are mostly Amazon Ads roles that mention Twitch.
- amazon.jobs carries one record per role, with all locations in `locations[]`. Its titles match the Greenhouse roles: Tax Manager, Senior UX Designer, Software Engineer I / I Payments / I Memberships, Senior Manager Business Development, and others.
- A few amazon.jobs Twitch records have no Greenhouse twin. They are internal-style titles ("Software Dev Engineer III - AMZ10430678", "Applied Scientist III - AMZ27946.1") plus "Executive Business Partner", "Software Development Manager, Commerce (SDM)", "Software Engineer, Data Platform" and an older "Software Engineer I" (Seattle, Dec 2025).
- **Conclusion:** the official Twitch careers site uses Greenhouse, so track `twitch`. If the Amazon checker scans all of amazon.jobs, it will see the Twitch requisitions too. A cross-check filter there is `company_name` starting "Twitch".

## Totals (observed 2026-10-19)
- **Feed, no filters:** **54**.
- **Live careers page, no filters:** **54**. A Playwright render of /en/careers, reading the embedded frame's text, showed "54 jobs", with 50 job links on page 1.
- **Intern/student:** **0**. The early-career page says: "Applications for Summer 2027 are opening soon. Check back in October 2026 for Summer 2027 internship offerings… limited to applicants at North American-based colleges/universities."

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/twitch/jobs | ALLOW | no matching rule |
| https://careers.twitch.com/en/careers | ALLOW | no robots.txt |
| https://job-boards.greenhouse.io/embed/job_board?for=twitch | ALLOW | no matching rule |
| https://boards.greenhouse.io/embed/job_board/js?for=twitch | **BLOCK** | `Disallow: /embed/` (the browser loads it; the checker must not) |
| https://www.amazon.jobs/en/search.json?base_query=twitch… | ALLOW | no matching rule |

## Recommended checker
```yaml
- key: twitch
  name: Twitch
  adapter: greenhouse
  settings:
    board: twitch
  careers_url: https://careers.twitch.com/en/careers
```

## Evidence
- Sample: `discovery/samples/twitch.json` is the raw Greenhouse `twitch` list (54 jobs, 34 KB).
- I made Playwright renders of /en/early-career, /en/careers (main page and embed frame) and /en/jobs (404). I made 3 amazon.jobs search calls and one Greenhouse list call.
