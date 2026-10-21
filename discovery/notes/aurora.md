# Aurora Innovation (`aurora`)

**Status:** verified-feed (Ashby is a superset of the website by 2 duplicate postings)   ·   **Checked:** 2026-10-19 (US Central) = 2026-10-20 00:12 UTC

| | |
|---|---|
| Official careers URL | https://aurora.tech/careers. The bookmark adds `?departments=Software+Engineering`; track the unfiltered page. Each job is at `https://aurora.tech/careers/{postingId}`, and the apply links are `https://aurora.tech/careers?ashby_jid={postingId}`, which opens an embedded Ashby form. |
| Hiring system | **Ashby**, org slug `aurora-operations-inc`. The Nuxt config on the page has `ashbyOrgSlug:"aurora-operations-inc"`, and the hosted board's `organization.customJobsPageUrl` is `https://aurora.tech/careers`. The site renders its list from its own index, `GET https://aurora.tech/api/jobs-index`. |
| Recommended adapter | shared `ashby`: `{board: aurora-operations-inc}` |

Greenhouse probes (`aurora`, `aurorainnovation`, `aurora-innovation`) all returned 0 jobs. They are unrelated boards.

## Recommended feed
- **Request:** `GET https://api.ashbyhq.com/posting-api/job-board/aurora-operations-inc?includeCompensation=true`. The response is 1.77 MB because it includes full descriptions; drop `includeCompensation` if size matters. There is no pagination: all jobs come in one response. The `apiVersion` field is present.
- **Website index (cross-check):** `GET https://aurora.tech/api/jobs-index` (1.29 MB, `no-cache`) returns `{jobs[], index, facets}`. Each job has `id` (the same Ashby posting id), `jobId` (Ashby job id), `title`, `category`, `locations[]`, `isRemote`, `employmentType`, `applyLink`, `publishedDate`, `updatedAt` and `searchText`. `index` is a serialized search index of about 430 KB.
- **Headers:** a normal browser UA. No auth.

## Field map (Ashby posting API)
Paths are relative to `jobs[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | `id` | the posting UUID, the same one used in aurora.tech URLs |
| title | `title` | some have a trailing space ("Senior Software Engineer, Geometric Generation "), so trim |
| location(s) | `location` + `secondaryLocations[].location` (structured: `address.postalAddress`) | e.g. "Mountain View, CA" + "Pittsburgh, PA". `isRemote`, `workplaceType` (Hybrid/OnSite/Remote) |
| url (detail/apply) | `jobUrl` = `https://jobs.ashbyhq.com/aurora-operations-inc/{id}` (apply: `applyUrl`) | for display, `https://aurora.tech/careers/{id}` is the company page |
| posted date | `publishedAt` (ISO) | |
| description / snippet | `descriptionPlain` / `descriptionHtml` | |
| employment type | `employmentType` (`FullTime` for all 101) | |
| department / team | `department`, `team` | e.g. Software Engineering. The site's `category` equals the department. |
| other | `isListed` (true for all), `compensation.compensationTierSummary` | |

## Totals (observed 2026-10-20 00:12 UTC)
- **Feed, no filters:** **101** postings, all `isListed`. The hosted board `https://jobs.ashbyhq.com/aurora-operations-inc` (`window.__appData.jobBoard.jobPostings`) has the **same 101 ids**.
- **Live careers page, no filters:** **99**. A Playwright render of https://aurora.tech/careers shows 8 jobs and "Load more". Its **Departments facet counts sum to 99**: Software Engineering 24, Vehicle Operations 23, Hardware & Embedded Engineering 11, Enterprise IT & Security 9, Finance 5, … This equals the page's data file `/api/jobs-index` (99 jobs) fetched by the same render.
- **Why 101 vs 99:** the 2 Ashby-only postings are **second postings of jobs the site already lists**. The same pair was missing in the previous run (100 vs 98), when one more job existed on both sides.

  | Ashby-only posting | Twin on aurora.tech | Same? |
  |---|---|---|
  | 65a32061 "Senior Software Engineer, Motion Controls", published 2026-08-04 | fcb5715b, same title, published 2026-10-14 | same locations (Mountain View + Pittsburgh), description 99.8 % identical |
  | 2e895957 "Senior Software Engineer, Geometric Generation", published 2026-10-06 16:17:32 | b557e5a3 "Software Engineer, Geometric Generation", published 9 s later | same 4 locations, description 99.2 % identical |

  The site's index has exactly one entry per Ashby `jobId` (99 unique), while the posting API lists every posting. Same-title postings for *different* jobs, such as 7 × "Truck Operations Specialist", all appear on the site. So the site keeps one posting per job. **Ashby is complete** (a superset): the extra two are real, listed postings, merely duplicates.
- **Intern/student:** **0**. All 101 are full time.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://api.ashbyhq.com/posting-api/job-board/aurora-operations-inc?includeCompensation=true | ALLOW | api.ashbyhq.com has no robots.txt |
| https://jobs.ashbyhq.com/aurora-operations-inc | ALLOW | no matching rule (`/api/` is disallowed there; do not use it) |
| https://aurora.tech/api/jobs-index | ALLOW | `Allow: /` |
| https://aurora.tech/careers | ALLOW | `Allow: /` |

## Anti-bot / quirks
- No challenge on either host.
- Expect the checker's count to be about 2 above the website's. That is not a bug. Optionally collapse duplicates by (normalised title, location set) when emailing.
- The "of 20" count text in the first capture is from the benefits copy ("20 vacation days"), not a pager.

## Recommended checker
```yaml
- key: aurora
  name: Aurora Innovation
  adapter: ashby
  careers_url: https://aurora.tech/careers
  settings:
    board: aurora-operations-inc
  # display link: https://aurora.tech/careers/{id}
```

## Evidence
- Sample: `discovery/samples/aurora.json` is the Ashby posting API response **truncated to the first 3 of 101 jobs**; the raw response is 1.77 MB. The structure is unchanged, plus a `_sample_note`.
- Capture: `discovery/captures/aurora/` (the bookmark render, `feed_0_0.json` = jobs-index with 98 jobs at capture time).
- Requests: the previous run made 3 (robots, Ashby API, jobs-index). This run made 5 (robots ×3, Ashby API, hosted board) plus 1 Playwright render, which itself loaded jobs-index.
