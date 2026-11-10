"""Stage 1 (network): mirror both trackers and archive each new HEAD as a git bundle.

Bundles are append-only: an existing bundle is never rewritten. All later stages read
only from bare clones made from bundles (see `restore`), never from the network.

    python -m pipeline.fetch            # fetch + archive + restore work clones
    python -m pipeline.fetch --restore  # rebuild work clones from archived bundles only
"""
import argparse
import datetime as dt

import subprocess

from .common import (ARCHIVE, CACHE, REPOS, WORK, PipelineError, git, git_cmd, is_bare_repo, read_json, rmtree,
                     sha256_file, work_repo, write_json)

MANIFEST = ARCHIVE / 'manifest.json'


def _manifest():
    return read_json(MANIFEST) if MANIFEST.exists() else {'bundles': []}


def fetch():
    CACHE.mkdir(exist_ok=True); ARCHIVE.mkdir(exist_ok=True)
    man = _manifest()
    for name, spec in REPOS.items():
        mirror = CACHE / f'{name}.git'
        if mirror.exists() and not is_bare_repo(mirror):
            rmtree(mirror)
        if mirror.exists():
            git(mirror, 'fetch', '--prune', 'origin', '+refs/heads/*:refs/heads/*')
        else:
            subprocess.run(['git', 'clone', '--mirror', '-q', spec['url'], str(mirror)], check=True)
        head = git(mirror, 'rev-parse', f"refs/heads/{spec['branch']}").strip()
        bundle = ARCHIVE / f'{name}-{head}.bundle'
        known = {b['file'] for b in man['bundles']}
        if bundle.name not in known:
            git(mirror, 'bundle', 'create', str(bundle), f"refs/heads/{spec['branch']}")
            man['bundles'].append({
                'repo': name, 'url': spec['url'], 'branch': spec['branch'], 'head': head,
                'file': bundle.name, 'sha256': sha256_file(bundle),
                'head_commit_date': git(mirror, 'show', '-s', '--format=%cI', head).strip(),
                'fetched_utc': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            })
            print(f'archived {bundle.name}')
        # history-rewrite check: every previously archived head must still be an ancestor
        for b in man['bundles']:
            if b['repo'] == name and b['head'] != head:
                ok = subprocess.run([*git_cmd(mirror), 'merge-base', '--is-ancestor', b['head'], head]).returncode == 0
                b.setdefault('upstream_rewrite_detected', False)
                if not ok and not b['upstream_rewrite_detected']:
                    b['upstream_rewrite_detected'] = True
                    print(f"WARNING: {name} upstream no longer contains archived head {b['head']}; bundle kept")
    write_json(MANIFEST, man)


def restore():
    """Make each work clone contain the union of all archived bundles for that repo."""
    man = _manifest()
    WORK.mkdir(exist_ok=True)
    for name, spec in REPOS.items():
        bundles = [b for b in man['bundles'] if b['repo'] == name]
        if not bundles:
            raise PipelineError(f'no archived bundle for {name}; run fetch first')
        repo = work_repo(name)
        if repo.exists() and not is_bare_repo(repo):
            rmtree(repo)          # broken leftover: never let git fall back to another repository
        if not repo.exists():
            subprocess.run(['git', 'init', '-q', '--bare', str(repo)], check=True)
        if not is_bare_repo(repo):
            raise PipelineError(f'{repo} is not a bare git repository')
        for b in bundles:
            p = ARCHIVE / b['file']
            if sha256_file(p) != b['sha256']:
                raise PipelineError(f'bundle checksum mismatch: {p}')
            git(repo, 'fetch', '-q', str(p), f"refs/heads/{spec['branch']}:refs/archive/{b['head']}")
    print('work clones restored from', len(man['bundles']), 'bundle(s)')


def latest_archived_head(name):
    bs = [b for b in _manifest()['bundles'] if b['repo'] == name]
    if not bs:
        raise PipelineError(f'no archived bundle for {name}')
    return max(bs, key=lambda b: b['head_commit_date'])['head']


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--restore', action='store_true', help='skip network; rebuild work clones from bundles')
    a = ap.parse_args()
    if not a.restore:
        fetch()
    restore()
