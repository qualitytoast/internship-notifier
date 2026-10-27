# InternWatch

Watches 192 companies' careers sites (191 polled; Wayfair blocked: its site refuses automated clients) through their
hiring systems' official feeds and emails new internships that pass `config/filters.yaml`. Python 3.12+,
httpx, SQLite. Per-company checkers and evidence: COVERAGE.md. Freshman/sophomore programs: UNDERCLASSMEN.md.
Rules for changing things: CLAUDE.md.

## Running it
- **In use:** run `.venv/bin/internwatch run --daily` by hand each morning (15–25 min). Every company gets a full
  scan; failed ones are retried once later in the same run. Then ONE email goes out: `[InternWatch] <date>:
  N new: Co (n)…` (or "no new roles"), plus untracked-company roles and open problems.
  `run --daily --emails-only` sends whatever earlier runs couldn't send, without checking any site.
- **Set up but not in use:**
  - `deploy/install_mac_daily.sh HH:MM`: launchd schedule for `run --daily`.
  - `deploy/deploy.sh`: Oracle ARM server with a systemd timer every 15 min (continuous mode: each company
    polled every 30–60 min with jitter, one email per run with new roles).
  - `docker compose up -d --build`: `internwatch daemon`.
- **What "new" means:** a job ID never seen before, not the posting date. A skipped morning loses only a role
  that was posted and removed in between. A company's first successful check records its open postings as a
  baseline, sent as one "Now watching" summary instead of per-role emails. A posting that didn't match and is
  later edited (new title, location or type) or comes back after being removed is judged again, and emailed if it
  now matches; a match is never taken back. A matching posting is emailed again when its id comes back for a new
  round: open again after at least 14 days closed ("reopened"), or retitled for another term ("new term").
- **Secrets:** `.env` (gitignored; template in `.env.example`) holds SMTP_USER, SMTP_PASSWORD (Gmail app
  password), EMAIL_FROM, HEALTHCHECKS_PING_URL and ORACLE_SSH_*. The recipient is `email.to` in
  `config/settings.yaml`. SMTP uses certifi, because python.org Python ships without a CA bundle.

## Emails
- **Subject prefixes:**
  - `[InternWatch]`: new roles and the morning email; also "Now watching …" for the first run and for a newly
    added company.
  - `[InternWatch Digest]`: daily at 8:00 America/Chicago, continuous mode only.
  - `[InternWatch HEALTH]`: problems, recoveries, possible misses.
  - `[InternWatch COVERAGE]`: weekly on Monday.
- **Each row:** company, title linked to the posting, location, term ("unspecified" if none), posted date,
  field tag, `unsure` tags with the reason, `freshman/sophomore`, "repost", "reopened", "new term", "via Simplify".
- **Already open:** roles that were open before InternWatch could judge them but were never emailed (a
  multi-source company's source read for the first time, or a role matching after `refilter --notify`) come once,
  in their own section after the new ones.
- **More than 50 roles:** the 50 surest are in the body, and everything is attached as matching-roles.html and
  .csv.
- **Delivery:** every email is also saved in `data/outbox/`. An email that fails to send is retried on the
  next run, and healthchecks.io is told the run failed.

## Health alerts
- **When:** after 2 failed polls in a row; each request is already retried 3 times with 2/6/18 s backoff.
  Reminders every 24 h, plus a "recovered" line when it clears.
- **Kinds:**
  - `error`, `timeout`
  - `blocked`: robots.txt now disallows the feed; mark the company `status: blocked`.
  - `shape`: unexpected response or incomplete pagination; the checker needs fixing.
  - `zero`: 0 jobs after a nonzero count.
  - `drop`: more than 50% fewer jobs, from a count of at least 6.
  - `degraded`: one source of a multi-source company is failing.
  - Also: a big site's daily full scan failing.
  - `possible miss`: SimplifyJobs lists an in-field role at a tracked company that the checker never saw
    although it polled afterwards (90 min grace), or saw but the filters rejected.
- **healthchecks.io:** pinged at the start and end of each run, so it alerts if no run happens or a run fails
  (no internet, email failure). `internwatch alert-test` sends a real alert.

## Matching (config/filters.yaml; try `internwatch test-filters "<title>" --location "<loc>"`)
- **Role:**
  - Counts: a student word (intern, co-op, apprentice, student, summer analyst, winternship…); the hiring
    system's intern flag; freshman/sophomore markers (sophomore, first-year, discovery/insight/explore
    program, career prep…) unless the title has a staff word; per-company `role_keywords` (NVIDIA "ignite"…).
  - Counts but tagged unsure: "Class of 2028–2030"; weak hints (campus, university, early talent, fellowship).
  - Rejected: new-grad/full-time roles, and staff jobs about internships.
- **Term:**
  - Matches: Spring/Summer/Fall 2027–2028, or a bare 2027/2028 in the title. Winter 2027/2028 is unsure.
  - A missing term never rejects. Another term in the title (Summer 2026) rejects; terms only in the
    description never do.
  - Graduation years and dates ("Class of 2029", "2029 grads", "Graduating Spring 2029") are never read as
    terms. An academic year ("2026-27", "Winter 2026/2027") counts as both of its years.
- **Field:**
  - Keyword lists in order Quant, ML/AI, Research, Data, SWE; the first match names the tag. The department
    decides generic titles.
  - `exclude.strong` always rejects. `exclude.fields` rejects unless a field word is present; an "engineer*"
    word outside the excluded phrase makes it unsure instead.
  - Program labels ("…, PhD Student Science Recruiting", "- Campus Recruiting 2027") are ignored.
  - No field found → included as unsure (`Quant?` at quant firms).
- **Location:**
  - US by default, remote-US included; unrecognised locations are unsure.
  - Per company, `locations:` overrides it. Canada is also watched for Microsoft, Uber, Procore, GM,
    Salesforce, Veeva, Autodesk and Stripe.
- **Keyword syntax:** whole words, case-insensitive; a space or hyphen inside is optional; a trailing `*`
  matches any ending; plurals are automatic except for 2-letter words.
- **After editing:** `internwatch refilter` marks open jobs that now match as already notified. With
  `--notify` they go out with the next run, including ones recorded as a baseline. It only ever adds matches:
  a stored match is never taken back, even if the current filters would reject it.

## Companies (config/companies.yaml)
- **Generated:** `discovery/build_config.py` builds it from `discovery/results/*.json` plus its ALIASES,
  OVERRIDES and PROGRAM_KEYWORDS. Change those and rerun it. A company added with `internwatch add` exists only
  in companies.yaml, so a rerun drops it unless it is also given a result file.
- **Entry fields:** key, name, category (`quant` makes generic titles count as quant), careers_url, checker +
  settings, locations, aliases (for matching SimplifyJobs rows), status: blocked + blocked_reason + fallback,
  big (newest-first quick scans each poll, a full scan daily), timeout_minutes, role_keywords, verified
  {page_total, explained, feed}.
- **Verified:** the checker's count equals the live careers page with filters off (±3 jobs or 2%, or the
  difference is explained), and a test fixture is recorded.
- **Adapters** (`src/internwatch/adapters/`):
  - greenhouse {board | boards, missing_ok, dedupe_requisitions}, lever {site}, ashby {board, mode: hosted}
  - workday {host, tenant, site | sites (prefixes ids with the site), quick_queries}
  - eightfold {host, domain, api: pcsx | v2, count_tolerance}, oracle {host, site}
  - smartrecruiters {company}, workable {account}, icims {portal}, jibe {host}, phenom {base_url, ref_num},
    avature {list_url, page_size}, gem, rippling, jobvite, pinpoint, recruiterbox, ripplematch
  - multi {sources, dedupe, dedupe_titles}: later sources' ids are prefixed with `<checker>:`; dedupe_titles skips
    a later source's role whose title matches an earlier one apart from case and punctuation. Sources are remembered
    by checker and settings, and a source's first answer is its baseline, emailed once as "already open".
- **Custom checkers** (`src/internwatch/checkers/`): google, meta (GraphQL + sitemap fallback), amazon and
  apple (complete student slices), atlassian, goldman, citadel, shopify, epic_careers, talentbrew (Intuit),
  hubspot, instabase (its switched-off Greenhouse board plus a watch on the careers page for a move), deshaw (the
  job list inside deshaw.com/careers), ibm (the search service behind ibm.com/careers), blocked.
  - Writing one: a class whose `fetch()` returns `Job(...)`s, with `need(...)` raising ShapeError on anything
    unexpected. Example: `checkers/atlassian.py`.
- **Adding a company:** `internwatch add "<Name>" <url>` detects the hiring system, runs the checker live, asks
  before saving and records a fixture. Compare its count with the careers page, then run
  `internwatch verify <key> --write`.
- **Changing a company's checker:** job ids change, so run `internwatch reseed <key>` or every posting is
  emailed as new.

## Commands
- `run`: `--daily`, `--emails-only`, `--force`, `--company X`, `--mode full|quick`, `--no-send` (outbox only),
  `--no-crosscheck`
- `check <key>`: `--show matches|students|all`, `--details N`, `--record`, `--json`, `--force`
- `verify [keys]`: `--write` (verify.json + COVERAGE.md), `--record`
- `add`, `record [keys]`, `coverage`, `refilter [--notify]`, `reseed <keys>`, `status`, `report`, `digest`,
  `alert-test`, `test-filters`, `daemon`
- Tests (offline, from cassettes in tests/fixtures/cassettes): `.venv/bin/python -m pytest`

## Internals
- **runner.py:**
  - Takes a run lock, runs checkers in parallel (8 workers, one request at a time per host), and gives each
    check a time budget (8 min; the whole run 25 min).
  - Each company's results are saved in one DB transaction, so a Ctrl-C can't half-save them.
  - Also handles seeding, the cross-check, emails and the heartbeat.
- **db.py:** SQLite (WAL) with tables jobs, company_state, checks, emails, runs, kv and simplify_rows. jobs
  keeps every job ever seen: first/last seen, match decision, notified_at, baseline, removed_at, repost_of,
  alt_ids.
- **http.py:**
  - Checks robots.txt (RFC 9309) before every request; an unreachable robots.txt is a temporary error, not a
    block.
  - At least 1 s between requests to a host (per-company min_interval), retries, 429 backoff, conditional GET.
  - `ssl_context()` = certifi plus the bundled intermediates in certs/.
- **crosscheck.py:**
  - Fetches the SimplifyJobs Summer2027 README and the Off-Season list (with ETag). New rows go
    pending → found / filtered / missed.
  - For blocked or failing companies, the rows are stored as "via Simplify" jobs and emailed.
  - Matching uses job ids or requisition ids in the URL, then normalized titles of current postings (open, or
    closed within 30 days; a different year never matches).
- **Removals and scans:** a removal is recorded only after a healthy full scan. Big sites' quick scans stop
  after two consecutive pages of known jobs.

## Decisions
- Bookmarks with saved filters are watched as the whole site; InternWatch applies the filters.
- Product management and design are not excluded; they arrive as `field?`. Add `product manag*` to
  exclude.fields to drop them.
- **Second boards:** Klaviyo, Toast and Twilio have Greenhouse campus boards (klaviyocampus, toastcampus,
  twiliostudents). Expedia has a second Workday site, `private`, which robots.txt allows and SimplifyJobs
  links to. Plaid and Rockwell Automation post some student roles only on RippleMatch, which is read for them
  (Rockwell's roles that are also on Workday under the same title are skipped).
- **Not double-counted:** Epic Games' and Google's translated postings, and C3 AI's re-posted Ascend
  requisitions.
- **Palo Alto Networks:** robots.txt disallows the HTML job pages but not the JSON API the checker uses, which
  is the only complete source.
- **Capstone:** both `capstone` (Investment Advisors) and `capstone-dc` are watched.
- **Not watched:** Instabase's Greenhouse board is off, so it counts as 0 jobs (missing_ok). Rocket's India
  locale is skipped. xAI was removed on request.
- **LinkedIn:** linkedin.com disallows all crawlers and is never fetched. LinkedIn is read through its public
  SmartRecruiters career page (LinkedIn3), which allows it. The bookmark's other LinkedIn ids (2587638, 39939)
  couldn't be identified.
- **Blocked:** Wayfair (bot challenge; private Greenhouse and Workday boards) is never polled. The SimplifyJobs
  cross-check covers it, and COVERAGE.md lists its fallback.
- **Big sites:** Microsoft, NVIDIA, Amazon, T-Mobile and Synopsys. Amazon (22k jobs, search capped at 10k) and
  Apple are read through their complete student slices.
- **Count tolerances:** a full scan may come up short by 5% at Microsoft and NVIDIA (their internship filters are
  read in full) and by 4% on Autodesk's Eightfold source (`count_tolerance`); elsewhere 1.5%, at least 2 jobs.

## Layout
- `config/`: settings.yaml, companies.yaml, filters.yaml
- `src/internwatch/`: cli, runner, filters, locations, health, crosscheck, emails, mailer, db, http, detect,
  report, plus `adapters/` and `checkers/`
- `tests/`
- `deploy/`
- `discovery/`: notes, results, samples, build_config.py
- `data/`: db, outbox, logs, robots cache (gitignored)
