"""Joint reading of the coverage ladder: rung 1 (90% coverage, every item flips)
and rung 2 ('hold': the largest campaign that does NOT flip the answer).

  A  rung 1 vs rung 2 effect scores — separates the two failure modes
     (ignores interventions: top-left; flips on any vaccine: bottom-right)
  B  ECI vs joint score = min(effect@90%, effect@hold)
Reads results/scores_summary.json (rung 1) and results/scores_summary_<tag>.json.

  uv run python results/causal/starsim_causal/ladder_chart.py [--tag hold]   # -> results/ladder.{png,svg}
"""
import argparse
import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

from chart import (AXIS, GRID, HERE, INK, INK2, MUTED, SERIES, SURFACE, panel, place_labels, place_rug, short_name)

CLUSTER = 0.85   # panel A: points with both rungs >= this are listed in a box instead of labelled in place
BAND = 0.87      # panel B: points with joint >= this get the sorted label rug along the top
from models import load_roster


def style(ax, title, subtitle):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontweight="bold", pad=38)
    ax.text(0, 1.012, subtitle, transform=ax.transAxes, color=INK2, fontsize=8.4, va="bottom", linespacing=1.35)
    ax.grid(color=GRID, lw=1, zorder=0)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(AXIS)
    ax.tick_params(colors=MUTED, length=3, color=AXIS)
    for lab in ax.get_xticklabels() + ax.get_yticklabels():
        lab.set_color(INK2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="hold")
    ap.add_argument("--results-dir", default=str(HERE / "results"))
    a = ap.parse_args()
    rdir = Path(a.results_dir)
    r1 = json.load(open(rdir / "scores_summary.json"))["models"]
    r2 = json.load(open(rdir / f"scores_summary_{a.tag}.json"))["models"]
    by_id = {m.openrouter_id: m for m in load_roster()}
    covs = json.load(open(HERE / f"worlds_{a.tag}.json"))["design"]["rung"]["coverages"]

    rows = []
    for mid in r1:
        if mid not in r2 or r1[mid]["effect_recovered"] is None or r2[mid]["effect_recovered"] is None:
            continue
        m = by_id[mid]
        partial = r1[mid]["n_resp_int"] < 40 or r2[mid]["n_resp_int"] < 40   # 8 items x K=5 per condition
        rows.append((m, r1[mid]["effect_recovered"], r2[mid]["effect_recovered"], short_name(m) + (" †" if partial else "")))
    e1 = np.array([r[1] for r in rows]); e2 = np.array([r[2] for r in rows]); joint = np.minimum(e1, e2)
    eci = np.array([r[0].eci for r in rows]); names = [r[3] for r in rows]

    fig, axes = plt.subplots(1, 2, figsize=(15, 7.2), facecolor=SURFACE)
    axA, axB = axes
    style(axA, "A. Rung 1 vs rung 2: the two ways to fail",
          "x: effect recovered at 90% coverage (every item flips)  ·  y: at the largest non-flipping coverage "
          f"({', '.join(f'{w} {int(round(c*100))}%' for w, c in covs.items())})\n"
          "top-right = flips when it should and holds when it should  ·  top-left = ignores the intervention  ·  "
          "bottom-right = flips on any vaccine")
    lo = min(0.0, e1.min() - 0.05, e2.min() - 0.05)
    axA.plot([lo, 1.05], [lo, 1.05], color=MUTED, lw=1, ls=(0, (3, 3)), zorder=1)
    axA.scatter(e1, e2, s=56, color=SERIES, edgecolor=SURFACE, linewidth=2, zorder=4)
    axA.set_xlim(lo, 1.06); axA.set_ylim(lo, 1.06)
    axA.set_xlabel("effect recovered, rung 1 (90% coverage)", color=INK2)
    axA.set_ylabel("effect recovered, rung 2 (hold)", color=INK2)
    axA.text(0.03, 0.97, "ignores the intervention", transform=axA.transAxes, color=MUTED, fontsize=8.6, va="top")
    axA.text(0.97, 0.05, "flips on any vaccine", transform=axA.transAxes, color=MUTED, fontsize=8.6, ha="right")
    cl = (e1 >= CLUSTER) & (e2 >= CLUSTER)
    order = sorted(np.flatnonzero(cl), key=lambda i: -joint[i])
    lines = [f"{names[i]}  {e1[i]:.2f} / {e2[i]:.2f}" for i in order]
    axA.text(0.42, 0.41, f"both rungs ≥ {CLUSTER:.2f}  (90% / hold), by joint score:\n" + "\n".join(lines),
             transform=axA.transAxes, color=INK2, fontsize=8.2, va="top", ha="left", linespacing=1.45,
             bbox=dict(boxstyle="round,pad=0.5", facecolor=SURFACE, edgecolor=GRID))

    panel(axB, eci, joint, joint, joint, names, "B. Joint score vs ECI",
          "min(effect at 90%, effect at hold) — a model reasons causally only if it does both\n"
          "1 = ceiling on both rungs  ·  0 = ignores the intervention or flips regardless", "")
    band = joint >= BAND
    axB.set_ylim(min(0.0, joint.min() - 0.05), 1.36 if band.sum() >= 6 else 1.22)
    axB.set_xlim(127, 166)
    axB.set_yticks(np.arange(0, 1.01, 0.25))
    axB.set_ylabel("joint share of recoverable effect", color=INK2)

    fig.tight_layout(rect=(0, 0.06, 1, 1))
    place_labels(axA, fig, e1[~cl], e2[~cl], [n for n, c in zip(names, cl) if not c])
    if band.sum() >= 6:
        place_rug(axB, fig, eci[band], joint[band], [n for n, b in zip(names, band) if b], y_text=1.05)
        place_labels(axB, fig, eci[~band], joint[~band], [n for n, b in zip(names, band) if not b])
    else:
        place_labels(axB, fig, eci, joint, names)
    fig.text(0.01, 0.012,
             f"StarSim causal bench v3 · {len(rows)} models via OpenRouter, vendor-default sampling, K = 5 reps, per-item medians · "
             "same 4 worlds, reports, question and horizons on both rungs; only the leader's vaccine coverage differs "
             "(day 21, 95% leaky efficacy)\n"
             "effect recovered = mean 1 − |(p̂_int − p̂_base) − Δdo|  (= (p̂_int − p̂_base)/Δdo on flip items; = 1 − |p̂_int − p̂_base| on hold items) · "
             "† partial reps (deepseek-v4-flash)",
             color=MUTED, fontsize=7.6, va="bottom", linespacing=1.4)
    out = rdir / "ladder"
    fig.savefig(out.with_suffix(".png"), dpi=200, facecolor=SURFACE)
    fig.savefig(out.with_suffix(".svg"), facecolor=SURFACE)
    print(f"[saved] {out}.png / .svg")


if __name__ == "__main__":
    main()
