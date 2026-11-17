"""Stage: eligible frame at T0 (depends only on T0 commits and rules, never on S)."""
import re

from . import erdos, fc
from .common import PipelineError
from .snapshot import CatFile

FRAME_FIELDS = ['unit_id', 'source', 'collection', 'stratum', 'display_name', 'fc_path_t0', 'fc_blob_t0',
                'headline', 'n_headline', 'prize', 'tags', 'erdos_state_t0']
EXCL_FIELDS = ['unit_id', 'source', 'collection', 'reason']


def _headline(decls, rules):
    rx = re.compile(rules['fc']['headline_exclude_regex'])
    return [d for d in decls if d['category'] == 'open' and not rx.search(d['name'])]


def _stratum(source, collection, rules):
    if source == 'erdos':
        return 'erdos'
    return 'fc_named' if collection in rules['fc']['named_dirs'] else 'fc_other'


def build(c_t0_erdos, c_t0_fc, rules):
    r = rules['fc']
    cf = CatFile(erdos.REPO)
    try:
        _, txt = cf.get(f"{c_t0_erdos}:{rules['erdos']['path']}")
    finally:
        cf.close()
    edb = erdos.parse(txt, rules)
    cf = CatFile(fc.REPO)
    try:
        idx = fc.Index(rules)
        idx.load(c_t0_fc, cf)
    finally:
        cf.close()

    units, excl = [], []
    erdos_prefix = f"{r['root']}/{r['erdos_dir']}/"

    def check_issue(path, f):
        if f['issue']:
            raise PipelineError(f'unparseable attributes in {path} ({f["issue"]}); fix parser, bump rules version')

    # Erdős units: status from the Erdős DB, statement text + second status source from FC.
    for num in sorted(edb, key=int):
        e = edb[num]
        uid = f'erdos:{num}'
        path = f'{erdos_prefix}{num}.lean'
        f = idx.files.get(path)
        reason = None
        if e['class'] == 'partial':
            reason = f"Erdős DB state '{e['state']}' at T0 (partial meta-result)"
        elif e['class'] == 'solved':
            reason = f"solved at T0 (Erdős DB: {e['state']})"
        elif f is None:
            reason = 'no Formal Conjectures file at T0 (no statement text)'
        else:
            head = _headline(f['decls'], rules)
            if not head:
                reason = ('solved at T0 (FC: no open headline theorem)' if f['decls']
                          else 'FC file has no research theorem at T0')
        if reason:
            excl.append({'unit_id': uid, 'source': 'erdos', 'collection': 'ErdosProblems', 'reason': reason})
            continue
        check_issue(path, f)
        units.append({'unit_id': uid, 'source': 'erdos', 'collection': 'ErdosProblems', 'stratum': 'erdos',
                      'display_name': f'Erdős Problem {num}', 'fc_path_t0': path, 'fc_blob_t0': f['blob'],
                      'headline': ';'.join(d['name'] for d in head), 'n_headline': len(head),
                      'prize': e['prize'], 'tags': e['tags'], 'erdos_state_t0': e['state']})

    # FC units (all other collections).
    for path in sorted(idx.files):
        if path.startswith(erdos_prefix):
            continue
        f = idx.files[path]
        rel = path[len(r['root']) + 1:-len('.lean')]
        coll = rel.split('/')[0]
        uid = f'fc:{rel}'
        head = _headline(f['decls'], rules)
        reason = None
        if coll in r.get('exclude_collections', []):
            reason = 'collection excluded by rules'
        elif not f['decls']:
            reason = 'no research theorem'
        elif not head:
            reason = 'solved at T0 (FC: no open headline theorem)'
        elif len(head) > r['headline_max']:
            reason = f'{len(head)} headline theorems (> {r["headline_max"]})'
        if reason:
            excl.append({'unit_id': uid, 'source': 'fc', 'collection': coll, 'reason': reason})
            continue
        check_issue(path, f)
        units.append({'unit_id': uid, 'source': 'fc', 'collection': coll, 'stratum': _stratum('fc', coll, rules),
                      'display_name': f"{coll}: {f['title'] or rel.split('/')[-1]}", 'fc_path_t0': path, 'fc_blob_t0': f['blob'],
                      'headline': ';'.join(d['name'] for d in head), 'n_headline': len(head),
                      'prize': '', 'tags': '', 'erdos_state_t0': ''})
    return units, excl, idx
