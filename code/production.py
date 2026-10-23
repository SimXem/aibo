#!/usr/bin/env python3
"""Explicit releases and durable UTC jobs. Configuration and data stay outside git."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import http.client
import hashlib
from http.server import SimpleHTTPRequestHandler
import json
import os
from pathlib import Path
import re
import shutil
import socket
from socketserver import ThreadingUnixStreamServer
import subprocess
import sys
import uuid

REQUIRED_CHECKS = {'test (py3.11)', 'test (py3.12)', 'test (py3.13)', 'reproduce'}
GENERATED_DATA = ('epoch_capabilities_index_*.csv', 'auto_models.json',
                  'eci_self_conditions.json', 'eci_self6mo_conditions.json', 'combined_conditions.json')


DATA_BLOCK = re.compile(rb'<!--([A-Z][A-Z0-9_]*_DATA)-->(.*?)<!--/\1-->', re.S)
DATA_MARKER = re.compile(rb'<!--(/?[A-Z][A-Z0-9_]*_DATA)-->')
DATA_FILES = ('forecasts.csv', 'rationales.csv', 'debriefs.csv', 'redlines-data.zip')


def data_blocks(html):
    """Read the published data boundary, rejecting missing/duplicate markers."""
    matches = list(DATA_BLOCK.finditer(html))
    markers = DATA_MARKER.findall(html)
    expected = [tag for match in matches for tag in (match[1], b'/' + match[1])]
    if not matches or markers != expected or len({m[1] for m in matches}) != len(matches):
        raise RuntimeError('Invalid or duplicate dashboard data markers')
    for match in matches:
        name = match[1].removesuffix(b'_DATA')
        assignment = re.fullmatch(rb'\s*<script>\s*window\.__' + name + rb'__\s*=\s*(.*?)\s*;\s*</script>\s*', match[2], re.S)
        if not assignment:
            raise RuntimeError('Invalid dashboard data assignment: ' + name.decode())
        json.loads(assignment[1])
    return {m[1].decode(): m[0] for m in matches}


def frontend_html(template, published):
    """New interface, byte-identical previously published data and labels."""
    old, new = data_blocks(published), data_blocks(template)
    if old.keys() != new.keys():
        raise RuntimeError('Dashboard data blocks changed; publish validated data or migrate the snapshot explicitly')
    return DATA_BLOCK.sub(lambda m: old[m[1].decode()], template)


def data_snapshot(site):
    blocks = {name: hashlib.sha256(block).hexdigest()
              for name, block in data_blocks((site / 'index.html').read_bytes()).items()}
    files = {}
    for name in DATA_FILES:
        path = site / name
        if path.exists():
            with path.open('rb') as f:
                files[name] = hashlib.file_digest(f, 'sha256').hexdigest()
    manifest = {'blocks': blocks, 'files': files}
    return {**manifest, 'sha256': hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w') as f:
        f.write(json.dumps(value, indent=2) + '\n')
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def link(target, path):
    tmp = path.with_name(path.name + '.tmp')
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(target)
    tmp.replace(path)


def run(argv, **kw):
    return subprocess.run([str(x) for x in argv], check=True, **kw)


def output(argv, **kw):
    return run(argv, capture_output=True, text=True, **kw).stdout.strip()


def validate_jobs(jobs):
    ids = set()
    for job in jobs:
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', job['id']) or job['id'] in ids:
            raise ValueError('Job IDs must be unique safe names')
        ids.add(job['id'])
        if job['kind'] not in ('forecast', 'forecastbench', 'news-poll', 'smoke'):
            raise ValueError('Unknown job kind')
        if 'at' in job:
            when = datetime.fromisoformat(job['at'].replace('Z', '+00:00'))
            if when.tzinfo is None or when.utcoffset().total_seconds() != 0 or when.second or when.microsecond:
                raise ValueError('Job dates must be UTC')
        elif not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', job['daily_utc']):
            raise ValueError('Invalid UTC time')
        if job['kind'] == 'forecastbench':
            datetime.strptime(job['due'], '%Y-%m-%d')
    return jobs


def due_jobs(jobs, now):
    """No catch-up: start only within the scheduled minute. Ledger deduplicates it."""
    now = now.astimezone(timezone.utc)
    for job in validate_jobs(jobs):
        if 'at' in job:
            at = datetime.fromisoformat(job['at'].replace('Z', '+00:00'))
            due = now.replace(second=0, microsecond=0) == at.replace(second=0, microsecond=0)
            key = job['id'] + '-' + at.strftime('%Y%m%dT%H%M')
        else:
            due = now.strftime('%H:%M') == job['daily_utc']
            key = job['id'] + '-' + now.strftime('%Y%m%d')
        if due:
            yield key, job


class Runtime:
    def __init__(self, config):
        self.config = config
        self.root = Path(config['root']).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.current = self.root / 'current'
        self.state = self.root / 'state'
        self.home = self.root / 'home'
        self.mirror = self.root / 'repository.git'
        for name in ('releases', 'sites', 'runs', 'logs', 'tmp'):
            (self.root / name).mkdir(exist_ok=True)

    @contextmanager
    def lock(self):
        with (self.root / 'operation.lock').open('a') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield

    def environment(self, code, docroot):
        env = os.environ.copy()
        for key in list(env):
            if key.endswith('_API_KEY') or key in ('ANTHROPIC_AUTH_TOKEN', 'OPENAI_AUTH_TOKEN'):
                env.pop(key)
        env.update(HOME=str(self.home), PATH=str(code / '.venv/bin') + ':' + self.config['path'],
                   REDLINES_PY=str(code / '.venv/bin/python'), PY=str(code / '.venv/bin/python'),
                   AIRO_RELEASE=str(code), REDLINES_REPO=str(code), REDLINES_DOCROOT=str(docroot),
                   AIRO_NEWS_DIR=str(self.state / 'recent-news'),
                   FORECASTER_PI=str(code / 'packages/fri-forecaster/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'),
                   FORECASTER_ENV_FILE=str(self.home / '.config/fri-forecaster/env'),
                   FORECASTER_ROUND_ENV=str(self.home / '.config/fri-forecaster/round.env'),
                   PI_CODING_AGENT_DIR=str(self.home / 'pi-agent'),
                   TMPDIR=str(self.root / 'tmp'), TZ='UTC', NODE_USE_ENV_PROXY='1',
                   NO_PROXY='localhost,127.0.0.1,::1', no_proxy='localhost,127.0.0.1,::1')
        return env

    def storage_status(self):
        disk = shutil.disk_usage(self.root)
        fs = os.statvfs(self.root)
        minimum = int(self.config.get('min_free_bytes', 5 * 1024**3))
        used_percent = round(100 * disk.used / disk.total, 1)
        inode_percent = round(100 * (1 - fs.f_favail / fs.f_files), 1) if fs.f_files else 0
        return {'total_bytes': disk.total, 'free_bytes': disk.free,
                'used_percent': used_percent, 'inode_used_percent': inode_percent,
                'min_free_bytes': minimum,
                'healthy': disk.free >= minimum and used_percent < 80 and inode_percent < 80}

    def storage(self):
        status = self.storage_status()
        print(json.dumps(status, indent=2))
        if not status['healthy']:
            raise SystemExit(1)

    def require_space(self, publish_data=False):
        # Reserve headroom in addition to the candidate's code, website and data copy.
        def size(path):
            return sum(p.stat().st_size for p in path.rglob('*')
                       if not p.is_symlink() and p.is_file()) if path.exists() else 0
        needed = 2 * 1024**3 + 2 * (size(self.current / 'code') + size(self.current / 'site'))
        if publish_data:
            needed += size(self.state)
        status = self.storage_status()
        needed = max(needed, status['min_free_bytes'])
        if status['free_bytes'] < needed or status['inode_used_percent'] >= 90:
            raise RuntimeError(f'Insufficient deployment storage: need {needed} free bytes; '
                               f"have {status['free_bytes']}; inode usage {status['inode_used_percent']}%")

    def prune_locked(self):
        """Caller holds operation.lock. Only disposable releases/sites are collected."""
        releases = self.root / 'releases'
        sites = self.root / 'sites'
        if releases.is_symlink() or sites.is_symlink():
            raise RuntimeError('Retention roots must not be symlinks')
        protected = set()
        for name in ('current', 'previous'):
            pointer = self.root / name
            if pointer.exists() or pointer.is_symlink():
                target = pointer.resolve(strict=True)
                if target.parent != releases or not target.is_dir():
                    raise RuntimeError('Release pointer escapes retention root')
                protected.add(target)
        candidates = sorted((p for p in releases.iterdir()
                             if not p.is_symlink() and p.is_dir()
                             and re.fullmatch(r'\d{8}T\d{6}-[0-9a-f]{12}', p.name)), reverse=True)
        count = max(2, int(self.config.get('keep_releases', 3)))
        retained = protected | set([p for p in candidates if p not in protected][:max(0, count - len(protected))])
        # Keep sites referenced by every retained or unrecognized release, including job publications.
        removed_releases = set(candidates) - retained
        referenced = {sites / p.name for p in retained}
        for r in releases.iterdir():
            if r in removed_releases:
                continue
            site = r / 'site'
            if site.exists() or site.is_symlink():
                target = site.resolve(strict=True)
                if target.parent == sites:
                    referenced.add(target)
        disposable_sites = sorted((p for p in sites.iterdir()
                                   if not p.is_symlink() and p.is_dir() and p not in referenced
                                   and re.fullmatch(r'(?:\d{8}T\d{6}-[0-9a-f]{12}|job-[a-zA-Z0-9_-]+)', p.name)),
                                  key=lambda p: p.stat().st_mtime, reverse=True)
        # Preserve the newest unreferenced job publication for diagnosis; receipts/logs never expire here.
        orphan_jobs = [p for p in disposable_sites if p.name.startswith('job-')]
        keep_jobs = set(orphan_jobs[:1])
        removed = []
        for path in sorted(removed_releases) + [p for p in disposable_sites if p not in keep_jobs]:
            shutil.rmtree(path)
            removed.append(str(path.relative_to(self.root)))
        return removed

    def prune(self):
        with self.lock():
            removed = self.prune_locked()
        print(json.dumps({'removed': removed, 'storage': self.storage_status()}, indent=2))

    def merged_sha(self, requested=None):
        if not self.mirror.exists():
            run(['git', 'clone', '--bare', self.config['repository'], self.mirror])
        run(['git', '-C', self.mirror, 'fetch', 'origin', '+refs/heads/main:refs/heads/main'])
        sha = output(['git', '-C', self.mirror, 'rev-parse', '--verify', (requested or 'main') + '^{commit}'])
        if not re.fullmatch(r'[0-9a-f]{40}', sha):
            raise ValueError('Expected a full commit SHA')
        run(['git', '-C', self.mirror, 'merge-base', '--is-ancestor', sha, 'main'])
        checks = json.loads(output(['gh', 'api', f"repos/{self.config['github_repository']}/commits/{sha}/check-runs?per_page=100"]))['check_runs']
        # GitHub returns newest first. A newer failure must not be hidden by an old pass.
        latest = {}
        for check in sorted(checks, key=lambda x: x['id'], reverse=True):
            if check.get('app', {}).get('slug') == 'github-actions':
                latest.setdefault(check['name'], check)
        failed = [name for name in REQUIRED_CHECKS if name not in latest or latest[name]['status'] != 'completed' or latest[name]['conclusion'] != 'success']
        if failed:
            raise RuntimeError('Required checks have not passed for this commit: ' + ', '.join(sorted(failed)))
        return sha

    def stage_data(self, code, copy_results=True):
        # Build on a private copy: a failed candidate cannot alter live forecast data.
        if copy_results:
            shutil.copytree(self.state / 'results', code / 'results', dirs_exist_ok=True)
        for pattern in GENERATED_DATA:
            for source in (self.state / 'data').glob(pattern):
                shutil.copy2(source, code / 'data' / source.name)
        if (self.state / 'fonts').exists():
            shutil.copytree(self.state / 'fonts', code / 'web/fonts', dirs_exist_ok=True)

    def attach_state(self, code):
        # Results are accrued production data, not reset by git. Seed only new files.
        source = code / 'results'
        for p in source.rglob('*'):
            dest = self.state / 'results' / p.relative_to(source)
            if p.is_file() and not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
        shutil.rmtree(source)
        source.symlink_to(self.state / 'results')
        for pattern in GENERATED_DATA:
            for p in (code / 'data').glob(pattern):
                dest = self.state / 'data' / p.name
                if not dest.exists():
                    shutil.copy2(p, dest)
                p.unlink()
                p.symlink_to(dest)

    def save_generated_data(self, code):
        # Epoch may create a new dated snapshot, or a writer may replace a symlink.
        for pattern in GENERATED_DATA:
            for p in (code / 'data').glob(pattern):
                if p.is_file() and not p.is_symlink():
                    dest = self.state / 'data' / p.name
                    shutil.copy2(p, dest)
                    p.unlink()
                    p.symlink_to(dest)

    def verify_site(self, site):
        for name in ('index.html', 'forecasts.csv', 'rationales.csv', 'redlines-data.zip'):
            if not (site / name).is_file() or (site / name).stat().st_size == 0:
                raise RuntimeError('Incomplete publication: ' + name)
        if '<html' not in (site / 'index.html').read_text().lower():
            raise RuntimeError('Publication has no HTML document')
        if any(p.is_symlink() for p in site.rglob('*')):
            raise RuntimeError('Publication must not contain symlinks')

    def probe(self, release):
        """Check the actual serving process sees the newly selected release."""
        connection = http.client.HTTPConnection('localhost', timeout=10)
        connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.sock.settimeout(10)
        connection.sock.connect(self.config['socket'])
        try:
            connection.request('GET', '/release.json')
            response = connection.getresponse()
            body = json.loads(response.read())
            if response.status != 200 or body['release'] != release.name:
                raise RuntimeError('Serving process did not activate the candidate')
        finally:
            connection.close()

    def activate(self, release):
        previous = self.current.resolve() if self.current.exists() else None
        link(release, self.current)
        try:
            self.probe(release)
        except Exception:
            if previous:
                link(previous, self.current)
            else:
                self.current.unlink()
            raise
        if previous and previous != release:
            link(previous, self.root / 'previous')
        write_json(self.root / 'last-deploy.json', {'release': release.name, 'previous': previous.name if previous else None, 'at': datetime.now(timezone.utc).isoformat()})

    def publish_frontend(self, code, site):
        if not self.current.exists():
            raise RuntimeError('No published data snapshot; initialize with --publish-data or an explicit publication import')
        source = self.current / 'site'
        self.verify_site(source)
        prior = json.loads((source / 'release.json').read_text())
        snapshot = data_snapshot(source)
        previous = prior.get('data_snapshot', {})
        if previous.get('sha256', snapshot['sha256']) != snapshot['sha256']:
            raise RuntimeError('Published data snapshot changed unexpectedly')
        html = frontend_html((code / 'index.html').read_bytes(), (source / 'index.html').read_bytes())
        shutil.copytree(source, site)
        (site / 'index.html').write_bytes(html)
        for name in ('img', 'fonts'):
            assets = code / 'web' / name
            if assets.exists():
                target = site / 'web' / name
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(assets, target)
        self.verify_site(site)
        if data_snapshot(site) != snapshot:
            raise RuntimeError('Frontend deployment changed published data')
        return {**snapshot,
                'origin_commit': previous.get('origin_commit', prior.get('publication_commit')),
                'source_release': previous.get('source_release', prior.get('release'))}

    def deploy(self, requested=None, keep_publication=False, publish_data=False):
        if keep_publication and publish_data:
            raise ValueError('Choose either preserved publication or new data publication')
        with self.lock():
            self.prune_locked()
            self.require_space(publish_data=publish_data)
            sha = self.merged_sha(requested)
            name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + sha[:12]
            release = self.root / 'releases' / name
            code = release / 'code'
            release.mkdir()
            try:
                run(['git', 'clone', '--no-hardlinks', self.mirror, code])
                run(['git', '-C', code, 'checkout', '--detach', sha])
                validate_jobs(json.loads((code / 'deploy/jobs.json').read_text()))
                env = os.environ.copy()
                env.update(PATH=self.config['path'], TMPDIR=str(self.root / 'tmp'))
                run(['python3', '-m', 'venv', code / '.venv'], env=env)
                run([code / '.venv/bin/pip', 'install', '-e', code, '-e', code / 'packages/fri-forecaster'], env=env)
                run(['npm', 'ci', '--prefix', code / 'packages/fri-forecaster'], env=env)
                (release / 'python-packages.txt').write_text(output([code / '.venv/bin/pip', 'freeze']))
                self.stage_data(code, copy_results=publish_data)
                site = self.root / 'sites' / name
                metadata = {'release': name, 'commit': sha, 'publication': 'frontend', 'publication_commit': sha, 'frontend_commit': sha}
                if keep_publication:
                    source = self.current / 'site' if self.current.exists() else Path(self.config['bootstrap_publication'])
                    self.verify_site(source)
                    shutil.copytree(source, site)
                    prior = json.loads((source / 'release.json').read_text()) if (source / 'release.json').exists() else {}
                    metadata.update(publication='preserved', publication_commit=prior.get('publication_commit', prior.get('commit')),
                                    frontend_commit=prior.get('frontend_commit', prior.get('publication_commit')))
                    if 'data_snapshot' in prior:
                        metadata['data_snapshot'] = prior['data_snapshot']
                elif publish_data:
                    site.mkdir()
                    run(['bash', code / 'code/publish_dashboard.sh'], cwd=code, env=self.environment(code, site))
                    self.verify_site(site)
                    metadata.update(publication='rebuilt', data_snapshot={**data_snapshot(site), 'origin_commit': sha, 'source_release': name})
                else:
                    metadata['data_snapshot'] = self.publish_frontend(code, site)
                self.verify_site(site)
                write_json(site / 'release.json', metadata)
                link(site, release / 'site')
                write_json(release / 'release.json', metadata)
                self.attach_state(code)
                self.activate(release)
                try:
                    self.prune_locked()
                except (OSError, RuntimeError) as exc:
                    print(f'Retention needs attention: {exc}', file=sys.stderr)
                print(json.dumps({'deployed': name, 'commit': sha}))
            except Exception:
                # Keep the candidate and logs for diagnosis; never switch on failure.
                write_json(release / 'failed.json', {'at': datetime.now(timezone.utc).isoformat()})
                raise

    def rollback(self):
        with self.lock():
            release = (self.root / 'previous').resolve(strict=True)
            self.verify_site(release / 'site')
            self.activate(release)
            print(json.dumps({'rolled_back': release.name}))

    def execute_job(self, key, job):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', key):
            raise ValueError('Unsafe run key')
        with self.lock():
            receipt = self.root / 'runs' / (key + '.json')
            if receipt.exists():
                return False  # Includes interrupted/failed runs: no surprise paid retries.
            if job['kind'] != 'smoke':
                self.require_space(publish_data=job['kind'] == 'forecast')
            release = self.current.resolve(strict=True)
            code = release / 'code'
            started = {'key': key, 'job': job['id'], 'release': release.name, 'status': 'running', 'started': datetime.now(timezone.utc).isoformat()}
            write_json(receipt, started)
            site = self.root / 'sites' / ('job-' + key)
            site.mkdir()
            env = self.environment(code, site)
            argv = {'forecast': ['bash', code / 'code/cron_run.sh'],
                    'news-poll': [code / '.venv/bin/python', code / 'code/recent_news.py', 'poll'],
                    'forecastbench': ['bash', code / 'packages/fri-forecaster/scripts/fb_cron.sh', job.get('due', '')],
                    'smoke': [code / '.venv/bin/python', '-c', 'import redlines, fri_forecaster; print("scheduled runtime smoke passed")']}[job['kind']]
            try:
                expects_site = job['kind'] == 'forecast' and any(
                    len(row.split()) > 1 and row.split()[1] == 'publish'
                    for row in output([code / '.venv/bin/python', '-m', 'redlines.experiments', 'due'], cwd=code, env=env).splitlines())
                with (self.root / 'logs' / (key + '.log')).open('a') as log:
                    run(argv, cwd=code, env=env, stdout=log, stderr=subprocess.STDOUT)
                if job['kind'] == 'forecastbench':
                    # fb_round's shell exit alone is insufficient; every expected set must build.
                    round_root = self.home / 'forecastbench/rounds' / job['due']
                    # Use the same CLI/config as the round, without exposing private names.
                    count = int(output(['bash', '-o', 'pipefail', '-c', 'set -a; source "$FORECASTER_ROUND_ENV"; set +a; "$PY" -m fri_forecaster.names conditions | wc -l'], cwd=code, env=env))
                    built = (round_root / 'logs/round.log').read_text().count('build exited 0')
                    if count == 0 or built < count:
                        raise RuntimeError('ForecastBench has incomplete submission sets')
                if expects_site or (site / 'index.html').exists():
                    self.verify_site(site)
                    meta = json.loads((release / 'release.json').read_text())
                    meta.update(publication='rebuilt', publication_commit=meta['commit'], frontend_commit=meta['commit'],
                                data_snapshot={**data_snapshot(site), 'origin_commit': meta['commit'], 'source_release': 'job-' + key})
                    write_json(site / 'release.json', meta)
                    link(site, release / 'site')
                    write_json(release / 'release.json', meta)
                started.update(status='succeeded')
            except Exception as exc:
                started.update(status='failed', error=type(exc).__name__)
                raise
            finally:
                self.save_generated_data(code)
                started['finished'] = datetime.now(timezone.utc).isoformat()
                write_json(receipt, started)
            return True

    def tick(self):
        if not self.current.exists() or not (self.root / 'jobs-enabled').exists():
            return
        jobs = json.loads((self.current / 'code/deploy/jobs.json').read_text())
        for key, job in due_jobs(jobs, datetime.now(timezone.utc)):
            self.execute_job(key, job)

    def status(self):
        print(json.dumps({'storage': self.storage_status(),
                          'release': json.loads((self.current / 'release.json').read_text()) if self.current.exists() else None,
                          'jobs_enabled': (self.root / 'jobs-enabled').exists(),
                          'jobs': json.loads((self.current / 'code/deploy/jobs.json').read_text()) if self.current.exists() else [],
                          'recent_runs': [json.loads(p.read_text()) for p in sorted((self.root / 'runs').glob('*.json'))[-10:]]}, indent=2))

    def serve(self):
        runtime = self
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                # Pin the whole HTTP response to one publication, even during activation.
                root = (runtime.current / 'site').resolve()
                super().__init__(*args, directory=str(root), **kwargs)
            def address_string(self):
                return 'ingress'
            def list_directory(self, path):
                self.send_error(404)
            def log_message(self, *args):
                pass
        sock = Path(self.config['socket'])
        sock.unlink(missing_ok=True)
        server = ThreadingUnixStreamServer(str(sock), Handler)
        os.chmod(sock, 0o660)
        server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=os.environ.get('AIRO_RUNTIME_CONFIG', str(Path.home() / '.config/airo/runtime.json')))
    parser.add_argument('command', choices=['deploy', 'rollback', 'status', 'tick', 'serve', 'smoke', 'prune', 'storage'])
    parser.add_argument('--commit')
    publication = parser.add_mutually_exclusive_group()
    publication.add_argument('--keep-publication', action='store_true', help='Retain the entire website while deploying code and schedules')
    publication.add_argument('--publish-data', action='store_true', help='Rebuild and validate forecast data as part of deployment; never launches forecast jobs')
    parser.add_argument('--run-id', default='smoke-' + uuid.uuid4().hex[:12])
    args = parser.parse_args()
    runtime = Runtime(json.loads(Path(args.config).read_text()))
    if args.command == 'deploy': runtime.deploy(args.commit, keep_publication=args.keep_publication, publish_data=args.publish_data)
    elif args.command == 'smoke': runtime.execute_job(args.run_id, {'id': 'smoke', 'kind': 'smoke'})
    else: getattr(runtime, args.command)()


if __name__ == '__main__':
    main()
