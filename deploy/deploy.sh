#!/usr/bin/env bash
# One-command deploy to the Oracle Cloud machine:   ./deploy/deploy.sh
# Reads the SSH details from .env, copies the project, installs Python + dependencies, installs the systemd
# timer, does the first (seeding) run, sends a test health alert and starts the schedule. Safe to re-run
# after any change (config edits, new companies, code updates): it updates in place and keeps the database.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "missing .env (copy .env.example to .env and fill it in)"; exit 1; }
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
need ORACLE_SSH_HOST "public IP or hostname of the Oracle VM"
need ORACLE_SSH_USER "usually ubuntu"
need ORACLE_SSH_KEY "path to the SSH private key for the VM"
need SMTP_USER "your Gmail address"
need SMTP_PASSWORD "a Gmail app password"
need HEALTHCHECKS_PING_URL "ping URL of your healthchecks.io check"
if grep -q '<YOUR EMAIL HERE>' config/settings.yaml; then
  echo "  set email.to in config/settings.yaml (where the emails go)"; fail=1
fi
[ "$fail" = 0 ] || { echo "fix the items above, then run ./deploy/deploy.sh again"; exit 1; }

KEY="${ORACLE_SSH_KEY/#\~/$HOME}"
PORT="${ORACLE_SSH_PORT:-22}"
TARGET="${ORACLE_SSH_USER}@${ORACLE_SSH_HOST}"
APP_DIR="${REMOTE_APP_DIR:-/home/${ORACLE_SSH_USER}/internwatch}"
SSH=(ssh -i "$KEY" -p "$PORT" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30)

echo "==> copying the project to ${TARGET}:${APP_DIR}"
"${SSH[@]}" "$TARGET" "mkdir -p '$APP_DIR'"
rsync -az --delete -e "ssh -i $KEY -p $PORT -o StrictHostKeyChecking=accept-new" \
  --exclude '.venv/' --exclude 'data/' --exclude '.git/' --exclude '__pycache__/' --exclude '*.egg-info/' \
  --exclude '.pytest_cache/' --exclude 'discovery/captures/' --exclude 'discovery/capture_run.log' \
  ./ "$TARGET:$APP_DIR/"
"${SSH[@]}" "$TARGET" "chmod 600 '$APP_DIR/.env'"

echo "==> setting up the server"
"${SSH[@]}" "$TARGET" "bash '$APP_DIR/deploy/remote_setup.sh' '$APP_DIR'"

cat <<MSG

Deployed. InternWatch now runs every 15 minutes on ${ORACLE_SSH_HOST}.
  logs:     ssh -i $KEY $TARGET 'journalctl -u internwatch -n 100 --no-pager'
  status:   ssh -i $KEY $TARGET 'cd $APP_DIR && .venv/bin/internwatch status'
  update:   ./deploy/deploy.sh   (after editing config/companies.yaml, filters.yaml or the code)
MSG
