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
- main moved during the batch: 1bb8da7 (the user's change for Citadel's rebuilt sites, 2026-11-13 10:35). The branch
  was rebased on it (COVERAGE.md and UNDERCLASSMEN.md merged by hand, COVERAGE.md and companies.yaml regenerated)
  and every proof below was run after the rebase, against that main.
- [x] tests pass; golden.py against main (9fd9414): PASS (the 778 cassette runs of the companies already live
      identical, 128,194 filter verdicts, 40,424 matches, 91 Workday files; 937 rows go to batch 4's companies)
- [x] two live go-live mornings recorded on a copy of the database. The first (morning-2026-11-13-batch4) found
      Walmart's failed read (`past_total`, above). The second, with the final code and config
      (morning-2026-11-13-batch4b: run 28, 404 checks, 12 seeded, 7,219 exchanges): the 198's checks ended at 18.9
      min; the added round's 204 companies ran from 19.4 to 28.6 min with 3,357 requests (1,700 batch 4's; Bank of
      America the longest at 306 s); CVS's weekly read took 1,081 s. All 12 read on the first pass. The clock says
      113.8 min because the laptop lid was closed for 65 of them (pmset log: Clamshell Sleep 12:53 to 13:58); the
      run itself is about 49 min with a weekly read, about 35 without (a recording made the same day skips most
      careers pages, which take about 4 more minutes on a real morning)
- [x] alerts in the recording, the predicted day-one alerts: three possible misses, each a SimplifyJobs row the
      checker has and the filters reject (Lowe's "Store Operations Intern - Retail Facilities Support": excluded
      field 'Store'; Applied Materials "Industrial Engineering Intern": excluded field 'Industrial Engineering';
      Micron "Data Scientist New Grad - AI for Business Functions": new grad). No `new job site?`, no `moved?`, no
      degraded read. The 198's own: Citadel's three checks fail in the recording (it was made with the branch's
      code from before the rebase)
- [x] re-match: 222 stored rows given to batch 4's companies (163 known, 51 found, 5 abroad, 3 filtered), none
      missed, no "via Simplify" job; "Now watching" 361 roles of 388 matching (27 left out as already shown; 58 KB
      HTML, 786 KB with its attachments); the morning email 72 KB HTML
- [x] three mornings replayed (proof-9fd9414, old = main 1bb8da7; M2_NEW stripe;databricks;openai;walmart;citi;
      micron;cvs-health;kla;cerebras, M2_FAIL figma;bank-of-america;target;new-york-times): PASS. The tables of the
      198 and of batches 1 to 3 identical, the first round's requests identical and in order. For review: the run
      totals, the email subjects, and a HEALTH email only the new version sends on morning 1 (the three possible
      misses). The compare step took that email as a difference; it now lists it for review, since the alerts of the
      198 are compared row by row (runall-batch4-9fd9414-compare.log is the comparison with that change)
- [x] the morning after CVS's weekly read (morning 2 of the replay): two `posting elsewhere?` alerts, for the two
      clinical student rotations outside its Intern worker type, as predicted
- [x] go-live with Walmart, HPE and Micron failing (proof-9fd9414/new-1-fail): not seeded, their 11 open rows stay
      pending, no "via Simplify" job, three `error` alerts

## Batch 4's go-live mornings (2026-11-14 run 28, 2026-11-15 run 29)

- Nov 14 (run 28): Workday was down all morning. Every Workday site answered Workday's maintenance page (132 shape
  errors; some tenants' robots.txt answered 503), and Rippling's API and Citadel's new sitemaps refused (403). 72
  checks failed, 79 problems in the HEALTH email; all of them cleared on Nov 15. Two of batch 4's companies were
  seeded (HP from its Greenhouse boards, Walmart): "Now watching" 31 roles. CVS's first weekly read failed.
- Nov 15 (run 29): 404 checks, 3 failed (Citadel's three, the 198's own), 68.7 minutes: two weekly full reads (CVS
  again, as a failed read is read again the next morning, 992 s, and Lowe's on its own turn, 662 s). The other ten
  seeded: "Now watching" 303 roles, 20 left out as already shown; HP's Workday roles (its source's first answer)
  went once in the morning email's "already open" (26). The 198 against the mornings before: the same 197
  companies, requests within their range (Bloomberg 29, with no new job to read in detail), none slower.
- Alerts: the three predicted possible misses (Lowe's, Applied Materials, Micron). Not predicted:
  - `new site` at CVS (Private_Postings_Mergers_and_Acquisitions_ONLY) and HPE (WFMathpe; ACJobSite and Jobsathpe
    raised and cleared in the same run). On Nov 14 their tenants answered /robots.txt with the maintenance page
    (HTML, status 200), which was cached; the first look of the `new site` check took it for a robots.txt naming no
    site, so on Nov 15 every site not read looked new. Fixed: the check skips a cached copy without one robots.txt
    line (a Workday tenant always serves one), and compares site names in any case, as its alert sweep does. The
    shared robots.txt handling is unchanged: 12 hosts (SmartRecruiters, IBM's API, Oracle, GEICO, KLA…) answer an HTML
    page for /robots.txt every day, which means "no rules". The two open alerts are sites batch 4 chose not to read.
  - a possible miss at Applied Materials: "2027 Spring Software Engineer Co-op (Billerica, MA)" was on its site on
    Nov 13 (both recordings) and gone by Nov 15 (no search finds R2631540; its page answers 403). Workday was down on
    the 14th, so the first good read came after it closed; SimplifyJobs still lists it.
- Emailed twice: Micron's "Enterprise SSD Architecture Intern", a Simplify row first seen on Nov 14 while Micron
  couldn't be read, went out "via Simplify" (as agreed for new rows), and the next morning "Now watching" listed it
  again, as Simplify's copy and as the site's posting. Fixed: "Now watching" leaves out a role tied to a row stored
  via Simplify (when that copy passed the filters) and the copy itself, as it does for rows shown in an untracked list.
- The Nov 15 morning email had 103 KB of HTML, past Gmail's ~102 KB clipping: 44 new roles and 26 "already open",
  each list capped at 50 rows on its own. For the user (it is the 198's email too).
- [x] both fixes tested (each new test fails on the old code: "Now watching" listed 4 roles instead of 2; the outage
      page was taken for the first look); golden.py against main (a611189): PASS (802 cassette runs, 155,604 filter
      verdicts, 40,454 matches, 103 Workday files identical); three replayed mornings of the Nov 13 recording
      (proof-a611189): PASS, with nothing even for review (no outage page and no row sent via Simplify in it)
- For the user to dismiss: #179 and #182 (sites batch 4 chose not to read), #186 (a closed posting)

## Batch 5: 24 companies on Oracle, Jibe, SmartRecruiters, Phenom, Radancy, Eightfold, iCIMS and Jobvite (branch stage2-batch5)

American Express, Arista Networks, athenahealth, BNY, Charles Schwab, Ford, Fortinet, Hilton, ICE (NYSE), Intuitive
Surgical, JPMorgan Chase, Keysight, Macy's, Navy Federal, Principal, Qualcomm, Rivian, SAS, State Farm, Texas
Instruments, Tyler Technologies, United Airlines, UnitedHealth Group (Optum), Western Digital.

- Costco moves to batch 6: every Costco row SimplifyJobs ever listed is on its IT site (the Taleo reader of batch 6);
  its warehouse site has no matching role, and going live without the IT site would make its 8 open rows day-one
  possible misses and send its interns as "already open" later instead of in "Now watching". Symmetry Systems is
  Zscaler's (an alias since batch 1).
- Every site re-read on 2026-11-15, the copies the plan set aside included (40 reads), and every careers page.
  - athenahealth's and Ford's careers pages now refuse scripts (403): their own careers sites answer and are the
    pages read (careers.athenahealth.com, where its jobs are, and www.careers.ford.com).
  - The Oracle sites recorded as copies list only jobs of the site read (BNY's two others, Fortinet's CX_1,
    JPMorgan's CX_2001, TI's edbz CX_1: all the same; Macy's CX_1001 a subset; Hilton's CX_1009 has 4 of its own,
    hotel roles, none a student role).
  - Western Digital's SmartRecruiters page now lists 162 postings (all 336 on Nov 9); its search counts 325 and lists
    only its newest 100, half of them not on the page (two US Summer 2027 internships among them); neither the
    page's own keyword search nor any search parameter reaches the rest. The read is the page plus the newest 100
    (210): every new posting is read on its first morning. The first go-live recording found the gap: a Simplify row,
    "Winter 2027 Intern/Co-op Development Engineer" (posted Sep 28, open, its page has the apply button), was in
    neither, and became a day-one possible miss. New SmartRecruiters setting `watch_ids`/`learn_ids` (off unless set,
    as for Oracle and Ashby; tests in test_added_settings.py): the postings Simplify links are read from their own
    page; one whose page says it has expired is closed. Western Digital has it: 211 jobs live, the co-op among them.
- Settings from Stage 1's plan: `learn_ids` (Simplify rows of open but unlisted requisitions read one by one) for
  American Express, JPMorgan Chase, BNY and Texas Instruments; `ignore_search_total` for Arista (its search counts
  132 and lists the same 98 on every page) and Western Digital. TI reads two Oracle sites, and learn_ids worked only
  for a company with one source: a multi-source company may now set it on one source, which learns from the links
  to its own host (runner.py; no company used learn_ids inside a source before, so nothing else changes).
- URL markers (`match_urls`) for systems the cross-check can't tell from a link: SmartRecruiters and Jobvite (the
  company's name on a shared host), Phenom, Radancy and iCIMS hosts, and the iCIMS portals robots.txt closes behind
  ICE's Jibe site and Schwab's Radancy site (from batch 5 on; earlier batches' settings are unchanged).
- Lists and careers pages: every job system the lists link is configured or recorded as a copy (listcheck: 0). The
  careers pages name 14 iCIMS portals robots.txt closes (Keysight 2, Principal 8 including its Asian and internal
  portals, Rivian's internal one, State Farm 3): listed as unreadable (watch_unreadable). The portals behind ICE's,
  Keysight's and Rivian's Jibe sites are copies: the ids the lists link there are in the Jibe reads.
- Backup checks for the four careers pages that refuse scripts or are closed by robots.txt: Arista and Intuitive
  (refused), Fortinet and SAS (robots.txt): archive.org copies for all four, Intuitive's job sitemap and its program
  pages. liveness.blocked: 64.
- Page counts: the count each Oracle site's page shows (TotalJobsCount of the search it calls), Radancy's search page
  where robots.txt allows it (UnitedHealth; Schwab's is closed: its sitemap is the list), Tyler's hosted Jobvite page
  (it cuts off after 125 of 144 jobs, alphabetically), and the systems' own totals for the rest. All 24 match or are
  explained (verify, 2026-11-15): 35,391 jobs, 1,052 student roles, 501 matching.
- JPMorgan Chase's "Fellowship Program" is a company keyword (a 2027 posting becomes a sure match, tagged
  freshman/sophomore). UNDERCLASSMEN.md: 10 rows (American Express 2, BNY 2, Ford 1, JPMorgan Chase 4, UnitedHealth
  1); 351 companies with no program.
- [x] tests pass; golden.py against main (a3b2d46): PASS (802 cassette runs of the companies already live identical,
      155,604 filter verdicts, 40,454 matches, 103 Workday files; 1,281 rows go to batch 5's companies)
- [x] two live go-live mornings recorded on a copy of the database. The first (morning-2026-11-15-batch5) found
      Western Digital's unlisted co-op (above). The second, with the final code and config (morning-2026-11-15-batch5b:
      run 30, 429 checks, 24 seeded, 7,986 exchanges, 56.2 min with Target's first weekly read): the 198's checks
      ended at 18.8 min, the added round's 228 companies ran from 24.5 to 38.6 min with 4,104 requests (581 batch
      5's; Qualcomm the longest at 201 s). Alerts: CVS's two clinical rotations (`posting elsewhere?`, predicted after
      its weekly read), a Texas Instruments row the filters reject ("Product Marketing Engineer Intern - Marketing":
      excluded field 'Sales'), and the 198's own Rocket `board empty`; no `new job site?`, no `moved?`. Citi's first
      check met one Workday maintenance page mid-read; the retry pass read it whole
- [x] re-match: 347 stored rows given to batch 5's companies (269 known, 54 found, 23 abroad, 1 filtered), none
      missed, no "via Simplify" job; "Now watching" 489 roles; learn_ids read 23 open requisitions the companies'
      own lists leave out (American Express 9, Texas Instruments 9, JPMorgan Chase 4, BNY 1) and Western Digital's co-op
- [x] three mornings replayed (proof-a3b2d46, old = main 42be46e; M2_NEW stripe;databricks;openai;walmart;
      jpmorgan-chase;qualcomm;western-digital;keysight, M2_FAIL figma;target;hilton;intuitive-surgical): PASS when the
      compare is given batch 5's companies as the ones added. For review: 2 archive.org requests and 4 to 10 keys of
      the weekly archive.org check of earlier added companies fall on other days (the round grew)
- [x] go-live with JPMorgan Chase, Keysight and Western Digital failing (new-1-fail): not seeded, their 11 open rows
      stay pending, no "via Simplify" job, three `error` alerts
- Correction to the proofs of batch 4 and of the go-live fixes: their compare was given every added company as
  "added", which also exempted batches 1 to 3. Compared again with batch 4's 12 companies only (proof-9fd9414):
  PASS, so batches 1 to 3 were identical. The go-live fixes compared with nothing exempt (proof-a611189): morning 1
  differs only in the reworded "Now watching" sentence (the morning and HEALTH emails byte for byte), mornings 2 and
  3 PASS. The compare now pairs emails by kind: written in the same second, they sort by name, not by sending order.

## After batch 5: the user's answers (2026-11-15)

- Gmail clipping: yes. The morning email (and the new-postings email) now lists 50 roles at most in its body, new and
  already-open ones together, the new ones first; a list that doesn't fit is attached whole. Rebuilt with the Nov 15
  morning's 70 roles, its role lists go from 86.8 KB of HTML to 66.3 KB (the whole email about 83 KB instead of
  103). Proof (bb2001c, old = main 1f5d456): golden PASS; three replayed mornings PASS with nothing exempt (none had
  more than 50 roles); test_new_and_already_open_roles_share_one_body_cap fails on the old code.
- Disk: every recorded morning but the latest (morning-2026-11-15-batch5b) deleted; data/stage2 40 GB to 4.1 GB.
- `past_total` for the 198: measured, for the user (32 of the 198 read Workday, plus 7 watched Workday boards; 7
  more requests of 1,583 on the Nov 15 recording; no Workday read of the 198 fell short of its count in the run
  history since Oct 19).

## Batch 5's go-live morning (2026-11-16, run 30): batch 5 as predicted; Workday answered 429

- Batch 5: all 24 read and seeded, no failure (580 requests); "Now watching" 487 roles; Western Digital's unlisted
  co-op emailed; learn_ids found 24 open unlisted requisitions; alerts as predicted (CVS's two clinical rotations,
  TI's filtered row).
- Workday answered HTTP 429 to most of its sites from the run's first minutes, the 198's included (Capital One,
  T-Mobile, Workday, Adobe, PayPal, Salesforce, Visa, CrowdStrike, Zendesk, Intel…): 101 of 132 Workday checks
  failed or came out partial, the 198's round took 36.5 min instead of about 19, the run 83 min, and 43 second tries
  were postponed. Workday had never answered 429 before. On the Nov 15 recording, the 198's round peaks near 4
  Workday requests a second and the added round at 11 a second across up to 51 Workday sites in a minute (each
  site paced on its own, 12 workers). One request at 15:16 UTC got an ordinary answer: a rate limit, not a block.
- Fix (the user chose to cover every company): `http.host_groups.workday`, one shared pace of 3 requests a second
  for all Workday sites (myworkdayjobs.com, myworkdaysite.com) across threads and rounds, and a 429 from any of them
  pauses all of them for 60 s, after which the request is asked again (up to 3 pauses; before, a read gave up after
  4 quick tries while the other threads kept asking). The added round's time limit went from 35 to 50 minutes (its
  Workday reads, about 3,300 requests, take 18 minutes or more at 3 a second). Tests in test_http.py. Proof
  (old = main b698ee5): golden PASS; three replayed mornings PASS with nothing exempt (replays are never paced).
- To watch: NVIDIA's weekly full read (the 198's) last completed on Nov 7 (Nov 14 the outage, Nov 15 cut short, Nov
  16 out of time): it is read first on the next morning.

## 2026-11-17 (run 31): Workday still answered 429, at 3 requests a second

- The run's first Workday request got a 429 (06:53:19 local, about 22 hours after the last request), and a new 429
  came nearly every minute after that: 98 pauses of 60 s in 97 minutes. About 550 Workday requests got through in
  completed reads (3,229 on Nov 15, 1,625 on Nov 16); most Workday reads ran out of time partway ("time budget
  exhausted waiting for workday's next turn"). The careers-page scan was never reached on Nov 16 or 17, so 29 pages
  that last answered on Nov 14 alerted `check gone dark` (none of them is down). Partial reads close nothing. One
  request at 14:53 UTC, 20 minutes after the run, got an ordinary 200: a limit that resets, not a block.
- Fixes (the user's choice): robots.txt now takes its turn like any request (per host and in its host group; until
  now each morning began with an unpaced burst of them, every copy being older than 12 hours), and a 429 on a Workday
  robots.txt pauses the group and asks again. The group pause steps up, 60, 120, 300 s, while 429s come back within
  5 minutes of a pause's end, honors a longer Retry-After (up to 15 min), and is logged with the 429's headers, body
  start and the requests sent since the last pause, to measure the limit. Proof (old = main a3760e2): golden PASS;
  tests in test_http.py.
- To watch: tomorrow's log lines `workday answered 429 (...)`: their headers and "N requests in S s since the last
  pause ended" say what the limit is.
- Rerun of the 96 Workday companies that failed (run 32, 15:37 to 16:30 UTC, the pause stepping up): all 96 partial
  again, 88 requests, 1,340 jobs; 3 roles emailed (KLA 2, Comcast 1). The first 4 requests worked; then every pause,
  60 s, 120 s and ten of 300 s, let only 1 to 3 requests through before the next 429. Every 429 is a Cloudflare
  challenge page: `cf-mitigated: challenge`, `server: cloudflare`, an HTML body, no Retry-After, no rate-limit
  headers. Back to a fixed 60 s pause (about 6 requests a minute this morning against about 2).

## 2026-11-17: the morning check of run 31, the late checks' own time, and one Chrome test

- Runs 31 and 32 by company (last check): of the 198, 160 non-Workday companies read cleanly; the 3 others were
  Citadel's checks (HTTP 403, before they moved to Chrome at 10:09); 29 of the 34 Workday companies came out partial
  or failed. Of the added, 157 non-Workday companies read cleanly, plus Qualcomm (batch 5): its first read stopped 21
  jobs short of its total (Eightfold's order moving during a 207 s walk: degraded) and its second ran out of the
  round's time (alert dismissed by the user; no count_tolerance on one short read in two, watched); 67 of the 70
  Workday companies came out partial or failed. NVIDIA's daily read (Eightfold) was whole; its weekly Workday full
  read is still undone since Nov 7.
- Found: neither round's careers-page scan, backup checks nor watched boards ran on Nov 16 or 17 (every
  `page_scan_at` and `blocked:ok` is Nov 15 or older). They had to end five minutes before the round's limit, and
  Workday's waits held the reading past it (the 198's round 36 min both days). A third such morning would have raised
  `check gone dark` for about 440 reads, 160 of them the 198's careers pages.
- The user's decision (permanent): Workday's reading is not cut short on refusal days; the late checks get their own
  time after the reading ends, even if the run takes longer. Done: the page scan, the blocked companies' checks and the
  watched boards each get their whole budget counted from their own start, in both rounds. On a morning when Workday
  refuses, expect up to about 2.5 hours (the reading as on Nov 17, then up to 14 min of the 198's late checks and 36
  of the added round's, which read Workday sites too). Proof (old = main d0cad33): golden PASS; three replayed
  mornings PASS with nothing exempt (replays never reach a time limit); two tests that fail on the old code.
- One Chrome test (the user's request, report before any change), NVIDIA's Workday site, 13:53 to 13:54 local: the
  script's job-list POST got 429 `cf-mitigated: challenge` on its first request, before and after; a minimized real
  Chrome window (fresh profile, as browser.py opens it, nothing hidden, nothing clicked) loaded the site (200, 3.5 s,
  no challenge shown) and its own job-list request, then 30 more job-list POSTs from inside the page about one every
  1.5 s: all 200, none challenged (postings per answer not counted). Chrome was closed and its profile deleted. Workday's
  challenge goes by client, as Citadel's does. Nothing changed for it yet.

## 2026-11-17/18: every Workday request read through Chrome (1e669b7), proven

- Why: since Nov 16 Workday's Cloudflare challenged every script request (429 `cf-mitigated: challenge`) whatever the
  pace; real Chrome was never challenged. The user's choices: every Workday site through Chrome (one refused script
  request pauses the whole group), the same requests and the same reading as before the refusals, only the transport
  changed. Done inside `Http.request` for a host group with `browser: true`: one minimized Chrome per run
  (`chrome_session.py`, async Playwright on its own thread), one tab per site opened by loading its robots.txt (the
  robots check needs it anyway), each request a `fetch()` from that tab with httpx's own method, URL, body and headers.
  Every run first stops and deletes Chrome profiles whose owning process no longer runs (PID and start time).
- Trial (Nov 17, 19:11 to 19:18 local, 12 sites, one minimized Chrome): 3/s 361 of 361 answered 200, 5/s 601 of 601,
  10/s 1,201 of 1,201 (9.94/s), no challenge. 20 of those requests again through httpx: all 200, 19 the same bytes;
  Walmart's differed, and asking it again through Chrome gave httpx's bytes (its list changed in between). The user
  chose 10/s. Chrome sends 16 headers its own way (`CHROME_SETS` in http.py), each approved.
- Proofs (old = main 139717e):
  1. golden PASS (850 cassettes, 195,570 verdicts, 40,578 matches, 104 Workday robots files); three replayed mornings
     PASS with nothing exempt. `morning.py`'s replay now accepts `browser=`, so Citadel's checks replay their recorded
     403s instead of crashing the same way in old and new.
  2. tests: `tests/test_chrome_session.py` (37, plus 4 live ones against a local server with
     `INTERNWATCH_CHROME_TESTS=1`): the exact request, the same Resp and recording, failures, robots, pauses,
     timeouts, the owner-aware sweep, Chrome closed after a run, a crash, or a Chrome that can't start.
  3. send-step replay (`tools/prove/sendstep.py`, Nov 15's recording through the real `Http.request`): 7,986 of 7,986
     outcomes the same; 2,518 non-Workday requests the same, in order, Chrome never touched; 5,632 Workday requests
     reach Chrome with httpx's method, URL, body and headers apart from `CHROME_SETS`; 230 robots.txt fetches (101 tab
     loads), 1 redirect.
  4. a live morning through Chrome (`tools/prove/chrome_morning.py`; recorded on a copy Nov 17 21:44 to 22:40, run
     33, against Nov 15's recording and run 29) PASS: 103 of 103 Workday checks whole on the first try; 5,421 Workday
     answers 200, 2 answers 422 (one-request checks of boards that don't exist at Dell and Netflix); 7 searches short
     of their totals by 13 postings, each within the reader's 1.5% (Nov 15: 2 by 2; postings shifting during a walk
     are as common through httpx: 140 postings on two pages of one search on Nov 15, 85 here); the same postedOn forms;
     the same place text for 84,509 of the 84,574 postings both mornings list (the rest real edits); Workday reading
     10.5 min in the 198's round (10.4) and 7.7 in the added round (6.9: about 12 sites start at once, more than the
     10/s pace allows); the whole morning 56 min (69). Request differences: Citi read twice on Nov 15 (its first read
     met Workday's maintenance page); watched boards reached this time (a0d06f7); Bloomberg Industry Group added after
     Nov 15's recording; T-Mobile's weekly alumni read skipped for room after NVIDIA's weekly read (245 s through
     Chrome, 252 s on its last httpx read). No Chrome or profile left. An earlier recording, paused 63 min at the
     user's request, was dropped (its time limits ran out); its Chrome ended with it and the leftover sweep deleted its
     profile ("left by process 59273, which no longer runs").
  5. role by role (`tools/prove/chrome_roles.py`) PASS: 69,110 open Workday roles at 103 companies; 64,280 appeared.
     Of the 4,830 missing, 4,781 pages confirm them closed, 28 were relisted since, 14 were unlisted on Nov 15 too, 4
     are listed at a new address (same requisition), 3 slipped past Salesforce's walk (1,567 of 1,570; Workday's own
     search finds them). 3,243 new roles: 3,109 posted after their site's last complete read, 132 on its day, and 2 at
     HPE listed late (Nov 15's complete read of 1,774 didn't list them, never in the database, dated October). 216
     reopened: 211 pages open, 5 closed within the hour after the morning. Filters: 1,145 matched against the
     database's 1,201, every difference explained (179 roles opened or closed, 51 moved roles compared as one, 4
     stored decisions older than a filter change, 2 postings retitled, CrowdStrike's "Launch Intern" moved to Reading,
     UK and rejected there).
     - Found: Workday answers a removed posting's job page with 403 `{"errorCode":"S22","message":"permission
       denied"}` at 82 of the 97 companies with missing roles (others answer 404 or `canApply: false`); httpx gets the
       same, and so does a role closed Oct 20. The user approved counting it as closed (2026-11-18), and four named
       cases: same requisition at a new address, slipped past a walk, listed late or relisted, closed since the
       morning. Every 403 asked again was S22 (4,078).
     - Pages: 5,050 asked in 63 min (company by company, so mostly one site at a time), then the 4,118 that answered
       403 asked again in 7.3 min (one site per thread, 12 at once).
  6. the first real morning (run 33, Nov 18 08:32 to 09:36 local, started by hand) against run 29: 103 of 103
     Workday checks clean (run 29: 103; runs 30 to 32: 31, 7, 0), 4,546 requests in them (4,556), Workday reading
     10.6 min of wall time in the 198's round (10.4) and 7.9 in the added round (6.9); no 429, no challenge, no
     warning in the log; one Chrome for the run, closed and its profile deleted. 426 checked, 0 failed, 93 new
     matches emailed (roles posted during the refused mornings among them).
- Side finding (the runner, not Chrome: Nov 15's recorded morning through httpx does the same): a list's place
  shorter than the stored one replaces it, and the role is judged on it. Marvell lists "Yokneam" for a stored
  "Yokneam (Israel)", so 4 Marvell roles in Israel and Switzerland become possible matches ("location not
  recognised") on their next complete read. Left as is.

## 2026-11-18: careers pages read 8 at a time
- Why: run 33's health email had 215 `check gone dark` alerts, "Careers page has not answered since 2026-11-15". The
  daily careers-page scan got no time on Nov 16 and 17 (fixed by a0d06f7), and on Nov 18 it read 138 of the 351 due
  pages before its budgets ran out (180 s in the 198's round: 88 read; 240 s in the added round: 50 read). Read one at
  a time, a page took about 1 s until 07a45df paced robots.txt like any request (Nov 17): each page now waits its
  host's 1 s turn after its robots.txt, about 2 s a page, so the budgets held about half the pages. In the added round
  Washington Post's timeout (145 s, 4 attempts) took most of the budget. Not Chrome: careers pages are not on Workday.
- Change: `liveness.read_pages` reads the due pages `page_scan_workers` (8) at a time, started in the same order
  (retries first, then oldest), none after the budget; each host keeps its own pace, so no site gets more. The pages
  read are then compared one by one in that order, as before. No budget changed.
- Proof (old = main d4c9183): tests (two mornings over 40 companies with every kind of answer, finishing in a shuffled
  order: 8 at a time leaves the same kv, alerts and problems as one at a time; 8 reads overlap; the pages read are
  always the first in line), the full suite (2,436 passed); three replayed mornings of Nov 17's Chrome recording PASS
  with nothing exempt (the same answers give the same results). Live, on a copy of the database with every page a
  morning reads made due and robots.txt fetched fresh: the 198's round read 160 of its 165 pages in 51 s (budget 180),
  the added round 190 of 196 in 159 s (budget 240, Washington Post's timeout the last to end); the other 11 were not
  due (refused pages wait a week). No Chrome or profile left.
- The 215 alerts clear by themselves (rule `dark`: the page answers again) with the next morning's scan.

## 2026-11-18: the morning check of runs 33 and 35 (Workday through Chrome), and three fixes

- Run 33 (08:32 to 09:36 local): 104 of 104 Workday companies read whole, Citadel's three checks read through
  Chrome, every company but Qualcomm clean. Run 34 was stopped 16 s in (its row stays `running`; run 35 removed its
  Chrome profile). Run 35 (10:23 to 11:21): every late check ran in both rounds (346 careers pages and 472 backup
  checks answered today); the 209 `check gone dark` alerts of run 33 resolved. Weekly full reads done: NVIDIA's (the
  first since Nov 7), Target's, Walmart's, T-Mobile's alumni site. No Chrome or profile left.
- Run 33's morning email was 125 KB of HTML (Gmail clips past about 102 KB): 76.5 KB its 50 surest roles (93 new, the
  refused mornings' roles among them), 26.2 KB its 221 open alerts (the gone-dark ones), 16.1 KB 36 untracked roles.
  Run 35's was 62 KB. Left to the user (the open-alert list has no cap).
- Alerts left open, explained: Rocket's and Yelp's Phenom copies (`board empty`, 1 job each to 0: while Workday
  refused, the copies stood in; read whole again, they dedupe away); Target's weekly full read found 2 matching roles
  its daily student slice doesn't list (`posting elsewhere?`, as designed); Akuna's three gone-dark backup checks
  (open since Nov 12).
- Fixes (4ccfbe5):
  - Qualcomm (batch 5): its walk fell short of its total on 4 of its first 6 reads (up to 3.3%, postings moving during
    a 3.5-minute walk). Its 'Intern' seniority filter (114 roles, 12 requests) is now read in full first on every
    poll, as Microsoft's, and count_tolerance 0.04, as Autodesk's. Live verify: 2,020 jobs, 119 student roles.
  - Cisco (the 198): 5 postings without a link on both reads of run 35, its first such alert: `unlinked_ok: 50`
    (the user's rule of 2026-11-12). Visa listed 6 on one read of run 35, but its retry was clean: no alert, no change.
  - The program-page check (N) leaves out the page of a job InternWatch already stores: Cox's and Wells Fargo's job
    sitemaps list every job page, and 7 of the 15 `new page` alerts ever raised were such pages of stored apprentice
    and program roles (Cox 2, Wells Fargo 5, all still open); the other 8 (Citadel Securities' programs, OpenAI) are
    unchanged by the rule.
  - Proof (old = main ee445be): golden PASS. Three replayed mornings of Nov 17's Chrome recording, strict: every
    difference is Qualcomm's (its new first request, the Intern filter, isn't in the recording, so its replayed check
    fails: with its requests left out, both rounds' requests are the same, in order) or the intended one: the 6 Cox
    and Wells Fargo job-page alerts are not raised, with their counts, links and keys. Tests: a stored job's page
    is no news, an unread one still is; the full suite passes.
- Reverted the same day at the user's request: the Cisco fix (`unlinked_ok` removed; its list, cassette, verify
  entry and coverage row back to before 4ccfbe5) and the program-page fix (`stored_job_page`, its test and README
  line). Qualcomm's fix stays.

## Batch 6: 7 companies on 5 new readers, and the campus sites of Bank of America and Morgan Stanley (branch stage2-batch6)

ADP, Best Buy, Costco, NetApp, Paramount, Qorvo, Sandisk; Bank of America and Morgan Stanley (live since batches 4 and
3) gain their Oleeo campus sites as a last source.

- New readers (src/internwatch/adapters/, tests/test_batch6_readers.py, 22 tests on edited recordings):
  - `successfactors` {host}: SAP SuccessFactors search pages, 25 jobs a page, table or tile layout, the page's own
    total checked (NetApp 332, Paramount 199, Qorvo 8). A place "City, [State,] code, postal code" loses its postal
    code and a country code with no state is written out ("Dusseldorf, DE" read as Delaware before); a list row's
    "+1 more" stays as "+1 more" (unsure, not rejected) until the job's page gives every place.
  - `taleo_tbe` {server, dc, org, cws}: a Taleo Business Edition RSS feed (Costco's IT jobs, 16 on Nov 18; its 25
    Costco Digital Services interns of Nov 9 have closed: "This job has moved or is no longer available"). The
    server is shared by every TBE site there, so it is not named `host` (no URL marker, no system identity): the site
    is `org=costco&cws=41` (match_urls) and `taleo_tbe:cws=41,org=costco` (moves.system_key_v2).
  - `oleeo` {host, feeds | pages}: Bank of America's four Atom feeds (20 entries, 17 programs and events) and Morgan
    Stanley's two pages (68 programs; its feeds answer 404), at the 10 s robots.txt asks for.
  - `job_sitemap` {sitemap, job_url, job_page}: Sandisk (523 job pages; its search page needs scripts and styles
    robots.txt closes, so it can't be rendered or counted) and ADP (855 jobs, each under ~20 language addresses, 183
    of them with 16-digit ids). Titles from the addresses; Sandisk's new student roles are read from their own page
    (JSON-LD title and date, City / State / Country). (`detail` was the first name of that setting: build_config.py
    drops a setting named so, and the reader never saw it.)
  - `servicenow` {host, portal, page, widget}: Best Buy's portal page (for its guest token), then the call the page
    makes to list its jobs (`update_data`, `getAll`): 1,740 jobs, exactly the requisitions of its SEO sitemap.
  - `jibe` gains `queries` (off unless set; the 198's Jibe recordings replay the same): Costco's warehouse site
    (19,304 jobs, 17,434 in its warehouses and 964 in its depots) is read for its other categories (70) and an
    "intern" search (2), each to its end. No weekly whole read: 194 pages at its 5 s, and Stage 1's walk didn't hold
    together (5,106 of 18,692).
- Every site read live on Nov 18 through the project's checkers (read_results_extra.json). Page counts: the sites' own
  totals (SuccessFactors, Best Buy, Costco's two listings, its IT site's search pages: 16 = the feed); Sandisk and ADP
  can't be counted by a script (NOT_COUNTED). verify: all 9 match or are explained.
- Lists and pages (listcheck): SimplifyJobs still links Sandisk's former SmartRecruiters company: recorded as a copy of
  its Avature site (mirrors.yaml). 0 unknown systems after that.
- Backup checks: NetApp's and ADP's careers pages refuse scripts (liveness.blocked: 66): NetApp's archive.org copies,
  ADP's program pages (its jobs sitemap and adp.com's). ADP's own job list is its read itself, so it isn't read twice
  (stage2_batch.py skips a job list the read already is).
- UNDERCLASSMEN.md: none of the 7 has a freshman/sophomore program (358 companies with none).
- [x] tests pass
- [x] live go-live morning recorded on a copy of the database (morning-2026-11-18-batch6: run 36, 433 checked, 0
      failed, 7 seeded, 6,689 exchanges, 36.7 min). Batch 6's checks: 34 requests, NetApp the longest (13 s); the
      banks' Oleeo sources 6 more. "Now watching" 35 roles (ADP 5, Costco 2, NetApp 7, Qorvo 6, Sandisk 15). "Already
      open": Morgan Stanley's 4 matching programs (a new source's first answer). Re-match: Costco's 8 and Qorvo's 50
      stored rows given to them as known (SimplifyJobs no longer lists them open; a Qorvo one's page says "Sorry, this
      position has been filled"): nothing pending, no possible miss. Alerts, none batch 6's: Copart's Workday listed 3
      postings without a link (`shape`, its first such case), and Walmart's weekly read of run 35 confirmed 3 roles its
      student read doesn't list (`posting elsewhere?`: a Canadian optician student, two "2026 Intern Conversion"
      offers Stage 1 noted): both expected in the next real morning too
- [x] golden.py against main (1f29e2c): PASS (850 cassette runs of the companies already live identical, 202,804
      filter verdicts, 41,394 matches, 104 Workday files; 171 rows go to batch 6's companies)
- [x] three mornings replayed (proof-a5b2eed, old = main 1f29e2c; M2_NEW stripe;databricks;openai;walmart;costco;
      netapp;sandisk, M2_FAIL figma;target;best-buy;qorvo; compare given batch 6's 7 and the two banks): everything
      the same apart from what the batch adds (7 more checked, their injected failures and roles, "4 already open" in
      the subject). The compare's one flag, on all three mornings: four groups of alerts raised before the recording
      (Nov 14, 16, 17, 18) where a bank's alert is numbered before another added company's. The banks went live in
      batches 3 and 4, so their alerts sit among the added round's; identical in old and new, and no alert of the 198
      is numbered after one of them

## 2026-11-19: batch 6's go-live (run 36), careers pages through Chrome, and batch 7's final pass

- Run 36 (07:55 to 08:34 local, 38.3 min: the original companies 21.1, the added round 17.2): 432 checked, 0 failed,
  76 new matches, 7 seeded. No Chrome or profile left.
  - "Now watching" 38 roles (ADP 5, Costco 2, NetApp 9, Qorvo 6, Sandisk 16): the recording's 35 and 3 posted since
    (NetApp's two "Emerging Talent - Software Engineer" roles, Sandisk's "Product Development Engineer University
    Recruitment"). "Already open": Morgan Stanley's 4 Oleeo programs, as recorded. Morgan Stanley's 4 new roles are
    other postings (its private Workday site's "Intern" roles).
  - Re-match: 65 rows given a company in the added round's cross-check: Costco's 8 and Qorvo's 50, as known
    (baseline), as in the dry run, and 7 rows first seen today at earlier batches' companies (found or abroad). No
    possible miss.
  - HEALTH: Walmart's 3 `posting elsewhere?`, as predicted. Copart's predicted `shape` didn't come (its Workday no
    longer lists postings without a link). 3 `new page` alerts for job pages in sitemaps (Box, Intuitive Surgical,
    Wells Fargo: the kind the reverted stored-job skip left out); the user dismissed them. Cisco's and Qualcomm's
    Nov 18 `shape` alerts resolved.
  - The user reverted on Nov 18 (2d8d83d) Cisco's `unlinked_ok` and the program-page check's stored-job skip,
    keeping Qualcomm's fix. Not redone; fixes that quiet an alert are asked first from now on.
- Gap: Paramount's careers page (page scan) and ADP's adp.com sitemap (its program pages) answered 200 on Nov 18 and
  403 to scripts today; Chrome read both whole. Neither would have alerted: a page that never answered is no news,
  and ADP's program check counts as answered when one of its two lists answers.
- CLAUDE.md's rule (a page a Cloudflare-style guard refuses is first tried through Chrome) had not been applied to
  the pages refused before it existed. One Chrome read (`Http.request(browser=True)`, robots.txt first) of every page
  refused lately: 84 pages (16 of the page scan, 66 of the blocked companies' page check, ADP's sitemap); 69 answered
  with the page itself (median 2.7 s, 13.4 s at most), 11 refused even Chrome (403 after ~47 s of retries:
  AllTrails, Dropbox, Fidelity, GM, Nutanix, Pinterest, SeatGeek, ServiceNow, Uber, Zocdoc; Analog Devices, whose
  robots.txt a script can't reach), 4 closed by robots.txt (Fortinet, Goldman's campus page, SAS, ZipRecruiter). A
  first try through a `browser` host group (fetch() from a tab) was stopped part way: it reads by host, and most of
  these hosts also serve script reads that work (Akamai's and Rocket's feeds, ADP's job sitemap, several sitemaps).
- The user's choice: both the original companies' 28 pages and the added companies' 41 (69, about 3 more minutes a
  morning). `liveness.chrome_pages` lists them by URL; `liveness.get_page` reads a listed URL with browser=True (no
  headers: Chrome sends its own) and every other as before, in the page scan (read_pages) and moves.py's P
  (check_pages) and N (page_list). The added round's backup-check budget goes from 150 to 300 s (its checks took ~40
  s today; its 29 Chrome pages add ~80 s). A page that waits out a refusal is tried at its next weekly turn, so the
  last of them are read through Chrome by Nov 26.
- Batch 7 (final pass): README's run time (about 40 min; 15 to 20 more on a weekly full read morning), the Chrome
  pages in README, UNDERCLASSMEN.md's 358 checked. Citadel's three checkers verified again (through Chrome since Nov
  17: 66 jobs against the page's 63, 79 against 79, 13 programs against 11): COVERAGE.md now 432 verified, 1 blocked.
- [x] tests pass (new: a listed page is read with browser=True and every other as before, in the page scan and in P
      and N; every listed URL is a page some check reads)
- [x] golden.py against main (2d8d83d): PASS (864 cassette runs, 210,363 filter verdicts, 41,441 matches, 105
      Workday files; nothing given to another company)
- [x] three mornings replayed (proof-2d8d83d of morning-2026-11-18-batch6, old = main 2d8d83d; M2_NEW
      stripe;openai;netapp;paramount, M2_FAIL figma;box; compared strictly, no company exempted): PASS on all three.
      The recording's answers for these pages are its script answers, so a replay can't show Chrome's: the tests and
      the Nov 19 probe do. The next real morning is the live check (16 page-scan pages, 52 P pages and ADP's sitemap
      read through Chrome as each comes due; no first look alerts).
