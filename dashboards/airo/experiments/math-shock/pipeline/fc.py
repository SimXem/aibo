"""Formal Conjectures: parse Lean files (theorem name, research category, docstring, statement) and
track per-theorem category over the first-parent history, following file renames.

Theorems are identified by fully-qualified name, so moved or renamed files keep their identity.
A file whose count of `category research ...` occurrences does not match the parsed declarations is
recorded as a parse issue; the frame stage halts if such a file backs a unit.
"""
import re

from .common import PipelineError, git, work_repo
from .snapshot import CatFile, first_parent_commits

REPO = 'formal-conjectures'

_SETOPT = r'(?:set_option[^\n]*?\bin\s+)*'
_DOC = r'(?:/--(?P<doc>(?:(?!-/).)*)-/\s*)?'
_COMMENTS = r'(?:--[^\n]*\n\s*)*'      # line comments may sit between attributes and the keyword
_ATTRS = r'(?P<attrs>(?:@\[(?:[^\[\]"]|"[^"]*"|\[[^\[\]]*\])*\]\s*' + _COMMENTS + r')+)'
_MODS = r'(?:(?:private|protected|noncomputable|nonrec)\s+)*'
# `example` has no name; research-tagged examples/defs are parsed so the attribute count check passes,
# and examples are then dropped (they cannot be tracked by name).
DECL = re.compile(_SETOPT + _DOC + _SETOPT + _ATTRS + _MODS +
                  r'(?P<kw>theorem|lemma|def|abbrev|instance|example)\b\s*(?P<name>[^\s:(\[{]*)', re.S)
CAT = re.compile(r'\bcategory\s+([A-Za-z_]+(?:\s+(?:formally\s+)?(?:open|solved))?)')
CAT_TEXT = re.compile(r'@\[[^\]]*?\bcategory\s+research\b', re.S)
NS = re.compile(r'^[ \t]*(?:(namespace)[ \t]+(\S+)|(?:noncomputable[ \t]+)?(section)(?:[ \t]+(\S+))?|(end)(?:[ \t]+(\S+))?)[ \t]*(?:--.*)?$', re.M)
TITLE = re.compile(r'/-!.*?^#\s+(.+?)\s*$', re.S | re.M)


def _namespaces(text):
    """Return a function pos -> current namespace prefix."""
    events, stack = [], []
    for m in NS.finditer(text):
        if m.group(1):
            stack.append(('ns', m.group(2)))
        elif m.group(3):
            stack.append(('sec', m.group(4) or ''))
        elif m.group(5):
            name = m.group(6) or ''
            if name:
                while stack:
                    k, n = stack.pop()
                    if n == name:
                        break
            elif stack:
                stack.pop()
        events.append((m.start(), '.'.join(n for k, n in stack if k == 'ns')))

    def at(pos):
        cur = ''
        for p, ns in events:
            if p > pos:
                break
            cur = ns
        return cur
    return at


def classify_category(raw, rules):
    r = rules['fc']
    raw = ' '.join(raw.split())
    if raw in r['open_categories']:
        return 'open'
    if raw in r['solved_categories']:
        return 'solved'
    if raw.split()[0] in r['other_categories']:
        return None
    raise PipelineError(f'unknown FC category {raw!r}: add it to rules (new rules version)')


def parse_lean(text, rules):
    """-> (decls, title, issue). decls: list of {name, category, doc, stmt}."""
    ns_at = _namespaces(text)
    decls = []
    for m in DECL.finditer(text):
        cm = CAT.search(m.group('attrs'))
        if not cm:
            continue
        cat = classify_category(cm.group(1), rules)
        name = m.group('name')
        if cat is None or m.group('kw') == 'example' or not name:
            continue
        if name.startswith('_root_.'):
            full = name[len('_root_.'):]
        else:
            ns = ns_at(m.start('kw'))
            full = f'{ns}.{name}' if ns else name
        start = m.start('kw')
        rest = text[start:start + 4000]
        end = rest.find(':= by')
        stmt = rest[:end] if end > 0 else rest[:rest.find(':=')] if rest.find(':=') > 0 else rest[:1500]
        decls.append({'name': full, 'category': cat, 'doc': (m.group('doc') or '').strip(), 'stmt': stmt.strip()})
    n_text = len(CAT_TEXT.findall(text))
    n_research = sum(1 for m in DECL.finditer(text) if CAT.search(m.group('attrs')) and
                     CAT.search(m.group('attrs')).group(1).startswith('research'))
    issue = '' if n_text == n_research else f'{n_text} research attributes in text, {n_research} parsed'
    t = TITLE.search(text)
    return decls, (t.group(1).strip() if t else ''), issue


def lean_paths(commit, rules):
    r = rules['fc']
    out = git(work_repo(REPO), 'ls-tree', '-r', '--name-only', commit, '--', r['root']).splitlines()
    excl = tuple(f"{r['root']}/{d}/" for d in r['exclude_dirs'])
    return [p for p in out if p.endswith('.lean') and not p.startswith(excl)]


class Index:
    """Theorem-name -> {path: category} at one point in history, updated commit by commit."""

    def __init__(self, rules):
        self.rules = rules
        self.files = {}     # path -> {'blob', 'decls', 'title', 'issue'}
        self.by_name = {}   # name -> {path: category}

    def _remove(self, path):
        info = self.files.pop(path, None)
        if info:
            for d in info['decls']:
                occ = self.by_name.get(d['name'], {})
                occ.pop(path, None)
                if not occ:
                    self.by_name.pop(d['name'], None)
        return info

    def _add(self, path, blob, text):
        decls, title, issue = parse_lean(text, self.rules)
        self.files[path] = {'blob': blob, 'decls': decls, 'title': title, 'issue': issue}
        for d in decls:
            self.by_name.setdefault(d['name'], {})[path] = d['category']
        return decls

    def load(self, commit, cf):
        for p in lean_paths(commit, self.rules):
            blob, text = cf.get(f'{commit}:{p}')
            self._add(p, blob, text)

    def status(self, names):
        """'solved' iff every name exists and all its occurrences are solved; 'missing' if a name vanished."""
        st = []
        for n in names:
            occ = self.by_name.get(n)
            if not occ:
                return 'missing'
            st.append('open' if 'open' in occ.values() else 'solved')
        return 'solved' if all(s == 'solved' for s in st) else 'open'

    def path_of(self, name):
        occ = self.by_name.get(name, {})
        return sorted(occ)[0] if occ else ''


def _changes(commit):
    """Name-status of a first-parent commit (renames detected)."""
    out = git(work_repo(REPO), 'diff-tree', '-r', '-M', '--name-status', '--no-commit-id',
              f'{commit}^1', commit)
    for line in out.splitlines():
        parts = line.split('\t')
        code = parts[0][0]
        if code in 'RC':
            yield code, parts[1], parts[2]
        else:
            yield code, parts[1], parts[1]


def history(c_t0, c_s, units, rules):
    """Walk (C_T0, C_S]. units: {unit_id: [headline names]}.

    Returns (index_t0_files, index_s, unit_transitions, issues_s) where unit_transitions[unit_id] is a
    list of {commit, committer_date, subject, from, to}.
    """
    cf = CatFile(REPO)
    try:
        idx = Index(rules)
        idx.load(c_t0, cf)
        files_t0 = {p: dict(v) for p, v in idx.files.items()}
        by_name_unit = {}
        for u, names in units.items():
            for n in names:
                by_name_unit.setdefault(n, set()).add(u)
        cur = {u: idx.status(names) for u, names in units.items()}
        trans = {}
        root = rules['fc']['root']
        excl = tuple(f"{root}/{d}/" for d in rules['fc']['exclude_dirs'])
        for c in first_parent_commits(REPO, c_t0, c_s, root):
            touched = set()
            for code, old, new in _changes(c['sha']):
                for p in {old, new}:
                    info = idx.files.get(p)
                    if info:
                        touched.update(d['name'] for d in info['decls'])
                if code in 'DR':
                    idx._remove(old)
                if code != 'D' and new.endswith('.lean') and new.startswith(root + '/') and not new.startswith(excl):
                    idx._remove(new)
                    blob, text = cf.get(f"{c['sha']}:{new}")
                    if blob is not None:
                        touched.update(d['name'] for d in idx._add(new, blob, text))
            for u in {u for n in touched for u in by_name_unit.get(n, ())}:
                st = idx.status(units[u])
                if st != cur[u]:
                    trans.setdefault(u, []).append({'commit': c['sha'], 'committer_date': c['committer_date'],
                                                    'subject': c['subject'], 'from': cur[u], 'to': st})
                    cur[u] = st
        return files_t0, idx, trans
    finally:
        cf.close()


def file_text(commit, path):
    cf = CatFile(REPO)
    try:
        return cf.get(f'{commit}:{path}')
    finally:
        cf.close()
