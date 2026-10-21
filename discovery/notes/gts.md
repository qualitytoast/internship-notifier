# GTS (`gts`)

**Status:** needs-custom (iCIMS: no public JSON list API; parse one light HTML page)   ·   **Checked:** 2026-10-19

| | |
|---|---|
| Official careers URL | https://gtsx.com/careers/. The firm's domain is **gtsx.com**; `www.gts.com` does not resolve. The page's "SEARCH OPEN POSITIONS" button goes to the iCIMS portal at https://careers-gtsx.icims.com/jobs/search?ss=1, which is wrapped in the gtsx.com header and footer (WordPress page 4059). |
| Hiring system | iCIMS (customer portal `careers-gtsx.icims.com`) |
| Recommended adapter | iCIMS HTML list (shared `icims` adapter: search page with `in_iframe=1`, `pr` pager) |

## Recommended feed
- **Request:** `GET https://careers-gtsx.icims.com/jobs/search?ss=1&in_iframe=1`. Use `&pr=<n>` (0-based page index) for further pages.
- **Headers:** a normal browser UA. No cookies needed. `in_iframe=1` returns the bare list (43 KB) instead of the page wrapped in gtsx.com chrome (208 KB).
- **Pagination:** the header text reads `Search Results Page X of N`. Fetch `pr=0…N-1`. All 16 jobs are on one page today ("Page 1 of 1"). iCIMS's maximum page size was not observable with 16 jobs; it is at least 16 (the iCIMS default is usually 20), so always follow `Page X of N`.
- **Completeness cross-check (cheap):** `GET https://careers-gtsx.icims.com/sitemap.xml` lists every live job URL with `<lastmod>` (16 job URLs = 16 cards today). This is machine-readable and complete, but has no title or location, only the slug.
- **Detail endpoint (optional):** `GET https://careers-gtsx.icims.com/jobs/<id>/<slug>/job?in_iframe=1`. It has a `<script type="application/ld+json">` JobPosting with `title`, `datePosted`, `validThrough`, `employmentType` (e.g. `FULL_TIME`), `description` (HTML) and `jobLocation[].address` (often "UNAVAILABLE").

## Field map
List cards are `ul.iCIMS_JobsTable > li.iCIMS_JobCardItem`.

| Job field | Response path | Notes |
|---|---|---|
| id | `a.iCIMS_Anchor@title` prefix (`"1608 - Quantitative Trader - 2027 Graduates"`) or `/jobs/(\d+)/` in href | iCIMS job number |
| title | `a.iCIMS_Anchor h3` text | HTML entities (`&ndash;`), so unescape |
| location(s) | `dl.iCIMS_JobHeaderGroup` → `dd.iCIMS_JobHeaderData span` for the "Job Location" dt, plus the "Additional Locations" dt (pipe-separated) | format `US-NY-New York`, `UK-London`, `PL-Warsaw`, `UY-Montevideo` |
| url (detail/apply) | `a.iCIMS_Anchor@href` with `?in_iframe=1` removed | `https://careers-gtsx.icims.com/jobs/<id>/<slug>/job`; Apply is on that page |
| posted date | detail JSON-LD `datePosted` | not on the list. The sitemap `lastmod` is the last-modified time, not the posted date. |
| description / snippet | `div.col-xs-12.description` (about 500-character overview) | full text in JSON-LD `description` |
| employment type | detail JSON-LD `employmentType` | not on the list |
| department / team | not exposed | |

## Totals (observed 2026-10-19)
- **Feed (iCIMS list), no filters:** **16** (1 request, "Page 1 of 1").
- **Live careers page, no filters:** **16** cards under "Search Results Page 1 of 1" on careers-gtsx.icims.com/jobs/search?ss=1 (httpx, full page). The sitemap.xml also has exactly 16 job URLs.
- **Intern/student:** **0**. The only campus role is 1608 "Quantitative Trader - 2027 Graduates" (new-grad, JSON-LD `employmentType: FULL_TIME`, posted 2026-09-09). GTS says internships are posted at schools when slots open.
- Locations: mostly New York. Others: Chicago, London, Warsaw (FPGA Developer - Poland), Montevideo/AR (Operations Analyst).

## robots.txt
careers-gtsx.icims.com disallows only referral, login, candidate, reminder and connect paths. The sitemap is declared.

| URL | Verdict | Deciding rule |
|---|---|---|
| https://careers-gtsx.icims.com/jobs/search?ss=1&in_iframe=1 | ALLOW | no matching rule |
| https://careers-gtsx.icims.com/jobs/search?pr=1&in_iframe=1 | ALLOW | no matching rule |
| https://careers-gtsx.icims.com/jobs/1608/quantitative-trader---2027-graduates/job?in_iframe=1 | ALLOW | no matching rule |
| https://careers-gtsx.icims.com/sitemap.xml | ALLOW | no matching rule |
| https://gtsx.com/careers/ | ALLOW | no matching rule (`Disallow:` empty) |

## Anti-bot / quirks
- **gtsx.com / www.gtsx.com** (WordPress) is behind Cloudflare. Plain httpx got HTTP 403 "Just a moment…" at www.gtsx.com, while one Playwright page load of gtsx.com/careers/ rendered fine. The checker never needs gtsx.com.
- **careers-gtsx.icims.com** (nginx + CloudFront) served plain httpx without challenge (5 requests).
- iCIMS sets cookies and shows a "Please enable cookies" banner. Listing works without cookies.
- `Additional Locations` holds pipe-separated values, which can repeat the main location.

## Recommended checker
```yaml
- key: gts
  name: GTS
  adapter: icims_html
  settings:
    portal: https://careers-gtsx.icims.com
    list_path: /jobs/search?ss=1&in_iframe=1
    page_param: pr            # 0-based; stop at "Page X of N"
    card: 'li.iCIMS_JobCardItem'
    detail_jsonld: true       # fetch /jobs/<id>/<slug>/job?in_iframe=1 for NEW ids only (datePosted, employmentType, description)
  careers_url: https://gtsx.com/careers/
```

## Evidence
- Sample: `discovery/samples/gts.html` (raw `jobs/search?ss=1&in_iframe=1` response, 43 KB, all 16 cards)
- Old capture: discovery/captures/gts (`ERR_NAME_NOT_RESOLVED` for www.gts.com)
