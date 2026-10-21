# Veeva Systems (`veeva`)

**Status:** verified-feed. The careers site is a stale cached copy, so Lever is the complete source.   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://careers.veeva.com/job-search-results/. The bookmark filtered to `search=intern` and US + Canada, which shows "0 Results" today. |
| Hiring system | **Lever** site `veeva`. careers.veeva.com runs on WordPress and embeds a cached copy of the Lever postings in the search page as `let allJobs = [...]`.<br>- Fields: `id` (the WordPress id), `lever_id`, `job_title`, `team`, `region`, `city`, `country`, `remote`, `keywords`, `slug`.<br>- Job pages: `careers.veeva.com/job/<lever_id>/<slug>/?lever-source=veeva-career-site`.<br>- The Greenhouse tokens veeva, veevasystems and veeva-systems are empty. |
| Recommended adapter | shared `lever` adapter, `site: veeva` |

## Page vs feed (937 vs 935)
- The page shows "**937 Results**", and `allJobs` holds 937 unique `lever_id`s. Lever returned 935 on both fetches, 40 minutes apart.
- **930 ids are shared.**
- **7 are only on the page**, and they are closed in Lever:
  - The 7: "Account Partner - Development Cloud - Southern Europe" (Barcelona), 3× "Operations Manager - Global Business Consulting" (Boston, Philadelphia, Columbus) and 3× "Technical Consultant" (Raleigh, Madison, Boston).
  - For the 3 I checked, `GET https://api.lever.co/v0/postings/veeva/<id>` returns 404 `"Document not found"`. The WordPress cache is stale.
- **5 are only in Lever**:
  - "Director - QualityOne Strategy Operations", created 2026-10-19, after the last cache refresh.
  - The evergreen "General Application" from 2020.
  - 3× "Consultant - Site Solutions" (Raleigh, Philadelphia, Madison; created 2025-04 and 2026-04). The site leaves them out for a reason I couldn't see.
- **Decision:** Lever is current and complete. The net difference is 2, inside the ±2 tolerance.

## Recommended feed
- **Request:** `GET https://api.lever.co/v0/postings/veeva?mode=json`
- **Response:** a JSON array of every posting (935), **about 13 MB**, because it includes `description`, `descriptionPlain`, `lists` and `additional`. Lever returns everything without paging; `limit` and `skip` exist if you ever need them.
- **Rate:** Lever's robots.txt asks for `Crawl-delay: 1`. One call per run is fine.

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `[].id` (uuid) | the same as the page's `lever_id` |
| title | `[].text` | |
| location(s) | `[].categories.location` / `[].categories.allLocations`, plus `[].country` (ISO2) | e.g. "China - Shanghai", "Hungary - Budapest", "Massachusetts - Boston" |
| url | `[].hostedUrl` | `https://jobs.lever.co/veeva/<id>`. The public page is `https://careers.veeva.com/job/<id>/<slug>/`. |
| posted date | `[].createdAt` | epoch milliseconds |
| description / snippet | `[].descriptionPlain` + `[].additionalPlain` | |
| employment type | `[].categories.commitment` | Full-Time 929, **Internship 4**, Part-Time 1, Contractor 1 |
| department / team | `[].categories.department` / `[].categories.team` | |
| remote | `[].workplaceType` | remote 769, onsite 133, hybrid 33 |

## Totals (observed 2026-10-20)
- **Feed, no filters:** **935**.
- **Live careers page, no filters:** **937**. A Playwright render of https://careers.veeva.com/job-search-results/ showed "937 Results", and `allJobs` holds 937 entries.
- **Intern/student:** **4**, all with commitment "Internship". None are in the US or Canada today.
  - e7540220-… Associate Consultant (R&D), China - Shanghai. The title doesn't say intern; only the commitment does.
  - bd55ddbb-… Implementation Consultant Intern, China - Shanghai
  - 87ae81ed-… Intern Technical Consultant, China - Shanghai
  - f7cea665-… Technology Consulting Intern - Entry-Level, Hungary - Budapest

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://api.lever.co/v0/postings/veeva?mode=json | ALLOW | `Allow: /` (`Crawl-delay: 1`) |
| https://api.lever.co/v0/postings/veeva/<id> | ALLOW | `Allow: /` |
| https://careers.veeva.com/job-search-results/ | ALLOW | no robots.txt |

## Anti-bot / quirks
- None seen. careers.veeva.com serves its pages normally. The page's `allJobs` copy could be a fallback, but it lags Lever, so don't use it.
- Most postings are remote (769 of 935).

## Recommended checker
```yaml
- key: veeva
  name: Veeva Systems
  adapter: lever
  settings:
    site: veeva
  careers_url: https://careers.veeva.com/job-search-results/
```

## Evidence
- Sample: `discovery/samples/veeva.json` is the raw Lever response for `?mode=json&limit=2` (27 KB), showing the record shape. The full response is 13 MB.
- Capture: `discovery/captures/veeva/` (the bookmark's intern + US/Canada filter: "0 Results").
