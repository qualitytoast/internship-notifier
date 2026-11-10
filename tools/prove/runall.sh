#!/usr/bin/env bash
# Three replayed mornings of one recorded daily run (tools/prove/morning.py), old code against this tree's, compared:
#   1  the recorded morning as it was
#   2  a day later: new matching roles at the companies in M2_NEW, a failure at those in M2_FAIL, every email failing
#   3  two days later, after morning 2's failed emails: what didn't go out goes out
#
#   M2_NEW="stripe;openai;newco" M2_FAIL="figma;newco2" tools/prove/runall.sh <old git ref> <recording dir> [added keys…]
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=${PY:-/Users/nathanhung/Projects/internship-notifier/.venv/bin/python}
OLD_REF=$1; REC=$2; shift 2
WORK="$REC/proof-$(git rev-parse --short HEAD)"
rm -rf "$WORK"; mkdir -p "$WORK/old"
git archive "$OLD_REF" src config | tar -x -C "$WORK/old"
for v in old new; do
  dir="$WORK/old"; [ "$v" = new ] && dir="$(pwd)"
  "$PY" -I tools/prove/morning.py replay "$dir" "$REC" "$WORK/$v-1"
  "$PY" -I tools/prove/morning.py replay "$dir" "$REC" "$WORK/$v-2" \
    "after:$WORK/$v-1,day:1,new:${M2_NEW:-},fail:${M2_FAIL:-},mailfail"
  "$PY" -I tools/prove/morning.py replay "$dir" "$REC" "$WORK/$v-3" "after:$WORK/$v-2,day:2"
done
rc=0
for m in 1 2 3; do
  echo "morning $m:"
  "$PY" -I tools/prove/morning.py compare "$WORK/old-$m" "$WORK/new-$m" "$@" || rc=1
done
exit $rc
