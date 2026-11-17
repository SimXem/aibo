"""Paper Figure: calibration & resolution on ForecastBench (Graph 3), from
results/graph3_data.json.

Same two series the dashboard draws -- the model makers' retrieval systems
on our base models, and the 2024 superforecaster round -- as each
forecaster's own deciles, with the blob's 95% Wilson intervals on observed
frequency. The bare (zero-shot) series can be added, muted, for context.
Brier, resolution and n are not drawn; they are \rl{g3:*} macros for the caption.
"""
from __future__ import annotations

from . import style
from .style import COL_W, DASH, INK_FAINT, SUPER

SERIES = [
    ("tools", "Our models + retrieval", DASH, False),
    ("sup", "Superforecasters (2024)", SUPER, False),
]
BARE = ("bare", "Our models, no retrieval", INK_FAINT, True)


def render(blob: dict, include_bare: bool = False):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    series = list(SERIES) + ([BARE] if include_bare else [])
    fig, ax = plt.subplots(figsize=(COL_W, COL_W * 0.92))
    ax.plot([0, 1], [0, 1], ls=(0, (3, 3)), lw=0.7, color=INK_FAINT, zorder=1)
    # Under the diagonal in its upper half: both curves sit above it there.
    ax.text(0.79, 0.755, "perfect calibration", fontsize=6.5, color=INK_FAINT,
            ha="center", va="top", rotation=45, rotation_mode="anchor",
            transform=ax.transData)

    for key, label, color, muted in series:
        s = blob[key]
        pts = s["pts"]
        xs = [p["pred"] for p in pts]
        ys = [p["obs"] for p in pts]
        for p in pts:
            if p.get("lo95") is not None:
                ax.plot([p["pred"], p["pred"]], [p["lo95"], p["hi95"]], color=color,
                        lw=1.0, alpha=0.35 if not muted else 0.25, solid_capstyle="round", zorder=2)
        ax.plot(xs, ys, color=color, lw=1.3 if not muted else 1.0,
                ls="-" if not muted else (0, (4, 3)), alpha=0.85 if not muted else 0.5, zorder=3)
        ax.scatter(xs, ys, s=14 if not muted else 8, color=color,
                   alpha=1 if not muted else 0.6, zorder=4, label=label)

    pct = FuncFormatter(lambda v, _: style.esc(f"{v * 100:.0f}%"))
    ax.xaxis.set_major_formatter(pct)
    ax.yaxis.set_major_formatter(pct)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_aspect("equal")
    ax.set_xlabel("Forecast probability (decile means)")
    ax.set_ylabel("Observed frequency")
    ax.grid(True)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", handletextpad=0.3, borderaxespad=0.2, markerscale=1.2)
    return fig
