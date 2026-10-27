#!/usr/bin/env python3
"""Prepare a current frozen news input only for conditions that require it.

Used by cron_run.sh before the Friday shadow, never to alter ordinary AIRO
calls. All feeds must return nonempty, parseable data. Jev reduction may incur
charges; failures exit nonzero and must not fall back to an old snapshot.
Prints the snapshot path, or nothing when this group does not need news.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from redlines import experiments, news_shadow, recent_news as news


def prepare(state, guard, *, poll=None, reduce=None, now=None):
    poll, reduce = poll or news.poll, reduce or news.run_reduce
    state = Path(state)
    rows = poll(state_dir=state)
    if not rows or any(r.get("error") or not r.get("entries") for r in rows):
        raise ValueError("current news poll incomplete; refusing stale/partial input (see fetches.jsonl)")
    reduce(state_dir=state)
    end = now or datetime.now(timezone.utc)
    fmt = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = news_shadow.snapshot(state, fmt(end - timedelta(days=7)), fmt(end), guard)
    target = state / "prepared" / (end.strftime("%Y-%m-%dT%H%M%S") + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    # Reuse the same validation and immutable-copy path as a manual launch.
    pinned = news_shadow.pin(target, guard, directory=state / "snapshots")
    return pinned["path"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--condition", action="append", required=True)
    ap.add_argument("--state", default=news.STATE_DIR)
    args = ap.parse_args()
    try:
        exp = experiments.load(args.experiment)
        conditions = [exp["conditions"][cid] for cid in args.condition]
        required = [c for c in conditions if c["news_cache"]]
        if not required:
            return 0
        if len(required) != len(conditions):
            raise ValueError("run news-cache conditions separately from other conditions")
        guards = {c["url_block_patterns"] for c in required}
        if len(guards) != 1:
            raise ValueError("news group has different URL guards")
        # Load only the news key, not coding-provider credentials. Environment
        # wins; a private installation can also use the runtime home's file.
        if not os.environ.get("TYPESAFE_API_KEY"):
            from fri_forecaster.keys import parse_env
            envfile = Path(os.environ.get("AIRO_NEWS_ENV_FILE", Path.home() / ".config/airo-news/env"))
            key = parse_env(envfile).get("TYPESAFE_API_KEY")
            if key:
                os.environ["TYPESAFE_API_KEY"] = key
        print(prepare(args.state, guards.pop()))
    except (OSError, ValueError, KeyError, news.JevError) as e:
        print(f"news preparation failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
