"""Noise ceiling: how well could a forecaster that knew the TRUE pair
associations score against OUR measured (finite-panel) associations?

Method: block-bootstrap re-measurements of every scored pair's anomaly phi
(same residualization and blocks as mine_anomaly2.py). Treat the full-panel
estimate as the oracle's answer; each bootstrap replicate is one plausible
re-measurement. Ceiling = mean Spearman(oracle, replicate) across replicates.
Split-half reliability reported alongside as the pessimistic cousin.
Also emits each pair's phi CI half-width -> the diagonal noise band, and the
control-zone half-width."""
import json, os, glob, itertools, random, math
from datetime import date
from collections import defaultdict
import numpy as np

D = os.path.expanduser("~/Projects/forecastbench-datasets/datasets")
MAX_GAP, B = 35, 1000
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

def residualize(cells):
    keys = sorted(cells)
    y = np.array([cells[k][0] for k in keys], float)
    doy = np.array([cells[k][1] for k in keys], float)
    h = np.array([cells[k][2] for k in keys], float)
    w = 2 * math.pi * doy / 365.25
    X = np.column_stack([np.ones_like(w), np.sin(w), np.cos(w), np.sin(2*w), np.cos(2*w), h])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return dict(zip(keys, y - np.clip(X @ beta, 0.02, 0.98)))

resid = {q: residualize(c) for q, c in panel.items() if len(c) >= 25}

PAIRS = [p for p in json.load(open("pairs_selected.json")) if p["scored"]]
def corr(ra, rb, keys):
    x = np.array([ra[k] for k in keys]); y = np.array([rb[k] for k in keys])
    sx, sy = x.std(), y.std()
    return None if sx < 1e-9 or sy < 1e-9 else float(((x-x.mean())*(y-y.mean())).mean()/(sx*sy))

def spearman(x, y):
    def rk(v):
        o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0]*len(v); i = 0
        while i < len(o):
            j = i
            while j+1 < len(o) and v[o[j+1]] == v[o[i]]: j += 1
            for k in range(i, j+1): r[o[k]] = (i+j)/2+1
            i = j+1
        return r
    rx, ry = rk(x), rk(y); mx, my = sum(rx)/len(rx), sum(ry)/len(ry)
    num = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a-mx)**2 for a in rx)*sum((b-my)**2 for b in ry))
    return num/den if den else 0.0

rng = random.Random(0)
meta = []
for p in PAIRS:
    keys = sorted(set(resid[p["a"]]) & set(resid[p["b"]]))
    sets_ = sorted({k[0] for k in keys})
    by_set = defaultdict(list)
    for k in keys: by_set[k[0]].append(k)
    meta.append((p, keys, sets_, by_set))

oracle = [p["phi"] for p, *_ in meta]
ceil_samples, replicate_cache = [], []
for b in range(B):
    rep = []
    for p, keys, sets_, by_set in meta:
        sk = [k for s in rng.choices(sets_, k=len(sets_)) for k in by_set[s]]
        c = corr(resid[p["a"]], resid[p["b"]], sk)
        rep.append(p["phi"] if c is None else c)
    ceil_samples.append(spearman(oracle, rep))
ceil_samples.sort()
ceiling = sum(ceil_samples)/len(ceil_samples)
lo, hi = ceil_samples[int(.025*B)], ceil_samples[int(.975*B)]

# split-half: disjoint halves of question sets -> two independent measurements
sh = []
for b in range(200):
    r2 = random.Random(1000+b)
    va, vb = [], []
    for p, keys, sets_, by_set in meta:
        s = sets_[:]; r2.shuffle(s)
        h1, h2 = s[:len(s)//2], s[len(s)//2:]
        c1 = corr(resid[p["a"]], resid[p["b"]], [k for x in h1 for k in by_set[x]])
        c2 = corr(resid[p["a"]], resid[p["b"]], [k for x in h2 for k in by_set[x]])
        if c1 is None or c2 is None: c1, c2 = p["phi"], p["phi"]
        va.append(c1); vb.append(c2)
    sh.append(spearman(va, vb))
split_half = sum(sh)/len(sh)

half_widths = [(p["ci_hi"]-p["ci_lo"])/2 for p, *_ in meta]
half_widths.sort()
band = half_widths[len(half_widths)//2]

print(f"noise ceiling (oracle vs re-measurement): rho = {ceiling:.2f}  [{lo:.2f}, {hi:.2f}]")
print(f"split-half reliability (pessimistic):     rho = {split_half:.2f}")
print(f"median phi CI half-width (diagonal band): +/-{band:.2f}")
json.dump({"ceiling": round(ceiling,3), "ceiling_lo": round(lo,3), "ceiling_hi": round(hi,3),
           "split_half": round(split_half,3), "band": round(band,3)},
          open("noise_ceiling.json","w"), indent=1)
