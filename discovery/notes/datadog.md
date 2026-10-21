# Datadog (`datadog`)

**Status:** verified-feed. The page shows only English postings, so the feed is the complete source.   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://careers.datadoghq.com/all-jobs/ (the bookmark adds `?time_type[0]=Early Career`) |
| Hiring system | Greenhouse board `datadog`. The careers site is a custom front that searches a **Typesense** index built from the board. Index host `gk6e3zbyuntvc5dap.a1.typesense.net`, collection alias `careers_alias` (→ `careers_roles`), preset `careers_list_view`. Job pages are `careers.datadoghq.com/detail/<gh id>/?gh_jid=<id>`. |
| Recommended adapter | shared `greenhouse` adapter, `board: datadog` |

## Page vs feed (430 vs 414)
- The page shows "**414 jobs**". It makes one `POST .../multi_search` with `q:"*"` and `filter_by:"language: en"`, and gets back `found: 414, out_of: 430`.
- The Greenhouse `language` field splits the board as **en 416, ja 11, ko 3**. The non-English postings are Tokyo, Osaka and Seoul sales, sales-engineering and support roles, e.g. "Commercial Account Executive" (Tokyo, ja) and "Customer Success Manager" (Seoul, ko).
- So the English site lists English postings only, and 416 against 414 is index lag. I did not check localized versions of the site.
- The **feed (430) is the complete source**. If you only want English postings, filter on `language` later.

## Recommended feed
- **Request:** `GET https://boards-api.greenhouse.io/v1/boards/datadog/jobs`. Use a normal UA; no auth is needed.
- **Pagination:** none. `meta.total` equals the number of jobs. The response is 590 KB without `content`.

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `jobs[].id` | |
| title | `jobs[].title` | |
| location(s) | `jobs[].location.name` | e.g. "New York, New York, USA; Pittsburgh, Pennsylvania, USA" |
| url | `jobs[].absolute_url` | `https://careers.datadoghq.com/detail/<id>/?gh_jid=<id>` |
| posted date | `jobs[].first_published` | |
| language | `jobs[].language` | en / ja / ko |
| employment type | metadata "Time Type" and "Early Career Time Type" | "Time Type" is "Full time" on all 430 jobs, so it tells you nothing. "Early Career Time Type" is **"Internship" on exactly the 8 intern titles** and "Early Career" on 6 SDR roles, null otherwise. The shared adapter reads the first metadata name containing "time type", which is "Time Type". Interns are still caught, because all 8 titles say "Intern". |
| department / team | metadata "Area - Engineering", "Cost Center", "Geography" | `departments[]` in the detail call |

## Totals (observed 2026-10-20)
- **Feed, no filters:** **430** (`meta.total` 430).
- **Live careers page, no filters:** **414**. A Playwright render of https://careers.datadoghq.com/all-jobs/ showed "414 jobs", and the Typesense response confirms it (`found` 414, `out_of` 430). The page's `time_type` facet shows Early Career 14, which is 8 Internship + 6 Early Career.
- **Intern/student:** **8**. Only 3 are in the US:
  - 8181440 Applied Science Intern, Paris
  - 8129799 IT Support Technician Intern, Paris
  - 8108241 Product Management Intern, New York
  - 8143729 Product Management Intern, Paris
  - 8203657 Research Science Intern (PhD), New York; Pittsburgh
  - 8114161 Software Engineering Intern, Madrid
  - 8114186 Software Engineering Intern, Paris
  - 8052118 Software Engineering Intern (Summer), Boston; New York

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/datadog/jobs | ALLOW | no matching rule (only `/embed/` is disallowed) |
| https://careers.datadoghq.com/all-jobs/ | ALLOW | no matching rule |
| https://gk6e3zbyuntvc5dap.a1.typesense.net/multi_search | ALLOW | no robots.txt. The checker doesn't need it. |

## Anti-bot / quirks
- None seen. The Typesense search key is a public search-only key embedded in the page. The checker doesn't need it, because the Greenhouse feed is complete.

## Recommended checker
```yaml
- key: datadog
  name: Datadog
  adapter: greenhouse
  settings:
    board: datadog
  careers_url: https://careers.datadoghq.com/all-jobs/
```

## Evidence
- Sample: `discovery/samples/datadog.json` is the raw Typesense `multi_search` response for the unfiltered page (54 KB). It shows `found` 414, `out_of` 430, the facets, and 10 hits.
- Capture: `discovery/captures/datadog/` (the bookmark's Early Career filter: "14 jobs").
