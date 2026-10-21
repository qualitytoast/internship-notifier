# Instabase (`instabase`)

**Status:** verified (0 = 0): **the job board is switched off** and the careers page shows "No jobs available."   ·   **Checked:** 2026-10-19 (US Central); re-checked 2026-10-20 00:28 UTC

| | |
|---|---|
| Official careers URL | https://www.instabase.com/careers/jobs (Webflow). It is linked from https://www.instabase.com/careers. |
| Hiring system | **Greenhouse**, board token `instabase`. The page's own inline script defines `API_BASE_URL = 'https://boards-api.greenhouse.io/v1/boards/instabase'` and fetches `${API_BASE_URL}/jobs?content=true` to build the list and its department/location filters. Apply links have the form `https://job-boards.greenhouse.io/instabase/jobs/{id}`. |
| Recommended adapter | shared `greenhouse` `{board: instabase}`. It is correct but currently returns 404; see "Anti-bot / quirks" for how to treat that. |

## Recommended feed
- **Request:** `GET https://boards-api.greenhouse.io/v1/boards/instabase/jobs?content=true`
- **Current response:** **HTTP 404** `{"status":404,"error":"Job not found"}`. That was the result at 2026-10-19 23:51 UTC and again at 2026-10-20 00:28 UTC. The board root `/v1/boards/instabase` returns 404 "Job board not found". A job that search engines still index (8391125002, from July 2026) returns 404 as well.
- **The hosted board says the same:** `https://job-boards.greenhouse.io/instabase` returns 404 "The job board you were viewing is no longer active". Job URLs 302 to `?error=true`.
- If the board is turned back on, the standard Greenhouse field map applies (see notes/walleye.md), and `content=true` is what the page itself requests.

## Field map
This is the standard Greenhouse boards API, used by the page with `content=true`.

| Job field | Response path | Notes |
|---|---|---|
| id | `jobs[].id` | |
| title | `jobs[].title` | |
| location(s) | `jobs[].location.name` | the page's location filter uses this |
| url (detail/apply) | `jobs[].absolute_url` | `https://job-boards.greenhouse.io/instabase/jobs/{id}` |
| posted date | `jobs[].first_published` / `updated_at` | |
| description / snippet | `jobs[].content` (HTML-escaped) | |
| employment type | none | use the title |
| department / team | `jobs[].departments[].name` | the page's department filter |

## Totals (observed 2026-10-19 23:51 – 2026-10-20 00:28 UTC)
- **Feed, no filters:** **0**. The board API returns 404.
- **Live careers page, no filters:** **0**. The Playwright capture of `/careers/jobs` renders "Open positions · All departments · All locations · **No jobs available.**" The static HTML still contains Webflow template cards, e.g. "Product Marketing Manager, Competitive Intelligence (AI)" with "Lorem ipsum" text. Their Apply links (`…/jobs/8042464002`, `…/jobs/8073772002`) lead to the inactive board, and the script replaces them with the empty API result.
- **Intern/student:** **0**.

### Where else I looked (nothing found)
- Ashby: the API `instabase` returns 404, and `jobs.ashbyhq.com/instabase` is a generic shell with no organization.
- Lever `instabase`: 404. Greenhouse `instabaseinc`: 404.
- Rippling `ats.rippling.com/instabase/jobs`: 404. Workable `instabase`: 404.
- The Webflow sitemap (171 URLs) has only `/careers`, `/careers/jobs` and `/careers/jobs/recruitment-fraud-alert`; there are no job pages.
- Two web searches found only aggregator copies, the newest dated 2026-07-28, and old Greenhouse job URLs. No other ATS turned up.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/instabase/jobs?content=true | ALLOW | no matching rule |
| https://www.instabase.com/careers/jobs | ALLOW | no matching rule (robots.txt is empty) |
| https://job-boards.greenhouse.io/instabase | ALLOW | no matching rule |

## Anti-bot / quirks
- No anti-bot on either host.
- **Treat 404 as "board inactive", not as a failing checker.** If the shared Greenhouse adapter turns HTTP 404 into a hard failure, Instabase will raise a health email every 24 h. Recommended: map a 404 from `boards-api` with `"Job not found"` / `"Job board not found"` to 0 jobs plus a single "board inactive" health note. Keep polling at the normal interval (one tiny request) so a reactivated board is caught at once.
- If Instabase moves to a new token or ATS, the page script's `API_BASE_URL` will change. Re-capture `/careers/jobs` monthly, or alert when the page stops referencing `boards/instabase`.

## Recommended checker
```yaml
- key: instabase
  name: Instabase
  adapter: greenhouse
  careers_url: https://www.instabase.com/careers/jobs
  settings:
    board: instabase
    content: true
    inactive_ok: true      # 404 "Job not found" → 0 jobs + one "board inactive" note (board switched off since ≤ 2026-10-19)
  # fallback: SimplifyJobs cross-check
```

## Evidence
- Sample: `discovery/samples/instabase.html`, the raw `/careers/jobs` HTML (68 KB). It contains the inline script with the Greenhouse API URL and the "Lorem ipsum" template cards.
- Capture: `discovery/captures/instabase/` (rendered: "No jobs available.").
- Requests: the previous run made 18 (Greenhouse API ×3, the hosted board ×2, the Webflow page, careers, sitemap, and the Ashby/Lever/Rippling/Workable probes with their robots files). This run made 3 (robots and the Greenhouse API ×2), plus 2 web searches.
