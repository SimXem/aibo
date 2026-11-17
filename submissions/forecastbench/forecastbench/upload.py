"""Upload a validated round; retry uploads without rerunning forecasts.

    python -m forecastbench.upload --root /private/rounds/YYYY-MM-DD

Configuration comes from the environment (the scripts source private round.env):
FB_UPLOAD_PREFIX is the gs:// bucket/team/binary prefix, without a round date;
FB_UPLOAD_ACCOUNT is the dedicated service-account email. Settings may instead
live in ~/.config/forecastbench-uploader/settings.json. A service-account key in
that directory authenticates without gcloud or a personal login.
"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

import forecastbench as fb
from forecastbench import names
from fri_forecaster import alert


def config_dir():
    return Path.home() / '.config/forecastbench-uploader'


def settings():
    path = config_dir() / 'settings.json'
    found = json.loads(path.read_text()) if path.exists() else {}
    return (os.environ.get('FB_UPLOAD_PREFIX', found.get('prefix', '')),
            os.environ.get('FB_UPLOAD_ACCOUNT', found.get('account', '')))


def utcnow():
    return datetime.now(timezone.utc)


def check_window(due, now=None):
    start = datetime.strptime(due, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    if not start <= (now or utcnow()) < start + timedelta(days=1):
        raise ValueError(f'Upload refused: submissions for {due} must be uploaded on that UTC date')


def destination(prefix, due):
    parsed = urllib.parse.urlsplit(prefix)
    if (parsed.scheme != 'gs' or not parsed.netloc or not parsed.path.strip('/')
            or parsed.query or parsed.fragment or parsed.username or parsed.port):
        raise ValueError('Set FB_UPLOAD_PREFIX to gs://bucket/team-prefix/binary (without the round date)')
    if any(part in ('.', '..', '') for part in parsed.path.strip('/').split('/')):
        raise ValueError('Invalid upload prefix')
    return parsed.netloc, parsed.path.strip('/') + '/' + due


def submissions(root, reg, org, public_org):
    """Validate the exact submitted conditions, not a glob of everything in a round."""
    qbytes = (root / 'question_set.json').read_bytes()
    qset = json.loads(qbytes)
    due = qset['forecast_due_date']
    if root.name != due or qset['question_set'] != f'{due}-llm.json':
        raise ValueError('Upload refused: root must be the dated real round, not a rehearsal')
    conditions = names.submitted(reg)
    if not conditions:
        raise ValueError('No submitted conditions in the registry')
    prepared = []
    for n, condition in enumerate(conditions, 1):
        name = names.current(reg, condition)
        organization = public_org if condition in names.public_of(reg) else org
        if not organization:
            raise ValueError('Configure FB_ORG and, for public submissions, FB_PUBLIC_ORG')
        path = root / f'{due}.{fb.file_org(organization)}.{n}.json'
        if path.parent != root or path.is_symlink():
            raise ValueError('Invalid submission filename')
        data = path.read_bytes()
        fs = json.loads(data)
        provenance = json.loads(Path(str(path) + '.provenance.json').read_text())
        if (provenance.get('submission_sha256') != hashlib.sha256(data).hexdigest()
                or provenance.get('question_set_sha256') != hashlib.sha256(qbytes).hexdigest()):
            raise ValueError(f'{path.name}: missing or stale build provenance; rebuild this set')
        if (fs['organization'] != organization or fs['model'] != name
                or fs['model_organization'] != organization
                or provenance['name'] != name or provenance['organization'] != organization):
            raise ValueError(f'{path.name}: build does not match the registered submission')
        expected_members = {
            Path(fb.member_dir(str(root), model, thinking, mode)).name
            for model, thinking, mode in (
                (spec.split('@')[0], spec.split('@')[1].split(',')[0], spec.split(',')[1])
                for spec in names.member_specs(reg, condition))}
        if set(provenance['members']) != expected_members:
            raise ValueError(f'{path.name}: members do not match the registered submission')
        covs = provenance['member_coverage']
        if set(covs) != expected_members or any(
                set(cov) != {'market', 'dataset'} or fb.short_kinds(cov) for cov in covs.values()):
            raise ValueError(f'{path.name}: a member is below 95% coverage')
        errors = fb.validate(fs, qset)
        if errors:
            raise ValueError(f'{path.name}: invalid forecasts: {errors}')
        results = {}
        for row in fs['forecasts']:
            key = (row['source'], str(row['id']))
            result = results.setdefault(key, {'wanted': [], 'probabilities': {}})
            d = row['resolution_date'] or 'final'
            result['probabilities'][d] = row['forecast']
        for q in fb.questions_of(qset):
            key = (q['source'], str(q['id']))
            if key in results:
                results[key]['wanted'] = fb.dates_of(q)
        if fb.short_kinds(fb.coverage(qset, results)):
            raise ValueError(f'{path.name}: set is below 95% coverage')
        prepared.append((path.name, data))
    return due, prepared


class Storage:
    def __init__(self, account):
        if not account or not account.endswith('.iam.gserviceaccount.com'):
            raise ValueError('Set FB_UPLOAD_ACCOUNT to the dedicated service-account email')
        key_path = Path(os.environ.get('FB_UPLOAD_KEY_FILE', str(config_dir() / 'key.json')))
        if key_path.exists():
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request
            credentials = service_account.Credentials.from_service_account_file(
                str(key_path), scopes=['https://www.googleapis.com/auth/devstorage.read_write'])
            if credentials.service_account_email != account:
                raise ValueError('Uploader key does not belong to FB_UPLOAD_ACCOUNT')
            credentials.refresh(Request())
            self.token = credentials.token
            return
        env = dict(os.environ, CLOUDSDK_CORE_DISABLE_PROMPTS='1')
        result = subprocess.run(['gcloud', 'auth', 'print-access-token', account, '--quiet'],
                                env=env, capture_output=True, text=True, timeout=90)
        if result.returncode or not result.stdout.strip():
            raise RuntimeError('Service-account authentication failed; check the runner credentials and gcloud configuration')
        self.token = result.stdout.strip()

    def request(self, bucket, name, data=None):
        if data is None:
            url = f'https://storage.googleapis.com/storage/v1/b/{urllib.parse.quote(bucket, safe="")}/o/{urllib.parse.quote(name, safe="")}'
        else:
            query = urllib.parse.urlencode({'uploadType': 'media', 'name': name, 'ifGenerationMatch': '0'})
            url = f'https://storage.googleapis.com/upload/storage/v1/b/{urllib.parse.quote(bucket, safe="")}/o?{query}'
        req = urllib.request.Request(url, data=data, headers={
            'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.load(response)

    def delete_probe(self, bucket, name, generation):
        query = urllib.parse.urlencode({'ifGenerationMatch': generation})
        url = f'https://storage.googleapis.com/storage/v1/b/{urllib.parse.quote(bucket, safe="")}/o/{urllib.parse.quote(name, safe="")}?{query}'
        req = urllib.request.Request(url, method='DELETE', headers={'Authorization': 'Bearer ' + self.token})
        with urllib.request.urlopen(req, timeout=120) as response:
            response.read()


def confirmed(meta, bucket, name, data, due):
    md5 = base64.b64encode(hashlib.md5(data).digest()).decode()
    if (meta.get('bucket') != bucket or meta.get('name') != name
            or meta.get('md5Hash') != md5 or meta.get('size') != str(len(data))
            or not meta.get('generation')):
        raise ValueError(f'{name}: remote upload could not be verified')
    check_window(due, datetime.fromisoformat(meta['timeCreated'].replace('Z', '+00:00')))
    return {k: meta[k] for k in ('bucket', 'name', 'md5Hash', 'size', 'generation', 'timeCreated')}


def upload(root, reg, org, public_org, prefix, account, storage_factory=Storage):
    root = Path(root).resolve()
    # One upload/retry at a time. Validation finishes before the first network write.
    with (root / '.upload.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        due, files = submissions(root, reg, org, public_org)
        check_window(due)
        bucket, prefix = destination(prefix, due)
        storage = storage_factory(account)
        receipt_path = root / 'upload-receipt.json'
        receipt = {'due': due, 'account': account, 'objects': [], 'status': 'uploading'}
        for filename, data in files:
            check_window(due)  # A long or retried round cannot cross into the next day unnoticed.
            name = prefix + '/' + filename
            try:
                meta = storage.request(bucket, name, data)
            except urllib.error.HTTPError as error:
                if error.code != 412:
                    raise RuntimeError(f'Cloud Storage upload failed (HTTP {error.code}); forecasts retained') from error
                # Already exists, perhaps the previous request succeeded before a network
                # failure. Read and compare; never silently skip or replace different bytes.
                meta = storage.request(bucket, name)
            receipt['objects'].append(confirmed(meta, bucket, name, data, due))
            receipt['status'] = 'uploaded' if len(receipt['objects']) == len(files) else 'uploading'
            tmp = receipt_path.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(receipt, indent=2) + '\n')
            tmp.replace(receipt_path)
            print(f'Confirmed gs://{bucket}/{name}')
        return receipt


def check_access(prefix, account, due):
    """An explicit setup test, never a forecast: write/read a unique .txt probe."""
    datetime.strptime(due, '%Y-%m-%d')
    bucket, prefix = destination(prefix, due)
    name = prefix + '/_upload-access-test-' + uuid.uuid4().hex + '.txt'
    data = b'ForecastBench uploader access test; not a forecast submission.\n'
    storage = Storage(account)
    meta = storage.request(bucket, name, data)
    try:
        confirmed(meta, bucket, name, data, utcnow().strftime('%Y-%m-%d'))
        actual = storage.request(bucket, name)
        if actual['generation'] != meta['generation']:
            raise ValueError('Probe generation changed')
        confirmed(actual, bucket, name, data, utcnow().strftime('%Y-%m-%d'))
    finally:
        try:
            storage.delete_probe(bucket, name, meta['generation'])
        except urllib.error.HTTPError as error:
            if error.code != 403:
                raise
            print(f'Probe retained (no delete permission): gs://{bucket}/{name}')
    print(f'Service-account write and metadata read verified for gs://{bucket}/{prefix}/')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--root')
    action.add_argument('--check-access', metavar='YYYY-MM-DD', help='explicit .txt probe; no forecasts or alerts')
    args = parser.parse_args(argv)
    if args.check_access:
        try:
            check_access(*settings(), args.check_access)
        except Exception as error:
            print(f'Upload access check failed ({type(error).__name__}): {error}', file=sys.stderr)
            return 1
        return 0
    try:
        prefix, account = settings()
        receipt = upload(args.root, names.load(), os.environ.get('FB_ORG'), os.environ.get('FB_PUBLIC_ORG'),
                         prefix, account)
    except (Exception, SystemExit) as error:
        message = (f'{type(error).__name__}: {error}. Forecasts retained in {args.root}. '
                   'Fix access/configuration, source the private round.env with variables exported, '
                   f'and retry python -m forecastbench.upload --root {args.root}; do not rerun forecasting.')
        print('UPLOAD FAILED: ' + message, file=sys.stderr)
        alert.send('forecastbench', 'upload FAILED', message, severity='page')
        return 1
    alert.send('forecastbench', 'submissions uploaded',
               f"{receipt['due']}: {len(receipt['objects'])} uploads confirmed.", severity='notice')
    return 0


if __name__ == '__main__':
    sys.exit(main())
