#!/usr/bin/env bash
# Run InternWatch once every morning on this Mac:      ./deploy/install_mac_daily.sh [HH:MM]      (default 07:30)
#
# Checks .env and config/settings.yaml, schedules `internwatch run --daily` with launchd (a Mac that is asleep at
# that time runs it as soon as it wakes up; one that is shut down skips that morning, and the next run still
# catches everything new since the last one), then does the first run right away (about 15 minutes): it
# records every open posting and emails you one summary. Run the script again to change the time.
set -euo pipefail
cd "$(dirname "$0")/.."
APP="$(pwd)"
TIME="${1:-07:30}"
if ! [[ "$TIME" =~ ^([01]?[0-9]|2[0-3]):[0-5][0-9]$ ]]; then
  echo "time must be HH:MM in 24-hour form, e.g. 07:30"; exit 1
fi
HOUR=$((10#${TIME%%:*})); MINUTE=$((10#${TIME##*:}))

[ -f .env ] || cp .env.example .env
# read KEY=value lines literally (values may contain characters the shell would interpret)
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in ''|\#*) continue ;; esac
  key="${line%%=*}"; val="${line#*=}"
  val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
  export "$key=$val"
done < .env

fail=0
need() {  # need VAR "description"
  local v="${!1:-}"
  if [ -z "$v" ] || [[ "$v" == \<*\> ]]; then echo "  fill in $1 in .env ($2)"; fail=1; fi
}
echo "==> checking .env and config"
need SMTP_USER "your Gmail address"
need SMTP_PASSWORD "a Gmail app password from https://myaccount.google.com/apppasswords"
if grep -q '<YOUR EMAIL HERE>' config/settings.yaml; then
  echo "  set email.to in config/settings.yaml (where the emails go)"; fail=1
fi
[ "$fail" = 0 ] || { echo "fix the items above, then run ./deploy/install_mac_daily.sh again"; exit 1; }
hc="${HEALTHCHECKS_PING_URL:-}"
if [ -z "$hc" ] || [[ "$hc" == \<*\> ]]; then
  echo "  (optional) HEALTHCHECKS_PING_URL is not set, so nothing will tell you if a morning run never happens"
fi

if [ ! -x .venv/bin/internwatch ]; then
  echo "==> installing InternWatch (needs Python 3.12 or newer)"
  PY="$(command -v python3.13 || command -v python3.12 || command -v python3)"
  "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else "Python 3.12+ is needed (brew install python)")'
  "$PY" -m venv .venv
  .venv/bin/pip install -q -e ".[dev]"
fi

LABEL=com.internwatch.daily
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" data/logs
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$APP/.venv/bin/internwatch</string><string>run</string><string>--daily</string></array>
  <key>WorkingDirectory</key><string>$APP</string>
  <key>EnvironmentVariables</key><dict><key>INTERNWATCH_HOME</key><string>$APP</string></dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
  <key>StandardOutPath</key><string>$APP/data/logs/morning-run.log</string>
  <key>StandardErrorPath</key><string>$APP/data/logs/morning-run.log</string>
</dict>
</plist>
PLIST
plutil -lint "$PLIST" >/dev/null
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "==> scheduled every day at $TIME (if the Mac is asleep then, as soon as it wakes)"

if [ ! -f data/internwatch.db ]; then
  echo "==> first run now: records every open posting and emails you one summary (about 15 minutes)"
  .venv/bin/internwatch run --daily || true
  echo "==> sending a deliberate test health alert (proves alerts reach your inbox)"
  .venv/bin/internwatch alert-test || true
fi

cat <<MSG

Done. Every morning at $TIME you get one email, "[InternWatch] <date>: N new: …" (or "no new roles"),
with everything posted since the previous morning's check.
  run it now:   launchctl kickstart gui/$(id -u)/$LABEL
  its log:      $APP/data/logs/morning-run.log   (details: data/logs/internwatch.log)
  change time:  ./deploy/install_mac_daily.sh HH:MM
  stop it:      launchctl bootout gui/$(id -u)/$LABEL
MSG
