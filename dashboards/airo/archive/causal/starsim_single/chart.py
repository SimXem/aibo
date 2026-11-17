"""ECI vs share-of-recoverable-CRPS, baseline (A) and intervention (B), single-region design.

  uv run python results/causal/starsim_single/chart.py [--pilot] [--tag T] [--allow-partial]   # -> results/eci_vs_recovered[suffix].{png,svg,csv}
"""
import argparse
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

FLOOR = -1.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--results-dir", default=str(HERE / "results"))
    ap.add_argument("--worlds", default=str(HERE / "worlds.json"))
    ap.add_argument("--allow-partial", action="store_true")
    a = ap.parse_args()
    suffix = "_pilot" if a.pilot else (f"_{a.tag}" if a.tag else "")
    rdir = Path(a.results_dir)
    summary = json.load(open(rdir / f"scores_summary{suffix}.json"))["models"]
    design = json.load(open(a.worlds)); d = design["design"]; n_items = len(design["items"])
    by_id = {m.openrouter_id: m for m in load_roster()}
    rows = [(by_id[mid], t["baseline_recovered"], t["intervention_recovered"], t["n_resp_base"] + t["n_resp_int"])
            for mid, t in summary.items()
            if (t["complete"] or a.allow_partial) and t.get("baseline_recovered") is not None
            and t.get("intervention_recovered") is not None]
    skipped = [mid for mid in summary if mid not in {m.openrouter_id for m, *_ in rows}]
    if skipped:
        print("not plotted (incomplete):", ", ".join(skipped))
    K = round(max(r[3] for r in rows) / (2 * n_items)) if rows else 0
    eci = np.array([r[0].eci for r in rows])
    cov = f"{int(d['vax']['coverage']*100)}% coverage, {int(d['vax']['efficacy']*100)}% efficacy, day {d['vax']['day']}"
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.2), facecolor=SURFACE)
    specs = [(axes[0], 1, f"A. Baseline: forecasting new infections after day 20 ({n_items} items)",
              "CRPS skill score vs climatology  ·  1 − (CRPS − CRPS_oracle) / (CRPS_ref − CRPS_oracle)\n"
              "1 = matches the simulator's distribution  ·  0 = climatology (all worlds × coverages 0–90% pooled)  ·  < 0 = worse"),
             (axes[1], 2, f"B. Intervention: the same forecast given the vaccine ({n_items} items)",
              f"vaccine: {cov}\n"
              "same score and reference, against the vaccinated arm's distribution  ·  separate prompts")]
    ymin = 0.0
    for ax, idx, title, sub in specs:
        ys = np.array([r[idx] for r in rows]); names = [short_name(r[0]) for r in rows]
        off = ys < FLOOR
        names = [f"{n} ({y:+.2f}, below axis)" if o else n for n, y, o in zip(names, ys, off)]
        ys = np.where(off, FLOOR + 0.06, ys)
        panel(ax, eci, ys, ys, ys, names, title, sub, "")
        ax.texts[-1].set_position((0.99, 0.12))
        ymin = min(ymin, ys.min()); ax._labels = (eci, ys, names)
    lo_lim = max(np.floor((ymin - 0.05) * 4) / 4, FLOOR)
    rug = {ax: (ax._labels[1] >= RUG_BAND).sum() >= RUG_MIN for ax in axes}
    top = 1.05 + 0.31 * (1.05 - lo_lim) / 1.05 if any(rug.values()) else 1.22
    for ax in axes:
        ax.set_ylim(lo_lim, top); ax.set_xlim(127, 166)
        ax.set_yticks(np.arange(lo_lim, 1.01, 0.5 if lo_lim <= -0.5 else 0.25))
    axes[0].set_ylabel("share of recoverable CRPS", color=INK2)
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
             f"StarSim single-region bench · {len(rows)} models via OpenRouter, vendor-default sampling, K = {K} reps, per-quantile medians · "
             f"one SIR population of {d['n_agents']:,}, parameters stated, report through day 20 · "
             f"forecast = p10/p25/p50/p75/p90 of new infections by day 40 and day 60, 4 worlds (R0 1.8–3.9)\n"
             "truth: distribution over simulator seeds matching the shown day-20 count (±15%)",
             color=MUTED, fontsize=7.6, va="bottom", linespacing=1.4)
    out = rdir / f"eci_vs_recovered{suffix}"
    fig.savefig(out.with_suffix(".png"), dpi=200, facecolor=SURFACE); fig.savefig(out.with_suffix(".svg"), facecolor=SURFACE)
    with open(out.with_suffix(".csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["model", "name", "eci", "baseline_recovered", "intervention_recovered"])
        for m, b, i, _ in rows:
            w.writerow([m.openrouter_id, short_name(m), m.eci, f"{b:.4f}", f"{i:.4f}"])
    print(f"[saved] {out}.png / .svg / .csv")


if __name__ == "__main__":
    main()
