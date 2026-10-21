# Workiva (`workiva`)

**Status:** verified-feed (2 small Workday sites)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://www.workiva.com/careers ("View Open Positions" goes to `https://workiva.wd503.myworkdayjobs.com/careers`) |
| Hiring system | Workday (tenant `workiva`, data centre **wd503**). robots.txt lists `careers` and `parseportcareers` (the site of ParsePort, a Workiva subsidiary). |
| Recommended adapter | shared `workday`, `sites: [careers, parseportcareers]` |

## Totals (observed 2026-10-20 UTC)
| Site | Feed `total` | Page (Playwright) | Interns |
|---|---|---|---|
| `careers` | 108 | "108 JOBS FOUND" | 1 ("Marketing Intern - JAPAC"; `workerSubType` "Intern (Fixed Term)" = 1) |
| `parseportcareers` | 1 | "1 JOB FOUND" | 0 ("Solution Consultant", USA remote, not on `careers`) |
| **Total** | **109** (no overlap) | 109 | **1** |

The bookmark `careers?workerSubType=831d1538442f014d2d2badf7c52a6e07` is the intern filter (1 job).

## Recommended feed
`POST https://workiva.wd503.myworkdayjobs.com/wday/cxs/workiva/<site>/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`. Full run: 6 + 1 = 7 requests. Field map is the standard Workday one (`bulletFields[0]` = `R12635`).

## robots.txt
| URL | Verdict | Rule |
|---|---|---|
| `…/wday/cxs/workiva/careers/jobs` | ALLOW | no matching rule (`Allow: /careers/`, `Allow: /parseportcareers/`) |
| `…/wday/cxs/workiva/parseportcareers/jobs` | ALLOW | no matching rule |

## Recommended checker
```yaml
- key: workiva
  name: Workiva
  careers_url: https://www.workiva.com/careers
  checker: workday
  settings: {host: workiva.wd503.myworkdayjobs.com, tenant: workiva, sites: [careers, parseportcareers]}
```

## Evidence
- Sample: `discovery/samples/workiva.json` holds first-page excerpts of both sites.
- Requests: 11 to workiva.wd503 and 1 to www.workiva.com.
