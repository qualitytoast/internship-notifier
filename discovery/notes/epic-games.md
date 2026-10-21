# Epic Games (`epic-games`)

**Status:** verified-feed   ·   **Checked:** 2026-10-20

| | |
|---|---|
| Official careers URL | https://www.epicgames.com/site/en-US/careers/jobs (the page shows "156 Positions" with no filters) |
| Hiring system | **Greenhouse, three boards.** The careers page calls its own API `GET https://www.epicgames.com/site/api/v2/jobs?limit=50&skip=0&page=1&lang=en-US`. That API returns Greenhouse job objects with an extra `board` field: `epicgames` (English), `epicgamesportuguese` and `epicgamesfrench`. Job links are `https://epicgames.com/careers/jobs/<gh id>?gh_jid=<gh id>`. |
| Recommended adapter | shared `greenhouse` adapter, board `epicgames` only (see "Which boards" below) |

## Recommended feed
- **Request:** `GET https://boards-api.greenhouse.io/v1/boards/epicgames/jobs` (add `?content=true` for descriptions; that makes it 1.36 MB instead of 179 KB)
- **Headers:** a normal browser UA. No auth needed.
- **Pagination:** none. `meta.total` gives the count.
- Do **not** use `www.epicgames.com/site/api/v2/jobs`. From plain httpx, and even from headless Chromium navigating to it directly, it returns 403 with a Cloudflare managed challenge (`cf_chl`). Its robots.txt also returns that 403 challenge page.

## Which boards
| Board | Postings | Requisitions | Interns (title rule) | What it is |
|---|---|---|---|---|
| `epicgames` | 135 | 67 | 23 | English board. It has one posting per location, so the same requisition appears up to 5 times (e.g. "Machine Learning Engineer, Memory": Cary, London, Porto Alegre, …). One posting is in Chinese (高级业务拓展经理, Shanghai). |
| `epicgamesportuguese` | 9 | 9 | 0 | Porto Alegre (Brazil) postings, mostly with Portuguese titles ("Artista de UI", "Programador de UI") |
| `epicgamesfrench` | 12 | 12 | 0 by title, 1 by type | Montreal postings with French titles. It includes "Stagiaire en apprentissage automatique", whose `Careers Page Job Type` metadata is `Intern`. |

**Every one of the 21 Portuguese/French postings is a translated copy of an English-board posting with the same `requisition_id` and the same location string.** I checked all 21 (req, location) pairs, and none is missing from the English board. So `epicgames` alone is complete. Adding the two language boards reproduces the site's count of 156, but adds 21 duplicates under different Greenhouse ids and translated titles. For example, the French "Stagiaire en apprentissage automatique" (6138142004) duplicates the English "Machine Learning Intern" in Montreal (6138140004). If you ever want them, the setting is `boards: [epicgames, epicgamesportuguese, epicgamesfrench]`, and you should dedupe by `requisition_id` + `location.name`.

Other Epic-owned boards probed: `epicgameschinese`, `epicgamesjapanese`, `epicgameskorean`, `epicgamesspanish`, `epicgamesgerman`, `epicgamesserbian`, `harmonix` return 404. `psyonix` and `mediatonic` exist but are empty (0). Rocket League (Psyonix) jobs are on the `epicgames` board, with product "Rocket League".

## Field map
| Job field | Response path | Notes |
|---|---|---|
| id | `jobs[].id` | Greenhouse post id. Each location of a requisition has its own id. |
| title | `jobs[].title` | |
| location(s) | `jobs[].location.name` | e.g. "Cary,North Carolina,United States", "BLANK,BLANK,Multiple Locations" (a literal "BLANK" means the field is empty) |
| url | `jobs[].absolute_url` | `https://epicgames.com/careers/jobs/<id>?gh_jid=<id>` |
| posted date | `jobs[].first_published` | `updated_at` also present |
| employment type | `jobs[].metadata[name="Careers Page Job Type"].value` | `Regular` (112) / `Intern` (23). The shared adapter already maps "job type" metadata to `employment_type`. |
| department / product | metadata `Careers Page Department` / `Careers Page Product` | e.g. Engineering / Fortnite. `requisition_id` (R27xxx) groups the per-location postings. |

## Totals (observed 2026-10-19/20)
- **Feed, no filters:** `epicgames` **135** (`meta.total` 135). With the language boards: 135 + 9 + 12 = **156**.
- **Live careers page, no filters:** **156 Positions**. This was text in the Playwright capture `discovery/captures/epic-games` (2026-10-19). The page's API response in that capture had `total: 156`, `counts.type` = Regular 132 / Intern 24 and `counts.company` = Epic Games 156. The `board` fields of its hits are the three boards above.
- **Difference 156 vs 135:** this is exactly the 21 translated duplicates. The site's 24 interns are the 23 English intern postings plus the French "Stagiaire" copy.
- **Intern/student (English board):** **23** postings across 20 requisitions. All have type `Intern`, and 17 of them are in Cary, NC. Examples: Backend Services Programmer Intern, Data Science Intern, Engine Programmer Intern (Cary; London), Frontend Programmer Intern, Gameplay Programmer Intern, Machine Learning Intern (Multiple Locations / Montreal / London), SDET Intern, Tools Programmer Intern ×2, UI Programmer Intern, Web Engineer Intern (London; Novi Sad), and Product Management, Game/Level Design, Tech Art and Communications interns.

## robots.txt
| URL | Verdict | Deciding rule |
|---|---|---|
| https://boards-api.greenhouse.io/v1/boards/epicgames/jobs | ALLOW | no matching rule |
| https://boards-api.greenhouse.io/v1/boards/epicgamesportuguese/jobs | ALLOW | no matching rule |
| https://boards-api.greenhouse.io/v1/boards/epicgamesfrench/jobs | ALLOW | no matching rule |
| https://www.epicgames.com/site/api/v2/jobs?... | (ALLOW: robots.txt answers 403, which counts as 4xx) | The endpoint itself refuses automated clients (Cloudflare challenge), so it is not used. |

## Anti-bot / quirks
- `www.epicgames.com` is behind a Cloudflare managed challenge for non-browser clients, including robots.txt. Greenhouse has no anti-bot measures.
- One posting per location means a multi-location internship shows up as several jobs (Machine Learning Intern ×3). Dedupe by `requisition_id` in emails if that is noisy.

## Recommended checker
```yaml
- key: epic-games
  name: Epic Games
  adapter: greenhouse
  settings:
    board: epicgames            # complete; the language boards only add translated duplicates
  careers_url: https://www.epicgames.com/site/en-US/careers/jobs
```

## Evidence
- Sample: `discovery/samples/epic-games.json` is the raw `epicgames` board response without content (135 jobs, 179 KB).
- Capture: `discovery/captures/epic-games/` (page + `feed_0_0.json` from the site API, total 156).
- Requests: the 3 board lists (with and without content), probes of 9 other board tokens, and 2 attempts at the site API (both 403 challenges, not retried).
