"""Parse and validate model forecasts. Violations are flagged, never repaired.

    python -m pipeline.parse config/runs/<run>.yaml    # raw/*.json -> parsed.csv
"""
import argparse
import json
import re

from .common import load_run_config, read_json, run_dir, write_csv

DATE = re.compile(r'^(\d{4})-(\d{2})$')
PARSED_FIELDS = ['model', 'returned_model', 'sample_idx', 'code', 'position', 'best', 'q10', 'q90', 'valid', 'issues']


def extract_array(text):
    """First top-level JSON array in the text (tolerates code fences / surrounding prose)."""
    t = re.sub(r'```(?:json)?', '', text)
    i, j = t.find('['), t.rfind(']')
    if i < 0 or j < i:
        raise ValueError('no JSON array found')
    return json.loads(t[i:j + 1])


def _key(v):
    """Sortable key: (year, month); after-2100 -> (9999, 12)."""
    if v == 'after-2100':
        return (9999, 12)
    m = DATE.match(v or '')
    if not m or not 1 <= int(m.group(2)) <= 12:
        return None
    return (int(m.group(1)), int(m.group(2)))


def validate(items, codes, t0):
    """-> (rows, global_issues). One row per expected code."""
    t0k = (int(t0[:4]), int(t0[5:7]))
    got, issues = {}, []
    for it in items:
        c = str(it.get('id', '')).strip()
        if c not in codes:
            issues.append(f'unknown id {c!r}')
        elif c in got:
            issues.append(f'duplicate id {c}')
        else:
            got[c] = it
    rows = []
    for pos, c in enumerate(codes):
        it = got.get(c)
        if it is None:
            rows.append({'code': c, 'position': pos, 'valid': 0, 'issues': 'missing'}); continue
        vals = {k: str(it.get(k, '')).strip() for k in ('best', 'q10', 'q90')}
        keys = {k: _key(v) for k, v in vals.items()}
        prob = [f'bad format {k}={vals[k]!r}' for k, v in keys.items() if v is None]
        if not prob:
            if not keys['q10'] <= keys['best'] <= keys['q90']:
                prob.append('quantiles not ordered')
            if any(v < t0k for v in keys.values()):
                prob.append('date before T0 month')
        rows.append({'code': c, 'position': pos, **vals, 'valid': int(not prob), 'issues': '; '.join(prob)})
    return rows, issues


def parse_run(run_cfg_path, stub=False):
    run, wave, _ = load_run_config(run_cfg_path)
    d = run_dir(run)
    out = []
    for p in sorted((d / ('raw_stub' if stub else 'raw')).glob('*__s*[0-9].json')):
        rec = read_json(p)
        final = rec['turns'][rec['forecast_turn_index']]
        try:
            items = extract_array(final['text'])
            rows, gi = validate(items, rec['order'], wave['t0'])
        except (ValueError, json.JSONDecodeError) as e:
            rows, gi = [{'code': c, 'position': i, 'valid': 0, 'issues': 'unparseable'} for i, c in enumerate(rec['order'])], [str(e)]
        for r in rows:
            r.update(model=rec['model'], returned_model=final.get('returned_model', ''), sample_idx=rec['sample_idx'])
            if gi:
                r['issues'] = '; '.join(filter(None, [r.get('issues', ''), 'response: ' + ' | '.join(gi)]))
        out += rows
    write_csv(d / ('parsed_stub.csv' if stub else 'parsed.csv'), out, PARSED_FIELDS)
    print(f"parsed {len(out)} forecasts; valid {sum(r['valid'] for r in out)}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('run_config')
    ap.add_argument('--stub', action='store_true')
    a = ap.parse_args()
    parse_run(a.run_config, a.stub)
