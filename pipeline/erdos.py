"""Erdős DB (teorth/erdosproblems): status at a commit and status history over a commit range."""
import re

import yaml

from .common import PipelineError
from .snapshot import CatFile, first_parent_commits

try:
    _Loader = yaml.CSafeLoader
except AttributeError:  # pragma: no cover
    _Loader = yaml.SafeLoader

REPO = 'erdosproblems'


def classify(state, rules):
    r = rules['erdos']
    if state in r['open_states']:
        return 'open'
    if state in r['solved_states']:
        return 'solved'
    if state in r['partial_states']:
        return 'partial'
    raise PipelineError(f'unknown Erdős DB status {state!r}: add it to rules (new rules version)')


def parse(text, rules):
    """-> {number: {'state','class','date','prize','tags'}}"""
    r = rules['erdos']
    data = yaml.load(text, Loader=_Loader)
    out = {}
    for e in data:
        num = str(e['number'])
        field = next((f for f in r['status_fields'] if isinstance(e.get(f), dict) and 'state' in e[f]), None)
        if field is None:
            raise PipelineError(f'Erdős #{num}: no status field among {r["status_fields"]}')
        state = re.sub(r['strip_suffix_regex'], '', str(e[field]['state'])).strip()
        out[num] = {'state': state, 'class': classify(state, rules),
                    'date': str(e[field].get('last_update', '')),
                    'prize': str(e.get('prize', '')), 'tags': ';'.join(e.get('tags') or [])}
    return out


def history(c_t0, c_s, rules):
    """Status at C_T0, final status at C_S and per-problem class transitions in (C_T0, C_S]."""
    path = rules['erdos']['path']
    cf = CatFile(REPO)
    try:
        _, txt = cf.get(f'{c_t0}:{path}')
        at_t0 = parse(txt, rules)
        prev, cache = at_t0, {}
        transitions = {}   # number -> [ {commit, committer_date, subject, from, to, state, date} ]
        for c in first_parent_commits(REPO, c_t0, c_s, path):
            blob, txt = cf.get(f"{c['sha']}:{path}")
            if blob is None:
                raise PipelineError(f'{path} missing at {c["sha"]}')
            cur = cache.get(blob) or parse(txt, rules)
            cache = {blob: cur}
            for num, e in cur.items():
                p = prev.get(num)
                if p is not None and p['class'] != e['class']:
                    transitions.setdefault(num, []).append({
                        'commit': c['sha'], 'committer_date': c['committer_date'], 'subject': c['subject'],
                        'from': p['class'], 'to': e['class'], 'state': e['state'], 'date': e['date']})
            prev = cur
        return at_t0, prev, transitions
    finally:
        cf.close()
