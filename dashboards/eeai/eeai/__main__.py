"""python3 -m eeai {prompt,run,build}"""
import argparse
import sys
from datetime import date, datetime, timezone

from . import config, instrument, survey as S


def cmd_prompt(args):
    from fri_forecaster import baseline, panel
    survey, history = S.load(), S.history()
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    prompt, qids = instrument.build_prompt(survey, history, today)
    members, _ = panel.panel(snapshot_dir=config.ECI_DIR)
    print(f"##### {config.EXPERIMENT} / {config.CONDITION} [{survey['instrument']}]: {len(qids)} questions, "
          f"{S.n_values(survey, today)} values + Part 1, {len(prompt)} chars #####")
    print(prompt)
    print("##### TOOLS: " + ", ".join(t["name"] for t in baseline.research_tools())
          + ", submit_cells, submit_forecast; no system prompt; turn limit "
          + f"{baseline.MAX_TURNS} #####")
    print("##### PANEL: " + ", ".join(f"{m['label']} ({m['pi_model']}, thinking {m['reasoning']})" for m in members)
          + " #####")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m eeai", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prompt", help="print the prompt, the tools and the panel; calls nothing")
    p.add_argument("--today")
    r = sub.add_parser("run", help="ask the panel (PAID unless --synthetic)")
    r.add_argument("--smoke", action="store_true", help="the panel's top model only")
    r.add_argument("--models", help="panel members by key or label, comma-separated")
    r.add_argument("--resume", metavar="RUN_ID", help="add the models an earlier run file lacks, under its run id and date")
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--retries", type=int, default=1, help="extra calls for a model that delivers too little")
    r.add_argument("--out", help="directory for the run file (default eeai/results/runs)")
    r.add_argument("--today", help="the run date, YYYY-MM-DD (default today, UTC)")
    r.add_argument("--synthetic", action="store_true", help="no calls: made-up answers (needs --out)")
    r.add_argument("--allow-ungrounded", action="store_true", help="run without TAVILY_API_KEY")
    b = sub.add_parser("build", help="the run files -> the page")
    b.add_argument("--runs", help="directory of run files (default eeai/results/runs)")
    b.add_argument("--out", help="write only the page, to this file (and the download beside it)")
    b.add_argument("--json", help="also write the page's data here")
    b.add_argument("--site", help="the site folder to write (default eeai/site): index.html, the download, web/")
    args = ap.parse_args(argv)
    if args.cmd == "prompt":
        return cmd_prompt(args)
    if args.cmd == "run":
        from . import run
        return run.main(args)
    from . import build
    return build.main(args)


if __name__ == "__main__":
    sys.exit(main())
