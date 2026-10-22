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
def runtime(tmp_path):
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
