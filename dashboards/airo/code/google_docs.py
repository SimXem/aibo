#!/usr/bin/env python3
"""Local Google Docs OAuth and revision-checked API access; no external deps.

Secrets come from .env. Tokens and snapshots belong in ignored .local/google-docs/.
Run `python3 code/google_docs.py auth`, then `fetch DOCUMENT_URL --out PATH`.
The apply command takes a reviewed JSON batch with requiredRevisionId.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.local/google-docs'
TOKEN = PRIVATE / 'token.json'
SCOPE = 'https://www.googleapis.com/auth/documents'
AUTH_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'


def private_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError('Refusing to write through a symlink')
    temporary = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    temporary.replace(path)


def client() -> tuple[str, str]:
    # Parse only credential assignments; never source arbitrary shell code.
    values = {}
    for line in (ROOT / '.env').read_text().splitlines():
        key, separator, value = line.strip().removeprefix('export ').partition('=')
        if separator:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key.strip()] = value
    # Accept the spelling in an existing .env without rewriting it.
    identifier = values.get('GOOGLE_CLIENT_ID') or values.get('GOOGLE_CLLIENT_ID')
    secret = values.get('GOOGLE_CLIENT_SECRET')
    if not identifier or not secret:
        raise RuntimeError('Google client ID and secret are missing from .env')
    return identifier, secret


def request_json(url: str, *, payload=None, bearer=None, form=False) -> dict:
    headers = {}
    data = None
    if payload is not None:
        data = (urllib.parse.urlencode(payload) if form else json.dumps(payload)).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Do not echo request headers, callback URLs, codes, or tokens.
        try:
            body = json.load(exc)
            error = body.get('error', 'request_failed')
            if isinstance(error, dict):
                error = error.get('message', error.get('status', 'request_failed'))
        except (ValueError, TypeError):
            error = 'request_failed'
        raise RuntimeError(f'Google API HTTP {exc.code}: {error}') from None


def authorize(port: int) -> None:
    identifier, secret = client()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    state = secrets.token_urlsafe(32)
    result = {}

    class Callback(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Callback query strings contain credentials.

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if parsed.path != '/' or not secrets.compare_digest(query.get('state', [''])[0], state):
                self.send_error(400, 'Invalid OAuth callback')
                return
            if 'error' in query:
                result['error'] = query['error'][0]
            elif 'code' in query:
                result['code'] = query['code'][0]
            else:
                self.send_error(400, 'Missing authorization code')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(b'Google authorization received. You can return to Codex.')

    with http.server.HTTPServer(('127.0.0.1', port), Callback) as server:
        redirect = f'http://localhost:{server.server_port}/'
        url = AUTH_ENDPOINT + '?' + urllib.parse.urlencode({
            'client_id': identifier, 'redirect_uri': redirect, 'response_type': 'code',
            'scope': SCOPE, 'access_type': 'offline', 'prompt': 'consent',
            'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
        })
        if not webbrowser.open(url):
            raise RuntimeError('Could not open the system browser')
        print(f'Google sign-in opened. Waiting for browser authorization at {redirect}', flush=True)
        server.timeout = 1
        deadline = time.monotonic() + 900
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if 'error' in result:
        raise RuntimeError('Google authorization declined: ' + result['error'])
    if 'code' not in result:
        raise RuntimeError('Authorization timed out; rerun auth to try again')
    token = request_json(TOKEN_ENDPOINT, payload={
        'client_id': identifier, 'client_secret': secret, 'code': result['code'],
        'redirect_uri': redirect, 'grant_type': 'authorization_code', 'code_verifier': verifier,
    }, form=True)
    if SCOPE not in token.get('scope', '').split():
        raise RuntimeError('Google Docs editing scope was not granted')
    token['expires_at'] = time.time() + token.get('expires_in', 3600)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    PRIVATE.chmod(0o700)
    private_write(TOKEN, token)
    print('Google Docs authorization saved in ignored local storage (permissions 0600).')


def access_token() -> str:
    if not TOKEN.exists():
        raise RuntimeError('Run the auth command first')
    token = json.loads(TOKEN.read_text())
    if token.get('expires_at', 0) < time.time() + 60:
        if not token.get('refresh_token'):
            raise RuntimeError('Authorization has expired; run auth again')
        identifier, secret = client()
        update = request_json(TOKEN_ENDPOINT, payload={
            'client_id': identifier, 'client_secret': secret,
            'refresh_token': token['refresh_token'], 'grant_type': 'refresh_token',
        }, form=True)
        token.update(update)
        token['expires_at'] = time.time() + update.get('expires_in', 3600)
        private_write(TOKEN, token)
    return token['access_token']


def document_id(value: str) -> str:
    match = re.search(r'/document/d/([\w-]+)', value)
    value = match.group(1) if match else value
    if not re.fullmatch(r'[\w-]+', value):
        raise ValueError('Expected a Google document ID or URL')
    return value


def fetch(identifier: str) -> dict:
    query = urllib.parse.urlencode({'includeTabsContent': 'true', 'suggestionsViewMode': 'SUGGESTIONS_INLINE'})
    return request_json(f'https://docs.googleapis.com/v1/documents/{document_id(identifier)}?{query}', bearer=access_token())


def apply(identifier: str, batch: dict) -> dict:
    revision = batch.get('writeControl', {}).get('requiredRevisionId')
    if not revision or batch.get('writeControl', {}).get('targetRevisionId'):
        raise ValueError('A reviewed batch must specify requiredRevisionId only')
    if not batch.get('requests'):
        raise ValueError('Empty edit batch')
    if fetch(identifier).get('revisionId') != revision:
        raise RuntimeError('Document changed since review; fetch and reconcile before editing')
    # Google rechecks this revision atomically at the write, closing the fetch/write race.
    return request_json(f'https://docs.googleapis.com/v1/documents/{document_id(identifier)}:batchUpdate',
                        payload=batch, bearer=access_token())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    auth = commands.add_parser('auth')
    auth.add_argument('--port', type=int, default=8765)
    get = commands.add_parser('fetch')
    get.add_argument('document')
    get.add_argument('--out', type=Path, required=True)
    update = commands.add_parser('apply')
    update.add_argument('document')
    update.add_argument('--batch', type=Path, required=True)
    update.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'auth':
            authorize(args.port)
        elif args.command == 'fetch':
            doc = fetch(args.document)
            private_write(args.out, doc)
            print(json.dumps({'title': doc.get('title'), 'documentId': doc.get('documentId'),
                              'revisionId': doc.get('revisionId'), 'saved': str(args.out)}))
        else:
            response = apply(args.document, json.loads(args.batch.read_text()))
            private_write(args.out, response)
            print(f'Applied {len(response.get("replies", []))} requests; response saved to {args.out}')
    except (RuntimeError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
