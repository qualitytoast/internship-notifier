# Adobe (`adobe`)

**Status:** verified-feed (Workday)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://careers.adobe.com/us/en/search-results (Phenom front, refNum `ADOBUS`). Its jobs apply on the Workday site https://adobe.wd5.myworkdayjobs.com/external_experienced. |
| Hiring system | **Workday** tenant `adobe` on `wd5`. **One public site:** `external_experienced`. University and intern jobs are on the same site: jobFamilyGroup `University` 21, workerSubType `Intern (Fixed Term)` 21. Phenom (`careers.adobe.com`) is a marketing copy of that site. |
| Recommended adapter | shared **`workday`**, settings `{host: adobe.wd5.myworkdayjobs.com, tenant: adobe, site: external_experienced}` |

## Workday sites found
| Site | CXS `POST /wday/cxs/adobe/<site>/jobs` | Notes |
|---|---|---|
| `external_experienced` | **200, total 305** | The only site in `robots.txt` (`Allow: /external_experienced/` plus its `siteMap.xml`). All Phenom `applyUrl`s point here. |
| `external_university` | **403** `{"errorCode":"S22","message":"permission denied"}` | The site id exists but is not public, so it holds no reachable jobs. Campus jobs are on `external_experienced`. |
| `external`, `university` | 404 `not found: Job_Posting_Site_ID=…` | do not exist |

## Phenom vs Workday
- Phenom `POST https://careers.adobe.com/widgets` (refineSearch, `ADOBUS`, `en_us`/`us`) returns `totalHits` **300**. The page shows "300 results".
- Workday CXS returns **305**. The Workday site page shows "305 JOBS FOUND".
- Comparing ids (Phenom `jobId` = Workday req id `R…`):
  - **6 live Workday jobs are missing from Phenom.** All were posted 30+ days ago and are mostly remote or multi-location:
    - R170167 Senior Engineering Manager | iOS Video Applications (Remote California)
    - R170076 Senior AI Systems Engineer — C++ / Applied AI (6 locations)
    - R171338 Principal Program Manager, Frame.io (3 locations)
    - R171035 Principal Enterprise Architect (Remote Illinois)
    - R170086 Senior Front-end Engineer, AI (4 locations)
    - R167414 Technical Account Manager (2 locations)

    A Phenom keyword search for "Frame.io" does not find R171338.
  - **1 Phenom job is no longer public on Workday:** R170591 "Sr. Principal Scientist". CXS search returns 0, and its CXS detail returns 403 "permission denied".
- **Conclusion:** Workday is complete and current. Phenom lags in both directions. Use Workday.
- **Phenom paging warning (relevant to the shared `phenom` adapter):** three calls with `size=100` and `from` = 0/100/200 returned 300 rows but only **238 unique** jobs. The relevance order reshuffles between calls. One call with `size=500` returned all 300 unique jobs. The phenom adapter must use one call with `size >= totalHits`, or dedupe and verify against `totalHits`.

## Recommended feed
- `POST https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`. 16 pages today. `total` is only on the first page (305).
- This is well under the CXS 2000-result cap, so no facet splitting is needed.
- Detail (optional): `GET https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced<externalPath>`.

## Field map
Standard Workday CXS (see the `workday` adapter): `title`, `externalPath`, `locationsText`, `postedOn` (relative), and `bulletFields[0]` = req id (`R172265`). Adobe also returns `timeLeftToApply` and `jobPostingEndDateAsText` ("End Date: December 31, 2026").
- Job URL: `https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced<externalPath>`.
- Phenom equivalent: `https://careers.adobe.com/us/en/job/{reqId}/{slug}`. Tested: `/us/en/job/R170716/AI-Engineer-4` gives 200 with jobDetail.

## Totals (observed 2026-10-20 00:28–00:47 UTC)
- **Feed, no filters:** **305**. The `total` field is 305, and 16 pages gave 305 unique `externalPath`s and 305 unique req ids.
- **Live careers page, no filters:** **305**. A Playwright render of https://adobe.wd5.myworkdayjobs.com/external_experienced showed "305 JOBS FOUND" and "1 - 20 of 305 jobs". The Phenom front https://careers.adobe.com/us/en/search-results showed "300 results"; that is 6 missing and 1 stale, as above.
- **Intern/student:** **21**. The title regex finds 21, and the Workday facets agree: workerSubType `Intern (Fixed Term)` 21 and jobFamilyGroup `University` 21.
  - Most are "2027 Intern - …" or "2027 MBA Intern - …": Software Engineer, ML Engineer, Applied/Research Scientist, Security Engineer, Data AI & Innovation, Sales Velocity Analyst, and others.
  - Locations include San Jose, Lehi, New York, Yerevan, Bucharest, Basel and Bangalore.
  - 2 are German working-student roles (Munich).

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/jobs` | ALLOW | no matching rule (only `/refreshFacet/` is disallowed) |
| `https://adobe.wd5.myworkdayjobs.com/external_experienced` | ALLOW | `Allow: /external_experienced/` |
| `https://careers.adobe.com/widgets`, `/us/en/search-results` | ALLOW | no matching rule (cross-check only) |

## Anti-bot / quirks
- There was no challenge on Workday or Phenom.
- Workday `postedOn` is relative ("Posted 30+ Days Ago").
- Some `externalPath` slugs are stale. For example, R170076 is titled "Senior AI Systems Engineer…", but its path says `Principal-AI-Systems-Engineer…`.

## Recommended checker
```yaml
- key: adobe
  name: Adobe
  adapter: workday
  careers_url: https://careers.adobe.com/us/en/search-results
  settings:
    host: adobe.wd5.myworkdayjobs.com
    tenant: adobe
    site: external_experienced
  # cross-check (optional): phenom {base_url: https://careers.adobe.com, ref_num: ADOBUS, lang: en_us, country: us,
  #   site_type: external, page_name: search-results, job_path: /us/en/job/{jobId}/{slug}, page_size: 500} -> 300 today
```

## Evidence
- Sample: `discovery/samples/adobe.json` is the raw Workday CXS first page (offset 0, limit 20) with facets, 18 KB.
- Capture: `discovery/captures/adobe/` (Phenom search-results, "300 results").
- Requests:
  - adobe.wd5: 23 (16 CXS pages, 3 site-name probes, 2 searchText probes, 1 detail, …).
  - careers.adobe.com: 5 refineSearch calls (`size=100` ×3, `size=500`, keyword "Frame.io") and 1 job page.
  - 2 Playwright renders.
  - All at ≤1 request/second per host.
