"""Shared helpers: paths, hashing, git access, config loading, CSV/JSON I/O."""
import csv
import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / 'archive'      # git bundles + manifest (bundles are not committed; manifest is)
WORK = ROOT / 'work'            # bare clones made from bundles (disposable)
CACHE = ROOT / 'cache'          # fetch mirrors (disposable)
RUNS = ROOT / 'runs'
STATEMENTS = ROOT / 'statements'

REPOS = {
    'erdosproblems': {'url': 'https://github.com/teorth/erdosproblems.git', 'branch': 'main'},
    'formal-conjectures': {'url': 'https://github.com/google-deepmind/formal-conjectures.git', 'branch': 'main'},
}


class PipelineError(Exception):
    """Raised when an input violates a rule; the pipeline halts instead of guessing."""


# ---------- hashing ----------
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode('utf-8'))


def hash_rank(seed: str, key: str) -> str:
    """Portable deterministic ranking key (independent of Python's `random`)."""
    return sha256_text(f'{seed}|{key}')


# ---------- dates ----------
def end_of_day_utc(date_str: str) -> str:
    """'2026-06-30' -> '2026-06-30T23:59:59+00:00' (inclusive end of day, UTC)."""
    d = dt.date.fromisoformat(date_str)
    return dt.datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=dt.timezone.utc).isoformat()


def to_utc_date(iso: str) -> str:
    return dt.datetime.fromisoformat(iso).astimezone(dt.timezone.utc).date().isoformat()


# ---------- git (always against a local bare clone made from an archived bundle) ----------
# `--git-dir` (not `-C`): if a repo dir were ever broken, `-C` would silently fall back to a parent
# repository found by discovery; `--git-dir` fails instead.
def git_cmd(repo_dir):
    return ['git', f'--git-dir={repo_dir}']


def git(repo_dir, *args, check=True) -> str:
    r = subprocess.run([*git_cmd(repo_dir), *args], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if check and r.returncode != 0:
        raise PipelineError(f'git {" ".join(args)} failed: {r.stderr.strip()}')
    return r.stdout


def is_bare_repo(repo_dir) -> bool:
    r = subprocess.run([*git_cmd(repo_dir), 'rev-parse', '--is-bare-repository'], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == 'true'


def rmtree(path):
    """Delete a tree, including read-only files (git pack files on Windows)."""
    import shutil
    import stat

    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if Path(path).exists():
        shutil.rmtree(path, onerror=onerror)


def work_repo(name) -> Path:
    return WORK / f'{name}.git'


# ---------- config ----------
def load_yaml(p):
    with open(p, encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_run_config(run_cfg_path):
    run = load_yaml(run_cfg_path)
    wave = load_yaml(ROOT / 'config' / 'waves' / f"{run['wave']}.yaml")
    rules = load_yaml(ROOT / 'rules' / f"{wave['rules_version']}.yaml")
    return run, wave, rules


def run_dir(run):
    d = RUNS / run['run_id']
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------- deterministic output ----------
def write_csv(path, rows, fields):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
        w.writeheader()
        for r in rows:
            w.writerow({k: ('' if r.get(k) is None else r.get(k)) for k in fields})


def read_csv(path):
    with open(path, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def write_json(path, obj):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write('\n')


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def source_hash() -> str:
    """Hash of the pipeline's own code, rules and templates (works without commits)."""
    h = hashlib.sha256()
    for sub in ('pipeline', 'rules', 'templates'):
        for p in sorted((ROOT / sub).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                h.update(str(p.relative_to(ROOT)).replace(os.sep, '/').encode())
                h.update(p.read_bytes())
    return h.hexdigest()
