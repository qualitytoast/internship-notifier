# Citadel (`citadel`)

**Status:** needs-custom (WordPress site behind Cloudflare; the only list reachable over plain HTTP is the Yoast career sitemap)   ·   **Checked:** 2026-10-20 (00:20–00:40 UTC; earlier evidence from 2026-10-19 18:35–18:55 local)

| | |
|---|---|
| Official careers URL | https://www.citadel.com/careers/open-opportunities/ (unfiltered list, "Viewing 10 of 63"). The student link `/careers/open-opportunities/students/` returns 301 to the same list filtered to `experience-filter=internships,new-graduates` (43 of 63), so it is a subset. |
| Hiring system | In-house. The site is WordPress (custom post type `career`, detail URLs `/careers/details/<slug>/`). Applications go through an on-page "gild" form (`action=gild`, hidden `job_id` UUID, `career_post_id` WordPress id, Cloudflare Turnstile). There is no external ATS link (no Greenhouse, Workday, Lever, etc.). The Greenhouse probe `citadel` = 0. |
| Recommended adapter | **`custom:citadel_sitemap`**, one checker shared with `citadel-securities` (settings differ only in `base_url`). |

## Recommended feed
- **Request:** `GET https://www.citadel.com/career-sitemap.xml`
  - Headers: normal browser UA only. No cookies. Plain httpx gets **HTTP 200** `text/xml; charset=UTF-8`, `cache-control: max-age=600, must-revalidate`, `x-robots-tag: noindex, follow`, Cloudflare `cf-cache-status: DYNAMIC`. Not challenged in 4 requests across two days.
  - The file is Yoast SEO's sitemap for the `career` post type and is listed in `https://www.citadel.com/sitemap_index.xml`. robots.txt advertises that index (`Sitemap:` line), so it is meant for crawlers.
- **Pagination:** none today (one file, 63 URLs). Yoast splits a post type at 1000 URLs into `career-sitemap2.xml`, `career-sitemap3.xml`, … If `career-sitemap.xml` has exactly 1000 `<url>`, also read the next numbered file (or read `sitemap_index.xml` and take every `<loc>` matching `/career-sitemap\d*\.xml$`).
- **Pacing:** robots.txt has `Crawl-delay: 10`. It sits before the first `User-agent` line, so the project's RFC 9309 parser ignores it, but honour it anyway: at least 10 s between requests to this host. The checker needs 1 request per run.
- **Detail endpoint:** none usable. Detail pages answer plain HTTP with **403 "Just a moment…"** (`cf-mitigated: challenge`, `cType: 'interactive'`). Do not fetch them and do not try to get past the challenge. Use the detail URL only as the link in emails (it opens fine in a person's browser).

### Parsing (exact)
```python
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
DETAIL = re.compile(r"^https://www\.citadel\.com/careers/details/([a-z0-9-]+)/?$")   # base_url-specific
DUP = re.compile(r"-([2-9]|[1-9]\d)$")      # WordPress duplicate-slug suffix -2..-99; never matches a 4-digit year
for u in ET.fromstring(body).findall("s:url", NS):
    loc = u.findtext("s:loc", namespaces=NS).strip()
    m = DETAIL.match(loc)
    if not m: continue                       # (today every <loc> matches)
    slug = m.group(1)
    job = Job(id=slug, url=loc, title=title_from_slug(slug), location=region_hint(slug),
              posted=None)                    # lastmod is NOT a posting date (see below); use first-seen
```
- `title_from_slug`: drop the `DUP` suffix, split on `-`, capitalise each word. Keep small words (`and of for the in to a an on with or`) lower-case except the first. Upper-case known tokens: `us uk emea apac bs ms ui ux it hr ai ml fx etf ces gqs fpga sre otc llm api vp pm dmm mba kdb sdet`, and `phd → PhD`.
  - **Do not strip a trailing year:** `equities-citadel-associate-program-summer-internship-2028` → "Equities Citadel Associate Program Summer Internship 2028". (An earlier version used `-\d+$` and lost the 2028.)
  - The suffix rule matters on the sister site: `c-software-engineer` and `c-software-engineer-2` are two different posts with the same title. Keep both as separate jobs (ids differ). Only the title loses the `-2`.
- `region_hint` (optional, recommended): map the last slug token(s) to a location so the US filter has something to work with. `us → "United States"`, `europe → "Europe"`, `asia → "Asia"`, `emea → "EMEA"`, `apac → "APAC"`, `australia → "Australia"`, `americas → "Americas"`, plus city tokens `new-york, london, hong-kong, singapore, miami, chicago, greenwich, houston, sydney, tokyo, dublin, zurich, paris, amsterdam`, and a leading `us-` token. Otherwise use `""`, which filters.yaml treats as unknown, so the job is included as unsure. Citadel today: 20 United States, 10 Europe, 10 Asia, 2 EMEA, 1 New York, 20 no hint.
- Derived titles lose punctuation and case. Page 1 of the live list compared with the derived titles:

  | Page title | Derived title |
  |---|---|
  | Software Engineer – Intern (US) | Software Engineer Intern US |
  | Trader: Fixed Income & Macro Rotational Trader – Intern (US) | Trader Fixed Income Macro Rotational Trader Intern US |
  | Trader: Power & Renewables Trader – FlexPower (a Citadel company)… | Trader Power Renewables Trader Flexpower a Citadel Company … |
  | US Physical Gas Specialist | US Physical Gas Specialist |

  Every word that matters for filtering ("intern", "phd", "university graduate", role words) survives. A lone `c` token is "C++" on these sites (e.g. `c-market-data-engineer` = "C++ Market Data Engineer"); it is shown as "C". That is cosmetic, since "Engineer"/"Software" still drive the SWE field.

## Field map
| Job field | Source | Notes |
|---|---|---|
| id | slug from `<loc>` | Stable while the WordPress post exists. A re-created post gets a new slug (often `-2`), which looks like a new job. That is acceptable, or the checker can suppress an alert when the derived title + region equal a job removed in the last 7 days. |
| title | derived from slug (above) | Real titles are only on challenged pages. |
| location(s) | `region_hint(slug)` | Real office list (e.g. "Greenwich, Houston, Miami, New York") is only on the listing cards and detail pages. |
| url (detail/apply) | `<loc>` | `https://www.citadel.com/careers/details/<slug>/` (apply form is on that page) |
| posted date | none | `<lastmod>` is rewritten for **every** URL on every sync. All 63 had lastmod 2026-10-19T23:14Z on 2026-10-19 and 2026-10-20T00:xxZ on 2026-10-20, so use first-seen. |
| description / snippet | none | Detail-page JSON-LD has the full text, but it is browser-only. |
| employment type | none in feed | Slug words carry it (`intern`, `university-graduate`, `phd-intern`, `post-doctoral-intern`). |
| department / team | none | |

## Totals (observed)
- **Feed, no filters:** **63** `<url>` entries, all `/careers/details/…`, 63 unique slugs. `GET /career-sitemap.xml` returned the same 63 on 2026-10-19 18:49 local and 2026-10-20 00:2x UTC.
- **Live careers page, no filters:** **63**. A Playwright render of `/careers/open-opportunities/` on 2026-10-20 showed "Viewing 10 of 63" (the 2026-10-19 capture showed "of 63" too). All 13 cards seen across both renders are in the sitemap.
- **Intern/student:** **28**. The title regex on derived titles gives 28, and the site's own Internships filter (`?experience-filter=internships&…`) showed "Opportunities (28)" (Playwright, 2026-10-19). So the slug heuristic matches the site's own classification exactly.
  - 13 have a US hint: finance-accounting, human-resources, human-resources-mba, machine-learning-researcher-phd, operations-analyst, quantitative-research-analyst, quantitative-research-engineer-phd, quantitative-researcher-post-doctoral, quantitative-researcher-phd, quantitative-trader-equity-quantitative-research, sector-data-scientist-2027, software-engineer and trader-fixed-income-macro-rotational-trader (each `…-intern-us`).
  - 1 has no region: `equities-citadel-associate-program-summer-internship-2028`.
  - 14 are Europe or Asia.

## robots.txt
`https://www.citadel.com/robots.txt` (HTTP 200): `Crawl-delay: 10` (before any group), then `User-agent: *` / `Disallow: /cdn-cgi/`, plus `Sitemap: https://www.citadel.com/sitemap_index.xml` and `Sitemap: https://www.citadelsecurities.com/sitemap_index.xml`.

| URL | Verdict | Deciding rule |
|---|---|---|
| https://www.citadel.com/career-sitemap.xml | ALLOW | no matching rule |
| https://www.citadel.com/sitemap_index.xml | ALLOW | no matching rule |
| https://www.citadel.com/careers/open-opportunities/ | ALLOW | no matching rule (but Cloudflare-challenged for plain HTTP) |
| https://www.citadel.com/careers/details/software-engineer-intern-us/ | ALLOW | no matching rule (Cloudflare-challenged for plain HTTP) |
| https://www.citadel.com/wp-admin/admin-ajax.php | ALLOW | no matching rule (challenged; see below) |

## Anti-bot / quirks
Cloudflare decides what plain HTTP (httpx, browser UA) can reach:

| URL | Plain HTTP result |
|---|---|
| `/career-sitemap.xml`, `/sitemap_index.xml` | **200** |
| static `/wp-content/…js` | **200** |
| `/careers/open-opportunities/` | **403 challenge** |
| `/careers/details/<slug>/` | **403 challenge** (interactive, re-tested 2026-10-20) |
| `/wp-json/wp/v2/types` | **403 challenge** |
| `/feed/?post_type=career` | **403 challenge** |

This is bot management, not robots. The rule is: do not evade it, and use only the sitemap.

- **Headless Chromium** (normal UA, no stealth) loads the listing and detail pages with status 200 after Cloudflare's passive JS check. That is how the page totals above were observed. It is not used by the checker.
  - The listing shows 10 cards per page. Each card is `a.careers-listing-card` with `data-position` (real title), `data-audience` (`student`/`professional`) and a location line. `per_page=100` in the URL is ignored.
  - The filter XHR `POST /wp-admin/admin-ajax.php` (`action=careers_listing_filter`) returns `{number_of_post, found_posts, content: <cards HTML>, post_per_page, page_number}` when the page itself calls it. A replay with `per_page=100` from the same browser session got a 403 challenge.
- **Detail pages** (browser only) carry `JobPosting` JSON-LD: `title`, full `description`, `employmentType` ("internship"), `jobLocation[]` with street addresses, `hiringOrganization`, `directApply: true`. `datePosted` equals the render date (2026-10-19 on 2026-10-19), so it is not a real posting date. The sample includes one example.
- **Health checks for the checker:**
  - The response must be HTTP 200, XML, with root `urlset`. A `403` or `cf-mitigated: challenge` means Cloudflare started challenging the sitemap: mark the source *blocked*, back off to once a day, and alert. Never retry with tricks.
  - Alert on 0 jobs, or a drop of more than 50% from the previous run.
- **Fallback if the sitemap ever gets challenged:** Citadel's own job alerts / talent network emails, and the SimplifyJobs cross-check.

## Recommended checker
```yaml
- key: citadel
  name: Citadel
  adapter: custom:citadel_sitemap        # shared with citadel-securities
  careers_url: https://www.citadel.com/careers/open-opportunities/
  settings:
    base_url: https://www.citadel.com
    sitemap: /career-sitemap.xml           # follow career-sitemap2.xml… only if 1000 entries
    detail_prefix: /careers/details/
    min_interval_s: 10                     # robots Crawl-delay: 10 (not parsed by the RFC 9309 matcher)
    title_from: slug                       # strip only -2..-99 WordPress suffix, keep years
    location_from: slug_region_hint        # "" when no hint -> unsure -> included
    posted_from: first_seen                # lastmod is rewritten on every sync
  health:
    expect: {status: 200, content_type: xml, root: urlset}
    alert_on_challenge: true               # 403 / cf-mitigated: challenge
    min_jobs: 1
    max_drop_ratio: 0.5
```

## Evidence
- Sample: `discovery/samples/citadel.json`. It has the raw sitemap (whole), the parsed rows with derived titles and region hints, the page-1 cards compared with derived titles, and one browser-only JSON-LD example.
- Capture: `discovery/captures/citadel/` (listing page, "of 63").
- Requests made for this company: 2026-10-19 by the previous agent (robots, 2 theme JS files, wp-json, listing, feed, sitemap index, career sitemap, plus 5 Playwright page loads), and 2026-10-20 by me (career sitemap, 1 detail page over plain HTTP, 1 Playwright listing render). All spaced at least 10 s apart.
