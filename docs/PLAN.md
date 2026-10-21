# Build plan

Work order (as requested): plan → discovery → core build → company coverage → deployment.

## 1. Discovery
- `discovery/companies_seed.yaml`: every company from the brief (118 bookmarked + 50 to add),
  with its bookmark URL(s) or the official careers URL found for it.
- `discovery/capture.py`: opens each careers page in headless Chromium (Playwright), records every
  network request/response (URL, method, status, content type, size, JSON shape), fingerprints the
  hiring system (Greenhouse, Lever, Ashby, Workday, Eightfold, Oracle, SmartRecruiters, Workable,
  iCIMS, Phenom, Avature, Gem, …) and saves the evidence to `discovery/captures/<company>.json`.
- `discovery/probe.py`: tries the public JSON feeds of each hiring system directly and reports totals.
- Result: `COVERAGE.md` row per company (careers URL, hiring system, feed endpoint, total jobs,
  intern jobs, status), plus robots.txt findings. Hard cases get a written note in `discovery/notes/`.

## 2. Core build (`src/internwatch/`)
| Module | Job |
|---|---|
| `models.py` | `Job` (normalized: id, title, location, url, posted date, description snippet, extras) |
| `http.py` | one HTTP client: real browser UA, timeouts, retries with backoff, per-host pacing, robots.txt gate, record/replay for fixtures |
| `adapters/` | one module per hiring system, shared interface `fetch(settings) -> list[Job]` |
| `checkers/` | custom checkers for sites that fit no shared adapter (same interface) |
| `filters.py` | role type, term, field, location rules → match / reject / unsure, with tags |
| `db.py` | SQLite: every job ever seen, runs, per-company health, cross-check snapshots, sent mail |
| `health.py` | errors, timeouts, zero-after-nonzero, >50 % drop, bad shape → alert with retry/backoff and de-duplication |
| `crosscheck.py` | diff SimplifyJobs Summer2027 README + Off-Season README each run; possible-miss alerts and untracked companies |
| `emailer.py` | SMTP (Gmail app password) + always writes a copy to `data/outbox/` |
| `runner.py` | a polling run: pick due companies (30–60 min jittered), run checkers concurrently (one at a time per host), store, filter, notify, ping healthchecks.io |
| `cli.py` | `add`, `check`, `verify`, `run`, `digest`, `report`, `alert-test`, `seed` … |

## 3. Company coverage
For each company: config entry in `config/companies.yaml`, live check, count compared with the
live careers page (filters off), recorded fixture under `tests/fixtures/`, `COVERAGE.md` row → verified/blocked.

## 4. Deployment
`deploy/deploy.sh` (one command): rsync to the Oracle box, install uv + Python 3.12+, install
systemd service + timers (run every 30 min, daily digest, weekly report), seed, smoke test, alert test.
Dockerfile as an alternative. README covers setup, adding a company, and every alert type.
