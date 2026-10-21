# SeatGeek (`seatgeek`)

**Status:** verified-feed (the front-end is bot-protected, so I verified through Greenhouse's own embed of the same board)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://seatgeek.com/jobs. Headless Chromium gets **HTTP 403 plus a DataDome CAPTCHA** (`geo.captcha-delivery.com`, "It looks like our system thinks you are a robot"). I did not try to get past it. |
| Hiring system | Greenhouse, board **`seatgeek`**. Three things show seatgeek.com/jobs renders this board. Every `absolute_url` in the feed is `https://seatgeek.com/jobs/<id>?gh_jid=<id>` (the board's configured custom URL). `https://job-boards.greenhouse.io/seatgeek` answers **302 → https://seatgeek.com/jobs**. The GH embed view of the board lists the same 37 jobs, linked to `seatgeek.com/jobs/<id>?gh_jid=<id>`. |
| Recommended adapter | shared `greenhouse` adapter, `board: seatgeek`. It never touches seatgeek.com. |

## Recommended feed
- **Request:** `GET https://boards-api.greenhouse.io/v1/boards/seatgeek/jobs` (add `?content=true` for descriptions, departments and offices)
- **Headers:** a normal browser UA. No auth needed, and no bot protection on boards-api.greenhouse.io.
- **Pagination:** none. One response holds every job, and `meta.total` gives the count (37).
- **Detail (optional):** `GET https://boards-api.greenhouse.io/v1/boards/seatgeek/jobs/<id>`

## Field map
Same as every Greenhouse board (see notes/walleye.md). Paths are relative to `jobs[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | `id` | e.g. 8247554 |
| title | `title` | interns are titled `<Role> - Internship` |
| location(s) | `location.name` | `New York, New York` (21) or `Remote - United States` (16). Many roles are posted twice, once per location, as separate ids. The page lists both. |
| url | `absolute_url` | `https://seatgeek.com/jobs/<id>?gh_jid=<id>`. The link opens the DataDome-protected site, which is fine for a human clicking from an email. |
| posted date | `first_published` | `updated_at` also present |
| description | `content` (with `?content=true`) | HTML-escaped |
| employment type | none | `metadata` is null, so use the title |
| department | `departments[].name` (with `?content=true`) | the embed groups the interns under "Internships" / "Internships - R&D" |

## Totals (observed 2026-10-20 ~00:20 UTC)
- **Feed, no filters:** **37** (`meta.total` 37, 37 unique ids).
- **Careers page, no filters:** **37**. seatgeek.com/jobs itself returns 403 to headless Chromium. A Playwright render of Greenhouse's embed view of the board, `https://job-boards.greenhouse.io/embed/job_board?for=seatgeek` (robots ALLOW), showed "Current openings at SeatGeek … **37 jobs**" and 37 links `seatgeek.com/jobs/<id>?gh_jid=<id>`, identical to the feed ids. This is the same Greenhouse board widget that seatgeek.com/jobs embeds. I could not see the company page's own chrome around it.
- **Intern/student:** **3**, all in New York, New York:
  - 8227553 Software Engineer - Internship (first published 2026-09-23)
  - 8247554 Data Analyst - Internship (2026-10-01)
  - 8248151 Security Engineer - Internship (2026-10-01)

  The board also has "UX Design - New Grad" (New York).

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/seatgeek/jobs | ALLOW | no matching rule (only `/embed/` is disallowed on boards-api) |
| https://job-boards.greenhouse.io/embed/job_board?for=seatgeek | ALLOW | job-boards.greenhouse.io robots.txt has no active rules |
| https://job-boards.greenhouse.io/seatgeek | ALLOW | no matching rule (it 302-redirects to seatgeek.com/jobs) |
| https://seatgeek.com/jobs | ALLOW on paper | `seatgeek.com/robots.txt` itself returned 403 (DataDome), which counts as allow under RFC 9309. The site is bot-protected anyway, so the checker must not fetch it. |

## Anti-bot / quirks
- **DataDome** protects seatgeek.com, including `/jobs` and `/robots.txt`. The capture (`discovery/captures/seatgeek`) also got 403. Do not render or scrape seatgeek.com. The Greenhouse API is the openly reachable feed underneath it.
- Duplicate postings per location (NY + Remote US) are separate GH ids, so dedupe by title and location only in the email if wanted. The page shows them separately too.

## Recommended checker
```yaml
- key: seatgeek
  name: SeatGeek
  adapter: greenhouse
  settings:
    board: seatgeek
  careers_url: https://seatgeek.com/jobs
```

## Evidence
- Sample: `discovery/samples/seatgeek.json` is the raw `boards-api.greenhouse.io/v1/boards/seatgeek/jobs` response (37 jobs, 22 KB).
- Playwright renders: seatgeek.com/jobs (403 + DataDome CAPTCHA iframe), job-boards.greenhouse.io/seatgeek (302 → seatgeek.com/jobs, then 403), and the embed view (200, "37 jobs"). That is one render each, plus one API call.
