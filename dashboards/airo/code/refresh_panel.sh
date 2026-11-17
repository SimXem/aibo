#!/usr/bin/env bash
# THE PANEL, REFRESHED (2026-10-21): fetch Epoch's index, give a registry row
# to any model it now ranks into the panel without one, rebuild the capability
# scenarios from the new snapshot, and page what changed. Every job on the box
# that reads the panel runs this first -- code/cron_run.sh before each AIRO run,
# and the ForecastBench rounds (round.env's panel_members hook, see
# submissions/forecastbench/examples/round.env.example) -- so the panel is never
# older than the job reading it, and whichever job fetches a change first is
# the one that pages it. Until 2026-10-21 this was inline in cron_run.sh, and a
# round that fetched on its own left the next AIRO run nothing to page.
#
# Prints what it did; exits non-zero only when the panel cannot be read or the
# scenarios cannot be rebuilt. A failed fetch keeps the previous snapshot and
# pages; the runner's preflight (code/check_eci_snapshot.py) still refuses one
# older than 21 days.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -z "${REDLINES_PY:-}" ] && [ -x "$REPO/../../.venv/bin/python" ]; then
    REDLINES_PY="$REPO/../../.venv/bin/python"
fi
PY="${REDLINES_PY:-$HOME/Projects/xrisk-canaries/.venv/bin/python}"
. "$REPO/code/notify.sh"
cd "$REPO"

panel_labels() {
    "$PY" -c 'from redlines import registry; print(", ".join(m["label"] for m, _ in registry.panel()))'
}
PREV_PANEL="$(panel_labels 2>/dev/null || true)"
if ! "$PY" -m redlines.eci --fetch; then
    notify "ECI fetch failed" "Falling back to the last known ensemble. Check https://epoch.ai/data/eci_scores.csv"
fi
# NEW MODELS (2026-10-07): give a row to each model the index now ranks into
# the panel without one (redlines.autoreg), before the panel is read. A model
# that still has no row afterwards fails the run below: nothing stands in.
if ! ADDED="$("$PY" -m redlines.autoreg)"; then
    echo "WARN: redlines.autoreg failed"
    ADDED=""
fi
[ -z "$ADDED" ] || echo "$ADDED"
"$PY" code/check_eci_snapshot.py --rebuild
PANEL="$(panel_labels)"
# A top model that cannot be run, though its lab's key is held (stdout); one
# whose lab's key is not held is left out of the ensemble (a NOTE, stderr).
UNRUNNABLE="$("$PY" -c 'import sys; from redlines import registry; problems, omitted = registry.unseated(); print("\n".join(problems)); [print("NOTE:", o, file=sys.stderr) for o in omitted]')"
echo "panel: $PANEL"
if [ -n "$PREV_PANEL" ] && [ "$PANEL" != "$PREV_PANEL" ]; then
    notify "ensemble changed" "Was: $PREV_PANEL
Now: $PANEL"
fi
# NO FALLBACK (2026-11-13): the run asks the index's top models or it does not
# run. The caller fails its run on this exit and pages that.
if [ -n "$UNRUNNABLE" ]; then
    echo "FATAL: the ensemble cannot be seated, and no other model stands in: $UNRUNNABLE"
    exit 1
fi
