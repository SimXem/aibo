"""Certified effect sizes on the single-region worlds by vaccine coverage:
median new infections after day 20 (day 60), matched seeds, ± = half the p10–p90 range.
Simulates missing (beta, coverage) combos into starsim_causal/.sim_cache_dose.json.

  uv run python results/causal/starsim_single/effect_sizes.py
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "starsim_causal"))
import mine_worlds as mw  # noqa: E402
import mine_dose as md  # noqa: E402

COVS = [0.10, 0.25, 0.50, 0.75]


def main():
    W = json.load(open(HERE / "worlds.json"))
    rows = mw.simulate_all()
    matched = {}
    for w in W["worlds"]:
        ctl = mw.arrays(rows, w["beta"], False)
        matched[w["beta"]] = [int(s) for s in ctl["seed"][np.abs(ctl["ever20"] - w["c20"]) <= mw.MATCH_BAND * w["c20"]]]
    cache = md.ensure_sims(list(matched), matched, COVS)
    print("median NEW infections after day 20 (day 60) by coverage; ± = half the p10–p90 range")
    print(f"{'world':6s} {'R0':>4s} {'0%':>10s} " + " ".join(f"{c:>10.0%}" for c in COVS + [0.9]))
    for w in W["worlds"]:
        b = w["beta"]; ctl = mw.arrays(rows, b, False); vax = mw.arrays(rows, b, True)
        m = np.isin(ctl["seed"], matched[b])
        def fmt(x):
            return f"{np.median(x):5.0f}±{(np.quantile(x, .9) - np.quantile(x, .1)) / 2:3.0f}"
        cells = [fmt(ctl["ever60"][m] - ctl["ever20"][m])]
        for c in COVS:
            x = np.array([cache[md.key(b, c, s)][60] - cache[md.key(b, c, s)][20] for s in matched[b]]); cells.append(fmt(x))
        cells.append(fmt(vax["ever60"][m] - vax["ever20"][m]))
        print(f"{w['world_id']:6s} {w['r0']:4.1f} " + " ".join(f"{c:>10s}" for c in cells))


if __name__ == "__main__":
    main()
