# Stage 1 progress (companies added in November 2026)

Plan: /Users/nathanhung/.claude/plans/pasted-content-id-2f7d-add-the-reactive-matsumoto.md. Stage 1 is discovery only:
nothing in config/ or src/ changes. Tools: `discovery/stage1.py` (pages, lists, homes, hints, probe, read), run with
`INTERNWATCH_HOME=<scratch home>` (a copy of config/ and data/; never the repo).

## Done (2026-11-09)
- `candidates.yaml`: 241 entries (Persona and Persona AI both), keys checked against the 198 (no clashes, no
  normalized-name clashes).
- `pages.json`: every careers page read once, robots.txt first. 29 refused scripts (403/406), 3 disallowed by
  robots.txt for all readers (Fortinet, SAS, ZipRecruiter), the rest answered; wrong URLs corrected via home pages.
- `simplify_evidence.json`, `lists.json` (the 11 third-party lists, downloaded once), `systems.json`,
  `draft_systems.json`: every job system each company is linked to, by source.
- `reads.yaml`: the checker + settings of each candidate's first full read (246 reads for 231 companies);
  `read_results.json`: jobs, students, matches, seconds, requests per read (raw jobs in the scratch folder).

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
- Freshman/sophomore research: scratch underclassmen.md (18 companies; keywords for BofA, Hartford, Citi, JPMC).

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

## Next
1. Read the special cases that existing adapters can read (Costco, UHG, Tyler, Precisely).
2. Per company: Workday robots.txt sites (from the reads' cached robots.txt), lists check with candidate settings,
   page systems against config, Simplify coverage against each read, re-match dry run, name-clash counts.
3. Page counts with filters off, explained differences; backup checks for the refused careers pages.
4. Freshman/sophomore programs; run-time model; the Stage 1 report.
