"""Trial chart: one scoring rule everywhere. Panel A = Brier skill score (vs the
½ forecast, against the simulator's certified P*) on the 8 baseline forecasts;
panel B = the same score on all intervention forecasts pooled across rungs
(8 items at 90% coverage where every answer flips + 8 'hold' items where none
does). No effect metric, no min.

  uv run python results/causal/starsim_causal/chart_pooled.py [--tags hold]   # -> results/eci_vs_recovered_pooled.{png,svg,csv}
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

from chart import (HERE, INK2, MUTED, RUG_BAND, RUG_MIN, SURFACE, panel, place_labels, place_rug, short_name)
from models import load_roster


def bss(pairs):
    pairs = list(pairs)
    return 1 - sum((p - t) ** 2 for p, t in pairs) / sum((0.5 - t) ** 2 for _, t in pairs)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tags", default="hold", help="comma-separated rung tags pooled with the 90% rung")
    ap.add_argument("--results-dir", default=str(HERE / "results"))
    a = ap.parse_args()
    rdir = Path(a.results_dir)
    rungs = [("", HERE / "worlds.json")] + [(f"_{t}", HERE / f"worlds_{t}.json") for t in a.tags.split(",") if t]
    tables = [json.load(open(rdir / f"scores{sfx}.json")) for sfx, _ in rungs]
    truths = [{i["item_id"]: i["truth_int"] for i in json.load(open(w))["items"]} for _, w in rungs]
    covs = [json.load(open(w))["design"] for _, w in rungs]
    by_id = {m.openrouter_id: m for m in load_roster()}

    rows = []
    for mid, t0 in tables[0].items():
        pairs, n_resp = [], 0
        for tab, tr in zip(tables, truths):
            med = (tab.get(mid, {}).get("intervention") or {}).get("per_item", {})
            pairs += [(med[i], tr[i]) for i in tr if i in med]
            n_resp += tab.get(mid, {}).get("n_resp_int", 0)
        n_items = sum(len(tr) for tr in truths)
        if len(pairs) < n_items or not t0["baseline"]:
            print(f"skipped {mid}: {len(pairs)}/{n_items} intervention items")
            continue
        partial = n_resp < 5 * n_items
        rows.append((by_id[mid], t0["baseline"]["recovered"], bss(pairs), partial))
    names = [short_name(m) + (" †" if p else "") for m, _, _, p in rows]
    eci = np.array([m.eci for m, _, _, _ in rows])
    ya = np.array([r[1] for r in rows]); yb = np.array([r[2] for r in rows])

    fig, axes = plt.subplots(1, 2, figsize=(15, 7.2), facecolor=SURFACE)
    n_int = sum(len(tr) for tr in truths)
    rung_txt = "8 at 90% coverage (every answer flips) + 8 at 10–20% coverage (no answer flips)"
    specs = [
        (axes[0], ya, "A. Baseline: forecasting the epidemic (8 items)",
         "Brier skill score vs the ½ forecast, against the simulator's certified P*  ·  1 − Σ(p̂−P*)² / Σ(½−P*)²\n"
         "1 = ceiling (forecasts P* exactly)  ·  0 = uninformed (always ½)  ·  < 0 = confidently wrong"),
        (axes[1], yb, f"B. Intervention: forecasting the epidemic given the vaccine ({n_int} items, 2 rungs)",
         f"the same score on the intervention forecasts, pooled over {rung_txt}\n"
         "1 = ceiling on both rungs  ·  ignoring the vaccine fails the first 8  ·  flipping on any vaccine fails the last 8"),
    ]
    ymin = 0.0
    for ax, ys, title, subtitle in specs:
        panel(ax, eci, ys, ys, ys, names, title, subtitle, "")
        ymin = min(ymin, ys.min())
        ax._labels = (eci, ys, names)
    lo_lim = max(np.floor((ymin - 0.05) * 4) / 4, -1.0)
    rug = {ax: (ax._labels[1] >= RUG_BAND).sum() >= RUG_MIN for ax in axes}
    top = 1.36 if any(rug.values()) else 1.22
    for ax in axes:
        ax.set_ylim(lo_lim, top); ax.set_xlim(127, 166)
        ax.set_yticks(np.arange(lo_lim, 1.01, 0.25))
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
             f"StarSim causal bench v3 · {len(rows)} models via OpenRouter, vendor-default sampling, K = 5 reps, per-item medians · "
             "baseline and intervention asked in separate prompts · same 4 worlds, reports, question and horizons on both rungs; "
             "only the leader's vaccine coverage differs (day 21, 95% leaky efficacy)\n"
             "truth: certified P* given the shown day-20 report · † partial reps (deepseek-v4-flash)",
             color=MUTED, fontsize=7.6, va="bottom", linespacing=1.4)
    out = rdir / "eci_vs_recovered_pooled"
    fig.savefig(out.with_suffix(".png"), dpi=200, facecolor=SURFACE)
    fig.savefig(out.with_suffix(".svg"), facecolor=SURFACE)
    with open(out.with_suffix(".csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["model", "name", "eci", "baseline_recovered", "intervention_recovered_pooled"])
        for (m, b, i, _), n in zip(rows, names):
            w.writerow([m.openrouter_id, n, m.eci, f"{b:.4f}", f"{i:.4f}"])
    from scipy.stats import spearmanr
    print("pooled intervention BSS vs ECI: rho=%+.2f" % spearmanr(eci, yb)[0])
    for (m, b, i, _), n in sorted(zip(rows, names), key=lambda r: -r[0][2]):
        print(f"  {m.eci:6.1f} {n:28s} base {b:6.3f}  int(pooled) {i:6.3f}")
    print(f"[saved] {out}.png / .svg / .csv")


if __name__ == "__main__":
    main()
