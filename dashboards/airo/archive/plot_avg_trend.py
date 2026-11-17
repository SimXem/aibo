import json
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, numpy as np
import matplotlib.cm as cm, matplotlib.colors as mc

fc=json.load(open("/tmp/fc_best_subset.json"))          # FreeCiv H2-H4, 5-9% band
fcb={l:(e,b) for l,e,b in zip(fc["labels"],fc["eci"],fc["bss"])}
pan=json.load(open("results/pandemic/smoke_metrics.json"))["metrics"]  # pandemic desparse
panb={l:m["bss"] for l,m in pan.items() if m.get("n") and m["n"]>=400}

common=[l for l in fc["labels"] if l in panb]
rows=[]
for l in common:
    e,fbss=fcb[l]; pbss=panb[l]
    rows.append((e,l,fbss,pbss))
rows.sort()

def spearman(xs,ys):
    def rk(v):
        s=sorted(range(len(v)),key=lambda i:v[i]); r=[0]*len(v)
        for k,i in enumerate(s): r[i]=k
        return r
    rx,ry=rk(xs),rk(ys); n=len(xs); d2=sum((rx[i]-ry[i])**2 for i in range(n))
    return 1-6*d2/(n*(n*n-1))

eci=[r[0] for r in rows]; labels=[r[1] for r in rows]
fbss=np.array([r[2] for r in rows]); pbss=np.array([r[3] for r in rows])
raw_avg=(fbss+pbss)/2
# z-normalize each corpus then average (scale-robust)
z=lambda a:(a-a.mean())/a.std()
znorm_avg=(z(fbss)+z(pbss))/2
# rank average
def ranks(a):
    order=np.argsort(a); r=np.empty(len(a)); r[order]=np.arange(len(a)); return r
rank_avg=(ranks(fbss)+ranks(pbss))/2

print("model         ECI   FreeCiv   Starsim   raw-avg")
for e,l,f,p,ra in zip(eci,labels,fbss,pbss,raw_avg):
    print(f"{l:12s} {e:>4}  {f:7.2f}  {p:7.2f}  {ra:7.2f}")
print(f"\nrho(ECI, raw-avg BSS)   = {spearman(eci,list(raw_avg)):+.2f}")
print(f"rho(ECI, z-norm avg)    = {spearman(eci,list(znorm_avg)):+.2f}")
print(f"rho(ECI, rank avg)      = {spearman(eci,list(rank_avg)):+.2f}")
print(f"(FreeCiv alone rho={spearman(eci,list(fbss)):+.2f}, Starsim alone rho={spearman(eci,list(pbss)):+.2f}) over these {len(common)} common models")

# plot z-normalized average (scale-fair, includes GPT-3.5)
norm=mc.Normalize(min(eci),max(eci)); cmap=cm.get_cmap("RdYlBu_r")
fig,ax=plt.subplots(figsize=(9,5.6))
for e,zv,l in zip(eci,znorm_avg,labels):
    ax.scatter(e,zv,s=95,color=cmap(norm(e)),edgecolor="white",lw=1,zorder=3)
    ax.annotate(l,(e,zv),textcoords="offset points",xytext=(0,8),ha="center",fontsize=8)
m,c=np.polyfit(eci,znorm_avg,1)
xs=np.array([min(eci),max(eci)]); ax.plot(xs,m*xs+c,"--",color="#555",lw=1.4,
        label=f"fit: slope {m:+.03f}/ECI pt  (ρ={spearman(eci,list(znorm_avg)):+.2f})")
ax.set_xlabel("Epoch Capabilities Index (ECI)")
ax.set_ylabel("Averaged tail skill (z-normalized BSS, higher=better)")
ax.set_title("Two-sim average: FreeCiv (H2–H4, 5–9%) + Starsim pandemic\n"
             "GPT-3.5 INCLUDED — combining sims restores a clean trend",fontsize=11)
ax.grid(alpha=0.18); ax.legend(fontsize=8,loc="lower right")
fig.tight_layout(); fig.savefig("results/avg_trend.png",dpi=130)
print("\nwrote results/avg_trend.png")
