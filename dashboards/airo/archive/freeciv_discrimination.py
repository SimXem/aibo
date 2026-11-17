import json, os, sys
from pathlib import Path
# one-off exploratory script: paths assume sibling checkouts under ~/Projects
sys.path.insert(0, os.path.expanduser("~/Projects/redlines/code"))
from eci_scores import demo_set_with_eci
RED=Path(os.path.expanduser("~/Projects/redlines")); FB=Path(os.path.expanduser("~/Projects/forecastbench-sim"))
results=json.load(open(RED/"results/eval_full.json"))["results"]
qm={q["question_id"]:q for q in json.load(open(FB/"data/lowprob/lowprob_questions.json"))["questions"]}
for r in results:
    q=qm.get(r["question_id"],{}); r["_t"]=q.get("template_id"); r["_h"]=q.get("horizon"); r["_br"]=q.get("class_base_rate",0.045)
# frontier-ish models to test discrimination
mids=[(m["model_id"],m["label"],m["eci"]) for m in demo_set_with_eci(include_gap_fillers=True)]
frontier=[m for m in mids if m[1] in ("Fable 5","Opus 4.8","Sonnet 4.5","GPT-5")]

def discrim(rows, mid):
    """obs in top vs bottom half of this model's predictions; + overall obs."""
    pairs=[]
    for r in rows:
        p=r.get("predictions",{}).get(mid,{}).get("probability")
        if p is None: continue
        pairs.append((p, 1.0 if r["ground_truth"] else 0.0))
    if len(pairs)<40: return None
    pairs.sort()
    n=len(pairs); half=n//2
    lo=pairs[:half]; hi=pairs[half:]
    obs_lo=sum(y for _,y in lo)/len(lo); obs_hi=sum(y for _,y in hi)/len(hi)
    base=sum(y for _,y in pairs)/n
    return (obs_hi-obs_lo, obs_lo, obs_hi, base, n)

def show(name, rows):
    print(f"\n{name}  (n_q={len(rows)})")
    for mid,lbl,eci in frontier:
        d=discrim(rows,mid)
        if d is None: continue
        gap,olo,ohi,base,n=d
        flag=" <-- discriminates" if gap>0.02 else ""
        print(f"   {lbl:11s} obs: low-half {olo*100:4.1f}%  high-half {ohi*100:4.1f}%  (base {base*100:4.1f}%)  gap {gap*100:+4.1f}pp{flag}")

show("ALL FreeCiv", results)
show("government_at (rho +0.71)", [r for r in results if r["_t"]=="government_at"])
show("tech_discovered (rho +0.68)", [r for r in results if r["_t"]=="tech_discovered"])
show("wonder_completed (rho +0.21)", [r for r in results if r["_t"]=="wonder_completed"])
show("5-9% band", [r for r in results if 0.05<=r["_br"]<0.09])
show("very-rare 1-2.5%", [r for r in results if r["_br"]<0.025])
show("long horizon H5-H7", [r for r in results if r["_h"] in ("H5","H6","H7")])
show("short horizon H1", [r for r in results if r["_h"]=="H1"])
