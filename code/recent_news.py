#!/usr/bin/env python3
"""Isolated news experiment. See experiments/recent-news/README.md."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from redlines import recent_news as news


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("step", choices=["poll", "reduce", "list", "run", "report", "snapshot"])
    ap.add_argument("--state", default=news.STATE_DIR)
    ap.add_argument("--since", help="list/run: inclusive ISO date or timestamp (UTC default)")
    ap.add_argument("--as-of", help="snapshot: last permitted observation timestamp")
    ap.add_argument("--out", help="list/run/report: private output file; default stdout")
    ap.add_argument("--replay", action="store_true", help="reduce only: no API calls")
    a = ap.parse_args(argv)
    if a.step in ("list", "run") and not news.parse_time(a.since):
        ap.error("list/run requires a valid --since ISO date or timestamp")
    if a.replay and a.step != "reduce":
        ap.error("--replay is only supported with reduce")
    if a.out and a.step not in ("list", "run", "report", "snapshot"):
        ap.error("--out is only supported with list/run/report")
    try:
        if a.step == "snapshot":
            from redlines import experiments, news_shadow
            if not a.out or not a.since or not a.as_of:
                ap.error("snapshot requires --since, --as-of and --out")
            c = experiments.load("recent-shadow-noairo")["conditions"]["recent-shadow-noairo"]
            data = news_shadow.snapshot(a.state, a.since, a.as_of, c["url_block_patterns"])
            dest = Path(a.out).expanduser()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            return 0
        if a.step in ("poll", "run"):
            rows = news.poll(state_dir=a.state)
            print(json.dumps(rows), file=sys.stderr if a.step == "run" else sys.stdout)
            if any(r.get("error") or not r["entries"] for r in rows):
                print("Incomplete fetch: inspect fetches.jsonl; no combined run output produced.", file=sys.stderr)
                return 1
        if a.step in ("reduce", "run"):
            stats = news.run_reduce(state_dir=a.state, replay=a.replay)
            print(json.dumps(stats), file=sys.stderr if a.step == "run" else sys.stdout)
        text = None
        if a.step in ("list", "run"):
            text = json.dumps(news.stories_since(a.since, a.state), ensure_ascii=False, indent=2)
        elif a.step == "report":
            text = news.report(a.state)
        if text is not None:
            if a.out:
                Path(a.out).expanduser().write_text(text + "\n")
            else:
                print(text)
    except (news.JevError, OSError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
