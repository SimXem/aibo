import json, os, sys
from pathlib import Path
# one-off exploratory script: paths assume sibling checkouts under ~/Projects
sys.path.insert(0, os.path.expanduser("~/Projects/redlines/code"))
from eci_scores import demo_set_with_eci
RED=Path(os.path.expanduser("~/Projects/redlines"))
FB=Path(os.path.expanduser("~/Projects/forecastbench-sim"))
results=json.load(open(RED/"results/eval_full.json"))["results"]
qmeta={q["question_id"]:q for q in json.load(open(FB/"data/lowprob/lowprob_questions.json"))["questions"]}
models=sorted(demo_set_with_eci(include_gap_fillers=True), key=lambda r:r["eci"])
mids=[(m["model_id"],m["label"],m["eci"]) for m in models]

def spearman(xs,ys):
    def rank(v):
        s=sorted(range(len(v)),key=lambda i:v[i]); r=[0]*len(v)
        for rk,i in enumerate(s): r[i]=rk
        return r
    rx,ry=rank(xs),rank(ys); n=len(xs)
    d2=sum((rx[i]-ry[i])**2 for i in range(n))
    return 1-6*d2/(n*(n*n-1))

def bss_for(rows, mid):
    samples=[]; clim=[]
    for res in rows:
        p=res.get("predictions",{}).get(mid,{}).get("probability")
        if p is None: continue
        y=1.0 if res["ground_truth"] else 0.0
        c=qmeta.get(res["question_id"],{}).get("class_base_rate",0.045)
        samples.append((p,y)); clim.append((c,y))
    if len(samples)<15: return None
    n=len(samples)
    b=sum((p-y)**2 for p,y in samples)/n
    bc=sum((c-y)**2 for c,y in clim)/n
    return 1-b/bc if bc>0 else None

def analyze(name, rows):
    ecis=[]; bsss=[]
    for mid,lbl,eci in mids:
        b=bss_for(rows,mid)
        if b is not None: ecis.append(eci); bsss.append(b)
    if len(ecis)<5: return
    rho=spearman(ecis,bsss)
    flag=" <== GRADIENT" if rho>=0.5 else (" (mild)" if rho>=0.3 else "")
    print(f"{name:26s} n_q={len(rows):5d}  rho(ECI,BSS)={rho:+.2f}  BSS {min(bsss):+.1f}..{max(bsss):+.1f}{flag}")

for res in results:
    q=qmeta.get(res["question_id"],{})
    res["_t"]=q.get("template_id"); res["_h"]=q.get("horizon"); res["_br"]=q.get("class_base_rate",0.045)
print("=== OVERALL ==="); analyze("ALL", results)
print("\n=== by TEMPLATE ===")
for t in ["tech_discovered","wonder_completed","government_at"]:
    analyze(t, [r for r in results if r["_t"]==t])
print("\n=== by HORIZON ===")
for h in ["H1","H2","H3","H4","H5","H6","H7"]:
    analyze(h, [r for r in results if r["_h"]==h])
print("\n=== by BASE-RATE BAND ===")
for name,lo,hi in [("very rare 1-2.5%",0,0.025),("rare 2.5-5%",0.025,0.05),("5-9%",0.05,0.09)]:
    analyze(name, [r for r in results if lo<=r["_br"]<hi])
print("\n=== template x horizon ===")
for t in ["tech_discovered","wonder_completed","government_at"]:
    for h in ["H2","H3","H4","H5","H6"]:
        rows=[r for r in results if r["_t"]==t and r["_h"]==h]
        if len(rows)>=200: analyze(f"{t[:8]}.{h}", rows)
