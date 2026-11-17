import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

def load(p): return json.load(open(p))
fc = load("results/graph4_data.json")            # curated low-prob FreeCiv subset
pan = load("results/pandemic/graph4_pandemic.json")  # Starsim pandemic

fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.2))
fig.suptitle("Graph 4 — calibration on low-probability, resolved events", fontsize=14, fontweight="bold", y=0.99)

def panel(ax, blob, title, subtitle):
    dm = blob["domainMax"]; base = blob["base"]
    # perfect-calibration diagonal
    ax.plot([0, dm], [0, dm], ls="--", lw=1, color="#9aa7b3", zorder=1)
    ax.text(dm, dm, "  perfect calibration", fontsize=8, color="#9aa7b3",
            ha="left", va="center", rotation=0)
    # base-rate line
    ax.axhline(base, ls=":", lw=1.4, color="#c0392b", zorder=1)
    ax.text(dm*0.99, base, f"base rate {base*100:.1f}% — where rare events land",
            fontsize=8, color="#c0392b", ha="right", va="bottom")
    # model calibration curves, colored by ECI
    for m in blob["models"]:
        xs = [p["pred"] for p in m["pts"]]; ys = [p["obs"] for p in m["pts"]]
        ax.plot(xs, ys, "-o", ms=3.5, lw=1.6, color=m["color"], alpha=0.9, zorder=3)
    ax.set_xlim(0, dm); ax.set_ylim(0, dm)
    ax.set_xlabel("Forecast probability (decile means)")
    ax.set_ylabel("Observed frequency")
    ax.set_title(title, fontsize=12, fontweight="bold", loc="left", pad=18)
    ax.text(0, 1.015, subtitle, transform=ax.transAxes, fontsize=8.5, color="#555")
    ax.set_aspect("equal")
    ax.grid(alpha=0.15)
    # ECI legend (low->high)
    ms = sorted(blob["models"], key=lambda m: m["eci"])
    handles = [Line2D([0],[0], color=m["color"], lw=2.4,
               label=f"{m['label']} (ECI {m['eci']})") for m in ms]
    ax.legend(handles=handles, fontsize=6.8, loc="upper left", framealpha=0.9,
              handlelength=1.4, borderpad=0.4, labelspacing=0.25)

panel(axes[0], fc, "A · Curated low-prob CivBench (FreeCiv)",
      f"{fc['nModels']} models · {fc['nQuestions']:,} resolved tail events · base rates 1–9%")
panel(axes[1], pan, "B · Starsim pandemic sim",
      f"{pan['nModels']} models · {pan['nQuestions']:,} resolved tail events · deaths thresholds, base rates 1–5%")

fig.text(0.5, 0.005,
         "Curves above the diagonal = over-forecasting the tail. Dots hug the base-rate line while forecasts run right = overconfidence.",
         ha="center", fontsize=8.5, color="#444")
fig.tight_layout(rect=[0, 0.02, 1, 0.97])
fig.savefig("results/graph4_panels.png", dpi=130)
print("wrote results/graph4_panels.png")
