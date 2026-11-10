"""Get the forecasts: call the models on the run's forecast prompts, then parse the answers.

    python -m pipeline.stage_forecast config/runs/<run>.yaml                          # all models in the wave
    python -m pipeline.stage_forecast config/runs/<run>.yaml --models claude-opus-5-5 # a subset
    python -m pipeline.stage_forecast config/runs/<run>.yaml --stub                   # offline dry run

- run:   every model goes through its provider's batch API (Anthropic Message Batches, OpenAI Batch
          API; PAID, half price), polled until each batch ends; parse retries and failed requests are
          sent in further batches (at most --rounds). With --direct: direct calls (PAID, full price).
          Finished samples are always skipped, so the runner can be re-run safely.
- parse: raw/*.json -> parsed.csv (violations are flagged, never repaired)
"""
import argparse
import sys

from . import parse, run, run_batch
from .run_batch import BATCH_PROVIDERS
from .common import load_run_config


def _unfinished(run_cfg_path, models, samples, stub=False):
    _, _, out, convs, stages = run.load_checked(run_cfg_path, stub=stub, allow_unreviewed=True)
    return [f"{c['model']}__s{c['sample_idx']}" for c in run.selected(convs, models, samples)
            if not run.is_done(out, c, stages)]


def forecast(run_cfg_path, models=None, samples=None, direct=False, stub=False, rounds=3, poll_seconds=60):
    _, wave, _ = load_run_config(run_cfg_path)
    prov = {m['id']: m['provider'] for m in wave['models']}
    models = models or list(prov)
    unknown = [m for m in models if m not in prov]
    if unknown:
        raise SystemExit(f'not in the wave: {unknown}; wave models: {list(prov)}')

    print('== forecasts' + (' (stub)' if stub else ''))
    if stub:
        run.run(run_cfg_path, models, samples, stub=True)
    else:
        batched = [] if direct else [m for m in models if prov[m] in BATCH_PROVIDERS]
        directs = [m for m in models if m not in batched]
        if batched:
            print(f'batch: {batched}')
            run_batch.collect(run_cfg_path, wait=True, poll_seconds=poll_seconds)   # batches left from an earlier run
            for _ in range(rounds):
                if run_batch.submit(run_cfg_path, batched, samples) is None:
                    break
                run_batch.collect(run_cfg_path, wait=True, poll_seconds=poll_seconds)
        if directs:
            print(f'direct: {directs}')
            run.run(run_cfg_path, directs, samples)
    left = _unfinished(run_cfg_path, models, samples, stub)
    if left:
        print(f'WARNING: {len(left)} conversations unfinished (see raw/*.error.json): {left}')

    print('== parse -> parsed.csv')
    parse.parse_run(run_cfg_path, stub=stub)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run_config')
    ap.add_argument('--models', nargs='*', help='model ids (default: all models in the wave)')
    ap.add_argument('--samples', type=int, help='only sample_idx < N')
    ap.add_argument('--direct', action='store_true', help='direct calls (full price) instead of batches')
    ap.add_argument('--stub', action='store_true', help='offline dry run -> raw_stub/, parsed_stub.csv')
    ap.add_argument('--rounds', type=int, default=3, help='max batches (first + retry rounds, default 3)')
    ap.add_argument('--poll', type=int, default=60, help='seconds between batch status checks')
    a = ap.parse_args()
    forecast(a.run_config, a.models, a.samples, a.direct, a.stub, a.rounds, a.poll)
    sys.exit(0)
