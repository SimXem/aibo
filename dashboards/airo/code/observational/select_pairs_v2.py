"""Selection v2 (supersedes select_pairs.py): weather-only, 30-day horizon,
bootstrap-certified classes with a dead zone. See spec.md."""
import json, os, random
S = os.path.dirname(os.path.abspath(__file__))
rows = [json.loads(l) for l in open(f"{S}/pair_candidates_short.jsonl") if json.loads(l)["source"] == "dbnomics"]
rng = random.Random(0)
used = {}

def take(cands, k, cat):
    out = []
    for r in cands:
        if len(out) >= k: break
        if used.get(r["a"], 0) >= 2 or used.get(r["b"], 0) >= 2: continue
        used[r["a"]] = used.get(r["a"], 0) + 1
        used[r["b"]] = used.get(r["b"], 0) + 1
        r = dict(r); r["category"] = cat
        if rng.random() < 0.5:
            for x, y in [("a","b"),("q_a","q_b"),("base_a","base_b")]:
                r[x], r[y] = r[y], r[x]
        out.append(r)
    return out

sel = []
sel += take(sorted([r for r in rows if r["phi"] >= 0.95 and r["ci_lo"] >= 0.85],
                   key=lambda r: -r["phi"]), 2, "sanity_near_duplicate")
for lo, hi in [(0.85, 0.95), (0.65, 0.85), (0.45, 0.65), (0.30, 0.45)]:
    band = sorted([r for r in rows if lo <= r["phi"] < hi and r["ci_lo"] > (0 if lo > 0.4 else 0.05)],
                  key=lambda r: -r["n"])
    sel += take(band, 3, f"associated_pos_{lo}")
neg = sorted([r for r in rows if r["phi"] <= -0.30 and r["ci_hi"] < 0], key=lambda r: -r["n"])
sel += take(neg, 8, "associated_negative")
ctl = sorted([r for r in rows if abs(r["phi"]) <= 0.08 and r["ci_lo"] > -0.25 and r["ci_hi"] < 0.25],
             key=lambda r: (r["ci_hi"] - r["ci_lo"]))
sel += take(ctl, 8, "control_independent")

for i, r in enumerate(sel): r["pair_id"] = f"pair-{i:02d}"
json.dump(sel, open(f"{S}/pairs_selected.json", "w"), indent=1)

from collections import Counter
import re
def st(q):
    m = re.search(r"station at (.+?) will", q); return m.group(1) if m else q[:35]
print(Counter(r["category"] for r in sel), "| total:", len(sel))
for r in sel:
    print(f"{r['pair_id']} {r['category']:<22} phi={r['phi']:+.2f} CI[{r['ci_lo']:+.2f},{r['ci_hi']:+.2f}] n={r['n']}/{r['n_sets']}s | {st(r['q_a'])} || {st(r['q_b'])}")
