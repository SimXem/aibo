"""Follow-up stage: continue finished forecast conversations of a base run with one more user turn,
and archive and parse the model's revised forecasts.

    python -m pipeline.followup build   config/followups/w1-r1-f1.yaml          # render + lock (no API)
    python -m pipeline.followup submit  config/followups/w1-r1-f1.yaml          # Message Batch
    python -m pipeline.followup collect config/followups/w1-r1-f1.yaml --wait
    python -m pipeline.followup run     config/followups/w1-r1-f1.yaml          # or direct calls; --stub for a dry run
    python -m pipeline.followup parse   config/followups/w1-r1-f1.yaml          # -> parsed.csv (before/after)

Reveal `solved_side_by_side`: only the problems solved by S are listed, each with the forecast the
model gave for it in that same conversation and where the solve date fell relative to it. The prompt
states how the sample was drawn (guaranteed solved draws plus a random draw) and the population solve
rate, so the update is not driven by the enriched sample. The model is then asked to re-forecast
the still-open problems, with no date earlier than the snapshot month.

The base conversation is sent back unchanged (including thinking blocks). Base records must match the
base run's lock (forecast prompt hash) and are pinned by SHA-256 in followup.lock.json; `run`/`submit`
refuse to start if anything pinned has changed. Output: runs/<base run>/followups/<id>/.
"""
import argparse
import json
import sys

from . import parse as parse_mod
from .common import ROOT, PipelineError, load_yaml, read_csv, read_json, sha256_file, sha256_text, write_csv, write_json
from .render import _outcome_text
from .run import RETRY_MSG, load_checked, now
from .run_batch import collect_jobs, params_for, submit_jobs

STAGE = 'followup'
PARSED_FIELDS = ['model', 'returned_model', 'sample_idx', 'code', 'unit_id', 'position', 'best', 'q10', 'q90',
                 'valid', 'issues', 'before_best', 'before_q10', 'before_q90']


def _load(fu_path):
    fu = load_yaml(fu_path)
    run_cfg, d, base_raw, convs, _ = load_checked(ROOT / fu['base_run'])
    fdir = d / 'followups' / fu['followup_id']
    (fdir / 'raw').mkdir(parents=True, exist_ok=True)
    return fu, run_cfg, d, base_raw, convs, fdir


def _month(v):
    return (9999, 12) if v == 'after-2100' else (int(v[:4]), int(v[5:7]))


def _relation(solve_date, f):
    if not f or not int(f['valid']):
        return 'you gave no valid forecast'
    m = _month(solve_date[:7])
    if m < _month(f['q10']):
        return 'solved before your 10% date'
    if m <= _month(f['q90']):
        return 'solved inside your 10%-90% range'
    return 'solved after your 90% date'


def _fmt(f):
    if not f or not int(f['valid']):
        return '(no valid forecast)'
    return f"best {f['best']}, q10 {f['q10']}, q90 {f['q90']}"


def base_messages(rec):
    """Rebuild the API message list of a finished base conversation, up to its forecast answer."""
    msgs = []
    for t in rec['turns'][:rec['forecast_turn_index'] + 1]:
        if t['role'] == 'user':
            msgs.append({'role': 'user', 'content': t['text']})
        else:
            msgs.append({'role': 'assistant', 'content': t['response']['content']})
    return msgs


def render(fu, run_cfg, d, base_raw, convs):
    if fu['reveal'] != 'solved_side_by_side':
        raise PipelineError(f"unknown reveal mode {fu['reveal']!r}")
    from .common import load_run_config
    _, wave, _ = load_run_config(ROOT / fu['base_run'])
    tmpl = (ROOT / fu['template']).read_text(encoding='utf-8')
    sample = {r['code']: r for r in read_csv(d / 'sample.csv')}
    slog = read_json(d / 'sample_log.json')
    parsed = {(r['model'], r['sample_idx'], r['code']): r for r in read_csv(d / 'parsed.csv')}
    s_date, t0 = run_cfg['snapshot_date'], wave['t0']
    n_random = sum(r['role'] == 'random' for r in sample.values())
    stats = dict(t0=t0, snapshot_date=s_date, s_month=s_date[:7], n_items=len(sample),
                 n_solved=sum(int(r['solved']) for r in sample.values()),
                 n_guaranteed=sum(r['role'] == 'guaranteed' for r in sample.values()), n_random=n_random,
                 n_random_solved=sum(r['role'] == 'random' and int(r['solved']) for r in sample.values()),
                 n_eligible=slog['n_eligible'], n_pool_solved=slog['n_solved_pool'],
                 pool_pct=f"{100 * slog['n_solved_pool'] / slog['n_eligible']:.1f}")
    rows, pins = [], {}
    for c in convs:
        if c['model'] not in fu['models']:
            continue
        sid = f"{c['model']}__s{c['sample_idx']}"
        p = base_raw / f'{sid}.json'
        if not p.exists() or read_json(p).get('stage_done') is None:
            raise PipelineError(f'{p} missing or unfinished; run the base forecast first')
        rec = read_json(p)
        if rec['forecast_sha256'] != c['forecast_sha256']:
            raise PipelineError(f'{p}: forecast prompt hash differs from the base run lock')
        pins[f'{sid}.json'] = sha256_file(p)
        solved = [k for k in c['order'] if int(sample[k]['solved'])]
        open_ = [k for k in c['order'] if not int(sample[k]['solved'])]
        f = lambda k: parsed.get((c['model'], str(c['sample_idx']), k))
        s_items = '\n'.join(
            f"- [{k}] {sample[k]['display_name']}: {_outcome_text(sample[k], s_date)}. "
            f"Your forecast: {_fmt(f(k))}; {_relation(sample[k]['solve_date'], f(k))}." for k in solved)
        o_items = '\n'.join(f"[{k}] {sample[k]['display_name']}" for k in open_)
        prompt = tmpl.format(**stats, n_open=len(open_), solved_items=s_items, open_items=o_items)
        rows.append({'model': c['model'], 'provider': c['provider'], 'effort': c['effort'],
                     'sample_idx': c['sample_idx'], 'order': open_, 'base_record': f'{sid}.json',
                     'followup_prompt': prompt, 'followup_sha256': sha256_text(prompt)})
    if not rows:
        raise PipelineError(f"no base conversations for models {fu['models']}")
    return rows, pins


def build(fu_path):
    fu, run_cfg, d, base_raw, convs, fdir = _load(fu_path)
    rows, pins = render(fu, run_cfg, d, base_raw, convs)
    with open(fdir / 'prompts.jsonl', 'w', encoding='utf-8', newline='\n') as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n')
    lock = {'followup_id': fu['followup_id'], 'base_run': fu['base_run'],
            'config_sha256': sha256_file(fu_path), 'template_sha256': sha256_file(ROOT / fu['template']),
            'base_lock_sha256': sha256_file(d / 'run.lock.json'),
            'base_inputs': {n: sha256_file(d / n) for n in ('sample.csv', 'sample_log.json', 'parsed.csv')},
            'base_records': pins, 'prompts_sha256': sha256_file(fdir / 'prompts.jsonl'),
            'built_utc': now()}
    write_json(fdir / 'followup.lock.json', lock)
    print(f"{len(rows)} follow-up conversations rendered -> {fdir / 'prompts.jsonl'}")
    return fdir


def _checked(fu_path):
    """Re-render and compare with the lock: refuses if config, template, base data or prompts changed."""
    fu, run_cfg, d, base_raw, convs, fdir = _load(fu_path)
    lp = fdir / 'followup.lock.json'
    if not lp.exists():
        raise PipelineError(f'{lp} missing; run: python -m pipeline.followup build {fu_path}')
    lock = read_json(lp)
    rows, pins = render(fu, run_cfg, d, base_raw, convs)
    now_ = {'config_sha256': sha256_file(fu_path), 'template_sha256': sha256_file(ROOT / fu['template']),
            'base_lock_sha256': sha256_file(d / 'run.lock.json'),
            'base_inputs': {n: sha256_file(d / n) for n in ('sample.csv', 'sample_log.json', 'parsed.csv')},
            'base_records': pins, 'prompts_sha256': sha256_file(fdir / 'prompts.jsonl')}
    bad = [k for k, v in now_.items() if lock.get(k) != v]
    stored = [json.loads(l) for l in open(fdir / 'prompts.jsonl', encoding='utf-8')]
    if [r['followup_sha256'] for r in rows] != [r['followup_sha256'] for r in stored]:
        bad.append('rendered prompts')
    if bad:
        raise PipelineError(f'follow-up inputs changed since build: {bad}; use a new followup_id')
    return fu, run_cfg, base_raw, stored, fdir


def _jobs(fu, run_cfg, base_raw, rows):
    jobs = []
    for r in rows:
        base = read_json(base_raw / r['base_record'])

        def start(r=r, base=base):
            return {'run_id': run_cfg['run_id'], 'followup_id': fu['followup_id'], 'model': r['model'],
                    'provider': r['provider'], 'effort': r['effort'], 'sample_idx': r['sample_idx'],
                    'order': r['order'], 'base_record': r['base_record'], 'followup_sha256': r['followup_sha256'],
                    'started_utc': now(), 'parse_retry': False, 'stage_done': None,
                    'base_turns': len(base['turns'][:base['forecast_turn_index'] + 1]),
                    'turns': [*base['turns'][:base['forecast_turn_index'] + 1],
                              {'role': 'user', 'text': r['followup_prompt'], 'utc': now()}]}
        jobs.append({'sid': f"{r['model']}__s{r['sample_idx']}", 'params': params_for(r['model'], r['effort']),
                     'messages': [*base_messages(base), {'role': 'user', 'content': r['followup_prompt']}],
                     'start_record': start, 'stage': STAGE})
    return jobs


def _anthropic(rows):
    skipped = sorted({r['model'] for r in rows if r['provider'] != 'anthropic'})
    if skipped:
        print(f'batch mode is Anthropic-only; not batched: {skipped} (use run for these)')
    return [r for r in rows if r['provider'] == 'anthropic']


def submit(fu_path, client=None):
    fu, run_cfg, base_raw, rows, fdir = _checked(fu_path)
    return submit_jobs(_jobs(fu, run_cfg, base_raw, _anthropic(rows)), fdir / 'raw', fdir / 'batches.json', client,
                       f'python -m pipeline.followup collect {fu_path} --wait')


def collect(fu_path, wait=False, client=None, poll_seconds=60):
    fu, run_cfg, base_raw, rows, fdir = _checked(fu_path)
    collect_jobs(_jobs(fu, run_cfg, base_raw, rows), fdir / 'raw', fdir / 'batches.json', client, wait, poll_seconds)


def pending(fu_path):
    """sids of follow-up conversations without a finished record."""
    fu, run_cfg, base_raw, rows, fdir = _checked(fu_path)
    out = []
    for r in rows:
        p = fdir / 'raw' / f"{r['model']}__s{r['sample_idx']}.json"
        if not (p.exists() and read_json(p).get('stage_done') == STAGE):
            out.append(f"{r['model']}__s{r['sample_idx']}")
    return out


def run_direct(fu_path, stub=False, skip_providers=()):
    """Direct calls (resumable), same retry rule as pipeline.run. --stub writes raw_stub/."""
    from .llm import provider
    from .parse import extract_array
    fu, run_cfg, base_raw, rows, fdir = _checked(fu_path)
    out = fdir / ('raw_stub' if stub else 'raw')
    out.mkdir(exist_ok=True)
    clients = {}
    for j, r in zip(_jobs(fu, run_cfg, base_raw, rows), rows):
        p = out / f"{j['sid']}.json"
        if (p.exists() and read_json(p).get('stage_done') == STAGE) or (not stub and r['provider'] in skip_providers):
            continue
        prov = 'stub' if stub else r['provider']
        llm = clients.setdefault(prov, provider(prov))
        rec, messages = j['start_record'](), list(j['messages'])

        def turn():
            t, text, raw = llm.chat(r['model'], messages, r['effort'])
            messages.append(t)
            rec['turns'].append({'role': 'assistant', 'text': text, 'returned_model': raw['returned_model'],
                                 'stop_reason': raw['stop_reason'], 'request_id': raw['request_id'],
                                 'request_params': raw['request_params'], 'response': raw['response'], 'utc': now()})
            return text
        try:
            text = turn()
            try:
                extract_array(text)
            except ValueError:
                rec['parse_retry'] = True
                messages.append({'role': 'user', 'content': RETRY_MSG})
                rec['turns'].append({'role': 'user', 'text': RETRY_MSG, 'utc': now()})
                turn()
        except PipelineError:
            raise
        except Exception as e:  # transport/API failure: archive it, do not count the sample
            rec['error'] = f'{type(e).__name__}: {e}'
            write_json(out / f"{j['sid']}.error.json", rec)
            print('ERROR', j['sid'], rec['error'][:200])
            continue
        rec.update(forecast_turn_index=len(rec['turns']) - 1, stage_done=STAGE, finished_utc=now())
        write_json(p, rec)
        print('done', j['sid'], 'stop:', rec['turns'][-1]['stop_reason'], '(retry)' if rec['parse_retry'] else '')


def parse(fu_path, stub=False):
    """Revised forecasts -> parsed.csv, one row per (sample, still-open problem), with the forecast
    the same conversation gave before the reveal. Only still-open problems are re-forecast, so the
    revealed outcomes are never part of what is compared."""
    fu = load_yaml(fu_path)
    run_cfg, d, _, _, _ = load_checked(ROOT / fu['base_run'])
    fdir = d / 'followups' / fu['followup_id']
    before = {(r['model'], r['sample_idx'], r['code']): r for r in read_csv(d / 'parsed.csv')}
    unit = {r['code']: r['unit_id'] for r in read_csv(d / 'sample.csv')}
    out = []
    for p in sorted((fdir / ('raw_stub' if stub else 'raw')).glob('*__s*[0-9].json')):
        rec = read_json(p)
        final = rec['turns'][rec['forecast_turn_index']]
        try:
            rows, gi = parse_mod.validate(parse_mod.extract_array(final['text']), rec['order'], run_cfg['snapshot_date'])
        except (ValueError, json.JSONDecodeError) as e:
            rows, gi = [{'code': c, 'position': i, 'valid': 0, 'issues': 'unparseable'} for i, c in enumerate(rec['order'])], [str(e)]
        for r in rows:
            b = before.get((rec['model'], str(rec['sample_idx']), r['code']), {})
            r.update(model=rec['model'], returned_model=final.get('returned_model', ''), sample_idx=rec['sample_idx'],
                     unit_id=unit[r['code']], before_best=b.get('best', ''), before_q10=b.get('q10', ''),
                     before_q90=b.get('q90', ''))
            if gi:
                r['issues'] = '; '.join(filter(None, [r.get('issues', ''), 'response: ' + ' | '.join(gi)]))
        out += rows
    dest = fdir / ('parsed_stub.csv' if stub else 'parsed.csv')
    write_csv(dest, out, PARSED_FIELDS)
    print(f"parsed {len(out)} revised forecasts; valid {sum(int(r['valid']) for r in out)} -> {dest}")


LONG_FIELDS = ['model', 'sample_idx', 'unit_id', 'code', 'stratum', 'quantile', 'phase', 'date',
               'after_2100', 'months_from_ref', 'valid']
SUMMARY_FIELDS = ['model', 'quantile', 'phase', 'n', 'n_after_2100', 'share_after_2100',
                  'n_finite', 'mean_months_finite', 'median_months_finite', 'min_months_finite', 'max_months_finite',
                  'median_months_all', 'median_all_is_after_2100', 'max_all_is_after_2100', 'ref_month']


def _median(xs):
    xs = sorted(xs); n = len(xs)
    return (xs[(n - 1) // 2] + xs[n // 2]) / 2


def export(fu_path, stub=False):
    """Tidy CSVs for analysis (e.g. pandas), from followups/<id>/parsed.csv:
    dates_long.csv    one row per (sample, problem, quantile, before/after); months_from_ref is empty
                      for "after-2100" (after_2100 = 1 instead)
    dates_summary.csv per (model, quantile, phase): counts, mean/median/min/max of months over dates up to
                      2100, and the median over all dates with "after-2100" ranked last (empty plus
                      median_all_is_after_2100 = 1 when that median falls on "after-2100").
    Months are counted from the snapshot month (both forecast rounds were answered in it)."""
    fu = load_yaml(fu_path)
    run_cfg, d, _, _, _ = load_checked(ROOT / fu['base_run'])
    fdir = d / 'followups' / fu['followup_id']
    ref = run_cfg['snapshot_date'][:7]
    ry, rm = map(int, ref.split('-'))
    months = lambda v: None if v == 'after-2100' else (int(v[:4]) - ry) * 12 + int(v[5:7]) - rm
    strata = {r['unit_id']: r['stratum'] for r in read_csv(d / 'sample.csv')}
    long = []
    for r in read_csv(fdir / ('parsed_stub.csv' if stub else 'parsed.csv')):
        for q in ('q10', 'best', 'q90'):
            for phase, key in (('before', f'before_{q}'), ('after', q)):
                v = r[key]
                if not v:
                    continue
                mo = months(v)
                long.append({'model': r['model'], 'sample_idx': r['sample_idx'], 'unit_id': r['unit_id'],
                             'code': r['code'], 'stratum': strata.get(r['unit_id'], ''), 'quantile': q,
                             'phase': phase, 'date': v, 'after_2100': int(mo is None),
                             'months_from_ref': '' if mo is None else mo,
                             'valid': r['valid'] if phase == 'after' else ''})
    sfx = '_stub' if stub else ''
    write_csv(fdir / f'dates_long{sfx}.csv', long, LONG_FIELDS)
    summary = []
    for model in sorted({x['model'] for x in long}):
        for q in ('q10', 'best', 'q90'):
            for phase in ('before', 'after'):
                xs = [x for x in long if x['model'] == model and x['quantile'] == q and x['phase'] == phase]
                fin = [x['months_from_ref'] for x in xs if not x['after_2100']]
                ranked = sorted(fin) + [float('inf')] * (len(xs) - len(fin))
                med_all = _median(ranked) if ranked else None
                summary.append({
                    'model': model, 'quantile': q, 'phase': phase, 'n': len(xs),
                    'n_after_2100': len(xs) - len(fin), 'share_after_2100': round((len(xs) - len(fin)) / len(xs), 4),
                    'n_finite': len(fin),
                    'mean_months_finite': round(sum(fin) / len(fin), 2) if fin else '',
                    'median_months_finite': _median(fin) if fin else '',
                    'min_months_finite': min(fin) if fin else '', 'max_months_finite': max(fin) if fin else '',
                    'median_months_all': '' if med_all in (None, float('inf')) else med_all,
                    'median_all_is_after_2100': int(med_all == float('inf')),
                    'max_all_is_after_2100': int(len(fin) < len(xs)), 'ref_month': ref})
    write_csv(fdir / f'dates_summary{sfx}.csv', summary, SUMMARY_FIELDS)
    print(f"{len(long)} rows -> {fdir / f'dates_long{sfx}.csv'}\n{len(summary)} rows -> {fdir / f'dates_summary{sfx}.csv'}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['build', 'submit', 'collect', 'run', 'parse', 'export'])
    ap.add_argument('followup_config')
    ap.add_argument('--wait', action='store_true', help='collect: poll until each batch has ended')
    ap.add_argument('--stub', action='store_true', help='run/parse: offline dry run (raw_stub/)')
    a = ap.parse_args()
    {'build': lambda: build(a.followup_config), 'submit': lambda: submit(a.followup_config),
     'collect': lambda: collect(a.followup_config, a.wait), 'run': lambda: run_direct(a.followup_config, a.stub),
     'parse': lambda: parse(a.followup_config, a.stub), 'export': lambda: export(a.followup_config, a.stub)}[a.cmd]()
    sys.exit(0)
