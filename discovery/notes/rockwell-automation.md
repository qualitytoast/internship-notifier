# Rockwell Automation (`rockwell-automation`)

**Status:** verified-feed (2 Workday career sites, plus a subset site that is skipped)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://www.rockwellautomation.com/en-us/careers.html. "View jobs" (`/en-us/careers/view-jobs.html`) redirects to `https://rockwellautomation.wd1.myworkdayjobs.com/en-US/External_Rockwell_Automation`. The EDGE student-programs page (`/en-us/careers/edge-student-early-career/edge-student-programs.html`) links `https://rockwellautomation.wd1.myworkdayjobs.com/External-Rockwell-Automation-Early-Careers`, which is the bookmark. |
| Hiring system | Workday (tenant `rockwellautomation`, wd1). Public sites: `External_Rockwell_Automation`, `External-Rockwell-Automation-Early-Careers`, `External-ERGs`. |
| Recommended adapter | shared `workday`, `sites: [External_Rockwell_Automation, External-Rockwell-Automation-Early-Careers]` |

## Recommended feed
- `POST https://rockwellautomation.wd1.myworkdayjobs.com/wday/cxs/rockwellautomation/<site>/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`.
- 20 per page, `total` on the first page only. Full run: 21 + 2 = 23 requests.
- The main-site name uses underscores and the early-careers name uses hyphens. Copy them exactly.

## Field map
Standard Workday:
- id: `externalPath`
- requisition: `bulletFields[0]`, e.g. `R26-5962`. The path adds `-1`/`-2` per posting, as in `…_R26-5962-1`.
- title, `locationsText`, `postedOn`
- url: `https://rockwellautomation.wd1.myworkdayjobs.com/en-US/<site><externalPath>`

## Totals (observed 2026-10-20 UTC)
| Site | Feed `total` | Page (Playwright) | Requisitions only here | Interns |
|---|---|---|---|---|
| `External_Rockwell_Automation` | 416 (417 at 03:19Z) | "416 JOBS FOUND" | 386 | 27 |
| `External-Rockwell-Automation-Early-Careers` | 29 | "29 JOBS FOUND" | 3 | 23 |
| `External-ERGs` (not watched) | 4 | "4 JOBS FOUND" | 0 (all 4 are also on the main site) | 0 |
| **Watched, deduped** | **419 requisitions** (445 postings; 26 requisitions are on both sites) | 445 | | **29** |

- Interns only on Early Careers: "Intern, Customer Success Professional" and "Intern, Marketing Engineer".
- Interns only on the main site:
  - "Intern Financial Planning and Analysis"
  - "Credit Management Intern"
  - "Intern, Project Administrator"
  - "Development Process Quality Control Intern"
  - "Intern Developer"
  - "Student Youth Apprentice"
- Neither site is a superset, so both are needed.
- There is no `workerSubType` facet. Titles are reliable here: "Intern, …", "Co-op, …", "Student Employee: …".

## robots.txt
| URL | Verdict | Rule |
|---|---|---|
| `…/wday/cxs/rockwellautomation/External_Rockwell_Automation/jobs` | ALLOW | no matching rule. The file has `Allow: /External_Rockwell_Automation/`, `/External-Rockwell-Automation-Early-Careers/`, `/External-ERGs/`. |
| `…/wday/cxs/rockwellautomation/External-Rockwell-Automation-Early-Careers/jobs` | ALLOW | no matching rule |

## Quirks
- The same requisition has a different `externalPath` on each site, so dedupe by `bulletFields[0]`. 26 intern and early-career requisitions are on both sites.
- The landing pages show a long cookie banner. It does not matter for the API.

## Recommended checker
```yaml
- key: rockwell-automation
  name: Rockwell Automation
  careers_url: https://www.rockwellautomation.com/en-us/careers.html
  checker: workday
  settings:
    host: rockwellautomation.wd1.myworkdayjobs.com
    tenant: rockwellautomation
    sites: [External_Rockwell_Automation, External-Rockwell-Automation-Early-Careers]   # External-ERGs ⊂ main site
```

## Evidence
- Sample: `discovery/samples/rockwell-automation.json` holds first-page excerpts and facets for both watched sites.
- Requests: 29 to rockwellautomation.wd1 (3 enumerations and 3 renders), plus 4 to www.rockwellautomation.com.
