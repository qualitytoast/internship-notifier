# Red Hat (`red-hat`)

**Status:** verified-feed (single Workday site; the total is small but correct)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://www.redhat.com/en/jobs. "Search all Red Hat jobs" goes to `https://redhat.wd5.myworkdayjobs.com/jobs/`, and "Returning applicants" goes to `/jobs/login`. |
| Hiring system | Workday (tenant `redhat`, wd5). robots.txt lists one site, `/Jobs/`. |
| Recommended adapter | shared `workday`, `site: jobs` |

## Is 174 really everything?
Yes, as far as Red Hat publishes:
- robots.txt (`Sitemap: …/Jobs/siteMap.xml`, `Allow: /Jobs/`) names a single career site.
- redhat.com/en/jobs links nothing else: no student or university site, no IBM careers link. Its other pages (departments, locations, life-at-red-hat) are content only.
- The CXS site name is case-insensitive: `jobs` and `Jobs` both return `total: 174` with the same first page.
- The Playwright render of `/Jobs` showed "174 JOBS FOUND".

The low count is real (US 43, Singapore 24, Czechia 20, Australia 20, Japan 19, …), not a filter. If Red Hat later moves roles to IBM's careers site, the drop alert will catch it.

## Totals (observed 2026-10-20 UTC)
- Feed `total` **174**, page **174**.
- **42 internships** by title:
  - 19 in Brno, CZ: software engineering on kernel, containers, OpenShift, virtualization, SRE and so on.
  - US: "Software Engineer Intern", "Software Engineer Co-op", product, sales, deal-desk, finance and marketing interns.
  - Marketing interns in China and ASEAN.
- The facet names are anonymised (`a` country, `b` region, `c` remote type, `d` job family group, `e` time type) and there is no worker-type facet, so rely on titles.

## Recommended feed
`POST https://redhat.wd5.myworkdayjobs.com/wday/cxs/redhat/jobs/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`. 9 requests. Field map is the standard Workday one (`bulletFields[0]` = requisition `R-0NNNNN`). Job URL: `https://redhat.wd5.myworkdayjobs.com/en-US/jobs<externalPath>`.

## robots.txt
| URL | Verdict | Rule |
|---|---|---|
| `https://redhat.wd5.myworkdayjobs.com/wday/cxs/redhat/jobs/jobs` | ALLOW | no matching rule (`Allow: /Jobs/`, `Disallow: /refreshFacet/`) |

## Recommended checker
```yaml
- key: red-hat
  name: Red Hat
  careers_url: https://www.redhat.com/en/jobs
  checker: workday
  settings: {host: redhat.wd5.myworkdayjobs.com, tenant: redhat, site: jobs}
```

## Evidence
- Sample: `discovery/samples/red-hat.json` holds the first-page excerpt with the anonymised facets.
- Requests: 12 to redhat.wd5 (both site spellings, the enumeration, 1 render, the recheck), plus 1 render of www.redhat.com/en/jobs.
