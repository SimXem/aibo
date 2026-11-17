"""Anomaly (deseasonalized) phi: residualize each question's outcomes on
(season-of-due-date x horizon-bucket) base rates, then correlate residuals.
This is the association that remains GIVEN the date — the quantity a
date-aware forecaster should express. Motivated by the v2 pilot: models
correctly treated hemispheric pairs as conditionally independent."""
import json, os, glob, itertools, random
from datetime import date
from collections import defaultdict
import numpy as np

D = os.path.expanduser("~/Projects/forecastbench-datasets/datasets")
MAX_GAP, MIN_CELLS, MIN_BIN, B = 35, 25, 3, 2000
def d(s): y, m, dd = s.split("-"); return date(int(y), int(m), int(dd))
SEASON = {12:"DJF",1:"DJF",2:"DJF",3:"MAM",4:"MAM",5:"MAM",6:"JJA",7:"JJA",8:"JJA",9:"SON",10:"SON",11:"SON"}

panel = defaultdict(dict)
for f in sorted(glob.glob(f"{D}/resolution_sets/*_resolution_set.json")):
    js = json.load(open(f)); due = js.get("forecast_due_date") or os.path.basename(f)[:10]
    for r in js["resolutions"]:
        if isinstance(r["id"], list) or r.get("source") != "dbnomics": continue
        if not r.get("resolved") or r.get("resolved_to") not in (0.0, 1.0): continue
        gap = (d(r["resolution_date"]) - d(due)).days
        if gap > MAX_GAP: continue
        panel[str(r["id"])][(due, r["resolution_date"])] = (int(r["resolved_to"]), SEASON[d(due).month], 0 if gap <= 10 else 1)

resid = {}
for q, cells in panel.items():
    if len(cells) < MIN_CELLS: continue
    bins = defaultdict(list)
    for (dd, rr), (y, s, h) in cells.items(): bins[(s, h)].append(y)
    p_hat = {k: sum(v)/len(v) for k, v in bins.items() if len(v) >= MIN_BIN}
    rq = {}
    for (dd, rr), (y, s, h) in cells.items():
        if (s, h) in p_hat: rq[(dd, rr)] = y - p_hat[(s, h)]
    if len(rq) >= MIN_CELLS: resid[q] = rq

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
ids = sorted(resid)
for a, b in itertools.combinations(ids, 2):
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
out.sort(key=lambda r: -abs(r["phi"]))
with open("pair_candidates_anomaly.jsonl", "w") as fh:
    for r in out: fh.write(json.dumps(r) + "\n")
print("questions with residual panels:", len(resid), "| pairs scored:", len(out))
