"""Revised forecasts: send the follow-up message in finished forecast conversations, parse, export.

    python -m pipeline.stage_followup config/followups/<id>.yaml
    python -m pipeline.stage_followup config/followups/<id>.yaml --stub    # offline dry run

- build:   render and lock the follow-up prompts (only if not built yet; an existing lock is checked,
             never rewritten, so a changed input stops the runner instead of being re-pinned)
- run:     every model through its provider's batch API (PAID, half price), polled until each batch
             ends, with parse retries / failed requests in further batches (at most --rounds);
             with --direct: direct calls (PAID, full price)
- parse:   followups/<id>/parsed.csv (revised forecast next to the earlier one)
- export:  dates_long.csv + dates_summary.csv (tidy, months from the snapshot month)
"""
import argparse
import sys

from . import followup
from .common import ROOT, load_yaml
from .run import load_checked


def run_followup(fu_path, direct=False, stub=False, rounds=3, poll_seconds=60):
    fu = load_yaml(fu_path)
    _, d, _, _, _ = load_checked(ROOT / fu['base_run'])
    fdir = d / 'followups' / fu['followup_id']

    print('== follow-up prompts + lock')
    if (fdir / 'followup.lock.json').exists():
        print('already built; checking the lock')
    else:
        followup.build(fu_path)
    _, _, _, rows, _ = followup._checked(fu_path)

    print('== revised forecasts' + (' (stub)' if stub else ''))
    if stub:
        followup.run_direct(fu_path, stub=True)
    else:
        batched = not direct
        if batched:
            followup.collect(fu_path, wait=True, poll_seconds=poll_seconds)        # batches left from an earlier run
            for _ in range(rounds):
                if followup.submit(fu_path) is None:
                    break
                followup.collect(fu_path, wait=True, poll_seconds=poll_seconds)
        if not batched:
            followup.run_direct(fu_path)
        left = followup.pending(fu_path)
        if left:
            print(f'WARNING: {len(left)} follow-up conversations unfinished (see raw/*.error.json): {left}')

    print('== parse -> parsed.csv')
    followup.parse(fu_path, stub=stub)
    print('== export -> dates_long.csv, dates_summary.csv')
    followup.export(fu_path, stub=stub)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('followup_config')
    ap.add_argument('--direct', action='store_true', help='direct calls (full price) instead of batches')
    ap.add_argument('--stub', action='store_true', help='offline dry run -> raw_stub/, *_stub.csv')
    ap.add_argument('--rounds', type=int, default=3, help='max batches (first + retry rounds, default 3)')
    ap.add_argument('--poll', type=int, default=60, help='seconds between batch status checks')
    a = ap.parse_args()
    run_followup(a.followup_config, a.direct, a.stub, a.rounds, a.poll)
    sys.exit(0)
