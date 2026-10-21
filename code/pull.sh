#!/usr/bin/env bash
# THE BOX'S CODE (2026-10-21): bring this checkout up to its upstream branch
# before a scheduled job runs from it, so what is merged is what runs --
# deploying is merging. The crontab runs it ahead of each job, holding the
# OTHER job's lock so code never changes under a running one:
#
#   0 12 * * 3,5 flock -n /tmp/redlines-forecast.lock bash -c 'flock -n /tmp/fb-round.lock <repo>/code/pull.sh; exec <repo>/code/cron_run.sh'
#   5 0 25 10 *  flock -n /tmp/fb-round.lock bash -c 'flock -n /tmp/redlines-forecast.lock <repo>/code/pull.sh; exec <repo>/packages/fri-forecaster/scripts/fb_cron.sh 2026-10-25'
#
# Fast-forward only. The runs rewrite some tracked files in place: the
# dashboard's index.html and results/*.json, and the scenario sets
# data/*_conditions.json. Where the incoming commits change one of those too,
# the box's copy goes to ~/backups/airo-pull-<stamp>/ and the incoming one is
# taken; the next AIRO run rebuilds it from the box's own rows (the served
# page, /var/www/html, is untouched until then). Anything else in the way --
# another file modified here, a commit only here, an untracked file the pull
# would overwrite -- stops the pull and pages, and the job runs the checkout
# as it is. A pull that changes a dependency manifest pages too: the venv and
# pi are not reinstalled here. One line per pull goes to ~/logs/pull.log.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$REPO/code/notify.sh"
cd "$REPO" || exit 1
STAMP="$(date -u +%Y-%m-%dT%H%MZ)"
mkdir -p "$HOME/logs"
log() { echo "$STAMP $*" >> "$HOME/logs/pull.log"; }
refuse() {
    log "not updated: $1"
    notify "Box code not updated" "$1 Jobs run $(git rev-parse --short HEAD) until it is pulled by hand: $(hostname):$REPO" high warning
    exit 1
}

out="$(git fetch -q 2>&1)" || refuse "git fetch failed: ${out:0:200}."
OLD="$(git rev-parse --short HEAD)"
if [ "$(git rev-list --count 'HEAD..@{u}')" = 0 ]; then
    log "$OLD, up to date"
    exit 0
fi
[ "$(git rev-list --count '@{u}..HEAD')" = 0 ] || refuse "The checkout has commits upstream does not."

# The incoming commits' files that the box has modified: rebuilt outputs are
# set aside, anything else stops the pull.
CLASH="$(comm -12 <(git diff --name-only HEAD '@{u}' | sort) <(git diff --name-only HEAD | sort))"
OTHER="$(grep -vE '^(index\.html|results/.*\.json|data/[^/]*_conditions\.json)$' <<< "$CLASH" | paste -sd' ' -)"
[ -z "$OTHER" ] || refuse "Modified here and upstream: $OTHER."
BACKUP=""
if [ -n "$CLASH" ]; then
    BACKUP="$HOME/backups/airo-pull-$STAMP"
    while read -r f; do
        mkdir -p "$BACKUP/$(dirname "$f")" && cp -p "$f" "$BACKUP/$f" || refuse "Could not back up $f."
    done <<< "$CLASH"
    xargs git checkout -- <<< "$CLASH" || refuse "Could not set aside the rebuilt files."
fi
out="$(git merge --ff-only -q '@{u}' 2>&1)" || refuse "git merge --ff-only failed: ${out:0:200}."

NEW="$(git rev-parse --short HEAD)"
log "$OLD -> $NEW${BACKUP:+; rebuilt files the pull replaced are in $BACKUP}"
DEPS="$(git diff --name-only "$OLD" "$NEW" -- pyproject.toml packages/fri-forecaster/pyproject.toml packages/fri-forecaster/package.json | paste -sd' ' -)"
if [ -n "$DEPS" ]; then
    notify "Box code updated; dependencies changed" "$OLD -> $NEW changed $DEPS. The venv and pi are not reinstalled by the pull: check them before the next job. $(hostname):$REPO" high warning
fi
