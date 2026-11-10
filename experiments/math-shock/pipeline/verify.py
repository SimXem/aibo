"""Rebuild a run from archived bundles and check every artifact hash against run.lock.json.

    python -m pipeline.verify config/runs/w1-r1.yaml          # uses existing work clones
    python -m pipeline.verify config/runs/w1-r1.yaml --fresh  # rebuild work clones from bundles first
"""
import argparse
import tempfile

from . import build, fetch
from .common import APPROVED_STATUSES, WORK, load_run_config, read_json, rmtree, run_dir, source_hash


def verify(run_cfg_path, fresh=False):
    run, _, _ = load_run_config(run_cfg_path)
    lock = read_json(run_dir(run) / 'run.lock.json')
    if fresh:
        rmtree(WORK)
        fetch.restore()
    with tempfile.TemporaryDirectory() as tmp:
        new = build.build(run_cfg_path, out=tmp, allow_unreviewed=lock['statements_status'] not in APPROVED_STATUSES)
        ok = True
        for k in ('config_hash', 'commits', 'statement_files'):
            if new[k] != lock[k]:
                print('MISMATCH', k); ok = False
        for a, h in lock['artifacts'].items():
            h2 = new['artifacts'].get(a)
            print(('ok      ' if h == h2 else 'MISMATCH'), a)
            ok &= h == h2
    if source_hash() != lock['source_hash']:
        print('note: pipeline code/rules/templates changed since the run was built (source_hash differs)')
    print('VERIFIED' if ok else 'NOT REPRODUCED')
    return ok


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('run_config')
    ap.add_argument('--fresh', action='store_true')
    a = ap.parse_args()
    raise SystemExit(0 if verify(a.run_config, a.fresh) else 1)
