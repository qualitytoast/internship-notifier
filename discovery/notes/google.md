# Google — job feed discovery

**Status:** verified-feed
**Checked:** 2026-10-19, 23:47–23:55 UTC (18:47–18:55 CDT). 15 logged requests (13 to www.google.com, 2 to careers.google.com), plus 6 robots.txt fetches made by `discovery/robots_check.py`. The feed body was downloaded once.

## Careers site
- **Official careers URL (job search, no filters):** https://www.google.com/about/careers/applications/jobs/results
- **Hiring system:** Google's in-house careers portal. It is a Boq app (`HiringCportalFrontendUi`) backed by Google Cloud Talent Solution (the SSR data names `projects/gweb-careers-proto/tenants/…/companies/…`). There is no third-party ATS. Applying goes through `…/applications/signin?jobId=…`.
- **Public job detail URL:** `https://www.google.com/about/careers/applications/jobs/results/<jobid>-<slug>/`
  - The feed's `<url>` still uses the legacy host: `https://careers.google.com/jobs/results/<jobid>-<slug>/`. That host returns **301** to the URL above (verified: `…/86455395526025926-/` → 301 → `https://www.google.com/about/careers/applications/jobs/results/86455395526025926-/`, 200, canonical link equals that URL).
  - To build the link, replace the prefix `https://careers.google.com/jobs/results/` with `https://www.google.com/about/careers/applications/jobs/results/` and keep the `<jobid>-<slug>/` tail unchanged.
  - The slug is empty (`<jobid>-/`) for 97 jobs with ja-JP or zh-Hans-CN titles. That form works: it is the one verified above.
  - All 3,773 `<url>` values contain `/results/<jobid>-`.

## Recommended feed
- **Request:** `GET https://www.google.com/about/careers/applications/jobs/feed.xml`
- **Query params:** none.
- **Headers:**
  - A normal browser `User-Agent`.
  - `Accept-Encoding: gzip`, which cuts the transfer from 22.7 MB to 4.4 MB.
  - `If-Modified-Since: <Last-Modified from the previous 200>`.
  - No cookies or tokens are needed.
- **Body:** none.
- **Pagination:** none. One document holds every job: `<jobs><updated>…</updated><job>…</job>×N</jobs>`.
- **Full enumeration cost:** 1 request, about 4.4 MB gzipped, about 0.7 s. When unchanged, it is a 304 with no body.
- **Detail/description endpoint:** not needed. `<description>` already holds the full posting as HTML.
- **Transfer sizes and caching** (measured with HEAD and a streamed GET at 23:47 UTC):

  | Request | Status | Content-Encoding | Content-Length (bytes on the wire) |
  |---|---|---|---|
  | `Accept-Encoding: identity` | 200 | – | **22,655,746** (21.6 MiB) |
  | `Accept-Encoding: gzip` | 200 | gzip | **4,427,827** (4.2 MiB). 4,427,827 raw bytes were read, which decode to 22,655,746 (ratio 5.1×) |

  - **Other headers:** `Content-Type: text/xml`, `Vary: Accept-Encoding`, `Accept-Ranges: bytes`, `Cache-Control: public, max-age=1500` (25 min), `Expires: Date+25 min`, `Last-Modified: Mon, 19 Oct 2026 23:24:37 GMT`, `Server: sffe`.
  - **There is no `ETag`**, so If-None-Match can't be used.
  - **If-Modified-Since works correctly:**
    - IMS equal to Last-Modified → **304 Not Modified**. No body is sent. The 304 carries `Age: 1`, `Last-Modified`, `Cache-Control` and `Expires`.
    - IMS older than Last-Modified (`Mon, 19 Oct 2026 22:00:00 GMT`) → **200** with the full gzip body. I closed that response after the first chunk.
  - **Freshness:** `<updated>2026-10-19T23:24:26.981135+00:00</updated>` (an element at the top of the document) matches Last-Modified 23:24:37Z. The newest `<published>` in the feed (23:09:38Z) is also the newest job on the live page sorted by date. The feed was therefore current when fetched, about 23 minutes after generation. A HEAD at about 23:55 UTC still returned `Last-Modified 23:24:37 GMT`. That response came from a front-end cache (`Date 23:47:46`, `Age: 423`). So regeneration takes more than 30 minutes, at least this time. I saw only one generation, so the exact cadence is unknown. With `max-age=1500`, polling more often than about every 30 minutes gains nothing.
- **Alternatives considered:**
  - The search page's SSR data (`AF_initDataCallback` `ds:1`, 20 jobs per page) has richer fields, such as creation time and degree level. But robots.txt **disallows every `page=` URL**, so only the first 20 results of any query can be read. It works as a cross-check, not as a feed.
  - There is no public JSON API.

## Field map (paths relative to one `<job>` element)
List path: `/jobs/job`. There is no total element: count the `<job>` elements. Feed timestamp: `/jobs/updated`.

| Field | Path | Example / notes | Present |
|---|---|---|---|
| id | `jobid` | `83093570004624070`. Always 17–18 digits and **all are above 2^53, so keep it as a string**. | 3773/3773 |
| title | `title` | `Software Engineering Intern, PhD, Summer 2027`. Can be in ja/zh/fr. | 3773 |
| location(s) | `locations/location/{city,state,country}` (repeated) | `Mountain View / CA / USA`. 1–36 locations per job (2,625 jobs have 1). See the quirks below. | 3773 jobs, 6,527 locations |
| detail URL | `url` → rewrite host (see above) | `https://careers.google.com/jobs/results/83093570004624070-research-engineer/` | 3773 |
| apply URL | – (not in feed) | The page uses `…/applications/signin?jobId=<opaque>`. Link to the detail URL instead. | – |
| posted date | `published` | ISO 8601 UTC, e.g. `2026-09-23T19:40:22.127Z`. **This is the last (re)publish time, not the creation time.** For example, job 75192738219205318 was created 2026-09-08 but has `published` 2026-10-19T22:12:36Z, and several 2027 intern roles created in Aug 2026 show `published` 2026-10-19. Range: 2025-07-30 to 2026-10-19; 2,344 of the jobs are dated October 2026. | 3773 |
| updated date | – | Only the feed-level `/jobs/updated` exists. | – |
| description | `description` | Escaped HTML in one blob: Minimum qualifications, Preferred qualifications, About the job, Responsibilities, and EEO boilerplate. Median 4.8k characters, maximum 9.4k. | 3773 |
| employment type / intern flag | `jobtype` | `FULL_TIME` 3679, **`INTERN` 93**, `PART_TIME` 1 | 3773 |
| employer | `employer` | `Google` 3503, `YouTube` 160, `DeepMind` 110 | 3773 |
| language | `languageCode` | `en-US` 3638, `ja-JP` 83, `zh-Hans-CN` 38, `fr-CA` 12, `fr-FR` 2 | 3773 |
| category | `categories/category` (repeated) | e.g. `SOFTWARE_ENGINEERING` 1039, `TECHNICAL_SOLUTIONS` 393, `PROGRAM_MANAGEMENT` 380, … `JOB_CATEGORY_UNSPECIFIED` 20 (24 values) | 3773 jobs, 3,925 values |
| remote | `remote` / `isRemote` / `isHybrid` | `onsite`/`remote` (65 remote); `No`/`Yes`; hybrid `Yes` 13 | 3773 |

- **Not in the feed:** no education level, degree, target level ("Intern & apprentice / Early / Mid …"), experience, salary, team, requisition number or creation date. Degree (BS/MS/PhD/MBA) appears only in the title and description text.
- **Location quirks:**
  - US country is usually `USA`, but 35 locations (in 11 remote jobs) hold a combined `"<ST>, USA"` with an empty city and the city in `state` (`['', 'Mountain View', 'CA, USA']`).
  - 10 locations use `country = "United States"` (`['', '', 'United States']`). Remote jobs can also be `['', 'Arkansas', 'USA']` or `['', '', 'United Kingdom']`.
  - Singapore (171) and Hong Kong (7) have an empty `country`.
  - Taiwan sometimes shows as `"New Taipei City, Taiwan"`.
  - A US matcher must accept `country in {"USA", "United States"}` or `country.endswith(", USA")`.

## Totals (observed 2026-10-19, around 23:47–23:56 UTC)
| Measure | Value | How observed |
|---|---|---|
| Feed total, no filters | **3,773** `<job>` (3,773 unique `jobid`) | Parsed feed.xml generated 23:24:26Z |
| Feed, English (`en-US`) only | 3,638 | Feed minus 135 translated postings (ja-JP 83, zh-Hans-CN 38, fr-CA 12, fr-FR 2), which have their own `jobid`s |
| Live careers page total, no filters | **3,643** ("3,643 jobs matched"), and 3,644 six minutes later | Plain GET of `/about/careers/applications/jobs/results` (first page, no params). Present in the server-rendered HTML text and in `AF_initDataCallback({key:'ds:1'…})` data as `[jobs…], null, 3643, 20]` (total, page size). The `?sort_by=date` view gave 3,644. |
| Intern (feed `jobtype=INTERN`) | **93** worldwide (85 en-US + 5 fr-CA + 3 zh-Hans-CN). **16 have a US location, 14 a Canadian one, 30 either.** | Feed parse |
| Intern-like union (`jobtype=INTERN` OR title `\bintern(ship)?s?\b`) | 94: adds "Part-Time Software Engineering PhD Intern, 2027", which has `jobtype=PART_TIME`. Of the 93 INTERN jobs, 21 have no "intern" in the title (12 en-US "Student Researcher" roles, 2 gReach roles, and fr/zh translations). Apprentice titles: 0. | Feed parse |
| Live page, `target_level=INTERN_AND_APPRENTICE` | 88, which includes **3 placeholder "Open … Career Opportunities, CapitalG Portfolio Companies"** postings (no level set) | GET `…/results?target_level=INTERN_AND_APPRENTICE` (first page) and `…&employment_type=FULL_TIME&employment_type=PART_TIME&employment_type=TEMPORARY` (6: 3 part-time PhD/BS-MS interns plus the 3 placeholders) |
| Bookmark search (tech categories + `jex=ENTRY_LEVEL` + `target_level=INTERN_AND_APPRENTICE`, `sort_by=date`) | 70, the same as the earlier Playwright capture. All 20 first-page jobs are in the feed (19 `INTERN`, 1 `PART_TIME`). | GET bookmark URL (no `page=`) |
| US jobs (any type) | 2,034 jobs have ≥1 US location | Feed parse |

**The discrepancy is explained** (page 3,643 vs feed 3,773):
- The English page does not count the 135 translated (non-en-US) postings, which leaves 3,638.
- The page shows 5 evergreen placeholder postings that are **not in the feed**:
  - 2 found with `company=Waymo&company=Wing`: "Open Career Opportunities, Wing" (2020) and "… Waymo" (2019).
  - 3 "Open … Career Opportunities, CapitalG Portfolio Companies" (2023, employer Google).
- 3,638 + 5 = **3,643**, an exact match. The +1 on the later fetch is live churn.
- Every job I saw on the page that was not a placeholder was in the feed: 20 relevance-sorted, 20 newest-first, 20 intern-level, 20 bookmark and the 6 intern-level non-INTERN jobs.

Intern-level page count (88) vs feed:
- 88 − 3 CapitalG placeholders = 85, against 85 en-US `INTERN` + 1 en-US `PART_TIME` intern in the feed. The feed and the page agree to within ±1.
- I couldn't enumerate the remaining one because robots forbids `page=`.
- **Translated duplicates:** the same role can appear twice with different ids, for example "Student Researcher, PhD, Fall 2026" (en-US) and "Étudiant-chercheur, doctorat, automne 2026" (fr-CA).

## robots.txt
www.google.com uses the `User-agent: *` group. The stricter `Disallow: /about/careers/applications/jobs/results` is only in a separate `Yandex` group. careers.google.com/robots.txt returns 404 (allow all).

| URL | Verdict | Rule (discovery/robots_check.py) |
|---|---|---|
| `https://www.google.com/about/careers/applications/jobs/feed.xml` | ALLOW | no matching rule (allowed) |
| `https://www.google.com/about/careers/applications/jobs/results` | ALLOW | no matching rule (allowed) |
| `…/jobs/results?sort_by=date` | ALLOW | no matching rule (allowed) |
| `…/jobs/results?target_level=INTERN_AND_APPRENTICE` | ALLOW | no matching rule (allowed) |
| `…/jobs/results?target_level=INTERN_AND_APPRENTICE&employment_type=FULL_TIME&employment_type=PART_TIME&employment_type=TEMPORARY` | ALLOW | no matching rule (allowed) |
| `…/jobs/results?company=Waymo&company=Wing` | ALLOW | no matching rule (allowed) |
| bookmark `…/jobs/results/?category=…&jex=ENTRY_LEVEL&target_level=INTERN_AND_APPRENTICE&sort_by=date` | ALLOW | no matching rule (allowed) |
| `https://www.google.com/about/careers/applications/jobs/results/86455395526025926-/` (job detail, empty slug) | ALLOW | no matching rule (allowed) |
| `https://www.google.com/about/careers/applications/jobs/results/91436104816698054-software-engineering-intern-phd-summer-2027/` (job detail) | ALLOW | no matching rule (allowed) |
| `https://careers.google.com/jobs/results/86455395526025926-/` (legacy `<url>`) | ALLOW | no robots.txt (allowed) |
| `…/jobs/results?page=2` (any `page=`) | **BLOCK** | `Disallow: /about/careers/applications/jobs/results?page=` (also `?*&page=` and the `/results/?` variants) |

## Anti-bot / gotchas
- I saw no anti-bot measures. A plain httpx GET with a browser UA works, with no cookies, consent wall or JavaScript challenge.
- The feed is large: 22.7 MB uncompressed. Always send `Accept-Encoding: gzip` and `If-Modified-Since`. Parse it with a streaming parser (`iterparse`) if memory matters.
- There is no ETag, so use Last-Modified only. A 304 costs no body. The 25-minute max-age means polling every 30–60 minutes is right.
- `<published>` moves forward whenever a posting is re-published. Many Aug-2026 intern roles show `published=2026-10-19`. Detect new jobs by **`jobid` never seen before**, not by date. A changed `published` on a known id means it was re-posted or edited, not a new job.
- The feed lacks the 5 evergreen "Open Career Opportunities" placeholders (Waymo, Wing, CapitalG). That is harmless for a watcher, but it means the feed total sits about 130 above the English page count. A health check comparing the two should compare **feed en-US + 5 ≈ page**.
- Translated twins (fr-CA, zh-Hans-CN, ja-JP) have separate `jobid`s. Dedupe or skip `languageCode != en-US` before notifying, or the user may get the same internship twice. Example: 5 fr-CA "Étudiant-chercheur…/Stagiaire…" intern postings duplicate English Canada roles.
- `<url>` points at the legacy careers.google.com host, which 301-redirects. Rewrite the prefix so emailed links go straight to the page.
- `jobtype=INTERN` misses part-time interns (1 is typed `PART_TIME`), and titles miss "Student Researcher" (typed `INTERN`, with no "intern" in the title). Use the union.
- Never fetch `results?page=` or `results?…&page=`, because robots.txt disallows them. The first page of any filtered search is allowed but is capped at 20 results.

## Recommended checker approach
1. Each poll (every 30–60 min, jittered), send `GET https://www.google.com/about/careers/applications/jobs/feed.xml` with a browser UA, `Accept-Encoding: gzip` and `If-Modified-Since: <stored Last-Modified>`.
   - On **304**, mark the poll healthy with no changes.
   - On **200**, store the new `Last-Modified` (and `/jobs/updated`) and parse the body.
2. Parse with `xml.etree.ElementTree.iterparse` on `job` elements. Map the fields:
   - id = `jobid` (string)
   - title
   - locations = `[city, state, country]` with the normalization above
   - url = rewritten `<url>`
   - posted = `published`
   - description = `html.unescape`-d `<description>` (already HTML)
   - employment type = `jobtype`
   - extras = employer, languageCode, categories, remote
3. Treat a job as student/intern if `jobtype == "INTERN"`, or the title matches `\bintern(ship)?s?\b|student researcher|apprentice`. Then apply the location filters. For e-mail, prefer `languageCode == "en-US"`, or group twins by title and location set.
4. Health: expect about 3,700–3,800 `<job>` elements and a non-empty `/jobs/updated`. Alert if the count drops by more than 50%, or if `/jobs/updated` hasn't advanced in more than 24 h.
   - An optional low-frequency cross-check (e.g. daily) is one GET of the unfiltered results page and reading `ds:1`[2], the total.
   - Expect page total ≈ count(en-US) + 5.
5. No per-job detail requests are needed.

## Sample
`discovery/samples/google.xml` (34 KB) is the real feed's XML declaration and `<jobs><updated>` header plus 4 verbatim `<job>` elements, closed with `</jobs>` (well-formed):
- a FULL_TIME DeepMind job (London), from the start of the feed
- `91436104816698054` "Software Engineering Intern, PhD, Summer 2027" (INTERN, 3 US locations)
- `131518356678156998` "Student Researcher, BS/MS, Winter-Summer 2027" (INTERN, no "intern" in the title)
- `86455395526025926`, a ja-JP posting with an empty slug (`…/86455395526025926-/`)
