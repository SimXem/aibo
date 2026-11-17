"""One panel: ECI vs intervention CRPS skill pooled over the coverage rungs (25/50/90%).

  uv run python results/causal/starsim_single/chart_pooled.py   # -> results/eci_vs_pooled.{png,svg,csv}
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "starsim_causal"))
from chart import (INK2, MUTED, RUG_BAND, RUG_MIN, SURFACE, panel, place_labels, place_rug, short_name)  # noqa: E402
from models import load_roster  # noqa: E402

RUNGS = {"90%": "scores.json", "50%": "scores_c50.json", "25%": "scores_c25.json"}


def main():
    rdir = HERE / "results"
    T = {r: json.load(open(rdir / f)) for r, f in RUNGS.items()}
    rows = []
    for m in load_roster():
        per = []
        for r in RUNGS:
            t = T[r].get(m.openrouter_id, {}).get("intervention")
            if t:
                per += [v["recovered"] for v in t["per_item"].values()]
        if len(per) == 8 * len(RUNGS):
            rows.append((m, float(np.mean(per))))
        else:
            print(f"skipped {m.openrouter_id}: {len(per)}/{8 * len(RUNGS)} items")
    eci = np.array([m.eci for m, _ in rows]); ys = np.array([y for _, y in rows]); names = [short_name(m) for m, _ in rows]

    fig, ax = plt.subplots(figsize=(9, 7.2), facecolor=SURFACE)
    panel(ax, eci, ys, ys, ys, names, f"Intervention forecasts, pooled over coverage rungs ({8 * len(RUNGS)} items)",
          "CRPS skill score vs climatology, mean over 8 items × 3 vaccine coverages (25%, 50%, 90%)\n"
          "1 = matches the simulator's distribution  ·  0 = climatology  ·  < 0 = worse", "")
    lo = max(np.floor((ys.min() - 0.05) * 4) / 4, -1.0)
    rug = (ys >= RUG_BAND).sum() >= RUG_MIN
    ax.set_ylim(lo, 1.36 if rug else 1.22); ax.set_xlim(127, 166); ax.set_yticks(np.arange(lo, 1.01, 0.25))
    ax.set_ylabel("share of recoverable CRPS", color=INK2)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    if rug:
        band = ys >= RUG_BAND
        place_rug(ax, fig, eci[band], ys[band], [n for n, b in zip(names, band) if b], y_text=1.05)
        place_labels(ax, fig, eci[~band], ys[~band], [n for n, b in zip(names, band) if not b])
    else:
        place_labels(ax, fig, eci, ys, names)
    fig.text(0.01, 0.012,
             f"StarSim single-region bench · {len(rows)} models via OpenRouter, vendor-default sampling, K = 3 reps · "
             "one SIR population of 5,000, parameters stated, report through day 20\nforecast = p10/p25/p50/p75/p90 of new "
             "infections by day 40 and day 60 given a day-21 vaccination campaign (95% efficacy), 4 worlds (R0 1.8–3.9)\n"
             "truth: seed-matched simulator distribution",
             color=MUTED, fontsize=7.6, va="bottom", linespacing=1.4)
    out = rdir / "eci_vs_pooled"
    fig.savefig(out.with_suffix(".png"), dpi=200, facecolor=SURFACE); fig.savefig(out.with_suffix(".svg"), facecolor=SURFACE)
    with open(out.with_suffix(".csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["model", "name", "eci", "pooled_intervention_recovered"])
        for m, y in rows:
            w.writerow([m.openrouter_id, short_name(m), m.eci, f"{y:.4f}"])
    print(f"[saved] {out}.png")


if __name__ == "__main__":
    main()
