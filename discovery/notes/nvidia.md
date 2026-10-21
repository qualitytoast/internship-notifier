# NVIDIA (`nvidia`)

**Status:** verified-feed   ·   **Checked:** 2026-10-19 19:11–19:16 CDT (2026-10-20 00:11–00:16 UTC)

| | |
|---|---|
| Official careers URL | https://jobs.nvidia.com/careers (no filters). nvidia.com/careers "Search jobs" lands here. The bookmark is a filtered view of the same page (`location=United States`, `filter_job_type=intern (fixed term)`, 49 jobs). |
| Hiring system | **Eightfold.ai PCSX** career site on NVIDIA's own host (`/api/pcsx/*` XHRs, 12-digit Eightfold position ids). The system of record is **Workday**: tenant `nvidia`, site `NVIDIAExternalCareerSite` on `nvidia.wd5.myworkdayjobs.com`. Every position has `atsJobId` = the Workday requisition (`JR2023758`), and `position_details` gives `applyUrl` = `https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/<loc>/<slug>_JR…/apply?source=Eightfold`. |
| Recommended adapter | shared `eightfold` adapter (`api: pcsx`) with `big: true`, the intern job-type quick query, and ≥ 2.5 s host spacing. Workday CXS is a useful cross-check for the intern slice, but it can't be the main feed (see the 2000 cap below). |

## Recommended feed
- **Request:** `GET https://jobs.nvidia.com/api/pcsx/search?domain=nvidia.com&query=&location=&start=0&sort_by=timestamp`
- **Headers:** a normal browser UA and `Accept: application/json`. No cookie, CSRF token or referer is needed.
- **Pagination:** offset `start` = 0, 10, 20, …; 10 rows per page. Stop when `start >= data.count` or `positions` is empty. The whole site takes **276 requests** (2757 jobs), which is why it should be a `big` site: each poll reads newest-first until a page has only known ids, and it does a full scan once a day. I didn't re-test larger page sizes here. On Microsoft's identical PCSX API, `page_size` > 10 returns HTTP 400.
- **Order:** `sort_by=timestamp` is newest-first by `postedTs`. In the 176-job intern listing, 0 of 175 neighbouring pairs were out of order. NVIDIA's `postedTs` is a date at 00:00 UTC (e.g. 1792368000 = 2026-10-17), so many jobs share a timestamp. Quick scans must stop on known ids, not on timestamps.
- **Intern quick query (every poll, 18 requests):** add `&filter_job_type=intern+%28fixed+term%29` → `data.count` **176** worldwide. Other values of the `job_type` filter (from `data.filterDef.allFilters`): `regular employee`, `management`, `new college graduate`, `regular employee (fixed term)`, `academic (fixed term)`. Other filters: `job_category` (incl. `univ employment`), `time_type`, `work_location_option`, `hiring_title`, `skills`. Leave `location` empty: it is fuzzy and geocoded, and our code filters locations from `standardizedLocations` anyway.
- **Detail (optional):** `GET https://jobs.nvidia.com/api/pcsx/position_details?position_id=<id>&domain=nvidia.com&hl=en` returns `data.jobDescription` (HTML), `efcustomTextJobFmailyGroup` (sic, e.g. `["Engineering"]`), `efcustomTextTimeType` (`["Full time"]`), `publicUrl` and `positionUserActions.applyAction.applyUrl` (the Workday apply link). Job type isn't in the detail either; it only shows up through `filter_job_type`.
- **Job URL for emails:** `https://jobs.nvidia.com` + `positionUrl` = `https://jobs.nvidia.com/careers/job/<id>` (= `publicUrl`).
- **Alternative considered: Workday CXS** `POST https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs` `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`. It's robots-allowed and has 20 rows per page, but it is **unusable as a whole-site feed**:
  - `total` is **capped at 2000**, while the facet counts add up to 2752.
  - `offset=2000` returns **the first page again**: byte-identical to `offset=0`, still with `total: 2000`.

  The shared `workday` adapter would therefore stop after 100 pages, pass its own total check (2000 = 2000), and silently miss about 750 jobs. Reading all of Workday needs facet partitions, e.g. `jobFamilyGroup`: the largest group is Engineering with 1758, so every partition is < 2000 today. The adapter doesn't do that.
  - `siteMap.xml` lists only the newest 100 jobs.
  - `searchText=intern` returns 1086 hits because it matches descriptions, so it's useless.
  - The intern facet works: `appliedFacets: {"workerSubType": ["0c40f6bd1d8f10adf6dae42e46d44a17"]}` returns 176, which takes 9 requests.

## Field map
Paths are relative to `data.positions[]` of the search response.

| Job field | Response path | Notes |
|---|---|---|
| id | `id` (int, 12 digits) | e.g. `893397606507`. Keep `displayJobId`/`atsJobId` (`JR2023758`) as `alt_ids` so it can be matched with Workday and Simplify. |
| title | `name` | e.g. `Software Engineer Intern, Robotics - 2027` |
| location(s) | `locations[]` (`"US, CA, Santa Clara"`, `"China, Shanghai"`); `standardizedLocations[]` (`"Santa Clara, CA, US"`, `"Taipei City,TW"`) | multi-location jobs list several |
| url (detail) | `"https://jobs.nvidia.com" + positionUrl` | `/careers/job/893397606507` |
| url (apply) | detail → `positionUserActions.applyAction.applyUrl` | Workday `/apply?source=Eightfold` link; use it as a link only |
| posted date | `postedTs` (epoch seconds, date at 00:00 UTC) | `creationTs` = original creation |
| description / snippet | detail → `jobDescription` | not in the list |
| employment type | only through the `filter_job_type` query that returned the job; `department` = `"Intern"` for all 176 interns | |
| department / team | `department` (e.g. `Engineer, Dev Ops`, `Intern`) | detail: `efcustomTextJobFmailyGroup` |
| other | `workLocationOption` (`onsite`/`remote`), `locationFlexibility`, `isHot` | |

## Totals (observed 2026-10-19)
| Measure | Value | How observed |
|---|---|---|
| Feed, no filters | **2757** | `data.count` of the recommended request |
| Live careers page, no filters | **2757** | One Playwright render of https://jobs.nvidia.com/careers showed "**2757 jobs**" and "of 276" (pages). The page's own XHR is the same `/api/pcsx/search?domain=nvidia.com&query=&location=&start=0&…`. |
| Workday CXS | `total` 2000 (capped); facet sums **2752** (workerSubType, timeType and jobFamilyGroup all add up to 2752) | first page of the unfiltered CXS POST |
| By job type, PCSX / Workday | Regular Employee 2308 / 2303 · Management 204 / 203 · **Intern (Fixed Term) 176 / 176** · New College Graduate 66 / 67 · Regular (Fixed Term) + Academic 3 / 3 | `filter_job_type=…` counts vs the Workday `workerSubType` facet |
| Intern slice, ids compared | 175 in both. **PCSX-only JR2024054** ("AI Developer Technology Intern, Robotics - 2027", China): it is live on Workday but not in Workday's Intern facet. **Workday-only JR2025645** ("Software Engineer, Data Center Compute Software Tools (RDSS Intern)", Taipei, posted 13 days ago): it isn't on jobs.nvidia.com at all (`query=JR2025645` doesn't find it). | both intern slices fully listed (18 PCSX + 9 Workday requests) |
| **Intern/student** | **176** (job type `Intern (Fixed Term)`). 177 distinct across both systems. | All 176 titles contain Intern/Student. 48 have a US location and 2 a Canadian one (Toronto). By country, counted per job: CN 75, US 48, TW 33, CH 8, DE 6, PL 5, GB 3, FR 3, CA 2. |

The gap between the two systems is +5 jobs on Eightfold overall (2757 vs 2752). It is spread over the regular, management and NCG types, and it looks like normal sync lag between the two. jobs.nvidia.com is the page candidates see and it equals the feed. Eightfold can still lag Workday by a posting (JR2025645 above). If missing interns matter, run the Workday intern-facet query as a cheap cross-check (9 requests). Our code can join the two by `JR…` id: eightfold `alt_ids` = `atsJobId`; workday `alt_ids` = `bulletFields`.

## robots.txt
jobs.nvidia.com: `User-agent: *` / `Disallow: /` with `Allow: /$`, `/careers`, `/api/apply`, `/api/pcsx`, `/login`, `/events/…`, `/api/events`, `/careerhub/explore/jobs`, `/api/career_hub`, `/static/gen`, `/gen`. nvidia.wd5.myworkdayjobs.com: `Allow: /NVIDIAExternalCareerSite/`, `Disallow: /NVIDIAExternalCareerSiteResearch/`, `/talentcommunity/`, `/NVIDIARecruitAds/`, `/refreshFacet/`.

| URL | Verdict | Deciding rule |
|---|---|---|
| `https://jobs.nvidia.com/api/pcsx/search?domain=nvidia.com&query=&location=&start=0&sort_by=timestamp` | ALLOW | `Allow: /api/pcsx` |
| `…/api/pcsx/search?…&filter_job_type=intern+%28fixed+term%29` | ALLOW | `Allow: /api/pcsx` |
| `https://jobs.nvidia.com/api/pcsx/position_details?position_id=893397606507&domain=nvidia.com&hl=en` | ALLOW | `Allow: /api/pcsx` |
| `https://jobs.nvidia.com/careers` and `/careers/job/893397606507` | ALLOW | `Allow: /careers` |
| `https://jobs.nvidia.com/api/suggest?term=…` (location autocomplete) | **BLOCK** | `Disallow: /`. Don't use. |
| `https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs` (and `/job/…` detail) | ALLOW | no matching rule |
| `https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/Israel-Yokneam/DevOps-Engineer--DOCA_JR2023758` | ALLOW | no matching rule |
| `https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/siteMap.xml` | ALLOW | `Allow: /NVIDIAExternalCareerSite/` |
| `https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSiteResearch/` | **BLOCK** | `Disallow: /NVIDIAExternalCareerSiteResearch/` (a hidden research site; not used) |
| `https://nvidia.wd5.myworkdayjobs.com/refreshFacet/…` | **BLOCK** | `Disallow: /refreshFacet/` |

## Anti-bot / quirks
- No bot challenge on either host. The page loads an invisible reCAPTCHA, but the API doesn't need it.
- Rate limit: 24 PCSX requests at 2.5–3.6 s spacing got no 429. Microsoft's identical Eightfold PCSX returned 429 at 1.1 s spacing, so use `min_interval: 3.0` for this host (276 pages ≈ 14 min for the daily full scan).
- Workday CXS caps `total` at 2000 and wraps at offset 2000 (see above). Never point the plain `workday` adapter at the whole NVIDIA site.
- `postedTs` is date-only. It's refreshed on reposts, so `creationTs` ≤ `postedTs`.
- The bookmark's US-intern view (49) uses `location=United States` with `filter_include_remote=1`. The worldwide intern filter (176) is the right quick query; our location filters do the rest.

## Recommended checker
```yaml
- key: nvidia
  name: NVIDIA
  category: semiconductors
  careers_url: https://jobs.nvidia.com/careers
  checker: eightfold
  settings: {host: jobs.nvidia.com, domain: nvidia.com, api: pcsx, min_interval: 3.0,
             quick_queries: [{filter_job_type: "intern (fixed term)"}]}
  big: true                 # 276 pages; newest-first quick scans + intern query each poll, full scan daily
  timeout_minutes: 20
  # optional cross-check of the intern slice against the system of record (9 requests):
  # workday {host: nvidia.wd5.myworkdayjobs.com, tenant: nvidia, site: NVIDIAExternalCareerSite,
  #          facets: {workerSubType: ["0c40f6bd1d8f10adf6dae42e46d44a17"]}}   # Intern (Fixed Term) = 176
```

## Evidence
- Sample: `discovery/samples/nvidia.json` (49 KB): the raw PCSX unfiltered page 1 (count 2757, filterDef), raw `position_details` (extra media trimmed), and the raw Workday CXS unfiltered page 1 with facets (total 2000).
- Requests: 39 scripted requests, including 2 robots.txt fetches (24 to jobs.nvidia.com, 15 to nvidia.wd5.myworkdayjobs.com), 1 Playwright page load (6 same-host XHRs), and 2 `robots_check.py` runs. PCSX: unfiltered, 4 job-type counts (the intern one is also page 1 of the intern slice), 17 more intern pages, 1 id query. Workday: unfiltered, sitemap, intern facet 9 pages, `searchText=intern`, offset 2000, 1 id search.
- Old capture: `discovery/captures/nvidia/` (bookmark view: 49 US interns).
