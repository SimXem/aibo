#!/usr/bin/env bash
# THE PANEL, REFRESHED (2026-10-21): fetch Epoch's index, give a registry row
# to any model it now ranks into the panel without one, rebuild the capability
# scenarios from the new snapshot, and page what changed. Every job on the box
# that reads the panel runs this first -- code/cron_run.sh before each AIRO run,
# and the ForecastBench rounds (round.env's panel_members hook, see
# packages/fri-forecaster/examples/round.env.example) -- so the panel is never
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
if [ -z "${REDLINES_PY:-}" ] && [ -x "$REPO/.venv/bin/python" ]; then
    REDLINES_PY="$REPO/.venv/bin/python"
fi
PY="${REDLINES_PY:-$HOME/Projects/xrisk-canaries/.venv/bin/python}"
. "$REPO/code/notify.sh"
cd "$REPO"

panel_labels() {
    "$PY" -c 'from redlines import registry; print(", ".join(m["label"] for m, _ in registry.panel()))'
}
PREV_PANEL="$(panel_labels 2>/dev/null || true)"
if ! "$PY" -m redlines.eci --fetch; then
    notify "AIRO: Epoch ECI fetch failed" "The panel stays on the previous snapshot. Check https://epoch.ai/data/eci_scores.csv" high warning
fi
# NEW MODELS (2026-10-07): give a row to each model the index now ranks into
# the panel without one (redlines.autoreg), before the panel is read. A crash
# here costs only the new model's seat -- the job goes ahead, and the model is
# paged below as unrunnable.
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
