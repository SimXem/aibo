"""Fixed climatology reference for CRPS skill: the pooled distribution of the target
(new infections after day 20, by horizon) over all worlds x coverages {0, 25, 50, 75, 90}%,
matched seeds. Independent of which rung is being scored. -> climatology.json

  uv run python results/causal/starsim_single/climatology.py
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "starsim_causal"))
import mine_worlds as mw  # noqa: E402
import mine_dose as md  # noqa: E402

COVS = [0.25, 0.50, 0.75]
TAU = {"p10": 0.10, "p25": 0.25, "p50": 0.50, "p75": 0.75, "p90": 0.90}


def main():
    W = json.load(open(HERE / "worlds.json"))
    rows = mw.simulate_all()
    matched = {}
    for w in W["worlds"]:
        ctl = mw.arrays(rows, w["beta"], False)
        matched[w["beta"]] = [int(s) for s in ctl["seed"][np.abs(ctl["ever20"] - w["c20"]) <= mw.MATCH_BAND * w["c20"]]]
    dose = md.ensure_sims(list(matched), matched, COVS)
    out = {}
    for t in W["design"]["horizons"]:
        pool = []
        for w in W["worlds"]:
            b = w["beta"]; ctl = mw.arrays(rows, b, False); vax = mw.arrays(rows, b, True); m = np.isin(ctl["seed"], matched[b])
            pool += list(ctl[f"ever{t}"][m] - ctl["ever20"][m]) + list(vax[f"ever{t}"][m] - vax["ever20"][m])
            for c in COVS:
                pool += [dose[md.key(b, c, s)][t] - dose[md.key(b, c, s)][20] for s in matched[b]]
        pool = np.array(pool, float)
        out[str(t)] = dict(n=int(len(pool)), coverages=[0.0] + COVS + [0.9], **{k: float(np.quantile(pool, q)) for k, q in TAU.items()})
        print(t, out[str(t)])
    json.dump(out, open(HERE / "climatology.json", "w"), indent=1)


if __name__ == "__main__":
    main()
