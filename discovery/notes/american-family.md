# American Family Insurance (`american-family`)

**Status:** verified-feed, with a **robots.txt caveat for the lead to confirm**   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://careers.amfam.com/. www.amfam.com/about/careers redirects here. It is an Umbraco site behind Cloudflare: plain HTTP gets 403, a real browser loads it. Its internships page https://careers.amfam.com/early-careers/internships/ links `https://amfam.wd1.myworkdayjobs.com/en-US/AmFamGroupInternCareers?source=AFMIC%20Website`, which is the bookmark. |
| Hiring system | Workday (tenant `amfam`, wd1). robots.txt allows `Careers` and `Agent-Staff`, and **disallows `/AmFamGroupInternCareers/`**, `/Agent-Staff-Private/` and `/AmFam-Private/`. |
| Recommended adapter | shared `workday`, `sites: [AmFamGroupInternCareers, Careers]` |

## Why the intern site is needed
- `AmFamGroupInternCareers` has **24** jobs, all internships. None of them is on any other site: 0 requisitions are shared with `Careers` or `Agent-Staff`.
- `Careers` has 32 jobs, 3 of them internships: "Summer 2027 Intern - Data Engineering" and "Enterprise Data Intern" ×2.
- The careers.amfam.com job board (`/jobs/`, data from `/umbraco/jobboard/CandidateJobs/GetRecentJobs`) mirrors only `Careers` and `Agent-Staff`. Its `subTeam=Intern` view shows just those 3 interns.

Without the intern site the watcher would see 3 of 27 internships.

## robots.txt (the caveat)
| URL | Verdict | Rule |
|---|---|---|
| `POST https://amfam.wd1.myworkdayjobs.com/wday/cxs/amfam/AmFamGroupInternCareers/jobs` | **ALLOW** | no matching rule |
| `GET https://amfam.wd1.myworkdayjobs.com/wday/cxs/amfam/AmFamGroupInternCareers/job/WI-Madison/Summer-2027-Intern---Claims_R39421` (detail) | ALLOW | no matching rule |
| `https://amfam.wd1.myworkdayjobs.com/en-US/AmFamGroupInternCareers?source=…` (the page careers.amfam.com links) | ALLOW | no matching rule (the disallow has a trailing slash and no locale prefix) |
| `https://amfam.wd1.myworkdayjobs.com/AmFamGroupInternCareers/job/…` (the detail's `externalUrl`) | **BLOCK** | `Disallow: /AmFamGroupInternCareers/` |
| `POST …/wday/cxs/amfam/Careers/jobs` | ALLOW | no matching rule (`Allow: /Careers/` covers the pages) |
| `https://careers.amfam.com/jobs/` | ALLOW | `Allow: /` (Cloudflare; plain HTTP 403) |

Under the RFC 9309 matcher the project uses, every URL the checker would fetch is allowed. The disallow covers the intern site's own HTML and job pages, which look like Workday's "hide from search engines" setting. The company also links the site publicly from its internships page. I recommend using the CXS API. If the lead reads the disallow as covering the whole site, the only fallback is to watch `Careers` alone (3 interns) and use SimplifyJobs as a cross-check. Never fetch the `/AmFamGroupInternCareers/job/…` URLs. Using them as email links is fine.

## Recommended feed
- `POST https://amfam.wd1.myworkdayjobs.com/wday/cxs/amfam/<site>/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`. 20 per page, `total` on the first page only. Full run: 2 + 2 = 4 requests.
- Detail (verified on the intern site: HTTP 200, 5.8 KB description): `GET /wday/cxs/amfam/AmFamGroupInternCareers<externalPath>` returns `jobPostingInfo.jobReqId` (`R39421`), `timeType`, `startDate`, `location`, `country`, and `hiringOrganization.name` (AFMIC or AFICS).
- Field map: the standard Workday one, with `bulletFields` = `[req id, hiring company]`. The intern site's `workerSubType` facet shows Intern 24. On `Careers`, `workerSubType` "Intern" = 3, which equals the title matches.

## Totals (observed 2026-10-20 UTC)
| Site | Feed `total` | Page | Interns |
|---|---|---|---|
| `AmFamGroupInternCareers` | 24 | "24 JOBS" in the prior Playwright capture of the bookmark (`discovery/captures/american-family`). Not re-rendered because of the disallow. | 24 |
| `Careers` | 32 (31 at 03:19Z) | "32 JOBS FOUND" (Playwright) | 3 |
| `Agent-Staff` (not watched) | 74 | "74 JOBS FOUND" | 0. These are "Insurance Agent" / "Insurance Agency Owner" roles, workerSubType Agents. |
| **Watched** | **56** (no overlap) | 56 | **27** |

## Recommended checker
```yaml
- key: american-family
  name: American Family Insurance
  careers_url: https://careers.amfam.com/
  checker: workday
  settings:
    host: amfam.wd1.myworkdayjobs.com
    tenant: amfam
    sites: [AmFamGroupInternCareers, Careers]   # see robots caveat; Agent-Staff = agency-owner jobs, skipped
```

## Evidence
- Sample: `discovery/samples/american-family.json` holds intern-site and Careers first-page excerpts with facets.
- Requests: 13 to amfam.wd1 (enumerations, the intern-facet query, 1 detail, 2 renders of Careers and Agent-Staff), plus 5 to careers.amfam.com (robots and 3 renders).
