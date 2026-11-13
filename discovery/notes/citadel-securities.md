# Citadel Securities (`citadel-securities`)

**Status:** needs-custom (same WordPress + Cloudflare setup as citadel.com; use the career sitemap)   ·   **Checked:** 2026-10-20 (00:20–00:40 UTC; earlier evidence from 2026-10-19 18:51–18:54 local)

| | |
|---|---|
| Official careers URL | https://www.citadelsecurities.com/careers/open-opportunities/ (unfiltered, "Viewing 10 of 79") |
| Hiring system | In-house WordPress `career` post type, the same theme and on-page "gild" application form as citadel.com. There is no external ATS. Greenhouse probes `citadelsecurities`, `citadel-securities` and `citadel` = 0. |
| Recommended adapter | **`custom:citadel_sitemap`**, the same checker as `citadel` with `base_url: https://www.citadelsecurities.com`. The full parsing spec (XML paths, slug-to-title rule, region hints, health checks) is in `discovery/notes/citadel.md`. |

## Recommended feed
- **Request:** `GET https://www.citadelsecurities.com/career-sitemap.xml`. Plain HTTP, browser UA, returns **200** `text/xml` (Yoast SEO). It is listed in `/sitemap_index.xml`, together with post, page, leadership, category, series and career-perspectives sitemaps.
- Unlike citadel.com's, this sitemap has no `xhtml:link` alternates. Each entry is just `<loc>` + `<lastmod>`.
- **Detail URL pattern:** `^https://www\.citadelsecurities\.com/careers/details/([a-z0-9-]+)/?$`. id = slug, url = `<loc>`.
- **Pacing:** 1 request per run. Keep at least 10 s between requests to this host (`Crawl-delay: 10`, see robots below).

## What plain HTTP can reach (do not evade the rest)
| URL | Plain HTTP result |
|---|---|
| `/sitemap_index.xml` | **200** (2026-10-19) |
| `/career-sitemap.xml` | **200** (2026-10-19 and 2026-10-20) |
| `/robots.txt` | **403 Cloudflare interactive challenge** (`cType: 'interactive'`, 2026-10-19) |
| `/careers/details/software-engineer-intern-asia/` | **403 interactive challenge** (2026-10-20) |

The listing page, wp-json and admin-ajax were not tried over plain HTTP here. On the sister site they are challenged, so assume the same. Headless Chromium (no stealth) loads the listing page normally; that was used only to read the page total.

## Field map
Same as `citadel`: id = slug, title derived from slug, location = slug region hint, url = `<loc>`. There is no posted date: `lastmod` is rewritten for all URLs on every sync (2026-10-19T23:22Z for all on 2026-10-19, and 2026-10-20T00Z for all today).
- Duplicate-slug posts exist here: `c-software-engineer` and `c-software-engineer-2`, `site-reliability-engineer` and `site-reliability-engineer-2`, `quantitative-research-analyst-intern-bs-ms-europe` and `…-europe-2`. They are distinct jobs (different posts and locations) with identical titles. Keep both ids and strip only `-2` from the derived title.
- A lone `c` token means "C++": `c-market-data-engineer`, `rates-credit-c-engineer`, `c-software-engineer`.
- Region hints today: 15 United States, 11 Europe, 9 Asia, 2 Australia, 1 EMEA, 1 New York, 40 none.

## Totals (observed)
- **Feed, no filters:** **79** URLs, 79 unique slugs (sitemap on 2026-10-19 and again 2026-10-20).
- **Live careers page, no filters:** **79**. A Playwright render of `/careers/open-opportunities/` on 2026-10-20 showed "Viewing 10 of 79", and the 2026-10-19 capture showed the same. The page-1 cards (e.g. "UI Engineer (Contractor)", "Software Engineer – Intern (Asia)") are all in the sitemap.
- **Intern/student:** **23**. The title regex on derived titles gives 23, and the site's own Internships filter (`?experience-filter=internships&selected-job-sections=323,325,324,326&…`) showed "Opportunities (23)" (Playwright, 2026-10-19).
  - US hint (9): designated-market-maker-dmm-trader, fpga-engineer, machine-learning-researcher-phd, quantitative-research-engineer-phd, quantitative-researcher-phd, quantitative-researcher-post-doctoral, quantitative-trader, software-engineer, trading-fundamental-analyst (each `…-intern-us`).
  - Australia (2): quantitative-research-analyst-intern-bs-ms-australia, quantitative-research-phd-intern-australia.
  - The other 12 are Europe or Asia.

## robots.txt
Plain HTTP gets a 403 challenge page instead of robots.txt. Under RFC 9309 a 4xx means "unavailable" and crawling is allowed; the project matcher reports "no robots.txt (allowed)". The real file, seen in a browser on 2026-10-19, is identical to citadel.com's: `Crawl-delay: 10` / `User-agent: *` / `Disallow: /cdn-cgi/` / `Sitemap:` lines for both sites. So the sitemap is allowed either way, and citadel.com's robots.txt also points crawlers at `https://www.citadelsecurities.com/sitemap_index.xml`.

| URL | Verdict | Deciding rule |
|---|---|---|
| https://www.citadelsecurities.com/career-sitemap.xml | ALLOW | matcher: no robots.txt (403) → allowed; real file: no matching rule |
| https://www.citadelsecurities.com/sitemap_index.xml | ALLOW | same |
| https://www.citadelsecurities.com/careers/details/… | ALLOW by robots | Cloudflare-challenged for plain HTTP, do not fetch |

## Anti-bot / quirks
- Cloudflare challenges plain HTTP everywhere except the sitemaps and static assets. The checker must treat a 403 / `cf-mitigated: challenge` on the sitemap as "blocked", alert, and back off. Never work around it.
- The job list and the internship counts behave exactly like citadel.com (see that note).

## Recommended checker
```yaml
- key: citadel-securities
  name: Citadel Securities
  adapter: custom:citadel_sitemap        # spec in discovery/notes/citadel.md
  careers_url: https://www.citadelsecurities.com/careers/open-opportunities/
  settings:
    base_url: https://www.citadelsecurities.com
    sitemap: /career-sitemap.xml
    detail_prefix: /careers/details/
    min_interval_s: 10
    title_from: slug
    location_from: slug_region_hint
    posted_from: first_seen
  health: {expect: {status: 200, content_type: xml, root: urlset}, alert_on_challenge: true, min_jobs: 1, max_drop_ratio: 0.5}
```

## Programs (`citadel-securities-programs`, added 2026-11-07)
The student programs (Discover Citadel Securities, Ignite, and Spark, new on 2026-11-06) are never `career` posts.
They live under `/careers/programs-and-events/<program>/`. The pages are challenged, but `/page-sitemap.xml` answers
plain HTTP (200, the same as the career sitemap) and lists every page with a real per-page `<lastmod>`: on 2026-11-07
the dates ran from 2025-04-10 to 2026-11-06. Unlike the career sitemap, these are not rewritten on every sync.
- **Open = a page below the program page.** On 2026-11-07, Discover had `apply/` (US), `emea-apply/`, `apply-india/`,
  `hong-kong/` and `singapore/`. PhD Summit, the Quant Invitational, Datathons and the Conference Travel Grant each
  had an apply page, and Spark had `apply/`. Ignite, closed on Oct 16, had no page below it any more (lastmod Oct 16
  20:50).
- Checker `citadel_programs`: id `<program>/<page>`, title from the program slug, region from the page slug
  (`apply-india` → India, `emea-apply` → EMEA), url = that page, posted = its lastmod. 11 roles that day.
  `role_keywords: [discover citadel, ignite, spark]` on this entry only: Spark and Discover's US page match (tagged
  freshman/sophomore, location?); the regional pages fail the location rule, and the events fail the role rule.
- moves.py N still reports new program pages (`liveness.program_pages`), which is how Spark was found.

## Evidence
- Sample: `discovery/samples/citadel-securities.json`. It has the raw sitemap (whole), the parsed rows, and page-1 cards compared with derived titles.
- Capture: `discovery/captures/citadel-securities/` ("of 79").

## 2026-11-13: the site was rebuilt, and its new sitemaps refuse scripts
- Between the reads of Nov 12 13:46 UTC and Nov 13 14:19 UTC both sites went from WordPress to Next.js (content from
  Sanity). `/career-sitemap.xml`, `/page-sitemap.xml`, `/sitemap_index.xml` and `/wp-sitemap.xml` answer **404** (the
  site's own not-found page, not challenged).
- citadel.com's robots.txt (200, the same rules) now names `Sitemap: https://www.citadel.com/sitemap.xml` and
  `https://www.citadelsecurities.com/sitemap.xml`. `/sitemap.xml` answers plain HTTP (**200**, a `sitemapindex` of
  `/sitemap/page.xml`, `post.xml`, `career.xml`, `leadership.xml`, `category.xml`, `series.xml` and
  `career-perspectives.xml`, with no lastmod).
- `/sitemap/career.xml` and `/sitemap/page.xml` answer plain HTTP with **403** `cf-mitigated: challenge` on both
  sites (all 11 tries across the four addresses, 16:08 to 16:33 UTC, 10 s apart), as `/careers/open-opportunities/`
  does (2 of 2 on each site).
  `/sitemap.xml` answered 200 before and after, so the challenge goes by address, not by who asks.
- Seen in a browser that day, the new sitemaps have the old format: the same `urlset` (plus an `xmlns:xhtml`
  attribute), `<loc>` and `<lastmod>` (now with milliseconds), and every job and page kept its address.
- citadelsecurities.com `/sitemap/page.xml`: 13 pages below a program page, the 13 stored for
  `citadel-securities-programs`. Its `/sitemap/career.xml` was not looked at; citadel.com's had 66 entries,
  all `/careers/details/<slug>/`, each a job already stored under that id.
- The checkers ask the new addresses since then (one request each a run) and fail with HTTP 403 until Citadel lets
  scripts read them. The challenge is not worked around. While a checker fails, SimplifyJobs' rows for the company
  are emailed "via Simplify"; nothing stands in for the program pages.
