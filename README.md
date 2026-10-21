# InternWatch

InternWatch watches the careers sites of every company you apply to and emails you as soon as a new
internship that fits you is posted. It reads each company's real job feed (the hiring system's own API
wherever one exists), checks itself constantly, and tells you when anything looks wrong, so a broken site
never fails silently.

- **Coverage:** every company from your list. [COVERAGE.md](COVERAGE.md) has one row per company: careers page,
  hiring system, feed, job counts, and status.
- **Schedule:** a run starts every 15 minutes. Each site is polled every 30–60 minutes with random jitter
  (never more often), with a real browser user agent, request timeouts, and robots.txt respected.
- **Independent cross-check:** every run diffs the SimplifyJobs Summer 2027 lists against their previous
  versions and flags anything at a company you track that the checker didn't find.

---

## Setup

You need three accounts' worth of credentials. Everything else is already done.

1. **`.env`** (in this folder; it is in `.gitignore` and never committed). Fill in:
   - `SMTP_USER`: your Gmail address.
   - `SMTP_PASSWORD`: a Gmail **app password**. Turn on 2-Step Verification, then create one at
     <https://myaccount.google.com/apppasswords>.
   - `HEALTHCHECKS_PING_URL`: create a free check at <https://healthchecks.io> with **Period 15 minutes** and
     **Grace 30 minutes**, then copy its ping URL (`https://hc-ping.com/…`).
   - `ORACLE_SSH_HOST`, `ORACLE_SSH_USER` (usually `ubuntu`), `ORACLE_SSH_KEY` (path to the private key).
2. **`config/settings.yaml`**: set `email.to` to the address that should receive the emails.
3. **Deploy:** run

   ```bash
   ./deploy/deploy.sh
   ```

   This copies the project to the Oracle machine, installs Python 3.12 and the dependencies, runs the test
   suite there, and installs a systemd timer (every 15 minutes). It then does the first run and sends you a
   deliberate test health alert, so you know alerts reach you. Run it again after any change (new company,
   filter edit, code update); it updates in place and keeps the database.

   The first run takes about 15 minutes. It records every posting that is open right now without emailing
   each one, and sends one **"Now watching"** summary of the roles that match. From then on you only hear
   about new postings.

**Logs on the server:** `journalctl -u internwatch -n 200` and `~/internwatch/data/logs/internwatch.log`.

### Or: once a morning on your Mac (no server)

Fill in only `SMTP_USER`, `SMTP_PASSWORD` (and optionally `HEALTHCHECKS_PING_URL`) in `.env`, set `email.to` in
`config/settings.yaml`, then run

```bash
./deploy/install_mac_daily.sh 07:30
```

It schedules `internwatch run --daily` for 7:30 every morning with launchd (if the Mac is asleep then, it runs as
soon as it wakes), and does the first run right away (about 15 minutes: one summary email of what's open now).
Every morning after that you get **one email** with every matching role that appeared since the previous run, even
if a morning was skipped because the Mac was off ("new" means never seen before, not "posted in the last 24 h").
A company that fails is checked again later in the same run; only if it fails twice do you get a HEALTH email.
The trade-off versus the server: you hear about a posting up to a day after it appears instead of within the hour,
and a posting that opens and closes between two mornings is missed. For healthchecks.io in this mode, use
Period 1 day and Grace 6 hours.
**Status:** `cd ~/internwatch && .venv/bin/internwatch status`.

**Docker instead of systemd (optional):** `docker compose up -d --build` runs the same schedule in a
container (`internwatch daemon`), with the database in `./data`.

---

## The emails

Every email has a distinct subject prefix, so you can filter or label them in Gmail
(e.g. a filter on `subject:"[InternWatch HEALTH]"` that stars the message).

| Email | Subject looks like | When |
|---|---|---|
| New postings | `[InternWatch] 3 new: Stripe (2), Jane Street (1)` | As soon as a run finds new matching roles: one email per run, grouped by company |
| Morning email (daily mode) | `[InternWatch] Tue Oct 20: 3 new: Stripe (2), Jane Street (1)` | Every morning with `run --daily`: everything new since the last run, untracked companies, open problems (replaces the two rows above and the digest) |
| First-run summary | `[InternWatch] Now watching 168 companies: 412 matching roles open at 97` | Once, after the first run |
| Now watching | `[InternWatch] Now watching NewCo: 3 matching roles open` | When a company you added is read for the first time |
| Daily digest | `[InternWatch Digest] Tue Oct 20: 5 new roles, 2 from untracked companies` | Daily at 8:00 (America/Chicago) |
| Health alert | `[InternWatch HEALTH] 2 problems: Meta (shape), possible miss at Stripe` | When a checker keeps failing, looks wrong, or the cross-check finds a possible miss |
| Weekly coverage | `[InternWatch COVERAGE] Weekly report Mon Oct 26: 167/168 checkers healthy` | Mondays at 8:00 |

Each role shows the company, title (linked to the posting/apply page), location, term (or "unspecified"),
posted date when the site gives one, the field tag (SWE, ML/AI, Data, Research, Quant), and yellow
**unsure** tags with the reason whenever a rule couldn't decide. "repost" marks a posting whose title and
location match an older one; "via Simplify" marks a role learned from the cross-check.

The daily digest repeats everything new from the last 24 hours, and adds **untracked companies**: new
SimplifyJobs roles in your fields at companies you don't watch yet (add them with `internwatch add`).

Long lists (more than 50 roles, e.g. the first-run summary) show the 50 surest roles in the email, because
Gmail clips long messages; the complete list is attached as `matching-roles.html` (open in a browser) and
`matching-roles.csv` (open in a spreadsheet).

Every email is also saved to `data/outbox/` (`.eml` + `.html`), so nothing is lost even if sending fails. If sending
does fail, the alerts are kept and raised again on the next run, and healthchecks.io is told the run failed, so
it emails you through its own channel.

---

## What each alert means

A company's problem is only emailed after **two polls in a row** fail, and every request inside a poll is
already retried three times with backoff (2 s, 6 s, 18 s). So a single blip never emails you. While a problem
stays open you get a reminder every 24 hours, and a "recovered" line when it clears. **Until it clears, check
that careers page yourself** (the alert links it).

| Kind | Meaning | What to do |
|---|---|---|
| `error` | The site could not be read (network error, HTTP error) after all retries, twice in a row. | Usually temporary. If it lasts a day, run `internwatch check <company>` to see the error. |
| `timeout` | The checker ran past its time budget, or every attempt timed out. | Same as `error`. |
| `blocked` | robots.txt now disallows the feed. | The checker stops reading it by design. Mark the company `status: blocked` (with a reason and fallback) in `config/companies.yaml`. |
| `shape` | The site answered, but not in the expected structure (API or page layout changed), or pagination came back incomplete. | The checker needs an update. Meta's checker switches to its sitemap fallback and keeps emailing new roles meanwhile. |
| `zero` | 0 jobs after previously returning some. | The site changed how it loads jobs, or really took everything down. Look at the page. |
| `drop` | The job count fell by more than 50% since the last healthy poll. | Same. After one alert the new size becomes the baseline. |
| `possible miss` | A new SimplifyJobs role at a company you track that the checker has not seen, although it polled after the role appeared (90 min grace). Or the checker saw it but your filters rejected it. | Apply from the link. It is a checker or filter bug to fix. |
| healthchecks.io email | No successful run reached healthchecks.io in time (period 15 min + grace 30 min): the machine is down, the timer stopped, or a run hung. Or the run reported a failure: it could not send email (e.g. the app password was revoked) or had no internet. | SSH in: `systemctl status internwatch.timer`, `journalctl -u internwatch -n 100`; for email, re-check `SMTP_PASSWORD` in `.env` and redeploy. |

`internwatch alert-test` sends a real alert through the same code path at any time.

---

## What counts as a match

All rules live in [`config/filters.yaml`](config/filters.yaml); edit it freely. Try a title with:

```bash
internwatch test-filters "Software Engineer Intern (Summer 2027)" --location "Seattle, WA"
```

- **Role type:** intern, co-op, apprentice, student, off-cycle, placement, "summer analyst", Thrive Program…,
  or the hiring system's own intern flag. Weaker hints ("campus", "university", "early talent") count but
  are tagged unsure. New-grad and full-time roles are rejected; so are staff jobs about internships.
- **Terms:** Spring/Summer/Fall 2027 and 2028, and a bare 2027/2028 next to an internship word. Winter 2027/2028
  are included but tagged unsure. **A missing or unclear term never rejects a role** ("unspecified"). Any other
  term in the title (e.g. Summer 2026) rejects it; other terms only in the description never do.
- **Fields:** SWE, ML/AI, Data, Research, Quant (keyword lists in the file). Clearly unrelated fields are on the
  editable `exclude` list (HR, marketing, legal, sales, accounting, finance, design-for-marketing, mechanical…).
  A title with no recognisable field is **included and tagged unsure** (product management, for example), and so
  is an engineering title in an excluded area ("Policy Engineering Intern"). Program labels such as Amazon's
  ", PhD Student Science Recruiting" are not mistaken for the job's field.
  At quant firms a generic title counts as a probable quant role (tagged `Quant?`).
- **Freshman/sophomore programs:** titles such as "Discovery Program: Quantitative Trading", "Explore Program
  (Second-Year Students)" or "Coffee Chats — Class of 2029" count as student roles even without the word intern,
  as do each company's own program names (`role_keywords` in companies.yaml, e.g. NVIDIA Ignite). They, and any
  role whose description invites freshmen or sophomores, are tagged `freshman/sophomore`. A graduation year
  ("Class of 2029") is never read as the internship's term. [UNDERCLASSMEN.md](UNDERCLASSMEN.md) lists every
  program found at your companies, including the ones only on their own web pages (no email for those).
- **Location:** US (including remote in the US) by default. Per company, `locations:` overrides it; companies
  whose bookmarks included Canada also watch Canada. Unrecognised or missing locations are included, tagged unsure.

After editing the file, `internwatch refilter` re-applies it to every stored job. Open jobs that now match are
not emailed unless you pass `--notify`; then they go out with the next run, including ones that were already
open when their company was first recorded.

---

## Adding a company

**Easiest:** one command.

```bash
internwatch add "Company Name" https://company.com/careers
```

It detects the hiring system (from the URL, the page's HTML, and by probing the public Greenhouse, Lever,
Ashby and Workable APIs), runs the checker live, shows the job count and matching roles, and asks before
saving the entry to `config/companies.yaml`. Compare the count with the careers page (filters off). Then
record a test fixture and deploy:

```bash
internwatch record company-name && ./deploy/deploy.sh
```

**By hand:** a company on a supported system is one entry in `config/companies.yaml`, nothing else:

```yaml
  - key: acme
    name: Acme
    category: software            # quant | ai | big-tech | fintech | software | …
    careers_url: https://acme.com/careers
    checker: greenhouse
    settings: {board: acme}
```

| Hiring system | `checker` | `settings` |
|---|---|---|
| Greenhouse | `greenhouse` | `{board: stripe}` or `{boards: [a, b]}` |
| Lever | `lever` | `{site: zoox}` |
| Ashby | `ashby` | `{board: openai}` (or `boards: [...]`; `mode: hosted` if the API is off) |
| Workday | `workday` | `{host: x.wd5.myworkdayjobs.com, tenant: x, site: External}` (or `sites: [...]`) |
| Eightfold | `eightfold` | `{host: jobs.nvidia.com, domain: nvidia.com}` |
| Oracle Recruiting Cloud | `oracle` | `{host: eeho.fa.us2.oraclecloud.com, site: CX_45001}` |
| SmartRecruiters | `smartrecruiters` | `{company: ServiceNow}` |
| Workable | `workable` | `{account: huggingface}` |
| iCIMS | `icims` | `{portal: https://careers-x.icims.com}` |
| iCIMS Jibe | `jibe` | `{host: careers.docusign.com}` |
| Phenom | `phenom` | `{base_url: https://careers.x.com, ref_num: XXXXUS}` |
| Avature | `avature` | `{list_url: https://x.avature.net/careers/SearchJobs/, page_size: 12}` |
| Gem | `gem` | `{board: groq}` |
| Rippling | `rippling` | `{board: rippling}` |
| Jobvite | `jobvite` | `{company_id: qKr9VfwZ}` |
| Pinpoint | `pinpoint` | `{subdomain: wolve}` |
| Recruiterbox | `recruiterbox` | `{client_id: 42716}` |
| RippleMatch | `ripplematch` | `{company_id: 865}` |
| Several sources for one company | `multi` | `{sources: [{checker: workday, settings: {…}}, {checker: ripplematch, settings: {…}}]}` |

Custom checkers (one site each, in `src/internwatch/checkers/`): `google` (official XML feed), `meta`
(GraphQL + sitemap fallback), `amazon` and `apple` (complete student slices of sites too big to list),
`atlassian`, `goldman` (GS Higher GraphQL), `citadel` (career sitemaps of Citadel and Citadel Securities),
`shopify`, `epic-careers` (Epic Systems), `talentbrew` (Intuit's sitemap).

Optional fields: `locations: [US, CA]`, `aliases: [Other Name]` (for matching SimplifyJobs rows),
`big: true` (huge sites: newest-first quick scans each poll, a full scan daily), `timeout_minutes`,
`status: blocked` + `blocked_reason` + `fallback`.

**A site that fits no adapter:** write a custom checker in `src/internwatch/checkers/<name>.py`. It is one
class with a `fetch()` that returns every job on the site as `Job(id, title, location, url, posted, snippet)`
objects; raise `ShapeError` (via `need(...)`) whenever the response isn't what you expect, so a site change
becomes a health alert instead of silence. `checkers/atlassian.py` is a short example. Then use
`checker: <type>` in the config entry.

---

## Commands

| Command | What it does |
|---|---|
| `internwatch run` | One polling run (what the timer calls). `--force` polls every company now; `--no-send` writes emails to `data/outbox/` only. |
| `internwatch check <company>` | Run one checker and print what it finds (`--show all`, `--record` to save a fixture). |
| `internwatch verify [company…]` | Run every checker and print the coverage table; `--write` updates COVERAGE.md. |
| `internwatch add <name> <url>` | Detect, test and add a company. |
| `internwatch report` / `digest` | Send the weekly coverage report / daily digest now. |
| `internwatch alert-test` | Trigger a real health alert end to end. |
| `internwatch status` | Last run, open problems, recent emails. |
| `internwatch test-filters "<title>"` | See how the filters decide a title. |
| `internwatch record [company…]` | Record test fixtures from the live sites. |
| `internwatch coverage` | Regenerate COVERAGE.md. |
| `internwatch refilter` | Re-apply filters.yaml to stored jobs. |

Tests run offline from the recorded fixtures: `.venv/bin/python -m pytest`.

---

## How it stays reliable

1. **Every company has a verified checker.** During discovery each careers page was opened in a real browser
   and its network requests inspected, to find how it really loads jobs; the official feed of its hiring
   system is used wherever one exists. A company counts as verified when its checker returns the same number
   of jobs as the live careers page with filters off, and it has a recorded test fixture. Evidence per
   company: `discovery/results/<company>.json`, `discovery/notes/`, and COVERAGE.md.
2. **Every failure alerts you** (errors, timeouts, zero after nonzero, >50% drops, unexpected shapes,
   incomplete pagination), after retries.
3. **The service watches itself:** healthchecks.io is pinged at the start and end of every run, so it emails
   you if a run fails, hangs, or the machine is down. A run that can't reach the internet reports a failure
   instead of blaming every company.
4. **Independent cross-check:** the SimplifyJobs lists are diffed every run (`possible miss` alerts; untracked
   companies in the digest). For blocked companies, their new Simplify roles are emailed as new postings.
5. **Weekly coverage report** of every company: checker, last success, jobs, intern roles, errors this week.

Storage is SQLite (`data/internwatch.db`): every job ever seen, with first/last seen and match decision, so a
job is new only once; reposts and removals are recorded.

**Politeness:** at most one request per second per host (3–5 s on rate-limited hosts), one poll per company
every 30–60 minutes, conditional requests (ETag / If-Modified-Since) where supported, robots.txt checked
before every request. Sites that disallow automated access are not polled at all.

---

## Decisions on ambiguous points

- **Bookmarks with saved filters** (intern, location, department) are tracked as the whole site; the filters
  are applied by InternWatch, so a saved filter can't hide anything. The bookmark stays in `careers_url` as a
  convenient link.
- **Canada:** companies whose bookmarks included Canada or "North America" (Microsoft, Uber, Procore,
  General Motors, Salesforce, Veeva, Autodesk, Stripe) also match Canadian roles. Everyone else: US only.
- **Fields:** product management and design roles are not on the exclude list (your Google bookmark included
  those categories); they arrive tagged "unsure: field". Add `product manag*` to `exclude.fields` to drop them.
- **Winter 2027/2028** terms are not in your list but fall inside your window, so they are included as unsure.
- **"Campus"/"university"** without an intern word count as unsure student roles, except where the word is a
  place ("Mega Campus") or the title is a staff job (manager, recruiter, …).
- **Big sites** (Microsoft, NVIDIA, Amazon, T-Mobile, Synopsys) are read newest-first every poll and fully once
  a day; Amazon's site (22k jobs, search capped at 10k) is read through its complete student slice.
- **Second boards:** Klaviyo, Toast and Twilio post internships on a separate Greenhouse campus board
  (`klaviyocampus`, `toastcampus`, `twiliostudents`) that their careers pages don't list; both boards are read.
  Expedia posts some roles, 2027 internships among them, only on a second Workday site named `private`
  (SimplifyJobs links to it; robots.txt allows it); it is read as a second source.
- **Duplicate boards:** translated copies (Epic Games' French/Portuguese boards, Google's translated postings)
  and re-posted requisitions (C3 AI's Ascend board) are not double-counted.
- **Palo Alto Networks:** its Workday tenant's robots.txt disallows the HTML job pages but not the JSON API path
  the checker uses. The API is the only complete source (the Radancy careers front drops every intern posting),
  so InternWatch reads that allowed path only. Delete the entry if you'd rather not.
- **Capstone:** your bookmark points at Capstone DC (a Washington policy research firm), while the seed list
  meant Capstone Investment Advisors (the NYC fund). Both are watched (`capstone`, `capstone-dc`); delete the
  one you don't want.
- **Instabase** has switched its Greenhouse board off; the checker treats the missing board as "0 jobs" and
  picks postings up again automatically if it comes back.
- **Rocket** has a separate India careers locale with India-only roles; it is not watched (your filter is US).
- **LinkedIn** is blocked (see below). Its two other company ids in your bookmark (2587638, 39939) could not be
  identified without visiting linkedin.com, which its robots.txt forbids; they appear to be LinkedIn affiliate
  pages.
- **First run:** existing postings are recorded silently and summarised in one email, as requested.
- **Recipient** stays a placeholder in `config/settings.yaml` until you fill it in.

## Blocked companies and fallbacks

See the "Blocked companies" section of [COVERAGE.md](COVERAGE.md). They are never polled; the SimplifyJobs
cross-check covers them, and each entry says what else to do (usually: sign up for that company's own job-alert
emails).

## Layout

```
config/            settings.yaml (schedule, email, health thresholds) · companies.yaml · filters.yaml
src/internwatch/   runner, CLI, filters, health, cross-check, emails, db, http
  adapters/        one module per hiring system (shared)
  checkers/        custom checkers for sites that fit no adapter
tests/             pytest suite + recorded fixtures (offline)
deploy/            deploy.sh (one command), systemd service + timer
discovery/         how every site was investigated: notes, results, samples, scripts
data/              runtime: database, outbox, logs (not in git)
```
