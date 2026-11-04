"""Build a run: snapshot -> frame -> outcomes -> sample -> statements -> prompts, plus run.lock.json.

    python -m pipeline.build config/runs/w1-r1.yaml                 # writes runs/<run_id>/
    python -m pipeline.build config/runs/w1-r1.yaml --allow-unreviewed   # dry run with fallback statements
    python -m pipeline.build config/runs/w1-r1.yaml --out DIR        # used by verify (no lock check)

Everything here reads archived history only (no network).
"""
import argparse
import datetime as dt
import platform
import sys
from pathlib import Path

from . import fetch, frame, outcomes, render, sample, snapshot, statements
from .common import (ARCHIVE, ROOT, WORK, PipelineError, is_bare_repo, load_run_config, read_json, sha256_file, sha256_text,
                     source_hash, write_csv, write_json)

REPOS = ('erdosproblems', 'formal-conjectures')
ARTIFACTS = ['frame.csv', 'exclusions.csv', 'outcomes.csv', 'transitions.csv', 'sample.csv', 'sample_log.json',
             'prompts.jsonl']


def config_hash(run_cfg_path, wave, rules_path):
    wave_path = ROOT / 'config' / 'waves' / f"{wave['wave']}.yaml"
    return sha256_text(''.join(Path(p).read_text(encoding='utf-8') for p in (run_cfg_path, wave_path, rules_path)))


def build(run_cfg_path, out=None, allow_unreviewed=False):
    run, wave, rules = load_run_config(run_cfg_path)
    rules_path = ROOT / 'rules' / f"{wave['rules_version']}.yaml"
    if rules['version'] != wave['rules_version']:
        raise PipelineError('rules file version field does not match wave rules_version')
    if run['snapshot_date'] <= wave['t0']:
        raise PipelineError('snapshot_date must be after t0')
    d = Path(out) if out else ROOT / 'runs' / run['run_id']
    d.mkdir(parents=True, exist_ok=True)
    if not all(is_bare_repo(WORK / f"{r}.git") for r in REPOS):
        fetch.restore()

    c0 = {r: snapshot.commit_at(r, wave['t0']) for r in REPOS}
    cs = {r: snapshot.commit_at(r, run['snapshot_date']) for r in REPOS}
    print('C_T0', {r: c[:10] for r, c in c0.items()}, ' C_S', {r: c[:10] for r, c in cs.items()})

    units, excl, _ = frame.build(c0['erdosproblems'], c0['formal-conjectures'], rules)
    write_csv(d / 'frame.csv', units, frame.FRAME_FIELDS)
    write_csv(d / 'exclusions.csv', excl, frame.EXCL_FIELDS)
    print(f'frame: {len(units)} units, {len(excl)} exclusions')

    outs, trans = outcomes.compute(units, c0, cs, rules, wave['t0'], run['snapshot_date'])
    write_csv(d / 'outcomes.csv', outs, outcomes.OUT_FIELDS)
    write_csv(d / 'transitions.csv', trans, outcomes.TRANS_FIELDS)
    print(f"outcomes: {sum(int(o['solved']) for o in outs)} solved at S, "
          f"{sum(int(o['literature_find']) for o in outs)} literature finds")

    srows, slog = sample.draw(units, outs, wave, rules)
    write_csv(d / 'sample.csv', srows, sample.SAMPLE_FIELDS)
    write_json(d / 'sample_log.json', slog)
    print('sample:', slog)

    in_sample = {r['unit_id'] for r in srows}
    texts, missing = statements.lookup([u for u in units if u['unit_id'] in in_sample])
    st_status = statements.approval_status([u for u in units if u['unit_id'] in in_sample])
    if missing:
        if not allow_unreviewed:
            print(f'{len(missing)} sampled statements not approved yet. Next: '
                  f'python -m pipeline.statements submit {run_cfg_path}')
        else:
            st_status = 'UNREVIEWED-FALLBACK (dry run only)'
            for u in missing:
                docs, _ = statements.source_text(u, rules)
                texts[u['unit_id']] = statements.fallback_text(docs)
    chash = config_hash(run_cfg_path, wave, rules_path)
    prompts = None
    if not missing or allow_unreviewed:
        prompts = render.render(run, wave, srows, texts, chash)
        render.write_jsonl(d / 'prompts.jsonl', prompts)
        print(f'prompts: {len(prompts)} conversations rendered ({st_status})')

    man = read_json(ARCHIVE / 'manifest.json')
    lock = {
        'run_id': run['run_id'], 'wave': wave['wave'], 'rules_version': wave['rules_version'],
        't0': wave['t0'], 'snapshot_date': run['snapshot_date'], 'run_date': run['run_date'],
        'config_hash': chash, 'source_hash': source_hash(),
        'commits': {r: {'t0': c0[r], 's': cs[r], 't0_info': snapshot.commit_info(r, c0[r]),
                        's_info': snapshot.commit_info(r, cs[r])} for r in REPOS},
        'bundles': man['bundles'],
        'statements_status': st_status,
        'statement_files': {k.name: sha256_file(k) for k in sorted(statements.STATEMENTS.glob('*.json'))
                            if any(k.name.startswith(statements.key_of(u)) for u in units if u['unit_id'] in in_sample)},
        'artifacts': {a: sha256_file(d / a) for a in ARTIFACTS if (d / a).exists()},
        'inclusion_probability_note': 'random-draw probabilities are conditional on the realised guaranteed draw',
        'python': sys.version.split()[0], 'platform': platform.platform(),
        'requirements_sha256': sha256_file(ROOT / 'requirements.lock.txt'),
        'built_utc': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    }
    if out is None:
        write_json(d / 'run.lock.json', lock)
        print('wrote', d / 'run.lock.json')
    return lock


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('run_config')
    ap.add_argument('--out')
    ap.add_argument('--allow-unreviewed', action='store_true')
    a = ap.parse_args()
    build(a.run_config, a.out, a.allow_unreviewed)
