# XTX Markets (`xtx-markets`)

**Status:** verified-feed (the site's own API is a cached copy of the Greenhouse board)   ·   **Checked:** 2026-10-20 (00:15–00:20 UTC)

| | |
|---|---|
| Official careers URL | https://www.xtxmarkets.com/careers/ ("Open Positions" table; tabs London / New York / (all), with (all) as the default). Job links: `https://www.xtxmarkets.com/job/?role=<Title-Slug>&id=<greenhouse id>` |
| Hiring system | Greenhouse board **`xtxmarketstechnologies`**. The page fetches `GET https://api.xtxcareers.com/jobs.json` (Cloudflare, `cache-control: max-age:3600`), which is `{jobs, meta: {total}, updated}`. Those are the Greenhouse `?content=true` job objects with the same 7 ids, `absolute_url`s on job-boards.greenhouse.io, plus `departments`/`offices`/`content`. |
| Recommended adapter | shared `greenhouse`, `{board: xtxmarketstechnologies}` (the source of the mirror; no need for the custom API) |

## Equivalence check (2026-10-20)
| Source | Jobs | ids |
|---|---|---|
| `GET https://boards-api.greenhouse.io/v1/boards/xtxmarketstechnologies/jobs` | 7 (`meta.total` 7) | 7831489003, 7645996003, 7990993003, 8003372003, 7989054003, 7835362003, 7827774003 |
| `GET https://api.xtxcareers.com/jobs.json` (`updated` 2026-10-20T00:15:33Z) | 7 (`meta.total` 7) | identical set |
| careers page table (2026-10-19 capture) | 7 rows | identical ids in the `id=` link parameter |

## Totals
- **Feed:** **7**.
- **Page:** **7** (rows in the "(all)" view).
- **Intern/student:** **0**.
- Today's openings: datacentre roles (Finland ×2, Singapore), London (Realtime Analytics and Controls Developer, Software Developer – Shared Engineering, Technology Procurement Specialist), Singapore (C++ Software Engineer). None are in the US.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/xtxmarketstechnologies/jobs | ALLOW | no matching rule |
| https://api.xtxcareers.com/jobs.json | ALLOW | the file holds only Cloudflare content-signal comments, no rules |
| https://www.xtxmarkets.com/careers/ | ALLOW | `Allow: /` |

## Recommended checker
```yaml
- key: xtx-markets
  name: XTX Markets
  adapter: greenhouse
  settings: {board: xtxmarketstechnologies}
  careers_url: https://www.xtxmarkets.com/careers/
  # optional job_url: https://www.xtxmarkets.com/job/?id={id}  (the site also puts a role slug in the URL)
```

## Evidence
- Sample: `discovery/samples/xtx-markets.json` (both raw responses).
- Capture: `discovery/captures/xtx-markets/` (7-row table and the api.xtxcareers.com fetch).
