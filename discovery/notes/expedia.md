# Expedia Group (`expedia`)

**Status:** verified-feed (Workday)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://careers.expediagroup.com/jobs/. This is a WordPress copy of the job list behind Cloudflare. The bookmark adds `?keyword=intern&filter[…]=`. |
| Hiring system | **Workday**, tenant `expedia` on **`wd108`**, one public site **`search`**. Its `robots.txt` lists only `Allow: /search/`, plus the sitemap `/search/siteMap.xml`. Every "Apply Now" on the careers site goes to `https://expedia.wd108.myworkdayjobs.com/search/job/<loc>/<slug>_R-…/apply`. Some footer links still point to the old `expedia.wd5.myworkdayjobs.com/en-US/search/login`. |
| Recommended adapter | shared **`workday`**, settings `{host: expedia.wd108.myworkdayjobs.com, tenant: expedia, site: search}` |

## Recommended feed
- `POST https://expedia.wd108.myworkdayjobs.com/wday/cxs/expedia/search/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`. That is 9 pages today; `total` (173) is on the first page.
- This is far below the CXS 2000 cap.
- Do **not** use careers.expediagroup.com:
  - plain httpx gets **HTTP 403** "Just a moment…" (a Cloudflare challenge);
  - robots.txt sets **Crawl-delay: 10**;
  - its "Load More Jobs" button calls `GET /calc-results/?&mypage=N&ctok=…`, which is **`Disallow: /calc-results/`**;
  - it is a delayed per-location copy of Workday (see Totals).

## Field map
Standard Workday CXS (see the `workday` adapter): `title`, `externalPath`, `locationsText` ("3 Locations"), `postedOn` (relative) and `bulletFields[0]` = req id (`R-110306`).
- A suffixed `externalPath` (`…_R-107932-1`, `…_R-110671-2`) is a second posting of the same requisition.
- Job URL: `https://expedia.wd108.myworkdayjobs.com/en-US/search<externalPath>`.
- The careers-site equivalent is `https://careers.expediagroup.com/job/<slug>/<city-st>/<R-id>/`. It has one URL per *location*: the second location of R-104546 is `/R-104546-1/`. Use it only as a link.

## Totals (observed 2026-10-20 00:35–00:55 UTC)
- **Feed, no filters:** **173**. CXS `total` was 173, and 9 pages gave 173 unique postings. Facets: `workerSubType` Regular 166, Intern (Fixed Term) 5, Fixed Term 2. `jobFamilyGroup` Technology 111, Finance 18, ….
- **Live page, no filters:** **173**. A Playwright render of https://expedia.wd108.myworkdayjobs.com/en-US/search showed "173 JOBS FOUND" and "1 - 20 of 173 jobs".
- **careers.expediagroup.com:** a Playwright render showed "**215 positions** in all locations" (25 cards per page, `numpages = 9`). The gap is explained by how the site counts:
  - It shows **one card per job location**. Summed over the 173 Workday postings, the locations come to **214**. R-104546 "Software Development Engineer III, Advertising Technology" is one Workday posting with 2 locations and two cards there (Seattle `R-104546-1`, Chicago `R-104546`).
  - It is a **delayed copy**. It still lists **R-110311** "Software Development Engineering Intern - 2027 - Austin, San Jose, Seattle", but Workday CXS has no such posting: `searchText` "R-110311" returns 0, and the detail path `…_R-110311-1` returns **404**. Meanwhile 12 Workday postings are "Posted Today" and may not have synced yet.
  - Cross-check on the bookmark: the careers site's `keyword=intern` view showed "14 positions". The 5 Workday internships have 1+3+1+3+3 = 11 locations, and stale R-110311 adds 3 (Austin, San Jose, Seattle), so 11 + 3 = 14.
  - Of the 89 distinct requisitions I saw on the careers site, 87 are on Workday. The other two are R-110311 (closed) and R-109783.
- **Intern/student:** **5**. The title regex finds 5, matching workerSubType Intern (Fixed Term) 5. All were posted 7 days ago:
  - R-110310 Security Engineering Intern - 2027 - Seattle
  - R-110306 Mobile Engineering Intern - 2027 - Austin, San Jose, Seattle
  - R-110305 Finance Analyst Intern - 2027 - Seattle
  - R-110382 Applied Science Intern - PhD - 2027 - Austin, San Jose, Seattle
  - R-110379 Applied Science Intern - Masters - 2027 - Austin, San Jose, Seattle

  The SWE intern posting R-110311 is no longer on Workday.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `https://expedia.wd108.myworkdayjobs.com/wday/cxs/expedia/search/jobs` | ALLOW | no matching rule (only `/private/` and `/refreshFacet/` are disallowed) |
| `https://expedia.wd108.myworkdayjobs.com/en-US/search`, `/search/…` | ALLOW | `Allow: /search/` |
| `https://careers.expediagroup.com/jobs/`, `/job/…` | ALLOW | `Allow: /`, but with `Crawl-delay: 10`, and Cloudflare challenges httpx |
| `https://careers.expediagroup.com/calc-results/?&mypage=N…` | **BLOCK** | `Disallow: /calc-results/` |

## Anti-bot / quirks
- careers.expediagroup.com is behind a Cloudflare challenge: httpx gets 403 "Just a moment…", while a normal Chromium render passes. The checker never needs it.
- **Disclosure:** to read every card on the careers site, I automated its "Load More Jobs" button 4 times in Playwright. The page's own JS then made 8 GETs to `/calc-results/`, which is robots-disallowed. I did not check that endpoint before clicking, and I stopped once I saw it. The checker must never call it, and nothing in this recommendation depends on it.
- Workday `postedOn` is relative. Multi-location postings show "N Locations" in the list; the detail call gives `additionalLocations`.

## Recommended checker
```yaml
- key: expedia
  name: Expedia Group
  adapter: workday
  careers_url: https://careers.expediagroup.com/jobs/
  settings:
    host: expedia.wd108.myworkdayjobs.com
    tenant: expedia
    site: search
```

## Evidence
- Sample: `discovery/samples/expedia.json` is the raw Workday CXS first page (offset 0) with facets, 12 KB.
- Capture: `discovery/captures/expedia/` (bookmark `keyword=intern`, "14 positions").
- Requests:
  - Workday wd108: 14 (CXS 10 pages, 3 searchText probes, 1 detail).
  - careers.expediagroup.com: 1 httpx GET (403).
  - 4 Playwright sessions: the jobs page, the Load-More run (see disclosure), one job page, and the Workday site page.
