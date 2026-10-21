# CCC Intelligent Solutions (`ccc`)

**Status:** verified-feed (Workday; the second site is empty)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://www.cccis.com/about/careers (www.cccis.com/careers redirects there). Its job links go to `https://cccis.wd1.myworkdayjobs.com/broadbean_external`. |
| Hiring system | Workday (tenant `cccis`, wd1). robots.txt lists two public sites: `broadbean_external` (named after the Broadbean multiposting tool) and `CCCIS`. |
| Recommended adapter | shared `workday`, `sites: [broadbean_external, CCCIS]` |

## Totals (observed 2026-10-20 UTC)
| Site | Feed `total` | Page (Playwright) | Interns |
|---|---|---|---|
| `broadbean_external` | **35** | "35 JOBS FOUND" | 0 |
| `CCCIS` | 0 | – | – |

28 of the 35 jobs are at the Chicago (Green St) HQ. The rest are field inventory reps and sales roles. No internships are open today. `CCCIS` is empty but public. Watching it costs 1 request per run, which keeps postings covered if CCC switches sites.

## Recommended feed
`POST https://cccis.wd1.myworkdayjobs.com/wday/cxs/cccis/<site>/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`. Full run: 2 + 1 requests. Field map is the standard Workday one. The facets here are `JobFamilyGroup` and `JobFamily`, with capital J.

## robots.txt
| URL | Verdict | Rule |
|---|---|---|
| `…/wday/cxs/cccis/broadbean_external/jobs` | ALLOW | no matching rule (`Allow: /broadbean_external/`, `Allow: /CCCIS/`) |
| `…/wday/cxs/cccis/CCCIS/jobs` | ALLOW | no matching rule |

## Recommended checker
```yaml
- key: ccc
  name: CCC Intelligent Solutions
  careers_url: https://www.cccis.com/about/careers
  checker: workday
  settings: {host: cccis.wd1.myworkdayjobs.com, tenant: cccis, sites: [broadbean_external, CCCIS]}
```

## Evidence
- Sample: `discovery/samples/ccc.json` holds the broadbean_external first-page excerpt and the empty CCCIS response.
- Requests: 5 to cccis.wd1, plus 1 render of the CCC careers page.
