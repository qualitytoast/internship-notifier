# Two Sigma (`two-sigma`)

**Status:** needs-custom (no complete machine-readable feed; Avature HTML list, server-rendered)   ·   **Checked:** 2026-10-19

| | |
|---|---|
| Official careers URL | https://careers.twosigma.com/careers/OpenRoles (the "Open Roles" link in the careers portal nav and on www.twosigma.com/careers/). Student subset: https://careers.twosigma.com/careers/InternshipsAndEarlyCareers. The old bookmark `/careers/SearchJobs` now returns 404 because the Avature list page was renamed to `OpenRoles`. |
| Hiring system | Avature (careers.twosigma.com is the `twosigma.avature.net` portal; its robots.txt lists twosigma.avature.net sitemaps, and the page uses Avature markup: `article--result`, `jobOffset`, `avature.portal.*` form fields) |
| Recommended adapter | Avature HTML list pager (a shared `avature` adapter could also cover Bloomberg's bloomberg.avature.net) |

## Recommended feed
- **Request:** `GET https://careers.twosigma.com/careers/OpenRoles/?jobOffset={0,10,20,…}`. Leave out `jobOffset` (or send 0) for the first page.
- **Headers:** a normal browser User-Agent. No cookies or tokens needed. Responses are `text/html` with `cache-control: no-store`.
- **Pagination:** page size is fixed at **10**. `jobRecordsPerPage=50/100` is ignored, with or without `listFilterMode=1`. Add 10 to `jobOffset` until a page has fewer than 10 cards or no new ids. 63 jobs took 7 requests. The page shows no total, only page links ("Page 1 2 3 Next >>").
- **Detail endpoint (optional):** the job URL itself (`/careers/JobDetail/<slug>/<id>`). The HTML has the "Position Summary" text and Location / Business / Function / Experience Level fields. There is **no JSON-LD and no posted date**.

### Sources checked and rejected
- RSS `GET /careers/OpenRoles/feed/?jobRecordsPerPage=N` (linked from the page) always returns the **same 20 items**: the oldest by pubDate, from 2024-11-27 to 2026-02-25. It ignores `jobOffset`, page sizes above 20 and `jobSortDirection=DESC`. It misses every posting since Feb 2026, including all 2027 internships, so it is **unusable**.
- `GET /careers/SearchJobsData/?jobRecordsPerPage=100&jobOffset=0` (the map-data URL in the page config) returns an empty body (Google Maps is disabled).
- `careers/sitemap.xml` lists only portal pages, with no JobDetail URLs.
- A Greenhouse/Lever/Ashby probe of obvious tokens found nothing (discovery/probe_results.json).
- A Playwright render of OpenRoles made no XHR/fetch job requests: the list is fully server-rendered.

## Field map
Cards: `article.article--result` (the regex `<article class="article article--result"(.*?)</article>` works).

| Job field | Response path | Notes |
|---|---|---|
| id | last path segment of the card link (`…/JobDetail/<slug>/14096`) | numeric Avature job id, stable |
| title | `h3.article__header__text__title > a.link` text | |
| location(s) | 1st `span.paragraph_inner-span` in `.article__header__content__text` | e.g. `United States - NY New York`, `United Kingdom - UK London`, `Japan - Tokyo` (one per card) |
| url (detail/apply) | `h3 … a.link@href` | `https://careers.twosigma.com/careers/JobDetail/<slug>/<id>`; the Apply button is on the detail page |
| posted date | not available | only the broken RSS has pubDate |
| description / snippet | detail page body (`Position Summary …`) | not on the list |
| employment type | 3rd span (Experience Level): `Internship` / `Early Careers` / `Experienced` | reliable student marker |
| department / team | 2nd span (Function): `Engineering`, `Quantitative Research`, `Strategy and Operations`, `Investment and Client Solutions`, `Data Science` | the Business field is only on the detail page |

## Totals (observed 2026-10-19)
- **Feed (HTML pager), no filters:** **63** unique jobs (offsets 0–60, 7 requests, last page 3 cards).
- **Live careers page, no filters:** **63**. The page shows no total, so this is the cards counted across all pages, rendered server-side and checked with a Playwright render of page 1 (same 10 cards, no XHR).
- **By location:** 52 New York, 5 London, 5 Tokyo, 1 Houston. **By level:** 53 Experienced, 6 Early Careers, 4 Internship.
- **Intern/student:** **4**, all New York, Experience Level = Internship:
  - 14096 AI Research Scientist - Intern [2027 Summer]
  - 13945 Quantitative Researcher - Intern [2027 Summer]
  - 14016 Software Engineering Internship (Summer 2027)
  - 14289 TSS Hardware Engineering Internship (Summer 2027)
  
  There are also 6 "Early Careers" campus full-time roles. The InternshipsAndEarlyCareers page lists exactly these 10, and all of them are also in OpenRoles.

## robots.txt
careers.twosigma.com: `User-agent: *` with `Allow: /careers` and `Disallow: /careers/*qtvc=`. There is no crawl-delay.

| URL | Verdict | Deciding rule |
|---|---|---|
| https://careers.twosigma.com/careers/OpenRoles | ALLOW | Allow: /careers |
| https://careers.twosigma.com/careers/OpenRoles/?jobOffset=10 | ALLOW | Allow: /careers |
| https://careers.twosigma.com/careers/JobDetail/…/14096 | ALLOW | Allow: /careers |
| https://careers.twosigma.com/careers/OpenRoles/feed/?jobRecordsPerPage=20 | ALLOW | Allow: /careers (but incomplete, see above) |
| https://www.twosigma.com/careers/ | ALLOW | no matching rule. Its robots.txt has a stray `Crawl-delay: 10` before any group. |

## Anti-bot / quirks
- **www.twosigma.com** (marketing site) sends non-browser clients a Cloudflare managed challenge (HTTP 403 "Just a moment…"). The checker does not need it.
- **careers.twosigma.com** (Avature) did not challenge plain httpx with a browser UA in about 20 requests.
- Do not add `qtvc=` (an Avature tracking param) to URLs; robots.txt disallows it.
- The location text can contain odd whitespace or newlines (e.g. `United States New York\t…\nNy` in the RSS). Collapse whitespace.

## Recommended checker
```yaml
- key: two-sigma
  name: Two Sigma
  adapter: avature_html          # custom/shared HTML pager
  settings:
    list_url: https://careers.twosigma.com/careers/OpenRoles/
    offset_param: jobOffset
    page_size: 10                # fixed; jobRecordsPerPage ignored
    max_pages: 20
    card: 'article.article--result'
    title: 'h3.article__header__text__title a.link'
    fields: [location, department, employment_type]   # the 3 span.paragraph_inner-span, in order
    id_from_url: '/(\d+)$'
  # detail fetch only for new student-looking ids (description for term/field detection)
```

## Evidence
- Sample: `discovery/samples/two-sigma.html` (raw OpenRoles page 1, 110 KB)
- Old capture: discovery/captures/two-sigma (404 on /careers/SearchJobs/)
