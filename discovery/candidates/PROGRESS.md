# Stage 1 progress (companies added in November 2026)

Plan: /Users/nathanhung/.claude/plans/pasted-content-id-2f7d-add-the-reactive-matsumoto.md. Stage 1 is discovery only:
nothing in config/ or src/ changes. Tools: `discovery/stage1.py` (pages, lists, homes, hints, probe, read, sites,
coverage, clashes, rematch, backup, pagecount), run with `INTERNWATCH_HOME=data/stage1/home` (a copy of config/ and
data/; never the repo).

## Working files: data/stage1/ (gitignored, local only)
Moved from the session's temporary folder on 2026-11-09 (a restart wipes /private/tmp); the copy was checked file by
file with SHA-256 (1,141 files identical). Work from here:
- `home/`: the scratch home the reads ran in (config copy, database copy, robots.txt cache, log).
  `INTERNWATCH_HOME=data/stage1/home`; raw files then default to `data/stage1/raw/`.
- `home_moves/`: the scratch home of the backup-check measurement (`scripts/measure_backup.py`).
- `raw/jobs/<entry>.json.gz`: every job each Stage 1 read returned (374 reads): id, title, location, url, posted,
  department, alt ids. These are the jobs, not HTTP recordings; cassettes are recorded in Stage 2 with each company's
  final settings, as the plan requires.
- `raw/lists/`: the 11 third-party lists and Simplify's listings, downloaded once on 2026-11-09.
- `scripts/`: draft_settings.py, measure_backup.py. `base_list.tsv`, `draft.txt`, `facets.txt`, `*.log`: working notes
  and the logs of the page and read runs. `underclassmen.md`: the freshman/sophomore research (also committed as
  `underclassmen_research.md`). `notes/`: the Simplify name lists the candidate list was checked against.
- `prior-golden-nov7/`: the Nov 7 old-vs-new scripts (golden_replay.py, golden_filters.py) and the old code they
  compared against, which Batch 0 rebuilds into tools/prove/. Their 180 MB of outputs were left behind (regenerated
  by the scripts).

## Done (2026-11-09)
- `candidates.yaml`: 241 entries (Persona and Persona AI both), keys checked against the 198 (no clashes, no
  normalized-name clashes).
- `pages.json`: every careers page read once, robots.txt first. 29 refused scripts (403/406), 3 disallowed by
  robots.txt for all readers (Fortinet, SAS, ZipRecruiter), the rest answered; wrong URLs corrected via home pages.
- `simplify_evidence.json`, `lists.json` (the 11 third-party lists, downloaded once), `systems.json`,
  `draft_systems.json`: every job system each company is linked to, by source.
- `reads.yaml`: the checker + settings of each candidate's first full read (246 reads for 231 companies);
  `read_results.json`: jobs, students, matches, seconds, requests per read (raw jobs in data/stage1/raw/jobs).

## Special cases found so far (no read yet)
| Company | What it runs | Next |
|---|---|---|
| Costco | Jibe front careers.costco.com over iCIMS careers-costco.icims.com (Taleo TBE legacy) | read with `jibe` |
| UnitedHealth Group | Radancy TalentBrew front (org 34088) over Taleo uhg.taleo.net; sitemap ~24,600 URLs | read with `talentbrew`; very large |
| Tyler Technologies | Jobvite, company id q6NaVfwI (126 jobs on jobs.jobvite.com/tylertech) | read with `jobvite` |
| Precisely | Greenhouse `preciselyusjobs` (+ international page to check) | read |
| NetApp, Paramount, Qorvo | SAP SuccessFactors RMK sites (sitemaps: 317, 223, 8 job URLs) | new `successfactors` adapter (batch 6) |
| Bank of America | Workday tenant ghr (lateral sites) + campus roles on Oleeo bankcampuscareers.tal.net | new Oleeo reader for campus |
| ADP | jobs.adp.com marketing job site: sitemap answers (374 jobs), every page refuses scripts | sitemap-only titles, or blocked |
| Best Buy | jobs.bestbuy.com is a ServiceNow talent site | custom checker or blocked |
| Progressive | careers.progressive.com and progressive.com/careers refuse scripts; RippleMatch page exists | likely blocked; check RippleMatch |

## Findings from the full read (read_results.json; 246 reads, 162 worker-minutes, 8,503 requests)
- Walmart, Target, Lowe's, Bank of America: Workday reads fail on "N postings without externalPath" (a small
  partition's tolerance is max(3, total//50)); needs an opt-in per-company tolerance (default unchanged).
- CVS Health: 8,410 jobs read in 45 min (2,570 requests) and still cut short; 13 matching roles. Very large site.
- Delisted-but-open (ApplyWhenNotPosted) Oracle postings: American Express, JPMorgan, Texas Instruments, BNY →
  `learn_ids: true`. Rivian JV: an unlisted Ashby posting → `learn_ids`.
- robots.txt disallows the iCIMS portals of Charles Schwab, ICE and Northwestern Mutual. Schwab reads through its
  Radancy site (talentbrew, org 33727); ICE through Jibe; Northwestern Mutual through Workday.
- Moved/off: GlossGenius → Ashby geniusai; Dusty Robotics' Greenhouse board is off; Symmetry Systems redirects to
  Zscaler (acquired: fold into Zscaler); Sandisk's SmartRecruiters hosted page has no jobs (find another route);
  athenahealth is Phenom on careers.athenahealth.com; Comcast's live Workday host is wd115 (wd5 answers 422);
  nCino's Workday site answers 403 (Greenhouse boards instead).
- Short Workday tenants (ms, cox, fox, hp, kla, ptc, att, swa, fis) and ice.jibeapply.com: their host markers are
  substrings of other companies' hosts (Morgan Stanley would take Williams' rows) → opt-in: no raw host marker, an
  anchored `match_urls: ["//ms.wd5.myworkdayjobs.com/"]` instead.
- `simplify_coverage.json`, `rematch.json`, `name_clashes.json`, `workday_sites.json`, `list_check.json`,
  `backup_probe.json`, `backup_measure.json` (32 refused pages: ~54 requests, ~30 s a morning), `ripplematch.json`.
- Freshman/sophomore research: underclassmen_research.md (18 companies; keywords for BofA, Hartford, Citi, JPMC).

## Page counts (pagecounts.json, first pass)
- Workday, Oracle, Eightfold, Jibe, Phenom, SmartRecruiters: the system's own reported total (what the site shows).
  Gaps to explain: Citi 4,190 read vs 4,885 reported; Micron 2,881 vs 3,188; Arista 98 vs 147 (SmartRecruiters
  degraded); HPE partial; CVS cut short at 8,410.
- Greenhouse: the hosted board page states "N jobs" when it is served (Reddit: 154 = API). Many boards redirect to
  the company's own page, and boards.greenhouse.io/embed/ is disallowed by robots.txt, so those need the paginated
  hosted pages or a headless render of the careers page (robots.txt first). Ashby: the hosted page's own list.
  Lever: postings on the hosted page.

## Extra reads (read_results_extra.json; 128 reads, 36 worker-minutes, 978 requests)
- Read with existing adapters: UnitedHealth Group (talentbrew: 6,339 jobs, 87 matching, 41 s), Tyler (jobvite:
  145 jobs, 11 matching), Precisely (Greenhouse preciselyusjobs: 29).
- Costco's Jibe site reports ~18,000 jobs; the read stopped after 5,106 (997 s): a very large site.
- Mirrors: JPMorgan CX_2001 = CX_1001 (7,067), BNY CX_1 = CX_1001 (1,271); Texas Instruments' ebgj pod has 127
  other jobs (8 matching); Fortinet CX_1 1,051 (compare with CX_2001).
- Workday sites with student roles: Walmart Non-WorkdayInternal (2,693 jobs, 137 students, 5 matching), Mastercard
  CampusApplyOnly (10 students), Sonos Student_Opportunities (4), Synchrony careers, BofA Lateral-US, HPE WFMathpe,
  FOX FOXTVST_EAST, Cadence women-in-tech-scholarship, KLA Israel, McKesson CoverMyMeds, Elevance carelonglobal_ph.
  69 robots.txt sites are empty today.
- RippleMatch: DraftKings 6, Mercor 4, Progressive 1, UnitedHealth 1, Reddit/Roku/Snap/Verizon 0.
- Dead boards the lists still link: Ashby conductorone and superhuman (404) → aliases to the live boards.

## Very large sites (workday_facets.json): full daily read against a student slice
Workday costs ~1.0-1.5 s a request (20 jobs, unpartitioned); sites over the 2,000 cap are split and cost far more
(CVS: 3.3 jobs a request). Full read vs slice (facet counts on 2026-11-09):
| Company | Jobs | Full read | Student facet | Slice |
|---|---|---|---|---|
| CVS Health | 19,089 | >2 h (45 min read 8,410) | jobFamilyGroup "Internships and Devlpmt Pgms" 3,988 (mostly pharmacy) | ~200 req, ~4 min |
| Lowe's | 13,007 | ~15 min+ (failed at 940 s, malformed) | none: keyword search | — |
| Costco (Jibe) | ~18,000 | ~1 h+ (5,106 in 997 s) | category facet | — |
| Citi | 4,885 | 14 min, 810 req | Intern (Paid) 16, Apprentice 114 | ~6 req |
| GE Vernova | 2,177+ | 7.4 min | Co-op/Intern 179 | ~9 req |
| Dick's | 3,648 | 5.7 min | Students and Recent Grads 5 | 1 req |
| Micron | 2,882 | 5.2 min | Intern 141 | ~8 req |
| Walmart, Target | capped (>2,000) | failed (malformed) | Intern 34 / Internships 108 | 2-6 req |
Medium (full read is fine, ≤4 min): Applied Materials, HPE, BofA, HP, KLA, Morgan Stanley, Wells Fargo, Verizon,
AT&T, Home Depot (932 on the main site), Nike; Oracle sites are cheap (JPMorgan 7,065 jobs in 36 requests).

## Companies existing code can't read yet (probed 2026-11-09; new_systems_measure.json)
Each probe went through the project's client (robots.txt first). Jobs/students/matching from the site's own list.
| Company | Where its jobs are | What reading it takes | Requests a day | Jobs / students / matching |
|---|---|---|---|---|
| Costco | IT jobs on Taleo Business Edition (phf.tbe.taleo.net, org COSTCO, site 41): one RSS feed with every job ("Costco IT Job Feed"). careers.costco.com (Jibe, 18,698 warehouse jobs, Crawl-delay 5) has none of them; all 8 stored Simplify rows link the Taleo site | small new reader for the Taleo feed (`taleo_tbe`) | 1 | 41 / 25 / 22 (Costco Digital Services interns) |
| Sandisk | moved off SmartRecruiters (company empty; all 7 listed postings closed). Careers page links avature.sandisk.com/Careers; its list is drawn in the browser, its RSS feed shows the 20 newest only, its sitemap lists every job page (502) | new sitemap reader: titles from links, job page read for new student roles (location, date) | 1 + new student roles | 500 / 17 / 14 |
| NetApp, Paramount, Qorvo | SAP SuccessFactors sites (jobs.netapp.com, careers.paramount.com, careers.qorvo.com): server-rendered search pages, 25 a page, with title, location, date. robots.txt disallows /services/ (RSS) only | new `successfactors` reader of the search pages | 13 / 9 / 1 | NetApp 320 / 13 / 5 (1 in the US); Paramount 223 / 2 / 0; Qorvo 8 / 6 / 6 |
| Bank of America (campus) | Oleeo bankcampuscareers.tal.net: boards 1 (Global Programs, 20), 2 (Campus Events, 5), 5, 6 (Japan, 2+2), each with a complete Atom feed. Crawl-delay 10 | new `oleeo` reader (feeds) | 4 (40 s) | 29 / 16 / about 5 (US quant programs, Early Insights) |
| Morgan Stanley (campus) | Oleeo morganstanley.tal.net board 1 (72 programs, 50 a page; feed switched off) and board 2. Crawl-delay 10 | same `oleeo` reader (pages) | 3 (30 s) | 72 programs; page 1: 50 / 45 / 3 US |
| Best Buy | ServiceNow portal jobs.bestbuy.com: the list comes from a scripted service the page calls in the browser. Its sitemap (bestbuy.service-now.com) lists 2,252 job pages by requisition number; a job page carries its title but weighs 1.1 MB | custom checker: sitemap + one page per new requisition (about 130 a day; 2,252 on day one, 2.4 GB) | about 131 | 2,252 (mostly store roles) |
| ADP | jobs.adp.com refuses scripts on every page; its sitemap answers: 690 jobs (8 languages each), titles in the links, no location | sitemap-only reader (titles, location unknown, so tagged unsure) | 1 | 690 / 8 / 5 |
Read with existing code after all: Dusty Robotics (Rippling `dusty-robotics-inc`, 2 jobs; the Greenhouse board is gone),
Precisely (Greenhouse preciselyusjobs + preciselyinternationaljobs, 55), athenahealth (Phenom careers.athenahealth.com,
83), Charles Schwab (TalentBrew schwabjobs.com, 284). Fortinet: CX_1 and CX_2001 are mirrors (1,050 jobs in common, 1
extra on CX_1); read CX_2001 (Simplify links it), CX_1 becomes a mirror alias.

## Very large Workday sites: count gaps explained, and a cheaper full read (workday_partitions.json)
- Citi 4,190 read vs 4,885 and Micron 2,881 vs 3,188: the larger number adds up each location's count, so a job in
  several cities counts several times. The sites' own totals (time type and worker type counts) are 4,186 and 2,884.
- CVS, Target, Lowe's and Bank of America's us-emplsv split below Workday's 2,000-job cap only by single locations
  (4,991 / 2,117 / 1,873 / 2,763 searches). Workday matches any of several values in one search (tested: 19 CVS
  locations whose counts add to 1,900 returned 1,399 jobs), so packing locations into searches of under 1,900 cuts
  CVS from about 5,300 requests to about 1,000-1,300. Measured in read_results_big.json (STAGE1_PACK=1, scratch only).

## Copies, side sites and subsidiaries (measured by job overlap)
- Copies to record as known, not read: Fortinet CX_1, BNY CX_1 and bny-careers, JPMorgan CX_2001, Hilton CX_1009,
  Macy's CX_1001 (a subset), TI edbz CX_1, Applied Materials' Eightfold front, HPE WFMathpe (1,697 of 1,715
  requisitions on the main site), Bank of America Lateral-US (1,985 of 1,987 on us-emplsv), GE Vernova's
  only_confidential_executive_recruiting (248 jobs beyond the main site, none a student role).
- Extra boards with their own jobs, to read: TI ebgj (127), HP Inc. Greenhouse (59), Snyk Ashby (37), Circle Ashby (6),
  DriveWealth Ashby (28, 10 of them new), Best Buy Canada Workday (64; avoids a day-one list alert).
- Workday public sites (104 unread): 9 with student roles (read 7; WFMathpe and Lateral-US are copies), 27 with jobs
  but no student roles and 68 empty (recorded as known: the first look at a tenant is a silent baseline anyway).
- Subsidiaries with boards of their own: NBCUniversal (Comcast; SmartRecruiters NBCUniversal3: 525 jobs, 138 student,
  54 matching), Tubi (FOX; Greenhouse tubitv: 24, 0 student), FOX TV Stations (3 Workday sites, 50, 1), CoverMyMeds and
  Sarah Cannon (McKesson sites, 20 and 19), CenterWell (Humana site, 1,833, 0), Depop (Etsy site, 23, 0), Simply
  Business (Travelers site, 9, 0), NPA (Copart site, 20, 0), BA Continuum (BofA India site, 115, 0).

## Page counts (ghpages.json, second pass)
Oracle, Jibe, Workday and Eightfold reads are checked against the site's own total by the reader itself (a read
outside 1.5% fails), so those are verified. Greenhouse boards that redirect to the company's own page: the company
page links all of the read's jobs at Amperity, Descript, Fastly, Gemini, SoFi, ZoomInfo; Ripple's page is paged (78 of
117 on page one); about 19 pages draw their list in the browser (a render at batch time); Chime and Rubrik refuse
scripts.

## Matching roles without repeats (matched_dedup.json)
Multi-site reads list the same job twice (GE Vernova's two sites, HP's EU site): the jobs table treats a repeat with the
same title and location as a repost. Counted without repeats: 88,890 distinct jobs, 3,209 student roles, 1,606
matching (1,111 of them unsure), before the very large sites' full reads.

## Backup checks per company (backup_table.md)
32 companies: careers page (weekly while refused), WordPress pages (Cox, Match Group, YugabyteDB), job sitemaps (ADP,
Box, Cox, DraftKings, Intuitive, Wells Fargo), program pages, archive.org (21 with copies, weekly), hidden Workday sites
(cached robots.txt, no request), RippleMatch side boards (DraftKings, Progressive, Verizon). First morning: 54
requests, 30 s.

## Very large sites, measured both ways (read_results_big.json, slice_compare.json)
Full reads with locations packed (STAGE1_PACK, scratch only): CVS 19,078 jobs in 19.3 min (1,134 requests, 37
searches instead of 4,990), Walmart 20,474 in 20 min (1,143), Target 14,142 in 16.7 min (831, 15 searches instead of
2,117), Lowe's 13,001 in 12.9 min (757), Bank of America 3,107 in 6.1 min (366, 20 searches instead of 2,757).
Workday answers a search of 400 location values with an error (200 work), so packed searches hold at most 150.
Student reads: Walmart 2 requests, CVS 3, Target 6, Lowe's 11 (a search for "intern"). Matching roles the student
reads miss: Walmart 9 of 27, CVS 2 of 17, Target 2 of 26, Lowe's 0 of 19; 12 of the 13 are tagged unsure.

## Dry runs with the planned names and links
candidates.yaml now carries the plan's aliases; the dry runs give multi companies `match_urls` from their boards and
match the short Workday names (ms, hp, ...) from the start of the address, as the plan's config will. Coverage: 834
open Simplify rows at 111 companies, 27 not found (16 open but unlisted: one-by-one lookup; 9 closed at the company;
2 NBCUniversal). Re-match: 1,121 stored rows to 134 companies, 225 open get checks, 162 already shown, 3 day-one
possible misses.

## Stage 1 report
`STAGE1_REPORT.md` (written 2026-11-09): TLDR, the 6 decisions with measured numbers, the code changes, the batches,
the evidence and the table of every company (`companies_table.md`). The analysis scripts behind plan.json,
companies_table.md, matched_dedup*.json, now_watching.json, backup_table.md, new_systems_measure.json and
slice_compare.json are in data/stage1/scripts/ (build_plan.py, report_table.py, matched_dedup.py, now_watching.py,
backup_table.py, new_systems_measure.py, slice_compare.py, rmk_read.py, fetch.py).

## Next
Stage 1 is complete. Waiting for your answers to the report's 6 decisions; then Stage 2, batch 0 (groundwork).
