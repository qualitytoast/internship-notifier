# Shopify (`shopify`)

**Status:** needs-custom (one HTML page embeds every posting as a React Router turbo-stream; there is no public ATS feed)   ·   **Checked:** 2026-10-19 (US Central) = 2026-10-20 00:24–00:26 UTC

| | |
|---|---|
| Official careers URL | https://www.shopify.com/careers. `https://www.shopify.com/careers/search` 301-redirects here. The four big disciplines also have pages: `/careers/disciplines/{engineering-data,design,product,commercial}`. Internships are promoted on https://internships.shopify.com/, a Shopify storefront microsite, but are posted as normal postings on /careers. |
| Hiring system | **Ashby**, used privately. The page data has Ashby job and posting objects (`jobPostingIds`, `customFields`, `interviewPlanIds`) and links of the form `https://www.shopify.com/careers?ashby_jid={postingId}`. The public posting API has no Shopify board: `api.ashbyhq.com/posting-api/job-board/shopify` returns 404. shopify.com renders the jobs itself (Remix / React Router v7). |
| Recommended adapter | `custom:shopify-careers`: one GET of /careers plus a turbo-stream decode |

## Recommended feed
- **Request:** `GET https://www.shopify.com/careers` with a browser UA and `Accept: text/html`. The response is about 585 KB of HTML with no cookies. It never needs the discipline pages: /careers embeds **all** postings (119 here), while the discipline pages embed only their own subsets (engineering-data 50, product 1, commercial 33, design 0).
- **Do not use** `/careers.data` or `/careers/search?q=…`. Both are robots-blocked (`*.data$`, `/careers/search?*`).
- **Decoding the turbo-stream:**
  1. Find `window.__reactRouterContext.streamController.enqueue("…")`. Its argument is a JS string literal; `json.loads` it. There is 1 chunk today.
  2. Split the chunk into lines. The first line is a JSON array `flat`; the root value is `flat[0]`. Later lines starting with `P<n>:` resolve promises and are not needed here.
  3. Decode `val(i)` as follows:
     - A negative `i` is a constant: −5 null, −7 undefined, −1 hole, −2 NaN, −3 −Inf, −6 +Inf, −4 −0.
     - Otherwise look at `v = flat[i]`.
     - If `v` is a dict, its keys look like `"_123"`, where the key name is `flat[123]` and the value is `val(v[key])`.
     - If `v` is a list whose first item is a one-letter uppercase tag (`"D"` date, `"P"` promise, …), it is a typed value.
     - Any other list is `[val(x) for x in v]`.
     - Anything else is a literal.
     - Memoize by index, because objects are shared.
  4. Path: `root.loaderData["($locale)/careers"].jobPostingsWithJobs[]`. Each element is `{jobPosting: {...}, job: {...}}`.
- **Pagination:** none.
- **Detail (optional):** `GET https://www.shopify.com/careers/{slug}_{postingId}` (allowed) is the posting page. A closed posting returns **410** "This posting is no longer available".

## Field map
Paths are relative to `jobPostingsWithJobs[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | `jobPosting.id` | Ashby posting UUID. `jobPosting.jobId` is the Ashby job id. |
| title | `jobPosting.title` | |
| location(s) | `jobPosting.locationName` (primary) + `jobPosting.locationIds.secondaryLocationIds[]` → names via `loaderData["($locale)/careers"].atsLocations[]` (`{id, name, isRemote, workplaceType}`, 37 entries) | e.g. "Americas", "Ireland", "India" + "Singapore". The page shows these as "REMOTE - INDIA, SINGAPORE". `workplaceType` is `Remote` for all 119. `locationExternalName` is null. |
| url (detail/apply) | built: `https://www.shopify.com/careers/{slug}_{id}`, `slug = re.sub('[^a-z0-9]+', '-', ascii(title).lower()).strip('-')` | matched all 68 links seen on the pages. `jobPosting.externalLink` = `https://www.shopify.com/careers?ashby_jid={id}` also works as a link. |
| posted date | `jobPosting.publishedDate` (`2026-10-16`) | `updatedAt` is also present |
| description / snippet | not in the list data | detail page |
| employment type | `jobPosting.employmentType` (`FullTime` for all today) | |
| department / team | `job.customFields[]` where `title == "Discipline"` / `"Subdiscipline"` (`valueLabel`) | Disciplines: Engineering 45, Commercial 33, Growth 6, Finance 6, Support 5, Partnerships 5, Data Insights 5, Legal 4, Creative 4, Communications 2, Design 1, Product 1, Operations 1, Talent Density 1. `departmentName` is just "Shopify". `teamName` is the group shown on the page. |
| status | `jobPosting.status` ("Published"), `jobPosting.isListed` (true) | all 119 are Published and listed |

**Privacy:** `job.hiringTeam` and `job.author` contain Shopify staff details. The checker must not store or email them; keep only the `jobPosting` fields above and the Discipline/Subdiscipline custom fields.

## Totals (observed 2026-10-20 00:24–00:26 UTC)
- **Feed, no filters:** **119** postings (`jobPostingsWithJobs`, unique ids, all Published and isListed). The Playwright render a few minutes later embedded **118**: "Tax Lead, Controversy", published 2026-10-19, had been removed by then.
- **Live careers pages, no filters:** **118** jobs linked across the site, fetched in the same minute as the feed. That is 34 on /careers (the "generalist" groups: Communications, Creative, Finance, Growth, Legal, Operations, Partnerships, Support, Talent Density) + 50 on engineering-data (rendered on the client from its embedded list) + 33 on commercial + 1 on product + 0 on design. All 84 discipline-page postings are among the 119.
  - The only embedded posting not linked anywhere is **"Designers"** (`2e7f4ee3…`, Discipline Design, published 2024-10-07), an evergreen pipeline posting. Keep it; it is listed in Ashby.
- **Intern/student:** **0** today. internships.shopify.com links to "Software Engineering Internships - Winter 2027" (`/careers/software-engineering-internships-winter-2027_404bb82e-…`), which now returns **410 Gone**. When internships reopen they will be ordinary postings in this same list.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://www.shopify.com/careers | ALLOW | no matching rule |
| https://www.shopify.com/careers/disciplines/engineering-data | ALLOW | no matching rule |
| https://www.shopify.com/careers/compliance-lead_d6bd5347-… (detail) | ALLOW | no matching rule |
| https://www.shopify.com/careers/search?q=intern | **BLOCK** | `Disallow: /careers/search?*` |
| https://www.shopify.com/careers.data | **BLOCK** | `Disallow: *.data$` |
| https://internships.shopify.com/ | ALLOW | `Allow: /` |

The internships.shopify.com robots.txt contains free-text "agent instructions". They are irrelevant here and were not followed; the microsite is only informational.

## Anti-bot / quirks
- No challenge on www.shopify.com: 7 requests this run, 7 in the previous run, and 1 Playwright render.
- The page is about 585 KB, so poll it at the normal rate (30–60 min). There is only one request per poll.
- The loader data also holds geo fields (`realCountryCode`, `geoCountryCode`). The posting list was the same between a plain fetch and the browser render, apart from the one removed role, so no geo filtering was seen.
- Ashby's public API might be switched on for Shopify later (`ashby {board: shopify}` currently 404s). Re-probe it occasionally.

## Recommended checker
```yaml
- key: shopify
  name: Shopify
  adapter: custom:shopify-careers
  careers_url: https://www.shopify.com/careers
  settings:
    url: https://www.shopify.com/careers
    stream_marker: 'streamController.enqueue('        # JS string literal → turbo-stream lines
    loader_key: '($locale)/careers'
    list_path: jobPostingsWithJobs[].jobPosting
    locations_path: atsLocations                      # id → name for secondaryLocationIds
    discipline_field: Discipline                      # job.customFields[].title → valueLabel
    job_url: 'https://www.shopify.com/careers/{slug}_{id}'
  health:
    min_jobs: 20                                      # alert if decode finds none (site change)
```

## Evidence
- Sample: `discovery/samples/shopify.json` is a **decoded excerpt**. The raw page is 585 KB, over the 300 KB limit, so the sample holds the first 5 `jobPostingsWithJobs` entries with only the public fields and the Discipline-type custom fields, plus a note on how it was made.
- Capture: `discovery/captures/shopify/` (/careers render).
- Requests this run: 6 (robots, /careers/search → /careers, 4 discipline pages) and 1 Playwright render. The previous run made 7: the Ashby API (404), robots for both hosts, /careers, internships.shopify.com and the 410 intern posting.
