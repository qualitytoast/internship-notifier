# Palo Alto Networks (`palo-alto-networks`)

**Status:** verified-feed (Workday is the complete source; the Radancy front shows a subset)   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://jobs.paloaltonetworks.com/en/search-jobs (Radancy / TalentBrew, org id `47263`). The bookmark `/en/search-jobs/intern/47263/1` is a keyword search that returns 5 jobs, none of them internships. |
| Hiring system | **Workday**, tenant `paloaltonetworks` on `wd5`, site **`panwexternalcareers`**. Each Radancy job page carries the JR id (JSON-LD `identifier` "Job ID") and a Workday apply link `…/panwexternalcareers/job/<loc>/<slug>_JR-…/apply`. **Student roles are also on RippleMatch:** the "Search Internship Openings" button on https://jobs.paloaltonetworks.com/en/early-in-career goes to `https://app.ripplematch.com/v2/public/company/palo-alto-networks?tl=298554f5` (company id **676**). |
| Recommended adapter | `custom:panw` = the shared **`workday`** adapter (`panwexternalcareers`) **plus** a RippleMatch reader (company 676). This is the same pattern as `custom:ebay` (see ebay.md). |

## Sources compared
| Source | Total (2026-10-20 00:40–00:50 UTC) | Notes |
|---|---|---|
| Workday CXS `POST https://paloaltonetworks.wd5.myworkdayjobs.com/wday/cxs/paloaltonetworks/panwexternalcareers/jobs` | **1423** | 72 pages × 20, 1423 unique `externalPath` and JR ids. workerSubType: Regular 1380, **Intern 23**, Non-Entity Contractor 20. |
| Radancy page https://jobs.paloaltonetworks.com/en/search-jobs | **1312** | "1312 search results", `data-total-results="1312"`. The JSON results endpoint (3 × 500) gave 1312 unique `data-job-id`s. |
| RippleMatch `GET https://app.ripplematch.com/api/v2/public/roles/676` | **8** | The company page shows "Jobs (8)": 3 `Internship` and 5 `Full-Time Job` early-career roles. |

**Why Radancy shows 111 fewer:**
- **Radancy carries none of the 23 Workday intern postings.**
  - Keyword search "intern" returns 5 non-intern jobs, such as "Senior Program Specialist - Intern & Keep Warm Programs".
  - Radancy's category facet has no intern category, while Workday's jobFamilyGroup has `Intern Function` 23.
  - A Radancy keyword search for JR-011570 ("Intern - Software Engineer") returns 0.
- **Spot checks by JR id.** Radancy's search matches the JR id, and its titles often differ from Workday's.
  - Workday → Radancy: of 5 non-intern Workday postings whose title never appears on Radancy, 2 are absent (JR-020614, JR-012285). The other 3 are present under different titles. For example, JR-008572 is "Regional Sales Manager, Network Security" on Workday and "Prisma Browser Sales Specialist" on Radancy.
  - Radancy → Workday: 4 Radancy jobs whose titles never appear on Workday were all found in Workday by JR id, again under different titles. For example, JR-014864 is "Professional Service Staff Consultant - Cortex XSIAM" on Radancy and "Technical Lead - Cortex XSIAM" on Workday.
- **Conclusion:** Radancy is a subset of Workday that is filtered or behind, and it drops the student postings. Workday CXS is the complete source.
- I could not read the Workday site's own count: its HTML path is robots-disallowed (see below), so I did not render it.

## Recommended feed
1. **Workday (all jobs):** `POST https://paloaltonetworks.wd5.myworkdayjobs.com/wday/cxs/paloaltonetworks/panwexternalcareers/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`. That is 72 requests per full run.
   - **CXS cap warning:** 1423 is not far below the 2000-result cap. Past 2000, CXS `total` stops at 2000 and offsets wrap to page 1. The checker should alert when `total >= 1900` and then split by facet, for example `jobFamilyGroup` (Engineering Function 332, …) or `locationMainGroup`.
   - Intern-only facet (optional fast path): `{"appliedFacets":{"workerSubType":["<id of 'Intern'>"]}}` returned 23. Take the id from the first page's `facets[workerSubType].values[].id`.
2. **RippleMatch (student roles):** `GET https://app.ripplematch.com/api/v2/public/roles/676` returns a JSON list with no pagination. Use `name`, `public_id`, `job_type` (`Internship` / `Full-Time Job`) and `formatted_locations`. The job URL is `https://app.ripplematch.com/v2/public/job/{public_id}`.
   - The company id comes from `GET https://app.ripplematch.com/api/v2/company-branded-page/palo-alto-networks`. The company page made both calls when I rendered it once in a browser.
   - **TLS:** app.ripplematch.com omits its Sectigo DV R36 intermediate certificate, so httpx with certifi fails. ebay.md gives the fix (add the intermediate, or use truststore).
3. Optional cross-check: the Radancy JSON `GET https://jobs.paloaltonetworks.com/en/search-jobs/results?ActiveFacetID=0&CurrentPage=N&RecordsPerPage=500&…&SearchResultsModuleName=Section+29+-+Search+Results&SearchFiltersModuleName=Section+29+-+Search+Filters&SearchType=5`, with header `X-Requested-With: XMLHttpRequest`. It returns `{"results": "<html>", "filters": …}`, and cards are `a.section29__search-results-link[data-job-id]`. It is HTML in JSON, has no JR id, and is incomplete, so use it only as a cross-check.

## Field map (Workday)
Standard CXS: `title`, `externalPath`, `locationsText` ("2 Locations" for multi-location jobs), `postedOn` (relative), and `bulletFields[0]` = JR id (`JR-023090`).
- Job URL: `https://paloaltonetworks.wd5.myworkdayjobs.com/en-US/panwexternalcareers<externalPath>`. This is an email link only, because the `/panwexternalcareers/` HTML is robots-disallowed.
- The Radancy page for a job has no URL derivable from Workday data: it uses Radancy's own numeric id (`/en/job/<city>/<slug>/47263/<radancy-id>`).

## Totals (observed 2026-10-20)
- **Feed, no filters:** Workday **1423** + RippleMatch **8** roles.
- **Live careers page, no filters:** Radancy **1312** (Playwright render: "1312 search results"). RippleMatch company page "Jobs (8)".
- **Intern/student:** **24** on Workday, plus **3** RippleMatch internships.
  - Workday: 23 with workerSubType `Intern`, which is 22 "Intern …" titles plus JR-013641 "Strategy Extern". Add JR-010192 "Intern - Security Researcher - PhD Pipline", whose subtype is not Intern. "Senior Program Specialist - Intern & Keep Warm Programs" is a staff role and is excluded.
    - Most are "Intern - Software Engineer" (×9, Santa Clara HQ) and "Intern Sales" / "Sales Engineer - Intern" (Texas).
    - All are "Posted 30+ Days Ago" (JR-0113xx–0116xx, JR-0136xx), so they look like evergreen pipeline requisitions.
  - RippleMatch: "Intern - Security Researcher (PhD)", "Intern - Software Engineer (Bachelors)" and "Intern - Software Engineer (Masters)", all Santa Clara. These are probably the same programmes as the Workday requisitions under different ids; the filter will treat them as separate jobs.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `https://paloaltonetworks.wd5.myworkdayjobs.com/wday/cxs/paloaltonetworks/panwexternalcareers/jobs` | ALLOW | No matching rule. The tenant's robots.txt has `Disallow: /panwexternalcareers/`, `/hidden-private-pawn-temp-gateway-147258369/` and `/refreshFacet/`, and none of them match `/wday/cxs/…`. |
| `https://paloaltonetworks.wd5.myworkdayjobs.com/panwexternalcareers` (HTML site) | **BLOCK** | `Disallow: /panwexternalcareers/`. I never fetched or rendered it; it is a link target only. |
| `https://jobs.paloaltonetworks.com/en/search-jobs` and `/en/search-jobs/results?…` | ALLOW | No matching rule. The only rule is `Disallow:/search-jobs/`, which is root-anchored, so `/en/…` is not covered. |
| `https://jobs.paloaltonetworks.com/en/job/…`, `/en/early-in-career` | ALLOW | no matching rule |
| `https://app.ripplematch.com/api/v2/public/roles/676` | ALLOW once TLS is fixed | robots.txt is `User-agent: *` / `Allow: /` (read with curl). `robots_check.py` prints BLOCK (unreachable) only because of the TLS chain. |

**Judgement call for the reviewer:** the tenant hides its Workday HTML site from crawlers (the same pattern as Brevan Howard), but the CXS JSON path is allowed by RFC 9309 matching. Unlike Brevan Howard's Phenom, the Radancy front here is incomplete and drops every intern posting, so Workday CXS is the only complete route. If the project prefers to honour the tenant's intent strictly, the fallback is Radancy (1312, no interns) plus RippleMatch (8 roles, 3 internships).

## Anti-bot / quirks
- No challenge on Workday, Radancy or RippleMatch.
- Radancy titles drift from Workday titles. Key on the JR id, never on title.
- RippleMatch renders fire analytics POSTs (`/api/v2/activity-logs/client`). The checker must call only the JSON GET and never render the page.

## Recommended checker
```yaml
- key: palo-alto-networks
  name: Palo Alto Networks
  adapter: custom:panw              # = workday adapter + RippleMatch reader, results merged
  careers_url: https://jobs.paloaltonetworks.com/en/search-jobs
  settings:
    workday:
      host: paloaltonetworks.wd5.myworkdayjobs.com
      tenant: paloaltonetworks
      site: panwexternalcareers
    ripplematch:
      company_id: 676               # GET https://app.ripplematch.com/api/v2/public/roles/676
      job_url: https://app.ripplematch.com/v2/public/job/{public_id}
      extra_ca_pem: Sectigo Public Server Authentication CA DV R36
  health:
    workday_total_alert: 1900       # CXS caps at 2000; split by facet before then
```

## Evidence
- Sample: `discovery/samples/palo-alto-networks.json` is the raw Workday CXS first page (offset 0) with facets, 52 KB.
- Capture: `discovery/captures/palo-alto-networks/` (bookmark keyword "intern", Radancy).
- Requests:
  - Workday CXS: 75 (72 pages, the first page twice, 2 intern-facet pages).
  - jobs.paloaltonetworks.com: 17 (3 results pages of 500, 7 JR-id keyword searches, 5 job pages, home, early-in-career).
  - 3 Playwright renders: search, intern bookmark, and the RippleMatch company page.
  - All at ≤1 request/second per host.
