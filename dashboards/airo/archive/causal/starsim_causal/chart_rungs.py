"""Side-by-side intervention panels, one per rung of the coverage ladder.
Same score in both: Brier skill vs the ½ forecast, against the certified P*_int.
Reads results/scores_summary.json (90% rung) and results/scores_summary_<tag>.json.

  uv run python results/causal/starsim_causal/chart_rungs.py [--tag hold]   # -> results/eci_vs_recovered_rungs.{png,svg}
"""
import argparse
import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

from chart import (HERE, INK2, MUTED, RUG_BAND, RUG_MIN, SURFACE, panel, place_labels, place_rug, short_name)
from models import load_roster

FLOOR = -1.0   # y-axis floor; scores below it are drawn on the floor and annotated


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="hold")
    ap.add_argument("--results-dir", default=str(HERE / "results"))
    a = ap.parse_args()
    rdir = Path(a.results_dir)
    by_id = {m.openrouter_id: m for m in load_roster()}
    d1 = json.load(open(HERE / "worlds.json"))["design"]
    d2 = json.load(open(HERE / f"worlds_{a.tag}.json"))["design"]
    eff = int(d1["vax"]["efficacy"] * 100)
    cov1 = f"{int(d1['vax']['coverage'] * 100)}% of the leading region vaccinated"
    cov2 = ", ".join(f"{w} {int(round(c * 100))}%" for w, c in d2["rung"]["coverages"].items())
    rungs = [
        ("scores_summary.json", f"B1. Intervention, easy rung — coverage {int(d1['vax']['coverage'] * 100)}% (8 items)",
         f"vaccine: day 21, {eff}% efficacy, {cov1}  ·  every answer flips (Δdo = ±1)"),
        (f"scores_summary_{a.tag}.json", f"B2. Intervention, hard rung — coverage 10–20% (8 items)",
         f"vaccine: day 21, {eff}% efficacy, largest coverage that does not flip the answer: {cov2}  ·  no answer flips (Δdo ≈ 0)"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.2), facecolor=SURFACE)
    ymin = 0.0
    for ax, (fname, title, sub) in zip(axes, rungs):
        summ = json.load(open(rdir / fname))["models"]
        rows = [(by_id[m], t["intervention_recovered"], t["n_resp_int"] < 40) for m, t in summ.items()
                if t.get("intervention_recovered") is not None]
        xs = np.array([m.eci for m, _, _ in rows]); ys = np.array([y for _, y, _ in rows])
        names = [short_name(m) + (" †" if p else "") for m, _, p in rows]
        # clip the axis at FLOOR; off-scale points sit on the floor with their value in the label
        off = ys < FLOOR
        names = [f"{n} ({y:+.2f}, below axis)" if o else n for n, y, o in zip(names, ys, off)]
        ys = np.where(off, FLOOR + 0.06, ys)
        panel(ax, xs, ys, ys, ys, names, title,
              sub + "\nBrier skill score vs the ½ forecast, against the certified P*  ·  1 = ceiling  ·  0 = uninformed  ·  < 0 = confidently wrong", "")
        ax.texts[-1].set_position((0.99, 0.12))   # Spearman note: clear of floor-clipped labels
        ymin = min(ymin, ys.min()); ax._labels = (xs, ys, names)
    lo_lim = max(np.floor((ymin - 0.05) * 4) / 4, FLOOR)
    rug = {ax: (ax._labels[1] >= RUG_BAND).sum() >= RUG_MIN for ax in axes}
    top = 1.05 + 0.31 * (1.05 - lo_lim) / 1.05 if any(rug.values()) else 1.22   # same rug headroom as chart.py
    for ax in axes:
        ax.set_ylim(lo_lim, top); ax.set_xlim(127, 166)
        ax.set_yticks(np.arange(lo_lim, 1.01, 0.5 if lo_lim <= -0.5 else 0.25))
    axes[0].set_ylabel("share of recoverable score (Brier skill vs ½)", color=INK2)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    for ax in axes:
        xs, ys, nm = ax._labels
        if rug[ax]:
            band = ys >= RUG_BAND
            place_rug(ax, fig, xs[band], ys[band], [n for n, b in zip(nm, band) if b], y_text=1.05)
            place_labels(ax, fig, xs[~band], ys[~band], [n for n, b in zip(nm, band) if not b])
        else:
            place_labels(ax, fig, xs, ys, nm)
    fig.text(0.01, 0.012,
             "StarSim causal bench v3 · 24 models via OpenRouter, vendor-default sampling, K = 5 reps, per-item medians · "
             "baseline and intervention asked in separate prompts · same 4 worlds, reports, question and horizons (day 40, day 60) on both rungs; "
             "only vaccine coverage differs\ntruth: certified P* given the shown day-20 report · † partial reps (deepseek-v4-flash)",
             color=MUTED, fontsize=7.6, va="bottom", linespacing=1.4)
    out = rdir / "eci_vs_recovered_rungs"
    fig.savefig(out.with_suffix(".png"), dpi=200, facecolor=SURFACE)
    fig.savefig(out.with_suffix(".svg"), facecolor=SURFACE)
    print(f"[saved] {out}.png / .svg")


if __name__ == "__main__":
    main()
