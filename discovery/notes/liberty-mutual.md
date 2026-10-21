# Liberty Mutual (`liberty-mutual`)

**Status:** verified-feed (Eightfold, legacy v2 API)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://jobs.libertymutualgroup.com/ (WordPress). "Search Jobs" goes to `https://searchjobs.libertymutualgroup.com/careers`. |
| Hiring system | **Eightfold**, legacy "v2" career site. Domain `libertymutual.com`, with two hostnames for the same tenant: `searchjobs.libertymutualgroup.com` (canonical) and `libertymutual.eightfold.ai` (the bookmark). The requisition ids `2026-262273` look like iCIMS. The site also links `internal-libertymutual.icims.com`, but only for employees. The Taleo link in the page footer (`lmig.taleo.net`) is commented out, and that host no longer resolves. |
| Recommended adapter | shared `eightfold`, `api: v2` |

## Recommended feed
- **Request:** `GET https://searchjobs.libertymutualgroup.com/api/apply/v2/jobs?domain=libertymutual.com&start=N&num=10`, with a browser UA and `Accept: application/json`. No cookies.
- **Pagination:** 10 per page. `num` is ignored (25 and 100 still return 10). Step `start` by 10 until `start >= count`: 20 requests for 196 jobs.
- **Order:** the default order is `t_create` descending at minute granularity, with no ties seen. Paging was stable: 196 rows gave 196 unique ids. `sort_by=timestamp` is accepted but does not change the order.
- **PCSX** (`/api/pcsx/search`) returns 403 `{"message": "PCSX is not enabled for this user."}` on both hostnames.
- **Detail:** `GET /api/apply/v2/jobs/<id>?domain=libertymutual.com`. The list already contains `job_description` (HTML).

## Field map (`positions[]`)
| Job field | Path | Example |
|---|---|---|
| id | `id` | 618520324874 |
| requisition | `display_job_id` / `ats_job_id` | `2026-262273` / `262273` |
| title | `name` (= `posting_name`) | "Technology Strategy & Transformation Internship (Summer 2027)" |
| locations | `locations[]` ("City, State, Country") / `location` | `["Portsmouth, New Hampshire, United States", "Boston, Massachusetts, United States"]` |
| url | `canonicalPositionUrl` | `https://searchjobs.libertymutualgroup.com/careers/job/618520324874` |
| posted | `t_create` (epoch s); `t_update` is also present | 1792414860 |
| description | `job_description` (HTML, full text in the list) | |
| team | `department`, `business_unit` | "Technology", "0021-People, Purpose & Brand-US" |

## Totals (observed 2026-10-20 UTC)
- **Feed:** `count` 196. The full enumeration gave 196 unique ids. The recheck at 03:19Z gave 194.
- **Page:** a Playwright render of `https://libertymutual.eightfold.ai/careers?domain=libertymutual.com` showed "196 open jobs".
- **Interns: 14.** These are Summer 2027 internships (technology strategy, claims, underwriting, surety, cyber/tech audit, analyst development, data science) and January–June 2027 co-ops (Solaria Labs data science, cybersecurity, internal audit, catastrophe modelling, talent acquisition). The bookmark (`query=intern`) showed 15, because keyword search is fuzzy.

## robots.txt
| URL | Verdict | Rule |
|---|---|---|
| `https://searchjobs.libertymutualgroup.com/api/apply/v2/jobs?domain=libertymutual.com&start=0&num=10` | ALLOW | `Allow: /api/apply` (Eightfold standard file) |
| `https://libertymutual.eightfold.ai/api/apply/v2/jobs?…` | ALLOW | `Allow: /api/apply` |
| `https://searchjobs.libertymutualgroup.com/careers/job/<id>` | ALLOW | `Allow: /careers` |
| `https://lmig.taleo.net/careersection/lmigcorp/jobsearch.ftl` | BLOCK | robots unreachable: the host has no DNS any more. Not used. |

## Anti-bot / quirks
- No 429 in 31 requests across both hostnames at ≥2.6 s spacing. A few of them were accidentally closer together, about 0.4 s. Use `min_interval: 2.5`.
- jobs.libertymutualgroup.com runs a Cloudflare challenge script but loads in a browser. The checker never needs it.

## Recommended checker
```yaml
- key: liberty-mutual
  name: Liberty Mutual
  careers_url: https://jobs.libertymutualgroup.com/
  checker: eightfold
  settings: {host: searchjobs.libertymutualgroup.com, domain: libertymutual.com, api: v2, min_interval: 2.5}
```

## Evidence
- Sample: `discovery/samples/liberty-mutual.json` holds v2 page 1 (4 positions, descriptions cut, branding and candidate blocks removed).
- Requests: 22 to searchjobs.libertymutualgroup.com and 9 to libertymutual.eightfold.ai (probes, num tests, PCSX 403, 1 render), plus 1 render of jobs.libertymutualgroup.com.
