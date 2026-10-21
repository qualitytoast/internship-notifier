# Procore (`procore`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://careers.procore.com/jobs/search (bookmark: the same page filtered to US+CA and three `dropdown_field_1_uids`). It is a **Clinch** career site (`clinchtalent.com` assets) behind **AWS WAF**: the page runs `*.edge.sdk.awswaf.com` `mp_verify`/telemetry challenges. Job pages are `https://careers.procore.com/jobs/<slug>`, e.g. `/jobs/director-emea-field-marketing-dublin-ireland`. |
| Hiring system | **Workday**, tenant `procore`, host **`procore.wd12.myworkdayjobs.com`**, site `Procore_External_Careers`. Its robots.txt lists only this site. |
| Recommended adapter | shared `workday` adapter |

## How the hiring system was found
- Probes of `procore.wd{1,3,5,103}.myworkdayjobs.com/robots.txt` answered 422 (no tenant). `procore.wd12.myworkdayjobs.com/robots.txt` answered 200 with `Sitemap: …/Procore_External_Careers/siteMap.xml` and `Allow: /Procore_External_Careers/`.
- The Clinch job page's "Apply Now" is an in-page Clinch form (`href="#apply"`), so the site never links to Workday directly. The match is shown by the data instead: **112 = 112**, and all 30 titles on Clinch page 1 are exact matches for Workday titles.
- The Greenhouse tokens `procore` and `procoretechnologies` and the Workable token `procore` all have 0 jobs (probe).

## Recommended feed
- **Request:** `POST https://procore.wd12.myworkdayjobs.com/wday/cxs/procore/Procore_External_Careers/jobs` with body `{"appliedFacets":{},"limit":20,"offset":N,"searchText":""}` and headers `Content-Type: application/json`, `Accept: application/json`
- **Pagination:** offset in steps of 20 up to `total` (112 means 6 pages). Plain httpx got 200 on all pages. The wd12 data centre did not rate-limit this tenant, unlike Salesforce's on the same data centre.
- **Public job link:** `https://procore.wd12.myworkdayjobs.com/en-US/Procore_External_Careers<externalPath>`. The Clinch copy is `https://careers.procore.com/jobs/<slug>`, which is not derivable from Workday data.

## Totals (observed 2026-10-20)
- **Feed, no filters:** **112** (112 unique paths).
- **Live careers page, no filters:** **112**, "Displaying 1 - 30 of 112 in total" in a Playwright render of `/jobs/search`. Its country facets sum to 117 (US 65, India 16, Ireland 13, Egypt 8, UK 5, Australia 3, Costa Rica 3, Canada 2, NZ 1, Norway 1), probably because jobs in several countries count once per country.
- **Intern/student:** **0**. `workerSubType` is Regular 111 and Fixed-Term 1, and no title matches. The bookmark's `dropdown_field_1` filter appears to be a team filter: its 18 US results in the capture were all regular engineering and IT roles.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://procore.wd12.myworkdayjobs.com/wday/cxs/procore/Procore_External_Careers/jobs` | ALLOW | no matching rule (`Allow: /Procore_External_Careers/`, `Disallow: /refreshFacet/`) |
| https://careers.procore.com/jobs/search | ALLOW | no matching rule |

## Anti-bot / quirks
- careers.procore.com runs an AWS WAF JavaScript challenge. It was only rendered in Playwright to read the count, and the checker does not need it.
- Workday postings use `locationsText` like "NZ - New Zealand" / "US Remote, TX".

## Recommended checker
```yaml
- key: procore
  name: Procore
  adapter: workday
  settings:
    host: procore.wd12.myworkdayjobs.com
    tenant: procore
    site: Procore_External_Careers
  careers_url: https://careers.procore.com/jobs/search
```

## Evidence
- Sample: `discovery/samples/procore.json` is the first CXS page with facets (13 KB).
- Capture: `discovery/captures/procore/` (bookmark, filtered, 18 US items).
- Requests: 5 Workday robots probes, 6 CXS pages, and 2 Playwright renders (the search page and one job page).
