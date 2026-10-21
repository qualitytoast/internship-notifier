# Synopsys (`synopsys`)

**Status:** verified-feed (Avature HTML list; big site)   ·   **Checked:** 2026-10-19 (US Central) = 2026-10-20 00:21–00:29 UTC

| | |
|---|---|
| Official careers URL | https://careers.synopsys.com/search-jobs. The bookmark `https://careers.synopsys.com/category/interns-temp-jobs/44408/8675664/1` is the "Interns/Temp" category, a filtered view with 5 jobs. |
| Hiring system | **Avature** (`synopsys.avature.net`, portal `careers`, page title "Job Search \| Synopsys"). careers.synopsys.com is a **Radancy (TalentBrew)** front-end that mirrors it. Its Apply buttons go to `https://synopsys.avature.net/careers/Login?jobId={avatureId}`. |
| Recommended adapter | shared **`avature`** adapter on the Avature portal: `{list_url: https://synopsys.avature.net/careers/SearchJobs/, page_size: 6}`, marked `big` (newest-first pages each poll, full scan daily) |

## Recommended feed (Avature list pager)
- **Request:** `GET https://synopsys.avature.net/careers/SearchJobs/?jobOffset={0,6,12,…}`. The response is HTML of about 91 KB.
- **Headers:** a normal browser UA, `Accept: text/html`. No cookies or tokens, and there was no challenge.
- **Page size is fixed at 6.** `jobRecordsPerPage=100` was ignored and still returned 6 cards, "1-6 of 639". A full scan is therefore **107 requests** (about 2 minutes at 1 request/second). The last page, `jobOffset=636`, returned 3 cards with the legend "637-639 of 639".
- **Total:** `<div class="list-controls__text__legend" aria-label="639 results"> 1-6 of 639 results </div>`. This is the same markup as Bloomberg.
- **Default order:** by title, descending (Z → A). Page 1 starts with "ZeBu Application Engineer" and the last page ends with "Academic/Outreach, Sr Associate". The order is stable, but new jobs land anywhere in it.
- **Newest first:** `GET https://synopsys.avature.net/careers/SearchJobs/?jobSort=postedDate&jobSortDirection=DESC&jobOffset=N`. These are the form's hidden fields; they work as GET parameters. Page 1 then lists the 19-Oct, 19-Oct and 16-Oct postings. One 08-Jul-2026 job was listed first, so the order is not strictly by date. Read 2–3 pages per poll and dedupe by id; run the full default-order scan daily to catch everything.
- **Detail (needed for location):** `GET https://synopsys.avature.net/careers/JobDetail/{slug}/{id}` (about 44 KB, no JSON-LD). Fields are `.article__content__view__field` label/value pairs. Example (19195):
  - Job Title: Analog Design Internship - Summer 2027
  - Job ID: 19195
  - Country: Canada; City: Mississauga; State/Province
  - Date Posted: 07-Oct-2026
  - Job Category: Interns/Temp
  - Job Subcategory: Intern (Technical-Engineering)
  - **Hire Type: Intern**
  - Remote Eligible: No
  - Job Description and Requirements

### Other sources (checked; cross-checks only)
- **Avature sitemap** `GET https://synopsys.avature.net/careers/sitemap.xml` (194 KB) lists **639 unique JobDetail URLs** with `<lastmod>`, equal to the live total. Its slugs are *requisition* titles (`Intern-Technical-Engineering-19195`), not the shown title. It costs one request, so it works as a daily completeness check.
- **Radancy sitemap** `GET https://careers.synopsys.com/sitemap.xml` (359 KB) lists **638** `/job/{city}/{business-title-slug}/44408/{radancyId}` URLs. That is equal to the Radancy search count, and the file was regenerated recently (lastmod 2026-10-19T23:32Z). It is one job behind Avature.
- **Radancy search** `GET https://careers.synopsys.com/search-jobs` shows 15 jobs per page across 43 pages, and each page is **1.27 MB**. Its paging AJAX `/search-jobs/results?…` is **robots-blocked**. Do not use it.
- **Avature RSS** `/careers/SearchJobs/feed/?jobRecordsPerPage=6` is linked from the page. It was not re-tested here; on the Bloomberg and Two Sigma portals the RSS always returns the same 20 oldest items.

## Field map (Avature cards)
Card selector: `article.article--result`.

| Job field | Response path | Notes |
|---|---|---|
| id | `span.list-item-jobId` ("Job ID 18605"), or the number before `?` in the link | Avature id. Radancy ids (e.g. 102054577920) are different; 76 of 77 Radancy slugs that end in a number end in the Avature id. |
| title | `h3.article__header__text__title a.link` text | this is the **business title** (e.g. "ZeBu Application Engineer"). The link slug is the requisition title (`Applications-Engineering-Sr-Engineer`), and the title is repeated in `?businessTitle=`. |
| location(s) | **not on the card** | the detail has `City`, `State/Province` and `Country`. Fetch the detail only for new student-looking jobs (`detail_fetch_limit` 40). The Radancy sitemap path also has the city slug. |
| url (detail) | `a.link@href` | `https://synopsys.avature.net/careers/JobDetail/{reqSlug}/{id}?businessTitle=…`. The Apply button goes to `/careers/Login?jobId={id}`, a login form; do not fetch it. |
| posted date | `span.list-item-posted` ("Posted 02-Sep-2026") | format `%d-%b-%Y` |
| description / snippet | detail only | |
| employment type | `span.list-item-hireType` (`Employee`, `Intern`, …) | a reliable student marker together with the title |
| department / team | detail `Job Category` / `Job Subcategory` | e.g. Interns/Temp → Intern (Technical-Engineering) |

## Totals (observed 2026-10-20 00:21–00:29 UTC)
- **Feed, no filters:** **639**. This is the Avature legend `aria-label="639 results"`. The last page (offset 636) holds jobs 637–639, and the Avature sitemap has 639 unique ids. I did **not** walk all 107 pages, to keep within the request budget; Bloomberg's 29-page walk on the same Avature engine matched its legend exactly.
- **Live careers page, no filters:** **638**. The server-rendered https://careers.synopsys.com/search-jobs says "638 results" (`data-total-job-results="638"`; `data-total-results` is 668, the visible text is 638). The Radancy sitemap also has 638. The ±1 is mirror lag.
- **Intern/student:** **5**. The same 5 appear in the bookmark category (Interns/Temp, "5 results"), among the Radancy sitemap slugs, and among the Avature sitemap slugs:
  - 19195 Analog Design Internship - Summer 2027 (Mississauga; confirmed on the detail page)
  - Software Development and Optimization Internship (Villeurbanne)
  - Digital Design Engineer Apprenticeship (Noida)
  - ASIC Physical Design Intern (Yerevan)
  - R&D Engineering Intern (Dublin)

  The Avature sitemap has exactly 5 student-like slugs: 18414 `Intern-Technical-Engineering`, 19195, 19228 `Apprentice-Technical-Engineer`, 19287 `ASIC-Physical-Design-Internship-AM` and 19289 `R-D-Engineering-Intern-IE`. Only 19195 was matched to its Radancy job; the other pairings are inferred from the slugs (AM = Armenia, IE = Ireland).

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://synopsys.avature.net/careers/SearchJobs/?jobOffset=6 | ALLOW | Allow: /careers |
| https://synopsys.avature.net/careers/SearchJobs/?jobSort=postedDate&jobSortDirection=DESC&jobOffset=6 | ALLOW | Allow: /careers |
| https://synopsys.avature.net/careers/JobDetail/Intern-Technical-Engineering-19195/19195 | ALLOW | Allow: /careers |
| https://synopsys.avature.net/careers/sitemap.xml | ALLOW | Allow: /careers |
| https://careers.synopsys.com/search-jobs and `/job/…`, `/sitemap.xml` | ALLOW | no matching rule |
| https://careers.synopsys.com/search-jobs/results?… | **BLOCK** | `Disallow:/search-jobs/` |
| any Avature URL with `qtvc=` | BLOCK | Disallow: /careers/*qtvc= |

synopsys.avature.net also allows `/GlobalEarlyCareersSummerInternship` and `/GlobalEarlyCareersIndustrialPlacements`, which are Avature portals. Neither is linked from the careers site, and the only job list is `/careers`.

## Anti-bot / quirks
- No challenge on either host (11 requests). The Radancy pages are huge (1.27 MB) because they embed facets; avoid them.
- The card title and the URL slug differ (business title vs requisition title). Always display the card or detail title.
- Two Synopsys numbering systems exist: Avature ids (5 digits) are canonical, and Radancy ids (12 digits) are only used on careers.synopsys.com.

## Recommended checker
```yaml
- key: synopsys
  name: Synopsys
  adapter: avature
  careers_url: https://careers.synopsys.com/search-jobs
  big: true                              # 107 requests per full scan → newest-first each poll, full daily
  settings:
    list_url: https://synopsys.avature.net/careers/SearchJobs/
    offset_param: jobOffset
    page_size: 6                         # fixed by the portal
    newest_first_query: jobSort=postedDate&jobSortDirection=DESC   # 2-3 pages per poll
    total_regex: 'list-controls__text__legend"\s+aria-label="(\d+) results"'
    card: 'article.article--result'
    title: 'h3.article__header__text__title a.link'
    fields: {job_id: '.list-item-jobId', employment_type: '.list-item-hireType', posted: '.list-item-posted'}
    id_from_url: '/JobDetail/[^/]+/(\d+)'
    detail_for_location: true            # City/Country from JobDetail, only for new student-like jobs
  # optional daily completeness check: ids in https://synopsys.avature.net/careers/sitemap.xml
```

## Evidence
- Sample: `discovery/samples/synopsys.html`, the raw Avature SearchJobs page 1 (6 cards, legend "639 results", sort form; 91 KB).
- Capture: `discovery/captures/synopsys/` (the bookmark category page, 5 jobs).
- Requests this run: 11. They were Avature list ×4 (default, `jobRecordsPerPage=100`, sorted, offset 636), 1 detail, 2 Avature sitemap, Radancy search and sitemap, and robots.txt.
