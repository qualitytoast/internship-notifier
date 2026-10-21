# AQR Capital Management (`aqr`)

**Status:** verified-feed (the site search and Greenhouse hold the identical 56 jobs; use Greenhouse)   ·   **Checked:** 2026-10-20 (00:15–00:30 UTC)

| | |
|---|---|
| Official careers URL | https://careers.aqr.com/ (Laravel front-end with an Elastic App Search engine `jobs-production`). Job pages: `https://careers.aqr.com/jobs/<category>/<city>/<title-slug>/<greenhouse id>` |
| Hiring system | Greenhouse board **`aqr`**. The page also loads `boards.greenhouse.io/embed/job_board/js?for=aqr`, and Greenhouse `absolute_url`s point to `https://careers.aqr.com/jobs?gh_jid=<id>&gh_jid=<id>` (the param really is duplicated). |
| Recommended adapter | shared `greenhouse`, `{board: aqr}` |

## Site search API (checked, not needed)
- `POST https://careers.aqr.com/api/appSearch` needs Laravel Sanctum CSRF. Without it the response is **419**. With the page's flow it is 200: first `GET /sanctum/csrf-cookie` (204, sets `XSRF-TOKEN` and `laravel_session`), then the POST with header `X-XSRF-TOKEN: <url-decoded cookie>`.
  - Body: `{"query":"","page":{"size":100,"current":1},"filters":{"all":[{"any":[{"group_id":1551}]},{"any":[{"live":1}]}]}, "result_fields":{…}}`
  - Result: `meta.page.total_results` = **56** in one page. Each result `url.raw` ends with the Greenhouse id (e.g. `business-development/bengaluru/business-services-analyst/8289123`).
- **Id comparison:** the 56 appSearch ids are **identical** to the 56 Greenhouse ids (none only on one side).
- The page itself asks for only 5 results per page ("12 pages"). It also calls `GET /api/jobs?groupId=1551&groupBy=city|category&city_state=true` for the facet counts.

## Totals (observed)
- **Feed (Greenhouse):** **56**.
- **Page:** **56**.
  - The 2026-10-19 capture: appSearch `total_results` 56. The "Openings by team" counts add up to 56: Business Development 7, Compliance 9, Engineering 12, Global Trading 1, Legal 1, Operations 6, Research 7, Risk 1, University Jobs 12.
  - By location: Greenwich 40, Bangalore 13, Dubai 1, Hong Kong 1, London 1.
  - The 2026-10-20 appSearch call: 56.
- **Intern/student:** **9**, all Greenwich, CT. These are "2027 … Summer Analyst" (Business Development, Engineering, Portfolio Implementation, Quantitative Prediction Markets Research, Research and Portfolio Management Engineering, Research Product Specialist, Research, and AQR Arbitrage Research) and "2027 PhD Summer Associate, Machine Learning Research". They match filters.yaml `summer analyst` / `summer associate`; none of these titles contain "intern".

## robots.txt
`careers.aqr.com/robots.txt` = `User-agent: *` / `Disallow:` (empty), so everything is allowed.

| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/aqr/jobs | ALLOW | no matching rule |
| https://careers.aqr.com/api/appSearch | ALLOW | no matching rule |

## Recommended checker
```yaml
- key: aqr
  name: AQR
  adapter: greenhouse
  settings: {board: aqr}
  careers_url: https://careers.aqr.com/
```

## Evidence
- Sample: `discovery/samples/aqr.json` (the raw appSearch response with 100 results, plus the raw Greenhouse list).
- Capture: `discovery/captures/aqr/` (page, appSearch with 5 per page).
