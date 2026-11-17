#!/usr/bin/env python3
"""Graph 4 (the lead author's calibration format) fed the TWO-SIM AVERAGE.

Keeps the lead author's Graph-4 design (per-model calibration curves + Brier skill).
For each model, pools its forecasts from BOTH simulators, weighting each simulator
EQUALLY (so it's an average, not a count-weighted pool):
  - CivBench (FreeCiv): H2-H4 horizon x 5-9% base-rate subset of the full eval.
  - Starsim pandemic: the deaths-threshold smoke (per-question preds).
Where only one simulator scored a model, that one is used.

Thin shim: computes the blob via redlines.views.graph4.build (the pure port
of this script's original logic), mirrors it to results/graph4_combined.json
in the exact byte format this script always wrote (indent=2, no trailing
newline -- hydrate.inject's own json_out writer adds a trailing newline,
which would break byte-identical output here), then splices it into
index.html via redlines.hydrate.inject.

    uv run python code/make_demo_combined.py --final
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redlines.config import REPO_ROOT, FBSIM_ROOT
from redlines.views.graph4 import build
from redlines.hydrate import inject


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", type=Path, default=REPO_ROOT / "results" / "eval_full.json")
    ap.add_argument("--questions", type=Path, default=FBSIM_ROOT / "data" / "lowprob" / "lowprob_questions.json")
    ap.add_argument("--pandemic-preds", type=Path, default=REPO_ROOT / "results" / "pandemic" / "smoke_preds.json")
    ap.add_argument("--out-json", type=Path, default=REPO_ROOT / "results" / "graph4_combined.json")
    ap.add_argument("--final", action="store_true")
    args = ap.parse_args()

    blob = build(args.eval, args.questions, args.pandemic_preds, final=args.final)

    # Mirror to results/graph4_combined.json in the script's original format
    # (indent=2, no trailing newline) — hydrate.inject's own json_out writer
    # adds a trailing newline, which would break byte-identical output here.
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    json.dump(blob, open(args.out_json, "w"), indent=2)

    html_path = inject("GRAPH4", blob)

    base = blob["base"]
    domain_max = blob["domainMax"]
    print(f"{'[FINAL] ' if args.final else '[prelim] '}wrote {args.out_json.name} + {html_path.name}")
    print(f"base {base*100:.2f}%  domainMax {domain_max}  nModels {blob['nModels']}")
    print(f"\n{'model':14s} {'ECI':>4} {'BSS':>7} {'meanP':>6} sims")
    for m in blob["models"]:
        print(f"{m['label']:14s} {m['eci']:>4} {(m['bss'] or 0):>7.2f} {m['meanPred']:>6.3f}  {m['sims']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
