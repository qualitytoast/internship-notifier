# John Deere (`john-deere`)

**Status:** verified-feed (main board). There is also a second, SuccessFactors-only board; see below.   ·   **Checked:** 2026-10-19 19:16–19:22 CDT (2026-10-20 00:16–00:22 UTC)

| | |
|---|---|
| Official careers URL | https://careers.deere.com/careers (no filters). The bookmark is a filtered view of it (`location=united states`, `filter_seniority=0` = Intern, 9 jobs). |
| Hiring system | **Eightfold.ai PCSX** career site, Eightfold domain `johndeere.com`. Apply is **native Eightfold**: `position_details.positionUserActions.applyAction.status = "allowed"` and there is no external `applyUrl`. Job numbers are 6-digit (`displayJobId` = `atsJobId`, e.g. `123547`). **No Workday tenant was found**: `johndeere.wd5.myworkdayjobs.com/robots.txt` returns HTTP 422 (Workday's answer for an unknown tenant), and nothing on either site links to Workday. |
| Second board | **jobs.deere.com**, the legacy **SAP SuccessFactors Recruiting Marketing (RMK)** site. careers.deere.com links to it in a banner: "View and apply for apprentice jobs in Europe" → `https://jobs.deere.com/successfactors/go/R2ApprenticeJobs/9425200/`. It republishes the Eightfold jobs (`/eightfold/job/…` links) and adds **76 SuccessFactors-only items** (`/successfactors/job/…`) that are **not on careers.deere.com**: 36 Germany (Ausbildung apprenticeships and Schülerpraktikum pupil internships), 35 US hourly production/maintenance, and 5 China. |
| Recommended adapter | shared `eightfold` adapter (`api: pcsx`) for the main board, not `big` (34 pages). Optionally a small custom RSS reader (`custom:deere-rmk`) for the SuccessFactors-only items. |

## Recommended feed
### Main board (Eightfold)
- **Request:** `GET https://careers.deere.com/api/pcsx/search?domain=johndeere.com&query=&location=&start=0&sort_by=timestamp`
- **Headers:** a normal browser UA and `Accept: application/json`. No cookie or CSRF token is needed.
- **Pagination:** `start` += 10 until `start >= data.count`. The whole site was **34 requests** (334 jobs, 334 unique ids, and `count` stayed 334 on every page). 34 requests at 2.0 s spacing produced no 429.
- **Intern filter (optional):** `&filter_seniority=0` → **26** worldwide. `seniority` options: `0` = Intern, `1` = Entry, `2` = Mid/Senior, `3` = Director. The intern seniority filter **misses most student roles**: the 41 "Part-Time Student – …" US roles, the French "Stagiaire …" roles, "Student Placement" (UK) and the German Ausbildung roles are not seniority 0. So read the whole board each poll; it's only 34 requests.
- **Detail (optional):** `GET https://careers.deere.com/api/pcsx/position_details?position_id=<id>&domain=johndeere.com&hl=en` returns `data.jobDescription` (HTML) and `publicUrl`.
- **Job URL:** `https://careers.deere.com` + `positionUrl` = `https://careers.deere.com/careers/job/<id>`.
- **Eightfold sitemap** (`/careers/sitemap.xml?domain=johndeere.com`, linked from robots.txt) is **stale**: it had 322 jobs with lastmod ≤ 2026-10-15, missed 16 current jobs and still listed 4 closed ones. Don't use it as the feed.

### Second board (SuccessFactors RMK, jobs.deere.com), optional custom reader
- **Request:** `GET https://jobs.deere.com/sitemap.xml`. Despite the name, this is an **RSS 2.0 / Google Base feed** of the whole RMK site: 423 `<item>`s, 5.6 MB because every item carries its full description. `<ttl>720</ttl>`, `Cache-Control: no-cache, no-store`, and no ETag or Last-Modified, so it can't be fetched conditionally.
- **Keep** items whose `<link>` contains `/successfactors/job/` (76 today; 60 distinct titles, because 16 titles are posted twice under different ids). Items with `/eightfold/job/` (347) duplicate the main board; RMK's copy lags (e.g. req 125134 is still listed but no longer on careers.deere.com).
- **Item fields:** `title` = `"<title> (<City>, <ST>, <CC>, <zip>)"`, `link` (job URL, e.g. `https://jobs.deere.com/successfactors/job/Bruchsal-Ausbildung-zum-…/1408079300/`), `guid` = `g:id` (RMK id), `g:location` (`"Bruchsal, BW, DE, 76646"`), `g:job_function`, `g:expiration_date`, and `description` (HTML-escaped HTML).
- **Cadence:** every 6–12 h is enough given `ttl 720`. Alternatives on the same host:
  - the RMK search HTML, `GET https://jobs.deere.com/search/?q=&sortColumn=referencedate&sortDirection=desc&startrow=N`: 25 rows per page; "Results 1 – 25 of 347" on 2026-10-19; rows are `tr.data-row` with `a.jobTitle-link`, `.jobLocation`, `.jobDate`.
  - the apprentice category page `…/successfactors/go/R2ApprenticeJobs/9425200/` ("Results 1 – 18 of 18").
- `jobs.deere.com/services/rss/…` (RMK's official RSS endpoint) is **robots-disallowed** (`Disallow: /services/`). `/sitemap.xml` is allowed.

## Field map (main board, `data.positions[]`)
| Job field | Response path | Notes |
|---|---|---|
| id | `id` (int, 12 digits) | e.g. `137482769306`. `displayJobId` = `atsJobId` (`"123547"`) is the human job number, which also appears in RMK descriptions as "Title: … - 123547". |
| title | `name` | multilingual: English, German (`Praktikum …`, `Ausbildung 2027 - …`), French (`Stagiaire …`), Portuguese, Polish |
| location(s) | `locations[]` (`"Fargo,North Dakota,United States"`), `standardizedLocations[]` (`"Fargo, ND, US"`) | some are `"Various Locations,Illinois,United States"` → `"IL,US"` |
| url | `"https://careers.deere.com" + positionUrl` | `/careers/job/137482769306` |
| posted date | `postedTs` (epoch seconds, full timestamp) | `creationTs` = creation |
| description / snippet | detail → `jobDescription` | |
| employment type | none in list; `filter_seniority` (0 = Intern) | titles carry "Intern", "Part-Time Student", "Apprentice", "Praktikum", "Stagiaire" |
| department / team | `department` (e.g. `Product Engineering (CA)`, `Factory Engineering (CA)`, `Other (CA)`) | |
| other | `workLocationOption` (`onsite`/`hybrid`), `locationFlexibility` | |

## Totals (observed 2026-10-19)
| Measure | Value | How observed |
|---|---|---|
| Feed, no filters (main board) | **334** | `data.count`; all 34 pages read, 334 unique ids |
| Live careers page, no filters | **334** | One Playwright render of https://careers.deere.com/careers showed "**334 jobs**" and "of 34". The page's default sort is `sort_by=hot`; counts don't depend on sort. |
| By country (primary location) | US 198, BR 39, DE 36, CA 16, FR 16, PL 14, MX 8, GB 2, NL 2, AU 1 | from the 334 positions |
| Second board (jobs.deere.com) | RSS 423 items = 347 `/eightfold/` + **76 `/successfactors/`**. Search page: "Results 1 – 25 of 347". | RSS parsed; the RMK search HTML read once. None of the 76 SuccessFactors titles appears on careers.deere.com (normalized title match against all 334). |
| **Intern/student (main board)** | **86** = 26 with seniority Intern + 60 more by title | 41 "Part-Time Student – …" (US), 11 more "Stagiaire …" (FR), 2 "Student Placement" (UK), 3 "Ausbildung 2027 – …" (DE, Stadtlohn), "HR Stage" (NL), "Initiativbewerbungen Praktika und Abschlussarbeiten" (DE, open application for internships/theses), and "Rechtsreferendar" (DE legal trainee). The 26 seniority-Intern jobs are "2027 Intern – …" (9 US), Praktikum (10 DE), Apprentice (3 PL), Stagiaire (2 FR) and Intern (2 DE). **47** of the 86 have a US location. |
| Intern/student (second board only) | **36** items (20 distinct titles), all Germany | Ausbildung (apprenticeships) and Schülerpraktikum (pupil internships) |

Workday cross-check: not applicable. There is no Workday; the main-board count equals the page.

## robots.txt
careers.deere.com: `User-agent: *` / `Disallow: /` with `Allow:` `/$`, `/careers`, `/api/apply`, `/api/pcsx`, `/login`, `/events/…`, `/careerhub/explore/jobs`, `/api/career_hub`, `/static/gen`, `/gen`, plus `Sitemap: https://careers.deere.com/careers/sitemap_index.xml?domain=johndeere.com`. jobs.deere.com disallows `/applybutton/`, `/talentcommunity/`, `/mobile/talentcommunity/`, `/emailsubscribe/`, `/email/image/`, `/services/`, `/preapply/`, `/error`, `/unsubscribe/`, `/reset/`.

| URL | Verdict | Deciding rule |
|---|---|---|
| `https://careers.deere.com/api/pcsx/search?domain=johndeere.com&query=&location=&start=0&sort_by=timestamp` (and `&filter_seniority=0`) | ALLOW | `Allow: /api/pcsx` |
| `https://careers.deere.com/api/pcsx/position_details?position_id=137482769306&domain=johndeere.com&hl=en` | ALLOW | `Allow: /api/pcsx` |
| `https://careers.deere.com/careers`, `/careers/job/137482769306`, `/careers/sitemap.xml?domain=johndeere.com` | ALLOW | `Allow: /careers` |
| `https://careers.deere.com/api/suggest?…` | **BLOCK** | `Disallow: /`. Not needed. |
| `https://jobs.deere.com/sitemap.xml` (RSS) | ALLOW | no matching rule |
| `https://jobs.deere.com/search/?q=&sortColumn=referencedate&sortDirection=desc&startrow=25` | ALLOW | no matching rule |
| `https://jobs.deere.com/successfactors/go/R2ApprenticeJobs/9425200/` and `/successfactors/job/…/1408079300/` | ALLOW | no matching rule |
| `https://jobs.deere.com/services/rss/job/?locale=en_US&keywords=` | **BLOCK** | `Disallow: /services/` |
| `https://jobs.deere.com/applybutton/…` | **BLOCK** | `Disallow: /applybutton/`. Use it as a link only. |
| `https://johndeere.wd5.myworkdayjobs.com/wday/cxs/johndeere/…` | (ALLOW) | robots.txt HTTP 422, which counts as 4xx, so allow-all. No such tenant, so it's not used. |

## Anti-bot / quirks
- No bot challenge anywhere. careers.deere.com is Eightfold (CloudFront); jobs.deere.com is Apache/nginx (RMK).
- Eightfold spacing: 41 requests at ≥ 2.0 s gave no 429. Keep ≥ 2 s; Microsoft's PCSX did return 429 at 1.1 s.
- Titles are in 6+ languages. The project's role filters need the local words to see European student roles: Praktikum, Werkstudent, Ausbildung, Schülerpraktikum, Stagiaire/Stage, Estágio, Praktyk/Staż, Apprenti. US student roles are mostly titled "Part-Time Student – …" or "2027 Intern – …".
- The seniority=Intern filter catches only 26 of the 86 student-type roles (see Totals), so don't rely on it.
- The RMK RSS is 5.6 MB and can't be fetched conditionally. Fetch it rarely and stream-parse it.

## Recommended checker
```yaml
- key: john-deere
  name: John Deere
  category: industrial
  careers_url: https://careers.deere.com/careers
  checker: eightfold
  settings: {host: careers.deere.com, domain: johndeere.com, api: pcsx, min_interval: 2.0}
  # full scan each poll: 34 pages (334 jobs); not big
  # optional second board (SuccessFactors-only: DE apprenticeships/pupil internships, US hourly, CN):
  # - key: john-deere-rmk
  #   checker: custom:deere-rmk          # GET https://jobs.deere.com/sitemap.xml (RSS 2.0), keep <item>s whose
  #   settings: {feed: https://jobs.deere.com/sitemap.xml, keep_link_contains: /successfactors/job/, poll_hours: 12}
  #   # id = guid, title = title minus the trailing "(City, ST, CC, zip)", location = g:location, url = link
```

## Evidence
- Sample: `discovery/samples/john-deere.json` (41 KB): the raw PCSX unfiltered page 1 (count 334, filterDef), raw `position_details`, and 3 raw RSS `<item>`s from jobs.deere.com/sitemap.xml (1 Eightfold-sourced, 2 SuccessFactors-sourced; descriptions truncated).
- Requests: 46 scripted requests (40 careers.deere.com: unfiltered, intern filter 3 pages, 1 detail, the other 33 unfiltered pages, 2 sitemap files; 5 jobs.deere.com: apprentice page, search page, RSS, one HEAD; plus robots), 1 Playwright page load (7 same-host XHRs), and 3 `robots_check.py` runs.
- Old capture: `discovery/captures/john-deere/` (bookmark view: 9 US interns).
