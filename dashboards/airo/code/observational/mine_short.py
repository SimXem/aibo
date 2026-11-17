"""Re-mine: phi restricted to short-horizon cells (res - due <= 35 days),
block-bootstrap CI (block = question set / due date). Supersedes mine_pairs2.py."""
import json, os, glob, itertools, random
from datetime import date
from collections import defaultdict
import numpy as np

D = os.path.expanduser("~/Projects/forecastbench-datasets/datasets")
SOURCES = {"acled", "fred", "yfinance", "wikipedia", "dbnomics"}
MAX_GAP_DAYS = 35
MIN_CELLS = 20
MIN_SETS = 10
B = 2000

def d(s): y, m, dd = s.split("-"); return date(int(y), int(m), int(dd))

panel = defaultdict(lambda: defaultdict(dict))   # src -> id -> (due,res) -> 0/1
for f in sorted(glob.glob(f"{D}/resolution_sets/*_resolution_set.json")):
    js = json.load(open(f))
    due = js.get("forecast_due_date") or os.path.basename(f)[:10]
    for r in js["resolutions"]:
        if isinstance(r["id"], list) or r.get("source") not in SOURCES: continue
        if not r.get("resolved") or r.get("resolved_to") not in (0.0, 1.0): continue
        if (d(r["resolution_date"]) - d(due)).days > MAX_GAP_DAYS: continue
        panel[r["source"]][str(r["id"])][(due, r["resolution_date"])] = int(r["resolved_to"])

text = {}
for f in sorted(glob.glob(f"{D}/question_sets/*-llm.json")):
    for q in json.load(open(f))["questions"]:
        if not isinstance(q["id"], list):
            text[(q["source"], str(q["id"]))] = q["question"]

def phi_of(cells_a, cells_b, keys):
    x = np.array([cells_a[k] for k in keys], float)
    y = np.array([cells_b[k] for k in keys], float)
    sx, sy = x.std(), y.std()
    if sx == 0 or sy == 0: return None, x.mean(), y.mean()
    return float(((x - x.mean()) * (y - y.mean())).mean() / (sx * sy)), x.mean(), y.mean()

cands = []
for src, qmap in panel.items():
    ids = [i for i, c in qmap.items() if len(c) >= MIN_CELLS]
    for a, b in itertools.combinations(ids, 2):
        keys = sorted(set(qmap[a]) & set(qmap[b]))
        sets_ = sorted({k[0] for k in keys})
        if len(keys) < MIN_CELLS or len(sets_) < MIN_SETS: continue
        phi, pa, pb = phi_of(qmap[a], qmap[b], keys)
        if phi is None: continue
        if not (0.10 <= pa <= 0.90 and 0.10 <= pb <= 0.90): continue
        if not (abs(phi) >= 0.20 or abs(phi) <= 0.08): continue  # screen before bootstrap
        cands.append((src, a, b, keys, sets_, phi, pa, pb))

rng = random.Random(0)
out = []
for src, a, b, keys, sets_, phi, pa, pb in cands:
    by_set = defaultdict(list)
    for k in keys: by_set[k[0]].append(k)
    boots = []
    for _ in range(B):
        sample_keys = []
        for s in rng.choices(sets_, k=len(sets_)):
            sample_keys.extend(by_set[s])
        p, _, _ = phi_of(panel[src][a], panel[src][b], sample_keys)
        if p is not None: boots.append(p)
    if len(boots) < B * 0.8: continue
    boots.sort()
    lo, hi = boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]
    out.append(dict(source=src, a=a, b=b, n=len(keys), n_sets=len(sets_),
                    base_a=round(pa, 3), base_b=round(pb, 3),
                    phi=round(phi, 3), ci_lo=round(lo, 3), ci_hi=round(hi, 3),
                    q_a=text.get((src, a), "?"), q_b=text.get((src, b), "?")))

out.sort(key=lambda r: -abs(r["phi"]))
here = os.path.dirname(os.path.abspath(__file__))
with open(f"{here}/pair_candidates_short.jsonl", "w") as fh:
    for r in out: fh.write(json.dumps(r) + "\n")

from collections import Counter
print("bootstrapped candidates:", len(out), Counter(r["source"] for r in out))
neg = [r for r in out if r["ci_hi"] < 0 and r["phi"] <= -0.25]
pos = [r for r in out if r["ci_lo"] > 0 and r["phi"] >= 0.25]
ctl = [r for r in out if -0.15 < r["ci_lo"] and r["ci_hi"] < 0.15 and abs(r["phi"]) <= 0.05]
print(f"clean negatives: {len(neg)} | clean positives: {len(pos)} | clean controls: {len(ctl)}")
for r in neg[:10]:
    print(f"  NEG {r['source']} phi={r['phi']:+.2f} CI[{r['ci_lo']:+.2f},{r['ci_hi']:+.2f}] n={r['n']}/{r['n_sets']}sets | {r['q_a'][:60]} || {r['q_b'][:60]}")
