"""Single-region continuous design (v4, 2026-08-28): one SIR population, stated
parameters, report through day 20; the model forecasts NEW infections between
the end of day 20 and day t as quantiles (p10/p25/p50/p75/p90), once with no
intervention and once with a vaccination campaign on day 21 (separate prompts).

Worlds = the four v2 betas (R0 1.8/2.4/3.0/3.9); display seed and ±15% day-20
matching exactly as in starsim_causal/mine_worlds.py; sims come from its cache
(control arm and the 90%-coverage vaccinated arm, 300 seeds each).
Truth per item and arm = the matched seeds' distribution of ever[t] − ever[20]
(samples stored for CRPS scoring).

  uv run python results/causal/starsim_single/mine_single.py   # -> starsim_single/worlds.json
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "starsim_causal"))
import mine_worlds as mw  # noqa: E402
import mine_dose as md  # noqa: E402
from pandemic_world.runner import N_AGENTS, N_CONTACTS  # noqa: E402

OUT = HERE / "worlds.json"
HORIZONS = [40, 60]
QS = {"p10": 0.10, "p25": 0.25, "p50": 0.50, "p75": 0.75, "p90": 0.90}
REGION = "Riverton"
Q_TEXT = ("How many people in Riverton will be newly infected between the end of day 20 and the end of "
          "day {t}? (That is: cumulative infections at day {t} minus the {c20} already infected by day 20.)")


def report(beta, disp):
    traj = " -> ".join(f"d{d}:{disp['ever'][str(d)]}" for d in (0, 5, 10, 15, 20))
    return f"""PANDEMIC WORLD REPORT — Day 20

One isolated region, {REGION}: {N_AGENTS:,} people, no travel in or out.
Disease model: SIR (susceptible -> infectious -> recovered; no deaths). Infected people are \
infectious for {mw.DUR_INF} days on average, then recover with permanent immunity. Each person has \
about {N_CONTACTS} contacts per day. The simulation is agent-based and stochastic.
  Transmission probability per contact per day {beta:.3f} (basic reproduction number \
R0 ≈ {mw.r0(beta):.1f}); {disp['seeds0']} people infectious at day 0.

Observed cumulative infections at the end of each day (people ever infected, including those infectious at day 0):
  {REGION}: {traj}   (day 20: {disp['active']['20']} currently infectious)"""


def intervention_text(coverage=mw.VAX["coverage"]):
    eff, cov, day = int(mw.VAX["efficacy"] * 100), int(round(coverage * 100)), mw.VAX["day"]
    return (f"{REGION} will run a vaccination campaign on day {day} ({eff}% efficacy, {cov}% coverage): "
            f"on day {day}, {cov}% of {REGION}'s population is vaccinated, and vaccination reduces a "
            f"vaccinated person's probability of infection per exposure by {eff}%.")


def truth(samples):
    s = np.sort(samples.astype(float))
    return dict(n=int(len(s)), mean=float(s.mean()), sd=float(s.std(ddof=1)),
                **{k: float(np.quantile(s, q)) for k, q in QS.items()}, samples=[float(x) for x in s])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coverage", type=float, default=mw.VAX["coverage"], help="vaccine coverage (default 0.90)")
    ap.add_argument("--tag", default=None, help="write worlds_<tag>.json instead of worlds.json")
    a = ap.parse_args()
    out = HERE / (f"worlds_{a.tag}.json" if a.tag else "worlds.json")
    rows = mw.simulate_all()
    dose = None
    if abs(a.coverage - mw.VAX["coverage"]) > 1e-9:
        matched = {}
        for beta in mw.BETAS:
            ctl = mw.arrays(rows, beta, False)
            k = int(np.argmin(np.abs(ctl["ever20"] - np.median(ctl["ever20"]))))
            c20 = ctl["rows"][k]["ever"]["20"]
            matched[beta] = [int(s) for s in ctl["seed"][np.abs(ctl["ever20"] - c20) <= mw.MATCH_BAND * c20]]
        dose = md.ensure_sims(mw.BETAS, matched, [a.coverage])
    worlds, items = [], []
    for w, beta in enumerate(mw.BETAS):
        ctl, vax = mw.arrays(rows, beta, False), mw.arrays(rows, beta, True)
        k = int(np.argmin(np.abs(ctl["ever20"] - np.median(ctl["ever20"]))))
        disp = ctl["rows"][k]
        c20 = disp["ever"]["20"]
        m = np.abs(ctl["ever20"] - c20) <= mw.MATCH_BAND * c20      # identical in both arms (vax fires day 21)
        rep = report(beta, disp)
        world = dict(world_id=f"w{w}", beta=beta, r0=mw.r0(beta), seed=int(ctl["seed"][k]), c20=int(c20),
                     n_matched=int(m.sum()), report=rep, coverage=a.coverage, intervention=intervention_text(a.coverage))
        worlds.append(world)
        seeds = [int(s) for s in ctl["seed"][m]]
        for t in HORIZONS:
            tb = truth(ctl[f"ever{t}"][m] - ctl["ever20"][m])
            if dose is None:
                ti = truth(vax[f"ever{t}"][m] - vax["ever20"][m])
            else:
                ti = truth(np.array([dose[md.key(beta, a.coverage, s)][t] - dose[md.key(beta, a.coverage, s)][20] for s in seeds]))
            items.append(dict(item_id=f"w{w}_d{t}", world_id=world["world_id"], horizon=t, beta=beta, c20=int(c20),
                              question=Q_TEXT.format(t=t, c20=c20), report=rep, intervention=world["intervention"],
                              upper=N_AGENTS - int(c20), truth_base=tb, truth_int=ti,
                              effect_median=ti["p50"] - tb["p50"]))
            print(f"{items[-1]['item_id']:8s} beta {beta:.3f} R0 {mw.r0(beta):.1f} c20={c20:4d} n={m.sum():3d} | "
                  f"base p10/p50/p90 {tb['p10']:6.0f} {tb['p50']:6.0f} {tb['p90']:6.0f} | "
                  f"int {ti['p10']:6.0f} {ti['p50']:6.0f} {ti['p90']:6.0f} | effect {ti['p50']-tb['p50']:+.0f}")
    json.dump(dict(design=dict(n_agents=N_AGENTS, n_contacts=N_CONTACTS, dur_inf=mw.DUR_INF, p_death=mw.P_DEATH,
                               betas=mw.BETAS, snapshot_day=mw.SNAPSHOT, horizons=HORIZONS, quantiles=QS,
                               match_band=mw.MATCH_BAND, n_seeds=mw.N_SEEDS, vax=dict(mw.VAX, coverage=a.coverage),
                               target="new infections after day 20", rung=dict(tag=a.tag, coverage=a.coverage) if a.tag else None),
                   worlds=worlds, items=items), open(out, "w"), indent=1)
    print(f"[saved] {len(worlds)} worlds, {len(items)} items -> {out}")


if __name__ == "__main__":
    main()
