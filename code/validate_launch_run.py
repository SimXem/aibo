#!/usr/bin/env python3
"""Audit a complete, dated launch snapshot without changing it.

By default the airo experiment alone (the headline series and the policy and
capability panels: redlines/experiments.py, experiments/airo.toml), which is
what the scheduled run elicits since the axes instruments left the schedule
on 2026-09-14. --experiments audits others, e.g. --experiments
airo,axes,paperaxes for a date on which all three were run. Each experiment's
published conditions are audited in its scenario set's log: the pooled ones
make the grid, the rest are warnings when missing or defective.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from redlines import experiments
from redlines.instrument import CURRENT_INSTRUMENT, counting_windows
from redlines.logs import iter_rows, log_files
from redlines.registry import published_panel
from redlines.superseded import is_superseded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=ROOT / 'results')
    parser.add_argument('--date', type=date.fromisoformat, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--experiments', default=experiments.PUBLISHED,
                        help=f'comma-separated experiments to audit (default: {experiments.PUBLISHED})')
    args = parser.parse_args()
    names = [s.strip() for s in args.experiments.split(',') if s.strip()]
    unknown = [s for s in names if s not in experiments.names()]
    if unknown:
        parser.error(f"unknown experiment(s) {unknown}; choose from {experiments.names()}")
    module = importlib.util.spec_from_file_location('launch_runner', ROOT / 'code/run_unified.py')
    ru = importlib.util.module_from_spec(module)
    module.loader.exec_module(ru)
    labels = {m['label'] for m, _ in published_panel()}
    report = {'date': args.date.isoformat(), 'instrument_version': CURRENT_INSTRUMENT,
              'models': sorted(labels), 'experiments': {}, 'errors': [], 'coherence_warnings': [],
              # The debrief (2026-09-15) is asked after the forecasts are accepted
              # and cannot move them, so a missing or incomplete one is a warning
              # for the brief's author, never a reason to withhold the page.
              'debrief_warnings': [],
              # A published condition outside the pooled ones (airo's sixth,
              # "ai-banned", 2026-10-19): asked beside the five, never in the
              # published number, so a missing, short or defective call
              # (check_call) is a warning; the day is complete when the
              # pooled ones are. Its rows must still say what they ran under
              # (check).
              'condition_warnings': []}

    def check(ok, kind, detail):
        if not ok:
            report['errors'].append({'check': kind, 'detail': detail})

    def check_call(ok, kind, detail, row, name):
        """A check on what a CALL returned (its grid, its numbers, its
        rationale, its elicit). On an unpooled call (the sixth, `pooled:
        false`) a failure is a condition warning, never a reason to withhold
        the five; on a pooled call it is an error. What a row must SAY about
        its run (protocol, prompt, windows, dates, its condition's stamps)
        stays an error on every row: that is the code, not the model."""
        if ok:
            return
        if row.get('pooled') is False:
            report['condition_warnings'].append({'experiment': name, 'condition': row.get('condition') or 'none',
                                                 'label': row['label'], 'problem': kind, 'detail': detail})
        else:
            report['errors'].append({'check': kind, 'detail': detail})

    for name in names:
        exp = experiments.load(name)
        conds = {cid: c for cid, c in exp['conditions'].items() if c['publish']}
        sets = {c['scenarios'] for c in conds.values()}
        if len(sets) != 1:
            parser.error(f"experiment {name}: its published conditions ask {sorted(sets)}; "
                         "one scenario set per audited experiment")
        policies = ru.load_policies(ROOT / sets.pop())
        slug = ru.set_slug(policies)
        path = args.results / f'conditional_runs_{slug}.jsonl'
        digest = hashlib.sha256()
        for log_file in log_files(path):
            with log_file.open('rb') as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b''):
                    digest.update(chunk)
        # A draw the same day replaced (redlines.superseded) is not part of
        # the day's grid: without this, a re-run day fails as duplicates.
        rows = [r for r in iter_rows(path) if r.get('run_date') == args.date.isoformat()
                and r.get('instrument_version') == CURRENT_INSTRUMENT
                and not is_superseded(r)]
        policies = ru.resolve_set(policies, args.date)
        scenarios = list(policies['conditions'])
        groups, by_group, horizons, _, spec = ru.load_batch(ru.LADDER, ru.CROSS, ru.UNBATCHED)
        horizons = ru.set_horizons(policies, horizons)
        qs = {q['id']: q for g in groups for q in by_group[g['key']]}
        prompt, n, cells = ru.build_prompt_joint(groups, by_group, horizons, spec, scenarios, policies, args.date)
        prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
        # One call per model per published condition, each with its own
        # prompt. The pooled conditions make the grid; any other (the sixth)
        # is optional per model: absent, or complete.
        pooled = [cid for cid, c in conds.items() if c['pooled']]
        unpooled = {cid: c for cid, c in conds.items() if not c['pooled']}
        minimal = {cid: c['instrument'] == 'minimal' for cid, c in conds.items()}
        prompts = {cid: ru.condition_prompt(prompt, c) for cid, c in conds.items()}
        shas = {cid: hashlib.sha256(p.encode()).hexdigest() for cid, p in prompts.items()}
        scenario_ids = {None} | {c['id'] for c in scenarios}
        expected = {(label, v, q, c) for label in labels for v in pooled for q in qs for c in scenario_ids}
        keys = Counter((r['label'], r.get('condition') or 'none', r['question_id'], (r.get('scenario') or {}).get('id'))
                       for r in rows)
        pooled_keys = Counter({k: n for k, n in keys.items() if k[1] not in unpooled})
        check(set(pooled_keys) == expected and all(v == 1 for v in pooled_keys.values()), 'complete_unique_grid',
              {'experiment': name, 'expected_rows': len(expected), 'actual_rows': sum(pooled_keys.values()),
               'missing': len(expected-set(pooled_keys)), 'extra': len(set(pooled_keys)-expected),
               'duplicates': sum(v-1 for v in pooled_keys.values())})
        unpooled_calls = 0
        for v in unpooled:
            # A condition its cadence did not run that day, and nobody ran by
            # hand, is simply absent (redlines/experiments.py is_due).
            if not experiments.is_due(unpooled[v], args.date) and not any(k[1] == v for k in keys):
                continue
            for label in labels:
                grid = {k: n for k, n in keys.items() if k[0] == label and k[1] == v}
                want = {(label, v, q, c) for q in qs for c in scenario_ids}
                if not grid:
                    report['condition_warnings'].append({'experiment': name, 'condition': v, 'label': label,
                                                         'problem': 'no call'})
                elif set(grid) != want or any(n != 1 for n in grid.values()):
                    report['condition_warnings'].append({'experiment': name, 'condition': v, 'label': label,
                        'problem': 'incomplete grid', 'missing': len(want-set(grid)),
                        'extra': len(set(grid)-want), 'duplicates': sum(n-1 for n in grid.values())})
                else:
                    unpooled_calls += 1
        calls, probabilities = defaultdict(list), {}
        for r in rows:
            q = qs.get(r['question_id'])
            if q is None:
                continue
            v = r.get('condition') or 'none'
            ident = [name, r['label'], v, r['question_id'], (r.get('scenario') or {}).get('id')]
            c = conds.get(v)
            check(c is not None, 'known_condition', ident)
            if c is None:
                continue
            hs = {h for h in horizons if h in q['horizons']}
            fs = r.get('forecasts') or []
            check_call(len(fs) == len(hs) and {f['horizon'] for f in fs} == hs,
                       'complete_horizons', ident, r, name)
            check(r.get('protocol') == policies['protocol'], 'protocol', ident)
            check(r.get('prompt_sha256') == shas.get(v), 'prompt_hash', ident)
            # Every row says what it ran under: the condition's settings (a
            # row from before the stamps existed carries none), whether it is
            # pooled, and its URL guard.
            check(r.get('condition_sha256', c['sha256']) == c['sha256']
                  and r.get('experiment') in (None, name), 'condition_stamp', ident)
            check(r.get('pooled', True) == c['pooled']
                  and r.get('url_block_patterns') == c['url_block_patterns'], 'pooled_stamp', ident)
            check(r.get('counting_window') == counting_windows(q, horizons, args.date, spec),
                  'incident_window', ident)
            check(r.get('resolves_on') == {h: ru.resolves_on(h, args.date, spec) for h in horizons},
                  'resolution_dates', ident)
            for f in fs:
                p = f.get('probability')
                valid = isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(p) and 0 <= p <= 1
                check_call(valid, 'bounded_probability', ident+[f.get('horizon'), p], r, name)
                if valid:
                    probabilities[tuple(ident[1:])+ (f['horizon'],)] = p
            calls[r['call_id']].append(r)
        call_report = []
        for call_id, rs in calls.items():
            retained = [r for r in rs if r.get('prompt')]
            check(len(retained) == 1, 'one_retained_prompt', call_id)
            if retained:
                first = retained[0]
                cid = first.get('condition') or 'none'
                small = minimal.get(cid, False)
                check(first['prompt'] == prompts.get(cid)
                      and first.get('system_prompt') == (ru.MINIMAL_SYSTEM if small else ru.SYSTEM),
                      'exact_prompt_replay', call_id)
                evidence = [e for r in rs for e in r.get('evidence') or []]
                if not small:   # the minimal instrument has no research floor
                    check(len(evidence) >= ru.MIN_RESEARCH and all(r.get('grounded') for r in rs),
                          'grounding_floor', call_id)
                check_call(bool(first.get('rationale')), 'rationale_present', call_id, first, name)
                status = first.get('debrief_status') or {}
                if not small and not (isinstance(first.get('debrief'), dict) and status.get('complete')):
                    report['debrief_warnings'].append({
                        'experiment': name, 'call_id': call_id, 'label': first['label'],
                        'attempts': status.get('attempts'), 'error': status.get('error'),
                        'problems': status.get('problems') or (['no debrief recorded'] if not status else [])})
                for elicit in ru.set_elicits(policies):
                    value = (first.get('elicited') or {}).get(elicit['key'])
                    check_call(bool(ru.clean_elicit(value, elicit)), 'elicited_metadata',
                               [call_id, elicit['key']], first, name)
                call_report.append({'call_id': call_id, 'label': first['label'],
                                    'condition': cid,
                                    'pooled': bool(first.get('pooled', True)), 'rows': len(rs),
                                    'evidence': len(evidence), 'usage': first.get('usage'),
                                    'submission': first.get('delivery')})
        rungs = [r['short'] for r in spec['rungs']]
        legs = [l['key'] for l in spec['legs']]

        def ordered(left, right, kind):
            a, b = probabilities.get(left), probabilities.get(right)
            if a is not None and b is not None and a > b + 1e-9:
                report['coherence_warnings'].append({'experiment': name, 'check': kind,
                    'left': left, 'right': right, 'values': [a, b], 'excess_pp': (a-b)*100})

        for label, v in ((l, v) for l in labels for v in conds):
            for c in scenario_ids:
                for q in qs:
                    hs = sorted([h for h in horizons if h in qs[q]['horizons']],
                                key=lambda h: ru.resolves_on(h, args.date, spec))
                    for h1, h2 in zip(hs, hs[1:]):
                        ordered((label,v,q,c,h1), (label,v,q,c,h2), 'horizon')
                for h in horizons:
                    ordered((label,v,'catastrophe:ai',c,h), (label,v,'catastrophe:general',c,h), 'ai_within_general')
                    for cause in ('ai','cyber','bio','misalign'):
                        for leg in legs:
                            for lo, hi in zip(rungs, rungs[1:]):
                                ordered((label,v,f'ladder:{cause}:{hi}:{leg}',c,h),
                                        (label,v,f'ladder:{cause}:{lo}:{leg}',c,h), 'severity')
                            if cause != 'ai':
                                for rung in rungs:
                                    ordered((label,v,f'ladder:{cause}:{rung}:{leg}',c,h),
                                            (label,v,f'ladder:ai:{rung}:{leg}',c,h), 'subtype_within_ai')
        # 4 x 6 = 24 calls under airo's six conditions; the unpooled ones
        # count where they answered, and are listed as missing where not.
        report['experiments'][name] = {'scenario_set': slug, 'file_sha256': digest.hexdigest(),
            'prompt_sha256': prompt_sha, 'rows': len(rows), 'probabilities': len(probabilities),
            'expected_probabilities': cells * len(scenario_ids) * (len(labels) * len(pooled) + unpooled_calls),
            'expected_calls': len(labels) * len(conds), 'pooled_calls': len(labels) * len(pooled),
            'unpooled_calls': unpooled_calls, 'calls': call_report}
    report['passed_integrity_checks'] = not report['errors']
    report['recorded_cost_usd'] = round(sum((c.get('usage') or {}).get('cost_usd',0)
        for s in report['experiments'].values() for c in s['calls']),6)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'integrity_errors': len(report['errors']),
                      'coherence_warnings': len(report['coherence_warnings']),
                      'debrief_warnings': len(report['debrief_warnings']),
                      'condition_warnings': len(report['condition_warnings']),
                      'recorded_cost_usd': report['recorded_cost_usd'], 'report': str(args.out)}))
    return int(bool(report['errors']))


if __name__ == '__main__':
    raise SystemExit(main())
