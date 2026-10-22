#!/usr/bin/env python3
"""Explicit releases and durable UTC jobs. Configuration and data stay outside git."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import http.client
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
        if job['kind'] not in ('forecast', 'forecastbench', 'smoke'):
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
                   FORECASTER_PI=str(code / 'packages/fri-forecaster/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'),
                   FORECASTER_ENV_FILE=str(self.home / '.config/fri-forecaster/env'),
                   FORECASTER_ROUND_ENV=str(self.home / '.config/fri-forecaster/round.env'),
                   PI_CODING_AGENT_DIR=str(self.home / 'pi-agent'),
                   TMPDIR=str(self.root / 'tmp'), TZ='UTC')
        return env

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

    def stage_data(self, code):
        # Build on a private copy: a failed candidate cannot alter live forecast data.
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

    def deploy(self, requested=None):
        with self.lock():
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
                run([code / '.venv/bin/pip', 'install', '-e', str(code) + '[acquire]', '-e', code / 'packages/fri-forecaster'], env=env)
                run(['npm', 'ci', '--prefix', code / 'packages/fri-forecaster'], env=env)
                (release / 'python-packages.txt').write_text(output([code / '.venv/bin/pip', 'freeze']))
                self.stage_data(code)
                site = self.root / 'sites' / name
                site.mkdir()
                run(['bash', code / 'code/publish_dashboard.sh'], cwd=code, env=self.environment(code, site))
                self.verify_site(site)
                write_json(site / 'release.json', {'release': name, 'commit': sha})
                link(site, release / 'site')
                write_json(release / 'release.json', {'commit': sha, 'release': name})
                self.attach_state(code)
                self.activate(release)
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
            release = self.current.resolve(strict=True)
            code = release / 'code'
            started = {'key': key, 'job': job['id'], 'release': release.name, 'status': 'running', 'started': datetime.now(timezone.utc).isoformat()}
            write_json(receipt, started)
            site = self.root / 'sites' / ('job-' + key)
            site.mkdir()
            env = self.environment(code, site)
            argv = {'forecast': ['bash', code / 'code/cron_run.sh'],
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
                    write_json(site / 'release.json', meta)
                    link(site, release / 'site')
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
        print(json.dumps({'release': json.loads((self.current / 'release.json').read_text()) if self.current.exists() else None,
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
    parser.add_argument('command', choices=['deploy', 'rollback', 'status', 'tick', 'serve', 'smoke'])
    parser.add_argument('--commit')
    parser.add_argument('--run-id', default='smoke-' + uuid.uuid4().hex[:12])
    args = parser.parse_args()
    runtime = Runtime(json.loads(Path(args.config).read_text()))
    if args.command == 'deploy': runtime.deploy(args.commit)
    elif args.command == 'smoke': runtime.execute_job(args.run_id, {'id': 'smoke', 'kind': 'smoke'})
    else: getattr(runtime, args.command)()


if __name__ == '__main__':
    main()
