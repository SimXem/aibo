"""Read one explicitly supplied, hash-pinned news snapshot through read_page.

No arbitrary local-file access. Not enabled unless the caller supplies both
private environment values. Model-visible tool descriptions stay unchanged.
"""
import hashlib
import json
import os
from pathlib import Path

URL = "file:///news/recent.json"
PATH_ENV = "FORECASTER_NEWS_SNAPSHOT"
HASH_ENV = "FORECASTER_NEWS_SHA256"


def read_snapshot(url, offset=0):
    if url != URL:
        return None
    try:
        path, expected = os.environ[PATH_ENV], os.environ[HASH_ENV]
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("snapshot hash mismatch")
        text = raw.decode("utf-8")
        start = max(0, int(offset))
        result = {"url": url, "offset": start, "total_chars": len(text),
                  "text": text[start:start + 7000], "snapshot_sha256": expected}
        if start + 7000 < len(text):
            result["next_offset"] = start + 7000
        return result
    except (KeyError, OSError, ValueError) as e:
        return {"url": url, "text": "", "error": f"news snapshot unavailable: {type(e).__name__}"}
