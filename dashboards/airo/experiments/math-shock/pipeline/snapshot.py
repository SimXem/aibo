"""Resolve tracker commits for a date, from archived history only.

C(date) = last first-parent commit on the archived branch whose committer date is <= the end of
that day (UTC). The archived branch tip used is the newest archived bundle head.
"""
import subprocess

from .common import PipelineError, end_of_day_utc, git, git_cmd, work_repo
from .fetch import latest_archived_head


def tip(name):
    return f'refs/archive/{latest_archived_head(name)}'


def commit_at(name, date_str):
    repo = work_repo(name)
    t = tip(name)
    tip_date = git(repo, 'show', '-s', '--format=%cI', t).strip()
    # The archive must cover the whole day, otherwise a later fetch could change C(date).
    if _dt(_utc(tip_date)) < _dt(end_of_day_utc(date_str)):
        raise PipelineError(f'{name}: archive ends {tip_date}, before the end of {date_str}; '
                            'choose an earlier date or fetch again later')
    c = git(repo, 'rev-list', '--first-parent', '-1', f'--before={end_of_day_utc(date_str)}', t).strip()
    if not c:
        raise PipelineError(f'{name}: no commit on or before {date_str}')
    return c


def commit_info(name, c):
    out = git(work_repo(name), 'show', '-s', '--format=%H%x09%cI%x09%s', c).strip()
    h, d, s = out.split('\t', 2)
    return {'sha': h, 'committer_date': d, 'subject': s}


def first_parent_commits(name, c_from, c_to, path):
    """Commits on the first-parent chain in (c_from, c_to] touching `path`, oldest first."""
    out = git(work_repo(name), 'log', '--first-parent', '--reverse', '--format=%H%x09%cI%x09%s',
              f'{c_from}..{c_to}', '--', path)
    rows = []
    for line in out.splitlines():
        h, d, s = line.split('\t', 2)
        rows.append({'sha': h, 'committer_date': d, 'subject': s})
    return rows


def _utc(iso):
    import datetime as dt
    return dt.datetime.fromisoformat(iso).astimezone(dt.timezone.utc).isoformat()


def _dt(iso):
    import datetime as dt
    return dt.datetime.fromisoformat(iso)


class CatFile:
    """Persistent `git cat-file --batch` reader (fast blob access on Windows)."""

    def __init__(self, name):
        self.p = subprocess.Popen([*git_cmd(work_repo(name)), 'cat-file', '--batch'],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def get(self, rev_path):
        """rev_path like '<commit>:<path>'; returns (blob_sha, text) or (None, None) if missing."""
        self.p.stdin.write((rev_path + '\n').encode()); self.p.stdin.flush()
        header = self.p.stdout.readline().decode().rstrip('\n')
        if header.endswith('missing'):
            return None, None
        sha, _typ, size = header.split()
        data = self.p.stdout.read(int(size)); self.p.stdout.read(1)
        return sha, data.decode('utf-8', errors='replace')

    def close(self):
        self.p.stdin.close(); self.p.wait()
