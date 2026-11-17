"""Conditional-coherence MVP — scoring. Metric definitions in spec.md.
Usage: python3 score_bench.py [results.jsonl]"""
import json, os, sys, math
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
# Vendored into redlines 2026-08-28: inputs under data/observational/, runs
# under results/observational/ (upstream kept everything in one directory).
ROOT = os.path.dirname(os.path.dirname(HERE))
RESULTS = sys.argv[1] if len(sys.argv) > 1 else f"{ROOT}/results/observational/results_2026-08-20.jsonl"
PAIRS = {p["pair_id"]: p for p in json.load(open(f"{ROOT}/data/observational/pairs_selected.json"))}
POS = {pid for pid, p in PAIRS.items()
       if p["category"].startswith("associated_pos") or p["category"].startswith("sanity")}
CTRL = {pid for pid, p in PAIRS.items() if p["category"] == "control_independent"}
PROBE = {pid for pid, p in PAIRS.items() if p["category"] == "hemispheric_probe"}
SCORED = POS | CTRL

def implied_phi(v):
    pa, pb = v["p_a"], v["p_b"]
    denom = math.sqrt(pa * (1 - pa) * pb * (1 - pb))
    if denom < 1e-9:
        return None
    return max(-1.0, min(1.0, (v["p_b_given_a"] * pa - pa * pb) / denom))

def median(xs):
    xs = sorted(xs); n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2

def binom_p_ge(k, n):
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n

def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0

def perm_p(xs, ys, rho, n_perm=10000):
    import random
    rng = random.Random(0); ge = 0; ys2 = ys[:]
    for _ in range(n_perm):
        rng.shuffle(ys2)
        if spearman(xs, ys2) >= rho:
            ge += 1
    return (ge + 1) / (n_perm + 1)

by_mp = defaultdict(list)
for line in open(RESULTS):
    r = json.loads(line)
    by_mp[(r["model"], r["pair_id"])].append(r)

models = sorted({m for m, _ in by_mp})
for m in models:
    eps, phi_i, phi_h = [], [], []
    kp = np_ = 0
    d_ctrl, d_pos, probe_d = [], [], []
    for pid, pair in PAIRS.items():
        rs = by_mp.get((m, pid), [])
        if not rs:
            continue
        eps.append(median([abs(r["p_b"] - (r["p_b_given_a"] * r["p_a"]
                    + r["p_b_given_not_a"] * (1 - r["p_a"]))) for r in rs]))
        delta = median([r["p_b_given_a"] - r["p_b_given_not_a"] for r in rs])
        if pid in POS:
            np_ += 1; kp += int(delta > 0); d_pos.append(abs(delta))
        if pid in CTRL:
            d_ctrl.append(abs(delta))
        if pid in PROBE:
            probe_d.append((pid, delta))
        if pid in SCORED:
            phis = [p for p in (implied_phi(r) for r in rs) if p is not None]
            if phis:
                phi_i.append(median(phis)); phi_h.append(pair["phi"])
    p_pos = binom_p_ge(kp, np_) if np_ else float("nan")
    rho = spearman(phi_h, phi_i) if len(phi_i) > 2 else float("nan")
    p4 = perm_p(phi_h, phi_i, rho) if len(phi_i) > 2 else float("nan")
    m3 = median(d_ctrl) if d_ctrl else float("nan")
    print(f"\n{m}")
    print(f"  M1 coherence      median eps = {median(eps):.3f}")
    print(f"  M2 direction      positives {kp}/{np_} correct (exact binomial p={p_pos:.3f})")
    print(f"  M3 independence   control median |D| = {m3:.3f}  ({'PASS' if m3 < 0.075 else 'FAIL'} < 0.075)"
          f"   [positive median |D| = {median(d_pos):.3f}]")
    print(f"  M4 rank tracking  rho_scored = {rho:+.2f} (perm p={p4:.3f}, anticonservative)")
    if probe_d:
        s = "  ".join(f"{pid}:{dv:+.2f}" for pid, dv in sorted(probe_d))
        print(f"  probe (NOT SCORED, hemispheric) median D per pair: {s}")

print("\nPass bar (top model): M2 p<0.05, M3 PASS (<0.075), M4 rho_scored>0 at p<0.05.")
print("Gradient: M4 rho_scored non-decreasing on >=3 of 4 adjacent tier steps.")
print("Probe deltas are descriptive only — no ground truth is claimed for them.")
print("Interpret M4 as rank evidence only; implied-phi magnitudes are demand-inflated.")

scatter = defaultdict(list)
for (m, pid), rs in by_mp.items():
    phis = [p for p in (implied_phi(r) for r in rs) if p is not None]
    if phis:
        scatter[m].append({"pair_id": pid, "phi_hist": PAIRS[pid]["phi"],
                           "phi_implied": median(phis),
                           "category": PAIRS[pid]["category"]})
json.dump(scatter, open(os.path.splitext(RESULTS)[0].replace("results_", "scatter_by_model_") + ".json", "w"), indent=1)
print("wrote scatter_by_model.json (the 'why we trust this' graph data)")
