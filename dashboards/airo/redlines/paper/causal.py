"""Paper Figure: causal-conditional skill vs. capability, from
results/causal_data.json (redlines.views.causal over the locked StarSim causal
bench under data/causal/; Graph 6 on the dashboard).

One point per model: the share of recoverable CRPS its intervention forecasts
recover, pooled over three vaccine-coverage rungs, against ECI. The models in
our panel (the blob's `inPanel`, from redlines.registry) are drawn in the
accent colour; the rest of the roster in grey. Only the panel models and the
ends of the ladder are labelled -- the point of the figure is the gradient,
not the roster.
"""
from __future__ import annotations

from .style import FULL_W, DASH, INK, INK_FAINT, INK_SOFT, WARN

LABEL_PT = 7


def render(blob: dict):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    pts = sorted(blob["models"], key=lambda p: p["eci"])
    fig, ax = plt.subplots(figsize=(FULL_W, 3.4))
    fig.subplots_adjust(bottom=0.24, right=0.78)
    ax.axhline(0, color=WARN, lw=0.8, zorder=1)
    ax.axhline(1, color=INK_FAINT, lw=0.6, zorder=1)
    ax.text(0.01, 1.0, "simulator's own distribution", color=INK_FAINT, fontsize=6.5,
            va="bottom", ha="left", transform=ax.get_yaxis_transform())
    ax.text(0.01, 0.0, "climatology", color=WARN, fontsize=6.5, va="bottom", ha="left",
            transform=ax.get_yaxis_transform())

    for p in pts:
        ours = p["inPanel"]
        ax.scatter([p["eci"]], [p["recovered"]], s=22 if ours else 14, zorder=3,
                   facecolor=DASH if ours else INK_SOFT, edgecolor=DASH if ours else INK_SOFT, linewidth=0.6)

    # Labels: our models, plus the best, the weakest, and the top of the ladder.
    best = max(pts, key=lambda p: p["recovered"])
    worst = min(pts, key=lambda p: p["recovered"])
    top = max(pts, key=lambda p: p["eci"])
    show = {p["label"]: p for p in pts if p["inPanel"]}
    for p in (best, worst, top):
        show.setdefault(p["label"], p)
    # Give the clustered frontier labels a separate column and leader lines.
    # Fixed vertical separation keeps nearby scores from colliding in print.
    ranked = sorted((p for p in show.values() if p is not worst),
                    key=lambda p: p["recovered"], reverse=True)
    positions = {p["label"]: 0.76 - i * 0.12 for i, p in enumerate(ranked)}
    for label, p in show.items():
        ours = p["inPanel"]
        if p is worst:   # beside the dot: below it is the climatology line
            kw = dict(xytext=(5, 0), textcoords="offset points", ha="left", va="center")
        else:
            kw = dict(xytext=(1.03, positions[label]), textcoords="axes fraction",
                      ha="left", va="center", annotation_clip=False,
                      arrowprops=dict(arrowstyle="-", color=INK_FAINT, lw=0.5))
        ax.annotate(label, (p["eci"], p["recovered"]),
                    fontsize=LABEL_PT, color=DASH if ours else INK, zorder=4, **kw)

    ax.set_xlabel("Epoch Capabilities Index")
    ax.set_ylabel("Share of recoverable CRPS")
    ax.set_ylim(-0.08, 1.12)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.grid(True, axis="y")
    ax.set_axisbelow(True)

    h = blob["headline"]
    # Upper-left is empty on this ladder: the weak models sit low and left.
    ax.text(0.02, 0.84, rf"Spearman $\rho = {h['rho']:+.2f}$ ($n={h['n']}$, $p={h['p']:.4f}$)",
            transform=ax.transAxes, fontsize=6.5, color=INK_SOFT, va="top", ha="left")

    handles = [Line2D([], [], ls="", marker="o", ms=4.5, mfc=DASH, mec=DASH),
               Line2D([], [], ls="", marker="o", ms=3.5, mfc=INK_SOFT, mec=INK_SOFT)]
    fig.legend(handles, ["in our panel", "other models"], loc="lower center", ncol=2,
               bbox_to_anchor=(0.5, 0.01), handletextpad=0.3, columnspacing=1.0, borderaxespad=0)
    return fig
