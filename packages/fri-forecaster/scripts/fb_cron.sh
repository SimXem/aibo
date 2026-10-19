#!/usr/bin/env bash
# cron's entry for one ForecastBench round: scripts/fb_round.sh <due>, then one
# ntfy line so someone uploads the sets before the due date ends (UTC).
#
#   5 0 25 10 * /usr/bin/flock -n /tmp/fb-round.lock <checkout>/scripts/fb_cron.sh 2026-10-25
#
# Settings come from round.env like the round's (see examples/round.env.example);
# NTFY_TOPIC there, or in the keys env file, names the topic to ping (none: no ping).
# Output goes to $ROUNDS_DIR/<due>/logs/cron.out.
set -uo pipefail

DUE="$1"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
CONF="${FORECASTER_ROUND_ENV:-$HOME/.config/fri-forecaster/round.env}"
if [[ -f "$CONF" ]]; then set -a; source "$CONF"; set +a; fi
ROOT="${ROUNDS_DIR:-$HERE/rounds}/$DUE"
PY="${PY:-$HERE/.venv/bin/python}"
mkdir -p "$ROOT/logs"

"$HERE/scripts/fb_round.sh" "$DUE" >> "$ROOT/logs/cron.out" 2>&1
rc=$?
sets="$("$PY" -m fri_forecaster.names conditions 2>/dev/null | wc -l | tr -d ' ')"
ready="$(grep -c "build exited 0" "$ROOT/logs/round.log" 2>/dev/null)"
topic="${NTFY_TOPIC:-$(sed -n 's/^NTFY_TOPIC=//p' "${FORECASTER_ENV_FILE:-$HOME/.config/fri-forecaster/env}" 2>/dev/null | tr -d "\"'")}"
if [[ -n "$topic" ]]; then
  if [[ "$rc" == 0 && "${ready:-0}" == "$sets" ]]; then prio=default; else prio=high; fi
  curl -fsS -m 20 -H "Title: ForecastBench $DUE" -H "Priority: $prio" \
    --data-binary "round exited $rc, ${ready:-0}/$sets sets ready to upload: $ROOT on $(hostname). Upload by 23:59 UTC." \
    "https://ntfy.sh/$topic" >/dev/null || echo "WARN: ntfy push failed" >> "$ROOT/logs/cron.out"
fi
exit $rc
