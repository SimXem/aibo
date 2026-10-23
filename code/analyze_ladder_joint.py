#!/usr/bin/env python3
"""Score the joint-elicitation experiment against the separate-call control.

Primary endpoint is the LADDER, not the pair. One ladder = one
(model, cause, horizon) cell, and it is coherent or it is not. Pairs inside a
ladder are not independent — one bad rung breaks two pairs — so the pair rate
overstates the sample size. Both are reported; the ladder rate carries the test.

Control comes from results/forecast_runs.jsonl (the separate-call protocol, two
runs). Arms come from results/experiments/joint_*.jsonl. The control's two runs
also give the noise floor: whatever differs between them is what the protocol
does on its own, with no treatment at all.

    python3 code/analyze_ladder_joint.py
    python3 code/analyze_ladder_joint.py --arms results/experiments/joint_b_*.jsonl

Stdlib only, no keys, no network — same rules as the build pipeline.
"""
import argparse
import glob
import json
import math
import os
import statistics
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from redlines.registry import model_colors  # noqa: E402
from redlines.stats import wilson_interval  # noqa: E402

# The ladder set and its one-call-per-rung log were retired on 2026-08-14
# (the Auto-ARC swap, archive/legacy-forecasts/README.md); the experiment
# reads them from the archive, where they are kept so this stays reproducible.
_ARCHIVE = os.path.join(ROOT, "archive", "legacy-forecasts")
LADDER = os.path.join(_ARCHIVE, "severity_ladder_questions.json")
RUNLOG = os.path.join(_ARCHIVE, "forecast_runs.jsonl")
ARMS_GLOB = os.path.join(ROOT, "results", "experiments", "joint_*.jsonl")

CEILING = 99.0   # a rung at or above this is pinned (issue #7 territory)


# ---------------------------------------------------------------- loading

def load_spec():
    spec = json.load(open(LADDER))
    return (spec,
            [r["rung"] for r in spec["rungs"]],
            [c["key"] for c in spec["causes"]],
            {c["key"]: c["label"] for c in spec["causes"]})


def load_control(rungs):
    """-> {run_id: {(cause, rung, label, horizon): percent}}"""
    out = defaultdict(dict)
    for ln in open(RUNLOG):
        r = json.loads(ln)
        qid = r["question_id"]
        if not qid.startswith("ladder:"):
            continue
        _, cause, rung = qid.split(":", 2)
        for f in (r["forecasts"] or []):
            out[r["run_id"]][(cause, rung, r["label"], f["horizon"])] = \
                100 * f["probability"]
    return dict(out)


def load_arms(patterns):
    """-> {arm_key: {cell: percent}}, plus per-arm evidence counts."""
    grids, ev = defaultdict(dict), defaultdict(list)
    for pat in patterns:
        for path in sorted(glob.glob(pat)):
            for ln in open(path):
                r = json.loads(ln)
                # scope belongs in the key: a scope=all run carries arm "b" too,
                # and merging it into arm b would silently pool two protocols.
                key = r["arm"]
                if r.get("scope") == "all":
                    key += "-all"
                if r.get("order", "ladder") != "ladder":
                    key += f"/{r['order']}"
                for rung, byh in (r["grid"] or {}).items():
                    for h, p in byh.items():
                        grids[key][(r["cause"], rung, r["label"], h)] = 100 * p
                ev[key].append(len(r.get("evidence") or []))
    return dict(grids), dict(ev)


# ---------------------------------------------------------------- metrics

def ladders(cells, rungs, causes, labels, horizons):
    """-> list of (cause, label, horizon, [(rung, percent), ...]) in rung order."""
    out = []
    for c in causes:
        for lab in labels:
            for h in horizons:
                seq = [(r, cells[(c, r, lab, h)]) for r in rungs
                       if (c, r, lab, h) in cells]
                if len(seq) >= 2:
                    out.append((c, lab, h, seq))
    return out


def audit(lads):
    """Coherence at both units of analysis, plus the violation list."""
    viol, pairs, bad = [], 0, 0
    for c, lab, h, seq in lads:
        hit = False
        for (ra, pa), (rb, pb) in zip(seq, seq[1:]):
            pairs += 1
            if pb > pa:
                hit = True
                viol.append((lab, c, h, ra, pa, rb, pb))
        bad += hit
    return {"ladders": len(lads), "bad_ladders": bad, "pairs": pairs,
            "violations": viol}


def fisher_2x2(a, b, c, d):
    """Two-sided Fisher exact p for [[a,b],[c,d]]. Exact, stdlib, small counts."""
    n = a + b + c + d
    r1, c1 = a + b, a + c

    def prob(x):
        return (math.comb(r1, x) * math.comb(n - r1, c1 - x)) / math.comb(n, c1)

    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    obs = prob(a)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1)
                        if prob(x) <= obs * (1 + 1e-9)))


def degeneracy(lads):
    """Is a coherent ladder a reasoned ladder, or a mechanical one?

    Two tells. TIES: adjacent rungs given the same number — coherent by the
    letter of the rule, empty of information. FLAT SLOPE: a constant drop per
    rung in log space means the model applied a divisor, not a judgement, so the
    spread of the per-step log drop within a ladder goes to zero.
    """
    ties, steps, cvs = 0, 0, []
    for _, _, _, seq in lads:
        drops = []
        for (_, pa), (_, pb) in zip(seq, seq[1:]):
            steps += 1
            if pb == pa:
                ties += 1
            if pa > 0 and pb > 0:
                drops.append(math.log10(pa) - math.log10(pb))
        pos = [d for d in drops if d > 0]
        if len(pos) >= 3 and statistics.mean(pos) > 0:
            cvs.append(statistics.pstdev(pos) / statistics.mean(pos))
    return {"ties": ties, "steps": steps,
            "slope_cv": statistics.median(cvs) if cvs else None, "n_cv": len(cvs)}


def ceiling_count(cells):
    return sum(1 for v in cells.values() if v >= CEILING)


def level_shift(a, b):
    """Median |delta| between two cell maps, in log10 units and in points."""
    keys = set(a) & set(b)
    logs, pts = [], []
    for k in keys:
        pa, pb = a[k], b[k]
        pts.append(abs(pb - pa))
        if pa > 0 and pb > 0:
            logs.append(abs(math.log10(pb) - math.log10(pa)))
    if not keys:
        return None
    return {"n": len(keys),
            "log10": statistics.median(logs) if logs else None,
            "points": statistics.median(pts)}


def medians_by_cell(cells, rungs, causes, horizons, labels):
    """Cross-model median per (cause, rung, horizon) — the dashboard's number."""
    out = {}
    for c in causes:
        for r in rungs:
            for h in horizons:
                vs = [cells[(c, r, lab, h)] for lab in labels
                      if (c, r, lab, h) in cells]
                if vs:
                    out[(c, r, h)] = statistics.median(vs)
    return out


# ---------------------------------------------------------------- report

def line(name, st):
    k = st["ladders"] - st["bad_ladders"]
    lo, hi = wilson_interval(k, st["ladders"]) if st["ladders"] else (0, 0)
    pv = len(st["violations"])
    return (f"  {name:26} coherent ladders {k:3d}/{st['ladders']:<3d} "
            f"({100*k/st['ladders']:5.1f}%, CI {100*lo:4.1f}-{100*hi:4.1f})   "
            f"violating pairs {pv:3d}/{st['pairs']:<3d} ({100*pv/st['pairs']:4.1f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="*", default=[ARMS_GLOB])
    ap.add_argument("--violations", action="store_true",
                    help="print every surviving violation per arm")
    ap.add_argument("--levels", action="store_true",
                    help="per-cell median table, control vs each arm — the "
                         "level shift is structured, not noise, so the summary "
                         "median hides it")
    args = ap.parse_args()

    spec, rungs, causes, clabel = load_spec()
    labels = [l for l, _ in model_colors()]
    horizons = ["2030", "2050", "2100"]

    control = load_control(rungs)
    arms, ev = load_arms(args.arms)
    if not arms:
        sys.exit(f"no arm files matched {args.arms} — run archive/litellm-runners/run_ladder_joint.py first")

    ctrl_ids = sorted(control)
    ctrl_lads = {rid: ladders(control[rid], rungs, causes, labels, horizons)
                 for rid in ctrl_ids}
    pooled_ctrl = [l for rid in ctrl_ids for l in ctrl_lads[rid]]

    print("=" * 78)
    print("COHERENCE — separate calls (control) vs joint elicitation")
    print("=" * 78)
    print("\nCONTROL — one call per rung")
    for rid in ctrl_ids:
        print(line(rid, audit(ctrl_lads[rid])))
    cst = audit(pooled_ctrl)
    print(line("pooled control", cst))

    print("\nJOINT — one call per cause, all rungs together")
    astats = {}
    for key in sorted(arms):
        lads = ladders(arms[key], rungs, causes, labels, horizons)
        astats[key] = (audit(lads), lads)
        print(line(f"arm {key}", astats[key][0]))

    # ------------------------------------------------ primary test
    print("\nPRIMARY TEST — coherent-ladder proportion vs pooled control")
    ck, cn = cst["ladders"] - cst["bad_ladders"], cst["ladders"]
    for key, (st, _) in astats.items():
        ak, an = st["ladders"] - st["bad_ladders"], st["ladders"]
        p = fisher_2x2(ck, cn - ck, ak, an - ak)
        d = 100 * (ak / an - ck / cn) if an and cn else 0
        print(f"  arm {key:8} {100*ak/an:5.1f}% vs {100*ck/cn:5.1f}%  "
              f"({d:+5.1f} points)   Fisher p = {p:.4g}"
              f"{'   [significant at .05]' if p < .05 else ''}")
    if len(ctrl_ids) == 2:
        a = audit(ctrl_lads[ctrl_ids[0]])
        b = audit(ctrl_lads[ctrl_ids[1]])
        ak, an = a["ladders"] - a["bad_ladders"], a["ladders"]
        bk, bn = b["ladders"] - b["bad_ladders"], b["ladders"]
        print(f"  NOISE FLOOR: the two control runs differ by "
              f"{100*bk/bn - 100*ak/an:+.1f} points with no treatment at all "
              f"(Fisher p = {fisher_2x2(ak, an-ak, bk, bn-bk):.4g})")

    # ------------------------------------------------ is it a real fix?
    print("\nGUARDRAIL 1 — is the coherence earned or mechanical?")
    print(f"  {'arm':12} {'ties':>10}  {'slope CV':>9}   (low CV = constant divisor per rung)")
    for name, lads in [("control", pooled_ctrl)] + [(k, v[1]) for k, v in astats.items()]:
        d = degeneracy(lads)
        cv = f"{d['slope_cv']:.2f}" if d["slope_cv"] is not None else "  n/a"
        print(f"  {name:12} {d['ties']:4d}/{d['steps']:<5d}  {cv:>9}   (n={d['n_cv']})")

    print("\nGUARDRAIL 2 — level shift (does the headline number move?)")
    if len(ctrl_ids) == 2:
        s = level_shift(
            medians_by_cell(control[ctrl_ids[0]], rungs, causes, horizons, labels),
            medians_by_cell(control[ctrl_ids[1]], rungs, causes, horizons, labels))
        print(f"  control vs control   median |delta| {s['points']:5.2f} points, "
              f"{s['log10']:.2f} log10  (n={s['n']} cells)  <- noise floor")
    ref = medians_by_cell(control[ctrl_ids[-1]], rungs, causes, horizons, labels)
    for key in sorted(arms):
        s = level_shift(ref, medians_by_cell(arms[key], rungs, causes, horizons, labels))
        print(f"  arm {key:8} vs control  median |delta| {s['points']:5.2f} points, "
              f"{s['log10']:.2f} log10  (n={s['n']} cells)")

    print("\nGUARDRAIL 3 — pinned rungs (>= %.0f%%, issue #7)" % CEILING)
    print(f"  {'control ' + ctrl_ids[-1]:26} {ceiling_count(control[ctrl_ids[-1]]):3d} cells")
    for key in sorted(arms):
        print(f"  {'arm ' + key:26} {ceiling_count(arms[key]):3d} cells")

    print("\nGUARDRAIL 4 — coverage and cost")
    full = len(causes) * len(rungs) * len(labels) * len(horizons)
    print(f"  {'control ' + ctrl_ids[-1]:26} {len(control[ctrl_ids[-1]]):3d}/{full} cells filled")
    for key in sorted(arms):
        e = ev.get(key, [])
        print(f"  {'arm ' + key:26} {len(arms[key]):3d}/{full} cells filled, "
              f"{len(e)} calls, {sum(e)} evidence items "
              f"({sum(e)/len(e):.1f} per call)" if e else "")

    if args.levels:
        keys = sorted(arms)
        amed = {k: medians_by_cell(arms[k], rungs, causes, horizons, labels)
                for k in keys}
        for h in horizons:
            print(f"\nLEVELS {h} — cross-model median, percent"
                  f"   (* = moved more than 1 point and more than 25%)")
            head = "".join(f"{'arm ' + k:>10}" for k in keys)
            print(f"  {'cause':10}{'rung':>11}{'control':>10}{head}{'  delta':>9}")
            for c in causes:
                for r in rungs:
                    if (c, r, h) not in ref:
                        continue
                    base = ref[(c, r, h)]
                    vals = [amed[k].get((c, r, h)) for k in keys]
                    d = vals[0] - base if vals and vals[0] is not None else None
                    star = " *" if d is not None and abs(d) > max(1.0, .25 * base) else ""
                    cells = "".join(f"{v:10.4g}" if v is not None else f"{'--':>10}"
                                    for v in vals)
                    delta = f"{d:+9.3g}" if d is not None else f"{'--':>9}"
                    print(f"  {c:10}{r:>11}{base:10.4g}{cells}{delta}{star}")

    if args.violations:
        for key in sorted(arms):
            print(f"\nSURVIVING VIOLATIONS — arm {key}")
            for v in sorted(astats[key][0]["violations"]):
                lab, c, h, ra, pa, rb, pb = v
                print(f"  {lab:16} {clabel[c]:26} {h}  {ra} {pa:g} -> {rb} {pb:g}")


if __name__ == "__main__":
    main()
