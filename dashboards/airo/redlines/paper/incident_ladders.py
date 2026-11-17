"""Stacked incident-severity panels, one column per ladder (deaths, damages).

Uses the dashboard's graph2_data.json medians; stacking horizons leaves
enough horizontal room for every rung label at paper size.
"""
from __future__ import annotations

from . import style
from .dates import month_year
from .style import FULL_W, INK


def render(blob: dict):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, NullFormatter

    horizons = ("2030", "2050", "2100")
    legs = blob["legs"]
    fig, axes = plt.subplots(3, len(legs), figsize=(FULL_W, 5.4), sharex="col", sharey=True,
                             squeeze=False)
    fig.subplots_adjust(left=0.09, right=0.98, top=0.87, bottom=0.17, hspace=0.28, wspace=0.08)
    causes = ("cyber", "misalign", "bio")
    names = {"cyber": "Cyber", "misalign": "Misalignment", "bio": "Human-caused epidemic"}
    patterns = {"cyber": "-", "misalign": "--", "bio": ":"}
    dollar = r"\textdollar{}" if style.backend() == "pgf" else "$"
    values = []
    for j, leg in enumerate(legs):
        # The rungs every plotted cause answered at every horizon on this ladder:
        # the extinction rung (2026-09-16) is absent from runs before it and
        # never plotted then, and absent from the damages ladder altogether.
        answered = set.intersection(*[
            {r["rung"] for c in blob["byHorizon"][h]["legs"][leg["key"]]["causes"]
             if c["key"] == cause for r in c["rungs"]}
            for h in horizons for cause in causes])
        rungs = [r for r in leg["rungs"] if r["rung"] in answered]
        xs = list(range(len(rungs)))
        for i, horizon in enumerate(horizons):
            ax = axes[i][j]
            cells = {c["key"]: c for c in blob["byHorizon"][horizon]["legs"][leg["key"]]["causes"]}
            for cause in causes:
                cell = cells[cause]
                medians = {r["rung"]: r["median"] for r in cell["rungs"]}
                ys = [medians[r["rung"]] for r in rungs]
                if any(y is None or y <= 0 for y in ys):
                    raise ValueError("Incident ladder log plot needs complete positive medians; "
                                     "zero probabilities require an explicit treatment.")
                values.extend(ys)
                ax.plot(xs, ys, marker="o", markersize=2.5, linestyle=patterns[cause],
                        color=cell["color"], label=names[cause])
            ax.set_yscale("log")
            windows = (blob.get("instrumentInfo", {}).get("countingWindows", {}).get(horizon) or [])
            title = f"{leg['label']} · by {horizon}"
            if windows:
                title += " · onsets " + "; ".join(
                    f"{month_year(w['start'])} to {month_year(w['end'])}" for w in windows)
            ax.set_title(title, fontsize=8, color=INK, pad=3)
            ax.grid(True, axis="y")
            ax.set_axisbelow(True)
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: style.esc(f"{v:g}%")))
            ax.yaxis.set_minor_formatter(NullFormatter())
        axes[-1][j].set_xticks(xs)
        # The blob's own short labels, including units; the extinction rung reads as such.
        axes[-1][j].set_xticklabels([
            style.esc("Extinction" if r["rung"] == "extinction" else r["short"]).replace("$", dollar)
            for r in rungs])
        axes[-1][j].set_xlabel(leg["label"] + (" (2026 dollars)" if leg["unit"] == "usd" else ""),
                               labelpad=7)
    axes[0][0].set_ylim(min(values) / 1.5, 150)
    fig.text(0.015, 0.55, "Probability of reaching the threshold (log scale)",
             rotation=90, ha="center", va="center", fontsize=8, color=INK)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, bbox_to_anchor=(0.54, 1.0))
    fig.text(0.54, 0.94, f"Median of {len(blob['models'])} models. Cumulative incidents; harm within 3 years after onset.",
             ha="center", fontsize=7, color=INK)
    return fig
