"""Coverage (dose) ladder on the v2 worlds — v3 rung mining (DESIGN.md, 2026-08-27).

Same 4 worlds, reports, question and horizons as worlds.json; only the leading
region's vaccine coverage varies (day 21 and 95% leaky efficacy stay fixed).
Because the campaign fires on day 21, every vaccinated run is identical to its
control through day 20, so the matched seeds at any coverage are exactly v2's
matched control seeds (verified: 0/1,200 cached vax rows differ at day 20). We
simulate only those seeds, per leader beta, at each grid coverage, and cache the
full day-0..90 ever-infected series in .sim_cache_dose.json.

For every world x coverage x horizon: P*_int = crossed P(Riverton > Southbay)
over matched (R, S) pairs (leader = vaccinated arm, follower = control arm),
bootstrap CI, and MARGIN = median over crossed pairs of (follower - leader)/N
(> 0: the follower is ahead, i.e. the baseline answer flipped). A coverage is
CERTIFIED for a world when at BOTH horizons P*_int is within .05 of 0 or 1 with
CI half-width <= .03, and both horizons agree on flip / no-flip.

  uv run python results/causal/starsim_causal/mine_dose.py                                  # simulate (cached) + print grid
  uv run python results/causal/starsim_causal/mine_dose.py --select --target-margin -0.10 --tag m10   # per-world rung by margin
  uv run python results/causal/starsim_causal/mine_dose.py --select --coverage 0.50 --tag c50        # one global coverage
Writes worlds_<tag>.json (same schema/item_ids as worlds.json) for run.py --worlds.
"""
import argparse
import json
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from pandemic_world.runner import N_AGENTS, run_region
import mine_worlds as mw

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".sim_cache_dose.json"
GRID = [round(0.05 * k, 2) for k in range(1, 18)]  # 0.05 .. 0.85 (0.90 is the v2 rung)


def key(beta, cov, seed):
    return f"{beta:.3f}|{cov:.2f}|{seed}"


def one_sim(args):
    beta, cov, seed = args
    s = run_region(beta, True, mw.VAX["efficacy"], mw.VAX["day"], cov, seed, p_death=mw.P_DEATH)
    cum, act = s["cumulative_cases"], s["active_infections"]
    seeds0 = int(round(act[0] - cum[0]))
    return key(beta, cov, seed), [int(round(seeds0 + c)) for c in cum]


def load_v2():
    rows = mw.simulate_all()
    A = {b: mw.arrays(rows, b, False) for b in mw.BETAS}
    disp, matched = {}, {}
    for b in mw.BETAS:
        ctl = A[b]
        k = int(np.argmin(np.abs(ctl["ever20"] - np.median(ctl["ever20"]))))
        disp[b] = dict(seed=int(ctl["seed"][k]), ever20=float(ctl["ever20"][k]), row=ctl["rows"][k])
        m = np.abs(ctl["ever20"] - disp[b]["ever20"]) <= mw.MATCH_BAND * disp[b]["ever20"]
        matched[b] = [int(s) for s in ctl["seed"][m]]
    worlds = json.load(open(mw.OUT))["worlds"]
    return A, disp, matched, worlds


def ensure_sims(leader_betas, matched, grid):
    cache = json.load(open(CACHE)) if CACHE.exists() else {}
    jobs = [(b, c, s) for b in leader_betas for c in grid for s in matched[b] if key(b, c, s) not in cache]
    if jobs:
        print(f"simulating {len(jobs)} missing (beta, coverage, seed) runs ...", flush=True)
        with Pool() as pool:
            for i, (k, ever) in enumerate(pool.imap_unordered(one_sim, jobs, chunksize=16), 1):
                cache[k] = ever
                if i % 1000 == 0:
                    print(f"  {i}/{len(jobs)}", flush=True)
                    json.dump(cache, open(CACHE, "w"))
        json.dump(cache, open(CACHE, "w"))
    return cache


def series(cache, beta, cov, seeds, t):
    return np.array([cache[key(beta, cov, s)][t] for s in seeds])


def evaluate(world, cov, cache, A, matched, rng):
    """P*_int, CI, margin at each horizon for one world at one coverage."""
    br, bs, leader = world["beta_r"], world["beta_s"], world["leader"]
    bl, bf = (br, bs) if leader == "R" else (bs, br)
    out = {}
    for t in mw.HORIZONS:
        L = series(cache, bl, cov, matched[bl], t)                        # leader, vaccinated
        F = A[bf][f"ever{t}"][np.isin(A[bf]["seed"], matched[bf])]       # follower, control
        R, S = (L, F) if leader == "R" else (F, L)
        p = mw.crossed_p(R, S)
        ci = mw.boot_ci(R, S, rng)
        margin = float(np.median(F[None, :] - L[:, None]) / N_AGENTS)
        out[t] = dict(p_int=p, p_int_ci=ci, margin=margin)
    return out


def certify(base, ev):
    """-> 'flip' | 'noflip' | None ; requires both horizons certified and agreeing."""
    verdicts = set()
    for t, h in ev.items():
        p0, p1, ci = base[t]["p_base"], h["p_int"], h["p_int_ci"]
        if (ci[1] - ci[0]) / 2 > 0.03:
            return None
        side0 = p0 >= 0.95
        if p1 >= 0.95:
            verdicts.add("noflip" if side0 else "flip")
        elif p1 <= 0.05:
            verdicts.add("flip" if side0 else "noflip")
        else:
            return None
    return verdicts.pop() if len(verdicts) == 1 else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--select", action="store_true", help="write worlds_<tag>.json for the chosen rung")
    ap.add_argument("--coverage", type=float, default=None, help="one global coverage for every world")
    ap.add_argument("--target-margin", type=float, default=None,
                    help="per world, the certified coverage whose day-60 margin is closest to this (sign = flip/no-flip)")
    ap.add_argument("--tag", default=None, help="output suffix: worlds_<tag>.json")
    a = ap.parse_args()

    A, disp, matched, worlds = load_v2()
    v2_items = {i["item_id"]: i for i in json.load(open(mw.OUT))["items"]}
    leader_betas = sorted({w["beta_r"] if w["leader"] == "R" else w["beta_s"] for w in worlds})
    grid = sorted(set(GRID) | ({a.coverage} if a.coverage else set()))
    cache = ensure_sims(leader_betas, matched, grid)
    rng = np.random.default_rng(11)

    table = {}
    for w in worlds:
        base = {t: dict(p_base=v2_items[f"{w['world_id']}_{w['leader']}lead_d{t}"]["truth_base"]) for t in mw.HORIZONS}
        print(f"\n{w['world_id']}  beta R/S {w['beta_r']}/{w['beta_s']}  leader {w['leader']}  "
              f"(base P* d40={base[40]['p_base']:.2f} d60={base[60]['p_base']:.2f}; v2 rung = 0.90)")
        print("  cov   | d40 P*_int  CI±    margin | d60 P*_int  CI±    margin | verdict")
        for cov in grid:
            ev = evaluate(w, cov, cache, A, matched, rng)
            v = certify(base, ev)
            table[(w["world_id"], cov)] = (ev, v)
            cells = " | ".join(f"{ev[t]['p_int']:.3f}  {(ev[t]['p_int_ci'][1]-ev[t]['p_int_ci'][0])/2:.3f}  {ev[t]['margin']:+.3f}"
                               for t in mw.HORIZONS)
            print(f"  {cov:.2f}  |     {cells} | {v or '-'}")

    if not a.select:
        return
    if (a.coverage is None) == (a.target_margin is None):
        raise SystemExit("--select needs exactly one of --coverage / --target-margin")
    tag = a.tag or (f"c{int(round(a.coverage*100))}" if a.coverage else f"m{int(round(abs(a.target_margin)*100))}")

    out_worlds, out_items = [], []
    for w in worlds:
        if a.coverage is not None:
            cov = a.coverage
        else:
            want = "flip" if a.target_margin > 0 else "noflip"
            ok = [(c, table[(w["world_id"], c)][0]) for c in grid if table[(w["world_id"], c)][1] == want]
            if not ok:
                raise SystemExit(f"{w['world_id']}: no certified {want} coverage on the grid")
            cov = min(ok, key=lambda ce: abs(ce[1][60]["margin"] - a.target_margin))[0]
        ev, verdict = table[(w["world_id"], cov)]
        if verdict is None:
            print(f"WARNING {w['world_id']} @ {cov:.2f} is NOT certified (P* intermediate or CI too wide)")
        nw = dict(w, intervention=mw.intervention_text(w["leader"], cov), coverage=cov, verdict=verdict)
        out_worlds.append(nw)
        for t in mw.HORIZONS:
            v2 = v2_items[f"{w['world_id']}_{w['leader']}lead_d{t}"]
            h = ev[t]
            out_items.append(dict(v2, intervention=nw["intervention"],
                                  truth_int=h["p_int"], truth_int_ci=h["p_int_ci"],
                                  delta_do=h["p_int"] - v2["truth_base"], margin_int=h["margin"],
                                  config=dict(v2["config"], coverage=cov)))
            print(f"{v2['item_id']:18s} cov={cov:.2f} base={v2['truth_base']:.3f} int={h['p_int']:.3f} "
                  f"delta_do={h['p_int']-v2['truth_base']:+.3f} margin={h['margin']:+.3f} [{verdict}]")
    design = dict(json.load(open(mw.OUT))["design"])
    design["vax"] = dict(design["vax"], coverage="per-world (see worlds[].coverage)")
    design["rung"] = dict(tag=tag, global_coverage=a.coverage, target_margin=a.target_margin,
                          coverages={w["world_id"]: w["coverage"] for w in out_worlds})
    out = HERE / f"worlds_{tag}.json"
    json.dump(dict(design=design, worlds=out_worlds, items=out_items), open(out, "w"), indent=1)
    print(f"[saved] {len(out_worlds)} worlds, {len(out_items)} items -> {out}")


if __name__ == "__main__":
    main()
