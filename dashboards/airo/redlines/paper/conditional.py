"""Paper Figure: what each LEAP Wave 12 policy does to a forecast (the
Conditional-on tab), from results/conditional_data.json.

One panel per horizon the tab offers (2030, 2050). Rows are the scenarios
in the blob's order. Per row: the ensemble median ratio (conditional /
unconditional) as a bar from 1x and each model's own ratio as a coloured
dot. No intervals: since 2026-09-02 the instrument is elicited once per
run, so there is no re-elicitation noise to draw and the blob's `ci` /
`baselineCi` fields (present only on the repeated pilot) are ignored.
"""
from __future__ import annotations

from . import style
from .style import FULL_W, INK, INK_SOFT

# Short row labels for the figure. The blob's labels are the survey's full
# phrasings ("Status quo (no new substantial AI policy)"); ids are LEAP's.
SHORT = {
    "sq": "Status quo (no new policy)",
    "p1": "P1 Federal preemption",
    "p2a": "P2a Compute cap, US",
    "p2b": "P2b Compute cap, US + China",
    "p3a": "P3a Pre-release authorization, US",
    "p3b": "P3b Pre-release authorization, intl.",
    "p4": "P4 Strict liability",
    "p5": "P5 Bundle (P2b + P3b + P4)",
}


def render(blob: dict, question_id: str = "catastrophe:ai", short: dict | None = None,
           horizons: tuple[str, ...] = ("2030", "2050")):
    """`short` maps scenario id -> row label (default: the LEAP policies')."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

    q = next(q for q in blob["questions"] if q["id"] == question_id)
    horizons = [h for h in horizons if h in q["byHorizon"]]
    fig, axes = plt.subplots(1, len(horizons), figsize=(FULL_W, 3.0), sharey=True)
    if len(horizons) == 1:
        axes = [axes]

    models = {}
    for ax, h in zip(axes, horizons):
        cell = q["byHorizon"][h]
        bars = cell["bars"]
        ys = list(range(len(bars)))[::-1]
        ax.axvline(1, color=INK_SOFT, lw=0.8, zorder=1)
        for y, b in zip(ys, bars):
            r = b.get("ratio")
            if r is None:
                continue
            ax.plot([1, r], [y, y], color=INK, lw=3.2, solid_capstyle="butt", zorder=2, alpha=0.85)
            for m in b.get("models", []):
                if m.get("ratio") is None:
                    continue
                models.setdefault(m["label"], m["color"])
                ax.scatter([m["ratio"]], [y + 0.28], s=8, color=m["color"], zorder=4,
                           linewidths=0, alpha=0.95 if m.get("grounded", True) else 0.4)
        ax.set_yticks(ys)
        labels = SHORT if short is None else short
        ax.set_yticklabels([labels.get(b["id"], b["label"]) for b in bars])
        ax.set_xscale("log")
        pts = [b["ratio"] for b in bars if b.get("ratio")] + \
              [m["ratio"] for b in bars for m in b.get("models", []) if m.get("ratio")] + [1.0]
        lo, hi = min(pts), max(pts)
        ax.set_xlim(lo / 1.15, hi * 1.15)
        ticks = [t for t in (0.125, 0.25, 0.5, 1, 2, 4) if lo / 1.15 <= t <= hi * 1.15]
        ax.xaxis.set_major_locator(FixedLocator(ticks))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: rf"{v:g}$\times$"))
        base = cell["baselineMedian"]
        kind = cell.get("valueKind", "probability")
        base_txt = style.esc(f"{base:.2g}%" if base < 1 else f"{base:.1f}%") if kind == "probability" else f"{base:,.0f}"
        ax.set_title(f"by {h}  (unconditional median {base_txt})", fontsize=8, pad=4)
        ax.grid(True, axis="x")
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
        ax.set_ylim(-0.7, len(bars) - 0.3)
        ax.set_xlabel(r"conditional $\div$ unconditional forecast")

    handles = [Line2D([], [], ls="", marker="o", ms=3, color=c, label=l) for l, c in models.items()]
    handles.append(Line2D([], [], color=INK, lw=3, label="ensemble median"))
    fig.legend(handles=handles, loc="lower center", ncol=min(len(handles), 4), bbox_to_anchor=(0.5, -0.02),
               handletextpad=0.3, columnspacing=1.2, borderaxespad=0)
    sev = q.get("severity")
    fig.suptitle(f"{q['short']}" + (f" ({sev})" if isinstance(sev, str) and sev and sev != "not applicable" else ""),
                 fontsize=8.5, color=INK, y=1.0)
    fig.subplots_adjust(bottom=0.3, top=0.86, wspace=0.20, left=0.31, right=0.99)
    return fig
