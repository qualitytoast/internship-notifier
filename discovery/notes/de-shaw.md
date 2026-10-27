# D. E. Shaw (`de-shaw`)

**Status:** verified (105 = 105)   ·   **Checked:** 2026-10-26 (US Central)

| | |
|---|---|
| Official careers URL | https://www.deshaw.com/careers ("All positions" and "Internships") |
| Hiring system | None public. The Next.js page carries the job list in `__NEXT_DATA__`; apply links go to D. E. Shaw's own forms. |
| Checker | custom `deshaw` (`src/internwatch/checkers/deshaw.py`) |

## Feed
- **Request:** `GET https://www.deshaw.com/careers` (≈1 MB, ETag, so a 304 when nothing changed). robots.txt allows it.
- **Data:** `props.pageProps.regularJobs` (93, the "All positions" list) and `props.pageProps.internships` (12, the
  "Internships" list). `internalJobs` (92) are internal-only postings with `activeOnJobsListing: false`, such as
  "FinOp Intern (New York)- Summer 2027". The page doesn't show them, and the checker doesn't read them.
- `pageProps.jobsFetchingError: true` means the page itself failed to load its jobs. The checker then fails the
  check, so the day is never read as "0 jobs".

## Field map
| Job field | Path (`item.data`) |
|---|---|
| id | `id` (4 digits) |
| title | `displayName` |
| location | `jobMetadata.jobLocations[].name` ("New York", "Denver", "London", "Singapore", "Off-site") |
| url | `https://www.deshaw.com/careers/` + `jobUrl` in lower case |
| employment type | `jobMetadata.workStatus` ("Intern", "Regular Full-Time", "Limited/Fixed Term Assignee", "Contractor") |
| department | `department.name` |
| snippet | `jobDescription.websiteDescription` (HTML) |

## Totals (2026-10-26)
- **All:** 105 = 93 + 12, every one `activeOnJobsListing: true`, with no id in both lists.
- **Student roles:** 12. **Matches:** 5, the New York Summer 2027 internships: Quantitative Analyst (and Ph.D.),
  Software Developer (and Ph.D.), and Proprietary Trading.
