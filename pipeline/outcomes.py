"""Stage: status at S, solve date and outcome type per frame unit; literature-find rule (D9)."""
import datetime as dt
import re

from . import erdos, fc
from .common import git, to_utc_date, work_repo

OUT_FIELDS = ['unit_id', 'solved', 'solve_date', 'outcome_type', 'date_source',
              'erdos_state_s', 'erdos_solved', 'erdos_date', 'erdos_commit', 'erdos_recorded_date',
              'fc_status_s', 'fc_solved', 'fc_date', 'fc_commit', 'sources_disagree', 'reversal_in_window',
              'literature_find', 'literature_evidence', 'docstring_refs_s', 'docstring_refs_all_pre_t0', 'flags']
TRANS_FIELDS = ['unit_id', 'source', 'commit', 'committer_date', 'from', 'to', 'state', 'recorded_date', 'subject']


def _last_to_solved(trans, to_key='to'):
    ts = [t for t in trans if t[to_key] == 'solved']
    return ts[-1] if ts else None


def _commit_message(repo, sha):
    return git(work_repo(repo), 'show', '-s', '--format=%B', sha)


def _added_lines(sha, paths):
    out = git(work_repo(fc.REPO), 'show', '--format=', '-M', '--unified=0', sha, '--', *paths)
    return [l[1:] for l in out.splitlines() if l.startswith('+') and not l.startswith('+++')]


def _ref_dates(lines, lr):
    """-> list of (year, month or None) found in reference-like patterns."""
    refs = []
    ign = re.compile(lr['ignore_line_regex'])
    for line in lines:
        if ign.search(line):
            continue
        for m in re.finditer(lr['arxiv_regex'], line):
            refs.append((2000 + int(m.group(1)), int(m.group(2))))
        for m in re.finditer(lr['citekey_regex'], line):
            yy = int(m.group(1))
            refs.append((2000 + yy if yy <= lr['citekey_century_pivot'] else 1900 + yy, None))
        for m in re.finditer(lr['paren_year_regex'], line):
            refs.append((int(m.group(1)), None))
    return refs


def _predates(ref, t0):
    y, m = ref
    if m is None:
        return y < t0.year
    return (y, m) < (t0.year, t0.month)


def _decl(files, name):
    for f in files.values():
        for d in f['decls']:
            if d['name'] == name:
                return d
    return None


def _fmt(refs):
    return ', '.join(f'{y}-{m:02d}' if m else str(y) for y, m in refs)


def compute(units, c_t0, c_s, rules, t0, s_date):
    t0d, sd = dt.date.fromisoformat(t0), dt.date.fromisoformat(s_date)
    lr = rules['literature_rule']
    _, edb_s, etrans = erdos.history(c_t0['erdosproblems'], c_s['erdosproblems'], rules)
    names = {u['unit_id']: u['headline'].split(';') for u in units}
    files_t0, idx_s, ftrans = fc.history(c_t0['formal-conjectures'], c_s['formal-conjectures'], names, rules)

    outs, trows = [], []
    for u in units:
        uid = u['unit_id']
        o = {'unit_id': uid, 'flags': []}
        # --- Erdős DB side
        e_date = e_solved = None
        if u['source'] == 'erdos':
            num = uid.split(':')[1]
            es = edb_s.get(num)
            o['erdos_state_s'] = es['state'] if es else 'missing'
            e_solved = bool(es and es['class'] == 'solved')
            tr = etrans.get(num, [])
            for t in tr:
                trows.append({'unit_id': uid, 'source': 'erdos', 'commit': t['commit'], 'committer_date': t['committer_date'],
                              'from': t['from'], 'to': t['to'], 'state': t['state'], 'recorded_date': t['date'],
                              'subject': t['subject']})
            if es and es['class'] == 'partial':
                o['flags'].append(f"Erdős DB partial state at S: {es['state']}")
            last = _last_to_solved(tr) if e_solved else None
            if last:
                # Solve date = commit date (rules: erdos.date_source). The curated last_update field
                # is kept for information; it was found stale in most transitions.
                e_date = to_utc_date(last['committer_date'])
                o.update(erdos_commit=last['commit'], erdos_commit_date=e_date, erdos_recorded_date=last['date'])
            o['erdos_solved'] = int(e_solved)
            o['erdos_date'] = e_date or ''
        # --- FC side
        fst = idx_s.status(names[uid])
        o['fc_status_s'] = fst
        if fst == 'missing':
            o['flags'].append('FC headline theorem no longer found by name at S (treated as not solved)')
        f_solved = fst == 'solved'
        ftr = ftrans.get(uid, [])
        for t in ftr:
            trows.append({'unit_id': uid, 'source': 'fc', 'commit': t['commit'], 'committer_date': t['committer_date'],
                          'from': t['from'], 'to': t['to'], 'state': '', 'recorded_date': '', 'subject': t['subject']})
        f_date = None
        if f_solved:
            last = _last_to_solved(ftr)
            f_date = to_utc_date(last['committer_date'])
            o['fc_commit'] = last['commit']
        o['fc_solved'] = int(f_solved)
        o['fc_date'] = f_date or ''
        # --- union (D2)
        solved = bool(e_solved) or f_solved
        o['solved'] = int(solved)
        o['sources_disagree'] = int(u['source'] == 'erdos' and bool(e_solved) != f_solved)
        etr = etrans.get(uid.split(':')[1], []) if u['source'] == 'erdos' else []
        o['reversal_in_window'] = int(any(t['from'] == 'solved' for t in etr + ftr))
        if solved:
            cands = [(d, s) for d, s in ((e_date, 'erdos_db'), (f_date, 'formal_conjectures')) if d]
            o['solve_date'], o['date_source'] = min(cands)
            o['outcome_type'] = o['erdos_state_s'] if e_solved else 'resolved'
            # --- literature rule (D9)
            msgs, lines = [], []
            if o.get('erdos_commit'):
                msgs.append(_commit_message(erdos.REPO, o['erdos_commit']))
            if o.get('fc_commit'):
                msgs.append(_commit_message(fc.REPO, o['fc_commit']))
                p_s = idx_s.path_of(names[uid][0])
                lines = _added_lines(o['fc_commit'], sorted({u['fc_path_t0'], p_s} - {''}))
            low = '\n'.join(msgs).lower()
            kw = [k for k in lr['message_keywords'] if k in low]
            refs = _ref_dates(lines, lr)
            if kw:
                o['literature_find'] = 1
                o['literature_evidence'] = 'commit message: ' + ', '.join(kw)
            elif refs and all(_predates(r, t0d) for r in refs):
                o['literature_find'] = 1
                o['literature_evidence'] = 'all added refs predate T0: ' + ', '.join(f'{y}-{m:02d}' if m else str(y) for y, m in refs)
            else:
                o['literature_find'] = 0
                o['literature_evidence'] = ('refs: ' + _fmt(refs)) if refs else 'no dated refs'
            # diagnostic only (not a selection rule in rules_v1): references cited in the headline
            # docstrings at S.
            dl = [d['doc'] for n in names[uid] if idx_s.by_name.get(n) for d in [_decl(idx_s.files, n)] if d]
            drefs = _ref_dates('\n'.join(dl).splitlines(), lr)
            o['docstring_refs_s'] = _fmt(drefs)
            o['docstring_refs_all_pre_t0'] = int(bool(drefs) and all(_predates(r, t0d) for r in drefs))
        else:
            o['literature_find'] = 0
        o['flags'] = ' | '.join(o['flags'])
        outs.append(o)
    trows.sort(key=lambda t: (t['unit_id'], t['committer_date'], t['source']))
    return outs, trows
