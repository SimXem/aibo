"""Submission validation, non-overwriting retries and alerts; no cloud calls."""
import base64
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import forecastbench as fb
from forecastbench import names, upload


DUE = '2026-11-22'
NOW = datetime(2026, 11, 22, 8, tzinfo=timezone.utc)
ACCOUNT = 'uploader@example-project.iam.gserviceaccount.com'
PREFIX = 'gs://example-bucket/team/binary'
QSET = {'forecast_due_date': DUE, 'question_set': DUE + '-llm.json', 'questions': [
    {'source': 'metaculus', 'id': 'm', 'resolution_dates': 'N/A'},
    {'source': 'fred', 'id': 'd', 'resolution_dates': ['2026-12-01', '2026-12-02']},
]}


class FakeStorage:
    def __init__(self, account):
        self.objects = {}
        self.writes = []
        self.fail_after_write = False

    def request(self, bucket, name, data=None):
        key = (bucket, name)
        if data is None:
            return dict(self.objects[key])
        if key in self.objects:
            raise HTTPError('fake', 412, 'already exists', {}, None)
        self.writes.append(key)
        self.objects[key] = {'bucket': bucket, 'name': name,
                             'md5Hash': base64.b64encode(hashlib.md5(data).digest()).decode(),
                             'size': str(len(data)), 'generation': '1',
                             'timeCreated': NOW.isoformat()}
        if self.fail_after_write:
            raise TimeoutError('lost upload response')
        return dict(self.objects[key])


class UploadTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / DUE
        self.root.mkdir()
        config = patch.object(upload, 'config_dir', return_value=Path(self.temp.name) / 'private')
        config.start()
        self.addCleanup(config.stop)
        (self.root / 'question_set.json').write_text(json.dumps(QSET))
        self.reg = names.load(Path(__file__).parents[1] / 'examples/names.example.json')
        self.reg['conditions'] = {'solo': self.reg['conditions']['solo']}
        entry = self.reg['names']['solo-oak']
        entry['harness']['pi'] = fb.harness.PINNED_PI_VERSION
        entry['harness']['prompt_version'] = names.prompt_version(entry)
        entry['fingerprint'] = names.fingerprint(entry)
        specs = names.member_specs(self.reg, 'solo')
        member = entry['members'][0]
        self.member_path = Path(fb.member_dir(str(self.root), member['pi_model'],
                                            member['options']['thinking'], 'research'))
        self.member_path.mkdir(parents=True)
        (self.member_path / 'manifest.json').write_text('{}')
        results = [{'id': q['id'], 'source': q['source'], 'wanted': fb.dates_of(q),
                    'probabilities': {d: 0.4 for d in fb.dates_of(q)}} for q in QSET['questions']]
        (self.member_path / 'results.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in results))
        self.build_args = ['build', '--root', str(self.root), '--member', specs[0],
                           '--org', 'Example Team', '--name', 'solo-oak', '--set-number', '1']
        self.build()
        self.path = self.root / f'{DUE}.example-team.1.json'
        self.storage = FakeStorage(ACCOUNT)
        self.clock = patch.object(upload, 'utcnow', return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def build(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return fb.main(self.build_args)

    def run_upload(self):
        return upload.upload(self.root, self.reg, 'Example Team', None, PREFIX, ACCOUNT,
                             storage_factory=lambda account: self.storage)

    def rewrite(self, fs):
        self.path.write_text(json.dumps(fs))
        prov_path = Path(str(self.path) + '.provenance.json')
        prov = json.loads(prov_path.read_text())
        prov['submission_sha256'] = hashlib.sha256(self.path.read_bytes()).hexdigest()
        prov_path.write_text(json.dumps(prov))

    def test_uploads_only_registered_sets_and_records_verified_receipt(self):
        (self.root / 'not-a-submission.json').write_text('{}')
        result = self.run_upload()
        self.assertEqual(result['status'], 'uploaded')
        self.assertEqual(len(self.storage.writes), 1)
        self.assertEqual(result, json.loads((self.root / 'upload-receipt.json').read_text()))
        self.assertEqual(result['objects'][0]['name'], f'team/binary/{DUE}/{self.path.name}')

    def test_retry_recovers_from_lost_response_without_overwriting(self):
        self.storage.fail_after_write = True
        with self.assertRaises(TimeoutError):
            self.run_upload()
        self.storage.fail_after_write = False
        self.assertEqual(self.run_upload()['status'], 'uploaded')
        self.assertEqual(len(self.storage.writes), 1)

    def test_existing_different_remote_object_fails(self):
        self.run_upload()
        next(iter(self.storage.objects.values()))['md5Hash'] = 'different'
        with self.assertRaisesRegex(ValueError, 'could not be verified'):
            self.run_upload()
        self.assertEqual(len(self.storage.writes), 1)

    def test_changed_file_or_question_set_refuses_before_cloud_write(self):
        self.path.write_text(self.path.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'stale build provenance'):
            self.run_upload()
        self.assertFalse(self.storage.writes)
        self.build()
        (self.root / 'question_set.json').write_text(json.dumps(QSET) + ' ')
        with self.assertRaisesRegex(ValueError, 'stale build provenance'):
            self.run_upload()

    def test_incomplete_dataset_question_and_invalid_probabilities_refused(self):
        fs = json.loads(self.path.read_text())
        fs['forecasts'].pop()
        self.rewrite(fs)
        with self.assertRaisesRegex(ValueError, 'below 95%'):
            self.run_upload()
        fs['forecasts'][0]['forecast'] = float('nan')
        self.rewrite(fs)
        with self.assertRaisesRegex(ValueError, 'invalid forecasts'):
            self.run_upload()
        self.assertFalse(self.storage.writes)

    def test_complete_aggregate_with_short_member_refused(self):
        prov_path = Path(str(self.path) + '.provenance.json')
        prov = json.loads(prov_path.read_text())
        prov['member_coverage'][self.member_path.name]['dataset'] = [0, 1]
        prov_path.write_text(json.dumps(prov))
        with self.assertRaisesRegex(ValueError, 'member is below 95%'):
            self.run_upload()
        self.assertFalse(self.storage.writes)

    def test_rehearsals_and_outside_utc_date_refused(self):
        for time in (datetime(2026, 11, 21, 23, 59, tzinfo=timezone.utc),
                     datetime(2026, 11, 23, tzinfo=timezone.utc)):
            with patch.object(upload, 'utcnow', return_value=time):
                with self.assertRaisesRegex(ValueError, 'UTC date'):
                    self.run_upload()
        renamed = self.root.with_name(DUE + '-rehearsal')
        self.root.rename(renamed)
        self.root = renamed
        with self.assertRaisesRegex(ValueError, 'rehearsal'):
            self.run_upload()
        self.assertFalse(self.storage.writes)

    def test_expired_auth_pages_and_returns_failure(self):
        with patch.object(upload.names, 'load', return_value=self.reg), \
                patch.object(upload, 'upload', side_effect=RuntimeError('authentication failed')), \
                patch.object(upload.alert, 'send') as send:
            self.assertEqual(upload.main(['--root', str(self.root)]), 1)
        self.assertEqual(send.call_args.args[:2], ('forecastbench', 'upload FAILED'))
        self.assertEqual(send.call_args.kwargs['severity'], 'page')

    def test_personal_account_cannot_be_used_accidentally(self):
        with self.assertRaisesRegex(ValueError, 'dedicated service-account'):
            upload.Storage('person@example.org')

    def test_private_key_authentication_does_not_use_personal_gcloud_login(self):
        private = upload.config_dir()
        private.mkdir()
        (private / 'key.json').write_text('{}')
        credentials = unittest.mock.Mock(service_account_email=ACCOUNT, token='token')
        with patch('google.oauth2.service_account.Credentials.from_service_account_file', return_value=credentials), \
                patch('google.auth.transport.requests.Request'), patch.object(upload.subprocess, 'run') as gcloud:
            self.assertEqual(upload.Storage(ACCOUNT).token, 'token')
            credentials.refresh.assert_called_once()
            gcloud.assert_not_called()
            credentials.service_account_email = 'wrong@other.iam.gserviceaccount.com'
            with self.assertRaisesRegex(ValueError, 'does not belong'):
                upload.Storage(ACCOUNT)

    def test_transport_pins_identity_and_forbids_overwrite(self):
        token = unittest.mock.Mock(returncode=0, stdout='secret-token\n')
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{}'
        with patch.object(upload.subprocess, 'run', return_value=token) as auth, \
                patch.object(upload.urllib.request, 'urlopen', return_value=response) as request:
            client = upload.Storage(ACCOUNT)
            client.request('bucket', 'team/round/file.json', b'{}')
        self.assertEqual(auth.call_args.args[0], ['gcloud', 'auth', 'print-access-token', ACCOUNT, '--quiet'])
        req = request.call_args.args[0]
        self.assertIn('ifGenerationMatch=0', req.full_url)
        self.assertIn('name=team%2Fround%2Ffile.json', req.full_url)
        self.assertEqual(req.get_header('Authorization'), 'Bearer secret-token')
        self.assertEqual(req.data, b'{}')


class CronTest(unittest.TestCase):
    def test_upload_runs_only_after_successful_round_and_failure_propagates(self):
        source = Path(__file__).parents[1] / 'scripts/fb_cron.sh'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / 'scripts'
            scripts.mkdir()
            cron = scripts / 'fb_cron.sh'
            cron.write_text(source.read_text())
            round_script = scripts / 'fb_round.sh'
            round_script.write_text('#!/bin/bash\nexit "$FAKE_ROUND_RC"\n')
            round_script.chmod(0o700)
            fake_py = root / 'python'
            fake_py.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$FAKE_CALLS"\n'
                               'if [[ "$2" == forecastbench.upload ]]; then exit "$FAKE_UPLOAD_RC"; fi\n')
            fake_py.chmod(0o700)
            conf = root / 'round.env'
            conf.write_text(f'PY={shlex.quote(str(fake_py))}\nROUNDS_DIR={shlex.quote(str(root / "rounds"))}\n')
            calls_path = root / 'calls'
            env = dict(os.environ, FORECASTER_ROUND_ENV=str(conf), FAKE_CALLS=str(calls_path))
            for build_rc, upload_rc, expected in ((0, 0, 0), (0, 1, 1), (1, 0, 1)):
                calls_path.write_text('')
                result = subprocess.run(['bash', str(cron), DUE],
                                        env=dict(env, FAKE_ROUND_RC=str(build_rc), FAKE_UPLOAD_RC=str(upload_rc)),
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                calls = calls_path.read_text()
                self.assertEqual('forecastbench.upload' in calls, build_rc == 0)
                if build_rc:
                    self.assertIn('run FAILED', calls)


if __name__ == '__main__':
    unittest.main()
