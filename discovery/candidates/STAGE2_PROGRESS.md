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
