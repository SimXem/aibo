import json, os, random
S = os.path.dirname(os.path.abspath(__file__))
rows = [json.loads(l) for l in open(f"{S}/pair_candidates_all.jsonl")]
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
        if rng.random() < 0.5:   # counterbalance which question plays the role of A
            r["a"], r["b"] = r["b"], r["a"]
            r["q_a"], r["q_b"] = r["q_b"], r["q_a"]
            r["base_a"], r["base_b"] = r["base_b"], r["base_a"]
        out.append(r)
    return out

sel = []
dup = sorted([r for r in rows if abs(r["phi"]) >= 0.95], key=lambda r: -abs(r["phi"]))
sel += take(dup, 3, "sanity_near_duplicate")

fred = sorted([r for r in rows if r["source"] == "fred" and 0.30 <= abs(r["phi"]) < 0.95 and r["n"] >= 30],
              key=lambda r: -abs(r["phi"]))
neg = [r for r in fred if r["phi"] < 0]
pos = [r for r in fred if r["phi"] > 0]
sel += take(neg, 4, "associated_negative")
sel += take(pos, 8, "associated_positive")

db = [r for r in rows if r["source"] == "dbnomics" and r["n"] >= 40]
for lo, hi in [(0.8, 0.95), (0.6, 0.8), (0.4, 0.6), (0.2, 0.4)]:
    band = sorted([r for r in db if lo <= r["phi"] < hi], key=lambda r: -r["n"])
    sel += take(band, 3, f"associated_gradient_{lo}")

ctrl = sorted([r for r in rows if abs(r["phi"]) <= 0.05 and r["n"] >= 40], key=lambda r: -r["n"])
sel += take(ctrl, 8, "control_independent")

for i, r in enumerate(sel): r["pair_id"] = f"pair-{i:02d}"
json.dump(sel, open(f"{S}/pairs_selected.json", "w"), indent=1)

from collections import Counter
print(Counter(r["category"] for r in sel))
print("total:", len(sel))
for r in sel:
    print(f"{r['pair_id']} {r['source']:<9} {r['category']:<24} phi={r['phi']:+.2f} n={r['n']}")
    print(f"   A: {r['q_a'][:95]}")
    print(f"   B: {r['q_b'][:95]}")
