#!/usr/bin/env bash
# Scheduled forecast run. Lives on the box that serves airo.forecastingresearch.org, fired
# by cron at 12:00 UTC = 05:00 PT. WHAT RUNS ON WHICH DAY is each condition's
# `cadence` (experiments/*.toml, redlines/experiments.py; 2026-10-21): the
# published series, experiments/airo.toml, runs WEDNESDAYS AND FRIDAYS (twice
# weekly from 2026-09-16; Fridays only from 2026-08-14, Mondays before that),
# and a day with nothing due ends before anything is logged. The crontab only
# has to fire on every day any cadence names (daily covers all of them). Safe to
# run by hand: `cron_run.sh airo` runs every condition of the named
# experiments, whatever their cadence.
#
# WHY THIS EXISTS
#   Graph 1 becomes the dashboard's headline only once several months of
#   forecasts have accrued (2026-08-10 call). That is the one deliverable whose
#   cost is elapsed time rather than effort, so the job starts now — months
#   before the over-time view it feeds is due. The unified-batch cutover
#   (2026-08-14) retired the earlier series, so the Timeline panel is rebuilding
#   from one snapshot and every run from here is load-bearing.
#
# WHAT IT RUNS
#   The WHOLE question set, in one call per model (code/run_unified.py),
#   with NO relation between the questions stated in the prompt --
#   coherence is measured afterwards, never bought. The set is 37 questions in
#   5 groups (four AI incident types x 8 severity rungs, plus five
#   cross-cutting questions -- the extinction pair since 2026-09-15) over six horizons -- two of them ROLLING, so each
#   run stamps an absolute resolves_on per row. ONE call per model since
#   2026-09-02 (--repeats 1): the same-day repeats that preceded it measured a
#   re-asking spread nobody read as accuracy, and their budget went to the
#   agentic harness instead. The views draw no interval on a single-draw day.
#
# WHICH MODELS
#   THE PANEL (2026-08-28): run_unified.py --model-set defaults to eci_topk,
#   the four highest-ECI models the registry can run, re-ranked each run from
#   the newest data/epoch_capabilities_index_*.csv (redlines/eci.py). The run
#   prints the snapshot's date and age. Rows stamp panel={set,k,snapshot}. The
#   frontier five the series ran on until then are `--model-set frontier5`.
#   SINCE 2026-10-01 THE SNAPSHOT IS FETCHED HERE, before every run, from
#   Epoch's published scores (python3 -m redlines.eci --fetch), and the
#   capability scenarios are regenerated from it -- no hand step between a
#   model shipping and the panel and prompt knowing it. A new model the index
#   ranks into the panel that the registry has no row for is ADDED ON ITS OWN
#   since 2026-10-07 (redlines.autoreg: matched to its provider's API id,
#   probed with one request, recorded in data/auto_models.json) and paged once
#   as news. Only a model that cannot be added is skipped (the next runnable
#   one takes the seat) and paged as a fault; a hand row in
#   redlines/registry.py, if one is ever wanted, takes precedence.
#
# ALERTS (2026-10-01): with NTFY_TOPIC set in the env file, a failed run, a
#   failed fetch, a failed publish, a panel change and an unrunnable model at
#   the top of the index each push one line to https://ntfy.sh/$NTFY_TOPIC
#   (the ntfy app, subscribed to that topic). A finished run pushes a quiet
#   one too, so silence on a Wednesday or Friday afternoon means the box or
#   cron itself is down. The topic lives only in the env file: anyone who
#   knows it can read the channel, so messages say what failed, never data.
#
# OUTPUT
#   One dated file per run under results/runs/. Never appends to the shared
#   results/forecast_runs.jsonl: this box's checkout is rsynced from a laptop,
#   and two writers on one tracked file means a merge conflict every week.
#   redlines/runlog.py::load_runlog() reads the log and this directory.
#
#   Pull them down with:
#     rsync -avz <box>:Projects/redlines/results/runs/ results/runs/
#   and the inputs the run quoted (the fetched index and the sets built from it):
#     rsync -avz '<box>:Projects/redlines/data/epoch_capabilities_index_*.csv' data/
#     rsync -avz <box>:Projects/redlines/data/{eci_self_conditions,eci_self6mo_conditions,combined_conditions,auto_models}.json data/
#
# SETUP
#   Keys live in ~/.config/redlines/env (mode 600), one KEY=value per line:
#   ANTHROPIC / OPENAI / GEMINI / GOOGLE / XAI / TAVILY (METACULUS is no
#   longer read; the lookup left the toolset on 2026-09-02). They are
#   sourced into the environment here; redlines.llm.load_keys() reads the SAME
#   file (and never overrides a variable already set), so the run works whether
#   or not this script sourced it first.
#
#   PY just has to be an interpreter with litellm — `pip install -e '.[acquire]'`
#   in any venv. It points at the xrisk-canaries venv on this box only because
#   that is where litellm was already installed; override with REDLINES_PY.
set -euo pipefail

# The repo is wherever this script lives; PY is any interpreter with litellm
# (`pip install -e '.[acquire]'`): the repo's own venv when there is one, else
# whatever REDLINES_PY names.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -z "${REDLINES_PY:-}" ] && [ -x "$REPO/.venv/bin/python" ]; then
    REDLINES_PY="$REPO/.venv/bin/python"
fi
PY="${REDLINES_PY:-$HOME/Projects/xrisk-canaries/.venv/bin/python}"
ENVFILE="$HOME/.config/redlines/env"

# WHAT IS DUE: one line per group run_unified runs together,
# "<experiment> <publish|aside> <condition>..." -- today's by cadence, or every
# condition of the experiments named on the command line. Nothing due: done,
# quietly. Unreadable experiments: logged and paged below.
if DUE="$(cd "$REPO" && "$PY" -m redlines.experiments due "$@" 2>&1)"; then
    [ -n "$DUE" ] || exit 0
    DUE_OK=1
else
    DUE_OK=0
fi

STAMP="$(date -u +%Y-%m-%dT%H%MZ)"
LOG="$HOME/logs/forecast-$STAMP.log"
mkdir -p "$HOME/logs"

exec >>"$LOG" 2>&1
echo "=== $STAMP  scheduled run ==="

# notify TITLE MESSAGE [PRIORITY] [TAGS] -- one line to the operator's phone.
# A no-op without NTFY_TOPIC; a failed push is logged, never fatal.
notify() {
    [ -n "${NTFY_TOPIC:-}" ] || return 0
    curl -fsS -m 20 -H "Title: $1" -H "Priority: ${3:-default}" -H "Tags: ${4:-}" \
        --data-binary "$2" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null \
        || echo "WARN: ntfy push failed: $1"
}
# Any exit before the end is a failed run: page with the log's last lines.
FINISHED=0
on_exit() {
    local rc=$?
    if [ "$FINISHED" != 1 ]; then
        notify "AIRO run $STAMP FAILED" "exit $rc on $(hostname). $(grep -E 'FATAL|Error|failed|stale' "$LOG" | tail -3 | cut -c1-200)
log: $LOG" high rotating_light
    fi
}
trap on_exit EXIT

if [ ! -r "$ENVFILE" ]; then
    echo "FATAL: $ENVFILE missing or unreadable — no API keys, nothing to do."
    exit 1
fi
set -a; . "$ENVFILE"; set +a

if [ "$DUE_OK" != 1 ]; then
    echo "FATAL: experiments/ could not be read: $DUE"
    exit 1
fi
echo "due:"
echo "$DUE" | sed 's/^/  /'

cd "$REPO"

# THE ECI SNAPSHOT (2026-10-01): fetch Epoch's index, then rebuild the
# capability scenarios from it -- the frontier history the prompt quotes.
# A failed fetch keeps the previous snapshot and pages; the runner's
# preflight (code/check_eci_snapshot.py) still refuses one older than 21 days.
panel_labels() {
    "$PY" -c 'from redlines import registry; print(", ".join(m["label"] for m, _ in registry.panel()))'
}
PREV_PANEL="$(panel_labels 2>/dev/null || true)"
if ! "$PY" -m redlines.eci --fetch; then
    notify "AIRO: Epoch ECI fetch failed" "Run $STAMP goes ahead on the previous snapshot. Check https://epoch.ai/data/eci_scores.csv" high warning
fi
# NEW MODELS (2026-10-07): give a row to each model the index now ranks into
# the panel without one (redlines.autoreg), before the panel is read. A crash
# here costs only the new model's seat -- the rest of the run goes ahead, and
# the model is paged below as unrunnable.
if ! ADDED="$("$PY" -m redlines.autoreg)"; then
    echo "WARN: redlines.autoreg failed; a new model without a registry row sits this run out"
    ADDED=""
fi
if [ -n "$ADDED" ]; then
    echo "$ADDED"
    notify "AIRO: new model joins the registry" "$ADDED" default new
fi
"$PY" code/check_eci_snapshot.py --rebuild
PANEL="$(panel_labels)"
UNRUNNABLE="$("$PY" -c 'from redlines import registry; print("\n".join(w for w in registry.panel_warnings() if "cannot run" in w or "panel is short" in w))')"
echo "panel: $PANEL"
if [ -n "$PREV_PANEL" ] && [ "$PANEL" != "$PREV_PANEL" ]; then
    notify "AIRO panel changed" "Was: $PREV_PANEL
Now: $PANEL" default busts_in_silhouette
fi
if [ -n "$UNRUNNABLE" ]; then
    notify "AIRO: index model with no registry row" "$UNRUNNABLE" high warning
fi
# ONE call per model, every question. The second command that used to run here
# forecast XPT question #2 (a natural pandemic), which was held out of the batch
# because it nested under no rung of the bio ladder. The Auto-ARC set retired
# that question and holds nothing out — config.UNBATCHED is empty — so the
# command is gone, along with code/run_forecasts.py, which imported a
# STABLE_SUBSET that no longer exists and would now fail on import.
# THE SINGLE INSTRUMENT (2026-08-27): each call answers every cell
# unconditionally AND under each scenario of the set. The unconditional
# slice lands in results/runs/<stamp>.jsonl (this series); the whole instrument is appended to
# results/conditional_runs_<slug>.jsonl for the conditional panels. The plain
# batch it replaced was retired on 2026-10-21.
# THE COMBINED INSTRUMENT (2026-08-28 evening): the LEAP policies AND the
# six-month capability scenarios in one call, on THE PANEL (the four highest-
# ECI models; --model-set defaults to it). 2,520 probabilities a call, so two
# workers (three rate-limit the Anthropic endpoints when anything else runs on
# this box) and a 30-minute request timeout (GPT-5.5 Pro overran litellm's
# ten in the pilot).
# ONE ELICITATION PER MODEL since 2026-09-02 (a project decision): the repeats
# bought a re-asking spread nobody reads as accuracy, and the budget goes to
# the agentic harness instead -- every model now searches iteratively and
# reads pages (redlines/tools.py, MAX_ROUNDS in run_unified.py), so a
# call is longer and dearer than it was. 4 models x 1 = 4 calls. The views
# draw no interval on a single-draw day; the dots and the median are the
# reading.
# THE LOOP is each condition's own (experiments/airo.toml `harness`):
# agent-box's pi since combined-v9 (2026-10-16; redlines/pi_loop.py, three
# hours a call, REDLINES_PI_TIMEOUT), so the env file must give FORECASTER_PI
# (pi 0.99.2's cli.js) and a PATH with node on it (cron's own PATH has none).
# The request timeout here is the litellm loop's, which the axes experiments
# run.
export REDLINES_LLM_TIMEOUT="${REDLINES_LLM_TIMEOUT:-1800}"
# THE RUNS: one run_unified per due group (an experiment's conditions that
# ask one scenario set and write to one place), ten calls at a time. The
# runner exits non-zero when a pooled condition's call failed -- the date
# cannot publish without every panel model -- so a failed group that
# publishes withholds publication; any other failure pages and the rest go
# ahead. Its preflight also refuses an Epoch snapshot older than 21 days or
# scenario sets not built from the newest one (code/check_eci_snapshot.py).
# THE AIRO EXPERIMENT (experiments/airo.toml; redlines/experiments.py since
# 2026-10-21): the combined instrument under six conditions, one call per
# model each -- 24 calls. Five are pooled (Jason's five prompts, combined-v10,
# 2026-10-19): the published number per model is the mean of its five. The
# sixth (2026-10-19 evening) is the baseline prompt with the AI-forecast ban
# and agent-box's URL guard against AIRO's own pages, passed to that call
# alone: a line on the Timeline, never in the published number, and a failed
# sixth call does not fail the run. The guard needs agent-box's `url-guard`
# in PY (FORECASTER_BLOCK_URL_PATTERNS in its tools); an older agent-box
# ignores the variable and the sixth call searches unguarded while its rows
# say otherwise.
PUBLISHED=0
WITHHELD=0
while read -r exp dest conds; do
    args=()
    for c in $conds; do args+=(--condition "$c"); done
    echo "=== $exp ($dest): $conds ==="
    if "$PY" code/run_unified.py --experiment "$exp" "${args[@]}" --workers 10 </dev/null; then
        [ "$dest" = publish ] && PUBLISHED=1
    elif [ "$dest" = publish ]; then
        echo "FATAL: $exp did not complete for every panel model; see above. Publication withheld."
        WITHHELD=1
    else
        notify "AIRO $exp FAILED" "An unpublished run failed; the published runs are unaffected. log: $LOG" default warning
    fi
done <<< "$DUE"
if [ "$WITHHELD" = 1 ]; then
    exit 1
fi
if [ "$PUBLISHED" != 1 ]; then
    FINISHED=1
    notify "AIRO run $STAMP done" "Nothing to publish: $(echo "$DUE" | cut -d' ' -f1 | sort -u | tr '\n' ' ')" low
    exit 0
fi

# THE AXES INSTRUMENTS (2026-09-03, the FRI economist's spec of 2026-09-02) --
# the same questions at 2030/2050/2100 only, conditional on FIXED levels of an
# x-axis quantity (data/axes_conditions.json for the dashboard's scatter
# panels, data/paper_axes_conditions.json for the paper's figure) -- ran here
# after the combined instrument from 2026-09-03 to 2026-09-14, about $60 and
# $100 a run. LEFT THE SCHEDULE on 2026-09-14 (project decision): they are
# not re-elicited on every run, and the axes panel keeps drawing the newest
# complete axes date (`cadence = "manual"`). To re-elicit one by hand on
# this box, `cron_run.sh axes`, or without publishing,
#     "$PY" code/run_unified.py --experiment axes --workers 2
# (experiments/axes.toml, or paperaxes; rows go to
# results/conditional_runs_<slug>.jsonl and results/<slug>_runs/, never into
# results/runs/), then audit that date with
# code/validate_launch_run.py --experiments axes and run code/publish_dashboard.sh.

# Republish the dashboard with the new data point. A publish failure must not
# mask the successful run above — log it and carry on.
if ! "$REPO/code/publish_dashboard.sh"; then
    echo "WARN: publish_dashboard.sh failed — the last successful dashboard publication remains served"
    notify "AIRO run $STAMP: publish FAILED" "The forecasts ran but the dashboard was not republished. log: $LOG" high warning
    FINISHED=1
    exit 0
fi
FINISHED=1
notify "AIRO run $STAMP published" "$(grep -E 'ok, [0-9]+ failed' "$LOG" | tail -1 | sed 's/ -> .*//'). Panel: $PANEL" low white_check_mark

# THE SHADOW (2026-10-14 to 2026-10-21) ran the published instrument a second
# time through the other loop, after publication, when the env file set
# REDLINES_SHADOW_HARNESS. It has had no run to make since combined-v10: the
# minimal instrument runs only through pi, the published loop. A loop
# comparison is now an experiment of its own (experiments/<name>.toml, a
# condition with another `harness`, publish = false), compared with
# code/compare_harness.py.
