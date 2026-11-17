import json, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
d=json.load(open("results/graph4_combined.json")); dm=d["domainMax"]; base=d["base"]
fig,ax=plt.subplots(figsize=(7.2,6.4))
ax.plot([0,dm],[0,dm],"--",color="#9aa7b3",lw=1); ax.text(dm,dm,"  perfect calibration",fontsize=8,color="#9aa7b3",va="center")
ax.axhline(base,ls=":",lw=1.4,color="#c0392b"); ax.text(dm*0.99,base,f"base rate {base*100:.1f}% — where rare events land",fontsize=8,color="#c0392b",ha="right",va="bottom")
for m in sorted(d["models"],key=lambda m:m["eci"]):
    xs=[p["pred"] for p in m["pts"]]; ys=[p["obs"] for p in m["pts"]]
    ax.plot(xs,ys,"-o",ms=3.5,lw=1.6,color=m["color"],alpha=0.9,label=f"{m['label']} (ECI {m['eci']})")
ax.set_xlim(0,dm); ax.set_ylim(0,dm); ax.set_aspect("equal"); ax.grid(alpha=0.15)
ax.set_xlabel("Forecast probability (decile means)"); ax.set_ylabel("Observed frequency")
ax.set_title("Graph 4 (Jason's calibration format) — two-sim average\nCivBench tail + Starsim pandemic, weighted equally",fontsize=10)
ax.legend(fontsize=6.6,loc="upper left",ncol=1,framealpha=0.9)
fig.tight_layout(); fig.savefig("results/graph4_combined_preview.png",dpi=130); print("ok")
