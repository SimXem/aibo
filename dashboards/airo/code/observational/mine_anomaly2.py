"""Anomaly phi v2: residualize each question on a smooth seasonal model
(linear-probability fit on [1, sin(doy), cos(doy), sin(2 doy), cos(2 doy),
horizon]) instead of coarse season bins. If the hemispheric negatives are
within-bin seasonal drift, they collapse here; if they are a real
teleconnection, they survive."""
import json, os, glob, itertools, random, math
from datetime import date
from collections import defaultdict
import numpy as np

D = os.path.expanduser("~/Projects/forecastbench-datasets/datasets")
MAX_GAP, MIN_CELLS, B = 35, 25, 2000
def d(s): y, m, dd = s.split("-"); return date(int(y), int(m), int(dd))

panel = defaultdict(dict)
for f in sorted(glob.glob(f"{D}/resolution_sets/*_resolution_set.json")):
    js = json.load(open(f)); due = js.get("forecast_due_date") or os.path.basename(f)[:10]
    for r in js["resolutions"]:
        if isinstance(r["id"], list) or r.get("source") != "dbnomics": continue
        if not r.get("resolved") or r.get("resolved_to") not in (0.0, 1.0): continue
        gap = (d(r["resolution_date"]) - d(due)).days
        if gap > MAX_GAP: continue
        doy = d(due).timetuple().tm_yday
        panel[str(r["id"])][(due, r["resolution_date"])] = (int(r["resolved_to"]), doy, 0.0 if gap <= 10 else 1.0)

resid = {}
for q, cells in panel.items():
    if len(cells) < MIN_CELLS: continue
    keys = sorted(cells)
    y = np.array([cells[k][0] for k in keys], float)
    doy = np.array([cells[k][1] for k in keys], float)
    h = np.array([cells[k][2] for k in keys], float)
    w = 2 * math.pi * doy / 365.25
    X = np.column_stack([np.ones_like(w), np.sin(w), np.cos(w), np.sin(2*w), np.cos(2*w), h])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    p_hat = np.clip(X @ beta, 0.02, 0.98)
    resid[q] = dict(zip(keys, y - p_hat))

text = {}
for f in sorted(glob.glob(f"{D}/question_sets/*-llm.json")):
    for q in json.load(open(f))["questions"]:
        if not isinstance(q["id"], list): text[str(q["id"])] = q["question"]

def corr(ra, rb, keys):
    x = np.array([ra[k] for k in keys]); y = np.array([rb[k] for k in keys])
    sx, sy = x.std(), y.std()
    if sx < 1e-9 or sy < 1e-9: return None
    return float(((x - x.mean()) * (y - y.mean())).mean() / (sx * sy))

rng = random.Random(0); out = []
for a, b in itertools.combinations(sorted(resid), 2):
    keys = sorted(set(resid[a]) & set(resid[b]))
    sets_ = sorted({k[0] for k in keys})
    if len(keys) < MIN_CELLS or len(sets_) < 10: continue
    rho = corr(resid[a], resid[b], keys)
    if rho is None: continue
    by_set = defaultdict(list)
    for k in keys: by_set[k[0]].append(k)
    boots = []
    for _ in range(B):
        sk = [k for s in rng.choices(sets_, k=len(sets_)) for k in by_set[s]]
        c = corr(resid[a], resid[b], sk)
        if c is not None: boots.append(c)
    if len(boots) < B * 0.8: continue
    boots.sort(); lo, hi = boots[int(.025*len(boots))], boots[int(.975*len(boots))]
    out.append(dict(a=a, b=b, n=len(keys), n_sets=len(sets_), phi=round(rho,3),
                    ci_lo=round(lo,3), ci_hi=round(hi,3),
                    q_a=text.get(a,"?"), q_b=text.get(b,"?")))
with open("pair_candidates_anomaly2.jsonl", "w") as fh:
    for r in sorted(out, key=lambda r: -abs(r["phi"])): fh.write(json.dumps(r) + "\n")
print("pairs scored:", len(out))
