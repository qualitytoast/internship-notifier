# Stage 1 report: adding 240 companies (November 2026)

Discovery only: nothing in `config/` or `src/` has changed. Every number below was measured between Nov 9 and Nov 10,
2026 with InternWatch's own readers, robots.txt checked before every request and at most one request a second per site
(slower where a site asks). The evidence is in `discovery/candidates/` (one file per check, listed at the end) and the
working files in `data/stage1/` (local only).

## TLDR

- **All 240 companies can be watched.** 233 can be read with code InternWatch already has. 6 need a small new
  reader (Sandisk, NetApp, Paramount, Qorvo, ADP, Best Buy), and so do parts of 3 more (Costco's IT jobs, and Bank of
  America's and Morgan Stanley's campus programs). Progressive can only be read through a RippleMatch page with one
  role.
- **What's there today:** about 89,000 jobs, 3,400 student roles and 1,700 roles that pass your filters (about 1,200
  of them tagged unsure). Five giant store, pharmacy and warehouse sites add 55,000 to 74,000 more jobs if read in full.
- **Nothing changes for the 198.** The new companies run after them each morning with their own workers and time
  limits, and every batch is proven the way earlier changes were.
- **The morning email arrives later:** about 12 to 16 minutes later if the five giant sites are read for their student
  roles each morning (with a full read once a week), about 30 minutes later if they're read in full every morning.
  Mornings take 22 to 34 minutes today.
- **Alerts on the batches' first mornings:** about 6 in all, each predicted here (3 lists that file another
  company's site under an added name, 3 postings Simplify still lists after they closed), plus one "Now watching"
  email per batch with 30 to 490 roles.
- **6 decisions for you**, each with my recommendation.

## Decisions for you

### 1. The five giant store, pharmacy and warehouse sites
CVS, Walmart, Target, Lowe's and Costco's warehouse site list 13,000 to 20,500 jobs each. Your filters reject store,
pharmacy and warehouse roles, so almost none of them can ever be emailed. Both ways were measured on Nov 9 (the full
reads with code change 2):

| Site | Jobs | Full read every morning | Student roles only | Matching roles: full read / student read |
|---|---|---|---|---|
| Walmart | 20,474 | 20 min, 1,143 requests (24 min with its second site) | 3 s, 2 requests (its "Intern" job family) | 27 / 18. The other 9: 7 pharmacy "Pre Grad Intern" postings at Sam's Club, 2 "Intern Conversion" full-time offers |
| CVS Health | 19,078 | 19 min, 1,134 requests | 5 s, 3 requests (worker type "Intern") | 17 / 15. The other 2: clinical student rotations (RN-to-BSN, Physician Associate) |
| Target | 14,142 | 17 min, 831 requests | 11 s, 6 requests (its "Internships" job family) | 26 / 24. The other 2: full-time programs starting in 2027 |
| Lowe's | 13,001 | 13 min, 757 requests | 22 s, 11 requests (a search for "intern") | 19 / 19 |
| Costco's warehouse site | 18,698 | 187 pages at the 5 seconds between requests its robots.txt asks for: 16 min at best (the Stage 1 read got 52 pages in 17 min) | 30 s, 6 requests (its non-warehouse categories and a search for "intern") | 0 / 0. Costco's tech internships are on its IT site (decision 3) |

Of the 13 matching roles the student reads miss, 12 are tagged unsure. One is a sure match: Walmart's "2026 Intern
Conversion: 2027 Field Supply Chain - Quality Engineer". Bank of America's main site (3,107 jobs) is read in full
either way, in 6 minutes.

- (a) **Full read every morning**, as the 198 are read. The morning email about 30 minutes later (Walmart's two
  sites alone take 24 minutes, so more workers don't help). The database grows by about 135 MB on day one instead of
  100, then about 1,500 more store postings a weekday.
- (b) **Recommended: student roles every morning, plus a full read once a week**, each site on its own weekday. This
  is how NVIDIA is read today: its interns every morning, its whole site weekly as a watched board that raises an
  alert for any matching role InternWatch doesn't have. The morning email 12 to 16 minutes later; the weekly read adds
  up to 20 minutes on its own morning. The risk: a matching role posted outside the student label (13 today, 12 of
  them unsure) reaches you within a week, as an alert rather than as an email the morning it's posted.

### 2. How many companies the added round checks at once
Minutes the morning email arrives later, on top of today's 22 to 34:

| Workers | With student reads (1b) | With full reads (1a) |
|---|---|---|
| 8 (as the 198) | 16 | 30 |
| 12 | 12.5 | 30 |
| 16 | 12.3 | 30 |

Each round adds about 5.5 minutes after its checks: a retry of anything that failed (only on mornings when
something did), the careers-page scan of about 209 pages, the backup checks, side boards and the cross-check. More
workers only change how many different sites are read at the same moment; each site still gets at most one request
a second (slower where it asks), and the 198's run is over before the round starts.
- **Recommended: 12.** Past 12, the longest single reads set the length.
- A faster variant: start the added companies during the 198's run, on sites the 198 never use, while 4 to 7 of its 8
  workers sit idle (from about 7 to 18 minutes in). It would save up to about 10 minutes, but it changes what runs
  alongside the 198's checks, so "unchanged" could only be shown by timing, not by the exact replays.
  Recommended: not now; worth a look once all batches are in.

### 3. Which new readers to build
Nine sites hold jobs today's code can't read. Each needs a small new reader, written and tested in batch 6. Without
one, that site's jobs reach you only when SimplifyJobs lists them ("via Simplify"), and only if it does. Measured on
Nov 9:

| Site | What reading it takes | Requests each morning | What it holds today | My recommendation |
|---|---|---|---|---|
| Costco's IT jobs | one feed on Costco's Taleo site lists every IT job | 1 | 41 jobs, 25 student roles, 22 matching (Costco Digital Services interns). All 8 Costco rows Simplify ever listed are here; the main careers site has none of them | build |
| Sandisk | its new Avature site draws the list in the browser, but its sitemap lists every job page; titles come from the links and new student roles get their page read for location and date | about 3 | 500 jobs, 17 student roles, 14 matching | build |
| NetApp, Paramount, Qorvo | one reader for SAP SuccessFactors search pages (25 jobs a page, with title, place and date) | 13, 9 and 1 | NetApp 320 jobs, 13 student, 1 matching in the US; Paramount 223, 2, 0; Qorvo 8, 6, 6 | build (one reader, three companies) |
| Bank of America and Morgan Stanley campus programs | one reader for Oleeo job boards (Bank of America has a feed per board; Morgan Stanley's feed is off, so its two pages are read). Their robots.txt asks for 10 seconds between requests | 4 and 3 (70 s together) | Bank of America 29 programs and events (about 5 matching, including Early Insights); Morgan Stanley 72 programs (3 in the US match on the first of its two pages) | build: the banks' summer programs are only here, not on their Workday sites |
| ADP | every ADP page refuses scripts; its sitemap answers with every job's link, which holds the title | 1 | 690 jobs, 8 student roles, 5 matching. No location, so each is tagged unsure | build |
| Best Buy | its job site runs on ServiceNow and draws the list in the browser. Its sitemap lists 2,252 jobs by number only; each job page (1.1 MB) gives the title. About 130 job pages change a day | about 130 (about 3 min, 140 MB); 2,252 pages (2.4 GB, about 45 min) on the first morning, which can be spread over several | 2,252 jobs, mostly store roles; corporate internships open seasonally. No Simplify row has ever listed Best Buy | build, trying first in batch 6 to call the site's own job search (one request a page, if it allows it); the sitemap route if not |

### 4. Subsidiaries with boards of their own
The plan reads a parent's own sites when they hold student roles (FOX TV Stations and McKesson's CoverMyMeds site
are already in). These boards need your OK:

| Subsidiary | Board | Jobs | Student roles | Matching | Requests / seconds each morning |
|---|---|---|---|---|---|
| NBCUniversal (Comcast) | SmartRecruiters NBCUniversal3 | 525 | 138 | 54 | 49 / 118 s |
| Tubi (FOX) | Greenhouse tubitv | 24 | 0 | 0 | 2 / 1 s |
| CenterWell (Humana) | Humana Workday site | 1,833 | 0 | 0 | 92 / 96 s |
| Depop (Etsy) | Etsy Workday site | 23 | 0 | 0 | 2 / 3 s |
| Sarah Cannon Research Institute (McKesson) | McKesson Workday site | 19 | 0 | 0 | 1 / 3 s |
| Simply Business (Travelers) | Travelers Workday site | 9 | 0 | 0 | 1 / 1 s |
| NPA (Copart) | Copart Workday site | 20 | 0 | 0 | 1 / 1 s |
| BA Continuum, India (Bank of America) | Bank of America Workday site | 115 | 0 | 0 | 6 / 21 s |

- **Read as part of the parent**: their matching roles are emailed like the parent's.
- **Leave out**: nothing is read. Depop, CenterWell and Sarah Cannon are linked by the board registry, so each would
  raise one `new job site?` alert on day one unless recorded as known (see decision 5).

My recommendation: read NBCUniversal (54 matching roles today, 2 minutes a morning) and Tubi (a tech company,
2 requests); leave the other six out and record them as known.

### 5. The alerts expected on day one
6 in all, spread over the batches' first mornings, all predictable:
- **3 list rows that file another company's site under an added name**: Fox Factory's Workday site filed as "FOX"
  (zshah101's registry), HP Inc.'s as "Hewlett Packard Enterprise" (Boardsweep), the Rivian-VW joint venture's board
  as "rivian" (Trackr). Dismissing such an alert makes InternWatch read that board every morning as the company's own
  (that's how dismissed boards work), so a Fox Factory internship would later show up as a FOX alert.
  - (a) Dismiss them and accept that.
  - (b) **Recommended**: a small setting that records "this board is known, don't read it" (empty for the 198, so
    nothing changes for them). It also records the subsidiaries you leave out in decision 4.
- **3 possible misses**: Simplify still lists these as open, but the postings are already closed at the company
  (Marvell's "Data Science Intern", Rubrik's "Software Engineering Intern", Western Digital's data analytics
  co-op). They clear themselves when Simplify closes the rows.
  - (a) **Recommended**: let them come and dismiss them.
  - (b) Mark those rows as resolved at go-live.

### 6. Progressive
Every Progressive careers page refuses scripts. Its only readable listing is a RippleMatch page with 1 role (a
claims trainee).
- (a) **Recommended**: make that RippleMatch page its checker. It then counts as a watched company, so it also gets
  the backup checks (its careers page weekly, the program pages in progressive.com's sitemap) with no new code.
- (b) Mark it `blocked`: covered by Simplify only, and its backup checks would need new code.

## What Stage 2 changes in the code (no decision needed)

Each change is a setting the 198 don't use, so their default stays exactly today's behavior; every batch proves it
with the old-against-new replays from the plan.

1. **Workday sites that list a posting without a link** (Walmart, Target, Lowe's, Bank of America): today a handful
   of them stops the whole read, because the limit follows the size of the part of the site being read, not the
   site. A per-company setting skips them instead (they hold no title, link or place). They come and go: Bank of
   America had 4 on the first read and none on the second; Walmart had 22, Target 2 (each listed twice).
2. **Packing store locations into a few searches** (CVS, Target, Lowe's, Bank of America): a per-company setting that
   asks Workday for many locations in one search. Bank of America's full read went from 2,757 searches to 20.
3. **Exact address matching for short Workday names** (Morgan Stanley `ms`, Cox `cox`, FOX `fox`, HP `hp`, KLA `kla`,
   PTC `ptc`, AT&T `att`, Southwest `swa`, FIS `fis`, and ICE's `ice.jibeapply.com`): today an address is matched
   anywhere inside a link. Two collide today: Morgan Stanley would take Williams' and Marshfield Clinic's postings
   (`williams.wd5…` contains `ms.wd5…`) and HP Inc. the `ensemblehp` tenant's (`ensemblehp.wd5…` contains
   `hp.wd5…`). These companies match the start of the address instead; the other eight collide with nothing today and
   get the same setting as a precaution.
4. **Postings that are open but unlisted** (American Express, JPMorgan Chase, Texas Instruments, BNY on Oracle;
   the Rivian-VW joint venture on Ashby): Simplify's rows for them are looked up one by one, as for Dell today.
5. **Program titles the filters don't catch**, as per-company keywords (they only add matches): The Hartford "Early
   Immersion Program", Citi "D1 Athlete Development Program", USAA "Accelerate Program", Verizon "Sprinternship".
6. **SmartRecruiters searches that overstate their count** (Arista: says 147, returns 98): a per-company setting that
   compares the read with the postings the search really returns, so Arista's reads aren't marked degraded daily.
7. **The new readers you approve** (decision 3), as new modules with their own tests.
8. Configuration only, with existing settings: configured searches for Citi (810 requests a morning down to 244),
   Dick's (308 to 208), Micron (301 to 202) and GE Vernova; `dedupe` where a company's Workday sites repeat each other
   (HP's EU site repeats 911 of HP's jobs, KLA 150); copies recorded as mirrors; RippleMatch pages as side boards.

## Batches

Batch 0 (groundwork, no companies) comes first: the added round with its own workers and limits, the go-live
re-match and the "Now watching" rules, the proof tools, and code changes 1 to 6 (each off for the 198). Then one batch
per hiring system, each verified, tested, proven unchanged for the 198 and pushed, with a morning run between batches.

| Batch | Hiring systems | Companies | "Now watching" roles (email size) |
|---|---|---|---|
| 1 | Greenhouse | 77 | 91 (about 172 KB) |
| 2 | Ashby, Lever, Rippling, RippleMatch (Progressive) | 60 | 119 (about 225 KB) |
| 3 | Workday up to 2,000 jobs | 60 | 487 (about 921 KB) |
| 4 | Workday over 2,000 jobs (CVS, Walmart, Target, Lowe's, Bank of America, Citi, GE Vernova, Micron, HPE, HP, Dick's, Applied Materials) | 12 | 366 (about 692 KB) |
| 5 | Oracle, Eightfold, SmartRecruiters, Jibe, Phenom, Radancy, Jobvite, iCIMS | 25 | 459 (about 868 KB) |
| 6 | the new readers you approve: Sandisk, NetApp, Paramount, Qorvo, ADP, Best Buy, plus Costco's IT site and the two campus sites for companies already live | 6 | about 60 with Costco's IT interns and the campus programs |
| 7 | final pass: README, COVERAGE.md, UNDERCLASSMEN.md, the run-time report | - | - |

"Now watching" leaves out the roles you already saw in an untracked list (counted). The first-ever seed was 1,143
roles at 167 companies, so batch 3's email is about half that size.

## Evidence

### Who they are and how they're read
- 240 companies: the 240 names you listed, with Persona as two companies (identity verification and Persona AI)
  and Symmetry Systems folded into Zscaler (it was acquired; its site redirects to zscaler.com). Optum is read as
  UnitedHealth Group, Tinder and Hinge as Match Group, NYSE as ICE, Grammarly as Superhuman, Walmart Global Tech as
  Walmart's own site. None was watched before under any name, alias, board or mirror.
- Main hiring system: Greenhouse 77, Workday 73, Ashby 51, Oracle 9, Lever 7, iCIMS Jibe 6, SmartRecruiters 3,
  SuccessFactors 3, Phenom 2, Radancy 2, Eightfold, Rippling, Jobvite, iCIMS, Avature and ADP's own site 1 each.
  19 companies read more than one board.
- Today they list 89,337 jobs (repeats removed; the five giant sites through their student roles), 3,449 student
  roles and 1,687 roles that pass your filters (1,175 of them tagged unsure). Read in full, the giant sites bring the
  total to 144,323 jobs (163,000 with Costco's warehouse site), 6,846 student roles (CVS's pharmacy interns, mostly)
  and 1,697 matching.
- Fixed while reading: GlossGenius moved to Ashby (`geniusai`), Dusty Robotics to Rippling (`dusty-robotics-inc`),
  Comcast's Workday answers on `wd115` (not `wd5`), athenahealth's jobs are on careers.athenahealth.com (Phenom),
  Charles Schwab is read through schwabjobs.com (its iCIMS portal is closed to scripts by robots.txt), ICE through
  Jibe, Northwestern Mutual through Workday **and** SmartRecruiters (its 7 tech internships are only on
  SmartRecruiters), Precisely has a second Greenhouse board for jobs outside the US, nCino's Workday site answers 403
  (its Greenhouse boards are read).

### Copies and extra boards (measured by job overlap)
- Recorded as copies, not read twice: Fortinet CX_1 (1,050 of 1,051 jobs shared), BNY's two other Oracle sites,
  JPMorgan CX_2001, Hilton CX_1009, Macy's CX_1001 (a subset), TI's edbz site, Applied Materials' Eightfold front
  over Workday, HPE's WFMathpe site (1,697 of 1,715 requisitions shared; none of the other 18 is a student role),
  Bank of America's Lateral-US (1,985 of 1,987 shared), Qualcomm's `qualcomm.eightfold.ai` (same site as
  careers.qualcomm.com), and the dead Ashby boards `conductorone` and `superhuman` that lists still link.
- Extra boards with jobs of their own, read: TI's ebgj site (127 jobs, 8 matching), HP Inc.'s Greenhouse board (59,
  8), Northwestern Mutual's SmartRecruiters page (69, 7), Snyk's Ashby board (37), DriveWealth's Ashby board (10 jobs
  not on its Greenhouse board), Circle's Ashby board (6), Best Buy Canada's Workday site (64).
- GE Vernova's second site (`only_confidential_executive_recruiting`) adds 248 jobs, none a student role: not read,
  like every site without student roles.

### Workday sites a company's robots.txt lists
104 public sites aren't read yet. 9 have student roles: 7 are read (FOX TV Stations East, Sonos Student
Opportunities, Walmart Non-WorkdayInternal with 137 student roles, McKesson's CoverMyMeds, KLA Israel, Cadence's
women-in-tech scholarship, Elevance's Philippines site); 2 are copies (HPE WFMathpe, Bank of America Lateral-US).
27 have jobs but no student role (agency, contractor, foreign and subsidiary sites) and 68 are empty. The first look
at a tenant is a silent baseline, so none of them raises `new site` on day one; a site that appears later does.

### Third-party lists (the `new job site?` check)
The same code that raises `new job site?` ran over the 11 lists downloaded on Nov 9. 27 companies are linked to 31
boards not in their planned config. All but 3 are handled by the plan: copies recorded as mirrors, the extra boards
above read, RippleMatch pages read as side boards (DraftKings, Mercor, UnitedHealth, Progressive, Reddit, Roku, Snap,
Verizon: one request each), the short-name fix for Morgan Stanley, subsidiaries per decision 4. The 3 left are lists
filing another company's site under an added name (decision 5).

### Careers pages
205 careers pages answered, 29 refused scripts (403 or 406) and 3 are closed by robots.txt (Fortinet, SAS,
ZipRecruiter). 4 didn't load and get a corrected address in their batch: Cobot's and Persona AI's addresses return
404, Synchrony's site fails at the secure-connection step, Xcimer's robots.txt didn't answer (their boards read
fine). 9 pages name job systems that aren't read directly; each is a front over what is read (American Express, Citi, HP and Micron on Eightfold; Keysight, Principal, Rivian and State Farm iCIMS portals behind Jibe;
Nike's Avature talent community) and is recorded as a mirror, so the `moved?` check's silent first look starts clean.

### Job counts checked against the sites
- Oracle, Jibe, Workday, Eightfold and SmartRecruiters reads are checked by the reader itself against the site's own
  total (a read more than 1.5% short fails): all passed.
- Ashby and Lever: the hosted job page's own list matches the read at every company that has one (53 and 6).
- Greenhouse: 49 hosted boards state their count and match. 31 boards redirect to the company's own page: at
  Amperity, Descript, Fastly, Gemini, SoFi and ZoomInfo that page links every job read; Ripple's page shows 78 of
  117 on its first page (it pages); about 19 pages draw their list in the browser and are counted with a headless
  render at batch time; Chime's and Rubrik's pages refuse scripts, so only the board itself can be counted.
- Gaps explained: Citi's 4,885 and Micron's 3,188 count a job once per city; the sites' own totals (4,186 and 2,884)
  match the reads (4,190 and 2,881). Arista's SmartRecruiters search says 147 but returns 98 postings, the same 98 on
  every page; the read has all 98. The reader marks a read under 95% of that count as degraded, so Arista needs a
  small opt-in setting (code change 6).

### Careers pages that refuse scripts: backup checks
32 careers pages refuse scripts (29) or are closed by robots.txt (3). Each of these companies joins
`liveness.blocked` and gets every backup check it has something to read for, chosen as for today's 32, run in the
added round within its own time budget; every first look is silent. Measured once in a scratch copy: 54 requests and
30 seconds on the first morning. Later mornings read less: a page that refuses waits a week before the next try, and
archive.org is spread over the week. Every check that is skipped says why.

| Company | Backup checks | Requests (first morning) | Skipped, and why |
|---|---|---|---|
| ADP | careers page (refused today: re-read weekly); job list: jobs.adp.com sitemap (374 jobs); new student/program pages (sitemap or WordPress list) | 3 | WordPress pages: the site has no WordPress page list; archive.org: no saved copy of the careers page; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| AllTrails | careers page (refused today: re-read weekly) | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (no jobs); program pages: no sitemap or page list that answers; archive.org: no saved copy of the careers page; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Arista Networks | careers page (refused today: re-read weekly); archive.org copies (1), weekly | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Box | careers page (refused today: re-read weekly); job list: careers.box.com sitemap (250 jobs); new student/program pages (sitemap or WordPress list); archive.org copies (1), weekly | 3 | WordPress pages: the site has no WordPress page list; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Cadence Design Systems | careers page (refused today: re-read weekly); archive.org copies (2), weekly; hidden Workday sites (tenant robots.txt, cached by the check: no request) | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Censys | careers page (refused today: re-read weekly); archive.org copies (6), weekly | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (failed, no jobs); program pages: no sitemap or page list that answers; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Chime | careers page (refused today: re-read weekly) | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; archive.org: no saved copy of the careers page; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Ciena | careers page (refused today: re-read weekly); archive.org copies (7), weekly; hidden Workday sites (tenant robots.txt, cached by the check: no request) | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Cohesity | careers page (refused today: re-read weekly); hidden Workday sites (tenant robots.txt, cached by the check: no request) | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; archive.org: no saved copy of the careers page; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Cox Enterprises | careers page (refused today: re-read weekly); WordPress pages (69 on www.coxenterprises.com); job list: jobs.coxenterprises.com sitemap (785 jobs); new student/program pages (sitemap or WordPress list); archive.org copies (24), weekly; hidden Workday sites (tenant robots.txt, cached by the check: no request) | 4 | side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| d-Matrix | careers page (refused today: re-read weekly); archive.org copies (1), weekly | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (no jobs); program pages: no sitemap or page list that answers; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| DataRobot | careers page (refused today: re-read weekly); archive.org copies (4), weekly; hidden Workday sites (tenant robots.txt, cached by the check: no request) | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| DraftKings | careers page (refused today: re-read weekly); job list: careers.draftkings.com sitemap (76 jobs); new student/program pages (sitemap or WordPress list); archive.org copies (1), weekly; hidden Workday sites (tenant robots.txt, cached by the check: no request); side board: RippleMatch (6 roles) | 4 | WordPress pages: the site has no WordPress page list; Getro: no Getro board copies its careers page |
| Enova | careers page (refused today: re-read weekly); archive.org copies (1), weekly | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Fortinet | careers page (robots.txt blocks it: never read); archive.org copies (3), weekly | 0 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (robots); program pages: no sitemap or page list that answers; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Gusto | careers page (refused today: re-read weekly); archive.org copies (1), weekly | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Haize Labs | careers page (refused today: re-read weekly) | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; archive.org: no saved copy of the careers page; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Intuitive Surgical | careers page (refused today: re-read weekly); job list: careers.intuitive.com sitemap (3995 jobs); new student/program pages (sitemap or WordPress list); archive.org copies (1), weekly | 3 | WordPress pages: the site has no WordPress page list; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Lucid Software | careers page (refused today: re-read weekly); archive.org copies (2), weekly | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Marvell | careers page (refused today: re-read weekly); archive.org copies (5), weekly; hidden Workday sites (tenant robots.txt, cached by the check: no request) | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Match Group (Tinder, Hinge) | careers page (refused today: re-read weekly); WordPress pages (25 on mtch.com, 25 on www.mtch.com); new student/program pages (sitemap or WordPress list); archive.org copies (3), weekly | 3 | own job list: no job sitemap (failed, no jobs); hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| NetApp | careers page (refused today: re-read weekly); archive.org copies (1), weekly | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Persona | careers page (refused today: re-read weekly) | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (failed, refused); program pages: no sitemap or page list that answers; archive.org: no saved copy of the careers page; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Progressive | careers page (refused today: re-read weekly); new student/program pages (sitemap or WordPress list); side board: RippleMatch (1 roles) | 2 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (no jobs, refused); archive.org: no saved copy of the careers page; hidden Workday sites: no Workday tenant; Getro: no Getro board copies its careers page |
| Rubrik | careers page (refused today: re-read weekly) | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; archive.org: no saved copy of the careers page; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| SAS Institute | careers page (robots.txt blocks it: never read); archive.org copies (2), weekly | 0 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (failed, robots); program pages: no sitemap or page list that answers; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Udemy | careers page (refused today: re-read weekly) | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; archive.org: no saved copy of the careers page; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Verizon | careers page (refused today: re-read weekly); archive.org copies (4), weekly; hidden Workday sites (tenant robots.txt, cached by the check: no request); side board: RippleMatch (0 roles) | 2 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (no jobs); program pages: no sitemap or page list that answers; Getro: no Getro board copies its careers page |
| Wells Fargo | careers page (refused today: re-read weekly); job list: www.wellsfargojobs.com sitemap (4785 jobs); new student/program pages (sitemap or WordPress list); archive.org copies (3), weekly; hidden Workday sites (tenant robots.txt, cached by the check: no request) | 3 | WordPress pages: the site has no WordPress page list; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| YugabyteDB | careers page (refused today: re-read weekly); WordPress pages (93 on www.yugabyte.com); new student/program pages (sitemap or WordPress list); archive.org copies (2), weekly | 3 | own job list: no job sitemap (no jobs); hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| ZipRecruiter | careers page (robots.txt blocks it: never read) | 0 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (robots); program pages: no sitemap or page list that answers; archive.org: no saved copy of the careers page; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |
| Zocdoc | careers page (refused today: re-read weekly) | 1 | WordPress pages: the site has no WordPress page list; own job list: no job sitemap (refused); program pages: no sitemap or page list that answers; archive.org: no saved copy of the careers page; hidden Workday sites: no Workday tenant; side boards: none found (no campus board, RippleMatch page or second site); Getro: no Getro board copies its careers page |

### SimplifyJobs rows at go-live
At go-live, every stored Simplify row with no company that now matches an added company gets that company. Dry run
on a copy of the database with the planned names and links: **1,121 stored rows go to 134 companies**
(301 untracked, 820 from Simplify's first download, which stay as they are, like the 198's).
**225 of them are still open and get the same possible-miss checks as the 198's rows.** 162 of those
were already shown to you in an untracked list, so "Now watching" leaves their roles out and no row is ever emailed
again. Largest: Marvell 71, KLA 62, Keysight 56, Qorvo 50, Micron Technology 49, Hewlett Packard Enterprise 46, American Express 44, Qualcomm 43. Per company in the table below.

Today's open Simplify rows against the reads (`simplify_coverage.json`): 834 open rows at 111 companies, 807 found.
The other 27: 16 are open but unlisted postings that the one-by-one lookup finds (code change 4: American Express 7,
JPMorgan 4, TI 3, BNY 1, Rivian-VW 1); 9 are already closed at the company (Marvell 4, Micron 3, Rubrik 1, Western
Digital 1); 2 are NBCUniversal postings its Nov 9 read didn't have (rechecked if you add NBCUniversal). **Expected day-one
possible misses: 3** (Marvell "Data Science Intern", Rubrik "Software Engineering Intern", Western Digital
"Recording Electronics Data Analytics & Optimization Co-op"): the closed postings among the rows that start being
checked.

### Name matching on SimplifyJobs and the lists
Every added company matches by name and by link. Across the 6,912 stored rows and today's open ones, every row that an
added name catches by name alone is that company's own (its link goes to a system with no automatic address marker:
Qualcomm's Eightfold, Costco's Taleo, ICE's iCIMS and so on, which `match_urls` will cover). No outside company's row
would be pulled in, so there are no clashes to bring you. In the lists, three rows file another company's site under
an added name (decision 5). The explicit pairs (Box/Dropbox, Zip/ZipRecruiter, the two Lucids, HP Inc./HPE and the
rest) are proven row by row in each batch.

### Freshman and sophomore programs
18 of the companies run one (`underclassmen_research.md`): Morgan Stanley's Early Insights and sophomore summer
analyst programs, Citi's Early ID and Freshman Discovery, Wells Fargo's Sophomore Experience, BNY's Sophomore Summit
and Freshman Jumpstart, Walmart's Sophomore Summit, American Express's Discovery Program, The Hartford's Freshman
Experience and Early Immersion Program, USAA's Accelerate Program, Synchrony's sophomore externship, CVS's virtual
externship, Humana's Early ID, GlobalFoundries' sophomore internships, Lowe's exploratory software internship and
others. `internwatch test-filters` matches all of them today except four titles, which get per-company keywords
(code change 5). Bank of America's Early Insights event and Morgan Stanley's programs are on the campus sites of
decision 3. The other 222 companies have no program found; they go in UNDERCLASSMEN.md's list.

### Day-one alerts by kind
Expected over the batches' first mornings (each on the morning its company goes live), with the plan's code changes in
place:
| Alert | Expected | Why |
|---|---|---|
| `new job site?` | 3 | lists filing another company's site under an added name: Fox Factory's Workday site filed as "FOX", HP Inc.'s as "Hewlett Packard Enterprise", the Rivian-VW joint venture's board as "rivian" (decision 5) |
| `new job site?` | 0 to 3 | the subsidiary sites the lists link (Depop, CenterWell, Sarah Cannon), if you don't add them (decision 4) |
| `possible miss` | 3 | Simplify still lists these postings as open; they're closed at the company (Marvell "Data Science Intern", Rubrik "Software Engineering Intern", Western Digital "Recording Electronics Data Analytics & Optimization Co-op") |
| `new site`, `moved?`, backup checks | 0 | their first look is a silent baseline |
| error, timeout, shape | 0 | the read failures found here are fixed by code changes 1, 2 and 6 |
| `not checked` | 0 | the added round's time limit is set from these measurements |
| zero, drop, slow bleed, internships vanished, board alerts, `check gone dark` | 0 | they need several mornings of history |

### Database and test recordings
- **Database** (today 128.5 MB; the 198 add 1,000 to 1,900 job rows a weekday). A stored job with a description
  takes about 2.8 KB, one without (every store job) about 0.45 KB with its indexes.
  - Student slices for the very large sites: about +100 MB on day one (89,000 jobs), then about 2 MB a day.
  - Full reads: about +135 MB on day one (144,000 jobs, 163,000 with Costco's warehouse site), then about 3 MB a day
    (CVS adds 600 to 1,000 store postings a weekday, Walmart about 500, Lowe's about 250, Target about 60).
- **Test recordings** (today 197 recordings, 20 MB): about +17 MB at today's average size per hiring system, plus about
  5 MB for the very large sites' recordings with full reads.

### Requests Stage 1 made
About 16,000 requests over about 370 sites: one read of every board, the very large sites' full reads (about 4,500),
the careers pages, the 11 lists, the backup checks once, and one-off probes. robots.txt was checked first every time
and saved to `discovery/robots/`.

### Evidence files
`candidates.yaml` (the companies), `reads.yaml` and `reads_big.yaml` (each read), `read_results*.json` (jobs, student
roles, matches, seconds, requests per read), `pages.json`, `lists.json`, `list_check.json`, `page_systems_check.json`,
`workday_sites.json`, `workday_partitions.json`, `pagecounts.json`, `ghpages.json`, `new_systems_measure.json`,
`rmk_*.json`, `slice_compare.json`, `matched_dedup.json`, `simplify_coverage.json`, `rematch.json`,
`name_clashes.json`, `backup_probe.json`, `backup_measure.json`, `backup_table.md`, `ripplematch.json`,
`underclassmen_research.md`, `plan.json` (each company's proposed reads and batch), `companies_table.md` (below).

## Every company

Sorted by batch. Check times are for the recommended options (student reads for the five giant sites); their full-read times are in decision 1. "Count verified": "yes (N)" when the site itself states N; "site's own total" when the reader checks the read against the total the site reports; "render at batch time" for company pages that draw their list in the browser.

| Company | Batch | Hiring system and boards read | Careers page | Jobs (distinct) | Count verified | Student roles | Matching | Check time / requests each morning | Simplify rows at go-live (still open) | Day-one possible misses |
|---|---|---|---|---|---|---|---|---|---|---|
| Addepar | 1 | Greenhouse addepar1 | answers | 105 | yes (107) | 0 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| Allen Institute for AI (Ai2) | 1 | Greenhouse thealleninstitute | answers | 17 | yes (17) | 3 | 3 | 1 s / 1 | 3 (1 open) | 0 |
| Altruist | 1 | Greenhouse altruist | answers | 74 | render at batch time | 0 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| Amperity | 1 | Greenhouse amperity | answers | 14 | page shows all 15 | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Appian | 1 | Greenhouse appian | answers | 156 | yes (158) | 5 | 3 | 0 s / 1 | 2 (0 open) | 0 |
| Apptronik | 1 | Greenhouse apptronik | answers | 89 | render at batch time | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Arcesium | 1 | Greenhouse arcesiumllc | answers | 37 | yes (37) | 6 | 4 | 1 s / 1 | 2 (0 open) | 0 |
| Asana | 1 | Greenhouse asana | answers | 108 | render at batch time | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| BambooHR | 1 | Greenhouse bamboohr17 | answers | 28 | yes (28) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Bandwidth | 1 | Greenhouse bandwidth | answers | 26 | yes (26) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Betterment | 1 | Greenhouse betterment,bettermentcampusrecruiting | answers | 25 | render at batch time | 0 | 0 | 1 s / 2 | 1 (0 open) | 0 |
| BILL | 1 | Greenhouse billcom | answers | 40 | render at batch time | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Bot Auto | 1 | Greenhouse botauto | answers | 26 | yes (26) | 1 | 1 | 1 s / 1 | 2 (0 open) | 0 |
| Box | 1 | Greenhouse boxinc | refuses scripts | 139 | yes (142) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Braze | 1 | Greenhouse braze | answers | 343 | yes (355) | 1 | 1 | 2 s / 1 | 1 (0 open) | 0 |
| Bugcrowd | 1 | Greenhouse bugcrowd | answers | 13 | render at batch time | 0 | 0 | 2 s / 1 | 0 (0 open) | 0 |
| Censys | 1 | Greenhouse censys | refuses scripts | 27 | yes (28) | 0 | 0 | 2 s / 1 | 0 (0 open) | 0 |
| Checkr | 1 | Greenhouse checkr | answers | 38 | yes (38) | 0 | 0 | 2 s / 1 | 0 (0 open) | 0 |
| Chime | 1 | Greenhouse chime | refuses scripts | 67 | page refuses scripts | 0 | 0 | 2 s / 1 | 0 (0 open) | 0 |
| Clockwork Systems | 1 | Greenhouse clockworksystems | answers | 5 | yes (5) | 1 | 1 | 2 s / 1 | 1 (0 open) | 0 |
| Descript | 1 | Greenhouse descript | answers | 10 | page shows all 10 | 0 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| DigitalOcean | 1 | Greenhouse digitalocean98 | answers | 151 | render at batch time | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Domino Data Lab | 1 | Greenhouse dominodatalab | answers | 18 | render at batch time | 2 | 2 | 1 s / 1 | 2 (0 open) | 0 |
| DriveWealth | 1 | Greenhouse drivewealth; Ashby drivewealth | answers | 37 | render at batch time; yes (28) | 5 | 5 | 3 s / 2 | 6 (6 open) | 0 |
| EarnIn | 1 | Greenhouse earnin | answers | 29 | yes (31) | 0 | 0 | 2 s / 1 | 0 (0 open) | 0 |
| Enova | 1 | Greenhouse enova | refuses scripts | 39 | yes (39) | 4 | 2 | 2 s / 1 | 1 (0 open) | 0 |
| Fastly | 1 | Greenhouse fastly | answers | 55 | page shows all 55 | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Fervo Energy | 1 | Greenhouse fervoenergy | answers | 67 | yes (67) | 1 | 0 | 2 s / 1 | 0 (0 open) | 0 |
| Figure AI | 1 | Greenhouse figureai | answers | 102 | yes (103) | 12 | 10 | 2 s / 1 | 7 (0 open) | 0 |
| Garner Health | 1 | Greenhouse garnerhealth | answers | 60 | yes (62) | 1 | 1 | 3 s / 1 | 1 (0 open) | 0 |
| Gemini | 1 | Greenhouse gemini | answers | 27 | page shows all 27 | 4 | 4 | 3 s / 1 | 2 (1 open) | 0 |
| GoDaddy | 1 | Greenhouse godaddy,eventsandinterns | answers | 30 | page lists 1 of 30 (paged) | 1 | 1 | 4 s / 2 | 0 (0 open) | 0 |
| Gusto | 1 | Greenhouse gusto | refuses scripts | 80 | yes (80) | 0 | 0 | 2 s / 1 | 0 (0 open) | 0 |
| Haize Labs | 1 | Greenhouse haizelabs | refuses scripts | 6 | yes (6) | 2 | 2 | 3 s / 1 | 1 (0 open) | 0 |
| HeyGen | 1 | Greenhouse heygen | answers | 19 | yes (19) | 1 | 1 | 2 s / 1 | 1 (0 open) | 0 |
| Hyperproof | 1 | Greenhouse hyperproof | answers | 4 | render at batch time | 0 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| IXL Learning | 1 | Greenhouse ixllearning | answers | 115 | render at batch time | 1 | 1 | 3 s / 1 | 1 (0 open) | 0 |
| Khan Academy | 1 | Greenhouse khanacademy | answers | 3 | yes (3) | 0 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| KnowBe4 | 1 | Greenhouse knowbe4 | answers | 50 | yes (50) | 11 | 4 | 3 s / 1 | 1 (0 open) | 0 |
| LaunchDarkly | 1 | Greenhouse launchdarkly | answers | 43 | yes (43) | 0 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| Locus Robotics | 1 | Greenhouse locusrobotics | answers | 7 | yes (7) | 0 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| Lucid Motors | 1 | Greenhouse lucidmotors | answers | 443 | render at batch time | 1 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| Lucid Software | 1 | Greenhouse lucidsoftware | refuses scripts | 27 | yes (27) | 3 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| Nasuni | 1 | Greenhouse nasuni | answers | 29 | render at batch time | 0 | 0 | 2 s / 1 | 0 (0 open) | 0 |
| nCino | 1 | Greenhouse ncinoinc,ncinoearlytalent | answers | 30 | yes (30) | 0 | 0 | 6 s / 2 | 1 (0 open) | 0 |
| Neuralink | 1 | Greenhouse neuralink | answers | 80 | render at batch time | 19 | 18 | 3 s / 1 | 4 (0 open) | 0 |
| Nextdoor | 1 | Greenhouse nextdoor | answers | 20 | render at batch time | 0 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| Obsidian Security | 1 | Greenhouse obsidiansecurity | answers | 15 | yes (15) | 0 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| Pacific Fusion | 1 | Greenhouse pacificfusion | answers | 26 | yes (28) | 5 | 2 | 3 s / 1 | 1 (0 open) | 0 |
| Pendo | 1 | Greenhouse pendo | answers | 22 | yes (22) | 0 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| Perpay | 1 | Greenhouse perpay | answers | 17 | yes (17) | 5 | 3 | 4 s / 1 | 4 (0 open) | 0 |
| Precisely | 1 | Greenhouse preciselyusjobs,preciselyinternationaljobs | answers | 55 | render at batch time | 0 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| PrizePicks | 1 | Greenhouse prizepicks | answers | 31 | render at batch time | 4 | 3 | 3 s / 1 | 4 (2 open) | 0 |
| Pure Storage | 1 | Greenhouse purestorage | answers | 352 | yes (369) | 1 | 1 | 4 s / 1 | 1 (0 open) | 0 |
| Reddit | 1 | Greenhouse reddit | answers | 154 | yes (154) | 0 | 0 | 4 s / 1 | 0 (0 open) | 0 |
| Redwood Materials | 1 | Greenhouse redwoodmaterials | answers | 126 | render at batch time | 0 | 0 | 4 s / 1 | 0 (0 open) | 0 |
| Ridgeline | 1 | Greenhouse ridgeline | answers | 29 | render at batch time | 0 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| Ripple | 1 | Greenhouse ripple | answers | 116 | page lists 78 of 117 (paged) | 0 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| Roku | 1 | Greenhouse roku | answers | 88 | render at batch time | 6 | 1 | 4 s / 1 | 5 (5 open) | 0 |
| Rubrik | 1 | Greenhouse rubrik | refuses scripts | 145 | page refuses scripts | 5 | 0 | 4 s / 1 | 2 (2 open) | 1 |
| SingleStore | 1 | Greenhouse singlestore | answers | 40 | yes (40) | 2 | 2 | 4 s / 1 | 4 (0 open) | 0 |
| Snorkel AI | 1 | Greenhouse snorkelai | answers | 43 | yes (43) | 0 | 0 | 4 s / 1 | 1 (0 open) | 0 |
| SoFi | 1 | Greenhouse sofi | answers | 48 | page shows all 48 | 1 | 0 | 4 s / 1 | 0 (0 open) | 0 |
| Starburst | 1 | Greenhouse starburst | answers | 38 | yes (38) | 0 | 0 | 4 s / 1 | 0 (0 open) | 0 |
| The New York Times | 1 | Greenhouse thenewyorktimes | answers | 172 | yes (173) | 28 | 17 | 3 s / 1 | 10 (7 open) | 0 |
| Truveta | 1 | Greenhouse truveta | answers | 34 | yes (34) | 0 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| Typeface | 1 | Greenhouse typeface | answers | 18 | yes (18) | 0 | 0 | 4 s / 1 | 0 (0 open) | 0 |
| Udemy | 1 | Greenhouse udemy,udemybedi | refuses scripts | 3 | page shows all 4 | 0 | 0 | 8 s / 2 | 0 (0 open) | 0 |
| Veeam Software | 1 | Greenhouse veeamsoftware | answers | 197 | yes (198) | 17 | 12 | 4 s / 1 | 8 (0 open) | 0 |
| Vercel | 1 | Greenhouse vercel | answers | 87 | yes (87) | 1 | 1 | 4 s / 1 | 2 (0 open) | 0 |
| Viam | 1 | Greenhouse viamrobotics | answers | 8 | yes (8) | 1 | 1 | 5 s / 1 | 1 (0 open) | 0 |
| You.com | 1 | Greenhouse youcom | answers | 8 | yes (8) | 0 | 0 | 5 s / 1 | 0 (0 open) | 0 |
| YugabyteDB | 1 | Greenhouse yugabyte | refuses scripts | 14 | yes (14) | 0 | 0 | 5 s / 1 | 0 (0 open) | 0 |
| ZipRecruiter | 1 | Greenhouse ziprecruiter | robots.txt disallows | 68 | yes (68) | 1 | 1 | 4 s / 1 | 1 (0 open) | 0 |
| Zocdoc | 1 | Greenhouse zocdoc | refuses scripts | 63 | yes (63) | 0 | 0 | 5 s / 1 | 0 (0 open) | 0 |
| ZoomInfo | 1 | Greenhouse zoominfo | answers | 90 | page shows all 91 | 0 | 0 | 5 s / 1 | 0 (0 open) | 0 |
| Zscaler | 1 | Greenhouse zscaler | answers | 344 | yes (377) | 0 | 0 | 5 s / 1 | 0 (0 open) | 0 |
| AllTrails | 2 | Lever /alltrails | refuses scripts | 1 | yes (1) | 0 | 0 | 11 s / 1 | 0 (0 open) | 0 |
| Anchorage Digital | 2 | Lever /anchorage | answers | 23 | yes (23) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Base Power | 2 | Ashby base-power | answers | 196 | yes (197) | 27 | 14 | 0 s / 1 | 7 (0 open) | 0 |
| Baseten | 2 | Ashby baseten | answers | 100 | yes (101) | 1 | 1 | 1 s / 1 | 0 (0 open) | 0 |
| Bedrock Robotics | 2 | Ashby bedrock-robotics | answers | 57 | yes (57) | 13 | 13 | 1 s / 1 | 12 (0 open) | 0 |
| Bumble | 2 | Lever /bumbleinc | answers | 0 | ? | 0 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| Carbon Robotics | 2 | Ashby carbon-robotics | answers | 4 | yes (4) | 0 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| Cartesia | 2 | Ashby cartesia | answers | 24 | yes (24) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Cerebras | 2 | Ashby cerebras | answers | 121 | yes (121) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Clay | 2 | Ashby claylabs | answers | 62 | yes (62) | 1 | 1 | 1 s / 1 | 1 (0 open) | 0 |
| Collaborative Robotics (Cobot) | 2 | Ashby cobot | failed | 14 | yes (14) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Commonwealth Fusion Systems | 2 | Lever /cfsenergy | answers | 139 | yes (140) | 18 | 18 | 1 s / 1 | 4 (1 open) | 0 |
| Commure | 2 | Ashby commure,commure-athelas | answers | 74 | ? | 4 | 0 | 4 s / 2 | 0 (0 open) | 0 |
| ConductorOne | 2 | Ashby c1 | answers | 17 | yes (17) | 0 | 0 | 2 s / 1 | 0 (0 open) | 0 |
| Crusoe | 2 | Ashby crusoe | answers | 322 | yes (324) | 0 | 0 | 3 s / 1 | 1 (0 open) | 0 |
| d-Matrix | 2 | Ashby d-Matrix | refuses scripts | 36 | yes (37) | 0 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| Delinea | 2 | Ashby delinea | answers | 64 | yes (68) | 0 | 0 | 3 s / 1 | 0 (0 open) | 0 |
| Dusty Robotics | 2 | Rippling dusty-robotics-inc | answers | 2 | site's own total | 0 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| Ellipsis Labs | 2 | Ashby ellipsislabs | answers | 14 | yes (14) | 1 | 1 | 1 s / 1 | 1 (0 open) | 0 |
| Etched | 2 | Ashby Etched | answers | 115 | yes (115) | 13 | 12 | 1 s / 1 | 7 (1 open) | 0 |
| Eventual (Daft) | 2 | Ashby eventualcomputing | answers | 5 | yes (5) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Exa | 2 | Ashby exa | answers | 66 | yes (66) | 1 | 1 | 2 s / 1 | 1 (0 open) | 0 |
| Gen Digital | 2 | Ashby gen-digital | answers | 97 | yes (98) | 4 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| Genesis Molecular AI | 2 | Ashby genesis-molecular-ai | answers | 10 | yes (10) | 1 | 1 | 1 s / 1 | 1 (1 open) | 0 |
| Gimlet Labs | 2 | Ashby gimlet | answers | 17 | yes (17) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| GlossGenius | 2 | Ashby geniusai | answers | 17 | yes (17) | 2 | 2 | 1 s / 1 | 2 (2 open) | 0 |
| Grow Therapy | 2 | Ashby grow-therapy | answers | 30 | yes (32) | 1 | 1 | 1 s / 1 | 1 (0 open) | 0 |
| Handshake | 2 | Ashby handshake | answers | 76 | yes (77) | 0 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| Hex Technologies | 2 | Ashby hex | answers | 37 | yes (37) | 2 | 2 | 1 s / 1 | 2 (0 open) | 0 |
| Illumio | 2 | Ashby illumio | answers | 61 | yes (67) | 3 | 3 | 0 s / 1 | 0 (0 open) | 0 |
| Ironclad | 2 | Ashby ironcladhq | answers | 22 | yes (22) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Lambda | 2 | Ashby lambda | answers | 97 | yes (97) | 1 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| Lightspark | 2 | Ashby lightspark | answers | 8 | yes (8) | 0 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| Match Group (Tinder, Hinge) | 2 | Lever /matchgroup | refuses scripts | 71 | yes (71) | 14 | 8 | 1 s / 1 | 5 (5 open) | 0 |
| Mercor | 2 | Ashby mercor | answers | 86 | yes (86) | 5 | 5 | 0 s / 1 | 5 (0 open) | 0 |
| Multiply Labs | 2 | Lever /multiplylabs | answers | 14 | yes (14) | 3 | 2 | 1 s / 1 | 2 (0 open) | 0 |
| Netic | 2 | Ashby netic | answers | 36 | yes (36) | 3 | 3 | 0 s / 1 | 3 (0 open) | 0 |
| Niantic Spatial | 2 | Ashby niantic-spatial | answers | 19 | yes (19) | 0 | 0 | 0 s / 1 | 1 (0 open) | 0 |
| Numeric | 2 | Ashby numeric | answers | 24 | yes (24) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| ONE Finance | 2 | Ashby oneapp | answers | 38 | yes (38) | 4 | 1 | 1 s / 1 | 2 (0 open) | 0 |
| Patreon | 2 | Ashby patreon | answers | 21 | yes (21) | 3 | 3 | 1 s / 1 | 3 (0 open) | 0 |
| Persona | 2 | Ashby persona | refuses scripts | 14 | yes (14) | 0 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| Persona AI | 2 | Ashby persona.ai | failed | 23 | yes (23) | 1 | 1 | 1 s / 1 | 4 (0 open) | 0 |
| Progressive | 2 | RippleMatch | refuses scripts | 1 | site's own total | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Qumulo | 2 | Ashby qumulo | answers | 25 | yes (25) | 1 | 1 | 0 s / 1 | 1 (0 open) | 0 |
| Replit | 2 | Ashby replit | answers | 29 | yes (29) | 1 | 1 | 0 s / 1 | 1 (0 open) | 0 |
| Rhoda AI | 2 | Ashby rhoda-ai | answers | 45 | yes (45) | 3 | 3 | 1 s / 1 | 3 (1 open) | 0 |
| Rilla | 2 | Ashby rilla | answers | 24 | yes (24) | 3 | 3 | 1 s / 1 | 1 (0 open) | 0 |
| Rivian and VW Group Technologies (JV) | 2 | Ashby rivianvw.tech | answers | 174 | yes (176) | 21 | 20 | 1 s / 1 | 3 (1 open) | 0 |
| Sentry | 2 | Ashby sentry | answers | 39 | yes (41) | 1 | 1 | 1 s / 1 | 0 (0 open) | 0 |
| Serval | 2 | Ashby serval | answers | 67 | yes (67) | 1 | 1 | 1 s / 1 | 1 (0 open) | 0 |
| Socure | 2 | Ashby socure | answers | 89 | yes (89) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Suno | 2 | Ashby suno | answers | 68 | yes (68) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Superhuman (formerly Grammarly) | 2 | Ashby Superhuman Platform Inc | answers | 73 | yes (73) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Tamr | 2 | Ashby tamr | answers | 0 | ? | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| TensorWave | 2 | Ashby tensorwave | answers | 39 | yes (39) | 0 | 0 | 2 s / 1 | 1 (0 open) | 0 |
| UiPath | 2 | Ashby uipath | answers | 101 | yes (102) | 2 | 2 | 1 s / 1 | 0 (0 open) | 0 |
| Unify | 2 | Ashby unify | answers | 11 | yes (11) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Xcimer Energy | 2 | Lever /xcimer | failed | 63 | yes (63) | 7 | 6 | 1 s / 1 | 1 (0 open) | 0 |
| Zip | 2 | Ashby zip | answers | 96 | yes (96) | 0 | 0 | 1 s / 1 | 0 (0 open) | 0 |
| Allstate | 3 | Workday allstate: allstate_careers, sourcing_event | answers | 413 | yes (430) | 11 | 7 | 24 s / 23 | 5 (4 open) | 0 |
| Analog Devices | 3 | Workday analogdevices/External | answers | 719 | yes (800) | 67 | 25 | 41 s / 40 | 21 (1 open) | 0 |
| AT&T | 3 | Workday att: ATTGeneral, ATTcollege, Cricket, ATTCollegeSpecialInvite | answers | 1,008 | yes (1105) | 6 | 2 | 66 s / 58 | 0 (0 open) | 0 |
| BlackRock | 3 | Workday blackrock: BlackRock_Professional, BlackRock_Early_Careers_Program | answers | 272 | yes (280) | 14 | 11 | 15 s / 15 | 7 (0 open) | 0 |
| Cadence Design Systems | 3 | Workday cadence: External_Careers, Univ_Careers, University_Talent, University_Talent_Intern, University_Talent_NCG, University_CST, OpenEye_Careers; Workday cadence/women-in-tech-scholarship | refuses scripts | 522 | yes (740); yes (1) | 27 | 13 | 46 s / 43 | 12 (0 open) | 0 |
| Chewy | 3 | Workday chewy/External | answers | 225 | yes (232) | 0 | 0 | 12 s / 12 | 0 (0 open) | 0 |
| Ciena | 3 | Workday ciena/Careers | refuses scripts | 161 | yes (164) | 17 | 6 | 9 s / 9 | 20 (8 open) | 0 |
| Circle | 3 | Workday circle/Circle; Ashby circle | answers | 67 | yes (61); yes (6) | 0 | 0 | 5 s / 5 | 0 (0 open) | 0 |
| Cohesity | 3 | Workday cohesity/Cohesity_Careers | refuses scripts | 182 | yes (185) | 6 | 3 | 10 s / 10 | 1 (1 open) | 0 |
| Comcast | 3 | Workday comcast/Comcast_Careers | answers | 654 | yes (696) | 2 | 0 | 35 s / 35 | 4 (0 open) | 0 |
| Copart | 3 | Workday copart/Copart | answers | 368 | yes (414) | 11 | 11 | 21 s / 21 | 10 (2 open) | 0 |
| CoStar Group | 3 | Workday costar: CoStarCareers, Costar_Campus, confidential | answers | 352 | yes (367) | 1 | 0 | 23 s / 21 | 7 (0 open) | 0 |
| Cox Enterprises | 3 | Workday cox/Cox_External_Career_Site_1 | refuses scripts | 725 | yes (789) | 16 | 16 | 42 s / 40 | 1 (0 open) | 0 |
| DataRobot | 3 | Workday datarobot/DataRobot_External_Careers | refuses scripts | 13 | yes (13) | 3 | 3 | 1 s / 1 | 3 (1 open) | 0 |
| Dexcom | 3 | Workday dexcom/Dexcom | answers | 281 | yes (294) | 2 | 1 | 15 s / 15 | 0 (0 open) | 0 |
| DraftKings | 3 | Workday draftkings: draftkings, Campus_Career_Portal, Employee_Referral_Portal | refuses scripts | 96 | yes (175) | 11 | 8 | 10 s / 10 | 8 (0 open) | 0 |
| Elevance Health | 3 | Workday elevancehealth: ANT, ELV-ET; Workday elevancehealth/carelonglobal_ph | answers | 289 | yes (282); yes (19) | 9 | 3 | 20 s / 17 | 4 (0 open) | 0 |
| Equinix | 3 | Workday equinix/External | answers | 305 | yes (308) | 0 | 0 | 26 s / 16 | 0 (0 open) | 0 |
| Etsy | 3 | Workday etsy/Etsy_Careers | answers | 68 | yes (68) | 0 | 0 | 4 s / 4 | 0 (0 open) | 0 |
| F5 | 3 | Workday ffive/f5jobs | answers | 270 | yes (282) | 2 | 2 | 15 s / 15 | 2 (0 open) | 0 |
| FIS | 3 | Workday fis/SearchJobs | answers | 463 | yes (507) | 1 | 1 | 27 s / 26 | 0 (0 open) | 0 |
| Fiserv | 3 | Workday fiserv/EXT | answers | 370 | yes (386) | 3 | 0 | 20 s / 20 | 0 (0 open) | 0 |
| FOX Corporation | 3 | Workday fox/Domestic; Workday fox/FOXTVST_EAST | answers | 318 | yes (325); yes (26) | 62 | 50 | 35 s / 19 | 1 (0 open) | 0 |
| Freddie Mac | 3 | Workday freddiemac/External | answers | 66 | yes (71) | 2 | 2 | 4 s / 4 | 1 (0 open) | 0 |
| GlobalFoundries | 3 | Workday globalfoundries/External | answers | 781 | yes (851) | 105 | 68 | 54 s / 43 | 24 (12 open) | 0 |
| Guidewire | 3 | Workday guidewire/external | answers | 114 | yes (117) | 1 | 0 | 6 s / 6 | 0 (0 open) | 0 |
| Humana | 3 | Workday humana/Humana_External_Career_Site | answers | 304 | yes (312) | 5 | 1 | 17 s / 16 | 1 (0 open) | 0 |
| KLA | 3 | Workday kla: Search, UR, annarbor; Workday kla/Israel | answers | 974 | yes (1383); site's own total | 54 | 40 | 81 s / 76 | 62 (16 open) | 0 |
| Marvell | 3 | Workday marvell: MarvellCareers, MarvellCareers2 | refuses scripts | 349 | yes (387) | 97 | 38 | 29 s / 21 | 71 (9 open) | 1 |
| Mastercard | 3 | Workday mastercard: CorporateCareers, Campus, Public_Posting_Site; Workday mastercard/CampusApplyOnly | answers | 814 | yes (964); site's own total | 15 | 1 | 56 s / 52 | 2 (0 open) | 0 |
| McKesson | 3 | Workday mckesson: External_Careers, sourcer_on_req; Workday mckesson/CoverMyMeds_External_Careers | answers | 656 | yes (699); site's own total | 17 | 2 | 38 s / 37 | 7 (0 open) | 0 |
| Morgan Stanley | 3 | Workday ms: External, private; oleeo (new reader) | answers | 1,355 | yes (1598); site's own list | 78 | 36 | 116 s / 84 | 0 (0 open) | 0 |
| Nasdaq | 3 | Workday nasdaq/Global_External_Site | answers | 150 | yes (153) | 3 | 1 | 8 s / 8 | 1 (0 open) | 0 |
| Nationwide | 3 | Workday nationwide/Nationwide_Career | answers | 136 | yes (151) | 5 | 4 | 8 s / 8 | 3 (0 open) | 0 |
| Nike | 3 | Workday nike: nke, nke2 | answers | 1,173 | yes (1222) | 18 | 11 | 62 s / 62 | 3 (0 open) | 0 |
| Nordstrom | 3 | Workday nordstrom/nordstrom_careers | answers | 1,304 | yes (1312) | 15 | 3 | 66 s / 66 | 0 (0 open) | 0 |
| Northwestern Mutual | 3 | Workday northwesternmutual/corporate-careers; SmartRecruiters | answers | 136 | yes (80); site's own total | 9 | 8 | 11 s / 12 | 2 (0 open) | 0 |
| Proofpoint | 3 | Workday proofpoint/ProofpointCareers | answers | 115 | yes (131) | 0 | 0 | 7 s / 7 | 0 (0 open) | 0 |
| PTC | 3 | Workday ptc/PTC | answers | 162 | yes (165) | 9 | 6 | 9 s / 9 | 3 (2 open) | 0 |
| Q2 | 3 | Workday q2ebanking/Q2 | answers | 61 | yes (64) | 10 | 7 | 4 s / 4 | 7 (0 open) | 0 |
| SailPoint | 3 | Workday sailpoint/SailPoint | answers | 92 | yes (94) | 1 | 0 | 5 s / 5 | 1 (0 open) | 0 |
| Snap | 3 | Workday snapchat/snap | answers | 210 | yes (215) | 4 | 1 | 11 s / 11 | 1 (0 open) | 0 |
| Snyk | 3 | Workday snyk/External; Ashby snyk | answers | 45 | yes (11); yes (37) | 0 | 0 | 2 s / 2 | 0 (0 open) | 0 |
| Sonos | 3 | Workday sonos/Sonos; Workday sonos/Student_Opportunities | answers | 52 | yes (54); site's own total | 4 | 2 | 3 s / 4 | 8 (1 open) | 0 |
| Southwest Airlines | 3 | Workday swa/external | answers | 30 | yes (30) | 0 | 0 | 2 s / 2 | 0 (0 open) | 0 |
| Synchrony | 3 | Workday synchronyfinancial/University; Workday synchronyfinancial/careers | failed | 46 | yes (22); site's own total | 16 | 12 | 5 s / 4 | 2 (1 open) | 0 |
| The Hartford | 3 | Workday thehartford: Careers_External, careers_restricted | answers | 215 | yes (252) | 19 | 9 | 14 s / 14 | 3 (0 open) | 0 |
| The Home Depot | 3 | Workday homedepot: CareerDepot, CareerDepotCanada | answers | 1,324 | yes (1402) | 0 | 0 | 74 s / 71 | 4 (0 open) | 0 |
| The Walt Disney Company | 3 | Workday disney: disneycareer, disneycareerdc | answers | 209 | yes (266) | 44 | 13 | 14 s / 14 | 3 (0 open) | 0 |
| The Washington Post | 3 | Workday washpost/washingtonpostcareers | answers | 52 | yes (52) | 0 | 0 | 12 s / 3 | 0 (0 open) | 0 |
| Travelers | 3 | Workday travelers/External | answers | 391 | yes (409) | 65 | 46 | 21 s / 21 | 5 (0 open) | 0 |
| Tricentis | 3 | Workday tricentis/Tricentis_Careers | answers | 24 | yes (24) | 0 | 0 | 2 s / 2 | 0 (0 open) | 0 |
| Trimble | 3 | Workday trimble/TrimbleCareers | answers | 178 | yes (184) | 19 | 16 | 10 s / 10 | 10 (5 open) | 0 |
| USAA | 3 | Workday usaa/USAAJOBSWD | answers | 215 | yes (215) | 0 | 0 | 11 s / 11 | 1 (0 open) | 0 |
| Vanguard | 3 | Workday vanguard: vanguard_external, contractors_restricted | answers | 327 | yes (351) | 21 | 18 | 19 s / 19 | 8 (0 open) | 0 |
| Verizon | 3 | Workday verizon/verizon-careers | refuses scripts | 983 | yes (1254) | 1 | 0 | 63 s / 63 | 4 (0 open) | 0 |
| Warner Bros. Discovery | 3 | Workday warnerbros/global | answers | 201 | yes (205) | 12 | 5 | 12 s / 11 | 0 (0 open) | 0 |
| Wells Fargo | 3 | Workday wf/WellsFargoJobs | refuses scripts | 1,549 | yes (1601) | 15 | 10 | 85 s / 81 | 2 (2 open) | 0 |
| Zebra Technologies | 3 | Workday zebra/Zebra_careers | answers | 219 | yes (230) | 22 | 4 | 12 s / 12 | 15 (1 open) | 0 |
| Zillow | 3 | Workday zillow/Zillow_Group_External | answers | 198 | yes (206) | 5 | 4 | 11 s / 11 | 3 (3 open) | 0 |
| Applied Materials | 4 | Workday amat/External | answers | 1,771 | yes (2193) | 77 | 36 | 225 s / 213 | 18 (9 open) | 0 |
| Bank of America | 4 | Workday ghr: us-emplsv, lateral-emea; oleeo (new reader) | answers | 2,858 | site's own total; site's own list | 17 | 7 | 409 s / 370 | 0 (0 open) | 0 |
| Citi | 4 | Workday citi: 2, Citi_Early_Careers_Events_Site | answers | 3,841 | site's own total | 114 | 17 | 256 s / 244 | 7 (7 open) | 0 |
| CVS Health | 4 | Workday cvshealth: CVS_Health_Careers, Private_Postings_Intern_Conversion_ONLY | answers | 13,503 | site's own total | 2882 | 17 | 5 s / 3 | 11 (8 open) | 0 |
| Dick's Sporting Goods | 4 | Workday dickssportinggoods/DSG | answers | 3,605 | yes (3648) | 5 | 5 | 218 s / 208 | 3 (0 open) | 0 |
| GE Vernova | 4 | Workday gevernova: Vernova_ExternalSite, only_confidential_executive_recruiting | answers | 2,241 | yes (4530) | 83 | 62 | 117 s / 111 | 26 (0 open) | 0 |
| Hewlett Packard Enterprise | 4 | Workday hpe: jobsathpe, acjobsite | answers | 1,743 | yes (3467) | 158 | 62 | 190 s / 175 | 46 (2 open) | 0 |
| HP Inc. | 4 | Workday hp: ExternalCareerSite, EXTEU-AC-CareerSite; Greenhouse hp,hpiq | answers | 1,193 | yes (2130); yes (59) | 117 | 33 | 118 s / 110 | 37 (17 open) | 0 |
| Lowe's | 4 | Workday lowes/LWS_External_CS | answers | 12,386 | site's own total | 38 | 18 | 22 s / 11 | 6 (1 open) | 0 |
| Micron Technology | 4 | Workday micron/External | answers | 2,555 | site's own total | 143 | 89 | 212 s / 202 | 49 (2 open) | 0 |
| Target | 4 | Workday target/targetcareers | answers | 14,088 | site's own total | 121 | 26 | 11 s / 6 | 0 (0 open) | 0 |
| Walmart (Walmart Global Tech) | 4 | Workday walmart/WalmartExternal; Workday walmart/Non-WorkdayInternal | answers | 17,883 | site's own total | 724 | 27 | 256 s / 246 | 6 (1 open) | 0 |
| American Express | 5 | Oracle /CX_1 | answers | 299 | site's own total | 10 | 2 | 5 s / 2 | 44 (2 open) | 0 |
| Arista Networks | 5 | SmartRecruiters AristaNetworks | refuses scripts | 98 | site's own total | 4 | 3 | 1 s / 2 | 1 (0 open) | 0 |
| athenahealth | 5 | Phenom careers.athenahealth.com | answers | 68 | site's own total | 0 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| BNY | 5 | Oracle /CX_1001 | answers | 1,007 | site's own total | 76 | 31 | 27 s / 7 | 15 (0 open) | 0 |
| Charles Schwab | 5 | Radancy | answers | 278 | site's own total | 2 | 1 | 8 s / 9 | 1 (0 open) | 0 |
| Costco | 5 | iCIMS Jibe careers.costco.com; taleo_tbe (new reader) | answers | 18,738 | site's own total; site's own list | 25 | 22 | 31 s / 7 | 8 (8 open) | 0 |
| Ford Motor Company | 5 | Oracle /CX_1 | answers | 857 | site's own total | 3 | 0 | 24 s / 5 | 0 (0 open) | 0 |
| Fortinet | 5 | Oracle /CX_2001 | robots.txt disallows | 903 | site's own total | 9 | 1 | 12 s / 6 | 1 (0 open) | 0 |
| Hilton | 5 | Oracle /CX_1 | answers | 4,122 | site's own total | 33 | 2 | 59 s / 22 | 1 (0 open) | 0 |
| Intercontinental Exchange (NYSE) | 5 | iCIMS Jibe ice.jibeapply.com | answers | 281 | yes (327) | 44 | 38 | 15 s / 4 | 33 (16 open) | 0 |
| Intuitive Surgical | 5 | SmartRecruiters Intuitive | refuses scripts | 791 | yes (846) | 13 | 8 | 153 s / 81 | 6 (2 open) | 0 |
| JPMorgan Chase | 5 | Oracle /CX_1001 | answers | 6,789 | site's own total | 68 | 22 | 89 s / 36 | 22 (3 open) | 0 |
| Keysight | 5 | iCIMS Jibe jobs.keysight.com | answers | 682 | yes (769) | 114 | 76 | 35 s / 8 | 56 (6 open) | 0 |
| Macy's | 5 | Oracle /CX_1 | answers | 6,228 | site's own total | 103 | 13 | 75 s / 35 | 4 (1 open) | 0 |
| Navy Federal Credit Union | 5 | Oracle /nfcu | answers | 148 | site's own total | 68 | 56 | 2 s / 1 | 33 (2 open) | 0 |
| Principal Financial Group | 5 | iCIMS Jibe careers.principal.com | answers | 142 | yes (151) | 15 | 2 | 5 s / 2 | 1 (0 open) | 0 |
| Qualcomm | 5 | Eightfold careers.qualcomm.com | answers | 1,898 | yes (2017) | 115 | 18 | 235 s / 203 | 43 (22 open) | 0 |
| Rivian | 5 | iCIMS Jibe careers.rivian.com | answers | 948 | yes (964) | 46 | 41 | 45 s / 10 | 20 (2 open) | 0 |
| SAS Institute | 5 | iCIMS | robots.txt disallows | 35 | site's own total | 3 | 3 | 1 s / 2 | 0 (0 open) | 0 |
| State Farm | 5 | iCIMS Jibe jobs.statefarm.com | answers | 222 | yes (238) | 11 | 9 | 10 s / 3 | 4 (0 open) | 0 |
| Symmetry Systems | - | folded into Zscaler (acquired; its site redirects to zscaler.com) | - | - | - | - | - | - | 0 | - |
| Texas Instruments | 5 | Oracle /CX; Oracle /CX_1 | answers | 958 | site's own total | 132 | 53 | 13 s / 6 | 33 (6 open) | 0 |
| Tyler Technologies | 5 | Jobvite | answers | 136 | site's own total | 11 | 11 | 16 s / 1 | 7 (1 open) | 0 |
| United Airlines | 5 | Phenom careers.united.com | answers | 120 | yes (124) | 0 | 0 | 0 s / 1 | 0 (0 open) | 0 |
| UnitedHealth Group (Optum) | 5 | Radancy | answers | 5,965 | site's own total | 106 | 83 | 40 s / 41 | 0 (0 open) | 0 |
| Western Digital | 5 | SmartRecruiters WesternDigital | answers | 263 | yes (336) | 20 | 4 | 87 s / 30 | 5 (2 open) | 1 |
| ADP | 6 | sitemap (titles only) (new reader) | refuses scripts | 421 | site's own list | 8 | 5 | 2 s / 1 | 0 (0 open) | 0 |
| Best Buy | 6 | Workday bestbuycanada/BestBuyCA_Career; servicenow (sitemap + new job pages) (new reader) | answers | 64 | yes (64); site's own list | 0 | 0 | 184 s / 135 | 0 (0 open) | 0 |
| NetApp | 6 | successfactors (new reader) | refuses scripts | 305 | site's own list | 13 | 5 | 15 s / 13 | 0 (0 open) | 0 |
| Paramount | 6 | successfactors (new reader) | answers | 190 | site's own list | 2 | 0 | 10 s / 9 | 0 (0 open) | 0 |
| Qorvo | 6 | successfactors (new reader) | answers | 8 | site's own list | 6 | 6 | 0 s / 1 | 50 (0 open) | 0 |
| Sandisk | 6 | sitemap (Avature) (new reader) | answers | 412 | site's own list | 17 | 14 | 4 s / 3 | 0 (0 open) | 0 |

