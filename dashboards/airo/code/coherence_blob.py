"""results/coherence_experiment.json -- the joint-elicitation experiment's
headline numbers as data, so the paper quotes them through numbers.tex
(coh:* macros) instead of retyping docs/coherence-experiment.md.

Stdlib only, no keys, no network; deterministic from the tracked inputs:

  archive/legacy-forecasts/forecast_runs.jsonl   control: one call per rung
  archive/legacy-forecasts/severity_ladder_questions.json
  results/experiments/joint_b_*.jsonl            arm b: one call per cause
  results/experiments/joint_ball_*.jsonl         arm b-all: one call per model
  results/experiments/chain_eval_v2.jsonl        FreeCiv chains, sep vs joint

    python3 code/coherence_blob.py            # writes the blob
    python3 code/coherence_blob.py --check    # exit 1 if the tracked blob is stale
"""
import argparse
import json
import os
import statistics
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

import analyze_chain_eval as chain  # noqa: E402
import analyze_ladder_joint as lad  # noqa: E402

OUT = os.path.join(ROOT, "results", "coherence_experiment.json")
CHAIN = os.path.join(ROOT, "results", "experiments", "chain_eval_v2.jsonl")
ALL_CAUSES = "total"


def cross_cause(cells, rungs, causes, horizons):
    """A specific cause forecast above the all-cause rung that contains it.

    -> (violations, pairs) over every (model, rung, horizon) where both the
    cause and `total` were answered. docs/coherence-experiment.md section 6b.
    """
    bad = pairs = 0
    labels = {lab for (_, _, lab, _) in cells}
    for lab in labels:
        for h in horizons:
            for r in rungs:
                tot = cells.get((ALL_CAUSES, r, lab, h))
                if tot is None:
                    continue
                for c in causes:
                    if c == ALL_CAUSES:
                        continue
                    p = cells.get((c, r, lab, h))
                    if p is None:
                        continue
                    pairs += 1
                    bad += p > tot
    return bad, pairs


def ladder_block():
    spec, rungs, causes, clabel = lad.load_spec()
    labels = [l for l, _ in lad.model_colors()]
    horizons = ["2030", "2050", "2100"]
    control = lad.load_control(rungs)
    arms, _ = lad.load_arms([lad.ARMS_GLOB])
    ctrl_ids = sorted(control)
    pooled_cells = {}
    for rid in ctrl_ids:
        pooled_cells.update(control[rid])
    pooled = [l for rid in ctrl_ids
              for l in lad.ladders(control[rid], rungs, causes, labels, horizons)]

    def stats(lads):
        a = lad.audit(lads)
        return {"ladders": a["ladders"], "coherentLadders": a["ladders"] - a["bad_ladders"],
                "pairs": a["pairs"], "violatingPairs": len(a["violations"])}

    out = {"controlRuns": ctrl_ids, "control": stats(pooled), "arms": {}}
    # Cross-cause on the control is the LAST control run alone (14/312 in
    # section 6b) -- the run the analyzer's level-shift and pinned-rung
    # guardrails also take as the reference -- while the within-ladder
    # figures pool both runs, as the write-up does.
    ref = ctrl_ids[-1]
    out["control"]["crossRun"] = ref
    out["control"]["crossViolations"], out["control"]["crossPairs"] = \
        cross_cause(control[ref], rungs, causes, horizons)
    ck, cn = out["control"]["coherentLadders"], out["control"]["ladders"]
    for key in ("b", "c", "b-all"):
        if key not in arms:
            continue
        st = stats(lad.ladders(arms[key], rungs, causes, labels, horizons))
        st["crossViolations"], st["crossPairs"] = cross_cause(arms[key], rungs, causes, horizons)
        ak, an = st["coherentLadders"], st["ladders"]
        st["fisherP"] = lad.fisher_2x2(ck, cn - ck, ak, an - ak)
        out["arms"][key] = st
    return out


def chain_block():
    rows = chain.load(CHAIN)
    out = {"file": os.path.relpath(CHAIN, ROOT)}
    for arm in ("sep", "joint"):
        c = chain.coherence(rows, arm)
        out[arm] = {"chains": c["chains"], "coherentChains": c["chains"] - c["bad"],
                    "pairs": c["pairs"], "violatingPairs": len(c["violations"])}
    cells = chain.paired_cells(rows)
    bs, ss, ms = chain.brier_block(cells, lambda c: c[3])
    bj, sj, mj = chain.brier_block(cells, lambda c: c[4])
    out["cells"] = len(cells)
    out["sep"]["brier"], out["joint"]["brier"] = bs, bj
    out["models"] = sorted({c[0] for c in cells})
    by_chain = defaultdict(lambda: ([], []))
    for c in cells:
        s, j = by_chain[(c[0], c[7], c[1])]
        s.append((c[3] - c[5]) ** 2)
        j.append((c[4] - c[5]) ** 2)
    cd = [statistics.mean(j) - statistics.mean(s) for s, j in by_chain.values()]
    p, _ = chain.wilcoxon(cd)
    out["byChain"] = {"n": len(cd), "jointBetter": sum(1 for d in cd if d < 0),
                      "jointWorse": sum(1 for d in cd if d > 0),
                      "medianDelta": statistics.median(cd), "wilcoxonP": p}
    return out


def build():
    return {"title": "Joint elicitation and coherence (docs/coherence-experiment.md)",
            "ladder": ladder_block(), "chain": chain_block()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    blob = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        cur = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if cur != blob:
            sys.exit(f"{os.path.relpath(OUT, ROOT)} is stale; run python3 code/coherence_blob.py")
        print("up to date")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(blob)
    print(f"wrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
