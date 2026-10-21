#!/usr/bin/env bash
# Runs ON the Oracle machine (deploy.sh copies the project and calls this). Safe to run again: it upgrades in place.
set -euo pipefail
APP="$1"
USER_NAME="$(id -un)"
cd "$APP"

echo "==> installing Python 3.12 via uv (works on any Ubuntu, ARM included)"
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
"$UV" venv --python 3.12 --allow-existing .venv >/dev/null
"$UV" pip install --python .venv/bin/python -q -e ".[dev]"

echo "==> running the test suite on the server (offline)"
.venv/bin/python -m pytest -q -p no:cacheprovider tests | tail -3 \
  || echo "WARNING: some tests failed (see above). Deploying anyway; run the tests locally to investigate."

echo "==> installing the systemd timer (every 15 minutes)"
for unit in internwatch.service internwatch.timer; do
  sed -e "s#@USER@#${USER_NAME}#g" -e "s#@APP@#${APP}#g" "deploy/${unit}" | sudo tee "/etc/systemd/system/${unit}" >/dev/null
done
sudo systemctl daemon-reload
mkdir -p data/logs

if [ "${SKIP_FIRST_RUN:-0}" != "1" ] && [ ! -f data/internwatch.db ]; then
  echo "==> first run: records every open posting and emails one summary (takes ~15 minutes)"
  INTERNWATCH_HOME="$APP" .venv/bin/internwatch run || true
fi

echo "==> sending a deliberate test health alert (proves alerts reach your inbox)"
INTERNWATCH_HOME="$APP" .venv/bin/internwatch alert-test || true

sudo systemctl enable --now internwatch.timer
systemctl list-timers internwatch.timer --no-pager | head -3
INTERNWATCH_HOME="$APP" .venv/bin/internwatch status
