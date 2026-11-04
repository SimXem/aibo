"""Runner 1 (workflow steps 1-6): data, sample, statements and lock, without human statement review.

    python -m pipeline.stage_prepare config/runs/<run>.yaml              # network fetch first
    python -m pipeline.stage_prepare config/runs/<run>.yaml --no-fetch   # use the archived bundles as they are

1. fetch:      archive both trackers as git bundles (network; skipped with --no-fetch)
2. build:      frame, outcomes, sample
3. statements: one Message Batch with a draft for every sampled problem that has no frozen statement
               (PAID, Anthropic batch price), polled until it ends; failed drafts are resubmitted
               (at most --rounds batches)
4. freeze:     every new draft is frozen as-is, marked auto_approved; no human review
               (statements that already exist, reviewed or not, are reused and never overwritten)
5. build:      render prompts and write run.lock.json (statements_status says whether any statement
               was auto-approved)
6. verify:     rebuild from the bundles alone and compare every artifact hash

Stops with an error if statements are still missing after the last round or if verification fails.
"""
import argparse
import sys

from . import build, fetch, statements, verify
from .common import PipelineError, load_run_config, read_json, run_dir


def prepare(run_cfg_path, no_fetch=False, rounds=3, poll_seconds=60):
    print('== 1. fetch' + (' (skipped: --no-fetch)' if no_fetch else ''))
    if not no_fetch:
        fetch.fetch()
    fetch.restore()

    print('== 2. build (frame, outcomes, sample)')
    build.build(run_cfg_path)
    run, _, _ = load_run_config(run_cfg_path)

    print('== 3-4. statements (draft by Message Batch, freeze without human review)')
    for i in range(rounds):
        statements.collect(run_cfg_path, wait=True, poll_seconds=poll_seconds)   # batches left from an earlier run
        statements.auto_approve(run_cfg_path)
        _, missing = statements.lookup(statements._sampled_units(run))
        if not missing:
            break
        print(f'round {i + 1}: {len(missing)} statements missing; submitting drafts')
        statements.submit(run_cfg_path)
    statements.collect(run_cfg_path, wait=True, poll_seconds=poll_seconds)
    statements.auto_approve(run_cfg_path)
    _, missing = statements.lookup(statements._sampled_units(run))
    if missing:
        raise PipelineError(f"{len(missing)} statements still missing after {rounds} rounds: "
                            f"{[u['unit_id'] for u in missing][:10]}")
    print('all sampled statements are frozen')

    print('== 5. build (prompts + run.lock.json)')
    build.build(run_cfg_path)

    print('== 6. verify --fresh')
    if not verify.verify(run_cfg_path, fresh=True):
        raise PipelineError('verification failed: the run does not rebuild identically from the bundles')
    lock = read_json(run_dir(run) / 'run.lock.json')
    print(f"\nready: {run['run_id']}  statements_status={lock['statements_status']!r}\n"
          f"next:  python -m pipeline.stage_forecast {run_cfg_path}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run_config')
    ap.add_argument('--no-fetch', action='store_true', help='do not contact the trackers; use archived bundles')
    ap.add_argument('--rounds', type=int, default=3, help='max statement-draft batches (default 3)')
    ap.add_argument('--poll', type=int, default=60, help='seconds between batch status checks')
    a = ap.parse_args()
    prepare(a.run_config, a.no_fetch, a.rounds, a.poll)
    sys.exit(0)
