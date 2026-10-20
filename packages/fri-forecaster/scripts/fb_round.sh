#!/usr/bin/env bash
# One ForecastBench round, unattended: wait for the question set, run every
# member (research and no-research), retry what failed, build the arms.
#
#   scripts/fb_round.sh 2026-10-11                 # the real round
#   SAMPLE=8 scripts/fb_round.sh 2026-09-27 rehearsal   # a cheap end-to-end check
#
# The machine's settings come from ~/.config/fri-forecaster/round.env (or
# $FORECASTER_ROUND_ENV), sourced with every variable exported; see
# examples/round.env.example. The team name (FB_ORG) and the name registry
# (FORECASTER_NAMES) are private: they live there, never in the repo. API keys
# only, from FORECASTER_ENV_FILE: pi gets its own agent dir, never a login.
# Writes $ROUNDS_DIR/<due>[-<tag>]/ and a one-screen summary.txt there.
set -uo pipefail

DUE="$1"; TAG="${2:-}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
CONF="${FORECASTER_ROUND_ENV:-$HOME/.config/fri-forecaster/round.env}"
if [[ -f "$CONF" ]]; then set -a; source "$CONF"; set +a; fi
: "${FB_ORG:?set FB_ORG (the ForecastBench team name) in $CONF}"
ROOT="${ROUNDS_DIR:-$HERE/rounds}/$DUE${TAG:+-$TAG}"
PY="${PY:-$HERE/.venv/bin/python}"
SAMPLE="${SAMPLE:-}"
WORKERS="${WORKERS:-3}"
WAIT_UNTIL="${WAIT_UNTIL:-${DUE}T08:00:00Z}"    # give up waiting for the set after this

export FORECASTER_ENV_FILE="${FORECASTER_ENV_FILE:-$HOME/.config/fri-forecaster/env}"
export PI_CODING_AGENT_DIR="${PI_CODING_AGENT_DIR:-$HOME/.config/fri-forecaster/pi-agent}"
mkdir -p "$ROOT/logs" "$PI_CODING_AGENT_DIR"

# The submissions, in set-number order, are the registry's conditions.
SETS=($("$PY" -m fri_forecaster.names conditions)) || exit 3

log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$ROOT/logs/round.log"; }

QSET="$DUE-llm.json"
URL="https://raw.githubusercontent.com/forecastingresearch/forecastbench-datasets/main/datasets/question_sets/$QSET"
log "round $DUE${TAG:+ ($TAG)} -> $ROOT; waiting for $QSET"
until curl -fsI "$URL" >/dev/null 2>&1; do
  if [[ "$(date -u +%FT%TZ)" > "$WAIT_UNTIL" ]]; then log "gave up: $QSET not published by $WAIT_UNTIL"; exit 2; fi
  sleep 120
done
log "question set is up"

# The panel: the models this machine can run, best by ECI first, as the hook
# `panel_members` prints them (round.env; `<Epoch name> TAB <pi id> TAB <lab>`
# per line; AIRO's `python -m redlines.registry` is one). names.py registers
# the next place for a condition whose members are not the panel's top N or
# whose code drifted, so a round never runs a stale ensemble and never waits
# for a hand step. Without a hook the ranking is Epoch's published index,
# names only: a moved top N is then logged, not registered.
PANEL="$(declare -F panel_members >/dev/null && panel_members 2>>"$ROOT/logs/round.log" \
         || "$PY" -m fri_forecaster.eci --fetch --names 2>/dev/null)"
SYNC_NOTE="$("$PY" -m fri_forecaster.names sync <<< "$PANEL")" || { log "names sync failed: $SYNC_NOTE"; exit 3; }
while read -r line; do log "$line"; done <<< "$SYNC_NOTE"
for c in "${SETS[@]}"; do "$PY" -m fri_forecaster.names current "$c" >/dev/null || exit 3; done

run_member() {  # a names.py member spec: MODEL@THINKING,research|noresearch
  local spec="$1" model thinking flag
  model="${spec%%@*}"; thinking="${spec#*@}"; thinking="${thinking%%,*}"; flag="${spec##*,}"
  local extra=(); [[ "$flag" == noresearch ]] && extra=(--no-research)
  "$PY" -u -m fri_forecaster.forecastbench run --root "$ROOT" --question-set "$QSET" --model "$model" \
      --thinking "$thinking" --workers "$WORKERS" ${SAMPLE:+--sample "$SAMPLE"} ${extra[@]+"${extra[@]}"} \
      >> "$ROOT/logs/$(echo "$model-$flag" | tr '/' '_').log" 2>&1
  log "$spec exited $?"
}

# The first call writes question_set.json; the rest must not race it.
"$PY" -c "from fri_forecaster.forecastbench import load_question_set; import json; json.dump(load_question_set('$QSET'), open('$ROOT/question_set.json','w'))" \
  || { log "could not fetch $QSET"; exit 2; }

for pass in 1 2; do                         # pass 2 resumes whatever pass 1 left incomplete
  # every member of every set, each run once (sets may share members)
  for flag in research noresearch; do
    log "pass $pass: $flag members"
    for spec in $(for c in "${SETS[@]}"; do "$PY" -m fri_forecaster.names members "$c"; done | grep ",$flag\$" | sort -u); do
      run_member "$spec" &
    done; wait
  done
done

build() {  # set number, name, members...   (org and model_organization: $FB_ORG)
  local n="$1" name="$2"; shift 2
  local args=(); for m in "$@"; do args+=(--member "$m"); done
  "$PY" -m fri_forecaster.forecastbench build --root "$ROOT" --set-number "$n" --name "$name" \
      --org "$FB_ORG" "${args[@]}" >> "$ROOT/logs/build.log" 2>&1
  log "set $n ($name): build exited $? (0 = ready to upload)"
}
n=0
for c in "${SETS[@]}"; do
  n=$((n + 1))
  build "$n" "$("$PY" -m fri_forecaster.names current "$c")" $("$PY" -m fri_forecaster.names members "$c")
done

{ echo "ForecastBench round $DUE${TAG:+ ($TAG)} on $(hostname), $(date -u +%FT%TZ)"
  echo "$SYNC_NOTE"
  grep -h "complete\|ready\|NOT READY\|forecasts from" "$ROOT/logs/build.log"
  echo; echo "API cost by member:"
  for f in "$ROOT"/members/*/results.jsonl; do
    printf '  %-55s $%s\n' "$(basename "$(dirname "$f")")" \
      "$("$PY" -c "import json,sys; print(round(sum(json.loads(l)['usage'].get('cost_usd') or 0 for l in open(sys.argv[1]) if l.strip()),2))" "$f")"
  done
  echo; ls "$ROOT"/*.json | grep -v question_set
} > "$ROOT/summary.txt"
log "done"; cat "$ROOT/summary.txt"
