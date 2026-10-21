# DoorDash (`doordash`)

**Status:** verified-feed: 8 Greenhouse boards. The site also lists 217 hourly roles that no open feed has (see below); none are internships.   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://careersatdoordash.com/job-search/ (the bookmark `/university-careers/` is a filtered view of the same list) |
| Hiring system | Greenhouse, **8 public boards**, one per legal entity plus SevenRooms UK. careersatdoordash.com (a WordPress theme called `external-job-board`) shows them as one list with job pages at `/jobs/<slug>/<gh id>`. On a job page, "Apply To Job" goes to `job-boards.greenhouse.io/<board>/jobs/<id>`. For hourly roles it goes to Fountain instead (`doordash.fountain.com/apply/doordash/opening/...`). |
| Recommended adapter | shared `greenhouse` adapter with a `boards:` list |

The probe found only `doordashusa`. I found the other boards this way:
- `doordashaustralia`, `doordashindia`, `doordashquebec` and `sevenroomsuk`: from the apply links on job pages that were missing from `doordashusa`.
- `doordashcanada`, `doordashinternational` and `doordashmexico`: from token guesses, then matched against the page's ids.

| Board | `company_name` | Jobs |
|---|---|---|
| doordashusa | DoorDash USA | 453 |
| doordashcanada | DoorDash Canada | 42 |
| doordashaustralia | DoorDash ANZ | 32 |
| doordashmexico | DoorDash Mexico | 27 |
| doordashindia | DoorDash India | 16 |
| doordashinternational | DoorDash Brazil | 15 |
| sevenroomsuk | SevenRooms, a DoorDash company - United Kingdom | 10 |
| doordashquebec | DoorDash Quebec | 3 |
| **total** | | **598** |

These guessed tokens all returned **404**: doordashdashmart, dashmart, doordashhourly, doordashfulfillment, doordashoperations, doordashretail, doordashjapan, doordashnewzealand, doordashgermany, doordashuk, doordashlabs, doordashfountain, doordashusahourly, doordashdashmartusa, dashmartusa, doordashcx, doordashsupport, doordashessentials, sevenrooms, sevenroomsus, sevenrooms-us, sevenroomsinc. The probe's `doordash` token also returns 404; there is no board by that name.

## Page vs feed (the 217 gap)
- The page shows "1 – 25 of 815". I walked all 33 pages in a Playwright session, 1.5 s apart, using the page's own pager:
  - `GET /wp-content/themes/external-job-board/theme/get-jobs.php?ajax=1&keyword=&location=&function=&department=&level=&intern=&spage=N`
  - Each page returns JSON `{"postings": "<html rows>", "showing": "26 – 50 of 815", "pagination": "<html>"}` with 25 rows.
  - Result: **815 unique Greenhouse job ids**.
- **All 598 feed jobs are on the page.** No board job is missing from the site.
- **217 jobs are only on the page.** All are hourly roles:
  - 215 have Department "DashMart" and Function "Fulfillment": "Variable Schedule Team Member" ×79, "DashMart Team Member - <site>", "Operations Associate", "Warehouse Associate".
  - 1 "Customer Support Agent" (Hyderabad).
  - 1 "Representative, Authenticity" (Mexico City).
- All 3 of those job pages I opened apply at `doordash.fountain.com`. I found no public Greenhouse board for them. Greenhouse does not redirect `/doordashusa/jobs/<id>` to the right board; it goes to `?error=true`. Fountain's applicant UI is a JS shell, and its data lives under `/api`, which robots.txt disallows.
- Hourly roles are split across systems: 9 `doordashusa` jobs carry metadata `Fountain HVH = true` (e.g. "DashMart Team Member - Deer Park"), and those are in the feed.
- **Decision:** the 8 boards are complete for corporate and salaried roles and for **every internship**. All 7 intern titles on the page are in the feeds.
  - The 217 hourly roles appear only on careersatdoordash.com. That site returns a Cloudflare challenge (403, `cf-mitigated: challenge`) to plain HTTP clients, so a checker cannot use it without working around bot protection.
  - Fallback if hourly roles ever matter: none open. Skip them.

## Recommended feed
- **Requests:** one `GET https://boards-api.greenhouse.io/v1/boards/<board>/jobs` per board in the table. Use a normal UA; no auth is needed.
- **Pagination:** none. Each response holds the whole board, and `meta.total` equals the number of jobs (checked on all 8).
- **Size:** `doordashusa` is 1.2 MB even without `content=true`, because every job carries about 21 metadata fields, including pay bands.

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `jobs[].id` | Unique across boards. It is also the id in the careersatdoordash URL. |
| title | `jobs[].title` | |
| location(s) | `jobs[].location.name` | e.g. `"San Francisco, CA; Sunnyvale, CA"`, sometimes with a leading space, so trim it. Also in metadata "Job Location". |
| url (apply) | `jobs[].absolute_url` | `https://job-boards.greenhouse.io/<board>/jobs/<id>`. The public page is `https://careersatdoordash.com/jobs/<slug>/<id>`, but don't fetch it (Cloudflare). |
| posted date | `jobs[].first_published` | |
| employment type | metadata "Time Type" | `"Full time"` or `"Part time"`. It says "Full time" on intern roles too, so use the title. |
| department / team | metadata "Careers Page Sorting: Department", "Job Family", "Business Line" | |
| other | `company_name` (per board), metadata "Fountain HVH", "Fountain Opening ID", "Wolt: Careers Site Department" | |

## Totals (observed 2026-10-20 00:40Z)
- **Feed, no filters:** **598** (the 8 boards above).
- **Live careers page, no filters:** **815**. The page reads "1 – 25 of 815", and all 33 pages added up to 815 unique ids. The gap is explained above.
- **Intern/student:** **7**. The page and the feeds have the same 7:
  - 8274095 Electrical Engineer, Intern - Labs (Summer 2027), Oakland, CA (usa)
  - 8263774 Software Engineer, Intern - Labs (Summer 2027), San Francisco / Sunnyvale (usa)
  - 8233953 Machine Learning Intern (PhD) - Summer 2027, SF / Sunnyvale / NYC / Seattle (usa)
  - 8204111 Machine Learning Intern (Masters) - Summer 2027, same cities (usa)
  - 8171041 Software Engineer, Intern (Summer 2027) - US, NYC / SF / Sunnyvale / LA / Seattle (usa)
  - 8176863 Product Design, Intern (Summer 2027), SF / NYC (usa)
  - 8170944 Software Engineer, Intern (Summer 2027) - TOR, Toronto (canada)

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `https://boards-api.greenhouse.io/v1/boards/<each of the 8>/jobs` | ALLOW | no matching rule (only `/embed/` is disallowed) |
| `https://job-boards.greenhouse.io/doordashusa/jobs/<id>` | ALLOW | no matching rule |
| `https://careersatdoordash.com/job-search/` and `.../theme/get-jobs.php` | ALLOW | no robots.txt (404). Non-browser clients get a Cloudflare challenge. |
| `https://doordash.fountain.com/apply/doordash` | ALLOW | no matching rule, but `Disallow: /api` covers its data API |

## Anti-bot / quirks
- careersatdoordash.com is behind Cloudflare (rocket-loader, `cdn-cgi`). httpx gets 403 `cf-mitigated: challenge` on every URL, including job pages and `get-jobs.php`. A plain headless Chromium loaded it without a challenge. I only observed what the page loads.
- Board tokens follow legal entities, not regions: `doordashinternational` is DoorDash Brazil and `doordashaustralia` is DoorDash ANZ. Acquisitions add boards (SevenRooms UK is already merged). Wolt and Deliveroo are not on the site today.
  - New boards only show up in the apply links on the site. Re-check now and then (e.g. yearly) by opening a few careersatdoordash.com job pages in a browser.

## Recommended checker
```yaml
- key: doordash
  name: DoorDash
  adapter: greenhouse
  settings:
    boards: [doordashusa, doordashcanada, doordashquebec, doordashaustralia, doordashmexico,
             doordashindia, doordashinternational, sevenroomsuk]
  careers_url: https://careersatdoordash.com/job-search/
```

## Evidence
- Sample: `discovery/samples/doordash.json` is the raw `get-jobs.php` response for `spage=2`, captured in-browser (51 KB). It has 25 rows, including Fountain-only "Variable Schedule Team Member" rows, and `"showing": "26 – 50 of 815"`.
- Capture: `discovery/captures/doordash/` (university page, 2 jobs).
- Requests I made:
  - careersatdoordash.com: about 4 page loads, 8 job pages and 34 pager calls in Playwright, plus 3 httpx probes that got 403.
  - boards-api.greenhouse.io: about 45 calls in total (8 boards fetched 2–3 times, 22 token guesses, 2 redirect tests), at ≤1 request/second.
