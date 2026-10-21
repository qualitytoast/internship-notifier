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

## Evidence
- Sample: `discovery/samples/citadel-securities.json`. It has the raw sitemap (whole), the parsed rows, and page-1 cards compared with derived titles.
- Capture: `discovery/captures/citadel-securities/` ("of 79").
