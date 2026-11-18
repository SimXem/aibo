"""Release and scheduler failure tests; never call a provider or GitHub."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

spec = importlib.util.spec_from_file_location('production', Path(__file__).parents[1] / 'production.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(p.shutil, 'disk_usage', lambda _: type('Disk', (), {
        'total': 50*1024**3, 'used': 10*1024**3, 'free': 40*1024**3})())
    return p.Runtime({'root': str(tmp_path), 'path': '/usr/bin:/bin', 'socket': str(tmp_path / 'site.sock')})


def release(runtime, name):
    r = runtime.root / 'releases' / name
    (r / 'code' / p.AIRO / 'data').mkdir(parents=True)
    p.write_json(r / 'release.json', {'release': name, 'commit': 'a' * 40})
    return r


def test_activation_rolls_back_when_serving_process_rejects_candidate(runtime, monkeypatch):
    old, new = release(runtime, 'old'), release(runtime, 'new')
    p.link(old, runtime.current)
    def reject(candidate):
        assert runtime.current.resolve() == new
        raise RuntimeError('unhealthy')
    monkeypatch.setattr(runtime, 'probe', reject)
    with pytest.raises(RuntimeError, match='unhealthy'):
        runtime.activate(new)
    assert runtime.current.resolve() == old
    assert not (runtime.root / 'last-deploy.json').exists()


def test_initial_failure_leaves_no_active_release(runtime, monkeypatch):
    new = release(runtime, 'new')
    monkeypatch.setattr(runtime, 'probe', lambda _: (_ for _ in ()).throw(RuntimeError('unhealthy')))
    with pytest.raises(RuntimeError):
        runtime.activate(new)
    assert not runtime.current.exists()


def test_rollback_selects_previous_code_and_site_without_resetting_data(runtime, monkeypatch):
    old, new = release(runtime, 'old'), release(runtime, 'new')
    runtime.state.mkdir()
    data = runtime.state / 'accrued.jsonl'
    data.write_text('latest forecast\n')
    monkeypatch.setattr(runtime, 'probe', lambda _: None)
    monkeypatch.setattr(runtime, 'verify_site', lambda _: None)
    runtime.activate(old)
    runtime.activate(new)
    runtime.rollback()
    assert runtime.current.resolve() == old
    assert data.read_text() == 'latest forecast\n'
    assert (runtime.root / 'previous').resolve() == new


def test_staging_build_cannot_modify_accrued_data(runtime):
    (runtime.state / 'results').mkdir(parents=True)
    (runtime.state / 'data').mkdir()
    raw = runtime.state / 'results/runs.jsonl'
    raw.write_text('accrued\n')
    (runtime.state / 'data/epoch_capabilities_index_2030-01-01.csv').write_text('live')
    r = release(runtime, 'candidate')
    runtime.stage_data(r / 'code')
    (r / 'code' / p.AIRO / 'results/runs.jsonl').write_text('bad build')
    assert raw.read_text() == 'accrued\n'
    runtime.attach_state(r / 'code')
    assert (r / 'code' / p.AIRO / 'results/runs.jsonl').read_text() == 'accrued\n'


def test_job_receipt_prevents_duplicate_after_process_restart(runtime, monkeypatch):
    r = release(runtime, 'old')
    p.link(r, runtime.current)
    calls = []
    monkeypatch.setattr(p, 'run', lambda *args, **kw: calls.append(args))
    assert runtime.execute_job('unique-minute', {'id': 'smoke', 'kind': 'smoke'})
    restarted = p.Runtime(runtime.config)
    assert not restarted.execute_job('unique-minute', {'id': 'smoke', 'kind': 'smoke'})
    assert len(calls) == 1
    assert json.loads((runtime.root / 'runs/unique-minute.json').read_text())['status'] == 'succeeded'


def test_failed_or_interrupted_paid_job_is_not_automatically_retried(runtime, monkeypatch):
    r = release(runtime, 'old')
    p.link(r, runtime.current)
    def fail(*args, **kw):
        raise subprocess.CalledProcessError(1, 'job')
    monkeypatch.setattr(p, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        runtime.execute_job('failed', {'id': 'smoke', 'kind': 'smoke'})
    assert json.loads((runtime.root / 'runs/failed.json').read_text())['status'] == 'failed'
    assert not runtime.execute_job('failed', {'id': 'smoke', 'kind': 'smoke'})
    p.write_json(runtime.root / 'runs/interrupted.json', {'status': 'running'})
    assert not runtime.execute_job('interrupted', {'id': 'smoke', 'kind': 'smoke'})


def test_scheduler_has_explicit_year_and_no_reboot_catchup():
    jobs = [{'id': 'round', 'kind': 'forecastbench', 'at': '2030-11-08T00:05:00Z', 'due': '2030-11-08'}]
    assert len(list(p.due_jobs(jobs, datetime(2030, 11, 8, 0, 5, 40, tzinfo=timezone.utc)))) == 1
    assert not list(p.due_jobs(jobs, datetime(2031, 11, 8, 0, 5, tzinfo=timezone.utc)))
    assert not list(p.due_jobs(jobs, datetime(2030, 11, 8, 0, 6, tzinfo=timezone.utc)))


def test_scheduler_rejects_ambiguous_or_duplicate_schedules():
    with pytest.raises(ValueError):
        p.validate_jobs([{'id': 'bad', 'kind': 'forecast', 'at': '2030-11-08T00:05:00'}])
    job = {'id': 'duplicate', 'kind': 'forecast', 'daily_utc': '12:00'}
    with pytest.raises(ValueError):
        p.validate_jobs([job, job])


def test_partial_publication_and_symlink_are_rejected(runtime, tmp_path):
    site = tmp_path / 'test-site'
    site.mkdir()
    (site / 'index.html').write_text('<html>ready</html>')
    with pytest.raises(RuntimeError, match='Incomplete'):
        runtime.verify_site(site)
    for name in ('forecasts.csv', 'rationales.csv', 'redlines-data.zip'):
        (site / name).write_text('data')
    runtime.verify_site(site)
    (site / 'private').symlink_to('/etc/passwd')
    with pytest.raises(RuntimeError, match='symlinks'):
        runtime.verify_site(site)


def test_failed_build_never_activates_or_modifies_live_data(runtime, monkeypatch):
    old = release(runtime, 'old')
    p.link(old, runtime.current)
    runtime.state.mkdir()
    data = runtime.state / 'raw.jsonl'
    data.write_text('preserved')
    monkeypatch.setattr(runtime, 'merged_sha', lambda _: 'a' * 40)
    def fail(*args, **kw):
        raise subprocess.CalledProcessError(1, 'install failed')
    monkeypatch.setattr(p, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        runtime.deploy()
    assert runtime.current.resolve() == old
    assert data.read_text() == 'preserved'


def test_newest_failed_check_cannot_be_hidden_by_previous_pass(runtime, monkeypatch):
    runtime.config.update(repository='https://example.invalid/repo.git', github_repository='example/project')
    checks = [{'id': i, 'name': name, 'status': 'completed', 'conclusion': 'success', 'app': {'slug': 'github-actions'}} for i, name in enumerate(p.REQUIRED_CHECKS)]
    checks.append({'id': 100, 'name': 'reproduce', 'status': 'completed', 'conclusion': 'failure', 'app': {'slug': 'github-actions'}})
    monkeypatch.setattr(p, 'run', lambda *a, **kw: None)
    monkeypatch.setattr(p, 'output', lambda args, **kw: json.dumps({'check_runs': checks}) if args[0] == 'gh' else 'a' * 40)
    with pytest.raises(RuntimeError, match='reproduce'):
        runtime.merged_sha()


def test_forecast_environment_uses_proxy_and_separate_agent_directory(runtime, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'coding-session-key')
    env = runtime.environment(runtime.root / 'code', runtime.root / 'site')
    assert env['NODE_USE_ENV_PROXY'] == '1'
    assert env['PI_CODING_AGENT_DIR'] == str(runtime.home / 'pi-agent')
    assert env['HOME'] == str(runtime.home)
    assert 'OPENAI_API_KEY' not in env


def test_uploader_setup_keeps_credentials_private_and_outside_release(runtime, monkeypatch):
    selected = release(runtime, 'uploader')
    p.link(selected, runtime.current)
    key = {'type': 'service_account', 'client_email': 'uploader@example.iam.gserviceaccount.com',
           'private_key': '-----BEGIN PRIVATE KEY-----\nexample',
           'token_uri': 'https://oauth2.googleapis.com/token'}
    calls = []
    def verify(argv, **kwargs):
        candidate = Path(kwargs['env']['FB_UPLOAD_KEY_FILE'])
        assert json.loads(candidate.read_text()) == key
        assert candidate.stat().st_mode & 0o777 == 0o600
        calls.append(argv)
    monkeypatch.setattr(p, 'run', verify)
    runtime.configure_forecastbench('gs://bucket/team/binary', key)
    private = runtime.home / '.config/forecastbench-uploader'
    assert json.loads((private / 'key.json').read_text()) == key
    assert private.stat().st_mode & 0o777 == 0o700
    assert (private / 'key.json').stat().st_mode & 0o777 == 0o600
    assert json.loads((private / 'settings.json').read_text()) == {
        'prefix': 'gs://bucket/team/binary', 'account': key['client_email']}
    assert not (private / 'candidate-key.json').exists()
    assert len(calls) == 1
    monkeypatch.setattr(p, 'run', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('auth failed')))
    with pytest.raises(RuntimeError, match='auth failed'):
        runtime.configure_forecastbench('gs://bucket/other/binary', dict(key, private_key='-----BEGIN PRIVATE KEY-----\nreplacement'))
    assert json.loads((private / 'key.json').read_text()) == key
    assert not (private / 'candidate-key.json').exists()


def test_uploader_setup_refuses_personal_credentials(runtime):
    with pytest.raises(ValueError, match='service-account JSON key'):
        runtime.configure_forecastbench('gs://bucket/team/binary', {'type': 'authorized_user'})


def test_preserved_publication_requires_explicit_request_and_keeps_its_provenance(runtime, monkeypatch):
    runtime.config['repository'] = 'https://example.invalid/repo.git'
    runtime.config['github_repository'] = 'example/project'
    source = runtime.root / 'imported-site'
    source.mkdir()
    for name in ('forecasts.csv', 'rationales.csv', 'redlines-data.zip'):
        (source / name).write_text('published data')
    (source / 'index.html').write_text('<html>last good publication</html>')
    p.write_json(source / 'release.json', {'commit': 'b' * 40})
    runtime.config['bootstrap_publication'] = str(source)
    monkeypatch.setattr(runtime, 'merged_sha', lambda _: 'a' * 40)
    def fake_run(argv, **kw):
        if argv[:2] == ['git', 'clone']:
            code = Path(argv[-1])
            (code / 'packages/ops').mkdir(parents=True)
            (code / 'packages/ops/jobs.json').write_text('[]')
        if 'publish_dashboard.sh' in str(argv):
            raise AssertionError('Preserve must not rebuild data')
    monkeypatch.setattr(p, 'run', fake_run)
    monkeypatch.setattr(p, 'output', lambda *a, **kw: 'dependency inventory')
    monkeypatch.setattr(runtime, 'stage_data', lambda code, copy_results: None)
    monkeypatch.setattr(runtime, 'attach_state', lambda _: None)
    monkeypatch.setattr(runtime, 'probe', lambda _: None)
    runtime.deploy(keep_publication=True)
    meta = json.loads((runtime.current / 'release.json').read_text())
    assert meta['commit'] == 'a' * 40
    assert meta['publication'] == 'preserved'
    assert meta['publication_commit'] == 'b' * 40
    assert (runtime.current / 'site/index.html').read_bytes() == (source / 'index.html').read_bytes()


def dashboard(label, value, name='TIMELINE'):
    return ('<html><head><!--' + name + '_DATA-->\n<script>window.__' + name + '__ = ' +
            json.dumps({'value': value, 'instrument': 'published-version'}) +
            ';</script>\n<!--/' + name + '_DATA--></head><body>' + label + '</body></html>').encode()


def published_release(runtime):
    old = release(runtime, 'published')
    site = old / 'site'
    site.mkdir()
    (site / 'index.html').write_bytes(dashboard('old dot layout', 10))
    for name in p.DATA_FILES:
        (site / name).write_bytes(b'published forecast bytes\x00\xff')
    p.write_json(site / 'release.json', {'release': 'published', 'commit': 'b' * 40, 'publication_commit': 'b' * 40})
    p.link(old, runtime.current)
    return old


def fake_install(runtime, monkeypatch, publication=None):
    monkeypatch.setattr(runtime, 'merged_sha', lambda _: 'a' * 40)
    def command(argv, **kw):
        if argv[:2] == ['git', 'clone']:
            code = Path(argv[-1])
            (code / 'packages/ops').mkdir(parents=True)
            (code / 'packages/ops/jobs.json').write_text('[]')
            (code / p.AIRO).mkdir(parents=True)
            (code / p.AIRO / 'index.html').write_bytes(dashboard('aligned dots', 999))
        if 'publish_dashboard.sh' in str(argv):
            if publication is None:
                raise AssertionError('Frontend deployment must not build new forecast data')
            publication(Path(kw['env']['REDLINES_DOCROOT']))
    monkeypatch.setattr(p, 'run', command)
    monkeypatch.setattr(p, 'output', lambda *a, **kw: 'dependencies')
    monkeypatch.setattr(runtime, 'stage_data', lambda code, copy_results: None)
    monkeypatch.setattr(runtime, 'attach_state', lambda _: None)
    monkeypatch.setattr(runtime, 'probe', lambda _: None)


def test_frontend_deploy_publishes_new_ui_with_exact_existing_data_and_exports(runtime, monkeypatch):
    old = published_release(runtime)
    fake_install(runtime, monkeypatch)
    runtime.deploy()
    site = runtime.current / 'site'
    assert b'aligned dots' in (site / 'index.html').read_bytes()
    assert p.data_blocks((site / 'index.html').read_bytes()) == p.data_blocks((old / 'site/index.html').read_bytes())
    for name in p.DATA_FILES:
        assert (site / name).read_bytes() == (old / 'site' / name).read_bytes()
    meta = json.loads((site / 'release.json').read_text())
    assert meta['publication'] == 'frontend'
    assert meta['frontend_commit'] == 'a' * 40
    assert meta['data_snapshot']['origin_commit'] == 'b' * 40
    assert meta['data_snapshot']['sha256'] == p.data_snapshot(old / 'site')['sha256']
    assert (runtime.root / 'previous').resolve() == old


def test_data_publication_failure_cannot_fall_back_or_change_current_site(runtime, monkeypatch):
    old = published_release(runtime)
    def reject(_):
        raise subprocess.CalledProcessError(1, 'publication integrity check')
    fake_install(runtime, monkeypatch, reject)
    with pytest.raises(subprocess.CalledProcessError):
        runtime.deploy(publish_data=True)
    assert runtime.current.resolve() == old
    assert b'old dot layout' in (old / 'site/index.html').read_bytes()


def test_explicit_validated_data_publication_updates_data_provenance(runtime, monkeypatch):
    published_release(runtime)
    def publish(site):
        (site / 'index.html').write_bytes(dashboard('aligned dots', 20))
        for name in p.DATA_FILES:
            (site / name).write_text('new validated forecast data')
    fake_install(runtime, monkeypatch, publish)
    runtime.deploy(publish_data=True)
    meta = json.loads((runtime.current / 'site/release.json').read_text())
    assert meta['publication'] == 'rebuilt'
    assert meta['data_snapshot']['origin_commit'] == 'a' * 40
    assert b'20' in (runtime.current / 'site/index.html').read_bytes()


def test_frontend_requires_existing_publication_and_compatible_markers(runtime, monkeypatch):
    fake_install(runtime, monkeypatch)
    with pytest.raises(RuntimeError, match='No published data snapshot'):
        runtime.deploy()
    assert not runtime.current.exists()
    with pytest.raises(RuntimeError, match='data blocks changed'):
        p.frontend_html(dashboard('new', 5, 'DIFFERENT'), dashboard('old', 3))


@pytest.mark.parametrize('bad', [
    b'<html>no data</html>',
    dashboard('old', 1).replace(b'<!--/TIMELINE_DATA-->', b''),
    dashboard('old', 1) + dashboard('old', 1),
    dashboard('old', 1).replace(b'window.__TIMELINE__', b'window.__OTHER__'),
    dashboard('old', 1).replace(b'<script>', b'<script>bad();'),
])
def test_frontend_rejects_malformed_or_ambiguous_data_boundaries(bad):
    with pytest.raises((RuntimeError, ValueError)):
        p.frontend_html(dashboard('new', 2), bad)


def test_frontend_detects_corrupt_snapshot_and_retains_original_provenance(runtime):
    old = published_release(runtime)
    source = old / 'site'
    meta = json.loads((source / 'release.json').read_text())
    meta.update(publication_commit='c' * 40, data_snapshot={**p.data_snapshot(source), 'origin_commit': None, 'source_release': 'imported'})
    p.write_json(source / 'release.json', meta)
    code = runtime.root / 'candidate-code'
    (code / p.AIRO).mkdir(parents=True)
    (code / p.AIRO / 'index.html').write_bytes(dashboard('aligned dots', 999))
    snapshot = runtime.publish_frontend(code, runtime.root / 'candidate-site')
    assert snapshot['origin_commit'] is None
    assert snapshot['source_release'] == 'imported'
    (source / 'forecasts.csv').write_text('unexpected alteration')
    with pytest.raises(RuntimeError, match='changed unexpectedly'):
        runtime.publish_frontend(code, runtime.root / 'another-site')


def test_frontend_updates_static_assets_without_changing_the_previous_site(runtime):
    old = published_release(runtime)
    code = runtime.root / 'candidate-code'
    (code / p.AIRO / 'web/img').mkdir(parents=True)
    (code / p.AIRO / 'index.html').write_bytes(dashboard('new', 999))
    (code / p.AIRO / 'web/img/logo.svg').write_text('<svg>new logo</svg>')
    site = runtime.root / 'candidate-site'
    runtime.publish_frontend(code, site)
    assert (site / 'web/img/logo.svg').read_text() == '<svg>new logo</svg>'
    assert not (old / 'site/web/img/logo.svg').exists()


def test_scheduled_publication_records_new_data_snapshot(runtime, monkeypatch):
    old = published_release(runtime)
    before = (old / 'site').resolve()
    # Production sites live outside releases; mirror that layout in this fixture.
    saved = runtime.root / 'sites/before'
    before.rename(saved)
    p.link(saved, old / 'site')
    monkeypatch.setattr(p, 'output', lambda *a, **kw: 'fixture publish')
    def publish(argv, **kw):
        site = Path(kw['env']['REDLINES_DOCROOT'])
        (site / 'index.html').write_bytes(dashboard('new forecast', 25))
        for name in p.DATA_FILES:
            (site / name).write_text('validated new forecast')
    monkeypatch.setattr(p, 'run', publish)
    runtime.execute_job('fixture-new-data', {'id': 'forecast', 'kind': 'forecast'})
    meta = json.loads((old / 'site/release.json').read_text())
    assert meta['publication'] == 'rebuilt'
    assert meta['data_snapshot']['sha256'] == p.data_snapshot(old / 'site')['sha256']
    assert meta['data_snapshot']['source_release'] == 'job-fixture-new-data'
    assert b'old dot layout' in (saved / 'index.html').read_bytes()


def test_news_poll_is_free_standalone_job_with_persistent_private_state(runtime, monkeypatch):
    r = release(runtime, 'news')
    p.link(r, runtime.current)
    calls = []
    monkeypatch.setattr(p, 'run', lambda *args, **kw: calls.append((args, kw)))
    jobs = p.validate_jobs([{'id': 'recent-news-poll', 'kind': 'news-poll', 'daily_utc': '11:45'}])
    assert len(list(p.due_jobs(jobs, datetime(2026, 10, 23, 11, 45, tzinfo=timezone.utc)))) == 1
    assert not list(p.due_jobs(jobs, datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)))
    assert runtime.execute_job('news-poll-test', jobs[0])
    args, kw = calls[0]
    assert [str(x) for x in args[0]][-2:] == [str(r / 'code' / p.AIRO / 'code/recent_news.py'), 'poll']
    assert kw['env']['AIRO_NEWS_DIR'] == str(runtime.state / 'recent-news')
    assert runtime.current.resolve() == r


def test_retention_keeps_rollback_job_site_and_accrued_data(runtime):
    names = [f'20300101T00000{i}-' + 'a' * 12 for i in range(5)]
    versions = [release(runtime, name) for name in names]
    for r in versions:
        site = runtime.root / 'sites' / r.name
        site.mkdir()
        (site / 'index.html').write_text(r.name)
        p.link(site, r / 'site')
    p.link(versions[1], runtime.current)
    p.link(versions[0], runtime.root / 'previous')
    job = runtime.root / 'sites/job-active'
    job.mkdir()
    p.link(job, versions[1] / 'site')
    runtime.state.mkdir()
    (runtime.state / 'raw').write_text('do not remove')
    (runtime.root / 'runs/job.json').write_text('{}')
    (runtime.root / 'logs/job.log').write_text('diagnostic')
    # A failed candidate without its final site symlink retains its partial site.
    (versions[-1] / 'site').unlink()
    runtime.prune()
    assert all(r.exists() for r in [versions[0], versions[1], versions[4]])
    assert not versions[2].exists() and not versions[3].exists()
    assert job.exists()
    assert (runtime.root / 'sites' / names[-1]).exists()
    assert not (runtime.root / 'sites' / names[2]).exists()
    assert (runtime.state / 'raw').read_text() == 'do not remove'
    assert (runtime.root / 'runs/job.json').exists()
    assert (runtime.root / 'logs/job.log').exists()


def test_retention_never_follows_external_symlinks(runtime, tmp_path):
    external = tmp_path / 'external'
    external.mkdir()
    (external / 'precious').write_text('keep')
    (runtime.root / 'releases/20300101T000000-aaaaaaaaaaaa').symlink_to(external)
    (runtime.root / 'sites/job-external').symlink_to(external)
    runtime.prune()
    assert (external / 'precious').read_text() == 'keep'
    p.link(external, runtime.current)
    with pytest.raises(RuntimeError, match='escapes'):
        runtime.prune()


def test_low_disk_preflight_does_not_fetch_install_or_change_current(runtime, monkeypatch):
    old = release(runtime, 'old')
    p.link(old, runtime.current)
    monkeypatch.setattr(p.shutil, 'disk_usage', lambda _: type('Disk', (), {'total': 10*1024**3, 'used': 9*1024**3, 'free': 1024**3})())
    monkeypatch.setattr(runtime, 'merged_sha', lambda _: pytest.fail('must not fetch'))
    with pytest.raises(RuntimeError, match='Insufficient deployment storage'):
        runtime.deploy()
    assert runtime.current.resolve() == old
    assert list((runtime.root / 'releases').iterdir()) == [old]
    assert not runtime.storage_status()['healthy']


def test_low_disk_records_and_pages_preflight_failure_without_paid_work(runtime, monkeypatch):
    p.link(release(runtime, "old"), runtime.current)
    monkeypatch.setattr(p, "output", lambda *a, **kw: "airo publish none")
    sent = alerts(runtime, monkeypatch)
    def no_space(**kw):
        raise RuntimeError('Insufficient deployment storage')
    monkeypatch.setattr(runtime, 'require_space', no_space)
    monkeypatch.setattr(p, 'run', lambda *a, **kw: pytest.fail('must not run paid work'))
    with pytest.raises(RuntimeError, match='Insufficient'):
        runtime.execute_job('paid', {'id': 'forecast', 'kind': 'forecast'})
    receipt = json.loads((runtime.root / 'runs/paid.json').read_text())
    assert receipt['status'] == 'failed'
    assert receipt['stage'] == 'preflight FAILED'
    assert receipt['finished']
    assert 'Insufficient deployment storage' in (runtime.root / 'logs/paid.log').read_text()
    assert len(sent) == 1 and sent[0][1] == 'preflight FAILED'
    assert not runtime.execute_job('paid', {'id': 'forecast', 'kind': 'forecast'})
    assert len(sent) == 1


def test_inode_exhaustion_blocks_deployment(runtime, monkeypatch):
    monkeypatch.setattr(runtime, 'storage_status', lambda: {'free_bytes': 100*1024**3, 'min_free_bytes': 5*1024**3, 'inode_used_percent': 99})
    with pytest.raises(RuntimeError, match='inode usage 99'):
        runtime.require_space()


def test_status_lists_receipts_by_start_time_not_filename(runtime, capsys):
    # Alphabetical slicing previously hid airo-* behind news and smoke keys.
    for i in range(12):
        p.write_json(runtime.root / 'runs' / f'z-smoke-{i}.json',
                     {'key': f'z-smoke-{i}', 'started': f'2026-10-{i+1:02}T12:00:00Z'})
    p.write_json(runtime.root / 'runs/airo-latest.json',
                 {'key': 'airo-latest', 'started': '2026-10-28T12:00:00Z', 'status': 'failed'})
    runtime.status()
    receipts = json.loads(capsys.readouterr().out)['recent_runs']
    assert len(receipts) == 10
    assert receipts[0]['key'] == 'airo-latest'


def alerts(runtime, monkeypatch):
    sent = []
    monkeypatch.setattr(runtime, 'alert', lambda job, message, log=None, title='run FAILED': sent.append((job['id'], title, message)))
    return sent


def test_failed_job_pages_once_unless_the_job_already_paged(runtime, monkeypatch):
    p.link(release(runtime, 'old'), runtime.current)
    sent = alerts(runtime, monkeypatch)
    def fail(argv, **kw):
        raise subprocess.CalledProcessError(1, 'job')
    monkeypatch.setattr(p, 'run', fail)
    monkeypatch.setattr(p, 'output', lambda *a, **kw: 'airo publish none')
    job = {'id': 'airo', 'kind': 'forecast', 'daily_utc': '12:00'}
    with pytest.raises(subprocess.CalledProcessError):
        runtime.execute_job('quiet-job', job)
    assert [(j, t) for j, t, _ in sent] == [('airo', 'run FAILED')]
    def page_then_fail(argv, **kw):   # the job says what went wrong itself, through the shared sender's ledger
        Path(kw['env']['FRI_ALERT_LEDGER']).write_text(json.dumps({'severity': 'page', 'title': 'run FAILED'}) + '\n')
        raise subprocess.CalledProcessError(1, 'job')
    monkeypatch.setattr(p, 'run', page_then_fail)
    with pytest.raises(subprocess.CalledProcessError):
        runtime.execute_job('loud-job', job)
    assert len(sent) == 1


def test_a_run_that_succeeds_but_cannot_publish_is_a_publish_failure(runtime, monkeypatch):
    p.link(release(runtime, 'old'), runtime.current)
    sent = alerts(runtime, monkeypatch)
    def run_and_write_a_bad_site(argv, **kw):
        (Path(kw['env']['REDLINES_DOCROOT']) / 'index.html').write_text('not a dashboard')
    monkeypatch.setattr(p, 'run', run_and_write_a_bad_site)
    monkeypatch.setattr(p, 'output', lambda *a, **kw: 'airo publish none')
    with pytest.raises(Exception):
        runtime.execute_job('bad-site', {'id': 'airo', 'kind': 'forecast', 'daily_utc': '12:00'})
    assert [(j, t) for j, t, _ in sent] == [('airo', 'publish FAILED')]


def test_a_failed_news_poll_is_a_notice_and_a_failed_run_a_page(runtime, monkeypatch):
    r = release(runtime, 'old')
    p.link(r, runtime.current)
    sent = []
    monkeypatch.setattr(p.subprocess, 'run', lambda argv, **kw: sent.append([str(a) for a in argv]))
    runtime.alert({'id': 'recent-news-poll', 'kind': 'news-poll'}, 'poll failed')
    runtime.alert({'id': 'airo', 'kind': 'forecast'}, 'run failed')
    runtime.alert({'id': 'round', 'kind': 'forecastbench'}, 'not ready')
    def args(argv):
        return [argv[argv.index(flag) + 1] for flag in ('--deployment', '--severity', '--title')]
    assert [args(a) for a in sent] == [['airo', 'notice', 'news fetch failed'], ['airo', 'page', 'run FAILED'],
                                      ['forecastbench', 'page', 'run FAILED']]


def test_missed_and_interrupted_jobs_page_once_and_are_not_run_late(runtime, monkeypatch):
    monkeypatch.setattr(p, "output", lambda *a, **kw: "airo publish none")
    p.link(release(runtime, 'old'), runtime.current)
    (runtime.root / 'jobs-enabled').touch()
    switched_on = datetime(2030, 11, 7, 18, 0, tzinfo=timezone.utc).timestamp()
    p.os.utime(runtime.root / 'jobs-enabled', (switched_on, switched_on))
    p.os.utime(runtime.current, (switched_on, switched_on), follow_symlinks=False)
    sent = alerts(runtime, monkeypatch)
    jobs = [{'id': 'airo', 'kind': 'forecast', 'daily_utc': '12:00'},
            {'id': 'round', 'kind': 'forecastbench', 'at': '2030-11-08T00:05:00Z', 'due': '2030-11-08'},
            {'id': 'old-round', 'kind': 'forecastbench', 'at': '2030-11-01T00:05:00Z', 'due': '2030-11-01'}]
    # The round ran all day (its receipt exists); the daily job's minute passed meanwhile.
    p.write_json(runtime.root / 'runs/round-20301108T0005.json', {'key': 'round-20301108T0005', 'job': 'round', 'status': 'succeeded'})
    now = datetime(2030, 11, 8, 23, 4, 20, tzinfo=timezone.utc)
    runtime.report_unrun(jobs, now)
    assert len(sent) == 1 and sent[0][0] == 'airo' and 'never started' in sent[0][2]   # not 11-07's (before switch-on), not the old round's
    assert json.loads((runtime.root / 'runs/airo-20301108.json').read_text())['status'] == 'missed'
    runtime.report_unrun(jobs, now)
    assert len(sent) == 1
    assert not runtime.execute_job('airo-20301108', jobs[0])
    # A job due this very minute is not missed: it is about to start.
    runtime.report_unrun(jobs, datetime(2030, 11, 9, 12, 0, 30, tzinfo=timezone.utc))
    assert len(sent) == 1
    # A receipt still `running` while nothing holds the lock is a job that died.
    receipt = runtime.root / 'runs/airo-20301109.json'
    p.write_json(receipt, {'key': 'airo-20301109', 'job': 'airo', 'status': 'running'})
    stamp = datetime(2030, 11, 9, 12, 0, tzinfo=timezone.utc).timestamp()
    p.os.utime(receipt, (stamp, stamp))
    runtime.report_unrun(jobs, datetime(2030, 11, 9, 12, 30, tzinfo=timezone.utc))
    assert len(sent) == 2 and 'was running when the scheduler stopped' in sent[1][2]
    assert json.loads(receipt.read_text())['status'] == 'interrupted'


def test_deployment_refuses_a_release_with_no_alert_channel(runtime, monkeypatch):
    published_release(runtime)
    fake_install(runtime, monkeypatch)
    install = p.run
    checked = []
    def command(argv, **kw):
        if [str(a) for a in argv[1:]] == ['-m', 'fri_forecaster.alert', 'check']:
            checked.append(1)
            raise subprocess.CalledProcessError(1, 'alert check')
        return install(argv, **kw)
    monkeypatch.setattr(p, 'run', command)
    before = runtime.current.resolve()
    with pytest.raises(subprocess.CalledProcessError):
        runtime.deploy('a' * 40)
    assert checked and runtime.current.resolve() == before


def test_a_candidate_that_can_build_releases_builds_itself(runtime, monkeypatch):
    """The live release clones and checks out; the candidate's own script does the rest."""
    published_release(runtime)
    fake_install(runtime, monkeypatch)
    runtime.config_path = '/private/runtime.json'
    install, handed = p.run, []
    def command(argv, **kw):
        install(argv, **kw)
        if argv[:2] == ['git', 'clone']:
            (Path(argv[-1]) / 'code').mkdir()
            (Path(argv[-1]) / 'code/production.py').write_text('# the candidate')
        if 'build-release' in argv:
            handed.append([str(a) for a in argv])
    monkeypatch.setattr(p, 'run', command)
    monkeypatch.setattr(p, 'output', lambda argv, **kw: 'usage: {deploy,build-release}' if '--help' in argv else 'dependencies')
    monkeypatch.setattr(runtime, 'build_release', lambda *a, **kw: pytest.fail('the live release built the candidate'))
    runtime.deploy('a' * 40, keep_publication=True)
    [argv] = handed
    name = argv[argv.index('--release') + 1]
    assert argv[1] == str(runtime.root / 'releases' / name / 'code/code/production.py')
    assert argv[2:4] == ['--config', '/private/runtime.json'] and argv[-3:] == ['--commit', 'a' * 40, '--keep-publication']


def test_a_candidate_without_a_builder_is_built_by_the_live_release(runtime, monkeypatch):
    old = published_release(runtime)
    fake_install(runtime, monkeypatch)
    runtime.config_path = '/private/runtime.json'
    install = p.run
    def command(argv, **kw):
        install(argv, **kw)
        if argv[:2] == ['git', 'clone']:
            (Path(argv[-1]) / 'code').mkdir()
            (Path(argv[-1]) / 'code/production.py').write_text('# an older commit')
    monkeypatch.setattr(p, 'run', command)
    monkeypatch.setattr(p, 'output', lambda argv, **kw: 'usage: {deploy,rollback}' if '--help' in argv else 'dependencies')
    runtime.deploy('a' * 40)
    assert runtime.current.resolve() != old and json.loads((runtime.current / 'release.json').read_text())['commit'] == 'a' * 40


def test_a_failed_handover_marks_the_candidate_and_keeps_the_live_release(runtime, monkeypatch):
    old = published_release(runtime)
    fake_install(runtime, monkeypatch)
    runtime.config_path = '/private/runtime.json'
    install = p.run
    def command(argv, **kw):
        if 'build-release' in argv:
            raise subprocess.CalledProcessError(1, 'build-release')
        install(argv, **kw)
        if argv[:2] == ['git', 'clone']:
            (Path(argv[-1]) / 'code').mkdir()
            (Path(argv[-1]) / 'code/production.py').write_text('# the candidate')
    monkeypatch.setattr(p, 'run', command)
    monkeypatch.setattr(p, 'output', lambda argv, **kw: 'usage: {deploy,build-release}' if '--help' in argv else 'dependencies')
    with pytest.raises(subprocess.CalledProcessError):
        runtime.deploy('a' * 40)
    assert runtime.current.resolve() == old
    assert [f.parent.name for f in (runtime.root / 'releases').glob('*/failed.json')]


def test_forecast_with_nothing_due_skips_before_storage_or_runner(runtime, monkeypatch):
    p.link(release(runtime, 'old'), runtime.current)
    sent = alerts(runtime, monkeypatch)
    monkeypatch.setattr(p, 'output', lambda *a, **kw: '')
    monkeypatch.setattr(runtime, 'require_space', lambda **kw: pytest.fail('off-day must not check forecast storage'))
    monkeypatch.setattr(p, 'run', lambda *a, **kw: pytest.fail('off-day must not launch runner'))
    monkeypatch.setattr(runtime, 'save_generated_data', lambda *a: pytest.fail('off-day must not copy data'))
    job = {'id': 'airo', 'kind': 'forecast'}
    assert runtime.execute_job('off-day', job)
    record = json.loads((runtime.root / 'runs/off-day.json').read_text())
    assert record['status'] == 'skipped'
    assert record['reason'] == 'No forecast conditions due'
    assert record['finished']
    assert not (runtime.root / 'sites/job-off-day').exists()
    assert not runtime.execute_job('off-day', job)
    assert sent == []


def test_unreadable_forecast_schedule_records_preflight_failure(runtime, monkeypatch):
    p.link(release(runtime, 'old'), runtime.current)
    sent = alerts(runtime, monkeypatch)
    def fail(*a, **kw):
        raise subprocess.CalledProcessError(1, 'experiments due')
    monkeypatch.setattr(p, 'output', fail)
    monkeypatch.setattr(runtime, 'require_space', lambda **kw: pytest.fail('schedule must be checked first'))
    monkeypatch.setattr(p, 'run', lambda *a, **kw: pytest.fail('must not launch runner'))
    with pytest.raises(subprocess.CalledProcessError):
        runtime.execute_job('bad-schedule', {'id': 'airo', 'kind': 'forecast'})
    record = json.loads((runtime.root / 'runs/bad-schedule.json').read_text())
    assert record['status'] == 'failed' and record['stage'] == 'preflight FAILED'
    assert len(sent) == 1 and sent[0][1] == 'preflight FAILED'


def test_scheduled_forecast_does_not_reserve_deployment_copies(runtime, monkeypatch):
    old = release(runtime, '20301108T000000-' + 'a' * 12)
    p.link(old, runtime.current)
    # Installed code and historical state are reused, not copied by a job.
    (old / 'code/large').write_bytes(b'x' * 4096)
    runtime.state.mkdir()
    (runtime.state / 'history').write_bytes(b'x' * 4096)
    (old / 'site').mkdir()
    (old / 'site/index.html').write_bytes(b'x' * 128)
    monkeypatch.setattr(runtime, 'storage_status', lambda: {
        'free_bytes': 2 * 1024**3 + 512, 'min_free_bytes': 0, 'inode_used_percent': 1})
    runtime.require_space(publish_data=True, job_kind='forecast')
    with pytest.raises(RuntimeError, match='Insufficient deployment storage'):
        runtime.require_space(publish_data=True)
    monkeypatch.setattr(runtime, 'storage_status', lambda: {
        'free_bytes': 2 * 1024**3 + 128, 'min_free_bytes': 0, 'inode_used_percent': 1})
    with pytest.raises(RuntimeError, match='Insufficient job storage'):
        runtime.require_space(publish_data=True, job_kind='forecast')


def test_due_forecast_prunes_before_storage_preflight(runtime, monkeypatch):
    p.link(release(runtime, 'old'), runtime.current)
    monkeypatch.setattr(p, 'output', lambda *a, **kw: 'airo aside shadow')
    order = []
    monkeypatch.setattr(runtime, 'prune_locked', lambda: order.append('prune'))
    monkeypatch.setattr(runtime, 'require_space', lambda **kw: order.append(('storage', kw)))
    monkeypatch.setattr(p, 'run', lambda *a, **kw: order.append('run'))
    runtime.execute_job('due', {'id': 'airo', 'kind': 'forecast'})
    assert order == ['prune', ('storage', {'publish_data': False, 'job_kind': 'forecast'}), 'run']


@pytest.mark.parametrize('schedule_fails', [False, True])
def test_missed_offday_checks_cadence_and_records_outcome_once(runtime, monkeypatch, schedule_fails):
    p.link(release(runtime, 'old'), runtime.current)
    stamp = datetime(2026, 11, 16, 11, 0, tzinfo=timezone.utc).timestamp()
    (runtime.root / 'jobs-enabled').touch()
    p.os.utime(runtime.root / 'jobs-enabled', (stamp, stamp))
    p.os.utime(runtime.current, (stamp, stamp), follow_symlinks=False)
    sent = alerts(runtime, monkeypatch)
    def schedule(argv, **kw):
        assert argv[-2:] == ['--date', '2026-11-16']
        if schedule_fails:
            raise subprocess.CalledProcessError(1, 'experiments due')
        return ''
    monkeypatch.setattr(p, 'output', schedule)
    job = {'id': 'airo', 'kind': 'forecast', 'daily_utc': '12:00'}
    now = datetime(2026, 11, 16, 12, 1, tzinfo=timezone.utc)
    runtime.report_unrun([job], now)
    runtime.report_unrun([job], now)
    record = json.loads((runtime.root / 'runs/airo-20261116.json').read_text())
    assert record['status'] == ('failed' if schedule_fails else 'skipped')
    assert len(sent) == int(schedule_fails)
    if sent:
        assert sent[0][1] == 'preflight FAILED'


@pytest.mark.parametrize("name,block,download", [("eeai", "EEAI", "eeai-data.zip"), ("rsi", "SURVEY", None)])
def test_survey_frontend_retains_its_publication(tmp_path, name, block, download):
    runtime = p.Runtime({"dashboard": name, "root": str(tmp_path), "path": "/usr/bin", "socket": str(tmp_path / "site.sock")})
    old = release(runtime, "old")
    site = old / "site"
    site.mkdir()
    (site / "index.html").write_bytes(dashboard("old UI", 21, block))
    if download:
        (site / download).write_bytes(b"old download")
    p.write_json(site / "release.json", {"dashboard": name, "commit": "a"*40})
    p.link(old, runtime.current)
    repo = Path(__file__).resolve().parents[3]
    new = tmp_path / "candidate"
    snapshot = runtime.publish_frontend(repo, new)
    assert p.data_blocks((new / "index.html").read_bytes()) == p.data_blocks((site / "index.html").read_bytes())
    assert b"old UI" not in (new / "index.html").read_bytes()
    assert snapshot["sha256"] == p.data_snapshot(site, runtime.dashboard.downloads)["sha256"]
    if download:
        assert (new / download).read_bytes() == b"old download"


def test_survey_job_failure_does_not_publish_partial_models(tmp_path, monkeypatch, runtime):
    runtime = p.Runtime({"dashboard": "eeai", "root": str(tmp_path), "path": "/usr/bin", "socket": str(tmp_path / "site.sock")})
    active = release(runtime, "active")
    p.link(active, runtime.current)
    calls = []

    def fail_after_one_model(argv, **kwargs):
        calls.append(argv)
        (Path(argv[-1]) / "partial.jsonl").write_text("partial row")
        raise RuntimeError("model failure")

    monkeypatch.setattr(p, "run", fail_after_one_model)
    monkeypatch.setattr(runtime, "alert", lambda *args, **kwargs: None)
    with pytest.raises(RuntimeError, match="model failure"):
        runtime.execute_job("attempt-one", {"id": "eeai", "kind": "forecast"})
    assert not (runtime.state / "results").exists()
    assert (runtime.state / "attempts/attempt-one/partial.jsonl").is_file()
    assert not runtime.execute_job("attempt-one", {"id": "eeai", "kind": "forecast"})
    assert len(calls) == 1


def test_survey_forecast_switches_site_and_keeps_results(tmp_path, monkeypatch, runtime):
    runtime = p.Runtime({"dashboard": "rsi", "root": str(tmp_path), "path": "/usr/bin", "socket": str(tmp_path / "site.sock")})
    active = release(runtime, "active")
    p.link(active, runtime.current)
    def scripted(argv, **kw):
        if "rsi_dashboard.run" in argv:
            (Path(argv[-1]) / "dated-run").mkdir()
        else:
            results = Path(argv[argv.index("--results") + 1])
            assert (results / "dated-run").is_dir()
            (Path(argv[-1]) / "index.html").write_bytes(dashboard("survey", 42, "SURVEY"))
    monkeypatch.setattr(p, "run", scripted)
    assert runtime.execute_job("rsi-example", {"id": "rsi", "kind": "forecast"})
    assert (active / "site").resolve() == runtime.root / "sites/job-rsi-example"
    expected = p.data_snapshot(active / "site", ())
    assert json.loads((active / "release.json").read_text())["data_snapshot"]["sha256"] == expected["sha256"]


def test_runtime_dispatches_only_its_schedule(tmp_path):
    config = {"root": str(tmp_path/"rsi"), "dashboard": "rsi", "socket": "rsi.sock", "path": "/usr/bin"}
    rsi = p.Runtime(config)
    jobs = [{"id": "airo", "kind": "forecast", "daily_utc": "12:00"},
            {"id": "weekly-rsi", "dashboard": "rsi", "kind": "forecast", "at": "2030-01-01T12:00Z"}]
    p.write_json(tmp_path / p.JOBS, jobs)
    assert rsi.jobs(tmp_path) == jobs[1:]
    with pytest.raises(ValueError):
        p.validate_jobs([dict(jobs[1], kind="news-poll")])


def test_weekly_jobs_use_identical_live_and_missed_keys():
    job = {"id": "survey", "dashboard": "rsi", "kind": "forecast", "weekly_utc": "Fri 09:30"}
    at = datetime(2026, 11, 20, 9, 30, tzinfo=timezone.utc)
    key = "survey-20261120"
    assert list(p.due_jobs([job], at.replace(second=55))) == [(key, job)]
    assert not list(p.due_jobs([job], at.replace(day=21)))
    assert list(p.scheduled_between([job], at.replace(day=19), at.replace(day=21))) == [(key, job, at)]
    for bad in [dict(job, daily_utc="09:30"), dict(job, weekly_utc="Fri 25:00")]:
        with pytest.raises(ValueError):
            p.validate_jobs([bad])


@pytest.mark.parametrize("name", ["rsi", "eeai"])
def test_remote_publish_failure_pages_separately_from_survey_failure(runtime, monkeypatch, name):
    runtime.name = name
    runtime.dashboard = p.DASHBOARDS[name]
    p.link(release(runtime, 'old'), runtime.current)
    sent = alerts(runtime, monkeypatch)
    job = {'id': name + '-weekly', 'kind': 'forecast'}
    def forecast(argv, **kw):
        if 'stdout' in kw:
            raise RuntimeError('model unavailable')
    monkeypatch.setattr(p, 'run', forecast)
    with pytest.raises(RuntimeError, match='model unavailable'):
        runtime.execute_job('attempt', job)
    assert sent[-1][1] == 'run FAILED'
    assert 'failed to produce forecast' in sent[-1][2]
    def finish(argv, **kw):
        out = runtime.state / 'attempts/completed'
        (out / 'result').write_text('completed')
    monkeypatch.setattr(p, 'run', finish)
    monkeypatch.setattr(runtime, 'build_data', lambda code, site, env, **kw: (site / 'index.html').write_text('site'))
    monkeypatch.setattr(runtime, 'verify_site', lambda site: None)
    monkeypatch.setattr(p, 'data_snapshot', lambda *args: {'sha256': '0'*64})
    def disconnected(site):
        assert (site / 'release.json').exists()
        raise OSError('edge offline')
    monkeypatch.setattr(runtime, 'publish_public', disconnected)
    with pytest.raises(OSError, match='edge offline'):
        runtime.execute_job('completed', job)
    assert sent[-1][1] == 'publish FAILED'
    assert 'failed to publish dashboard' in sent[-1][2]
    assert (runtime.state / 'results/result').read_text() == 'completed'
