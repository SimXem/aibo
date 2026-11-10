"""Release and scheduler failure tests; never call a provider or GitHub."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

spec = importlib.util.spec_from_file_location('production', Path(__file__).parents[1] / 'code/production.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(p.shutil, 'disk_usage', lambda _: type('Disk', (), {
        'total': 50*1024**3, 'used': 10*1024**3, 'free': 40*1024**3})())
    return p.Runtime({'root': str(tmp_path), 'path': '/usr/bin:/bin', 'socket': str(tmp_path / 'site.sock')})


def release(runtime, name):
    r = runtime.root / 'releases' / name
    (r / 'code/data').mkdir(parents=True)
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
    (r / 'code/results/runs.jsonl').write_text('bad build')
    assert raw.read_text() == 'accrued\n'
    runtime.attach_state(r / 'code')
    assert (r / 'code/results/runs.jsonl').read_text() == 'accrued\n'


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
            (code / 'deploy').mkdir(parents=True)
            (code / 'deploy/jobs.json').write_text('[]')
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
            (code / 'deploy').mkdir(parents=True)
            (code / 'deploy/jobs.json').write_text('[]')
            (code / 'index.html').write_bytes(dashboard('aligned dots', 999))
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
    code.mkdir()
    (code / 'index.html').write_bytes(dashboard('aligned dots', 999))
    snapshot = runtime.publish_frontend(code, runtime.root / 'candidate-site')
    assert snapshot['origin_commit'] is None
    assert snapshot['source_release'] == 'imported'
    (source / 'forecasts.csv').write_text('unexpected alteration')
    with pytest.raises(RuntimeError, match='changed unexpectedly'):
        runtime.publish_frontend(code, runtime.root / 'another-site')


def test_frontend_updates_static_assets_without_changing_the_previous_site(runtime):
    old = published_release(runtime)
    code = runtime.root / 'candidate-code'
    (code / 'web/img').mkdir(parents=True)
    (code / 'index.html').write_bytes(dashboard('new', 999))
    (code / 'web/img/logo.svg').write_text('<svg>new logo</svg>')
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
    assert [str(x) for x in args[0]][-2:] == [str(r / 'code/code/recent_news.py'), 'poll']
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


def test_low_disk_blocks_paid_work_before_receipt_or_provider_call(runtime, monkeypatch):
    def no_space(**kw):
        raise RuntimeError('Insufficient deployment storage')
    monkeypatch.setattr(runtime, 'require_space', no_space)
    monkeypatch.setattr(p, 'run', lambda *a, **kw: pytest.fail('must not run paid work'))
    with pytest.raises(RuntimeError, match='Insufficient'):
        runtime.execute_job('paid', {'id': 'forecast', 'kind': 'forecast'})
    assert not (runtime.root / 'runs/paid.json').exists()


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
