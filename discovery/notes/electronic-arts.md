# Electronic Arts (`electronic-arts`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://jobs.ea.com/en_US/careers (`https://jobs.ea.com/` redirects here with a 302) |
| Hiring system | **Avature**. jobs.ea.com is the `ea.avature.net` instance: robots.txt lists `ea.avature.net/<portal>/sitemap_index.xml`, and the page uses Avature markup (`article--result`, `jobOffset`, `jobRecordsPerPage`). The job portal is `careers`. The other portals in robots.txt are campus or event pages (UTAustin, GDC2026, …), `internalcareers`, `agency` and `referrals`, and none of them is a public job list. |
| Recommended adapter | shared `avature` (HTML pager), with EA's card selectors |

## Recommended feed
- **Request:** `GET https://jobs.ea.com/en_US/careers/Home/?jobRecordsPerPage=20&jobOffset={0,20,40,…}`. This is the pager link format on the page.
- **Headers:** a browser UA. No cookies needed. The response is `text/html`, `cache-control: no-store`. Plain httpx got 200 on all 19 pages with no challenge.
- **Pagination:** fixed at **20 per page**. `jobRecordsPerPage=100` still returns 20 cards. Stop when a page has fewer than 20 cards or no new ids. 362 jobs took 19 requests, and the last page had 2.
- **Total:** shown on the page as "1-20 of 362 results" (regex `of\s+([\d,]+)\s+results`). Use it as the health check.
- **Detail:** `https://jobs.ea.com/en_US/careers/JobDetail/<slug>/<id>`
- **Rejected:** `https://jobs.ea.com/en_US/careers/sitemap.xml` is 200 but empty (0 bytes). The sitemap index lists only per-locale sitemaps.

## Field map
Cards are `article.article--result`:

| Job field | Selector | Notes |
|---|---|---|
| id | last path segment of `h3 a.link_result@href` | e.g. 216234. The same number appears as "Role ID 216234". |
| title | `h3 a.link_result` text | collapse whitespace (it has heavy indentation) |
| location | `span.list-item-location` | "Vancouver, Canada", "Austin, United States of America", "Los Angeles - Del Rey, United States of America" |
| url | `h3 a.link_result@href` | `https://jobs.ea.com/en_US/careers/JobDetail/AI-ML-Software-Engineer-Intern-Summer-2027-8-Months-Masters-QVS/216234` |
| employment type | `span.list-item-workerType` | Regular Employee 255, Temporary Employee 52, **Intern - Temporary Employee 42**, Temporary - with Benefits (EU & Malaysia) 13 |
| department | `span.list-item-department` | e.g. "People Experience & Workplaces" |
| posted date | not on the card | The "Sort by … Posted" option exists. I did not check the detail page. |

## Totals (observed 2026-10-19/20)
- **Feed, no filters:** **362** unique ids over 19 pages.
- **Live careers page, no filters:** **362** ("1-20 of 362 results" on page 1). The Playwright capture earlier on 2026-10-19 read "363 results", which is normal churn.
- **By country:** Canada 173, USA 71, China 27, UK 21, Romania 13, Sweden 10, …
- **Intern/student:** **45**. 42 have worker type "Intern - Temporary Employee", and the title rule adds 3 German/Czech "… - Opportunity for Students" temporary roles. Examples:
  - Vancouver Summer 2027 8-month co-ops: Software Engineer Co-op, C++ Gameplay/Generalist SE Co-op, AI/ML SE Intern (Masters), Technical Artist Intern, Animator Co-op
  - Orlando "Software Engineer Intern - SUMMER 2027" ×4
  - Austin Software Engineer Intern, AI Enablement Intern, Data & AI Engineering Intern (Master's)
  - LA Gameplay Engineer Intern
  - UK interns: Guildford, Manchester, Birmingham
  - Stockholm, Hyderabad

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://jobs.ea.com/en_US/careers/Home/?jobRecordsPerPage=20&jobOffset=20 | ALLOW | `Allow: /*/careers` |
| https://jobs.ea.com/en_US/careers/JobDetail/…/216234 | ALLOW | `Allow: /*/careers` |
| https://jobs.ea.com/en_US/careers | ALLOW | `Allow: /*/careers` |
| anything with `qtvc=` | BLOCK | `Disallow: /*/careers/*qtvc=`. Never add Avature's `qtvc` tracking parameter. |

## Anti-bot / quirks
- No challenge in about 22 plain requests.
- This is the same Avature product as Two Sigma but a different skin. EA uses `span.list-item-location` / `list-item-id` / `list-item-workerType` / `list-item-department`, while Two Sigma uses positional `span.paragraph_inner-span`, so the shared adapter needs per-company selectors. EA shows a total; Two Sigma does not.

## Recommended checker
```yaml
- key: electronic-arts
  name: Electronic Arts
  adapter: avature
  settings:
    list_url: https://jobs.ea.com/en_US/careers/Home/?jobRecordsPerPage=20
    offset_param: jobOffset
    page_size: 20                 # fixed
    card: article.article--result
    title: h3 a.link_result
    fields: {location: span.list-item-location, employment_type: span.list-item-workerType, department: span.list-item-department}
    id_from_url: '/(\d+)$'
    total_regex: 'of\s+([\d,]+)\s+results'
  careers_url: https://jobs.ea.com/en_US/careers
```

## Evidence
- Sample: `discovery/samples/electronic-arts.html` is page 1 (offset 0) of the list (227 KB).
- Capture: `discovery/captures/electronic-arts/` ("363 results", server-rendered, no job XHR).
- Requests: 19 list pages, 1 test with page size 100, and 2 sitemaps.
