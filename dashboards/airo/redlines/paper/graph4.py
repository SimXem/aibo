"""Paper Figure: tail skill vs. capability (Graph 4), from results/graph4_combined.json.

What is drawn is what the blob carries: every model's two-simulator Brier
skill score against the base-rate forecaster, on the ECI axis. Unlike the
dashboard (which since 2026-08-27 plots the clean subset and footnotes the
rest), the paper draws the full set and marks the excluded model hollow, so
both rho values on the panel refer to points the reader can see. Models scored
on one simulator only are drawn as triangles.

Labels: the ladder is sparse below ECI ~145 and dense above it (eight models
in 147-161). Sparse points are labelled beside the dot; the dense cluster is
listed in a gutter to the right of the axes, ordered by skill, each name
joined to its dot by a leader line. This is deterministic and cannot collide,
which the greedy placement the dashboard uses could not promise once the
figure is typeset in a wider face than the page's.
"""
from __future__ import annotations

from . import style
from .style import COL_W, INK, INK_FAINT, INK_SOFT, WARN

LABEL_PT = 5.8        # label font size
GUTTER_PT = 7.6       # minimum vertical spacing between gutter labels
CLUSTER_SPAN = 12     # models within this many ECI points of the top are "the cluster"
NEAR_SPAN = 4         # sparse models this close to the cluster are labelled on their left


def render(blob: dict):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    pts = sorted(blob["scatter"], key=lambda p: p["eci"])
    sims = {m["label"]: m["sims"] for m in blob["models"]}
    eci_min, eci_max = min(p["eci"] for p in pts), max(p["eci"] for p in pts)

    fig, ax = plt.subplots(figsize=(COL_W, 3.0))
    fig.subplots_adjust(bottom=0.2, right=0.98)
    ax.axhline(0, color=WARN, lw=0.8, zorder=1)
    ax.text(eci_min - 1.5, 0.12, "base-rate forecaster", color=WARN, fontsize=6.5,
            va="bottom", ha="left")

    kinds = {}
    for p in pts:
        excluded = p.get("excluded", False)
        one_sim = sims.get(p["label"]) != "civbench+starsim"
        if excluded:
            kw = dict(marker="o", facecolor="white", edgecolor=INK_SOFT, linewidth=0.9)
            kinds["excluded"] = kw
        elif one_sim:
            kw = dict(marker="^", facecolor=INK_SOFT, edgecolor=INK_SOFT, linewidth=0.6)
            kinds["one_sim"] = kw
        else:
            kw = dict(marker="o", facecolor=INK, edgecolor=INK, linewidth=0.6)
            kinds["both"] = kw
        ax.scatter([p["eci"]], [p["bss"]], s=22, zorder=3, **kw)

    ax.set_xlabel("Epoch Capabilities Index")
    ax.set_ylabel("Brier skill vs. base rate")
    # The right-hand 30% of the axis is the label gutter; ticks stop at the data.
    ax.set_xlim(eci_min - 3, eci_max + 16)
    ax.set_xticks([t for t in range(110, eci_max + 1, 10) if t >= eci_min - 3])
    ymin = min(min(p["bss"] for p in pts), 0)
    ax.set_ylim(ymin - 0.6, 0.9)
    ax.grid(True, axis="y")
    ax.set_axisbelow(True)
    ax.xaxis.label.set_ha("center")
    ax.xaxis.set_label_coords(0.36, -0.12)

    _label(ax, pts, eci_max)

    n, rho = blob["nModels"], blob["rho"]
    n_c, rho_c = blob.get("nModelsClean"), blob.get("rhoClean")
    lines = [rf"Spearman $\rho = {rho:+.2f}$ ($n={n}$)"]
    if rho_c is not None and n_c != n:
        lines.append(rf"$\rho = {rho_c:+.2f}$ excluding MoE ($n={n_c}$)")
    # Bottom-right corner is empty on every ladder we have drawn: the weakest
    # models sit at the far left and the gutter's leaders end well above it.
    ax.text(0.98, 0.15, "\n".join(lines), transform=ax.transAxes, fontsize=6.5,
            color=INK_SOFT, va="bottom", ha="right")

    handles, labels = [], []
    if "both" in kinds:
        handles.append(Line2D([], [], ls="", marker="o", ms=4.5, mfc=INK, mec=INK)); labels.append("both simulators")
    if "one_sim" in kinds:
        handles.append(Line2D([], [], ls="", marker="^", ms=4.5, mfc=INK_SOFT, mec=INK_SOFT)); labels.append("civilization world only")
    if "excluded" in kinds:
        handles.append(Line2D([], [], ls="", marker="o", ms=4.5, mfc="white", mec=INK_SOFT)); labels.append("excluded from trend (MoE)")
    fig.legend(handles, labels, loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.01),
               handletextpad=0.3, columnspacing=1.0, borderaxespad=0)
    return fig


def _label(ax, pts, eci_max):
    fig = ax.figure
    cluster = [p for p in pts if p["eci"] >= eci_max - CLUSTER_SPAN]
    sparse = [p for p in pts if p["eci"] < eci_max - CLUSTER_SPAN]

    cluster_lo = min(p["eci"] for p in cluster) if cluster else eci_max
    for p in sparse:
        left = p["eci"] >= cluster_lo - NEAR_SPAN     # would run into the cluster's dots
        ax.annotate(p["label"], (p["eci"], p["bss"]), xytext=(-5 if left else 5, 0),
                    textcoords="offset points", ha="right" if left else "left", va="center",
                    fontsize=LABEL_PT, color=INK_SOFT if p.get("excluded") else INK, zorder=4)

    # Gutter: one row per cluster model, ordered by skill, pushed apart to a
    # minimum spacing measured in points and converted to data units.
    axes_h_pt = ax.get_position().height * fig.get_figheight() * 72
    y0, y1 = ax.get_ylim()
    gap = GUTTER_PT * (y1 - y0) / axes_h_pt
    col_x = eci_max + 2.5
    ordered = sorted(cluster, key=lambda p: -p["bss"])
    ys = []
    for p in ordered:
        y = p["bss"]
        if ys and y > ys[-1] - gap:
            y = ys[-1] - gap
        ys.append(y)
    # keep the column inside the axes
    top_limit = y1 - gap * 0.6
    if ys and ys[0] > top_limit:
        shift = ys[0] - top_limit
        ys = [y - shift for y in ys]
    for p, y in zip(ordered, ys):
        ax.annotate(p["label"], (p["eci"], p["bss"]), xytext=(col_x, y), textcoords="data",
                    ha="left", va="center", fontsize=LABEL_PT,
                    color=INK_SOFT if p.get("excluded") else INK, zorder=4,
                    arrowprops=dict(arrowstyle="-", color=INK_FAINT, lw=0.4, shrinkA=2.5, shrinkB=1.5))
