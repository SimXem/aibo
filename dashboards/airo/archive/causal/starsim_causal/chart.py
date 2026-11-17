"""ECI vs share-of-recoverable-score, one point per model, two panels (v2 bench).

  A  baseline       recovered = 1 - Σ(p̂-P*)² / Σ(½-P*)²   (Brier skill vs the certified P*)
  B  intervention   effect_recovered = mean (p̂_int − p̂_base) / Δ_do  (share of the causal effect)
Both: 1 = ceiling, 0 = uninformed / ignores the intervention, < 0 = wrong way.
Reads results/scores_summary[_pilot].json (run score.py first). Point only: the
score is descriptive on this fixed item set, so no interval is drawn.

Usage:
  uv run python results/causal/starsim_causal/chart.py            # -> results/eci_vs_recovered.{png,svg,csv}
  uv run python results/causal/starsim_causal/chart.py --pilot
"""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from models import load_roster  # noqa: E402

HERE = Path(__file__).resolve().parent

# dataviz reference palette, light mode (single series -> slot 1 blue; validated)
SURFACE, INK, INK2, MUTED, GRID, AXIS, SERIES = (
    "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#2a78d6")
plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 10, "axes.titlesize": 11.5, "axes.labelsize": 10,
    "xtick.labelsize": 9, "ytick.labelsize": 9, "svg.fonttype": "none",
})


def short_name(m) -> str:
    n = m.name.split(": ")[-1]
    for junk in (" Preview", " 0731", " A22B"):
        n = n.replace(junk, "")
    return n


def _overlap_push(a: Bbox, b: Bbox) -> np.ndarray:
    """Vector that moves box a off box b along the axis of least overlap."""
    ox = min(a.x1, b.x1) - max(a.x0, b.x0)
    oy = min(a.y1, b.y1) - max(a.y0, b.y0)
    if ox <= 0 or oy <= 0:
        return np.zeros(2)
    ca = np.array([(a.x0 + a.x1) / 2, (a.y0 + a.y1) / 2])
    cb = np.array([(b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2])
    d = ca - cb
    if oy < ox:
        return np.array([0.0, np.sign(d[1]) * oy if d[1] else oy])
    return np.array([np.sign(d[0]) * ox if d[0] else ox, 0.0])


def place_labels(ax, fig, xs, ys, names):
    """Iterative repulsion with a home spring: labels push off each other,
    off every marker (foreign markers get a wide berth), and off the axes
    edge, while being pulled back toward a spot beside their own point. A
    leader line is drawn whenever the label is not adjacent to its own point
    or another point is at least as close to it as its own."""
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    px_per_pt = fig.dpi / 72
    axbb = ax.get_window_extent(rend)
    pts = ax.transData.transform(np.c_[xs, ys])
    n = len(xs)
    home = np.zeros((n, 2))
    for rank, i in enumerate(np.argsort(pts[:, 0])):       # alternate above/below by x-rank;
        home[i] = (8, 7 if rank % 2 == 0 else -7)           # below when close under a label rug
        if ys[i] >= 0.8:
            home[i] = (8, -9)
    off = home.copy()
    texts = [ax.annotate(names[i], (xs[i], ys[i]), xytext=tuple(off[i]), textcoords="offset points",
                         fontsize=8, color=INK2, ha="left", va="center", zorder=5) for i in range(n)]
    own = [Bbox.from_bounds(px - 9, py - 9, 18, 18) for px, py in pts]
    foreign = [Bbox.from_bounds(px - 16, py - 12, 32, 24) for px, py in pts]
    for _ in range(600):
        bbs = [t.get_window_extent(rend).padded(4) for t in texts]
        moved = False
        for i in range(n):
            push = np.zeros(2)
            for j in range(n):
                if j != i:
                    push += _overlap_push(bbs[i], bbs[j]) * 0.5
                    push += _overlap_push(bbs[i], foreign[j]) * 0.8
            push += _overlap_push(bbs[i], own[i])
            push[0] += min(0, axbb.x1 - bbs[i].x1) + max(0, axbb.x0 - bbs[i].x0)
            push[1] += min(0, axbb.y1 - bbs[i].y1) + max(0, axbb.y0 - bbs[i].y0)
            push += (home[i] - off[i]) * px_per_pt * 0.04          # weak spring home
            if np.abs(push).max() > 0.3:
                off[i] += push / px_per_pt * 0.7
                texts[i].xyann = tuple(off[i])
                moved = True
        if not moved:
            break
    for i, t in enumerate(texts):
        bb = t.get_window_extent(rend)
        c = np.array([(bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2])
        # nearest label-edge point to its own marker
        edge = np.array([min(max(pts[i, 0], bb.x0), bb.x1), min(max(pts[i, 1], bb.y0), bb.y1)])
        d_own = np.hypot(*(edge - pts[i]))
        d_other = min((np.hypot(*(np.array([min(max(px, bb.x0), bb.x1), min(max(py, bb.y0), bb.y1)]) - (px, py)))
                       for j, (px, py) in enumerate(pts) if j != i), default=np.inf)
        if d_own > 12 or d_other <= d_own + 6:
            t.remove()
            texts[i] = ax.annotate(names[i], (xs[i], ys[i]), xytext=tuple(off[i]), textcoords="offset points",
                                   fontsize=8, color=INK2, ha="left", va="center", zorder=5,
                                   arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7, shrinkA=1, shrinkB=5))


RUG_BAND = 0.95   # points at/above this share a label rug when there are many of them
RUG_MIN = 6


def place_rug(ax, fig, xs, ys, names, y_text):
    """Names of ceiling-band points in one row above the line, sorted by x with
    even spacing, rotated 45°, each with a straight leader. Sorted slots ↔ sorted
    points means leaders never cross."""
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    axbb = ax.get_window_extent(rend)
    order = np.argsort(xs)
    pts = ax.transData.transform(np.c_[xs, ys])
    step = 14 * fig.dpi / 72                                 # px between slots
    n = len(xs)
    centre = np.clip(pts[:, 0].mean(), axbb.x0 + 20 + step * n / 2, axbb.x1 - 40 - step * n / 2)
    slots = centre + (np.arange(n) - (n - 1) / 2) * step
    y_px = ax.transData.transform((0, y_text))[1]
    inv = ax.transData.inverted()
    for slot, i in zip(slots, order):
        xt, yt = inv.transform((slot, y_px))
        ax.annotate(names[i], (xs[i], ys[i]), xytext=(xt, yt), textcoords="data", fontsize=8, color=INK2,
                    ha="left", va="bottom", rotation=45, rotation_mode="anchor", zorder=5,
                    arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7, shrinkA=0, shrinkB=5))


def panel(ax, xs, ys, los, his, names, title, subtitle, zero_label):
    ax.set_facecolor(SURFACE)
    ax.axhline(1.0, color=MUTED, lw=1, zorder=1)
    ax.axhline(0.0, color=AXIS, lw=1, zorder=1)
    if np.any(his - los > 0):
        ax.errorbar(xs, ys, yerr=[ys - los, his - ys], fmt="none", ecolor=SERIES, elinewidth=1, alpha=0.45, zorder=2)
    ax.scatter(xs, ys, s=56, color=SERIES, edgecolor=SURFACE, linewidth=2, zorder=4)  # 2px surface ring
    ax.set_title(title, loc="left", color=INK, fontweight="bold", pad=38)
    ax.text(0, 1.012, subtitle, transform=ax.transAxes, color=INK2, fontsize=8.4, va="bottom", linespacing=1.35)
    ax.grid(axis="y", color=GRID, lw=1, zorder=0)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(AXIS)
    ax.tick_params(colors=MUTED, length=3, color=AXIS)
    for lab in ax.get_xticklabels() + ax.get_yticklabels():
        lab.set_color(INK2)
    ax.set_xlabel("Epoch Capabilities Index (ECI)", color=INK2)
    rho, p = spearmanr(xs, ys)
    ax.text(0.99, 0.03, f"Spearman ρ = {rho:+.2f}   n = {len(xs)}", transform=ax.transAxes,
            ha="right", va="bottom", color=INK2, fontsize=8.6)
    return zero_label


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--results-dir", default=str(HERE / "results"))
    ap.add_argument("--out", default=None, help="basename (no extension); default results/eci_vs_recovered[_pilot]")
    ap.add_argument("--allow-partial", action="store_true", help="plot models with incomplete items (pilot previews)")
    ap.add_argument("--worlds", default=str(HERE / "worlds.json"))
    ap.add_argument("--tag", default=None, help="v3 rung tag: reads scores_summary_<tag>.json, writes eci_vs_recovered_<tag>")
    a = ap.parse_args()
    suffix = "_pilot" if a.pilot else (f"_{a.tag}" if a.tag else "")
    rdir = Path(a.results_dir)
    out = Path(a.out) if a.out else rdir / f"eci_vs_recovered{suffix}"
    summary = json.load(open(rdir / f"scores_summary{suffix}.json"))["models"]
    design = json.load(open(a.worlds))
    n_items = len(design["items"])
    any_noflip = any(it["delta_do"] == 0 for it in design["items"])
    rung = design["design"].get("rung")
    by_id = {m.openrouter_id: m for m in load_roster()}

    rows = []
    for mid, t in summary.items():
        if not (t["complete"] or a.allow_partial):
            continue
        if t.get("baseline_recovered") is None or t.get("effect_recovered") is None:
            continue
        rows.append((by_id[mid], t["baseline_recovered"], t["effect_recovered"]))
    skipped = [mid for mid in summary if mid not in {m.openrouter_id for m, _, _ in rows}]
    if skipped:
        print("not plotted (incomplete):", ", ".join(skipped))
    K = max([t["n_resp_base"] for t in summary.values()] + [1]) // max(n_items, 1)

    fig, axes = plt.subplots(1, 2, figsize=(15, 7.2), facecolor=SURFACE)
    specs = [
        (axes[0], 1, f"A. Baseline: forecasting the epidemic ({n_items} items)",
         "share of recoverable Brier score  ·  1 − Σ(p̂−P*)² / Σ(½−P*)²\n"
         "1 = ceiling (forecasts the simulator's certified P* exactly)  ·  0 = uninformed (always ½)"),
        (axes[1], 2, f"B. Intervention: share of the certified causal effect recovered ({n_items} items)",
         ("mean 1 − |(p̂_int − p̂_base) − Δdo|, baseline and intervention asked in separate prompts\n"
          "1 = ceiling (moves exactly the certified effect; here Δdo = 0: holds)  ·  0 = flips a non-flipping item"
          if any_noflip else
          "mean (p̂_int − p̂_base) / Δdo, baseline and intervention asked in separate prompts\n"
          "1 = ceiling (full certified flip)  ·  0 = ignores the intervention  ·  < 0 = moves the wrong way")),
    ]
    ymin = 0.0
    for ax, idx, title, subtitle in specs:
        xs = np.array([r[0].eci for r in rows]); ys = np.array([r[idx] for r in rows])
        names = [short_name(r[0]) for r in rows]
        panel(ax, xs, ys, ys, ys, names, title, subtitle, "")
        ymin = min(ymin, ys.min())
        ax._labels = (xs, ys, names, "")
    lo_lim = max(np.floor((ymin - 0.05) * 4) / 4, -1.0)
    rug = {ax: (ax._labels[1] >= RUG_BAND).sum() >= RUG_MIN for ax in axes}
    top = 1.36 if any(rug.values()) else 1.22
    for ax in axes:
        ax.set_ylim(lo_lim, top)
        ax.set_xlim(127, 166)
        ax.set_yticks(np.arange(lo_lim, 1.01, 0.25))
    axes[0].set_ylabel("share of recoverable score", color=INK2)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    for ax in axes:
        xs, ys, names, _ = ax._labels
        if rug[ax]:
            band = ys >= RUG_BAND
            place_rug(ax, fig, xs[band], ys[band], [n for n, b in zip(names, band) if b], y_text=1.05)
            place_labels(ax, fig, xs[~band], ys[~band], [n for n, b in zip(names, band) if not b])
        else:
            place_labels(ax, fig, xs, ys, names)
    d = design["design"]
    if rung:
        covs = rung["coverages"]
        cov_txt = (f"{int(round(rung['global_coverage']*100))}% coverage" if rung.get("global_coverage")
                   else "coverage " + ", ".join(f"{w} {int(round(c*100))}%" for w, c in covs.items()))
        version = f"v3 rung '{rung['tag']}'"
    else:
        cov_txt, version = f"{int(d['vax']['coverage']*100)}% coverage", "v2"
    fig.text(0.01, 0.012,
             f"StarSim causal bench {version} · {len(rows)} models via OpenRouter, vendor-default sampling, K = {K} reps · "
             f"score = mean over items of per-item medians\n2 isolated SIR populations of {d['n_agents']:,}, "
             f"parameters stated · intervention: leader vaccinated day {d['vax']['day']}, "
             f"{cov_txt}, {int(d['vax']['efficacy']*100)}% efficacy · "
             "truth: certified P* given the shown day-20 report",
             color=MUTED, fontsize=7.6, va="bottom", linespacing=1.4)
    fig.savefig(out.with_suffix(".png"), dpi=200, facecolor=SURFACE)
    fig.savefig(out.with_suffix(".svg"), facecolor=SURFACE)
    with open(out.with_suffix(".csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "name", "eci", "fb_overall", "baseline_recovered", "effect_recovered"])
        for m, b, e in rows:
            w.writerow([m.openrouter_id, short_name(m), m.eci, m.fb_overall, f"{b:.4f}", f"{e:.4f}"])
    print(f"[saved] {out}.png / .svg / .csv")


if __name__ == "__main__":
    main()
