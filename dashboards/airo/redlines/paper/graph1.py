"""Paper Figure: the headline forecasts by horizon (Graph 1), from
results/graph1_data.json.

One panel per probability question on the rail (the expected-loss rows are
left to Graph 2's axis). Per panel: each model's forecast as a coloured dot
(registry colours, carried in the blob), the ensemble median as a black
marker, and prior human panels as
hollow diamonds -- a dated reference, not a like-for-like overlay, exactly
as the dashboard labels them.
"""
from __future__ import annotations

from . import style
from .dates import format_dates, month_year
from .style import FULL_W, INK, INK_FAINT, INK_SOFT


def render(blob: dict, kinds: tuple[str, ...] = ("probability",)):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FuncFormatter, NullFormatter

    qs = [q for q in blob["questions"] if q["valueKind"] in kinds]
    n = len(qs)
    fig, axes = plt.subplots(1, n, figsize=(FULL_W, 3.0), sharey=True)
    if n == 1:
        axes = [axes]

    seen_models, seen_human = {}, {}
    horizon_notes = {}
    jitter = {}
    for ax, q in zip(axes, qs):
        hs = q["horizons"]
        xs = {h: i for i, h in enumerate(hs)}
        # models: small dots, slightly spread so five colours at one horizon stay legible
        k = len(q["series"])
        for j, s in enumerate(q["series"]):
            off = (j - (k - 1) / 2) * 0.09
            jitter[s["label"]] = off
            seen_models.setdefault(s["label"], s["color"])
            for h in hs:
                v = s["ps"].get(h)
                if v is None or v <= 0:
                    continue
                ax.scatter([xs[h] + off], [v], s=9, color=s["color"], alpha=0.9, zorder=3, linewidths=0)
        # ensemble median. No interval: since 2026-09-02 the instrument is
        # elicited once per run, so there is no re-elicitation noise to draw.
        for h in hs:
            m = q["median"].get(h)
            if m is None:
                continue
            ax.scatter([xs[h]], [m], s=26, marker="_", color=INK, lw=1.4, zorder=5)
            ax.scatter([xs[h]], [m], s=18, marker="o", facecolor="white", edgecolor=INK, lw=0.9, zorder=5)
        # humans: hollow diamonds
        for hm in q.get("human") or []:
            key = f"{hm['panel']} {month_year(hm['date'])}"
            seen_human.setdefault(key, hm["color"])
            for h in hs:
                v = hm["ps"].get(h)
                if v is None or v <= 0:
                    continue
                ax.scatter([xs[h]], [v], s=22, marker="D", facecolor="white", edgecolor=hm["color"],
                           lw=1.0, zorder=6)
        ax.set_yscale("log")
        ax.set_xticks(list(xs.values()))
        labels = q.get("horizonLabels") or {}
        labels = labels if isinstance(labels, dict) else {}
        tick_labels = []
        for h in hs:
            label = format_dates(labels.get(h, h))
            if h.endswith("mo") and h[:-2].isdigit():
                tick_labels.append(f"{h[:-2]}\nmo")
                if label != h:
                    horizon_notes.setdefault(label, None)
            else:
                tick_labels.append(label.replace("by ", "by\n", 1))
        ax.set_xticklabels(tick_labels)
        ax.set_xlim(-0.5, len(hs) - 0.5)
        ax.set_title(q["short"], fontsize=8, color=INK, pad=4)
        ax.grid(True, axis="y")
        ax.set_axisbelow(True)
        ax.tick_params(axis="x", length=0)

    ax0 = axes[0]
    ax0.yaxis.set_major_formatter(FuncFormatter(lambda v, _: style.esc(_pct(v))))
    ax0.yaxis.set_minor_formatter(NullFormatter())
    ax0.set_ylabel("Probability (log scale)")
    lo = min(v for q in qs for s in q["series"] for v in s["ps"].values() if v and v > 0)
    hi = max(max(v for q in qs for s in q["series"] for v in s["ps"].values() if v),
             max((v for q in qs for hm in q.get("human") or [] for v in hm["ps"].values() if v), default=0))
    ax0.set_ylim(lo / 1.8, hi * 1.8)

    handles = [Line2D([], [], ls="", marker="o", ms=3.2, color=c, label=l) for l, c in seen_models.items()]
    handles.append(Line2D([], [], ls="-", marker="o", ms=4, mfc="white", mec=INK, color=INK,
                          label="ensemble median"))
    for l, c in seen_human.items():
        handles.append(Line2D([], [], ls="", marker="D", ms=4, mfc="white", mec=c, label=f"superforecasters, {l}"))
    if horizon_notes:
        fig.text(0.5, 0.20, style.esc("; ".join(horizon_notes)), ha="center", va="center",
                 fontsize=7, color=INK_SOFT)
    fig.legend(handles=handles, loc="lower center", ncol=min(len(handles), 4), bbox_to_anchor=(0.5, 0.01),
               handletextpad=0.3, columnspacing=1.2, borderaxespad=0)
    fig.subplots_adjust(left=0.10, right=0.99, bottom=0.36, top=0.91, wspace=0.16)
    return fig


def _pct(v: float) -> str:
    if v >= 10:
        return f"{v:.0f}%"
    if v >= 1:
        return f"{v:.0f}%" if float(v).is_integer() else f"{v:g}%"
    return f"{v:g}%"
