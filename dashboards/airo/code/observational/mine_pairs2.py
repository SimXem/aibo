import json, os, glob, itertools
from collections import defaultdict
import numpy as np

D = os.path.expanduser("~/Projects/forecastbench-datasets/datasets")
DATASET_SOURCES = {"acled", "fred", "yfinance", "wikipedia", "dbnomics"}

panel = defaultdict(lambda: defaultdict(dict))
for f in sorted(glob.glob(f"{D}/resolution_sets/*_resolution_set.json")):
    js = json.load(open(f))
    due = js.get("forecast_due_date") or os.path.basename(f)[:10]
    for r in js["resolutions"]:
        if isinstance(r["id"], list) or r.get("source") not in DATASET_SOURCES: continue
        if not r.get("resolved"): continue
        v = r.get("resolved_to")
        if v not in (0.0, 1.0): continue
        panel[r["source"]][str(r["id"])][(due, r["resolution_date"])] = int(v)

text = {}
for f in sorted(glob.glob(f"{D}/question_sets/*-llm.json")):
    for q in json.load(open(f))["questions"]:
        if isinstance(q["id"], list): continue
        text[(q["source"], str(q["id"]))] = q["question"]

MIN_N = 30
rows = []
stats = {}
for src, qmap in panel.items():
    ids = [i for i, cells in qmap.items() if len(cells) >= MIN_N]
    base = {}
    for i in ids:
        vals = list(qmap[i].values())
        base[i] = sum(vals)/len(vals)
    eligible = [i for i in ids if 0.10 <= base[i] <= 0.90]
    stats[src] = (len(qmap), len(ids), len(eligible))
    cells = sorted({c for i in eligible for c in qmap[i]})
    ci = {c: k for k, c in enumerate(cells)}
    M = np.full((len(eligible), len(cells)), np.nan)
    for a, i in enumerate(eligible):
        for c, v in qmap[i].items(): M[a, ci[c]] = v
    for a, b in itertools.combinations(range(len(eligible)), 2):
        mask = ~np.isnan(M[a]) & ~np.isnan(M[b])
        n = int(mask.sum())
        if n < MIN_N: continue
        x, y = M[a, mask], M[b, mask]
        px, py = x.mean(), y.mean()
        sx, sy = x.std(), y.std()
        if sx == 0 or sy == 0: continue
        phi = float(((x-px)*(y-py)).mean()/(sx*sy))
        rows.append(dict(source=src, a=eligible[a], b=eligible[b], n=n,
                         base_a=round(float(px),3), base_b=round(float(py),3), phi=round(phi,3)))

print("source: (all ids, >=30 obs, base-rate eligible)")
for s,v in stats.items(): print(f"  {s:<10} {v}")
from collections import Counter
print("pairs per source:", Counter(r["source"] for r in rows))
for src in ["fred","yfinance","acled","wikipedia"]:
    sub = sorted([r for r in rows if r["source"]==src], key=lambda r:-abs(r["phi"]))
    print(f"\n== {src} top ==")
    for r in sub[:8]:
        qa, qb = text.get((src,r["a"]),"?"), text.get((src,r["b"]),"?")
        print(f"  phi={r['phi']:+.2f} n={r['n']} ba={r['base_a']} bb={r['base_b']}\n    A: {qa[:110]}\n    B: {qb[:110]}")
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"pair_candidates_all.jsonl"),"w") as fh:
    for r in sorted(rows,key=lambda r:-abs(r["phi"])):
        r["q_a"]=text.get((r["source"],r["a"]),"?"); r["q_b"]=text.get((r["source"],r["b"]),"?")
        fh.write(json.dumps(r)+"\n")
print("\ntotal pairs scored:", len(rows))
