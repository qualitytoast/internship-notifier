#!/usr/bin/env bash
# Read-only audit of the disk space this project uses on this Mac. Prints one row per item; deletes nothing.
#   bash .claude/skills/audit-leftovers/audit.sh
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SLUG="$(printf '%s' "$ROOT" | tr '/' '-')"          # Claude Code's folder name for this project
TMP="${TMPDIR:-/tmp}"; TMP="${TMP%/}"
JUNK=(); OPTIONAL=()

row() {  # row CATEGORY PATH NOTE
  [ -n "$2" ] && [ -e "$2" ] || return 0
  printf '%-6s %-9s %s\n                 %s\n' "$(du -sh "$2" 2>/dev/null | cut -f1)" "$1" "$2" "$3"
  case "$1" in junk) JUNK+=("$2") ;; optional) OPTIONAL+=("$2") ;; esac
}

echo "Leftovers audit for $ROOT"
echo "keep = needed to run · junk = safe to delete · optional = only for discovery and 'internwatch add'"
echo "shared = also used by other projects · history = Claude Code's record of this project's sessions"

echo; echo "== In the project"
row keep "$ROOT/.venv" "the virtualenv that runs internwatch (includes the optional Playwright package below)"
row optional "$(ls -d "$ROOT"/.venv/lib/python*/site-packages/playwright 2>/dev/null | head -1)" \
  "Playwright package: discovery scripts and 'internwatch add' browser detection only (.venv/bin/pip uninstall -y playwright)"
row keep "$ROOT/data/internwatch.db" "the database: every job ever seen and what was emailed. Never delete"
row keep "$ROOT/data/outbox" "a copy of every email ($(ls "$ROOT/data/outbox" 2>/dev/null | wc -l | tr -d ' ') files); grows with each email, old ones can go"
row keep "$ROOT/data/logs" "logs (internwatch.log rotates at 5 x 5 MB; morning-run.log only with the launchd schedule)"
row keep "$ROOT/data/robots" "robots.txt cache"
row keep "$ROOT/.git" "git history"
row junk "$ROOT/discovery/captures" "raw page dumps from the first discovery pass (gitignored; results are in discovery/results, notes, samples)"
row junk "$ROOT/discovery/capture_run.log" "log of that discovery pass"

echo; echo "== Outside the project"
row junk "/private/tmp/claude-$(id -u)/$SLUG" "Claude Code scratch folders: database copies and backups, test runs (macOS clears /private/tmp on restart)"
for p in "$TMP"/playwright*; do row junk "$p" "temporary browser profile left by a Playwright run"; done
others="$(grep -lis playwright "$(dirname "$ROOT")"/*/requirements*.txt "$(dirname "$ROOT")"/*/pyproject.toml \
  "$(dirname "$ROOT")"/*/package.json 2>/dev/null | grep -v "^$ROOT/" | xargs -n1 dirname 2>/dev/null | xargs -n1 basename 2>/dev/null | sort -u | tr '\n' ' ')"
if [ -n "$others" ]; then pw_note="ALSO listed by other projects: $others- keep unless they no longer need it"
else pw_note="no other project in $(dirname "$ROOT") lists Playwright"; fi
row optional "$HOME/Library/Caches/ms-playwright" "Playwright browsers downloaded for discovery; $pw_note"
row shared "$HOME/Library/Caches/pip" "pip download cache for every Python project ('pip cache purge' empties it)"
row shared "$HOME/.cache/uv" "uv cache (deploy rehearsals use uv)"
row shared "$HOME/.local/share/uv/python" "Python builds installed by uv"
row shared "$TMP/pytest-of-$(id -un)" "pytest temp folders from every project (pytest keeps only the last 3 runs)"
row history "$HOME/.claude/projects/$SLUG" "Claude Code transcripts and memory for this project (needed to resume old sessions)"

echo; echo "== Schedules and containers"
if [ -e "$HOME/Library/LaunchAgents/com.internwatch.daily.plist" ]; then
  echo "launchd: com.internwatch.daily is installed, so 'run --daily' runs every morning"
  echo "         (remove: launchctl bootout gui/$(id -u)/com.internwatch.daily; rm ~/Library/LaunchAgents/com.internwatch.daily.plist)"
else echo "launchd: no InternWatch schedule"; fi
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "docker:"; { docker ps -a --format '  container {{.Names}} {{.Image}} {{.Size}}'
    docker images --format '  image {{.Repository}}:{{.Tag}} {{.Size}}'
    docker volume ls --format '  volume {{.Name}}'; } | grep -iE 'internwatch|internship' || echo "  nothing from InternWatch"
else echo "docker: not running, so images and containers can't be checked"; fi

echo; echo "== Anything else git doesn't track (check before calling it junk)"
cd "$ROOT" || exit 1
known='^(\.venv/|data/|discovery/captures/|discovery/capture_run\.log$|\.env$|.*__pycache__/$|\.pytest_cache/$|src/internwatch\.egg-info/$)'
extra="$( { git ls-files --others --ignored --exclude-standard --directory; git ls-files --others --exclude-standard; } 2>/dev/null | sort -u | grep -Ev "$known")"
if [ -n "$extra" ]; then while IFS= read -r f; do printf '%-6s %s\n' "$(du -sh "$f" 2>/dev/null | cut -f1)" "$f"; done <<< "$extra"
else echo "nothing"; fi

echo
[ ${#JUNK[@]} -gt 0 ] && echo "junk total:     $(du -shc "${JUNK[@]}" 2>/dev/null | tail -1 | cut -f1)"
[ ${#OPTIONAL[@]} -gt 0 ] && echo "optional total: $(du -shc "${OPTIONAL[@]}" 2>/dev/null | tail -1 | cut -f1)"
