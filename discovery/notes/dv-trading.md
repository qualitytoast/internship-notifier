# DV Trading (`dv-trading`)

**Status:** verified-feed (the seeded www host is broken; the careers page lives on the apex domain)   ·   **Checked:** 2026-10-20 (00:20–00:30 UTC)

| | |
|---|---|
| Official careers URL | https://dvtrading.co/join-dv/ ("Join DV", WordPress on WP Engine behind Cloudflare). It embeds the Greenhouse board via `boards.greenhouse.io/embed/job_board/js?for=dvtrading`. |
| Seed URL | `https://www.dvtrading.co/careers`. **Cloudflare 526 "Invalid SSL certificate"** (origin certificate problem on the `www` host), seen on 2026-10-19 and again on 2026-10-20. `www.dvtrading.co/robots.txt` also answers 526, which RFC 9309 treats as unreachable = disallow all, so do not crawl `www.dvtrading.co` while this lasts. On the apex host `/careers` is a WordPress 404, and `/campus-recruiting/` is also a 404. The real page is `/join-dv/`. |
| Hiring system | Greenhouse board **`dvtrading`** (company_name "DV Trading"; `absolute_url` → `https://job-boards.greenhouse.io/dvtrading/jobs/<id>`) |
| Recommended adapter | shared `greenhouse`, `{board: dvtrading}` |

## Recommended feed
- `GET https://boards-api.greenhouse.io/v1/boards/dvtrading/jobs` → 74. No pagination, standard Greenhouse field map.
- Locations: Chicago, New York, London, Hong Kong. Titles name the desk, e.g. "(DV Equities)", "(DV Commodities)".

## Totals (observed 2026-10-20)
- **Feed, no filters:** **74**.
- **Live careers page, no filters:** **74**. A Playwright render of https://dvtrading.co/join-dv/ showed the Greenhouse embed frame "74 jobs" (the first embed page lists 50 links).
- **Intern/student:** **20**, of which **13** are in the US: Chicago (AI Engineer, Client Platforms, Database, Data Center, DevOps, Quantitative Risk) and New York (Client Platforms, F&O Trading Analyst, QR/QT/Software Developer DV Equities, Software Engineer/Trading DV Commodities). The rest are London (4) and Hong Kong (3). All but one say "Summer 2027" or "2027"; "Quantitative Trading Intern (DV Equities)" (Hong Kong) has no year.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/dvtrading/jobs | ALLOW | no matching rule |
| https://dvtrading.co/join-dv/ | ALLOW | no matching rule (`Disallow: /wp-admin/` only) |
| https://www.dvtrading.co/careers | **BLOCK** | robots.txt unreachable (HTTP 526) → treated as disallow |

## Recommended checker
```yaml
- key: dv-trading
  name: DV Trading
  adapter: greenhouse
  settings: {board: dvtrading}
  careers_url: https://dvtrading.co/join-dv/
```

## Evidence
- Sample: `discovery/samples/dv-trading.json` (raw board response).
- Capture: `discovery/captures/dv-trading/` (the 526 page). Plain GETs of the apex `/careers` (404), `/join-dv/` (200) and `/campus-recruiting/` (404). Playwright render of /join-dv/.
