#!/usr/bin/env python3
"""Build a low-probability PANDEMIC corpus (Starsim SIR) — parity with FreeCiv.

Same principle as the FreeCiv miner, ported to a continuous world:
  - class = (metric=deaths, threshold X, horizon-day D)
  - cross-RUN base rate = fraction of Monte-Carlo runs where cumulative deaths
    reach X by day D. Spread comes from a PARAMETER PRIOR over transmissibility
    (beta), sampled per run (not just RNG) — near the epidemic threshold small
    beta changes flip fizzle vs full outbreak, so the tail is real and tunable.
  - snapshot at day 20: the model sees only the early trajectory + sim mechanics
    (beta is LATENT, must be inferred), and forecasts the day-{40,60,90} tail.

Writes results/pandemic/corpus.json (runs + reports + tail questions), schema-
compatible with the FreeCiv lowprob_questions.json so the same scoring applies.

    cd $FBSIM_ROOT/worlds/pandemic && uv run python <redlines>/code/pandemic_build_corpus.py
"""
from __future__ import annotations
import os
import argparse, json, os, sys
from pathlib import Path
import numpy as np

FBSIM = Path(os.environ.get("FBSIM_ROOT", os.path.expanduser("~/Projects/forecastbench-sim")))
sys.path.insert(0, str(FBSIM / "worlds" / "pandemic"))
from pandemic_world.runner import run_region, N_AGENTS, N_CONTACTS, P_DEATH  # noqa

REPO = Path(__file__).resolve().parent.parent
SNAPSHOT_DAY = 20
HORIZONS = [40, 60, 90]
REGION = "Riverton"
# candidate death thresholds; keep those whose cross-run base rate lands in [lo,hi]
CANDIDATE_THRESHOLDS = [70, 80, 90, 100, 110, 115, 120]


def sitrep(traj_cases, traj_deaths, active20) -> str:
    """Model-facing situation report at the snapshot day. Beta is NOT revealed."""
    curve = " -> ".join(f"d{d}:{int(c)}" for d, c in
                        zip(range(0, SNAPSHOT_DAY + 1, 4), traj_cases))
    dcurve = " -> ".join(f"d{d}:{int(x)}" for d, x in
                         zip(range(0, SNAPSHOT_DAY + 1, 4), traj_deaths))
    return (
        f"PANDEMIC SITUATION REPORT — {REGION}, Day {SNAPSHOT_DAY}\n\n"
        "SIMULATION: This is a stochastic SIR epidemic (Starsim). A single isolated\n"
        f"region of {N_AGENTS:,} people, well-mixed, ~{N_CONTACTS} contacts/person/day,\n"
        f"mean infectious period ~10 days, per-infection fatality ~{P_DEATH*100:.0f}%.\n"
        "Transmissibility (R0) is UNKNOWN and varies by outbreak — you must infer the\n"
        "outbreak's severity from the early trajectory below and extrapolate.\n\n"
        f"Cumulative cases:  {curve}\n"
        f"Cumulative deaths: {dcurve}\n"
        f"Day {SNAPSHOT_DAY}: {int(active20)} currently active infections.\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=250)
    ap.add_argument("--beta-lo", type=float, default=0.012)
    ap.add_argument("--beta-hi", type=float, default=0.055)
    ap.add_argument("--rate-lo", type=float, default=0.01)
    ap.add_argument("--rate-hi", type=float, default=0.09)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", type=Path, default=REPO / "results" / "pandemic" / "corpus.json")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    betas = rng.uniform(args.beta_lo, args.beta_hi, args.runs)
    runs = []
    print(f"running {args.runs} Starsim MC outbreaks (beta ~ U[{args.beta_lo},{args.beta_hi}])...")
    for i in range(args.runs):
        beta = float(betas[i])
        r = run_region(beta, False, 0.7, 25, 0.6, int(rng.integers(1, 10**7)))
        deaths, cases = r["cumulative_deaths"], r["cumulative_cases"]
        runs.append({
            "run_id": f"pan{i:04d}", "beta": beta,
            "deaths_by_day": {str(D): float(deaths[D]) for D in HORIZONS},
            "report": sitrep([cases[d] for d in range(0, SNAPSHOT_DAY + 1, 4)],
                             [deaths[d] for d in range(0, SNAPSHOT_DAY + 1, 4)],
                             r["active_infections"][SNAPSHOT_DAY]),
        })
        if (i + 1) % 50 == 0:
            print(f"  ...{i+1}/{args.runs}")

    # select tail classes: (threshold X, horizon D) with base rate in band
    classes = []
    for D in HORIZONS:
        d = np.array([run["deaths_by_day"][str(D)] for run in runs])
        for X in CANDIDATE_THRESHOLDS:
            rate = float((d >= X).mean())
            if args.rate_lo <= rate <= args.rate_hi:
                classes.append({"template_id": "deaths_threshold", "metric": "cumulative_deaths",
                                "threshold": X, "horizon_day": D, "base_rate": round(rate, 4),
                                "n": len(runs)})
    classes.sort(key=lambda c: c["base_rate"])
    print(f"\nselected {len(classes)} tail classes (base rate in "
          f"[{args.rate_lo},{args.rate_hi}]):")
    for c in classes:
        print(f"  {c['base_rate']*100:4.1f}%  deaths>={c['threshold']} by day {c['horizon_day']}")

    # emit questions (one per run per class) — schema parity with FreeCiv corpus
    questions = []
    for c in classes:
        D, X = c["horizon_day"], c["threshold"]
        horizon = f"D{D}"
        for run in runs:
            gt = run["deaths_by_day"][str(D)] >= X
            questions.append({
                "question_id": f"{run['run_id']}_x{X}_d{D}",
                "run_id": run["run_id"], "game_id": run["run_id"],
                "template_id": "deaths_threshold",
                "target": f"deaths>={X}", "horizon": horizon,
                "question_text": f"Will {REGION} reach {X} or more cumulative deaths by day {D}?",
                "ground_truth": bool(gt), "class_base_rate": c["base_rate"],
                "snapshot_day": SNAPSHOT_DAY, "resolution_day": D,
            })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"meta": {"runs": len(runs), "snapshot_day": SNAPSHOT_DAY,
                        "horizons": HORIZONS, "beta_prior": [args.beta_lo, args.beta_hi],
                        "rate_band": [args.rate_lo, args.rate_hi],
                        "n_classes": len(classes), "n_questions": len(questions),
                        "sim": {"n_agents": N_AGENTS, "n_contacts": N_CONTACTS,
                                "p_death": P_DEATH, "dur_inf": 10}},
               "classes": classes,
               "reports": {run["run_id"]: run["report"] for run in runs},
               "questions": questions},
              open(args.out, "w"), indent=2)
    overall = np.mean([q["ground_truth"] for q in questions])
    print(f"\nwrote {args.out}")
    print(f"{len(questions)} questions across {len(runs)} runs; overall yes-rate {overall*100:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
