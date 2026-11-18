#!/usr/bin/env python3
"""Explicit releases and durable UTC jobs. Configuration and data stay outside git."""
import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
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

# This script runs on the system interpreter, outside the release's venv.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))
from dashboard import page, site as site_kit  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard_projects import AIRO_FILES, DASHBOARDS  # noqa: E402

# Where things are in a release: the repository's layout.
AIRO = 'dashboards/airo'                    # its index.html, web/, data/, results/ and code/
FORECASTER = 'packages/forecaster'          # the engine; pi is under its node_modules
FORECASTBENCH = 'submissions/forecastbench'
JOBS = 'packages/ops/jobs.json'
PROJECTS = (FORECASTER, 'packages/dashboard', AIRO, 'dashboards/eeai', FORECASTBENCH, 'submissions/leap')   # each installed into the release's venv
# The installation's launcher runs this path in the live release, and deploy
# runs it in a candidate (build-release): it stays put whatever else moves.
LAUNCHER = 'code/production.py'

REQUIRED_CHECKS = {'test (py3.11)', 'test (py3.12)', 'test (py3.13)', 'reproduce'}
GENERATED_DATA = ('epoch_capabilities_index_*.csv', 'auto_models.json',
                  'eci_self_conditions.json', 'eci_self6mo_conditions.json', 'combined_conditions.json')


# What a job kind's alerts are filed under (fri_forecaster.alert's `deployment`).
DEPLOYMENT = {'forecast': 'airo', 'news-poll': 'airo', 'forecastbench': 'forecastbench', 'smoke': 'scheduler'}

DATA_FILES = AIRO_FILES

# The published data boundary is the dashboard kit's (packages/dashboard):
# reading a page's data blocks, a new interface around byte-identical data,
# and the hash of what a site publishes.
data_blocks = page.blocks
frontend_html = page.swap_frontend


def data_snapshot(site, files=DATA_FILES):
    return site_kit.snapshot(site, files)


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
        owner = job.get('dashboard', 'airo')
        if owner not in DASHBOARDS or (owner != 'airo' and job['kind'] not in ('forecast', 'smoke')):
            raise ValueError('Unknown dashboard or unsupported dashboard job')
        if job['kind'] not in ('forecast', 'forecastbench', 'news-poll', 'smoke'):
            raise ValueError('Unknown job kind')
        if sum(k in job for k in ('at', 'daily_utc', 'weekly_utc')) != 1:
            raise ValueError('Specify one UTC schedule: at, daily_utc or weekly_utc')
        if 'at' in job:
            when = datetime.fromisoformat(job['at'].replace('Z', '+00:00'))
            if when.tzinfo is None or when.utcoffset().total_seconds() != 0 or when.second or when.microsecond:
                raise ValueError('Job dates must be UTC')
        elif 'weekly_utc' in job:
            if not re.fullmatch(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) (?:[01][0-9]|2[0-3]):[0-5][0-9]', job['weekly_utc']):
                raise ValueError('Weekly schedule must be a weekday and UTC HH:MM')
        elif not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', job['daily_utc']):
            raise ValueError('Invalid UTC time')
        if job['kind'] == 'forecastbench':
            datetime.strptime(job['due'], '%Y-%m-%d')
    return jobs


def due_jobs(jobs, now):
    """No catch-up: start only within the scheduled minute. Ledger deduplicates it."""
    minute = now.astimezone(timezone.utc).replace(second=0, microsecond=0)
    for key, job, _ in scheduled_between(jobs, minute - timedelta(seconds=1), minute + timedelta(seconds=1)):
        yield key, job


def scheduled_between(jobs, after, before):
    """(key, job, time) for each scheduled UTC minute with after < time < before."""
    weekdays = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
    for job in validate_jobs(jobs):
        if 'at' in job:
            times = [datetime.fromisoformat(job['at'].replace('Z', '+00:00'))]
        else:
            weekday = None
            if 'weekly_utc' in job:
                weekday, clock = job['weekly_utc'].split()
            else:
                clock = job['daily_utc']
            hour, minute = map(int, clock.split(':'))
            start = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
            days = (before.date() - after.date()).days
            times = (start + timedelta(days=d) for d in range(days + 1))
            if weekday:
                times = filter(lambda at: weekdays[at.weekday()] == weekday, times)
        for at in times:
            if after < at < before:
                yield job['id'] + '-' + at.strftime('%Y%m%dT%H%M' if 'at' in job else '%Y%m%d'), job, at


def paged(ledger):
    """Did the job itself already page? (the ledger fri_forecaster.alert keeps for it)"""
    try:
        return any(json.loads(line).get('severity') == 'page' for line in ledger.read_text().splitlines() if line.strip())
    except OSError:
        return False


class Runtime:
    def __init__(self, config, config_path=None):
        self.config = config
        self.config_path = config_path
        self.root = Path(config['root']).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.name = config.get('dashboard', 'airo')
        self.dashboard = DASHBOARDS[self.name]
        self.current = self.root / 'current'
        if self.current.exists():
            selected = json.loads((self.current / 'release.json').read_text())
            if selected.get('dashboard', 'airo') != self.name:
                raise ValueError('Configured dashboard does not own the selected release')
        self.state = self.root / 'state'
        self.panel_runtime = None
        if 'panel_runtime_config' in config:
            authority = Path(config['panel_runtime_config'])
            primary = json.loads(authority.read_text())
            if self.name == 'airo' or primary.get('dashboard', 'airo') != 'airo' or 'panel_runtime_config' in primary:
                raise ValueError('panel_runtime_config must identify the primary AIRO installation')
            self.panel_runtime = Runtime(primary, config_path=authority)
            if self.panel_runtime.root == self.root or primary['socket'] == config['socket']:
                raise ValueError('Dashboard runtimes require separate roots and sockets')
        self.home = self.panel_runtime.home if self.panel_runtime else self.root / 'home'
        self.mirror = self.root / 'repository.git'
        for name in ('releases', 'sites', 'runs', 'logs', 'tmp'):
            (self.root / name).mkdir(exist_ok=True)

    @contextmanager
    def lock(self):
        lock_path = (self.panel_runtime or self).root / 'operation.lock'
        with lock_path.open('a') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield

    def environment(self, code, docroot):
        env = os.environ.copy()
        for key in list(env):
            if key.endswith('_API_KEY') or key in ('ANTHROPIC_AUTH_TOKEN', 'OPENAI_AUTH_TOKEN'):
                env.pop(key)
        env.update(HOME=str(self.home), PATH=str(code / '.venv/bin') + ':' + self.config['path'],
                   REDLINES_PY=str(code / '.venv/bin/python'), PY=str(code / '.venv/bin/python'),
                   AIRO_RELEASE=str(code / AIRO), REDLINES_REPO=str(code / AIRO), REDLINES_DOCROOT=str(docroot),
                   AIRO_PRIOR_PUBLICATION=str((self.current / "site").resolve()),
                   AIRO_NEWS_DIR=str(self.state / 'recent-news'),
                   FORECASTER_PI=str(code / FORECASTER / 'node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'),
                   FORECASTER_ENV_FILE=str(self.home / '.config/fri-forecaster/env'),
                   FORECASTER_ROUND_ENV=str(self.home / '.config/fri-forecaster/round.env'),
                   PI_CODING_AGENT_DIR=str(self.home / 'pi-agent'),
                   TMPDIR=str(self.root / 'tmp'), TZ='UTC', NODE_USE_ENV_PROXY='1',
                   NO_PROXY='localhost,127.0.0.1,::1', no_proxy='localhost,127.0.0.1,::1')
        panel_dir = (self.panel_runtime or self).state / 'data'
        env.update(FORECASTER_ECI_DIR=str(panel_dir), EEAI_ECI_DIR=str(panel_dir))
        return env

    def jobs(self, code):
        jobs = validate_jobs(json.loads((code / JOBS).read_text()))
        return [job for job in jobs if job.get('dashboard', 'airo') == self.name]

    def project_command(self, code, args, site, results=None):
        results = results or self.state / 'results'
        results.mkdir(parents=True, exist_ok=True)
        return [code / '.venv/bin/python', *(arg.format(results=results, site=site) for arg in args)]

    def build_data(self, code, site, env, **kwargs):
        if self.name == 'airo':
            command = ['bash', code / AIRO / 'code/publish_dashboard.sh']
        else:
            command = self.project_command(code, self.dashboard.build, site)
        run(command, cwd=code / self.dashboard.project, env=env, **kwargs)

    def configure_forecastbench(self, prefix, credentials):
        """Provision only the uploader key/settings via stdin, never a coding login."""
        from urllib.parse import urlsplit
        parsed = urlsplit(prefix or '')
        if (parsed.scheme != 'gs' or not parsed.netloc or not parsed.path.strip('/')
                or parsed.query or parsed.fragment):
            raise ValueError('An upload prefix gs://bucket/team-prefix/binary is required')
        if (credentials.get('type') != 'service_account'
                or not credentials.get('client_email', '').endswith('.iam.gserviceaccount.com')
                or not credentials.get('private_key', '').startswith('-----BEGIN PRIVATE KEY-----')
                or credentials.get('token_uri') != 'https://oauth2.googleapis.com/token'):
            raise ValueError('Expected a Google service-account JSON key on stdin')
        with self.lock():
            private = self.home / '.config/forecastbench-uploader'
            private.mkdir(parents=True, mode=0o700, exist_ok=True)
            private.chmod(0o700)
            candidate = private / 'candidate-key.json'
            try:
                write_json(candidate, credentials)
                candidate.chmod(0o600)
                code = self.current.resolve(strict=True) / 'code'
                env = self.environment(code, self.root / 'tmp')
                env['FB_UPLOAD_KEY_FILE'] = str(candidate)
                run([code / '.venv/bin/python', '-c',
                     'from forecastbench.upload import Storage; import sys; Storage(sys.argv[1])',
                     credentials['client_email']], env=env, cwd=code, timeout=120)
                candidate.replace(private / 'key.json')
                write_json(private / 'settings.json', {'prefix': prefix.rstrip('/'),
                                                       'account': credentials['client_email']})
                (private / 'settings.json').chmod(0o600)
            finally:
                candidate.unlink(missing_ok=True)
        print('ForecastBench uploader credentials configured and authentication verified')

    def check_forecastbench_upload(self, due):
        datetime.strptime(due, '%Y-%m-%d')
        with self.lock():
            code = self.current.resolve(strict=True) / 'code'
            run([code / '.venv/bin/python', '-m', 'forecastbench.upload', '--check-access', due],
                env=self.environment(code, self.root / 'tmp'), cwd=code, timeout=360)

    def alert(self, job, message, log=None, title='run FAILED'):
        """One alert through the release's shared sender (fri_forecaster.alert):
        a page that the run (or its publication) failed; for the news poll, a
        notice that the news fetch failed. Never raises."""
        try:
            code = self.current.resolve(strict=True) / 'code'
            env = self.environment(code, self.root / 'tmp')
            news = job['kind'] == 'news-poll'
            argv = [code / '.venv/bin/python', '-m', 'fri_forecaster.alert', 'send', '--deployment', (self.name if job['kind'] == 'forecast' else DEPLOYMENT[job['kind']]),
                    '--severity', 'notice' if news else 'page', '--title', 'news fetch failed' if news else title,
                    *(['--log', str(log)] if log else []), message]
            subprocess.run(argv, cwd=code, env=env, timeout=120, check=False)
        except Exception as exc:
            print(f'Alert not sent ({type(exc).__name__}): {title}', file=sys.stderr)

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

    def require_space(self, publish_data=False, job_kind=None):
        # Reserve headroom in addition to the candidate's code, website and data copy.
        def size(path):
            return sum(p.stat().st_size for p in path.rglob('*')
                       if not p.is_symlink() and p.is_file()) if path.exists() else 0
        if job_kind is not None:
            # Jobs use the installed code and shared state; only publication
            # builds another site. Reserve twice its current size plus headroom.
            needed = 2 * 1024**3 + (2 * size(self.current / 'site') if publish_data else 0)
        else:
            needed = 2 * 1024**3 + 2 * (size(self.current / 'code') + size(self.current / 'site'))
            if publish_data:
                needed += size(self.state)
        status = self.storage_status()
        needed = max(needed, status['min_free_bytes'])
        if status['free_bytes'] < needed or status['inode_used_percent'] >= 90:
            raise RuntimeError(f'Insufficient {"job" if job_kind else "deployment"} storage: need {needed} free bytes; '
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
        if self.name != 'airo':
            fonts = self.state / 'fonts'
            if fonts.is_dir():
                shutil.copytree(fonts, code / self.dashboard.project / self.dashboard.web / 'fonts', dirs_exist_ok=True)
            return
        airo = code / AIRO
        if copy_results:
            shutil.copytree(self.state / 'results', airo / 'results', dirs_exist_ok=True)
        for pattern in GENERATED_DATA:
            for source in (self.state / 'data').glob(pattern):
                shutil.copy2(source, airo / 'data' / source.name)
        if (self.state / 'fonts').exists():
            shutil.copytree(self.state / 'fonts', airo / 'web/fonts', dirs_exist_ok=True)

    def attach_state(self, code):
        if self.name != 'airo':
            return   # other runners write directly to state/results
        # Results are accrued production data, not reset by git. Seed only new files.
        airo = code / AIRO
        source = airo / 'results'
        for p in source.rglob('*'):
            dest = self.state / 'results' / p.relative_to(source)
            if p.is_file() and not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
        shutil.rmtree(source)
        source.symlink_to(self.state / 'results')
        for pattern in GENERATED_DATA:
            for p in (airo / 'data').glob(pattern):
                dest = self.state / 'data' / p.name
                if not dest.exists():
                    shutil.copy2(p, dest)
                p.unlink()
                p.symlink_to(dest)

    def save_generated_data(self, code):
        if self.name != 'airo':
            return
        # Epoch may create a new dated snapshot, or a writer may replace a symlink.
        for pattern in GENERATED_DATA:
            for p in (code / AIRO / 'data').glob(pattern):
                if p.is_file() and not p.is_symlink():
                    dest = self.state / 'data' / p.name
                    shutil.copy2(p, dest)
                    p.unlink()
                    p.symlink_to(dest)

    def verify_site(self, site):
        site_kit.verify(site, required=self.dashboard.required)
        if self.dashboard.block:
            blob = page.payload((site / 'index.html').read_bytes(), self.dashboard.block)
            if blob.get('synthetic'):
                raise RuntimeError('Cannot publish synthetic survey results')


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
            if response.status != 200 or body['release'] != release.name or body.get('dashboard', 'airo') != self.name:
                raise RuntimeError('Serving process did not activate the candidate')
        finally:
            connection.close()

    def publish_public(self, site):
        """An installation may mirror the verified static site to a separate ingress."""
        command = self.config.get('public_publisher')
        if command is None:
            return  # ingress serves the runtime socket directly
        if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command):
            raise ValueError('public_publisher must be a nonempty argv list')
        run([*command, site.resolve(strict=True)], timeout=900)

    def republish(self):
        with self.lock():
            site = (self.current / 'site').resolve(strict=True)
            self.verify_site(site)
            metadata = json.loads((site / 'release.json').read_text())
            if metadata['data_snapshot']['sha256'] != data_snapshot(site, self.dashboard.downloads)['sha256']:
                raise RuntimeError('Selected site differs from its recorded snapshot')
            self.publish_public(site)

    def activate(self, release):
        previous = self.current.resolve() if self.current.exists() else None
        link(release, self.current)
        try:
            self.probe(release)
            self.publish_public(release / 'site')
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
        snapshot = data_snapshot(source, self.dashboard.downloads)
        previous = prior.get('data_snapshot', {})
        if previous.get('sha256', snapshot['sha256']) != snapshot['sha256']:
            raise RuntimeError('Published data snapshot changed unexpectedly')
        project = code / self.dashboard.project
        if self.dashboard.assembled:
            template = (project / self.dashboard.assembled).read_bytes()
        else:
            web = project / self.dashboard.web
            template = page.render(web, dict.fromkeys(page.manifest(web)['blobs'])).encode()
        html = frontend_html(template, (source / 'index.html').read_bytes())
        shutil.copytree(source, site)
        (site / 'index.html').write_bytes(html)
        for asset, dest in self.dashboard.assets:
            assets = project / asset
            if assets.exists():
                target = site / dest
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(assets, target)
        self.verify_site(site)
        if data_snapshot(site, self.dashboard.downloads) != snapshot:
            raise RuntimeError('Frontend deployment changed published data')
        return {**snapshot,
                'origin_commit': previous.get('origin_commit', prior.get('publication_commit')),
                'source_release': previous.get('source_release', prior.get('release'))}

    def builder(self, code):
        """The candidate's own copy of this script, if it can build a release.
        A release is built by the code it carries, so a commit that moves files
        or changes the build deploys without the live release knowing how."""
        script = code / LAUNCHER
        if not self.config_path or not script.is_file():
            return None
        try:
            usage = output([sys.executable, script, '--help'])
        except (subprocess.CalledProcessError, OSError):
            return None
        if self.name != 'airo' and 'run-dashboard' not in usage:
            raise RuntimeError('Candidate predates multi-dashboard deployment')
        return script if 'build-release' in usage else None

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
                script = self.builder(code)
                if script:
                    run([sys.executable, script, '--config', self.config_path, 'build-release', '--release', name, '--commit', sha,
                         *(['--keep-publication'] if keep_publication else []), *(['--publish-data'] if publish_data else [])])
                else:   # a commit from before releases built themselves
                    self.build_release(name, sha, keep_publication=keep_publication, publish_data=publish_data)
            except Exception:
                # Keep the candidate and logs for diagnosis; never switch on failure.
                write_json(release / 'failed.json', {'at': datetime.now(timezone.utc).isoformat()})
                raise

    def build_release(self, name, sha, keep_publication=False, publish_data=False):
        """Install, publish and activate the checked-out release `name`. Called
        by deploy, which holds operation.lock (in the live release's process
        when this is the candidate's)."""
        if keep_publication and publish_data:
            raise ValueError('Choose either preserved publication or new data publication')
        if not re.fullmatch(r'\d{8}T\d{6}-[0-9a-f]{12}', name or '') or not re.fullmatch(r'[0-9a-f]{40}', sha or ''):
            raise ValueError('Expected a release name and its full commit SHA')
        release = self.root / 'releases' / name
        code = release / 'code'
        self.jobs(code)
        env = os.environ.copy()
        env.update(PATH=self.config['path'], TMPDIR=str(self.root / 'tmp'))
        run(['python3', '-m', 'venv', code / '.venv'], env=env)
        projects = PROJECTS if self.name == 'airo' else (FORECASTER, 'packages/dashboard', self.dashboard.project)
        run([code / '.venv/bin/pip', 'install', *(arg for project in projects for arg in ('-e', code / project))], env=env)
        run(['npm', 'ci', '--prefix', code / FORECASTER], env=env)
        (release / 'python-packages.txt').write_text(output([code / '.venv/bin/pip', 'freeze']))
        # A release whose failures would reach nobody does not go live.
        run([code / '.venv/bin/python', '-m', 'fri_forecaster.alert', 'check'], cwd=code, env=self.environment(code, self.root / 'tmp'))
        self.stage_data(code, copy_results=publish_data)
        site = self.root / 'sites' / name
        metadata = {'dashboard': self.name, 'release': name, 'commit': sha, 'publication': 'frontend', 'publication_commit': sha, 'frontend_commit': sha}
        if keep_publication:
            source = self.current / 'site' if self.current.exists() else Path(self.config['bootstrap_publication'])
            self.verify_site(source)
            shutil.copytree(source, site)
            prior = json.loads((source / 'release.json').read_text()) if (source / 'release.json').exists() else {}
            if self.name != 'airo':
                # Imported publications predate our release metadata. Record their data boundary.
                published = data_snapshot(site, self.dashboard.downloads)
                if prior.get('data_snapshot', published)['sha256'] != published['sha256']:
                    raise RuntimeError('Imported publication disagrees with its recorded snapshot')
                metadata['data_snapshot'] = published
            metadata.update(publication='preserved', publication_commit=prior.get('publication_commit', prior.get('commit')),
                            frontend_commit=prior.get('frontend_commit', prior.get('publication_commit')))
            if 'data_snapshot' in prior:
                metadata['data_snapshot'] = prior['data_snapshot']
        elif publish_data:
            site.mkdir()
            self.build_data(code, site, self.environment(code, site))
            self.verify_site(site)
            metadata.update(publication='rebuilt', data_snapshot={**data_snapshot(site, self.dashboard.downloads), 'origin_commit': sha, 'source_release': name})
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

    def rollback(self):
        with self.lock():
            release = (self.root / 'previous').resolve(strict=True)
            self.verify_site(release / 'site')
            self.activate(release)
            print(json.dumps({'rolled_back': release.name}))

    def execute_job(self, key, job, scheduled_minute=None):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', key):
            raise ValueError('Unsafe run key')
        with self.lock():
            receipt = self.root / 'runs' / (key + '.json')
            if scheduled_minute and datetime.now(timezone.utc).replace(second=0, microsecond=0) != scheduled_minute:
                return False  # the next tick records this as missed under the original key
            if receipt.exists():
                return False  # Includes interrupted/failed runs: no surprise paid retries.
            release = self.current.resolve(strict=True)
            code = release / 'code'
            started = {'key': key, 'job': job['id'], 'release': release.name, 'status': 'running', 'started': datetime.now(timezone.utc).isoformat()}
            write_json(receipt, started)
            site = self.root / 'sites' / ('job-' + key)
            ledger = self.root / 'runs' / (key + '.alerts.jsonl')
            airo = code / AIRO
            argv = {'forecast': ['bash', airo / 'code/cron_run.sh'],
                    'news-poll': [code / '.venv/bin/python', airo / 'code/recent_news.py', 'poll'],
                    'forecastbench': ['bash', code / FORECASTBENCH / 'scripts/fb_cron.sh', job.get('due', '')],
                    'smoke': [code / '.venv/bin/python', '-c', 'import redlines, eeai, forecastbench, fri_forecaster, dashboard; print("scheduled runtime smoke passed")']}[job['kind']]
            survey_job = job['kind'] == 'forecast' and self.name != 'airo'
            if job['kind'] == 'smoke' and self.name != 'airo':
                argv = [code / '.venv/bin/python', *self.dashboard.forecast[:2], '--help']
            cwd = code if job['kind'] in ('forecastbench', 'smoke') else code / self.dashboard.project
            stage = 'preflight FAILED'
            launched = False
            try:
                env = self.environment(code, site)
                env['FRI_ALERT_LEDGER'] = str(ledger)
                if job.get('paired_rationale_on') and key == job['id'] + '-' + date.fromisoformat(job['paired_rationale_on']).strftime('%Y%m%d'):
                    env['AIRO_PAIRED_RATIONALE'] = '1'
                due = ''
                if job['kind'] == 'forecast' and not survey_job:
                    due = output([code / '.venv/bin/python', '-m', 'redlines.experiments', 'due'], cwd=airo, env=env)
                    if not due.strip():
                        started.update(status='skipped', reason='No forecast conditions due')
                        return True
                expects_site = survey_job or any(len(row.split()) > 1 and row.split()[1] == 'publish'
                                   for row in due.splitlines())
                if job['kind'] == 'forecast':
                    self.prune_locked()
                if job['kind'] != 'smoke':
                    self.require_space(publish_data=expects_site, job_kind=job['kind'])
                site.mkdir()
                stage = 'run FAILED'
                with (self.root / 'logs' / (key + '.log')).open('a') as log:
                    if survey_job:
                        if self.panel_runtime:
                            primary = self.panel_runtime
                            primary_code = primary.current.resolve(strict=True) / 'code'
                            refresh = primary_code / AIRO / 'code/refresh_panel.sh'
                            try:
                                run(['bash', refresh], cwd=refresh.parent.parent,
                                    env=primary.environment(primary_code, primary.root / 'tmp'),
                                    stdout=log, stderr=subprocess.STDOUT)
                            finally:
                                primary.save_generated_data(primary_code)
                        incoming = self.state / 'attempts' / key
                        argv = self.project_command(code, self.dashboard.forecast, site, incoming)
                    launched = True
                    run(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
                if job['kind'] == 'forecastbench':
                    # fb_round's shell exit alone is insufficient; every expected set must build.
                    round_root = self.home / 'forecastbench/rounds' / job['due']
                    # Use the same CLI/config as the round, without exposing private names.
                    count = int(output(['bash', '-o', 'pipefail', '-c', 'set -a; source "$FORECASTER_ROUND_ENV"; set +a; "$PY" -m forecastbench.names conditions | wc -l'], cwd=code, env=env))
                    built = (round_root / 'logs/round.log').read_text().count('build exited 0')
                    if count == 0 or built < count:
                        raise RuntimeError('ForecastBench has incomplete submission sets')
                stage = 'publish FAILED'   # the run succeeded; what follows only publishes it
                if survey_job:
                    # The runners produce one file (EEAI) or directory (RSI).
                    # Failed attempts stay private; later builds read completed runs only.
                    artifacts = list(incoming.iterdir())
                    if len(artifacts) != 1:
                        raise RuntimeError('Expected one completed survey run')
                    artifact, = artifacts
                    results = self.state / 'results'
                    results.mkdir(parents=True, exist_ok=True)
                    target = results / artifact.name
                    if target.exists():
                        raise RuntimeError(f'Run already exists: {artifact.name}')
                    artifact.rename(target)
                    with (self.root / 'logs' / (key + '.log')).open('a') as log:
                        self.build_data(code, site, env, stdout=log, stderr=subprocess.STDOUT)
                if expects_site or (site / 'index.html').exists():
                    self.verify_site(site)
                    meta = json.loads((release / 'release.json').read_text())
                    meta.update(publication='rebuilt', publication_commit=meta['commit'], frontend_commit=meta['commit'],
                                data_snapshot={**data_snapshot(site, self.dashboard.downloads), 'origin_commit': meta['commit'], 'source_release': 'job-' + key})
                    write_json(site / 'release.json', meta)
                    link(site, release / 'site')
                    write_json(release / 'release.json', meta)
                    self.publish_public(site)
                started.update(status='succeeded')
            except Exception as exc:
                started.update(status='failed', error=type(exc).__name__, stage=stage)
                # Keep the reason in the private log, including failures before launch.
                with (self.root / 'logs' / (key + '.log')).open('a') as log:
                    print(f'{stage}: {type(exc).__name__}: {exc}', file=log)
                if job['kind'] != 'smoke' and not paged(ledger):  # the job's own page says more than this one
                    failure = 'failed'
                    if job['kind'] == 'forecast':
                        failure = 'failed to publish dashboard' if stage == 'publish FAILED' else 'failed to produce forecast'
                    self.alert(job, f"{key}: {failure} ({type(exc).__name__}). It is not retried.",
                               log=self.root / 'logs' / (key + '.log'), title=stage)
                raise
            finally:
                try:
                    if launched:
                        self.save_generated_data(code)
                finally:
                    started['finished'] = datetime.now(timezone.utc).isoformat()
                    write_json(receipt, started)
            return True

    def report_unrun(self, jobs, now):
        """Page, once each, for a job that died mid-run and for one whose minute
        passed with no start (the scheduler was down, or busy with another job:
        jobs run one at a time). Neither is run late; the receipt says what happened."""
        with self.lock():   # held, so no job is running: a receipt that says so is a dead one
            runs = self.root / 'runs'
            for receipt in runs.glob('*.json'):
                if now.timestamp() - receipt.stat().st_mtime > 7 * 86400:
                    continue
                record = json.loads(receipt.read_text())
                if record.get('status') != 'running':
                    continue
                record.update(status='interrupted', finished=now.isoformat())
                write_json(receipt, record)
                job = next((j for j in jobs if j['id'] == record.get('job')), None)
                if job and job['kind'] != 'smoke':
                    self.alert(job, f"{record['key']} was running when the scheduler stopped. It is not resumed.",
                               log=self.root / 'logs' / (record['key'] + '.log'))
            # Only since this release and schedule were switched on: a job added with a past time was never due here.
            since = max(datetime.fromtimestamp(max(os.lstat(self.current).st_mtime, (self.root / 'jobs-enabled').stat().st_mtime), timezone.utc),
                        now - timedelta(days=2))
            for key, job, at in scheduled_between(jobs, since, now.replace(second=0, microsecond=0)):
                receipt = runs / (key + '.json')
                if receipt.exists():
                    continue
                if job['kind'] == 'forecast' and self.name == 'airo':
                    code = self.current.resolve(strict=True) / 'code'
                    try:
                        due = output([code / '.venv/bin/python', '-m', 'redlines.experiments',
                                      'due', '--date', at.date().isoformat()],
                                     cwd=code / AIRO, env=self.environment(code, self.root / 'tmp'))
                    except Exception as exc:
                        log = self.root / 'logs' / (key + '.log')
                        log.write_text(f'preflight FAILED: {type(exc).__name__}: {exc}\n')
                        write_json(receipt, {'key': key, 'job': job['id'], 'status': 'failed',
                                            'stage': 'preflight FAILED', 'error': type(exc).__name__,
                                            'started': at.isoformat(), 'finished': now.isoformat()})
                        self.alert(job, f'{key}: could not check the forecast schedule. It is not run late.',
                                   log=log, title='preflight FAILED')
                        continue
                    if not due.strip():
                        write_json(receipt, {'key': key, 'job': job['id'], 'status': 'skipped',
                                            'reason': 'No forecast conditions due',
                                            'started': at.isoformat(), 'finished': now.isoformat()})
                        continue
                write_json(receipt, {'key': key, 'job': job['id'], 'status': 'missed', 'started': at.isoformat(), 'finished': now.isoformat()})
                self.alert(job, f"{key} was due at {at:%Y-%m-%d %H:%M} UTC and never started: "
                           'the scheduler was not running, or was busy with another job. It is not run late.')

    def tick(self):
        if not self.current.exists() or not (self.root / 'jobs-enabled').exists():
            return
        jobs = self.jobs(self.current / 'code')
        now = datetime.now(timezone.utc)
        self.report_unrun(jobs, now)
        for key, job in due_jobs(jobs, now):
            self.execute_job(key, job, scheduled_minute=now.replace(second=0, microsecond=0))

    def status(self):
        print(json.dumps({'storage': self.storage_status(),
                          'release': json.loads((self.current / 'release.json').read_text()) if self.current.exists() else None,
                          'jobs_enabled': (self.root / 'jobs-enabled').exists(),
                          'jobs': self.jobs(self.current / 'code') if self.current.exists() else [],
                          'recent_runs': sorted((json.loads(p.read_text()) for p in (self.root / 'runs').glob('*.json')),
                                                key=lambda receipt: receipt.get('started', ''), reverse=True)[:10]}, indent=2))

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
    parser.add_argument('command', choices=['deploy', 'rollback', 'status', 'tick', 'serve', 'smoke', 'prune', 'storage', 'build-release',
                                            'configure-forecastbench', 'check-forecastbench-upload', 'run-dashboard', 'republish'])
    parser.add_argument('--upload-prefix', help='configure-forecastbench: gs://bucket/team-prefix/binary; key JSON on stdin')
    parser.add_argument('--due', help='check-forecastbench-upload: round folder date for a .txt access probe')
    parser.add_argument('--commit')
    parser.add_argument('--release', help='build-release only (deploy runs it in the candidate): the checked-out release to build')
    publication = parser.add_mutually_exclusive_group()
    publication.add_argument('--keep-publication', action='store_true', help='Retain the entire website while deploying code and schedules')
    publication.add_argument('--publish-data', action='store_true', help='Rebuild and validate forecast data as part of deployment; never launches forecast jobs')
    parser.add_argument('--run-id', help='unique durable receipt ID (required for a paid manual run)')
    args = parser.parse_args()
    runtime = Runtime(json.loads(Path(args.config).read_text()), config_path=args.config)
    if args.command == 'deploy': runtime.deploy(args.commit, keep_publication=args.keep_publication, publish_data=args.publish_data)
    elif args.command == 'build-release': runtime.build_release(args.release, args.commit, keep_publication=args.keep_publication, publish_data=args.publish_data)
    elif args.command == 'run-dashboard':
        if not args.run_id:
            parser.error('run-dashboard requires --run-id')
        runtime.execute_job(args.run_id, {'id': runtime.name, 'kind': 'forecast'})
        receipt = json.loads((runtime.root / 'runs' / (args.run_id + '.json')).read_text())
        print(json.dumps(receipt, indent=2))
        if receipt.get('status') not in ('succeeded', 'skipped'):
            raise SystemExit(1)
    elif args.command == 'smoke': runtime.execute_job(args.run_id or 'smoke-' + uuid.uuid4().hex[:12], {'id': 'smoke', 'kind': 'smoke'})
    elif args.command in ('configure-forecastbench', 'check-forecastbench-upload') and runtime.name != 'airo':
        parser.error('ForecastBench is managed by the AIRO runtime')
    elif args.command == 'configure-forecastbench': runtime.configure_forecastbench(args.upload_prefix, json.load(sys.stdin))
    elif args.command == 'check-forecastbench-upload': runtime.check_forecastbench_upload(args.due)
    else: getattr(runtime, args.command)()


if __name__ == '__main__':
    main()
