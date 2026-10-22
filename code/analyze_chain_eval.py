#!/usr/bin/env python3
"""Score the FreeCiv chain experiment: coherence AND accuracy, SEP vs JOINT.

The ladder experiment could only measure coherence, because catastrophic-risk
questions do not resolve. These do. So this scorer answers the question that
decides app-wide adoption:

    Does batching a nested chain into one call make the forecasts BETTER,
    or only tidier?

Coherence is cheap to fake — sorting the existing numbers would give 100% and
improve nothing. Brier against ground truth cannot be faked, so it is the
endpoint that matters. Every question is forecast by the same model under both
arms, so Brier is compared PAIRED (per question, per model), not as two pooled
means: the chains differ wildly in difficulty and an unpaired mean is mostly
noise about which chains got sampled.

    python3 code/analyze_chain_eval.py results/experiments/chain_eval.jsonl

Stdlib only, no keys, no network.
"""
import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from redlines.stats import wilson_interval  # noqa: E402

CLIM_FALLBACK = 0.0458   # corpus-wide observed yes-rate, as in archive/litellm-runners/run_eval.py


def load(path):
    """-> {(arm, label, game, template, target): row}"""
    out = {}
    for ln in open(path):
        r = json.loads(ln)
        out[(r["arm"], r["label"], r["game_id"], r["template_id"], r["target"])] = r
    return out


def coherence(rows, arm):
    """P(by turn T) must be NON-DECREASING in T — the ground truth always is."""
    viol, pairs, bad, chains = [], 0, 0, 0
    for k, r in rows.items():
        if k[0] != arm:
            continue
        ps = [p for p in r["probs"] if p is not None]
        if len(ps) < 2:
            continue
        chains += 1
        hit = False
        for i, (a, b) in enumerate(zip(r["probs"], r["probs"][1:])):
            if a is None or b is None:
                continue
            pairs += 1
            if b < a - 1e-12:
                hit = True
                viol.append((r["label"], r["target"], r["turns"][i],
                             r["turns"][i + 1], a, b))
        bad += hit
    return {"chains": chains, "bad": bad, "pairs": pairs, "violations": viol}


def paired_cells(rows):
    """-> [(label, target, turn, p_sep, p_joint, y, clim, game)] where both arms answered.

    game is carried because the same wonder or tech is mined in several games —
    keying a chain on (model, target) alone silently merges two different games'
    chains into one observation and halves the chain-level sample.
    """
    out = []
    for k, r in rows.items():
        if k[0] != "sep":
            continue
        j = rows.get(("joint",) + k[1:])
        if not j:
            continue
        for i, t in enumerate(r["turns"]):
            ps, pj = r["probs"][i], j["probs"][i]
            if ps is None or pj is None:
                continue
            clim = r["class_base_rate"][i]
            out.append((r["label"], r["target"], t, ps, pj,
                        1.0 if r["ground_truth"][i] else 0.0,
                        CLIM_FALLBACK if clim is None else clim, r["game_id"]))
    return out


def wilcoxon(diffs):
    """Two-sided Wilcoxon signed-rank on the per-question Brier difference.

    Normal approximation with tie correction. Brier differences are strongly
    non-normal (most near zero, a few large), so the sign-and-rank test is the
    honest one; a paired t-test would be driven by the tail.
    """
    d = [x for x in diffs if x != 0]
    n = len(d)
    if n < 6:
        return None, n
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(d[order[j + 1]]) == abs(d[order[i]]):
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    w_pos = sum(ranks[i] for i in range(n) if d[i] > 0)
    mu = n * (n + 1) / 4
    sd = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    if sd == 0:
        return None, n
    z = (w_pos - mu) / sd
    p = math.erfc(abs(z) / math.sqrt(2))
    return p, n


def brier_block(cells, pick):
    """(brier, bss, mean_pred) for one arm over the paired cells."""
    n = len(cells)
    b = sum((pick(c) - c[5]) ** 2 for c in cells) / n
    bc = sum((c[6] - c[5]) ** 2 for c in cells) / n
    return b, (1 - b / bc if bc > 0 else None), sum(pick(c) for c in cells) / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--violations", action="store_true")
    args = ap.parse_args()

    rows = load(args.path)
    labels = sorted({k[1] for k in rows})

    print("=" * 78)
    print("FreeCiv nested chains — SEPARATE calls vs JOINT call")
    print("=" * 78)

    print("\nCOHERENCE  (P(by turn T) must not fall as T rises)")
    for arm in ("sep", "joint"):
        s = coherence(rows, arm)
        if not s["chains"]:
            continue
        ok = s["chains"] - s["bad"]
        lo, hi = wilson_interval(ok, s["chains"])
        print(f"  {arm:6} coherent chains {ok:3d}/{s['chains']:<3d} "
              f"({100*ok/s['chains']:5.1f}%, CI {100*lo:4.1f}-{100*hi:4.1f})   "
              f"violating pairs {len(s['violations']):3d}/{s['pairs']:<3d} "
              f"({100*len(s['violations'])/s['pairs']:4.1f}%)")

    cells = paired_cells(rows)
    if not cells:
        sys.exit("no paired cells — need both arms in the file")

    print(f"\nACCURACY  (paired: same model, same question, both arms; n={len(cells)})")
    bs, ss, ms = brier_block(cells, lambda c: c[3])
    bj, sj, mj = brier_block(cells, lambda c: c[4])
    print(f"  {'arm':8} {'Brier':>8} {'BSS':>8} {'mean P':>8}")
    print(f"  {'sep':8} {bs:8.4f} {(ss or 0):8.3f} {ms:8.3f}")
    print(f"  {'joint':8} {bj:8.4f} {(sj or 0):8.3f} {mj:8.3f}")
    print(f"  {'delta':8} {bj-bs:+8.4f} {((sj or 0)-(ss or 0)):+8.3f} {mj-ms:+8.3f}"
          f"   ({'JOINT better' if bj < bs else 'SEP better'} on Brier)")

    diffs = [(c[4] - c[5]) ** 2 - (c[3] - c[5]) ** 2 for c in cells]  # joint - sep
    p, n = wilcoxon(diffs)
    better = sum(1 for d in diffs if d < 0)
    worse = sum(1 for d in diffs if d > 0)
    print(f"\n  paired Wilcoxon on per-question Brier: "
          f"joint better on {better}, worse on {worse}, tied on {len(diffs)-better-worse}")
    if p is None:
        print("  p = n/a (too few non-ties)")
    else:
        flag = "[significant at .05]" if p < .05 else "[not significant]"
        print(f"  p = {p:.4g}   {flag}   <- over-counts: 7 cells of one chain "
              f"are not 7 independent facts")

    # The honest unit. One chain forecast by one model is one observation; its
    # 7 cells rise and fall together, so the per-cell test above inflates n
    # about sevenfold. Collapse to mean Brier per (model, chain) and re-test.
    by_chain = defaultdict(lambda: ([], []))
    for c in cells:
        s, j = by_chain[(c[0], c[7], c[1])]
        s.append((c[3] - c[5]) ** 2)
        j.append((c[4] - c[5]) ** 2)
    cd = [statistics.mean(j) - statistics.mean(s) for s, j in by_chain.values()]
    pc, nc = wilcoxon(cd)
    bt = sum(1 for d in cd if d < 0)
    ws = sum(1 for d in cd if d > 0)
    print(f"\n  BY CHAIN (model x chain = one observation, n={len(cd)}): "
          f"joint better on {bt}, worse on {ws}")
    if pc is None:
        print("  p = n/a (too few non-ties)")
    else:
        flag = "[significant at .05]" if pc < .05 else "[not significant]"
        print(f"  median per-chain Brier delta {statistics.median(cd):+.4f}   "
              f"p = {pc:.4g}   {flag}")

    print("\nPER MODEL")
    print(f"  {'model':16} {'Brier sep':>10} {'Brier joint':>12} {'delta':>8} "
          f"{'coh sep':>9} {'coh joint':>10}")
    for lab in labels:
        sub = [c for c in cells if c[0] == lab]
        if not sub:
            continue
        b1, _, _ = brier_block(sub, lambda c: c[3])
        b2, _, _ = brier_block(sub, lambda c: c[4])
        cs = coherence({k: v for k, v in rows.items() if k[1] == lab}, "sep")
        cj = coherence({k: v for k, v in rows.items() if k[1] == lab}, "joint")
        f1 = f"{cs['chains']-cs['bad']}/{cs['chains']}" if cs["chains"] else "-"
        f2 = f"{cj['chains']-cj['bad']}/{cj['chains']}" if cj["chains"] else "-"
        print(f"  {lab:16} {b1:10.4f} {b2:12.4f} {b2-b1:+8.4f} {f1:>9} {f2:>10}")

    print("\nCOVERAGE")
    for arm in ("sep", "joint"):
        got = sum(1 for k, r in rows.items() if k[0] == arm
                  for p_ in r["probs"] if p_ is not None)
        tot = sum(len(r["probs"]) for k, r in rows.items() if k[0] == arm)
        errs = sorted({r["error"].split(":")[0] for k, r in rows.items()
                       if k[0] == arm and r["error"]})
        print(f"  {arm:6} {got}/{tot} answered" + (f"   errors: {', '.join(errs)}" if errs else ""))

    if args.violations:
        for arm in ("sep", "joint"):
            s = coherence(rows, arm)
            if not s["violations"]:
                continue
            print(f"\nVIOLATIONS — {arm}")
            for v in sorted(s["violations"]):
                print(f"  {v[0]:16} {v[1][:38]:38} turn {v[2]}->{v[3]}  "
                      f"{v[4]:.3f} -> {v[5]:.3f}")


if __name__ == "__main__":
    main()
