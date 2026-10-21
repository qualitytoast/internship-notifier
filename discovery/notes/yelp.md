# Yelp (`yelp`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20 (UTC)

| | |
|---|---|
| Official careers URL | https://www.yelp.careers/us/en/search-results (the bookmark adds `?keywords=intern`) |
| Hiring system | **Phenom People** career site (refNum `YELPUS`), over **iCIMS** with two portals: `uscareers-yelp.icims.com` (US) and `cancareers-yelp.icims.com` (Canada). Every Phenom job's `applyUrl` is the iCIMS job page. A `de/de` Phenom locale exists, but it is only a German UI over the **same 20 jobs** (same jobIds, `jobSeqNo` ending `EXTERNALDEDE`). |
| Recommended adapter | shared **`phenom`**, one call. The iCIMS HTML lists (shared `icims` adapter, 2 portals) are an equal cross-check. |

## Phenom vs iCIMS: which to use
| | Phenom `POST /widgets` refineSearch | iCIMS hosted search `/jobs/search?ss=1&in_iframe=1` |
|---|---|---|
| Format | JSON | HTML cards |
| Calls | 1 (both portals together) | 1 per portal (US 17, Canada 2) |
| Total on 2026-10-20 | 20 | 19 |
| Freshness | 1 stale job: 14077 "Sales Enablement Manager, Multi Location Sales - US - Remote" is still listed, but its iCIMS page returns **HTTP 410** "no longer open" | system of record |
| robots | ALLOW | ALLOW (only referral/login/candidate/connect paths are disallowed) |

**Pick Phenom.** It is JSON, takes one request, and automatically covers any new portal Yelp adds. It is a superset of iCIMS: all 19 iCIMS jobs are in Phenom. The cost is that a closed job can linger for a while, which does not matter for a new-postings watcher. Use iCIMS as the optional cross-check.

## Recommended feed
- **Request:** `POST https://www.yelp.careers/widgets` with headers `Content-Type: application/json` and `Accept: application/json`. No cookies or CSRF token.
- **Body (tested):**
  ```json
  {"lang":"en_us","deviceType":"desktop","country":"us","pageName":"search-results","ddoKey":"refineSearch",
   "from":0,"size":100,"jobs":true,"counts":true,"all_fields":["category","country","state","city","type"],
   "selected_fields":{},"keywords":"","global":true,"sortBy":"","subsearch":"","clearAll":false,
   "jdsource":"facets","isSliderEnable":false,"siteType":"external","refNum":"YELPUS"}
  ```
- **Response:** `refineSearch.totalHits` (20), `refineSearch.hits` (20 on this page), `refineSearch.data.jobs[]`, and `refineSearch.data.aggregations[]` (facets).
- **Pagination:** `from` / `size`. A single call with `size >= totalHits` is safest, because Phenom's relevance order is not stable between calls (see adobe.md). `size=500` and `size=1000` work on other Phenom tenants (Adobe, Snowflake).

## Field map
Paths are relative to `refineSearch.data.jobs[]`.

| Job field | Response path | Notes |
|---|---|---|
| id | `jobId` (= `reqId` = iCIMS job id, e.g. `14067`) | `jobSeqNo` = `YELPUS14067EXTERNALENUS` is also unique |
| title | `title` | |
| location(s) | `multi_location[]` (`"City, State, Country"`) | All 20 jobs are multi-location; one has 19 cities. Primary: `location`, `city`, `state`, `country`. |
| url | built: `https://www.yelp.careers/us/en/job/{jobId}/{slug}` with `slug = re.sub('[^A-Za-z0-9]+','-',title).strip('-')` | matches the page's links, e.g. `/us/en/job/14067/Inside-Sales-Representative-Remote-Central-Region` |
| apply url | `applyUrl` | iCIMS `https://uscareers-yelp.icims.com/jobs/14067/<slug>/job` (also `cancareers-yelp`) |
| posted date | `postedDate` | also `dateCreated` |
| description / snippet | `descriptionTeaser` | |
| employment type | `type` | `Regular (Full-Time)`, `Regular (Part-Time)` |
| department | `category` / `multi_category[]` | Sales & Customer Success, Engineering, … |

## Totals (observed 2026-10-20 00:22–00:26 UTC)
- **Feed, no filters:** **20**. `totalHits` was 20 in both `en_us` and `de_de`, with the same jobIds.
- **Live careers page, no filters:** **20**. A Playwright render of https://www.yelp.careers/us/en/search-results showed "20 Results".
- **iCIMS cross-check:**
  - uscareers-yelp.icims.com: "Page 1 of 1", 17 jobs.
  - cancareers-yelp.icims.com: 2 jobs.
  - Total 19 = Phenom minus 14077, which returns 410 on iCIMS.
- **Intern/student:** **0**. No intern titles today; the bookmark `keywords=intern` matched 3 jobs, which are not internships. Yelp posts summer internships in this same feed when they open.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| `POST https://www.yelp.careers/widgets` | ALLOW | no matching rule. `*/px-widgets`, `*/apply`, `*/jobcart`, … are disallowed, but not `/widgets`. |
| `https://www.yelp.careers/us/en/search-results`, `/us/en/job/14067/…` | ALLOW | no matching rule |
| `https://uscareers-yelp.icims.com/jobs/search?ss=1&in_iframe=1` (+ `&pr=N`), `/jobs/<id>/<slug>/job` | ALLOW | no matching rule (only `/jobs/*login`, `*referral`, `*candidate`, `/connect…` are disallowed) |
| `https://cancareers-yelp.icims.com/jobs/search?ss=1&in_iframe=1` | ALLOW | no matching rule |
| `https://www.yelp.careers/us/en/apply?…` | **BLOCK** | `Disallow: */apply`. Link only. |

## Anti-bot / quirks
- There was no challenge on www.yelp.careers or on iCIMS.
- On first load the page renders 10 jobs server-side and calls `eagerLoadRefineSearchSession`, which returns no jobs. `ddoKey: "refineSearch"` is the call that returns the data.
- The `de_de` locale returns the same jobs. Do not fetch both, or every job will appear twice with different `jobSeqNo`.

## Recommended checker
```yaml
- key: yelp
  name: Yelp
  adapter: phenom
  careers_url: https://www.yelp.careers/us/en/search-results
  settings:
    base_url: https://www.yelp.careers
    ref_num: YELPUS
    lang: en_us
    country: us
    site_type: external
    page_name: search-results
    job_path: /us/en/job/{jobId}/{slug}     # slug = re.sub('[^A-Za-z0-9]+','-',title).strip('-')
    page_size: 500                         # one call; page with `from` only if totalHits > page_size
  health:
    expect_total_field: refineSearch.totalHits
  # cross-check (optional): icims portals [https://uscareers-yelp.icims.com, https://cancareers-yelp.icims.com]
```

## Evidence
- Sample: `discovery/samples/yelp.json` is the full `refineSearch` response (size=100, en_us): 20 jobs plus facets. It was re-serialised with indentation, 90 KB.
- Capture: `discovery/captures/yelp/` (bookmark `keywords=intern`, 3 results).
- Requests: 2 refineSearch (en_us, de_de), 2 iCIMS lists and 1 iCIMS detail (14077 → 410), plus 1 Playwright render, at ≤1 request/second per host.
