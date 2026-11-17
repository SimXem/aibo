#!/usr/bin/env python3
"""Graph 3 hydration: REAL calibration & resolution from ForecastBench.

Thin shim: computes the blob via redlines.views.graph3.build (the pure port
of this script's original logic — see that module's docstring for the full
write-up: the bare/tools/superforecaster series, the dataset-vs-market
scaffolding finding, and why there is deliberately NO horizon filter), mirrors
it to results/graph3_data.json, and splices it into index.html via
redlines.hydrate.inject — exactly as this script always did.

Source: ~/Projects/forecastbench-datasets (Karger et al., ICLR 2025; CC BY-SA 4.0).
The processed sets are NOT in that git repo — refresh them from
https://www.forecastbench.org/assets/data/processed-forecast-sets/processed_forecast_sets.tar.gz

    python3 code/make_demo_graph3.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redlines.hydrate import inject
from redlines.views.graph3 import build


if __name__ == "__main__":
    blob = build()
    path = inject("GRAPH3", blob, json_out="results/graph3_data.json")
    for k, lbl in (("bare", "bare"), ("tools", "with tools"), ("sup", "superf.")):
        s = blob[k]
        d, m, v = s["split"]["dataset"], s["split"]["market"], s["vsMarket"]
        line = f"  {lbl:11} n={s['n']:6} brier={s['brier']}   dataset={d.get('brier')}"
        if "brier" in m:
            line += f"  market={m['brier']}"
        if v:
            line += (f"   vs price: {v['brier']} vs {v['market']} "
                     f"edge={v['edge']:+.4f} corr={v['corr']} gap={v['medianGap']}")
        print(line)
    p = blob["perModel"]["pooled"]["market"]
    print(f"  per-model pooled market: n={p['n']} brier={p['brier']} "
          f"tail {p['lo']['pred']}->{p['lo']['obs']}")
    for g in blob["grokControl"]:
        print(f"  control {g['round']} {g['entry']:22} n={g['n']:4} "
              f"bare {g['bare']['brier']} -> tools {g['tools']['brier']}")
    print(f"GRAPH3 -> {path.name}")
