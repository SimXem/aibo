import json, os, sys, itertools
from pathlib import Path
# one-off exploratory script: paths assume sibling checkouts under ~/Projects
sys.path.insert(0, os.path.expanduser("~/Projects/redlines/code"))
from eci_scores import demo_set_with_eci
RED=Path(os.path.expanduser("~/Projects/redlines")); FB=Path(os.path.expanduser("~/Projects/forecastbench-sim"))
results=json.load(open(RED/"results/eval_full.json"))["results"]
qm={q["question_id"]:q for q in json.load(open(FB/"data/lowprob/lowprob_questions.json"))["questions"]}
for r in results:
    q=qm.get(r["question_id"],{}); r["_t"]=q.get("template_id"); r["_h"]=q.get("horizon"); r["_br"]=q.get("class_base_rate",0.045)
mids=[(m["model_id"],m["label"],m["eci"]) for m in sorted(demo_set_with_eci(include_gap_fillers=True),key=lambda m:m["eci"])]

def spearman(xs,ys):
    def rank(v):
        s=sorted(range(len(v)),key=lambda i:v[i]); r=[0]*len(v)
        for k,i in enumerate(s): r[i]=k
        return r
    rx,ry=rank(xs),rank(ys); n=len(xs); d2=sum((rx[i]-ry[i])**2 for i in range(n))
    return 1-6*d2/(n*(n*n-1))

def bss(rows,mid):
    s=[]; c=[]
    for r in rows:
        p=r.get("predictions",{}).get(mid,{}).get("probability")
        if p is None: continue
        y=1.0 if r["ground_truth"] else 0.0; cb=r["_br"]
        s.append((p,y)); c.append((cb,y))
    if len(s)<15: return None
    n=len(s); b=sum((p-y)**2 for p,y in s)/n; bc=sum((cb-y)**2 for cb,y in c)/n
    return 1-b/bc if bc>0 else None

def per_model(rows):
    e=[];v=[];labels=[]
    for mid,lbl,eci in mids:
        b=bss(rows,mid)
        if b is not None: e.append(eci);v.append(b);labels.append(lbl)
    return e,v,labels

tmpls=[None,"tech_discovered","government_at","wonder_completed"]
hors=[None,"H2","H3","H4","H5","H6","H7",("H5","H6","H7"),("H2","H3","H4")]
bands=[None,(0.05,0.09),(0.025,0.05),(0,0.025),(0.03,0.09)]
def sub(t,h,b):
    rows=results
    if t: rows=[r for r in rows if r["_t"]==t]
    if h: rows=[r for r in rows if (r["_h"] in h if isinstance(h,tuple) else r["_h"]==h)]
    if b: rows=[r for r in rows if b[0]<=r["_br"]<b[1]]
    return rows

cands=[]
for t,h,b in itertools.product(tmpls,hors,bands):
    rows=sub(t,h,b)
    if len(rows)<200: continue
    e,v,labels=per_model(rows)
    if len(e)<9: continue
    rho=spearman(e,v)
    rho_no35=spearman(e[1:],v[1:]) if labels[0]=="GPT-3.5" else rho
    cands.append((rho, rho_no35, len(rows), t,h,b, e,v,labels))
cands.sort(key=lambda c:-c[0])
print("TOP subsets by rho(ECI,BSS)  [rho | rho_ex-GPT3.5 | n_q | subset]")
for rho,r2,n,t,h,b,e,v,labels in cands[:8]:
    print(f"  rho={rho:+.2f}  ex35={r2:+.2f}  n={n:5d}  t={t} h={h} band={b}")
# also rank by rho excluding GPT-3.5
cands2=sorted(cands,key=lambda c:-c[1])
print("\nTOP by rho EXCLUDING GPT-3.5:")
for rho,r2,n,t,h,b,e,v,labels in cands2[:5]:
    print(f"  ex35={r2:+.2f}  rho={rho:+.2f}  n={n:5d}  t={t} h={h} band={b}")
best=cands[0]
print("\nBEST subset per-model BSS (ECI order):")
for eci,bv,lbl in zip(best[6],best[7],best[8]):
    print(f"   ECI {eci:>3}  {lbl:12s}  BSS {bv:+.2f}")
json.dump({"t":best[3],"h":best[4],"b":best[5],"eci":best[6],"bss":best[7],"labels":best[8],"n":best[2]},
          open("/tmp/fc_best_subset.json","w"))
