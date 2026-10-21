# Atlassian — job feed discovery

**Status:** verified-feed
**Checked:** 2026-10-19, 18:47–18:51 CDT (23:47–23:51 UTC). Requests made: 13 plain HTTP requests (5 to the feed and pages on www.atlassian.com, 3 iCIMS job pages, 2 iCIMS robots.txt, 3 more for the ETag test and detail pages) + 7 robots.txt fetches by `robots_check.py` + 2 headless-Chromium page loads (about 24 document/XHR requests to www.atlassian.com, plus the usual JS/CSS/CDN assets).

## Careers site
- Official careers URL (job search, no filters): https://www.atlassian.com/company/careers/all-jobs
  (the bookmark `?team=Interns&location=&search=` only filters on the client: `team` matches `fields.category` exactly, and `location` checks whether `fields.locations` contains one of 15 country names.)
- Hiring system / ATS: **iCIMS**, spread over 6 portals. Evidence: every posting's `applyUrl`/`portalJobPost.portalUrl` is an `*.icims.com/jobs/<id>/<slug>/job` URL, and the feed's `portalJobPost`/`portalId` fields are iCIMS portal ids:
  | portalId | iCIMS host | jobs (unique) |
  |---|---|---|
  | 111 | careers-americas.icims.com | 163 |
  | 17 | globalcareers-atlassian.icims.com | 95 |
  | 242 | careers-apac-atlassian.icims.com | 67 |
  | 251 | campus-americas.icims.com | 9 |
  | 250 | campus-globalcareers-atlassian.icims.com | 2 |
  | 193343 | globalmobility-careers-atlassian.icims.com | 1 |

  You don't need to query the portals one by one: the feed already merges all of them. Interns are **not** all on the campus portals (5 of the 12 intern postings are on portal 111).
- The atlassian.com pages (`all-jobs` gallery and `details/<id>`) are rendered server-side from a **CMS copy** of the postings (Contentful-shaped `{sys:{id}, fields:{…}}` items inside `window._uniformPreloadedComposition`). That copy lags behind iCIMS (see Totals).
- Public job detail URL formats:
  - iCIMS job page, which always works while the job is open: `portalJobPost.portalUrl`, e.g. `https://careers-americas.icims.com/jobs/27781/principal-technical-program-manager/job`. A closed job returns **HTTP 410**.
  - Apply URL: `applyUrl` = `portalUrl + "?mode=apply"` (true for 356/356 rows).
  - Atlassian page: `https://www.atlassian.com/company/careers/details/{id}`. This page only works once the CMS has synced the job: for brand-new job 27781 it returned 200 but rendered a **blank page** in Chromium.

## Recommended feed
- **Request:** `GET https://www.atlassian.com/endpoint/careers/listings`
- **Query params:** none. There are no filters or pagination, and the response is every posting.
- **Headers:** a normal browser `User-Agent`, `Accept: application/json`, `Accept-Encoding: gzip`. No cookies, tokens or CSRF are needed. For polling, send `If-None-Match: <ETag from last 200>`.
- **Body:** none.
- **Pagination:** none. The response is one top-level JSON array holding all rows (356 rows = 337 unique jobs). The array contains **exact duplicate rows** (19 extra rows across 18 ids, e.g. id 27059 appears 3 times), so dedupe on `id`. The row order is not by date.
- **Size / caching:** 2,452,263 bytes of JSON, about **513 KB gzip on the wire**. The ETag is weak and Express-style (`W/"256b27-…"`, where the hex part is the byte length) and was the same across fetches 11 minutes apart. Sending **`If-None-Match` returned `304` with an empty body** (verified). CloudFront showed `x-cache: Miss`, with no `cache-control` or `last-modified` headers.
- **Full enumeration cost:** 1 request (about 513 KB, or 0 bytes on a 304).
- **Detail/description endpoint:** not needed. The list already includes the full HTML description fields. Optional: the iCIMS job page `portalUrl + "?in_iframe=1"` has schema.org JSON-LD with `datePosted` (e.g. `2026-10-14T04:00:00.000Z`) and the requisition number (`REQ-2026-3489`), at one request per job.
- Alternatives considered:
  - SSR HTML of `/company/careers/all-jobs` (1.97 MB): the job array is at `window._uniformPreloadedComposition` → the component with `type == "careersGallery"` → `parameters.data.value[]` (fields `sys.id`, `fields.{id,title,category,type,locations,applyUrl,portalId,portalApplyUrls}`). It is a stale CMS copy with no descriptions and no dates, so use it only to cross-check the count the page shows.
  - iCIMS portal search pages: 6 portals of paginated HTML. They are worse and unnecessary.
  - `POST /gateway/api/graphql` on the page fetches the marketing profile (`growthUnifiedProfile_getUnifiedProfile`) and has nothing to do with jobs.

## Field map (JSON paths relative to one item of the top-level array)
| Field | Path | Example |
|---|---|---|
| id | `id` (int; equals the iCIMS job id and `portalJobPost.id`) | `26266` |
| title | `title` (the feed's titles were clean, but strip anyway: the page's CMS copy had 4 titles with trailing spaces) | `Software Engineer Intern, 2027 Summer U.S.` |
| location(s) | `locations[]` strings, `"<Office> - <Country> -   <City>, <Region> <ZIP> <Country>"` or `"Remote - Remote"`, `"Remote - UK - Remote"`, `"Remote - Americas - Remote"`; 11 jobs have `[]` | `["San Francisco - United States -   San Francisco, California 94104 United States", "Seattle - United States -   Seattle, Washington  United States"]` |
| detail URL | `portalJobPost.portalUrl` (iCIMS); secondary: `https://www.atlassian.com/company/careers/details/{id}` | `https://careers-americas.icims.com/jobs/26266/software-engineer-intern%2c-2027-summer-u.s./job` |
| apply URL | `applyUrl` | `…/job?mode=apply` |
| posted date | not in the feed (use first-seen, or iCIMS JSON-LD `datePosted`) | — |
| updated date | `portalJobPost.updatedDate`, `"YYYY-MM-DD hh:mm AM/PM"` with no timezone. Its latest value, `2026-10-19 10:41 PM`, came when it was 23:46 UTC, so it fits UTC. Treat it as an opaque change marker. | `2026-09-18 04:09 PM` |
| description / snippet | `overview`, `responsibilities`, `qualifications` (HTML); optional `compensation` (177 jobs) and `payRanges` (166 jobs; US zone pay ranges) | `<p><strong>Working at Atlassian</strong></p>…` |
| employment type / intern flag | `type` is only ever `"Full-Time"` (89 jobs) or **absent** (248, including every intern). Detect interns with `category == "Interns"`, early-career with `category == "Graduates"`, and also the title words "Intern" / "Graduate". | `category: "Interns"` |
| team / category | `category` (16 values: Sales 146, Engineering 104, Analytics & Data Science 17, Interns 12, Product Management 9, Security 8, Design 8, Other 6, Finance & Accounting 6, Graduates 5, Marketing 5, Legal 4, People 3, ACE 2, Support 1, Program Management 1) | `Engineering` |
| portal | `portalId` (int; equals `portalJobPost.portalId`) | `111` |

List path: top-level array (`$[*]`). Total: `len(unique(id))`. The feed has no total field.

## Totals (observed 2026-10-19)
| Measure | Value | How observed |
|---|---|---|
| Feed total, no filters | **337 unique jobs** (356 rows) | `GET /endpoint/careers/listings` at 18:47 and 18:51 CDT (same ETag), deduped on `id` |
| Live careers page total, no filters | **346** ("346 JOBS") | https://www.atlassian.com/company/careers/all-jobs loaded in headless Chromium at 18:49 CDT. The visible label is the length of the SSR-embedded array (346); the page makes no listing XHR. |
| Intern / student | **12 interns** (`category == "Interns"`: 11 US "2027 Summer U.S.", 1 Canada) + **5 graduate** roles (`"Graduates"`: 4 US, 1 Canada). There are 0 intern/graduate/student/co-op titles outside those two categories. | Feed. The page has the same 12 intern ids, and the capture of `?team=Interns` showed "12 JOBS". |
| US / Canada | 160 jobs have a "United States" location, 12 have "Canada" | Feed, substring match on `locations[]` |

Why the page and the feed differ (346 vs 337): the page's CMS copy lags iCIMS.
- **14 ids are on the page but not in the feed.** These are stale. I checked 2 of them on iCIMS (25587 on careers-americas, 25317 on globalcareers-atlassian) and both returned **HTTP 410 Gone**.
- **5 ids are in the feed but not on the page.** These are new or recently updated (e.g. 27781 updated 2026-10-19, and 27379). 27781 is **live on iCIMS** (200, `datePosted 2026-10-14`), while its atlassian.com detail page renders blank.

So the feed is the more accurate source. A gap of about ±20 between feed and page is normal and is not a checker fault.

## robots.txt
Atlassian's robots.txt has a `User-agent: atlassian-bot` group that disallows `/company/careers/detail/*`. That group does not apply to us: we match the `*` group, which has no rule for `/endpoint` or `/company/careers`.

| URL | Verdict | Rule (from discovery/robots_check.py) |
|---|---|---|
| https://www.atlassian.com/endpoint/careers/listings | ALLOW | no matching rule (allowed) |
| https://www.atlassian.com/company/careers/all-jobs | ALLOW | no matching rule (allowed) |
| https://www.atlassian.com/company/careers/details/27781 | ALLOW | no matching rule (allowed) |
| https://careers-americas.icims.com/jobs/27059/senior-solutions-engineer/job (and `?mode=apply`) | ALLOW | no matching rule (allowed) |
| https://globalcareers-atlassian.icims.com/jobs/25480/account-executive%2c-mid-market/job | ALLOW | no matching rule (allowed) |
| https://careers-apac-atlassian.icims.com/jobs/25538/backend-software-engineer/job | ALLOW | no matching rule (allowed) |
| https://campus-americas.icims.com/jobs/26272/data-engineer-intern%2c-2027-summer-u.s./job | ALLOW | no matching rule (allowed) |
| https://campus-globalcareers-atlassian.icims.com/jobs/26275/software-engineer-intern%2c-2027-canada/job | ALLOW | no matching rule (allowed) |
| https://globalmobility-careers-atlassian.icims.com/jobs/27067/…/job | ALLOW | no matching rule (allowed) |

iCIMS robots.txt only disallows referral, login, candidate, reminder and connect paths.

## Anti-bot / gotchas
- I saw no anti-bot measures. Plain httpx GETs with a browser UA worked, with no cookies, no JS challenge and no rate-limit headers. The careers page loads a reCAPTCHA Enterprise anchor, but the feed doesn't need it.
- The response is large (2.45 MB), so always send `Accept-Encoding: gzip` and `If-None-Match`, which gives a 304 when nothing changed.
- The feed has duplicate rows, so dedupe on `id`. Strip titles defensively.
- `type` is missing for most jobs, so don't use it as the employment-type signal.
- The feed has no posted date. `updatedDate` has no timezone.
- The atlassian.com detail page is blank for jobs the CMS hasn't synced yet, so put the iCIMS `portalUrl` in alerts.
- iCIMS returns 410 for closed jobs. That gives a cheap way to confirm a disappearance if ever needed.

## Recommended checker approach
1. `GET https://www.atlassian.com/endpoint/careers/listings` with `If-None-Match` set to the stored ETag. On a 304, the job set is unchanged: record success and stop.
2. On a 200, parse the array, dedupe on `id`, `title.strip()`, and store the new ETag.
3. Map fields as above. Use `url = portalJobPost.portalUrl` and `apply_url = applyUrl`, and keep `https://www.atlassian.com/company/careers/details/{id}` as a secondary link. The location string is `"; ".join(locations)` and country matching can be a substring test ("United States", "Canada", "Remote - Americas"). The description comes from `overview + responsibilities + qualifications` (no extra fetch). The posted date is the first-seen time, and `updatedDate` is kept as an extra.
4. Student signal: `category in {"Interns", "Graduates"}` OR title regex (`intern|graduate|co-op|student`).
5. Health: expect about 300–400 unique jobs, so alert on 0 or on a drop of more than 50%. Don't compare strictly against the careers page count (346), because the CMS lags by about ±20.

## Sample
`discovery/samples/atlassian.json` is from the `GET https://www.atlassian.com/endpoint/careers/listings` response of 2026-10-19 18:51 CDT, trimmed to 5 items in the original bare-array shape:
- 2 interns (26266 on portal 111, 26272 on campus portal 251)
- 1 graduate role (25813)
- 1 Full-Time engineering job with `compensation`/`payRanges` and 6 locations (26762)
- 1 job with `locations: []` (26753)

HTML fields longer than 300 characters are cut off and end in `…[truncated]`.
