#!/usr/bin/env bash
# One ForecastBench round, unattended: wait for the question set, run every
# condition's members, retry what failed, build the sets to upload.
#
#   scripts/fb_round.sh 2026-10-11                 # the real round
#   SAMPLE=8 scripts/fb_round.sh 2026-09-27 rehearsal   # a cheap end-to-end check
#
# The machine's settings come from ~/.config/fri-forecaster/round.env (or
# $FORECASTER_ROUND_ENV), sourced with every variable exported; see
# examples/round.env.example. The team's names (FB_ORG, the anonymous one every
# set goes up under; FB_PUBLIC_ORG, its own, for the one condition the registry
# marks public) and the name registry (FORECASTER_NAMES) are private: they live
# there, never in the repo. API keys only, from FORECASTER_ENV_FILE: pi gets
# its own agent dir, never a login.
# Writes $ROUNDS_DIR/<due>[-<tag>]/ and a one-screen summary.txt there.
#
# The conditions run in the registry's order, the submitted ones first, each
# built as soon as its members are in: put the one that matters most first, so
# a round that runs out of day has it. A second pass asks again what the first
# left unanswered and builds each set for good.
set -uo pipefail

DUE="$1"; TAG="${2:-}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
CONF="${FORECASTER_ROUND_ENV:-$HOME/.config/fri-forecaster/round.env}"
if [[ -f "$CONF" ]]; then set -a; source "$CONF"; set +a; fi
: "${FB_ORG:?set FB_ORG (the ForecastBench team name for anonymous sets, Anonymous N) in $CONF}"
ROOT="${ROUNDS_DIR:-$HERE/rounds}/$DUE${TAG:+-$TAG}"
PY="${PY:-$HERE/../../.venv/bin/python}"
SAMPLE="${SAMPLE:-}"
CALLS="${CALLS:-12}"                            # pi calls at once, shared by the members that run together
WAIT_UNTIL="${WAIT_UNTIL:-${DUE}T08:00:00Z}"    # give up waiting for the set after this

export FORECASTER_ENV_FILE="${FORECASTER_ENV_FILE:-$HOME/.config/fri-forecaster/env}"
export PI_CODING_AGENT_DIR="${PI_CODING_AGENT_DIR:-$HOME/.config/fri-forecaster/pi-agent}"
mkdir -p "$ROOT/logs" "$PI_CODING_AGENT_DIR"
rm -f "$ROOT/logs/paged"

# The submissions, in set-number order, are the registry's submitted
# conditions; the others (OTHERS) only run, for scoring afterwards.
SETS=($("$PY" -m forecastbench.names conditions)) || exit 3
ALL=($("$PY" -m forecastbench.names conditions --all)) || exit 3
OTHERS=(); for c in "${ALL[@]}"; do [[ " ${SETS[*]} " == *" $c "* ]] || OTHERS+=("$c"); done
PUBLIC="$("$PY" -m forecastbench.names public)" || exit 3
if [[ -n "$PUBLIC" && -z "${FB_PUBLIC_ORG:-}" ]]; then
  echo "the registry submits $PUBLIC under the team's own name: set FB_PUBLIC_ORG in $CONF" >&2; exit 3
fi

log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$ROOT/logs/round.log"; }
page() {  # MESSAGE: "run FAILED" now, for what cannot wait for the round's end (fri_forecaster.alert)
  "$PY" -m fri_forecaster.alert send --deployment forecastbench --severity page --title "run FAILED" \
    --log "$ROOT/logs/round.log" "$DUE: $1" 2>&1 | tee -a "$ROOT/logs/round.log" >&2
  : > "$ROOT/logs/paged"   # fb_cron.sh says nothing more about a round that already paged
}

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
# A hook that fails stops the round (a top model it cannot run, say): nothing
# stands in for the panel.
if declare -F panel_members >/dev/null; then
  PANEL="$(panel_members 2>>"$ROOT/logs/round.log")" \
    || { log "FATAL: the panel could not be read (panel_members failed; see above): the round does not run"; exit 3; }
else
  PANEL="$("$PY" -m fri_forecaster.eci --fetch --names 2>/dev/null)"
fi
SYNC_NOTE="$("$PY" -m forecastbench.names sync <<< "$PANEL")" || { log "names sync failed: $SYNC_NOTE"; exit 3; }
while read -r line; do log "$line"; done <<< "$SYNC_NOTE"
for c in "${ALL[@]}"; do "$PY" -m forecastbench.names current "$c" >/dev/null || exit 3; done

run_member() {  # a names.py member spec, MODEL@THINKING,MODE (research, noresearch, airo-<condition>); its calls at once
  local spec="$1" workers="$2" model thinking mode rc
  model="${spec%%@*}"; thinking="${spec#*@}"; thinking="${thinking%%,*}"; mode="${spec##*,}"
  local extra=()
  case "$mode" in
    noresearch) extra=(--no-research) ;;
    airo-*)     extra=(--airo "${mode#airo-}") ;;
  esac
  "$PY" -u -m forecastbench run --root "$ROOT" --question-set "$QSET" --model "$model" \
      --thinking "$thinking" --workers "$workers" ${SAMPLE:+--sample "$SAMPLE"} ${TIMEOUT:+--timeout "$TIMEOUT"} \
      ${extra[@]+"${extra[@]}"} >> "$ROOT/logs/$(echo "$model-$mode" | tr '/' '_').log" 2>&1
  rc=$?
  log "$spec exited $rc (0 = complete, 1 = short of 95%, 2 = its key was refused)"
  # A refused key takes the provider's every member with it, and only a person
  # can mend it: say so now, once per provider, while the day is still long.
  if [[ $rc == 2 ]] && ( set -o noclobber; : > "$ROOT/logs/key-refused-${model%%/*}" ) 2>/dev/null; then
    page "${model%%/*}'s API key was refused: its members are not running. Fix the keys file ($FORECASTER_ENV_FILE) and rerun scripts/fb_round.sh $DUE${TAG:+ $TAG}; what is done is kept."
  fi
}

# The first call writes question_set.json; the rest must not race it.
"$PY" -c "from forecastbench import load_question_set; import json; json.dump(load_question_set('$QSET'), open('$ROOT/question_set.json','w'))" \
  || { log "could not fetch $QSET"; exit 2; }

build() {  # pass, set number, condition: organization and model_organization are the team's own name
  local pass="$1" n="$2" c="$3" name org rc   # for the public condition, its anonymous one for the rest
  name="$("$PY" -m forecastbench.names current "$c")"
  org="$FB_ORG"; [[ "$c" == "$PUBLIC" ]] && org="$FB_PUBLIC_ORG"
  local args=(); for m in $("$PY" -m forecastbench.names members "$c"); do args+=(--member "$m"); done
  "$PY" -m forecastbench build --root "$ROOT" --set-number "$n" --name "$name" \
      --org "$org" "${args[@]}" > "$ROOT/logs/build-$n.log" 2>&1
  rc=$?
  if [[ $pass == 2 && $rc != 0 ]]; then build_failed=1; fi
  # Only the last pass's line reads "build exited": fb_cron.sh and AIRO's
  # scheduler count those, one per set.
  if [[ $pass == 2 ]]; then log "set $n ($name, as $org): build exited $rc (0 = ready to upload)"
  else log "set $n ($name, as $org): after pass 1, build $rc (0 = ready to upload; pass 2 builds it again)"; fi
}

build_failed=0
rm -f "$ROOT"/logs/key-refused-*
for pass in 1 2; do                         # pass 2 resumes whatever pass 1 left incomplete
  declare -A ran=()                         # a member is run once a pass (conditions share members)
  n=0
  for c in "${SETS[@]}" ${OTHERS[@]+"${OTHERS[@]}"}; do
    todo=(); for spec in $("$PY" -m forecastbench.names members "$c"); do
      [[ -n "${ran[$spec]:-}" ]] || { todo+=("$spec"); ran[$spec]=1; }
    done
    # CALLS is the machine's (a pi process is some 130 MB) and the providers'
    # rate limits': the members of one condition share it evenly, and when
    # it does not go round (16 members, 24 calls) they take turns, two calls
    # each, rather than leave a third of it idle.
    k=${#todo[@]}
    workers=$(( k ? (CALLS + k - 1) / k : 1 )); at_once=$(( CALLS / workers )); (( at_once >= 1 )) || at_once=1
    if (( k )); then log "pass $pass: $c, $k member(s) to run, $workers call(s) at once each, $at_once member(s) at a time"
    else log "pass $pass: $c, its members have run"; fi
    for spec in ${todo[@]+"${todo[@]}"}; do
      while (( $(jobs -rp | wc -l) >= at_once )); do wait -n; done
      run_member "$spec" "$workers" &
    done; wait
    if [[ " ${SETS[*]} " == *" $c "* ]]; then n=$((n + 1)); build "$pass" "$n" "$c"; fi
  done
done

{ echo "ForecastBench round $DUE${TAG:+ ($TAG)} on $(hostname), $(date -u +%FT%TZ)"
  echo "$SYNC_NOTE"
  cat "$ROOT"/logs/build-[0-9]*.log | grep -h "complete\|ready\|NOT READY\|SHORT MEMBER\|forecasts from"
  [[ ${#OTHERS[@]} == 0 ]] || echo "run and kept, not submitted: ${OTHERS[*]}"
  echo; echo "API cost by member:"
  for f in "$ROOT"/members/*/results.jsonl; do
    printf '  %-55s $%s\n' "$(basename "$(dirname "$f")")" \
      "$("$PY" -c "import json,sys; print(round(sum(json.loads(l)['usage'].get('cost_usd') or 0 for l in open(sys.argv[1]) if l.strip()),2))" "$f")"
  done
  echo; ls "$ROOT"/*.json | grep -v question_set
} > "$ROOT/summary.txt"
log "done"; cat "$ROOT/summary.txt"
exit "$build_failed"
