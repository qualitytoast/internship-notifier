# Capstone (`capstone`) — two different companies

**Status:** verified-feed (both)   ·   **Checked:** 2026-10-20 (00:15–00:30 UTC)

The bookmark and the seed name point at **two unrelated firms**:

| | Capstone Investment Advisors (seed name) | Capstone DC / Capstone LLC (bookmark) |
|---|---|---|
| What | New York derivatives / volatility asset manager ("Capstone Hedge", ">300 employees, 11 offices") | Washington-DC policy research & strategy firm ("Predict Policy. Quantify Impact. Create Strategy") |
| Careers page | https://www.capstoneco.com/careers/ | https://capstonedc.com/about/careers/ |
| Hiring system | Greenhouse board **`capstoneinvestmentadvisors`**, embedded on the careers page as `job-boards.greenhouse.io/embed/job_board?for=capstoneinvestmentadvisors` | Workday **`capstonedc.wd501.myworkdayjobs.com/Capstone`**, linked from the careers page. The bookmark was `…/Capstone?q=intern`. |
| Jobs / interns | **16 / 8** (all "Summer 2027 - … Internship") | **14 / 0** |

Both are live and current. Each is the only board of its own company.
- The key `capstone` is filed under category "quant" with name "Capstone Investment Advisors", so its primary source is the Greenhouse board.
- The bookmarked Workday site belongs to a different firm. It is listed below as a second entry `capstone-dc`, so the user can keep it or drop it.
- The bookmark's search `q=intern` matched 2 non-internships ("Senior Associate, European Energy Policy & Investment", "Vice President, Accounting"), probably on description text. Capstone DC has no internships open.

## Capstone Investment Advisors — recommended feed
- **Request:** `GET https://boards-api.greenhouse.io/v1/boards/capstoneinvestmentadvisors/jobs`. No pagination. `company_name` = "Capstone Investment Advisors".
- **Field map:** the standard Greenhouse list: `id`, `title` (some have trailing spaces, so trim), `location.name` ("New York, New York", "London, England", "London, New York"), `absolute_url` (`https://job-boards.greenhouse.io/capstoneinvestmentadvisors/jobs/<id>`), `first_published`. There is no employment-type metadata; titles carry "Internship".
- **Totals:**
  - Feed **16** (`meta.total` 16).
  - Page **16**: the Greenhouse embed document loaded by a Playwright render of capstoneco.com/careers/ (2026-10-20) says "16 jobs" and has 16 job links.
  - Interns **8**:
    - New York: Execution Tech; Investment NYC; Marketing & Communications; Risk Tech (London, New York)
    - London: Investment LDN; Quant; Risk; Tech Enterprise
- **Quirk:** www.capstoneco.com sends plain HTTP a **Cloudflare 403 challenge** ("Just a moment…"). A normal headless browser renders the page. The checker never needs the site: it uses the Greenhouse API.

## Capstone DC — recommended feed (second entry `capstone-dc`)
- **Request:** `POST https://capstonedc.wd501.myworkdayjobs.com/wday/cxs/capstonedc/Capstone/jobs` with body `{"appliedFacets":{},"limit":20,"offset":0,"searchText":""}` and `Content-Type: application/json`. Use the shared `workday` adapter. `total` = 14 at offset 0. Facets: `workerSubType`, `timeType`, `locationMainGroup`.
- **Field map:** `jobPostings[].title`, `externalPath` (`/job/Washington-DC/Associate--Outreach---Events_JR100040` → `https://capstonedc.wd501.myworkdayjobs.com/Capstone` + path), `locationsText` ("Washington, DC" / "2 Locations"), `postedOn` (relative, e.g. "Posted 14 Days Ago"), `bulletFields[0]` = requisition id `JR1000NN`.
- **Totals:**
  - Feed **14**.
  - Page **14**: a Playwright render of `https://capstonedc.wd501.myworkdayjobs.com/Capstone` showed "14 JOBS FOUND" and "of 14", with 14 job links.
  - Interns **0**. "Research Analyst Associate Program (Summer 2027 Start)" is a full-time analyst programme, not an internship.
- capstonedc.com itself: `/careers/` is a 301 to the home page. The real page is `/about/careers/`, which links the Workday site.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/capstoneinvestmentadvisors/jobs | ALLOW | no matching rule |
| https://www.capstoneco.com/careers/ | ALLOW | no matching rule (Cloudflare challenge for plain HTTP) |
| https://capstonedc.wd501.myworkdayjobs.com/wday/cxs/capstonedc/Capstone/jobs | ALLOW | no matching rule (robots: `Allow: /Capstone/`, `Disallow: /refreshFacet/`) |
| https://capstonedc.com/about/careers/ | ALLOW | no matching rule |

## Recommended checker
```yaml
- key: capstone
  name: Capstone Investment Advisors
  adapter: greenhouse
  settings: {board: capstoneinvestmentadvisors}
  careers_url: https://www.capstoneco.com/careers/

- key: capstone-dc            # the bookmarked site; different company (policy research, Washington DC)
  name: Capstone DC
  adapter: workday
  settings: {host: capstonedc.wd501.myworkdayjobs.com, tenant: capstonedc, site: Capstone}
  careers_url: https://capstonedc.com/about/careers/
```

## Evidence
- Sample: `discovery/samples/capstone.json` (both raw responses: the Greenhouse list and the Workday CXS page 0).
- Capture of the bookmark: `discovery/captures/capstone/` (Workday `q=intern`, 2 results).
