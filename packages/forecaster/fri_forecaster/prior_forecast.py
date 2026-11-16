"""Read only the explicitly pinned prior forecast, using the existing page tool."""
import hashlib
import os
from pathlib import Path

URL = 'file:///forecasts/prior-ensemble.json'
PATH_ENV = 'FORECASTER_PRIOR_BASELINE_PATH'
HASH_ENV = 'FORECASTER_PRIOR_BASELINE_SHA256'


def read_snapshot(url, offset=0):
    if url != URL:
        return None
    try:
        raw = Path(os.environ[PATH_ENV]).read_bytes()
        digest = os.environ[HASH_ENV]
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('snapshot hash mismatch')
        text = raw.decode('utf-8')
        start = max(0, int(offset))
        result = dict(url=url, offset=start, total_chars=len(text),
                      text=text[start:start + 7000], snapshot_sha256=digest)
        if start + 7000 < len(text):
            result['next_offset'] = start + 7000
        return result
    except (KeyError, OSError, ValueError) as exc:
        return dict(url=url, text='', error=f'prior forecast unavailable: {type(exc).__name__}')
