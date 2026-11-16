"""Freeze the last published Baseline ensemble before starting shadow workers."""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from statistics import median
from datetime import date
from fri_forecaster.prior_forecast import URL, PATH_ENV, HASH_ENV

SENTENCE = f'The previous AIRO Baseline ensemble forecast is available at {URL}.'


def freeze(publication, results, directory=None, definitions=None):
    site = Path(publication).resolve(strict=True)
    html = (site / 'index.html').read_text()
    match = re.search(r'window\.__TIMELINE__\s*=\s*(.*?);\s*</script>', html, re.S)
    if not match:
        raise ValueError('published timeline missing')
    timeline = json.loads(match[1])
    snap = timeline['snapshots'][-1]
    if date.fromisoformat(snap['date']) > date.today():
        raise ValueError('future published forecast')
    i = len(timeline['snapshots']) - 1
    questions = []
    for q in timeline['questions']:
        if q.get('value_kind') != 'probability':
            continue
        values = {h: q.get('variants', {}).get('none', {}).get(h, [])[i]
                  for h in q['horizons']}
        if any(v is None for v in values.values()):
            raise ValueError('incomplete published Baseline forecast')
        questions.append(dict(id=q['id'], question=q['text'], criteria=q.get('criteria'),
                              probability_percent=values))
    if not questions:
        raise ValueError('no published Baseline questions')
    # ECI is elicited alongside the risk grid. Read only the published run IDs,
    # never the latest raw file (which may be today's unpublished run).
    raw_rows = {}
    models = {}
    labels = set()
    qmodels = {}
    for run in snap['runs']:
        if Path(run).name != run:
            raise ValueError('invalid published run ID')
        for line in (Path(results) / 'runs' / f'{run}.jsonl').open():
            row = json.loads(line)
            if row.get('condition') != 'none':
                continue
            if row['run_date'] != snap['date']:
                raise ValueError('published and raw dates differ')
            raw_rows[row['question_id'], row['model']] = row
            qmodels.setdefault(row['question_id'], set()).add(row['model'])
            models[row['model']] = row['elicited']
            labels.add(row.get('label', row['model']))
    if not models or any(qmodels.get(q['id']) != set(models) for q in questions):
        raise ValueError('incomplete source Baseline panel')
    for q in questions:
        published_q = next(x for x in timeline['questions'] if x['id'] == q['id'])
        for h in q['probability_percent']:
            panel = published_q['variantModels']['none'][h][i]
            if set(panel) != labels or any(v is None for v in panel.values()):
                raise ValueError('published and raw Baseline panels differ')
    if definitions is None:
        from .questions import questions_asked_on
        from .instrument import CURRENT_INSTRUMENT
        if snap['instrumentVersion'] != CURRENT_INSTRUMENT:
            raise ValueError('prior instrument differs; explicit migration required')
        definitions = questions_asked_on(snap['date'])
    questions = []
    for qid in sorted(qmodels):
        q = definitions[qid]
        if qmodels[qid] != set(models):
            raise ValueError('incomplete Baseline question panel')
        answers = [raw_rows[qid, m] for m in models]
        estimates = [{f['horizon']: f['probability'] for f in r['forecasts']} for r in answers]
        hs = set(q['horizons'])
        if any(set(e) != hs or any(e[h] is None for h in hs) for e in estimates):
            raise ValueError('incomplete Baseline horizons')
        questions.append(dict(id=qid, question=q['text'],
                              resolves_on=answers[0]['resolves_on'],
                              probability_percent={h: median(e[h] for e in estimates) * 100 for h in sorted(hs)}))
    targets = {m['target_date'] for m in models.values()}
    if len(targets) != 1:
        raise ValueError('mixed ECI target dates')
    data = dict(schema='prior-baseline-v1', forecast_date=snap['date'],
                aggregation='Median across models in the Baseline condition',
                counting_windows=snap['instrumentInfo']['countingWindows'],
                eci_forecast=dict(target_date=targets.pop(), **{
                    k: median(m['eci_forecast'][k] for m in models.values())
                    for k in ('p10', 'p25', 'p50', 'p75', 'p90')}),
                questions=questions)
    raw = (json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    sha = hashlib.sha256(raw).hexdigest()
    folder = Path(directory or Path(results) / 'experiments/prior-baseline-snapshots')
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'{sha}.json'
    fd, tmp = tempfile.mkstemp(dir=folder)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return dict(path=str(target.resolve()), sha256=sha, forecast_date=snap['date'],
                source_runs=snap['runs'], models=len(models), questions=len(questions))

SELF_SENTENCE = f'The previous ensemble forecast is available at {URL}.'


def load_self(results, publication, seed=False):
    latest = Path(results) / 'experiments/prior-recent-shadow/latest.json'
    if latest.exists():
        frozen = json.loads(latest.read_text())
        raw = Path(frozen['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != frozen['sha256']:
            raise ValueError('prior-recent snapshot hash mismatch')
        return frozen
    if not seed:
        raise ValueError('no prior-recent ensemble: explicitly bootstrap with --seed-prior-baseline')
    return freeze(publication, results)


def save_self(output, run_id, condition, panel, results):
    """Advance only after the entire panel produced a complete unconditional grid."""
    expected = {model for label, model in panel}
    rows = {}
    for line in Path(output).open():
        row = json.loads(line)
        if row.get('run_id') == run_id and row.get('condition') == condition['id']:
            rows[(row['question_id'], row['model'])] = row
    prior = json.loads(Path(condition['_prior_snapshot']['path']).read_text())
    questions = prior['questions']
    qids = {q['id'] for q in questions}
    if set(rows) != {(q, m) for q in qids for m in expected}:
        raise ValueError('incomplete prior-recent panel; prior snapshot retained')
    for q in questions:
        estimates = [{f['horizon']: f['probability'] for f in rows[q['id'], m]['forecasts']} for m in expected]
        horizons = set(q['probability_percent'])
        if any(set(e) != horizons or any(e[h] is None for h in horizons) for e in estimates):
            raise ValueError('incomplete prior-recent horizons; prior snapshot retained')
        q['probability_percent'] = {h: median(e[h] for e in estimates) * 100 for h in sorted(horizons)}
    sample = next(iter(rows.values()))
    for q in questions:
        q['resolves_on'] = rows[q['id'], next(iter(expected))]['resolves_on']
    windows = next((r['counting_window'] for r in rows.values() if r.get('counting_window')), {})
    prior.update(forecast_date=sample['run_date'],
                 aggregation='Median across models in the prior-recent-shadow condition',
                 counting_windows=windows)
    elicits = [rows[next(iter(qids)), m]['elicited'] for m in expected]
    if len({e['target_date'] for e in elicits}) != 1:
        raise ValueError('mixed ECI target dates')
    prior['eci_forecast'] = dict(target_date=elicits[0]['target_date'], **{
        k: median(e['eci_forecast'][k] for e in elicits) for k in ('p10', 'p25', 'p50', 'p75', 'p90')})
    raw = (json.dumps(prior, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    sha = hashlib.sha256(raw).hexdigest()
    folder = Path(results) / 'experiments/prior-recent-shadow'
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f'{sha}.json'
    dest.write_bytes(raw)
    frozen = dict(path=str(dest.resolve()), sha256=sha, forecast_date=sample['run_date'],
                  source_runs=[run_id], models=len(expected), questions=len(qids))
    fd, tmp = tempfile.mkstemp(dir=folder)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(frozen, f)
        os.replace(tmp, folder / 'latest.json')
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return frozen
