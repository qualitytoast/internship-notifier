# General Motors (`general-motors`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://search-careers.gm.com/en/jobs/ (bookmark: the same page with `search=intern`, US+Canada, `team=Students & Recent Graduates`). The site also has `/es/trabajos/`, `/fr-ca/emplois/`, `/kr/jobs/`, `/zh/工作/` and `/pt/cargos/` cultures. |
| Hiring system | **Workday**, tenant `generalmotors`, site `Careers_GM`, host `generalmotors.wd5.myworkdayjobs.com`. search-careers.gm.com is an Umbraco "jobboard" marketing site, the same platform as jobs.fidelity.com and pinterestcareers.com. Its job ids are Workday requisition numbers (`/en/jobs/jr-202622143/2027-summer-intern-seam-embodied-ai-phd/` = `JR-202622143`). |
| Recommended adapter | shared `workday` adapter |

## Recommended feed
- **Request:** `POST https://generalmotors.wd5.myworkdayjobs.com/wday/cxs/generalmotors/Careers_GM/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}`
- **Headers:** `Content-Type: application/json`, `Accept: application/json`, browser UA. No cookies needed. All 42 pages returned 200 to plain httpx.
- **Pagination:** offset in steps of 20 up to `total` (830 means 42 pages). `total` is only in the first page.
- **Other sites on the tenant** (from robots.txt `Sitemap:` lines): `Careers_TEI` has 2 jobs, and both are also in Careers_GM (JR-202612722, JR-202620534). `Careers_GM_Private` has 0. Watching only Careers_GM is enough.
- **Do not use the marketing site.** Plain httpx gets a Cloudflare "Just a moment..." challenge (403) on `search-careers.gm.com`. Headless Chromium rendered it, and that was used only to read its count.

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `jobPostings[].externalPath` | e.g. `/job/Sunnyvale-California-United-States-of-America/XMLNAME-2027-Summer-Intern--SEAM--Embodied-AI_JR-202622143`. `bulletFields[0]` is the requisition `JR-…`, unique across the 830. Some paths have a `-1` repost suffix. |
| title | `jobPostings[].title` | Many intern paths carry an `XMLNAME-` prefix in the slug. The title itself is clean. |
| location(s) | `jobPostings[].locationsText` | "Warren, Michigan, United States of America", "5 Locations" (use detail for the list) |
| url | `https://generalmotors.wd5.myworkdayjobs.com/en-US/Careers_GM` + `externalPath` | Marketing copy: `https://search-careers.gm.com/en/jobs/<jr-id lowercase>/<slug>/` |
| posted date | `jobPostings[].postedOn` | relative ("Posted Today": 59 on 2026-10-19) |
| employment type | facet only | `workerSubType`: Regular 758, Intern (Fixed Term) (Trainee) 58, Co-Op (Fixed Term) 8, Casual 3, Apprentice (Fixed Term) 1, Fixed Term 1, Temporary 1. `remoteType` is in the list items. `bulletFields[1]` is Exempt/Non-Exempt for US jobs. |
| department | facet `jobFamilyGroup` / `jobFamily` | `jobFamily` "Student Intern" = 66 |

## Totals (observed 2026-10-19/20)
- **Feed, no filters:** **830**. All 42 pages were fetched: 830 postings, 830 unique requisitions (the earlier agent saw 829 about 30 minutes before).
- **Live careers page, no filters:** **821**, "Showing 1 to 20 of 821 matching jobs" in a Playwright render of `/en/jobs/`. The earlier agent saw the same 821 about 30 minutes before. The page is fresh: all 20 jobs on its first page are "Posted Today" in Workday.
- **Difference (9), all in the US:** `/en/jobs/?country=United+States+of+America` shows **700**, while CXS has US 709. 700 is exactly CXS `hiringCompany` = "General Motors LLC" (700). The other 9 US postings are:
  - 3 "Cruise LLC" postings: AV Operations Coordinator, Senior Manager AI Deployment, Staff Research Scientist
  - 6 postings with no hiring company

  The marketing site evidently imports only postings that have a recognised GM company. Workday is the complete list, so the checker should use it. Outside the US the totals agree: site 821 − 700 = 121, and CXS 830 − 709 = 121. I did not compare country by country.
- **Intern/student:** **68** by the title rule. The facets agree closely: `workerSubType` Intern 58 + Co-Op 8 + Apprentice 1 = 67, and `jobFamily` "Student Intern" = 66. The title count also catches a few Regular-type roles with intern titles abroad: Australia "Planning Co-Op", "HSPO Warehouse Operations & Logistics Intern", "Sales & Distribution Operations Intern", and Shanghai "Aftersales Service Parts Data Intern". Most are "2027 Summer Intern – …", many in Sunnyvale (Embodied AI, AV/AI Platform) and Warren (R&D, Digital Product). There is one stale term, "Fall 2026 PhD Battery & Sustainability Intern".

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://generalmotors.wd5.myworkdayjobs.com/wday/cxs/generalmotors/Careers_GM/jobs` | ALLOW | no matching rule (`Allow: /Careers_GM/`, `/Careers_GM_Private/`, `/Careers_TEI/`; `Disallow: /refreshFacet/`) |
| `https://generalmotors.wd5.myworkdayjobs.com/en-US/Careers_GM/job/...` | ALLOW | no matching rule |
| `https://search-careers.gm.com/en/jobs/` | ALLOW | `Allow: /` for `*` (job paths are disallowed only for named SEO bots such as SemrushBot and AhrefsBot) |

## Anti-bot / quirks
- search-careers.gm.com is behind a Cloudflare challenge for non-browser clients. The Workday host is also behind Cloudflare but answers CXS POSTs normally.
- `externalPath` slugs carry `XMLNAME-` prefixes and `-1`/`-2`/`-3` repost suffixes. Key on the path, and use `JR-…` from `bulletFields[0]` as the stable requisition id (the adapter puts it in `alt_ids`).

## Recommended checker
```yaml
- key: general-motors
  name: General Motors
  adapter: workday
  settings:
    host: generalmotors.wd5.myworkdayjobs.com
    tenant: generalmotors
    site: Careers_GM
  careers_url: https://search-careers.gm.com/en/jobs/
```

## Evidence
- Sample: `discovery/samples/general-motors.json` is the first CXS page with all facets (20 postings, 58 KB).
- Capture: `discovery/captures/general-motors/` (bookmark: "of 66" student roles).
- Requests: 42 CXS pages, 3 facet-filtered CXS calls (US, Cruise LLC, and the TEI/Private sites), and 2 Playwright renders (`/en/jobs/` and the US filter). The earlier agent also made 3 CXS calls and 1 render.
