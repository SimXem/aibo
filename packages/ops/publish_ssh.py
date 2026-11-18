#!/usr/bin/env python3
"""Mirror a verified static publication to a web host over installation-configured SSH."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile


def receive(root, digest, verify, stream):
    """Stage immutable files and check the ingress before acknowledging the switch."""
    releases = root / 'releases'
    releases.mkdir(parents=True, exist_ok=True)
    current = root / 'current'
    with (root / 'publish.lock').open('a') as lock, tempfile.TemporaryFile(dir=root) as archive:
        fcntl.flock(lock, fcntl.LOCK_EX)
        shutil.copyfileobj(stream, archive)
        archive.seek(0)
        if hashlib.file_digest(archive, 'sha256').hexdigest() != digest:
            raise ValueError('Incomplete publication transfer')
        archive.seek(0)
        stage = Path(tempfile.mkdtemp(dir=releases, prefix='site.'))
        previous = current.resolve(strict=True) if current.exists() else None
        pending = root / 'current.next'
        try:
            with tarfile.open(fileobj=archive, mode='r:gz') as tar:
                if any(not (m.isfile() or m.isdir()) for m in tar.getmembers()):
                    raise ValueError('Expected only static files and directories')
                tar.extractall(stage, filter='data')
            json.loads((stage / 'release.json').read_text())
            if not (stage / 'index.html').stat().st_size:
                raise ValueError('Empty publication')
            # The web worker needs traversal even when the deploy account uses umask 077.
            for path in [*stage.rglob('*'), stage]:
                path.chmod(0o755 if path.is_dir() else 0o644)
            pending.unlink(missing_ok=True)
            pending.symlink_to(stage)
            pending.replace(current)
            if verify:
                subprocess.run([verify, stage], check=True, timeout=90)
        except BaseException:
            if current.resolve() == stage:
                if previous:
                    pending.symlink_to(previous)
                    pending.replace(current)
                else:
                    current.unlink()
            shutil.rmtree(stage)
            raise
        for candidate in releases.glob('site.*'):
            if candidate.is_dir() and not candidate.is_symlink() and candidate not in (stage, previous):
                shutil.rmtree(candidate)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    modes = ap.add_subparsers(dest='mode', required=True)
    send = modes.add_parser('send')
    send.add_argument('--ssh-config', required=True)
    send.add_argument('--target', required=True)
    send.add_argument('--receiver', required=True, help='Absolute installed path to this script on the web host')
    for parser in (send, modes.add_parser('receive')):
        parser.add_argument('--root', type=Path, required=True, help='Web-host publication root')
        parser.add_argument('--verify', help='Web-host executable that checks authenticated public delivery')
        if parser is not send:
            parser.add_argument('digest')
    send.add_argument('site', type=Path)
    args = ap.parse_args()
    if args.mode == 'receive':
        receive(args.root, args.digest, args.verify, sys.stdin.buffer)
        return
    with tempfile.TemporaryFile() as archive:
        with tarfile.open(fileobj=archive, mode='w:gz') as tar:
            tar.add(args.site, arcname='.')
        archive.seek(0)
        digest = hashlib.file_digest(archive, 'sha256').hexdigest()
        archive.seek(0)
        remote = ['python3', args.receiver, 'receive', '--root', str(args.root)]
        if args.verify:
            remote += ['--verify', args.verify]
        subprocess.run(['ssh', '-T', '-F', args.ssh_config, '-o', 'BatchMode=yes',
                        '--', args.target, shlex.join([*remote, digest])], stdin=archive, check=True)


if __name__ == '__main__':
    main()
