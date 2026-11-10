# Stage 2 progress

Branch `stage2-batch0`, worktree `../internship-notifier-batch0`. The morning run is started by hand from the main
working tree, so nothing here reaches it until the batch is proven and merged into main. Run tests here with
`PYTHONPATH=$PWD/src ../internship-notifier/.venv/bin/python -m pytest -q` (the main venv's editable install points
at the main tree's src; PYTHONPATH puts this worktree's src first).

Decisions (2026-11-09, STAGE1_REPORT.md): giant store sites read for student roles daily + a weekly full read; 12
workers in the added round; every new reader built; the subsidiaries added (Tubi pending); no "known site" setting;
Progressive through RippleMatch; DraftKings, FOX, Match Group, PrizePicks taken out (236 companies).

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
- [ ] 8. tools/prove: golden (cassettes, filters, matching, liveness functions) and replayed mornings
        (golden.py: PASS against main on 2026-11-09, twice; a live morning recorded into
        data/stage2/morning-2026-11-09 of the main tree; then runall.sh; plus a smoke replay of the added round on
        real data: data/stage2/smoke/version is this branch with stripe, figma, klaviyo marked round: added)
- [ ] 9. Test fixes: klaviyo's quiet-board test pinned to its recording date (done); the 8 drifted cassettes
        (bloomberg, visa, mongodb, electronic-arts, akuna-capital, peak6, virtu, flow-traders) re-recorded after the
        morning recording (never at the same time: same sites), with test_fixture_was_recorded_with_the_current_settings
- [ ] 10. Docs; proofs PASS; merge into main; push; then a morning run before batch 1

## How to prove a batch
- Static: `.venv/bin/python -I tools/prove/golden.py main` from the worktree (old = main, new = this tree): PASS
  means identical cassettes, filter verdicts, matching and Workday sites, apart from what goes to added companies.
- Mornings: record once with the new code (`morning.py record data/stage2/morning-<date>`, a live daily run on a
  database copy, no email, no heartbeat), then replay it through `git archive main` (old) and this tree (new):
  morning 1 as recorded; morning 2 `after:<morning 1 out>,day:1,new:<keys>,fail:<key>`; morning 3
  `after:<morning 2 out>,day:2,mailfail`; then `morning.py compare <old out> <new out> <added keys>` for each.
