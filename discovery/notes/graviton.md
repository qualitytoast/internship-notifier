# Graviton Research Capital (`graviton`)

**Status:** verified-feed (the site renders a scraped copy of the Greenhouse board)   ·   **Checked:** 2026-10-20 (00:15–00:30 UTC)

| | |
|---|---|
| Official careers URL | https://www.gravitontrading.com/careers.html ("Work with us"). The job list is an iframe `/greenhouse-embed-local.html`, which renders `GET /data/greenhouse_jobs.json`. |
| Hiring system | Greenhouse board **`gravitonresearchcapital`** ("Graviton Research Capital LLP"). `/data/greenhouse_jobs.json` is a scrape of the Greenhouse embed board: it has `scraped_at`, `source.board_url = https://boards.greenhouse.io/embed/job_board?for=gravitonresearchcapital`, `board.departments/offices/sections`, `jobs[]` with `gh_jid`, and `counts.jobs`. |
| Recommended adapter | shared `greenhouse`, `{board: gravitonresearchcapital}` (the original, rather than the site's copy) |

## Equivalence check (2026-10-20)
- `GET https://boards-api.greenhouse.io/v1/boards/gravitonresearchcapital/jobs` → **24** (`meta.total` 24).
- `GET https://www.gravitontrading.com/data/greenhouse_jobs.json` → `scraped_at` 2026-10-20T00:15:13Z, `counts.jobs` **24**. Its 24 `gh_jid`s equal the Greenhouse ids.
- Live page: a Playwright render on 2026-10-20 showed **24** job links (`job-boards.greenhouse.io/gravitonresearchcapital/jobs/<id>`) in the `greenhouse-embed-local.html` frame. The page shows no count text.
- The copy appears to refresh often (its `last-modified` matched `scraped_at`). Still, use the Greenhouse API, because a stale copy would delay alerts.

## Totals
- **Feed:** **24**.
- **Page:** **24**.
- **Intern/student:** **2**:
  - "Quantitative Researcher - 2027 Summer Internship" (Amsterdam; London; **New York**; Singapore)
  - "Quantitative Researcher PhD - 2027 Internship" (Amsterdam; London; Singapore)
- Other locations: 15 India (Gurugram/Noida) and 6 Singapore.
- Departments: Core Engineering 5, Quantitative Trading 12, Network Engineering 3, Finance, HR, Risk Management, Trade Support. Offices: Gurgaon/Noida, Singapore, London, Amsterdam, New York.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/gravitonresearchcapital/jobs | ALLOW | no matching rule |
| https://www.gravitontrading.com/data/greenhouse_jobs.json | ALLOW | robots.txt is 404 |

## Recommended checker
```yaml
- key: graviton
  name: Graviton Research Capital
  adapter: greenhouse
  settings: {board: gravitonresearchcapital}
  careers_url: https://www.gravitontrading.com/careers.html
```

## Evidence
- Sample: `discovery/samples/graviton.json` (the site copy with `details` truncated, plus the raw Greenhouse list).
- Capture: `discovery/captures/graviton/`.
