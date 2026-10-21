# Bloomberg (`bloomberg`)

**Status:** verified-feed (Avature HTML list, server-rendered)   ·   **Checked:** 2026-10-19 (US Central) = 2026-10-20 00:16–00:21 UTC

| | |
|---|---|
| Official careers URL | https://bloomberg.avature.net/careers/SearchJobs ("Search Jobs" on Bloomberg's careers portal). The bookmark adds `?1686=%5B55479%5D&1686_format=2312&listFilterMode=1&jobRecordsPerPage=12`, which is an Experience Level filter; track the unfiltered list. |
| Hiring system | Avature, portal `careers` on `bloomberg.avature.net`. Other portals listed in robots.txt (`/events`, `/talent`, `/internreferrals`, `/AIResearchInternship`, …) are forms and event pages, not job lists. `/AIResearchInternship` is a PhD interest form. |
| Recommended adapter | shared **`avature`** adapter: `{list_url: https://bloomberg.avature.net/careers/SearchJobs/, page_size: 12}` |

## Recommended feed (Avature list pager)
- **Request:** `GET https://bloomberg.avature.net/careers/SearchJobs/?jobRecordsPerPage=12&jobOffset={0,12,24,…}`. This is the pager's own link format; leaving out `jobRecordsPerPage` gives the same result.
- **Headers:** a normal browser UA, `Accept: text/html`. No cookies or tokens needed, and there was no challenge in 39 requests. The response is `text/html;charset=UTF-8`, about 96 KB per page.
- **Page size is fixed at 12.** `jobRecordsPerPage=100` and `=500` still returned 12 cards ("1-12 of 337"), with and without `listFilterMode=1`. Two Sigma's portal is fixed at 10 and Synopsys's at 6, so the page size is per portal and must be a setting.
- **Pagination:** add `page_size` to `jobOffset` until `jobOffset >= total` or a page returns fewer than `page_size` cards. 337 jobs took 29 requests (offsets 0–336; the last page had 1 card) and gave 337 unique ids with no duplicates.
- **Total:** `<div class="list-controls__text__legend" aria-label="337 results"> 1-12 of 337 results </div>`. The regex `list-controls__text__legend"\s+aria-label="(\d+) results"` works on every page. Check that unique ids equal this number.
- **Order:** the default order is **newest first**. Ids and sitemap lastmod both decrease, from 2026-10-19 on page 1 to 2025-06-16 on the last page. The first 1–2 pages are therefore enough between full scans. The only sort options are City, State, Country and Job Title; there is no posted-date sort.
- **Detail (optional):** `GET https://bloomberg.avature.net/careers/JobDetail/{slug}/{id}` (about 47 KB). Fields are `.article__content__view__field` label/value pairs: `Location` (city), `Business Area`, `Ref #` (e.g. 10054618) and "Description & Requirements". There is **no JSON-LD and no posted date**.

### Sources checked and rejected
- **RSS** `GET /careers/SearchJobs/feed/?jobRecordsPerPage=12` (linked from the page) always returns the **same 20 items**, the oldest by pubDate (2025-06-16 → 2026-03-25). `jobRecordsPerPage=500` gives the same 20. This is the Two Sigma behaviour again, so the feed is unusable.
- **Sitemap** `GET /careers/sitemap.xml` (via `sitemap_index.xml`, 117 KB) lists **337 JobDetail URLs, each with a `<lastmod>`**. Today it differed from the list by one id: list-only 22246 "Content Research & Activation Analyst", sitemap-only 20317 (an accountant role). So it lags a little. It is useful as a cheap daily cross-check, but it is not the primary feed. It has no titles (only slugs) and no locations.
- `api.altrulabs.com` (a widget) returned 404. The page also loads PerimeterX (`px-cloud.net` collector, `www.bloomberg.com/8FCGYgk4/init.js`), but the Avature HTML itself was served to plain httpx without any challenge.

## Field map (one card per job)
Card selector: `article.article--result` (regex `<article class="article article--result"(.*?)</article>`).

| Job field | Response path | Notes |
|---|---|---|
| id | last path segment of the title link `…/JobDetail/{slug}/{id}` | numeric Avature id (e.g. 45729), stable |
| title | `h3.article__header__text__title a.link` text | collapse whitespace; contains `&`, en-dashes |
| location(s) | `.article__header__text__subtitle span.list-item-location` | one string per card: `City, State, Country`, e.g. `Sao Paulo, São Paulo, Brazil`, `New York, New York, United States of America` |
| url (detail/apply) | the same `a.link@href` | `https://bloomberg.avature.net/careers/JobDetail/{slug}/{id}`. The "Apply" button has the same URL. "Save" → `/careers/SaveJob?jobId={id}`, never fetch it. |
| posted date | not on the card | the sitemap `<lastmod>` per JobDetail URL is the only date |
| description / snippet | detail page | |
| employment type | not on the card | titles carry the programme ("2027 Analytics & Sales Graduate Programme …") |
| department / team | detail `Business Area` | e.g. "Sales and Client Service" |

Two Sigma's portal uses a different card template (`span.paragraph_inner-span` × 3 for location / function / level). The shared adapter needs per-portal selectors for the subtitle fields. Title, link and id are the same in both.

## Totals (observed 2026-10-20 00:16–00:21 UTC)
- **Feed (HTML pager), no filters:** **337** unique jobs (29 pages).
- **Live careers page, no filters:** **337**, from the page's own legend "1-12 of 337 results" (server-rendered, the same HTML a browser gets).
- **By country:** US 167, UK 65, Singapore 28, Japan 21, Ireland 14, Hong Kong 13, India 9, Brazil 6, …
- **Intern/student:** **0**. No title contains intern, internship, co-op, apprentice, student or placement. The bookmark's Experience Level filter (`1686=[55479]`, captured page) also shows **0 results** today. There are 22 campus full-time roles: "2027 Analytics & Sales Graduate/Early Professional Programme …" and "2027 Bloomberg Customer Support Representative …". The checker will catch internships when Bloomberg posts them on this same list.

## robots.txt
bloomberg.avature.net has `Allow: /careers` and `Disallow: /careers/*qtvc=`, with a `Disallow: /` catch-all at the end for unlisted portals.

| URL | Verdict | Deciding rule |
|---|---|---|
| https://bloomberg.avature.net/careers/SearchJobs/?jobRecordsPerPage=12&jobOffset=12 | ALLOW | Allow: /careers |
| https://bloomberg.avature.net/careers/JobDetail/2027-Analytics-Sales-Sao-Paulo/45729 | ALLOW | Allow: /careers |
| https://bloomberg.avature.net/careers/sitemap.xml | ALLOW | Allow: /careers |
| https://bloomberg.avature.net/careers/SearchJobs/feed/?jobRecordsPerPage=12 | ALLOW | Allow: /careers (stale, see above) |
| any URL with `qtvc=` | BLOCK | Disallow: /careers/*qtvc= |

## Anti-bot / quirks
- No challenge on bloomberg.avature.net with plain httpx and a browser UA.
- The facet `<select>`s (`1845[]`, `1686[]`, `2562[]`) are filled by JavaScript; their option values do not appear in the HTML. That does not matter, because the checker reads the unfiltered list.
- Titles have no year or term for most experienced roles. Campus programmes start with the cohort year ("2027 …").

## Recommended checker
```yaml
- key: bloomberg
  name: Bloomberg
  adapter: avature
  careers_url: https://bloomberg.avature.net/careers/SearchJobs
  settings:
    list_url: https://bloomberg.avature.net/careers/SearchJobs/
    offset_param: jobOffset
    page_size: 12                     # fixed by the portal; jobRecordsPerPage is ignored
    total_regex: 'list-controls__text__legend"\s+aria-label="(\d+) results"'
    card: 'article.article--result'
    title: 'h3.article__header__text__title a.link'
    location: '.list-item-location'
    id_from_url: '/JobDetail/[^/]+/(\d+)'
    newest_first: true                # default order; read first 2 pages per poll, all 29 once a day
  big: true                           # 29 requests per full scan
```

## Evidence
- Sample: `discovery/samples/bloomberg.html`, the raw SearchJobs page 1 (12 cards, legend, pager; 96 KB).
- Capture: `discovery/captures/bloomberg/` (the bookmark view, which shows 0 results).
- Requests this run: 39 to bloomberg.avature.net. That is 29 list pages, 3 page-size tests, 2 RSS, 2 sitemap, 1 detail, 1 AIResearchInternship and robots.txt.
