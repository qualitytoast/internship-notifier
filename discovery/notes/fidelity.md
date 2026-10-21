# Fidelity Investments (`fidelity`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://jobs.fidelity.com/en/jobs/ (US culture). The same marketing site has two more cultures: `/ie/jobs/` (Ireland) and `/in/jobs/` (India), linked by `hreflang`. |
| Hiring system | **Workday**, tenant `fmr`, site `FidelityCareers`, data centre wd1, served on the `wd1.myworkdaysite.com/recruiting/fmr/FidelityCareers` form. jobs.fidelity.com is an Umbraco "jobboard" marketing site in front of it, the same platform as search-careers.gm.com and pinterestcareers.com. Its job ids (e.g. `/en/jobs/2136904/cybersecurity-internship/`) are the Workday requisition numbers, and its apply/login links go to `wd1.myworkdaysite.com/en-US/recruiting/fmr/FidelityCareers/...`. |
| Recommended adapter | shared `workday` adapter, `host: wd1.myworkdaysite.com` |

## Recommended feed
- **Request:** `POST https://wd1.myworkdaysite.com/wday/cxs/fmr/FidelityCareers/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`
- **Headers:** `Content-Type: application/json`, `Accept: application/json`, browser UA. No cookies or CSRF needed. Plain httpx got 200 on all 38 pages.
- **Pagination:** offset 0, 20, … up to `total` (760 means 38 pages). `total` is only in the first page.
- **Detail:** `GET https://wd1.myworkdaysite.com/wday/cxs/fmr/FidelityCareers<externalPath>` returns `jobPostingInfo` (description, location, timeType). It answered 200.
- Only one external site exists. `fmr.wd1.myworkdayjobs.com/robots.txt` lists only `Sitemap: …/FidelityCareers/siteMap.xml` and `Allow: /FidelityCareers/`.

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `jobPostings[].externalPath` | e.g. `/job/Dublin-Ireland/Cybersecurity-Internship_2136904`. Reposted requisitions get a `-1` suffix (`..._2129661-1`). `bulletFields[0]` is the bare requisition number (`2136904`). |
| title | `jobPostings[].title` | Some have double spaces ("Human Resources  Internship") |
| location(s) | `jobPostings[].locationsText` | "Westlake, TX", "Dublin, Ireland", "2 Locations" (use detail for the list) |
| url | `https://wd1.myworkdaysite.com/en-US/recruiting/fmr/FidelityCareers` + `externalPath` | (the adapter's myworkdaysite form). Marketing copy: `https://jobs.fidelity.com/en/jobs/<req>/<slug>/` |
| posted date | `jobPostings[].postedOn` | relative ("Posted 5 Days Ago") |
| employment type | none in the list | `timeType` facet is "Full time" for all 760, including the interns |

## Totals (observed 2026-10-19/20)
- **Feed, no filters:** **760**. All 38 pages were fetched: 760 postings, 760 unique `externalPath`.
- **Live careers site, no filters:** **755** = 709 + 33 + 13. Each count was read from the "N open roles" text in a Playwright render: `/en/jobs/` "709 open roles", `/ie/jobs/` "33 open roles", `/in/jobs/` "13 open roles".
- **Difference (5):** CXS `locationCountry` gives US 711, Ireland 33, India 12, United Kingdom 2, Japan 1, Germany 1. The four UK/JP/DE jobs are on none of the three cultures: Senior Manager, Global Thought Leadership (London); Quantitative Equity Research Analyst (London); Equity Research Associate (Tokyo); Customer Service Representative (Kronberg, Germany). The other ±2 (US 711 vs 709, India 12 vs 13) is sync lag between Workday and the marketing site. Workday is the complete source.
- **Intern/student (titles):** **7**. Workday has no intern facet, so these come from titles:
  - Intern, Investor Center: Santa Barbara CA, Ann Arbor MI, Hilton Head SC
  - Enterprise Infrastructure & Operations Internship (Galway)
  - Cybersecurity Internship (Dublin)
  - Human Resources Internship (Dublin + 1 more)
  - Fidelity Strategic Advisors Inc, Investment Trading Research Internship (Dublin)

  The CXS keyword search `searchText: "intern"` is fuzzy (the earlier run got 245 hits, mostly not internships), so do not use it as a filter.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://wd1.myworkdaysite.com/wday/cxs/fmr/FidelityCareers/jobs` | ALLOW | robots.txt returns HTTP 422, which counts as 4xx, so no robots |
| `https://wd1.myworkdaysite.com/en-US/recruiting/fmr/FidelityCareers/job/...` | ALLOW | same |
| `https://fmr.wd1.myworkdayjobs.com/wday/cxs/fmr/FidelityCareers/jobs` | ALLOW | no matching rule (`Allow: /FidelityCareers/`, `Disallow: /targeted/`, `/refreshFacet/`) |
| `https://jobs.fidelity.com/en/jobs/` | ALLOW | `Allow: /` |

## Anti-bot / quirks
- The Workday host is behind Cloudflare but answered every plain POST with 200. jobs.fidelity.com rendered fine in headless Chromium. Its `/umbraco/jobboard/...` endpoints were not needed.
- `externalPath` slugs can be stale. `/job/Dublin-Ireland/Intern_2136759-1` is titled "Fidelity Strategic Advisors Inc, Investment Trading Research Internship", so key on the path but show the title.

## Recommended checker
```yaml
- key: fidelity
  name: Fidelity Investments
  adapter: workday
  settings:
    host: wd1.myworkdaysite.com
    tenant: fmr
    site: FidelityCareers
  careers_url: https://jobs.fidelity.com/en/jobs/
```

## Evidence
- Sample: `discovery/samples/fidelity.json` is the first CXS page (20 postings plus facets, 51 KB).
- Capture: `discovery/captures/fidelity/` (bookmark with search=intern: "6 open roles").
- Requests: 38 CXS pages, 1 detail, and Playwright renders of `/en/jobs/`, `/ie/jobs/` and `/in/jobs/`. This run and the earlier agent's run together made about 45 requests.
