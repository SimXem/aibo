"""Stage: render forecast and reveal prompts (D12-D15) from the sample, statements and outcomes."""
import json

from .common import ROOT, hash_rank, sha256_text


def _outcome_text(r, s_date):
    if int(r['solved']):
        kind = r['outcome_type'] if r['outcome_type'] in ('proved', 'disproved', 'solved', 'independent') else 'resolved'
        return f"solved on {r['solve_date']} ({kind})"
    return f'still open as of {s_date}'


def render(run, wave, sample_rows, statements, config_hash):
    tdir = ROOT / run['templates']
    t_fc = (tdir / 'forecast.txt').read_text(encoding='utf-8')
    t_rv = (tdir / 'reveal.txt').read_text(encoding='utf-8')
    t0, s_date = wave['t0'], run['snapshot_date']
    rows = []
    for m in wave['models']:
        for k in range(wave['n_samples']):
            salt = f"{config_hash}|{m['id']}|{k}"
            order = sorted(sample_rows, key=lambda r: hash_rank(salt, r['unit_id']))
            items = '\n'.join(f"[{r['code']}] {r['display_name']}: {statements[r['unit_id']]}" for r in order)
            fprompt = t_fc.format(run_date=run['run_date'], t0=t0, t0_month=t0[:7], n_items=len(order), items=items)
            rec = {'model': m['id'], 'provider': m['provider'], 'effort': m.get('effort', wave.get('default_effort', 'high')),
                   'sample_idx': k, 'order': [r['code'] for r in order],
                   'forecast_prompt': fprompt, 'forecast_sha256': sha256_text(fprompt)}
            if 'reveal' in run.get('stages', []):
                ritems = '\n'.join(f"[{r['code']}] {r['display_name']}: {_outcome_text(r, s_date)}" for r in order)
                rprompt = t_rv.format(t0=t0, snapshot_date=s_date, items=ritems,
                                      stage3_question=run.get('stage3_question') or '').rstrip() + '\n'
                rec.update(reveal_prompt=rprompt, reveal_sha256=sha256_text(rprompt))
            rows.append(rec)
    return rows


def write_jsonl(path, rows):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n')
