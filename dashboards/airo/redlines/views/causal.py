"""Graph 6 (causal conditionals): blob builder.

The StarSim causal bench -- data/causal/, the locked dataset of 2026-08-28
from the ForecastBench-Sim ICLR work (iclr-2026 repo, tag causal-v4-locked;
generating code frozen under archive/causal/). One SIR population of 5,000
agents (starsim 3.3.4) with its parameters stated and its first twenty days
shown; a model forecasts the new infections by day 40 and day 60 as five
quantiles, once with no intervention and once given a day-21 vaccination
campaign of 25, 50 or 90% coverage, in SEPARATE prompts. Truth is the
simulator's own distribution over seeds matching the shown trajectory;
the score is CRPS skill against a fixed climatology (1 = the simulator's
distribution, 0 = climatology, below 0 = worse). Twenty-four models via
OpenRouter, vendor-default sampling, K = 3.

The chart is the dataset's headline figure: each model's intervention skill
pooled over the three coverage rungs, against ECI. The pooled numbers are
READ from the locked results/eci_vs_pooled.csv, never recomputed, and the
rank correlation and its p-value are recomputed here from that file
(redlines.stats.spearman_ties / spearman_p reproduce scipy's spearmanr;
tests/test_conditional_benches.py pins them to the README's rho=+0.68,
p=0.0003, n=23). Per-rung and baseline detail for the tooltips comes from the
per-rung score summaries. DeepSeek V4 Flash is partial in the dataset and
is excluded from the pooled figure, as the dataset's README excludes it.

Pure: build() reads its inputs and returns the blob dict; no writes.
"""
from __future__ import annotations

import csv
import json

from ..config import REPO_ROOT
from ..roster import by_id as roster_by_id
from ..stats import spearman_p, spearman_ties

DATA = REPO_ROOT / "data" / "causal"
POOLED = DATA / "results" / "eci_vs_pooled.csv"
RUNGS = ("25", "50", "90")
DESIGN = ("8 items (4 SIR worlds, R0 1.8-3.9, x day-40/day-60) x 3 vaccine-coverage rungs (25/50/90%); "
          "baseline and intervention in separate prompts; K=3 reps; truth = seed-matched simulator "
          "distribution; score = CRPS skill vs climatology (1 = simulator's distribution, 0 = climatology)")


def _summary(rung):
    return json.load(open(DATA / "results" / f"scores_summary_c{rung}.json"))


def build(data=DATA):
    pooled_path = data / "results" / "eci_vs_pooled.csv"
    roster = roster_by_id()
    summaries = {r: json.load(open(data / "results" / f"scores_summary_c{r}.json")) for r in RUNGS}

    models = []
    with open(pooled_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            mid = r["model"]
            m = roster.get(mid)
            if m is None:
                raise KeyError(f"{mid!r} in {pooled_path.name} is not on the roster")
            per = {}
            for rung in RUNGS:
                s = summaries[rung]["models"].get(mid) or {}
                per[rung] = {"intervention": _r(s.get("intervention_recovered")),
                             "effect": _r(s.get("effect_recovered"))}
            base = summaries["50"]["models"].get(mid, {}).get("baseline_recovered")
            models.append({"id": mid, "label": m["label"], "eci": float(r["eci"]), "inPanel": m["inPanel"],
                           "color": m["color"],
                           "recovered": float(r["pooled_intervention_recovered"]),
                           "baseline": _r(base), "perRung": per})
    models.sort(key=lambda m: m["eci"])

    xs = [m["eci"] for m in models]
    ys = [m["recovered"] for m in models]
    rho = spearman_ties(xs, ys)
    bxs = [m["eci"] for m in models if m["baseline"] is not None]
    bys = [m["baseline"] for m in models if m["baseline"] is not None]
    brho = spearman_ties(bxs, bys)
    per_rung = {}
    for rung in RUNGS:
        g = summaries[rung]["gradient"]["intervention_recovered"]["eci"]
        per_rung[rung] = {"rho": round(g["rho"], 4), "p": round(g["p"], 4), "n": g["n"]}
    # The causal roster only: redlines.roster also carries Graph 4's extra
    # models for the observational bench, which this bench never ran.
    on_roster = {mid for mid, r in roster.items() if r["source"] == "causal"}
    excluded = sorted(on_roster - {m["id"] for m in models})
    best = max(models, key=lambda m: m["recovered"])
    worst = min(models, key=lambda m: m["recovered"])
    return {
        "source": {
            "bench": "StarSim single-region causal bench, locked dataset 2026-08-28 (data/causal/README.md)",
            "upstream": "iclr-2026 repo, results/causal/data at tag causal-v4-locked; code frozen under archive/causal/",
            "file": "data/causal/results/eci_vs_pooled.csv",
            "eci": "data/causal/models.csv (Epoch Capabilities Index as published 2026-08-27; see redlines/roster.py)",
        },
        "design": DESIGN,
        "headline": {"rho": round(rho, 4), "p": round(spearman_p(rho, len(xs)), 4), "n": len(xs),
                     "baselineRho": round(brho, 4), "baselineP": round(spearman_p(brho, len(bxs)), 4),
                     "perRung": per_rung},
        "excluded": [{"id": mid, "label": roster[mid]["label"],
                      "why": "partial: its default reasoning stalls; excluded from the pooled figure as in the dataset"}
                     for mid in excluded],
        "best": {"label": best["label"], "recovered": best["recovered"]},
        "worst": {"label": worst["label"], "recovered": worst["recovered"]},
        "models": models,
    }


def _r(v, nd=4):
    return None if v is None else round(v, nd)
