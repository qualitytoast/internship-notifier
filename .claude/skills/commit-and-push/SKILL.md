---
name: commit-and-push
description: Commit and push after every change to this project. Use as soon as a change (code, config, docs, tests) is finished, before reporting back.
---

# Commit and push after every change

After each change you make to this project:

1. Run `git status` and check what changed. Stage only the files that belong to the change. `.gitignore`
   keeps out `.env`, `data/`, `.venv/` and the discovery captures; never force-add those or any other
   secrets.
2. Commit with a short message, one line in the imperative, saying what you did, for example
   `Add Klaviyo campus board` or `Fix Class of 2029 being read as a term`.
3. Push to the current branch's remote with `git push`.
4. If the push fails (no remote yet, no network, rejected), say so in your reply and leave the commit in
   place. Don't force-push.

Don't commit a change that `CLAUDE.md` says needs approval first (a change that could make the filters
stricter) until it has been approved.
