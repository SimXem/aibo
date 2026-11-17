"""v2 worlds + items for the StarSim causal bench (design agreed 2026-08-27).

WORLD: two isolated SIR populations (5,000 agents, ~6 contacts/day, 10-day
infectious period, NO deaths), per-region beta from {0.03, 0.04, 0.05, 0.065}
(R0 ≈ 1.8 / 2.4 / 3.0 / 3.9). The world report states the parameters and the
observed ever-infected counts through day 20 for one displayed run per region.
ITEM: (world, horizon) -> "Will Riverton have more cumulative infections than
Southbay at day {t}?"  Each item is asked in two SEPARATE prompts:
  baseline      report + question
  intervention  report + PLANNED INTERVENTION (the leading region vaccinates on
                day 21, 90% coverage, 95% efficacy) + question

Ground truth is conditioned on the shown report: per region and arm, keep seeds
whose day-20 ever-infected count is within ±15% of the displayed run's; P* =
crossed fraction of matched (R-seed, S-seed) pairs resolving YES (regions are
independent, so crossing is valid); bootstrap CIs over the two seed samples.
A world is CERTIFIED when, at BOTH horizons, base P* ≥ .95 or ≤ .05, the
intervention P* is on the opposite side (a full flip), both CI half-widths
≤ .03, and ≥ 50 matched seeds per region per arm. Four worlds are chosen: two
where Riverton leads, two where Southbay leads (sign balance), distinct beta
pairs, strongest flips first.

Run (from the repo root):  uv run python results/causal/starsim_causal/mine_worlds.py
Delete .sim_cache_v2.json to re-simulate (4 betas × 300 seeds × 2 arms).
"""
import json
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from pandemic_world.runner import N_AGENTS, N_CONTACTS, run_region

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".sim_cache_v2.json"
OUT = HERE / "worlds.json"

BETAS = [0.030, 0.040, 0.050, 0.065]
DUR_INF = 10
P_DEATH = 0.0
N_SEEDS = 300
SNAPSHOT = 20
HORIZONS = [40, 60]
CHECKPOINTS = [0, 5, 10, 15, 20, 40, 60]
MATCH_BAND = 0.15
BOOT = 500
MIN_N = 50
VAX = dict(efficacy=0.95, day=21, coverage=0.90)
NAMES = {"R": "Riverton", "S": "Southbay"}
Q_TEXT = "Will Riverton have more cumulative infections than Southbay at day {t}?"


def r0(beta: float) -> float:
    return beta * N_CONTACTS * DUR_INF


def one_sim(args):
    beta, seed, vax = args
    s = run_region(beta, vax, VAX["efficacy"], VAX["day"], VAX["coverage"], seed, p_death=P_DEATH)
    cum, act = s["cumulative_cases"], s["active_infections"]
    seeds0 = int(round(act[0] - cum[0]))          # infectious at day 0 before any transmission
    return dict(beta=beta, seed=seed, vax=vax, seeds0=seeds0,
                ever={str(d): int(round(seeds0 + cum[d])) for d in CHECKPOINTS},
                active={str(d): int(round(act[d])) for d in (0, 20)})


def simulate_all():
    if CACHE.exists():
        return json.load(open(CACHE))
    jobs = [(b, s, v) for b in BETAS for v in (False, True) for s in range(1, N_SEEDS + 1)]
    with Pool() as pool:
        rows = pool.map(one_sim, jobs, chunksize=8)
    json.dump(rows, open(CACHE, "w"))
    return rows


def arrays(rows, beta, vax):
    sub = sorted((r for r in rows if r["beta"] == beta and r["vax"] == vax), key=lambda r: r["seed"])
    out = {"seed": np.array([r["seed"] for r in sub]), "rows": sub}
    for d in CHECKPOINTS:
        out[f"ever{d}"] = np.array([r["ever"][str(d)] for r in sub])
    return out


def crossed_p(av, bv):
    """P(a > b) over the full cross of two 1-D samples (strict >; ties = NO)."""
    return float((av[:, None] > bv[None, :]).mean())


def boot_ci(av, bv, rng):
    ps = [crossed_p(rng.choice(av, len(av)), rng.choice(bv, len(bv))) for _ in range(BOOT)]
    return [float(np.percentile(ps, 2.5)), float(np.percentile(ps, 97.5))]


def world_report(br, bs, dr, ds):
    def traj(row):
        return " -> ".join(f"d{d}:{row['ever'][str(d)]}" for d in (0, 5, 10, 15, 20))
    return f"""PANDEMIC WORLD REPORT — Day 20

Two isolated regions, Riverton and Southbay: {N_AGENTS:,} people each, no travel between them.
Disease model: SIR (susceptible -> infectious -> recovered; no deaths). Infected people are \
infectious for {DUR_INF} days on average, then recover with permanent immunity. Each person has \
about {N_CONTACTS} contacts per day. The simulation is agent-based and stochastic.
  Riverton: transmission probability per contact per day {br:.3f} (basic reproduction number \
R0 ≈ {r0(br):.1f}); {dr['seeds0']} people infectious at day 0.
  Southbay: transmission probability per contact per day {bs:.3f} (R0 ≈ {r0(bs):.1f}); \
{ds['seeds0']} people infectious at day 0.

Observed cumulative infections at the end of each day (people ever infected, including those infectious at day 0):
  Riverton: {traj(dr)}   (day 20: {dr['active']['20']} currently infectious)
  Southbay: {traj(ds)}   (day 20: {ds['active']['20']} currently infectious)"""


def intervention_text(leader, coverage=None):
    L, O = NAMES[leader], NAMES["S" if leader == "R" else "R"]
    cov = int(round((VAX["coverage"] if coverage is None else coverage) * 100))
    eff, day = int(VAX["efficacy"] * 100), VAX["day"]
    return (f"{L} will run a vaccination campaign on day {day} ({eff}% efficacy, {cov}% coverage): "
            f"on day {day}, {cov}% of {L}'s population is vaccinated, and vaccination reduces a "
            f"vaccinated person's probability of infection per exposure by {eff}%. "
            f"{O} has no planned intervention.")


def main():
    rows = simulate_all()
    A = {(b, v): arrays(rows, b, v) for b in BETAS for v in (False, True)}
    rng = np.random.default_rng(11)

    disp = {}
    for b in BETAS:
        ctl = A[(b, False)]
        k = int(np.argmin(np.abs(ctl["ever20"] - np.median(ctl["ever20"]))))
        disp[b] = dict(seed=int(ctl["seed"][k]), ever20=float(ctl["ever20"][k]), row=ctl["rows"][k])

    def matched(b, vax):
        a = A[(b, vax)]
        return a, np.abs(a["ever20"] - disp[b]["ever20"]) <= MATCH_BAND * disp[b]["ever20"]

    candidates = []
    for br in BETAS:
        for bs in BETAS:
            if br == bs:
                continue
            leader = "R" if br > bs else "S"
            base_r, mbr = matched(br, False); base_s, mbs = matched(bs, False)
            int_r, mir = matched(br, leader == "R"); int_s, mis = matched(bs, leader == "S")
            n = [int(mbr.sum()), int(mbs.sum()), int(mir.sum()), int(mis.sum())]
            if min(n) < MIN_N:
                continue
            per_h, ok = {}, True
            for t in HORIZONS:
                p0 = crossed_p(base_r[f"ever{t}"][mbr], base_s[f"ever{t}"][mbs])
                p1 = crossed_p(int_r[f"ever{t}"][mir], int_s[f"ever{t}"][mis])
                if not ((p0 >= 0.95 and p1 <= 0.05) or (p0 <= 0.05 and p1 >= 0.95)):
                    ok = False; break
                ci0 = boot_ci(base_r[f"ever{t}"][mbr], base_s[f"ever{t}"][mbs], rng)
                ci1 = boot_ci(int_r[f"ever{t}"][mir], int_s[f"ever{t}"][mis], rng)
                if (ci0[1] - ci0[0]) / 2 > 0.03 or (ci1[1] - ci1[0]) / 2 > 0.03:
                    ok = False; break
                per_h[t] = dict(p_base=p0, p_base_ci=ci0, p_int=p1, p_int_ci=ci1, delta_do=p1 - p0)
            if ok:
                candidates.append(dict(beta_r=br, beta_s=bs, leader=leader, horizons=per_h, n=n,
                                       strength=min(abs(v["delta_do"]) for v in per_h.values())))
            print(f"beta {br}/{bs} leader {leader}: {'CERTIFIED' if ok else 'no'}  n={n}")
    print(f"\n{len(candidates)} certified worlds")

    # 2 Riverton-leading + 2 Southbay-leading; strongest first; distinct unordered
    # beta pairs preferred, then fill with mirrors (only full flips certify when the
    # betas are close, so every certified S-leading pair mirrors an R-leading one).
    chosen, used = [], set()
    for leader in ("R", "S"):
        pool = sorted((c for c in candidates if c["leader"] == leader), key=lambda c: -c["strength"])
        for pass_ in ("fresh", "mirror"):
            for c in pool:
                key = frozenset((c["beta_r"], c["beta_s"]))
                if c in chosen or (pass_ == "fresh" and key in used):
                    continue
                chosen.append(c); used.add(key)
                if sum(1 for x in chosen if x["leader"] == leader) == 2:
                    break
            if sum(1 for x in chosen if x["leader"] == leader) == 2:
                break
    if len(chosen) < 4:
        print(f"WARNING: only {len(chosen)} worlds chosen")

    worlds, items = [], []
    for w, c in enumerate(chosen):
        dr, ds = disp[c["beta_r"]]["row"], disp[c["beta_s"]]["row"]
        report = world_report(c["beta_r"], c["beta_s"], dr, ds)
        world = dict(world_id=f"w{w}", beta_r=c["beta_r"], beta_s=c["beta_s"], leader=c["leader"],
                     leader_name=NAMES[c["leader"]], seed_r=disp[c["beta_r"]]["seed"],
                     seed_s=disp[c["beta_s"]]["seed"], report=report,
                     intervention=intervention_text(c["leader"]), n_matched=c["n"])
        worlds.append(world)
        for t in HORIZONS:
            h = c["horizons"][t]
            items.append(dict(
                item_id=f"w{w}_{c['leader']}lead_d{t}", world_id=world["world_id"], horizon=t,
                question=Q_TEXT.format(t=t), report=report, intervention=world["intervention"],
                truth_base=h["p_base"], truth_base_ci=h["p_base_ci"],
                truth_int=h["p_int"], truth_int_ci=h["p_int_ci"], delta_do=h["delta_do"],
                config=dict(beta_r=c["beta_r"], beta_s=c["beta_s"], leader=c["leader"],
                            seed_r=world["seed_r"], seed_s=world["seed_s"], n=c["n"], **VAX)))
            print(f"{items[-1]['item_id']:18s} base={h['p_base']:.3f} int={h['p_int']:.3f} "
                  f"delta_do={h['delta_do']:+.3f}  beta {c['beta_r']}/{c['beta_s']}")

    json.dump(dict(design=dict(n_agents=N_AGENTS, n_contacts=N_CONTACTS, dur_inf=DUR_INF, p_death=P_DEATH,
                               betas=BETAS, snapshot_day=SNAPSHOT, horizons=HORIZONS,
                               match_band=MATCH_BAND, n_seeds=N_SEEDS, vax=VAX),
                   worlds=worlds, items=items), open(OUT, "w"), indent=1)
    print(f"[saved] {len(worlds)} worlds, {len(items)} items -> {OUT}")


if __name__ == "__main__":
    main()
