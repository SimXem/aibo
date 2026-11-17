"""Frozen feed-only inputs for the manual recent-shadow-noairo condition."""
import hashlib
import json
import re
import os
import tempfile
from pathlib import Path

from . import recent_news as news
from .tools import is_blocked

URL = "file:///news/recent.json"
# User-supplied wording, verbatim except substituting the fixed model-visible path.
NEWS_SENTENCE = f"For convenience, some relevant recent news stories are provided in {URL}."
PATH_ENV = "FORECASTER_NEWS_SNAPSHOT"
HASH_ENV = "FORECASTER_NEWS_SHA256"


def snapshot(state, since, as_of, guard):
    """Build from a completed reduction, never from survey/update/fulltext logs.

    Refuse post-cutoff reductions rather than pretending to reconstruct history.
    Filter blocked members before selecting the story headline and sources.
    """
    since, as_of = news.parse_time(since), news.parse_time(as_of)
    if not since or not as_of or since >= as_of:
        raise ValueError("snapshot requires since < as_of")
    state = Path(state)
    built = json.loads((state / "stories.json").read_text())
    if built["built_at"] > as_of or built["stats"].get("undecided"):
        raise ValueError("snapshot requires a complete reduction built on/before as_of")
    items = news.load_items(state)
    pats = [re.compile(p.strip(), re.I) for p in re.split(r"[\n,]", guard) if p.strip()]
    stories = []
    for story in sorted(built["stories"], key=lambda s: (s["first_seen"], s["id"])):
        if not since <= story["first_seen"] <= as_of:
            continue
        members = []
        for member in story["members"]:
            it = items[member["item"]]
            if it["first_fetched"] > as_of or news.item_time(it) > as_of:
                raise ValueError("snapshot contains a member observed/published after as_of")
            if is_blocked(it["url"], pats) or is_blocked(it["link"], pats):
                continue
            members.append({k: it.get(k) for k in
                            ("id", "source", "title", "summary", "url", "published", "first_fetched")})
        if members:
            stories.append({"id": story["id"], "title": members[0]["title"],
                            "first_seen": story["first_seen"], "reports": members})
    if not stories:
        raise ValueError("no news stories in the requested window")
    return {"schema": "recent-news-shadow-v1", "since": since, "as_of": as_of,
            "built_at": built["built_at"], "url_block_patterns": guard,
            "collected_until": max(it["first_fetched"] for it in items.values()),
            "headlines": [{"id": s["id"], "date": s["first_seen"], "title": s["title"]}
                          for s in stories], "stories": stories}


def pin(path, guard, directory=None):
    """Validate and copy input once before workers start; stamp exact bytes.

    No source path in forecast rows or model-visible prompt. Each tool read
    checks the hash again, so changed input fails rather than silently drifting.
    """
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    if data.get("schema") != "recent-news-shadow-v1" or not data.get("stories"):
        raise ValueError("expected a nonempty recent-news-shadow-v1 snapshot")
    if data.get("url_block_patterns") != guard:
        raise ValueError("snapshot URL guard differs from condition")
    since, end, built = (news.parse_time(data.get(k)) for k in ("since", "as_of", "built_at"))
    if not all((since, end, built)) or not since < end or built > end:
        raise ValueError("invalid snapshot date window")
    pats = [re.compile(p.strip(), re.I) for p in re.split(r"[\n,]", guard) if p.strip()]
    for s in data["stories"]:
        if not since <= s["first_seen"] <= end:
            raise ValueError("story outside snapshot window")
        for m in s["reports"]:
            if is_blocked(m["url"], pats):
                raise ValueError("blocked source in news snapshot")
            if m["first_fetched"] > end or (m.get("published") or m["first_fetched"]) > end:
                raise ValueError("post-cutoff news report")
    sha = hashlib.sha256(raw).hexdigest()
    folder = Path(directory or Path(news.STATE_DIR) / "snapshots")
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{sha}.json"
    if dest.exists():
        if dest.read_bytes() != raw:
            raise ValueError("existing pinned snapshot is corrupt")
    else:
        # Parallel probes may pin the same input. Never expose a truncated file
        # to another reader: publish a fully written temporary file atomically.
        fd, name = tempfile.mkstemp(dir=folder, prefix=".pin-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
            os.replace(name, dest)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    return {"path": str(dest.resolve()), "sha256": sha, "since": since, "as_of": end,
            "built_at": built, "collected_until": data["collected_until"],
            "stories": len(data["stories"])}
