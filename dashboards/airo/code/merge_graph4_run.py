#!/usr/bin/env python3
"""Merge a per-model Graph 4 run into the ladder's input files.

Graph 4 (redlines/views/graph4.py) reads one CivBench eval file and one
Starsim pandemic prediction file for the whole ladder. Adding a model means
running only it through both simulators (archive/litellm-runners/run_eval.py --models ...
--out results/eval_<tag>; archive/litellm-runners/pandemic_smoke.py --models ... --out
results/pandemic/<tag>) and splicing its predictions in -- the same games,
questions, seed and Starsim runs as everyone else, so the join is exact.
This was done by hand for GPT-5.5 / Gemini 3.1 Pro / Grok 4.20 on 2026-08-27
(commit 600da73); this script is that merge, written down.

    python3 code/merge_graph4_run.py --tag panel2 [--dry-run]

CivBench: results/eval_<tag>/eval_full.json's per-row `predictions[model]`
are added to results/eval_full.json's rows, keyed on (game_id, question_id)
-- every row of the run must exist in the ladder file and vice versa;
results/metrics_<tag>.csv rows are appended to results/metrics_full.csv.
Pandemic: results/pandemic/<tag>/smoke_preds.json's models are added to
results/pandemic/smoke_preds.json (and their metrics to smoke_metrics.json).
A model already present is replaced only with --replace.

results/eval_full.json is gitignored (regenerated, and on the box by rsync);
the pandemic files and metrics_full.csv are tracked. Rebuild with
`python3 -m redlines build --views g4` afterwards.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LADDER_EVAL = REPO / "results" / "eval_full.json"
LADDER_METRICS = REPO / "results" / "metrics_full.csv"
LADDER_PREDS = REPO / "results" / "pandemic" / "smoke_preds.json"
LADDER_SMOKE_METRICS = REPO / "results" / "pandemic" / "smoke_metrics.json"


def merge_civbench(tag, replace, dry_run):
    run_dir = REPO / "results" / f"eval_{tag}"
    run = json.load(open(run_dir / "eval_full.json"))
    ladder = json.load(open(LADDER_EVAL))
    models = run["metadata"]["models"]
    if (run["metadata"]["games"], run["metadata"]["questions"], run["metadata"]["seed"]) != \
            (ladder["metadata"]["games"], ladder["metadata"]["questions"], ladder["metadata"]["seed"]):
        raise SystemExit(f"{run_dir.name}: games/questions/seed differ from the ladder's -- not the same sample")
    by_key = {(r["game_id"], r["question_id"]): r for r in ladder["results"]}
    run_keys = {(r["game_id"], r["question_id"]) for r in run["results"]}
    if run_keys != set(by_key):
        raise SystemExit(f"{run_dir.name}: row set differs from the ladder's ({len(run_keys)} vs {len(by_key)})")
    present = [m for m in models if m in ladder["metadata"]["models"]]
    if present and not replace:
        raise SystemExit(f"already on the ladder: {present} (use --replace)")
    n = 0
    for r in run["results"]:
        row = by_key[(r["game_id"], r["question_id"])]
        for m in models:
            if m in r["predictions"]:
                row["predictions"][m] = r["predictions"][m]
                n += 1
    ladder["metadata"]["models"] = [m for m in ladder["metadata"]["models"] if m not in models] + models
    ladder["metadata"].setdefault("eci", {}).update(run["metadata"].get("eci") or {})
    for m in models:
        ladder["metrics"][m] = run["metrics"][m]
    print(f"civbench: {n} predictions for {models} onto {len(by_key)} rows")
    # metrics csv
    with open(run_dir / "metrics_full.csv") as fh:
        new_rows = list(csv.DictReader(fh))
    with open(LADDER_METRICS) as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        old_rows = [r for r in reader if r["model"] not in models]
    if not dry_run:
        json.dump(ladder, open(LADDER_EVAL, "w"), indent=1)
        with open(LADDER_METRICS, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(old_rows + [{k: r.get(k, "") for k in fields} for r in new_rows])
    return models


def merge_pandemic(tag, replace, dry_run):
    run_dir = REPO / "results" / "pandemic" / tag
    preds = json.load(open(run_dir / "smoke_preds.json"))
    metrics = json.load(open(run_dir / "smoke_metrics.json"))
    ladder = json.load(open(LADDER_PREDS))
    ladder_metrics = json.load(open(LADDER_SMOKE_METRICS))
    present = [m for m in preds if m in ladder]
    if present and not replace:
        raise SystemExit(f"already in smoke_preds.json: {present} (use --replace)")
    for m, v in preds.items():
        ladder[m] = v
        print(f"pandemic: {m} ({v['label']}, ECI {v['eci']}): {len(v['samples'])} samples")
    for k in ("metrics", "refusals", "errors"):
        if k in metrics:
            ladder_metrics.setdefault(k, {}).update(metrics[k])
    if not dry_run:
        json.dump(ladder, open(LADDER_PREDS, "w"))
        json.dump(ladder_metrics, open(LADDER_SMOKE_METRICS, "w"), indent=2, default=str)
    return list(preds)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", required=True, help="results/eval_<tag>/ and results/pandemic/<tag>/")
    ap.add_argument("--replace", action="store_true", help="overwrite a model already on the ladder")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-civbench", action="store_true")
    ap.add_argument("--skip-pandemic", action="store_true")
    a = ap.parse_args()
    if not a.skip_civbench:
        merge_civbench(a.tag, a.replace, a.dry_run)
    if not a.skip_pandemic:
        merge_pandemic(a.tag, a.replace, a.dry_run)
    if a.dry_run:
        print("dry run: nothing written")
    else:
        print("merged; now: python3 -m redlines build --views g4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
