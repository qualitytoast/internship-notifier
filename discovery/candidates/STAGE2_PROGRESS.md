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
- [ ] merge, push; the next real morning is batch 1's go-live

Corrections to STAGE1_REPORT.md's day-one alerts: `board quiet` needs no history, since the rule also reads a
board's own posting dates (newest > 45 days old alerts on the first read). Measured from Stage 1's reads, this
reproduces batch 1's 6 exactly; later batches: Eventual (Ashby, newest 47 days on Nov 10) and Northwestern Mutual's
SmartRecruiters page (6 evergreen postings dated 2015, 63 undated: a misleading alert, decide in batch 3). Alert
numbers: a run records the 198's alerts first, so on its own morning each gets the number the old code gives it; on
later mornings the added companies' earlier alerts have taken numbers, so the 198's next ones are higher than the
old code's (the replay compares alerts by key).

Every batch from now on: compare the recorded go-live morning's alerts with the batch's predicted day-one alerts
before replaying.
