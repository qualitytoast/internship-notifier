# PayPal (`paypal`)

**Status:** verified-feed (Workday is the more complete source; Eightfold shows a subset of it)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://careers.pypl.com/ (it lands on /home/default.aspx). Every search link goes to `https://paypal.eightfold.ai/careers`, which is the bookmark. |
| Hiring system | **Eightfold PCSX** career site (`paypal.eightfold.ai`, domain `paypal.com`) on top of **Workday**. The Workday tenant is `paypal` on wd1, site `jobs`. robots.txt `Sitemap: https://wd1.myworkdaysite.com/recruiting/paypal/jobs/siteMap.xml`. The Eightfold `displayJobId` (e.g. `R0138315`) is the Workday requisition. |
| Recommended adapter | shared `workday` (`site: jobs`). The Eightfold feed is the alternative and cross-check. |

## Which source
| Source | Total (no filters) | Page | Interns |
|---|---|---|---|
| Workday `jobs`: `POST https://paypal.wd1.myworkdayjobs.com/wday/cxs/paypal/jobs/jobs` | **340** | "340 JOBS FOUND" on both https://paypal.wd1.myworkdayjobs.com/jobs and https://wd1.myworkdaysite.com/recruiting/paypal/jobs (Playwright) | 0 |
| Eightfold: `GET https://paypal.eightfold.ai/api/pcsx/search?domain=paypal.com&query=&location=&start=N` | **330** (331 and 332 seen earlier) | "330 jobs", "Page 1 of 33", but only after pressing **Clear All**. By default the page applies a geo-IP location filter: it opened with `location=Madison, Wisconsin, US&sort_by=distance&filter_distance=80`, which showed "18 jobs". | 0 |

All 330 Eightfold requisitions are on the Workday site. Workday has **10 more**, none of them only on Eightfold. Two are "Sr Staff Software Engineer" (`R0138369`) and "Senior Lead Product Manager" (`R0138368`), posted 14 days ago. The others are older sales, legal and product roles. So Workday is the superset. It is also cheaper: 17 requests per run at 20 per page with no special rate limit, against 33 Eightfold requests at ≥2.5 s.

## Recommended feed (Workday)
- `POST https://paypal.wd1.myworkdayjobs.com/wday/cxs/paypal/jobs/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`. 20 per page, `total` on the first page only. 340 jobs is well under the 2000 cap.
- `wd1.myworkdaysite.com/wday/cxs/paypal/jobs/jobs` serves the same data. For email links, the canonical public URL is `https://wd1.myworkdaysite.com/en-US/recruiting/paypal/jobs<externalPath>`, or `https://paypal.wd1.myworkdayjobs.com/en-US/jobs<externalPath>`. Both work.
- Field map: the standard Workday one. `bulletFields[0]` is the requisition `R0137369`; the path suffix `-1` marks a reposting. Path slugs can be stale: `…/Sr-Lead-Product-Manager--Enterprise-AI-Accelerations_R0137369-1` is titled "Sr. Technical Program Manager- Automation and Simplification".

## Eightfold facts (if used)
- 10 per page. `page_size=20` returns 400 "Too many rows requested.", and v2 returns 403.
- `sort_by=timestamp` is newest-first, but `postedTs` is day-granular (all values at midnight, 40 distinct days), so tied jobs can reorder between pages. One full scan had no duplicates.
- No 429 in 43 requests. A few were accidentally closer than 1 s.
- Filters include `job_category`, `brand` (paypal/venmo/paidy), `work_location_option` and `employment_type` (only "full time" today).

## robots.txt
| URL | Verdict | Rule |
|---|---|---|
| `https://paypal.wd1.myworkdayjobs.com/wday/cxs/paypal/jobs/jobs` | ALLOW | no matching rule (`Allow: /jobs/`, `Disallow: /refreshFacet/`) |
| `https://wd1.myworkdaysite.com/wday/cxs/paypal/jobs/jobs` | ALLOW | no robots.txt |
| `https://paypal.eightfold.ai/api/pcsx/search?domain=paypal.com&…` | ALLOW | `Allow: /api/pcsx` |

## Recommended checker
```yaml
- key: paypal
  name: PayPal
  aliases: [Venmo]
  careers_url: https://careers.pypl.com/
  checker: workday
  settings: {host: paypal.wd1.myworkdayjobs.com, tenant: paypal, site: jobs}
  # alternative/cross-check: eightfold {host: paypal.eightfold.ai, domain: paypal.com, api: pcsx, min_interval: 2.5}
```

## Evidence
- Sample: `discovery/samples/paypal.json` holds the Workday first-page excerpt with facets, plus Eightfold search page 1 (filter lists trimmed).
- Requests: 17 to paypal.wd1 and 2 Playwright renders of the Workday pages; 43 to paypal.eightfold.ai (enumeration, experiments, 2 renders); 1 to careers.pypl.com.
