import argparse
import json
import sys
from datetime import date, datetime, timezone

from . import config  # noqa: F401  (puts the engine on the path in a bare checkout)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m leap", description=sys.modules["leap"].__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prompt", help="print the prompt a model gets; no calls")
    p.add_argument("questions")
    p.add_argument("--today")
    r = sub.add_parser("run", help="ask the panel (PAID: model and search calls)")
    r.add_argument("questions", help="the question set, as sent")
    r.add_argument("--out", required=True, help="directory for the run file (outside the repository)")
    r.add_argument("--models", help="only these panel members (keys or labels, comma-separated)")
    r.add_argument("--resume", metavar="RUN_ID", help="finish that run: the models it does not have yet")
    r.add_argument("--retries", type=int, default=1, help="ask a member again while values are missing (default 1)")
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--today", help="the run date, YYYY-MM-DD (default: today, UTC)")
    r.add_argument("--allow-ungrounded", action="store_true", help="run without the search key")
    b = sub.add_parser("build", help="pool the members and write the checked submission file")
    b.add_argument("questions")
    b.add_argument("run", help="the run file")
    b.add_argument("--model", required=True, help="the forecasting system's name; stable across waves, a new suffix when it changes")
    b.add_argument("--organization", default="FRI")
    b.add_argument("--model-organization", default="FRI", help="who made the underlying model; our own name for an ensemble")
    b.add_argument("--out", required=True, help="directory for the submission file")
    b.add_argument("--allow-partial", action="store_true", help="build even when a member lacks an entry")
    args = ap.parse_args(argv)
    if args.cmd == "prompt":
        from . import instrument
        with open(args.questions, encoding="utf-8") as f:
            question_set = json.load(f)
        today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
        print(instrument.build_prompt(question_set, today)[0])
        return 0
    if args.cmd == "run":
        from . import run
        return run.main(args)
    from . import build
    return build.main(args)


if __name__ == "__main__":
    sys.exit(main())
