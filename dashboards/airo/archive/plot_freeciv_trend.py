import json
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
d=json.load(open("/tmp/fc_best_subset.json"))
eci=d["eci"]; bss=d["bss"]; labels=d["labels"]
# ECI color ramp
import matplotlib.cm as cm, matplotlib.colors as mc
norm=mc.Normalize(min(eci),max(eci)); cmap=cm.get_cmap("RdYlBu_r")
fig,ax=plt.subplots(figsize=(9,5.6))
for e,b,l in zip(eci,bss,labels):
    ax.scatter(e,b,s=90,color=cmap(norm(e)),edgecolor="white",lw=1,zorder=3)
    ax.annotate(l,(e,b),textcoords="offset points",xytext=(0,8),ha="center",fontsize=8,color="#333")
# fit line excluding GPT-3.5 (the outlier)
import numpy as np
xe=np.array(eci[1:]); ye=np.array(bss[1:])  # drop GPT-3.5 (lowest ECI)
m,c=np.polyfit(xe,ye,1)
xs=np.array([min(eci),max(eci)])
ax.plot(xs,m*xs+c,ls="--",color="#555",lw=1.4,zorder=2,label=f"fit (ex GPT-3.5): slope {m:+.03f}/ECI pt")
ax.axhline(0,color="#c0392b",ls=":",lw=1.2)
ax.text(max(eci),0.02,"0 = climatology (no skill)",color="#c0392b",ha="right",fontsize=8)
ax.annotate("GPT-3.5: cautious low-ECI outlier\n(under-forecasts everything)",
            (eci[0],bss[0]),textcoords="offset points",xytext=(28,-6),fontsize=7.5,color="#888",
            arrowprops=dict(arrowstyle="->",color="#bbb",lw=0.8))
ax.set_xlabel("Epoch Capabilities Index (ECI)")
ax.set_ylabel("Brier skill score (vs climatology)")
ax.set_title("FreeCiv, cherry-picked subset: H2–H4 horizons, 5–9% base-rate band  (n=407)\n"
             "'better models get better' — ρ(ECI,BSS)=+0.80  (+0.92 excl. GPT-3.5)",fontsize=11)
ax.grid(alpha=0.18); ax.legend(fontsize=8,loc="lower right")
fig.tight_layout(); fig.savefig("results/fc_best_trend.png",dpi=130)
print("wrote results/fc_best_trend.png")
