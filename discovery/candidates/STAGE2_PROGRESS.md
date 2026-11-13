# Stage 2 progress

Branch `stage2-batch0`, worktree `../internship-notifier-batch0`. The morning run is started by hand from the main
working tree, so nothing here reaches it until the batch is proven and merged into main. Run tests here with
`PYTHONPATH=$PWD/src ../internship-notifier/.venv/bin/python -m pytest -q` (the main venv's editable install points
at the main tree's src; PYTHONPATH puts this worktree's src first).

Decisions (2026-11-09, STAGE1_REPORT.md): giant store sites read for student roles daily + a weekly full read; 12
workers in the added round; every new reader built; the subsidiaries added (Tubi pending); no "known site" setting;
Progressive through RippleMatch; DraftKings, FOX, Match Group, PrizePicks taken out (236 companies); Tubi
(FOX's) stays out (2026-11-10).

## Batch 0: groundwork, no companies (proof: everything identical)
Design: each round runs today's code over a view of the config that holds only its companies (and only their entries
in the per-company settings lists), so the 198's phases see exactly today's config. The added round runs after them
with `schedule.rounds.added` (workers, run_timeout_minutes, retry_delay, page/blocked/watch budgets). Alerts are
recorded round by round (198 problems, 198 misses, then the added round's), emails after both rounds.

- [x] 1. build_config.py back in step with companies.yaml, and a test that regenerates it in memory identically
- [x] 2. Config: `round` on companies, `Config.scoped(round)`, `schedule.rounds.added`
- [x] 3. Runner: the round loop, per-round summaries and alert recording, emails after both rounds
- [x] 4. Cross-check: the added round adopts untracked rows of its companies (go-live re-match), resolves its
        companies' rows; adopted rows never go "via Simplify"; digest_at set when a morning email lists an
        untracked row (and backfilled once from data/outbox)
- [x] 5. "Now watching": retried like every email; leaves out roles already shown in an untracked list
- [x] 6. moves.py / watch.py / liveness.py scoped by round (settings lists filtered by company); the list scan's
        downloads reused by the added round (no new requests)
- [x] 7. Opt-in settings (off for the 198): Workday skip postings without a link; Workday pack locations;
        anchored address markers for short tenants; SmartRecruiters search total; (Ashby learn_ids if needed)
- [x] 8. tools/prove: golden.py PASS against main (394 cassette runs, 85,183 filter verdicts, 39,614 matched rows,
        36 Workday robots files identical); a live morning recorded (data/stage2/morning-2026-11-09: 3,067 exchanges,
        198 checked, 0 failed) and runall.sh PASS for mornings 1, 2 (a day later: new roles at stripe, databricks,
        openai; figma failing; every email failing) and 3 (after the failed emails); smoke replay with stripe, figma,
        klaviyo as added: the added round ran last (its requests the last 4 of 2,779), no error
- [x] 9. Test fixes: klaviyo's quiet-board test pinned to its recording date; the 8 drifted cassettes re-recorded
        (test_fixture_was_recorded_with_the_current_settings); Bloomberg's tests now use the real shuffled walk the
        new recording caught (310 of 330 jobs newest-first, all 330 by title)
- [x] 10. Docs (README); proofs PASS; merged into main and pushed. Next: a real morning run before batch 1

## How to prove a batch
- Static: `.venv/bin/python -I tools/prove/golden.py main` from the worktree (old = main, new = this tree): PASS
  means identical cassettes, filter verdicts, matching and Workday sites, apart from what goes to added companies.
- Mornings: record once with the new code (`morning.py record data/stage2/morning-<date>`, a live daily run on a
  database copy, no email, no heartbeat), then replay it through `git archive main` (old) and this tree (new):
  morning 1 as recorded; morning 2 `after:<morning 1 out>,day:1,new:<keys>,fail:<key>`; morning 3
  `after:<morning 2 out>,day:2,mailfail`; then `morning.py compare <old out> <new out> <added keys>` for each.

## Batch 1: the 76 Greenhouse companies (branch stage2-batch1)
Batch 0's morning (2026-11-10, run 24): 28.7 min, 199 checks, 2,952 requests, morning email at 28.6 min; partial only
because Capital One's Workday listed 4 postings without a link (the unchanged code path, as before batch 0) and
CoreWeave's weights_and_biases Greenhouse board now answers 404. No added round (none yet); 104 untracked rows marked
as shown; 6 of 11 lists kept.
- [x] discovery/stage2_batch.py (render, apply): seed entries with round: added, results, aliases, settings
- [x] page counts: hosted boards, company pages, headless renders with every request checked against robots.txt
      (renders.json); six pages embed Greenhouse's board, which robots.txt disallows for scripts: explained
- [x] 12 careers pages that refuse scripts join liveness.blocked (44 now) with their backup checks; Reddit's and Roku's
      RippleMatch pages watched (aliases mark them as known)
- [x] cassettes for all 76; verify --write (COVERAGE.md: none unverified); README, UNDERCLASSMEN.md
- [x] golden.py against main: PASS, the 198 unchanged; 484 rows go from no company to an added one
- [x] a live go-live morning recorded (data/stage2/morning-2026-11-10-batch1: run 25, 278 checked, 0 failed, 76
      seeded, 3,538 exchanges). Its alerts against the prediction found three gaps, fixed:
      - DriveWealth: 3 possible misses. Its Ashby board now repeats all 27 Greenhouse postings, dedupe_titles kept the
        Greenhouse copies, and Simplify links the Ashby ones (titled differently). New multi setting `twin_ids` (off
        unless set; stage2_batch.py sets it for every added multi company): a dropped copy's ids join the kept job's
        alt_ids, and the copy's board counts the job too (else that board looks empty and goes `board quiet` in 45
        days)
      - `new job site?` for nCino's old Workday site (gone from the tenant's robots.txt, feed 403) and Symmetry
        Systems' Lever board (404): recorded as mirrors (candidates/mirrors.yaml → liveness.aliases). Stage 1's list
        check had counted them as read because its candidate config still had them
      - the recording's home had no outbox, so crosscheck.backfill_shown marked nothing (3 rows shown instead of 20);
        morning.py now snapshots data/lists and the morning/digest emails at record time and replays from them
- [x] golden.py: PASS (394 cassettes of the 198, 86,968 filter verdicts, 39,053 matches, 36 Workday files); 484 rows
      go from no company to an added one
- [x] three mornings replayed (proof-6c71a5b, M2_NEW stripe;databricks;openai;figure-ai;neuralink;veeam, M2_FAIL
      figma;new-york-times): PASS. The 198's alerts, jobs, rows and requests identical; the old version's requests are
      the start of the new one's; no link of the old emails lost. Morning 1 sends: "Now watching" 88 roles (15 left
      out as already shown; 66 KB HTML, 252 KB .eml), the morning email 28 KB HTML with 110 untracked roles (113 with
      the old code), HEALTH 7 problems: Rocket's board empty (the 198's own, raised by the old code too) and 6
      `board quiet` (Viam, Udemy x2, Perpay, GoDaddy eventsandinterns, Haize Labs)
- [x] go-live with New York Times failing (proof-6c71a5b/new-1-nytfail): its 9 open re-matched rows stay pending
      (adopted), no simplify: job, seeded on its first good morning
- [x] re-match against the dry run: 81 rows (55 baseline, 26 untracked) against 80 (55, 25); NYT 12 (10), Enova 2 (1),
      Gemini 1 (2), Betterment 0 (1): rows Simplify added or dropped in between; no row of the 198 changed. The dry
      run's one miss (Rubrik "Software Engineering Intern") closed on Simplify before go-live
- [x] merged into main (fast-forward) and pushed 2026-11-10; the next real morning is batch 1's go-live. Then check:
      the run time, all 274 processed, the re-match, the 198 unchanged against the 5 mornings before, and the alerts
      above (Rocket's board empty and the 6 `board quiet`)
- Three of the 198 changed on main after the merge (2026-11-10, the morning's alerts), so the go-live comparison
  expects them to differ: Capital One's Workday reader counts a link-less posting once (`unlinked_once`), CoreWeave no
  longer reads its dead weights_and_biases board, Klaviyo reads its Ashby board after Greenhouse (multi, `twin_ids`).
  Proof: golden.py against main differs only in coreweave's and klaviyo's cassette runs (filters, matching, Workday
  files identical); three mornings replayed (data/stage2/morning-2026-11-10-fixes, batch 1's recording plus Klaviyo's
  Ashby answer): the other 274's requests identical and in order, and the three differ only as intended. Capital One
  is read once instead of twice (the recording lists one link-less posting, R1005268, 5 times: old "skipped 4",
  degraded); CoreWeave reads clean and marks its 3 closed jobs; Klaviyo's jobs gain the Ashby twin ids, nothing else

Corrections to STAGE1_REPORT.md's day-one alerts: `board quiet` needs no history, since the rule also reads a
board's own posting dates (newest > 45 days old alerts on the first read). Measured from Stage 1's reads, this
reproduces batch 1's 6 exactly; later batches: Eventual (Ashby, newest 47 days on Nov 10) and Northwestern Mutual's
SmartRecruiters page (6 evergreen postings dated 2015, 63 undated: a misleading alert, decide in batch 3). Alert
numbers: a run records the 198's alerts first, so on its own morning each gets the number the old code gives it; on
later mornings the added companies' earlier alerts have taken numbers, so the 198's next ones are higher than the
old code's (the replay compares alerts by key).

Every batch from now on: compare the recorded go-live morning's alerts with the batch's predicted day-one alerts
before replaying.

## Batch 1's go-live morning (2026-11-11, run 25): as predicted, one gap fixed
- 273 active companies checked (197 + 76), none failed, 23.9 min; the 198's part ended at 21.8 min, the added round
  took 2.0 min (76 checks, 82 requests), emails at 23.8 min. All 76 seeded, 5,507 jobs stored, 107 matching.
- The 198 against the five mornings before: every company's requests and time within its usual range, every start
  within 17 s of its median; the page scan and backup checks started earlier than on any of them (no retry pass).
- Alerts: Rocket's board empty and a Citadel Securities new page (the 198's own), then the 6 predicted `board quiet`
  (#78-#83); no possible miss, no `new job site?`. The 198's two took the lower numbers.
- Emails: "Now watching" 92 roles, 15 left out as already shown (65 KB HTML); the morning email 31 new roles, none
  from an added company, 161 untracked rows, none of a watched company (64 KB HTML); HEALTH 8 problems.
- Re-match: 88 rows given to batch 1's companies (58 known, 23 found, 7 abroad), none missed or sent via Simplify.
- Gap: rows stored under the Off-Season README's source name (`offseason`, before listings.json held both lists) were
  never re-matched while untracked, since their source is no longer downloaded: Gemini's "Product Management Intern"
  and Betterment's "Software Engineer Intern" (the dry run counted both; my note above put the difference down to
  Simplify's changes). Fixed in CrossCheck.adopt (such a row is open if today's list has its key), proven on
  morning-2026-11-10-fixes (golden PASS, three mornings PASS: only those two rows differ), merged 2026-11-11 (ef79eaa).
- Trackr's API has refused robots (Disallow: /) since 2026-11-09: its four lists raise `check gone dark` for the 198 on
  the third missed morning (2026-11-12), as the old code would.

## Batch 2: 58 Ashby, Lever, Rippling and RippleMatch companies (branch stage2-batch2)
- Bumble moves to batch 3: bumble.com/en/jobs redirects to Workday (bumble.wd3 / Bumble_Careers), which has answered
  "Workday is currently unavailable" (403, robots.txt too) since 2026-11-09; the registry's Lever board `bumbleinc`
  lists nothing. Nothing of Bumble's can be read today: decided in batch 3.
- Careers pages corrected: Cobot → co.bot/team, Persona AI → persona.ai (both link their Ashby board), Xcimer →
  xcimer.energy/careers (refuses scripts: joins liveness.blocked with a WordPress page list and archive.org copies).
- Commure reads its `commure` board only (`commure-athelas` answers 404; mirror). Superhuman reads its Ashby board and
  Grammarly's Greenhouse board (lists nothing today; it would raise `board quiet` 45 days on if it stays empty).
- Mirrors (candidates/mirrors.yaml): the dead boards lists or pages still link for ConductorOne, Superhuman,
  GlossGenius, Dusty Robotics and Commure; Progressive's RippleMatch page by name. Mercor's RippleMatch page is watched.
- Aliases: Netic "Cybernetic Labs", Superhuman "Grammarly", GlossGenius "Genius AI", Rivian-VW "Rivian and Volkswagen
  Group Technologies" (SimplifyJobs' names; their rows link the companies' own boards). stage2_batch.py's alias writer
  had silently skipped batch 2's (its insert point was batch 1's): fixed.
- Rivian-VW has `learn_ids`. The added round now gives stored rows to their companies before its checks
  (Runner._adopt_rows), so a posting the board leaves out is read on the first morning and seeded with the rest,
  not emailed as new the morning after.
- New: `stage2_batch.py listcheck <batch>` (linked job systems the final config doesn't know: 0 for batches 1 and 2);
  page recounts are dated (five boards had moved by 4-5 postings since 2026-11-09 and were recounted).
- [x] apply, build_config (332 companies), 58 cassettes, verify --write (COVERAGE.md: 331 verified, 1 blocked),
      README (332 companies, 153 of 313 pages, 49 blocked), UNDERCLASSMEN.md (275 with no program)
- Predicted for the go-live morning: `board quiet` for Eventual (newest posting 49 days old); no possible miss, no
  `new job site?`; "Now watching" about 115-124 roles
- [x] golden.py against main: PASS (546 cassette runs of the 198 and batch 1, 94,412 filter verdicts, 39,715 matches,
      36 Workday files); 462 rows go from no company to a batch 2 company
- [x] a live go-live morning recorded (data/stage2/morning-2026-11-11-batch2: run 26, 331 checked, 0 failed, 58
      seeded, 2,992 exchanges, 20.8 min; the added round's 134 companies from 18.0 min, 142 requests). Its alerts
      against the prediction: Eventual's `board quiet` as predicted; AMD `internships vanished` (the 198's own: its
      student roles fell from 96 to 10 in the morning's real run; the old code raises it too); and one gap, fixed:
      - `new job site?` for Rivian-VW: the registry links `ashby:board=rivianvw` (404; the board is rivianvw.tech)
        under "Rivian and Volkswagen Group Technologies", which the new alias matched. Recorded as a mirror.
        listcheck had used Stage 1's matches (lists.json, made with the old names): it now matches the lists the last
        morning kept with the final config, and shows this link without the mirror
      Also fixed: a list robots.txt closed before the added round ever read it (Trackr's four) no longer keeps the
      round from closing its `new job site?` alerts when the other lists stop linking a board
- [x] re-match: 75 rows given to batch 2's companies (65 known, 9 found, 1 abroad; the dry run had 72), 11 of them
      from the old off-season source, none missed; "Now watching" 116 roles, 8 left out as already shown (59 KB
      HTML); the morning email 30 KB HTML; Rivian-VW read the posting its Simplify row links (closed) on day one
- [x] three mornings replayed (proof-9a7cc2f, old = main with batch 1; M2_NEW stripe;databricks;openai;rivian-vw;
      cerebras;replit;neuralink, M2_FAIL figma;crusoe;new-york-times): PASS. The 198's tables identical; the first
      round's requests identical and in order (2,769 / 3,007 / 3,006), the added round asks only after it, and
      batch 1's requests are all there in their order. Batch 1's 76 companies compared on their own: jobs, state,
      rows, alerts and checks identical in all three mornings
- [x] go-live with Crusoe and Rivian-VW failing (proof-867d750/new-1-fail): their re-matched open row stays pending
      (adopted), no simplify: job, both seeded on their first good morning
- [x] merged into main (fast-forward) and pushed 2026-11-11; the next real morning is batch 2's go-live. Expected then: Eventual `board quiet`; from the 198's
      own side AMD `internships vanished` (if its student roles stay near 10) and Trackr's four lists and Akuna's
      three checks `check gone dark`

## Batch 2's go-live morning (2026-11-12, run 26): as predicted, one gap fixed
- 331 active companies checked (197 + 134), none failed, 26.5 min; the 198's checks ended at 17.2 min (as on Nov 11),
  their page scan, backup checks and watched boards ran to 23.0 min, the added round's checks took 2.0 min (134 checks,
  143 requests), emails at 26.4 min. All 58 seeded, 3,159 jobs stored, 125 matching.
- The 198 against the five mornings before: every company's requests within its usual range. Palo Alto Networks' read
  took 391 s (78-83 s before, the same 78 requests), so the companies queued behind it started up to 73 s later than
  their median.
- Alerts #84-#92: the 7 predicted `check gone dark` (Trackr's four lists, Akuna's three checks), a possible miss at
  Microsoft (the 198's own: "Data Scientist Intern - CoreAI", rejected by the filters as not a student role), and
  Eventual's `board quiet`. No `new job site?`. AMD's `internships vanished` did not come: it lists 11 student roles
  (10 the day before, 96 and 101 before that), an 89% fall, and the rule needs 90%. AMD took down 86 student roles on
  Nov 11 (53 matching, every US one); SimplifyJobs shows them closed too.
- Emails: "Now watching" 117 roles, 8 left out as already shown (57 KB HTML); the morning email 26 new roles (24 at the
  198, Rubrik's and Arcesium's from batch 1), 125 untracked rows (56 KB HTML); HEALTH "13 problems".
- Re-match: the 75 stored rows given to batch 2's companies as in the recording (65 known, 9 found, 1 abroad), none
  missed, no "via Simplify" job; Gemini's old off-season row went to it as fixed on Nov 11.
- Gap: HEALTH listed Trackr's four `check gone dark` twice (9 alerts, 13 lines). Each round's gone-dark check
  (moves.finish) reports the reads the rounds share, here the third-party lists the first round downloads; the alert
  list had them once. Fixed in RunSummary.absorb: a later round's copy of an alert an earlier round raised in the same
  run is dropped (61baa70). Proof on morning-2026-11-11-batch2 against main: golden PASS (662 cassette runs, 99,103
  filter verdicts, 40,124 matches, 36 Workday files identical); mornings 1 and 2 identical; morning 3 differs only in
  the HEALTH email, which loses the four repeated entries ("11 problems" → "7 problems").
- Bumble's Workday site still answers "Workday is currently unavailable" (403), four days on: held out of batch 3.

## Batch 3: 58 Workday companies (branch stage2-batch3)
- Bumble stays out: bumble.com/en/jobs still ends on Workday's maintenance page and its Workday feed answers 403
  (2026-11-09 to 11-12). For the user: wait, or add it as `status: blocked` until the site returns.
- Every site re-read on 2026-11-12 (160 reads, 1,452 requests; read_results*.json, pagecounts.json and pages.json
  dated): 27,625 jobs, 1,234 student roles and 627 matching at the 58 companies (27,785 / 1,263 / 647 on Nov 9).
- The subsidiaries the user approved are read with their parents from the first morning: NBCUniversal (Comcast, its
  SmartRecruiters page NBCUniversal3: 520 jobs, 56 matching), CenterWell (Humana), Depop (Etsy), Sarah Cannon
  (McKesson's SCRI_Careers), Simply Business (Travelers), NPA (Copart). build_plan.py had still listed the five
  Workday ones as "known, not read". Comcast gets the alias NBCUniversal (SimplifyJobs' name; its 4 rows link
  NBCUniversal3).
- Each Workday site is a source of its own (`multi`, `dedupe`, `twin_ids`; 22 companies), so a requisition two sites
  of a tenant list is stored once. Measured in the Nov 12 reads (site_copies.yaml): 12 companies repeat 640 postings
  (KLA 233 of 1,463, Morgan Stanley 204 of 1,573, McKesson 59, Mastercard 43, Cadence 42, Marvell 24, Disney 19,
  Hartford 9, Synchrony 3, Sonos 2, Copart 1, Vanguard 1); each copy has the kept job's requisition, 635 its title too
  (5 are reworded). Copart's and Vanguard's second sites repeated nothing on Nov 9: which sites repeat changes, so
  the rule is the same for all, not only for those that repeat today.
- `dedupe_titles` is left out from this batch on. It drops a later board's job whose title was already read, and that
  includes the board's own earlier jobs: Northwestern Mutual's SmartRecruiters page lists "Sr Software Engineer"
  three times (11 distinct openings dropped on Nov 12), Snyk's Ashby board 2; NBCUniversal has 14 titles Comcast also
  uses, each another job. Without it Snyk's 3 real copies (Ashby repeats Workday) are stored twice. In the
  recordings of the 42 multi companies no live company loses a job this way today (Klaviyo, Rockwell, DriveWealth,
  Superhuman: 0); the rule itself (multi.py compares with every earlier job, its docstring says "an earlier
  source's") is the user's to change, since the 198 use it.
- Found by re-reading the sites the plan had dropped and by the list pre-check:
  - McKesson's Acquisition_Campus site lists 2 Summer 2027 operations internships since Nov 10 (it was empty on
    Nov 9): read as a fifth source.
  - Nasdaq opened a Greenhouse board on Oct 27 (21 jobs, a co-op in Toronto) and SimplifyJobs links it since Nov 12:
    read as a second source (it would have raised `new job site?` on the first morning).
  - Three Workday sites list postings without a link today (none on Nov 9): Nordstrom 5, Wells Fargo 4, CenterWell 4.
    More than two mark a read degraded, so the three get `unlinked_ok: 50` (the setting the report planned for
    Walmart, Target, Lowe's and Bank of America): such a posting has no title, link or place to read.
- Careers pages: Synchrony's is www.synchronycareers.com (www.synchrony.com/careers fails at the TLS handshake).
  11 refuse scripts and join liveness.blocked (60 now) with their backup checks: Cadence, Ciena, Cohesity, Cox,
  DataRobot, Marvell, Verizon, Wells Fargo, and CoStar, GlobalFoundries and Nasdaq, which answered on Nov 9 and
  refuse on Nov 12. Own job lists that match the Workday reads by id: Cox (802 of 802), Wells Fargo (1,538 of 1,542),
  Verizon's /en/jobs/sitemap.xml (1,273 of 1,273; the probe had not followed the sitemap index). Program pages:
  Cox, Wells Fargo, Verizon (/en/sitemap.xml). GlobalFoundries' page sitemap answers 403: nothing to read there.
- Two sites careers pages name that no script may read (robots.txt) are listed in watch_unreadable: Nike's Avature
  talent community and Northwestern Mutual's iCIMS portal. The Phenom and Eightfold fronts Stage 1 noted (Chewy,
  Circle, Dexcom, Disney, FIS, Fiserv, Freddie Mac, Humana, Mastercard, Southwest, Warner Bros. Discovery) are not
  systems the page check names: nothing to record.
- Snap's and Verizon's RippleMatch pages are watched; short Workday tenants match a link only at its start
  (`anchor_host`: Morgan Stanley ms, Cox, KLA, PTC, AT&T att, Southwest swa, FIS); program keywords: The Hartford
  "early immersion program", USAA "accelerate program", Verizon "sprinternship".
- stage2_batch.py: `sitecopies`; Workday and SmartRecruiters feeds; page counts added up over a company's reads;
  the list pre-check names page systems as the page check does (batches 1 and 2 still 0 and 0).
- [x] apply, build_config (390 companies, 192 added), 58 cassettes, verify --write (COVERAGE.md: 389 verified,
      1 blocked; every count within 3 jobs or 2% of its page, or explained by the copies between sites), README
      (390 companies, 175 of 360 pages, 60 blocked), UNDERCLASSMEN.md (8 companies' programs, 325 with none)
- Predicted for the go-live morning: `board quiet` for Northwestern Mutual's SmartRecruiters page (its 6 dated
  postings are from 2015, 63 carry no date); a possible miss at Marvell if SimplifyJobs still lists "Data Science
  Intern" (closed at Marvell); no `new job site?`; "Now watching" about 490 to 550 roles
- [x] golden.py against main: PASS (662 cassette runs of the 198 and batches 1-2, 99,103 filter verdicts, 40,124
      matches, 36 Workday files identical); 1,914 stored and list rows go from no company to a batch 3 company
- [x] a live go-live morning recorded (data/stage2/morning-2026-11-12-batch3: run 27, 389 companies, 0 failed, 58
      seeded, 4,673 exchanges, 31.6 min; the 198's last check ended at 21.1 min, the added round's 190 companies
      from 21.6 to 27.9 min with 1,641 requests, its page scan, backup checks and watched boards to 31.5 min). Its
      alerts against the prediction: Northwestern Mutual's `board quiet` as predicted ("no new job on smartrecruiters
      source 2 in 4056 days"); no possible miss (SimplifyJobs closed Marvell's row), no `new job site?`; Palo Alto
      Networks `board empty` (the 198's own: its RippleMatch page went from 8 roles to none); and one gap, fixed:
      - McKesson `shape`: "skipped 4 postings without a link", on the first read and on the second look 3 minutes
        later. It had none in the morning's reads: a fourth Workday site with them today, and T-Mobile and Autodesk
        (the 198's) read degraded on their first try and clean on the second. McKesson gets `unlinked_ok: 50` too.
        Any other Workday company can raise this alert on a morning its site lists three or more such postings.
      First looks reached on that morning: 47 careers pages (Analog Devices' and The Washington Post's timed out and
      are read again the next morning), the 11 blocked companies' pages (Cox's answered), 16 Workday tenants' hidden
      sites, the 3 job lists, 3 program-page lists, 3 of the archive.org copies (the rest later in the week), both
      RippleMatch pages
- [x] re-match: 391 stored rows given to batch 3's companies (292 known, 85 found, 14 abroad; 62 from the old
      off-season source), none missed, no "via Simplify" job; "Now watching" 508 roles of 550 matching (42 left out
      as already shown)
- The first three-morning run (proof-f0da7be) showed two kinds of difference, both explained, and one of them led to
  sites the plan had missed:
  - Wells Fargo's tenant state (`blocked:…:workday:wf.wd1.myworkdayjobs.com`): the backup check's first look found a
    site robots.txt hides, WellsFargoJobsTargeted. Stage 1's survey (workday_sites.json) had listed 23 hidden sites
    at batch 3's tenants as unread and never read them, and could not survey the three tenants on myworkdaysite.com
    (Wells Fargo, Snap, Guidewire: their robots.txt is on <tenant>.<wdN>.myworkdayjobs.com). All read on Nov 12:
    - with student roles, now read: Nasdaq job_postings (8 jobs: "Business Development Intern - 2027 Summer
      Internship", "MIT Internship", "Nasdaq Campus Program - 2027"), Nike nke4 (16 jobs, 15 student roles, none on
      Nike's two public sites), Warner Bros. Discovery directshare (19, 2 matching), Equinix
      Applications_By_Invitations (7, an intern in Sydney), Zillow Referrals (199, 188 copies), Snap sourced (189,
      157 copies);
    - student sites that are empty or without a student role today, now read: Nordstrom nordstrom_internship (0),
      Chewy Student-Ambassador-Contractors (0), SailPoint SailPointInternships (2);
    - private, targeted or referral sites with jobs of their own, now read: Wells Fargo WellsFargoJobsTargeted (25,
      19 not on the public site), Etsy Private_Etsy_Careers (75, 8), Snap referral19 (25, 13), Fiserv P3M (10, 10);
    - Verizon frontier_career_site (384 jobs, 356 of them also on Verizon's site, no student role): Frontier, which
      Verizon bought. Read like the subsidiaries the user approved; it was not on the list they saw;
    - not read (another audience, or empty): Chewy VeterinaryCareers, Equinix Exclusive_Applications_by_Invite and
      Mastercard CUOReqSite (executives), McKesson Contractor_Conversions, Verizon contractor_external_careers, Snap
      immigration, and the 10 empty ones.
    Later batches: read every hidden site, and survey myworkdaysite.com tenants on their own host, before applying.
  - The weekly archive.org check reads a seventh of a round's companies a day, never-read ones first, so batch 3's
    ten take the first days and five earlier added companies' copies (Enova, Gusto, Lucid Software, Xcimer,
    YugabyteDB) are read some days later; nothing of the 198's moves. morning.py compare lists these for review
    (kv keys and 2-3 archive.org requests a morning) instead of failing, and counts a Workday tenant's host keys as
    its company's. With that, proof-f0da7be passes all three mornings, and batch 2's proof-9a7cc2f still passes.
- After the hidden sites: 37 of the 58 companies are `multi` (116 sources); verify: 27,249 jobs, 1,136 student roles,
  553 matching, 1,519 requests; 21 companies' sites repeat each other (site_copies.yaml); no job in any of the 53
  multi companies' recordings is dropped for a repeat inside its own source.
- [x] golden.py against main with the final config (84791cc): PASS (662 cassette runs, 99,103 filter verdicts, 40,124
      matches, 36 Workday files identical; 1,914 rows go to batch 3 companies)
- [x] a second live go-live morning recorded with the final config (data/stage2/morning-2026-11-12-batch3b: run 27,
      389 companies, 58 seeded, 4,636 exchanges, 29.2 min; the 198's last check ended at 20.5 min, the added round's
      192 companies from 21.1 to 25.4 min with 1,661 requests, 1,520 of them batch 3's). Alerts: Northwestern
      Mutual's `board quiet` (predicted); Palo Alto Networks `board empty` and T-Mobile `shape` (the 198's own:
      T-Mobile's Workday site answered with Workday's maintenance page on both tries; the old code raises both). No
      possible miss, no `new job site?`, no degraded read among the added companies
- [x] re-match: 392 stored rows given to batch 3's companies (293 known, 84 found, 15 abroad), none missed, no "via
      Simplify" job; "Now watching" 516 roles of 558 matching (42 left out as already shown; 58 KB HTML, 1.06 MB
      with its attachments), Nike's 14 and Nasdaq's 3 matching internships among them; the morning email 21 KB HTML
- [x] three mornings replayed (proof-84791cc, old = main; M2_NEW stripe;databricks;openai;kla;comcast;cerebras;
      neuralink, M2_FAIL figma;morgan-stanley;new-york-times): PASS. The 198's and batches 1-2's tables identical;
      the first round's requests identical and in order (3,044 less the added round's in the old run / 4,646 in the
      new one on morning 1); the added round asks only after it; for review: 2-3 archive.org requests a morning
      and 4-13 keys of the weekly archive.org check fall on other days for earlier added companies
- [x] go-live with KLA, Comcast and Marvell failing (proof-84791cc/new-1-fail): their 41 re-matched open rows stay
      pending (adopted), no "via Simplify" job, no possible miss; the three are seeded on their first good morning
- [x] merged into main (fast-forward) and pushed 2026-11-12; the next real morning is batch 3's go-live. Expected
      then: about 29 to 32 minutes; "Now watching" with about 516 roles at 58 companies; Northwestern Mutual `board
      quiet`; a `shape` alert at any Workday company whose site lists three or more postings without a link, or
      shows Workday's maintenance page, that morning (Workday did both on Nov 12)

## After batch 3: the user's answers (2026-11-12)

- Frontier (Verizon's hidden site) stays read.
- Bumble stays held and is read again at each batch; it is not added as `status: blocked`.
- Workday postings listed without a link: `unlinked_ok` stays with the four companies it was seen at (Nordstrom,
  Wells Fargo, Humana, McKesson). Each new case alerts once (`shape`) and is given the setting after that.
- The title rule (`dedupe_titles`) compares a later board's job only with earlier boards' jobs: two openings one
  board lists under the same title are both kept (multi.py). It can only keep more jobs. Klaviyo and Rockwell
  Automation of the 198 and DriveWealth and Superhuman of the added round use it; none of the 53 multi recordings
  has such a pair today, so nothing changes on the day. Batch 3's companies stay without the rule (a subsidiary
  or another site of the tenant uses the same titles for different jobs).
  Proof (430a7b0, old = main): golden.py PASS (778 cassette runs, 99,103 filter verdicts, 40,124 matches, 36 Workday
  files identical); three replayed mornings of the Nov 12 recording (morning-2026-11-12-batch3b/proof-430a7b0;
  M2_NEW stripe;klaviyo;rockwell-automation;drivewealth;superhuman;kla;comcast, M2_FAIL figma;morgan-stanley) PASS
  with no company excepted: every table, email and request identical. The new test fails on the old code.

## Batch 3's go-live morning (2026-11-13, run 27): as predicted

- 389 active companies checked in 32.6 minutes (predicted 29 to 32). The 198's checks ended at 18.8 min; the added
  round's 192 checks ran from 23.6 to 27.8 min with 1,643 requests; the emails went out at 32.5 min.
- All 58 seeded: 26,910 jobs, 547 matching. "Now watching": 507 roles, 40 left out as already shown (58 KB HTML,
  1.07 MB with its attachments). No batch 3 role in the morning email (28 new: 25 at the 198, Xcimer 2, Crusoe 1;
  66 KB HTML).
- Re-match: 395 stored rows given to batch 3's companies (296 known, 84 found, 15 abroad), none missed, no "via
  Simplify" job.
- The 198 against the five mornings before: the same 197 companies, every start within 10 s of its median, every
  request count inside its earlier range, none slower.
- Alerts #93 to #97: Northwestern Mutual `board quiet` (predicted); the 198's own Palo Alto Networks `board empty`
  (its RippleMatch page, seen in the recording) and three `error` alerts for Citadel, Citadel Securities and Citadel
  Securities Programs. Citadel rebuilt both sites that morning: robots.txt now names /sitemap.xml, the old
  /career-sitemap.xml and /page-sitemap.xml answer 404, and the new /sitemap/career.xml answered a bot check (403)
  on the one try made. Nothing to do with the added round; for the user. No `shape` alert at any Workday company.

## Batch 4: 12 Workday companies over 2,000 jobs (branch stage2-batch4)

Applied Materials, Bank of America, Citi, CVS Health, Dick's Sporting Goods, GE Vernova, Hewlett Packard Enterprise,
HP Inc., Lowe's, Micron Technology, Target, Walmart (Walmart Global Tech).

- Every site of the 12 tenants read on 2026-11-13, the hidden ones included (robots.txt of each tenant, then the
  first page of every site it names): no site with a student role of its own that the plan didn't already read.
  Read: Bank of America us-emplsv (robots.txt hides it), lateral-emea and lateral-ba_continuum (BA Continuum, the
  approved subsidiary); Citi 2 and Citi_Early_Careers_Events_Site (both hidden); CVS's CVS_Health_Careers and
  Private_Postings_Intern_Conversion_ONLY (a student-named site, 10 jobs); GE Vernova's public site and its hidden
  "executive" site, which lists 2,420 jobs, 301 of them only there; HP's public site and EXTEU-AC-CareerSite; HPE
  jobsathpe and acjobsite; Walmart's WalmartExternal and Non-WorkdayInternal (2,489 jobs, 293 only there).
  Not read: Bank of America Lateral-US (1,982 of 1,984 are on us-emplsv), Scoutt, lateral-apac, lateral-canada,
  lateral-latam, lateral-ous (hidden, outside the US) and Contractor-Conversion (hidden, contractors); HPE WFMathpe
  (1,729 of 1,753 on the sites read; none of the other 24 a student role); CVS's mergers site (1 job); Dick's two
  hidden sites (empty). None has a student role of its own today.
- The four giant store sites (your decision 1): the company's own check reads their student roles every morning,
  and the whole site is a watched board read once a week (liveness.watch_boards, every_days: 7; moves.pick reads a
  seventh of a round's weekly boards a day, so each of the four gets its own morning, CVS first).
  | Site | Daily read | Jobs / matching | Whole site on 2026-11-13 | Matching roles outside the daily read |
  |---|---|---|---|---|
  | Walmart | job family "Intern" (2 requests) + all of Non-WorkdayInternal (135) | 2,523 / 25 | 20,190 jobs, 1,029 requests, 20.5 min | 8: 5 "Pre Grad Intern - Sam's" (pharmacy), 2 "Intern Conversion" full-time offers, 1 Canadian "Optician, Student" |
  | CVS Health | worker type "Intern" (3) + the intern-conversion site (1) | 64 / 15 | 18,452 jobs, 1,006 requests, 18 min | 2 clinical student rotations |
  | Target | job family group "Internships" (5) | 90 / 22 | 14,120 jobs, 729 requests, 15.5 min | 2 full-time programs starting in 2027 |
  | Lowe's | a search for "intern" (11) | 210 / 18 | 12,994 jobs, 658 requests, 11 min | none |
  Eleven of the 12 outside roles are tagged unsure. Each raises one `posting elsewhere?` alert the morning after its
  site's first weekly read (the board's read, then a healthy poll that still lacks it). CVS's virtual underwriting
  externship is under its Intern worker type, so it is in the daily read.
- New Workday setting `split_first` (off unless set; tests in test_added_settings.py): a search at the 2,000-job cap
  is split from its first page. Without it the capped search is read to its end first: 100 requests for 2,000 jobs
  the split reads again. It replaces the plan's configured partitions, whose lists of facet ids would go stale with
  every new country or location. With `pack` it brought Citi from 810 requests to 232, Applied Materials from 213 to
  129, Micron from 301 to 155, Dick's from 308 to 204. Every batch 4 Workday source has both except the giants'
  daily reads, which are far below the cap.
- New Workday setting `past_total` (off unless set; tests in test_added_settings.py), found by the first go-live
  recording: Walmart's Non-WorkdayInternal read failed on its first try ("collected 1364 jobs but the source reports
  1387"). Walmart had published 18 postings during the 75-second read of that job family: each pushed the list down
  by one, so 18 postings came twice and the 18 oldest fell past the offset where the reader stops (the first page's
  total). With the setting a search is read on while its last page is full and brings postings not seen before (one
  more request when a total is a multiple of 20; a page past the end is empty, or at Target's tenant repeats earlier
  postings, which ends it). Every batch 4 Workday source and the four weekly reads have it: one failed partition
  fails a whole 20-minute weekly read. The 198 don't (their requests would change): for the user.
- Postings without a link: Citi listed 4 on 2026-11-13 and the read stopped (the limit follows the search being
  read); it has `unlinked_ok: 50` now, as have the companies Stage 1 saw them at (Bank of America, CVS, Lowe's,
  Target, Walmart). The other six have none: a new case alerts once.
- Each Workday site is a source of its own with `dedupe`, as in batch 3: GE Vernova's executive site repeats 2,119
  of the public site's requisitions, HPE's acjobsite 1,562, HP's EU site 912, Citi's events site 4, Walmart's
  second site 2 of the 38 interns.
- Counted against the sites (verify, 2026-11-13): all 12 match. 24,895 jobs, 1,086 student roles, 384 matching.
  A site read one location at a time lists a job under each of its locations, so the searches' totals add up to too
  many (Bank of America 5,215 for 3,118 jobs): pagecount now counts such a site from its first page (its jobs per
  time type or worker type).
- Careers pages: all 12 answer; none joins liveness.blocked. Five Eightfold fronts their pages name are recorded as
  mirrors (Applied Materials: 2,222 of its 2,223 jobs are on the Workday site; Citi's events site, HP and Micron
  from Stage 1). listcheck: 0 and 0.
- Bank of America has `timeout_minutes: 10` (its three sites took 352 s; 8 minutes is the default). The added round's
  `watch_seconds` went from 1500 to 1800: Walmart's weekly read took 1,228 s and a weekly read starts only with 1.15
  times its last time left.
- Citi's program "D1 Athlete Development Program" is a company keyword. UNDERCLASSMEN.md: 9 rows for Bank of
  America (3, on its campus site, read from batch 6), Citi (3), CVS, Lowe's and Walmart; two more "open now" rows
  (Lowe's Exploratory Software Engineering internship, CVS's underwriting externship); 332 with no program.
- Stage 1 tooling: reads_big.yaml now holds only the four daily student reads; the giants' entries in reads.yaml are
  their weekly full reads. Today's results of extra sites go in read_results_extra.json (it overrides
  read_results.json, so a fresh result left only there was ignored).
