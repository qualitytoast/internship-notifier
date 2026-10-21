---
name: audit-leftovers
description: Audit the junk and disk bloat this project left on this Mac (Claude scratch copies, discovery captures, Playwright browsers, schedules, caches) and say what can be deleted. Use when asked to audit, clean up or find leftovers from this project.
---

# Audit leftovers from this project

1. Run `bash .claude/skills/audit-leftovers/audit.sh`. It is read-only. Each row is one path, its size and a
   category:
   - `keep`: needed to run
   - `junk`: safe to delete
   - `optional`: only needed for discovery or `internwatch add`
   - `shared`: other projects use it too
   - `history`: Claude Code's sessions for this project
2. Before calling anything under "Anything else git doesn't track" junk, look at what it is.
3. Report a short table: item, size, what it is, recommendation. Give the total that can be freed. Also say
   whether a launchd schedule or Docker container is still set up.
4. Delete nothing until the user has approved that specific item. Never touch other projects' files, shared
   caches (unless asked), `data/internwatch.db`, `.env` or `.git`. If the Claude scratch folder holds a database
   backup the user may still want, ask about that backup separately.
5. After approval, delete with exact commands: `rm -rf <path>`, or `.venv/bin/pip uninstall -y playwright` for
   the package. Then rerun the script and report what was freed.
