#!/usr/bin/env bash
# Publish a snapshot of a private branch (default main) to the public repo as
# ONE commit. By default the public repo's history is replaced each time (a
# single commit, always); PARENTED=1 stacks releases instead. The private
# repo keeps the full history either way.
#
#   code/publish_public.sh              # snapshot main as ONE commit, force-push public:main
#   PUSH=0 code/publish_public.sh       # create the commit, do not push
#   PARENTED=1 code/publish_public.sh   # instead: one commit per release, on top of the last
#   code/publish_public.sh main "Release notes"
#
# The public remote is `public` (git@github.com:forecastingresearch/airo.git);
# PUBLIC_REMOTE / PUBLIC_BRANCH override the names.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
REMOTE="${PUBLIC_REMOTE:-public}"
BRANCH="${PUBLIC_BRANCH:-public}"
SRC="${1:-main}"
MSG="${2:-Publish snapshot of $SRC, $(date -u +%Y-%m-%d)}"

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "refusing: the working tree has uncommitted changes" >&2; exit 1
fi
# Never carry internal material into the snapshot, whatever the ignore rules say.
for p in data/leap/ TODO.md private/ .env; do
    if git ls-tree -r --name-only "$SRC" | grep -q "^$p"; then
        echo "refusing: $p is tracked on $SRC" >&2; exit 1
    fi
done

TREE="$(git rev-parse "$SRC^{tree}")"
PARENT=()
if git rev-parse -q --verify "refs/heads/$BRANCH" >/dev/null; then
    if [ "$(git rev-parse "$BRANCH^{tree}")" = "$TREE" ]; then
        echo "nothing to publish: $BRANCH already carries $SRC's tree"; exit 0
    fi
    # PARENTED=1 keeps one commit per release; the default keeps the public
    # repo at a single commit (its history is replaced on every publish).
    if [ "${PARENTED:-0}" = 1 ]; then
        PARENT=(-p "$(git rev-parse "$BRANCH")")
    fi
fi
SHA="$(printf '%s\n' "$MSG" | git commit-tree "$TREE" ${PARENT[@]+"${PARENT[@]}"})"
git branch -f "$BRANCH" "$SHA"
echo "$BRANCH -> $SHA ($(git log --oneline "$BRANCH" | wc -l | tr -d ' ') commit(s))"
if [ "${PUSH:-1}" = 1 ]; then
    if [ "${PARENTED:-0}" = 1 ]; then
        git push "$REMOTE" "$BRANCH:main"
    else
        git push --force "$REMOTE" "$BRANCH:main"
    fi
fi
