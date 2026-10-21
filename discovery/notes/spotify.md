# Spotify (`spotify`)

**Status:** verified-feed (Lever is complete; the website is an edited mirror with 9 fewer entries)   ·   **Checked:** 2026-10-19 (US Central) = 2026-10-20 00:13–00:15 UTC

| | |
|---|---|
| Official careers URL | https://www.lifeatspotify.com/jobs ("All Jobs"). The bookmark adds `?j=internship`, a job-type filter, which shows 0 jobs today. Spotify's Lever hosted board, https://jobs.lever.co/spotify, is linked from every job's Apply button. |
| Hiring system | **Lever**, site `spotify` (global instance, not EU). lifeatspotify.com is a Next.js site backed by a WordPress API (`https://api.lifeatspotify.com/wp-json/animal/v1/job/search`) that mirrors Lever with some editing. |
| Recommended adapter | shared `lever`: `{site: spotify}` |

## Recommended feed
- **Request:** `GET https://api.lever.co/v0/postings/spotify?mode=json` returns a bare JSON array of **82** postings (790 KB with descriptions). There is no pagination: the API returns everything without `limit`/`skip`.
- **Headers:** a normal browser UA. No auth. The Lever robots.txt has `Crawl-delay: 1`, which matches our 1 request/second.

### Website mirror (rejected as the primary source)
- `GET https://api.lifeatspotify.com/wp-json/animal/v1/job/search` (27 KB) returns `{"result":[73 entries], "main_categories":[11], "time":…}`.
  - Each entry: `{id: "<slug>", text, main_category{name,slug}, sub_category{name,slug}, locations[{location,slug,num_jobs}], job_type{name,slug}}`.
  - The ids are WordPress slugs (e.g. `research-scientist-personalization`), not Lever UUIDs.
  - Titles are rewritten: " - " becomes ", ", and `&` is HTML-escaped as `&amp;`.
- What the mirror changes, compared with Lever (82 postings, 73 unique titles after normalising):
  1. **7 Lever postings are missing from the website entirely:**
     - Senior Manager, EU Government Affairs (Brussels, created 2026-05-14)
     - Tax Analyst (Stockholm, 08-24)
     - Communications Lead - MENAT+ (Dubai, 08-24)
     - State and Local Government Affairs Manager (New York, 08-26)
     - Manager, Artists Label & Partnerships (Paris, 09-16)
     - Backend Engineer II - Data Platform (Stockholm/London, 09-28)
     - Senior Growth Manager (Mumbai, 10-06)

     The 12 newest Lever postings (up to 2026-10-16) are all on the site, so this is **deliberate omission, not sync lag**.
  2. Same-title postings in several cities are **regrouped**. 9 titles have 2 Lever postings each. The site shows 7 of these titles as 2 entries (slug `…-2`) with different city sets (e.g. site "London, Stockholm" vs Lever "London" only). It merges the other 2 into 1 entry: "Senior Fullstack Engineer" London+Stockholm, and "Staff Machine Learning Engineer, Home Surfaces" with 2 × New York.
  - Net result: 82 Lever postings → 73 site entries (66 titles). Every site title exists in Lever; none are site-only.

## Field map (Lever)
| Job field | Response path | Notes |
|---|---|---|
| id | `[].id` (UUID) | |
| title | `[].text` | original Lever title with " - " |
| location(s) | `[].categories.location` (primary), `[].categories.allLocations[]` | 33 postings have 2 locations and 1 has 3. `country` (ISO-2), `workplaceType` (hybrid/onsite/remote). |
| url (detail/apply) | `[].hostedUrl` = `https://jobs.lever.co/spotify/{id}`; `[].applyUrl` | |
| posted date | `[].createdAt` (epoch ms) | range 2025-10-24 → 2026-10-16 |
| description / snippet | `[].descriptionPlain` / `descriptionBodyPlain`; `lists[]`, `additionalPlain` | |
| employment type | `[].categories.commitment` | Permanent 76, Short Term 2, Full Time Contractor 1, none 3 |
| department / team | `[].categories.department` / `team` | e.g. Markets and Subscriber Growth / Marketing |

## Totals (observed 2026-10-20 00:13–00:15 UTC)
- **Feed, no filters:** **82** (unique ids). Spotify's Lever hosted board `https://jobs.lever.co/spotify` lists the **same 82** posting links.
- **Live careers page, no filters:** **73**. A Playwright render of https://www.lifeatspotify.com/jobs showed "**73 jobs** in all locations in all categories in all job types". That is the 73-entry wp-json response the page loaded. The difference of 9 is explained above: 7 postings omitted and 2 merged. **Lever is the complete source.**
- **Intern/student:** **0** on both Lever and the site. The bookmark's internship filter shows 0 jobs. Spotify's student pages (`/start-your-journey/students`) list fairs and events, not postings. When internships open they are posted on Lever.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://api.lever.co/v0/postings/spotify?mode=json | ALLOW | `Allow: /` (Crawl-delay: 1) |
| https://jobs.lever.co/spotify | ALLOW | `Allow: /` |
| https://api.lifeatspotify.com/wp-json/animal/v1/job/search | ALLOW | no matching rule (only /wp-admin/ is disallowed) |
| https://www.lifeatspotify.com/jobs | ALLOW | `Allow: /` |

## Anti-bot / quirks
- No challenge on any host.
- Do not dedupe Lever postings by title. Same-title postings are separate requisitions in different cities. Dedupe by `id` only.
- To link to the site's page for a job, the slug must be derived from the site's rewritten title. That is not needed; use `hostedUrl`.

## Recommended checker
```yaml
- key: spotify
  name: Spotify
  adapter: lever
  careers_url: https://www.lifeatspotify.com/jobs
  settings:
    site: spotify
  # cross-check (optional, weekly): api.lifeatspotify.com wp-json job/search; expect ≈ Lever minus omissions
```

## Evidence
- Sample: `discovery/samples/spotify.json` is the Lever response **truncated to the first 3 of 82 postings**; the raw response is 790 KB. A `_sample_note` explains the truncation.
- Capture: `discovery/captures/spotify/` (the bookmark render: wp-json with `j=internship` returned an empty result; the `_next/data` frontpage reports `total_number_of_jobs` 73).
- Requests this run: 7 (robots ×4, Lever API, Lever hosted board, wp-json search) plus 1 Playwright render.
