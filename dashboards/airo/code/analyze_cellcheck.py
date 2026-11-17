#!/usr/bin/env python3
"""Each isolated cell against the same cell in the unified call
(experiments/cellcheck.toml; 2026-11-17).

The cellcheck run asks twenty cells of catastrophe:ai alone, five times each
per model (code/run_cellwise.py). The published unified (joint) call asks the
same cells beside 6,131 others. Per model, for each cell c:

    isolated mean   the mean of its 5 isolated answers
    unified         the same model's answer to the same cell (same prompt,
                    horizon and scenario) in the latest published joint call
    AE_c            |isolated mean - unified|, in probability points (the
                    mean of the probabilities) and in log-odds (the mean of
                    the log-odds)
    MAE             the mean of AE_c over the cells

THE TEST (log-odds, where the noise is about the same at 2030's ~1% and
2100's ~10%). d_c = isolated mean - unified. Under H0 -- the unified call
asks the same thing, every difference is noise -- d ~ N(0, S) with

    S = diag(s_iso^2 / n_c)                      the isolated mean's noise
      + s_u^2 [(1 - rho) I + rho J_call] / m_c   the unified answer's

s_iso^2 is the spread of the isolated repeats about their cell's mean, pooled
over the cells (df = sum of n_c - 1). A unified call answers every cell at
once, so cells from one call share its draw: J_call is 1 for two cells of the
same joint call (same prompt, same day), and rho is the shared part. s_u^2
and rho come from the same day's joint calls of the same model under the five
prompts, over every cell of the question (84): their spread across prompts
within a cell (two-way analysis of variance: the call's level, and the rest).
That counts the prompts' own differences as noise, so it errs toward calling
the arms alike. m_c is how many joint calls the unified answer averages
(one, on a publication day). Then

    X^2 = d' S^-1 d  ~  chi-square(k), k the number of cells

(a Wald test; the variances are estimated, from hundreds of degrees of
freedom on the unified side and 80 on the isolated). A second line takes the
other textbook assumption instead -- the unified call is as noisy as an
isolated one (s_u = s_iso) with rho = 0.47, the call-level share measured on
the series' same-day repeats of 2026-08 -- so the reader sees how much the
verdict leans on S.

THE MAE'S OWN p. The MAE has no closed-form null, so it is simulated: under
H0, each cell's isolated repeats and its unified answer are drawn about one
level (the precision-weighted mean of the two arms, on the log-odds), with
the noise above, and the MAE recomputed, --sims times; p is the share of
simulated MAEs at least the observed one. The same draws give the MAE in
probability points and in log-odds.

Both models together: X^2 summed (df summed), and the MAE over all their
cells against the same simulation.

The ECI step: a capability or policy cell is conditioned on the model's own
ECI forecast, which the isolated run elicits in a call of its own and the
joint call in its Step 1; the report prints how far the two forecasts are
apart, since a cell's difference includes theirs.

Usage, with the dashboard's download (copied somewhere gitignored, e.g.
private/) and the cellcheck run's cells log:

    python code/analyze_cellcheck.py private/redlines-data.zip \\
        results/experiments/cellcheck-<run>-cells.jsonl [--json out.json]

A joint instrument file (production state/results/conditional_runs_combined/
<run>.jsonl) reads as well as the zip. --joint-day picks the joint calls' day
(default: the cells' own day if the joint rows have it, else the latest).
"""
import argparse
import json
import math
import os
import random
import statistics as st
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_context import HORIZON_ORDER, _invert  # noqa: E402
from analyze_percell import UNCONDITIONAL, chi2_p, load_obs, prob  # noqa: E402

# The call-level share of a joint call's noise on the series' same-day
# repeats (2026-08): SD 0.38 shared by a call's answers, 0.40 not.
SERIES_RHO = 0.38 ** 2 / (0.38 ** 2 + 0.40 ** 2)
PROMPT_ORDER = ["none", "independent", "recent", "critical", "two-step"]


def _normal_p(z):
    return math.erfc(abs(z) / math.sqrt(2))


# ---- the two arms -----------------------------------------------------------------

def pick_day(joint, cell_days, wanted=None):
    """The joint calls' day: --joint-day, else the cells' own day when the
    joint rows have it, else the latest they have."""
    days = sorted({o["day"] for o in joint if o["day"]})
    if wanted:
        if wanted not in days:
            sys.exit(f"--joint-day {wanted}: the joint rows have {', '.join(days[-5:]) or 'no day'}")
        return wanted
    same = [d for d in sorted(cell_days, reverse=True) if d in days]
    return same[0] if same else (days[-1] if days else None)


def unified_noise(joint_day_obs):
    """The spread of one model's joint answers across its prompts' calls of
    one day, within a cell -> (s_u^2, rho, df, n_calls, n_cells), from a
    two-way analysis of variance without replication (calls x cells), or None
    with fewer than two calls."""
    by = defaultdict(dict)
    for o in joint_day_obs:
        by[o["cond"]].setdefault((o["h"], o["sid"]), []).append(o["y"])
    calls = sorted(by)
    if len(calls) < 2:
        return None
    cells = sorted(set.intersection(*(set(by[c]) for c in calls)))
    if len(cells) < 2:
        return None
    x = {(c, cell): st.fmean(by[c][cell]) for c in calls for cell in cells}
    r, k = len(calls), len(cells)
    grand = st.fmean(x.values())
    row = {c: st.fmean(x[(c, cell)] for cell in cells) for c in calls}
    col = {cell: st.fmean(x[(c, cell)] for c in calls) for cell in cells}
    ss_row = k * sum((row[c] - grand) ** 2 for c in calls)
    ss_res = sum((x[(c, cell)] - row[c] - col[cell] + grand) ** 2 for c in calls for cell in cells)
    ms_row, ms_res = ss_row / (r - 1), ss_res / ((r - 1) * (k - 1))
    var_call = max(0.0, (ms_row - ms_res) / k)
    total = var_call + ms_res
    return {"var": total, "rho": var_call / total if total > 0 else 0.0, "df": (r - 1) * k,
            "calls": r, "cells": k}


def cell_table(obs, model, day):
    """One model's twenty (or so) cells -> [cell], each with its isolated
    repeats and its unified answer(s) of `day`."""
    iso, uni = defaultdict(list), defaultdict(list)
    for o in obs:
        if o["model"] != model:
            continue
        key = (o["cond"], o["h"], o["sid"])
        if o["arm"] == "cell":
            iso[key].append(o)
        elif o["day"] == day and o["pooled"] is not False:
            uni[key].append(o)
    rows = []
    for key in sorted(iso, key=lambda k: (PROMPT_ORDER.index(k[0]) if k[0] in PROMPT_ORDER else 9,
                                          HORIZON_ORDER.index(k[1]) if k[1] in HORIZON_ORDER else 9, k[2])):
        if not uni.get(key):
            continue
        ys, ps = [o["y"] for o in iso[key]], [o["p"] for o in iso[key]]
        uy, up = [o["y"] for o in uni[key]], [o["p"] for o in uni[key]]
        rows.append({"prompt": key[0], "horizon": key[1], "scenario": key[2], "n": len(ys), "m": len(uy),
                     "call": (key[0], day), "iso_y": ys, "iso_p": ps,
                     "iso_mean_y": st.fmean(ys), "iso_mean_p": st.fmean(ps),
                     "iso_sd_p": st.stdev(ps) if len(ps) > 1 else None,
                     "uni_y": st.fmean(uy), "uni_p": st.fmean(up)})
    missing = sorted(set(iso) - {(r["prompt"], r["horizon"], r["scenario"]) for r in rows})
    return rows, missing


# ---- the test -------------------------------------------------------------------------

def covariance(rows, s_iso2, s_u2, rho):
    k = len(rows)
    return [[(s_iso2 / rows[i]["n"] if i == j else 0.0)
             + (s_u2 * ((1 - rho) * (i == j) + rho) / min(rows[i]["m"], rows[j]["m"])
                if rows[i]["call"] == rows[j]["call"] else 0.0)
             for j in range(k)] for i in range(k)]


def wald(d, cov):
    inv = _invert(cov)
    x2 = sum(d[i] * inv[i][j] * d[j] for i in range(len(d)) for j in range(len(d)))
    return {"X2": x2, "df": len(d), "p": chi2_p(x2, len(d))}


def simulate(rows, s_iso2, s_u2, rho, sims, rng):
    """Null draws of (MAE in points, MAE in log-odds) for one model's cells."""
    w_iso = [r["n"] / s_iso2 for r in rows]
    w_uni = [r["m"] / s_u2 if s_u2 > 0 else 0.0 for r in rows]
    level = [(wi * r["iso_mean_y"] + wu * r["uni_y"]) / (wi + wu) for r, wi, wu in zip(rows, w_iso, w_uni)]
    calls = sorted({r["call"] for r in rows})
    sd_iso, sd_call, sd_own = math.sqrt(s_iso2), math.sqrt(rho * s_u2), math.sqrt((1 - rho) * s_u2)
    out = []
    for _ in range(sims):
        shift = {c: rng.gauss(0, sd_call) for c in calls}
        ae_p = ae_y = 0.0
        for r, mu in zip(rows, level):
            ys = [mu + rng.gauss(0, sd_iso) for _ in range(r["n"])]
            uy = st.fmean(mu + shift[r["call"]] + rng.gauss(0, sd_own) for _ in range(r["m"]))
            ae_p += abs(st.fmean(prob(y) for y in ys) - prob(uy))
            ae_y += abs(st.fmean(ys) - uy)
        out.append((ae_p / len(rows), ae_y / len(rows)))
    return out


def analyse(obs, joint_day=None, sims=10000, seed=1):
    cells = [o for o in obs if o["arm"] == "cell"]
    if not cells:
        sys.exit("no isolated (cell) answers in the inputs: pass the cellcheck run's cells log")
    models = sorted({o["model"] for o in cells})
    conds = {o["cond"] for o in cells}
    joint = [o for o in obs if o["arm"] == "joint" and o["model"] in models and o["cond"] in conds
             and o["pooled"] is not False]
    if not joint:
        sys.exit(f"no joint answers for {', '.join(models)} under {', '.join(sorted(conds))} in the inputs: "
                 "pass the dashboard's download (redlines-data.zip) or a joint instrument file")
    cell_days = sorted({o["day"] for o in cells})
    day = pick_day(joint, cell_days, joint_day)
    rng = random.Random(seed)
    used = cells + [o for o in joint if o["day"] == day]
    res = {"joint_day": day, "cell_days": cell_days, "models": {}, "notes": [],
           "clipped": sum(o["clipped"] for o in used), "answers": len(used)}
    if day not in cell_days:
        res["notes"].append(f"the joint calls are of {day}, the isolated cells of {', '.join(cell_days)}: "
                            "a difference includes what changed between the days")
    pooled_sims = None
    for model in models:
        rows, missing = cell_table(obs, model, day)
        if not rows:
            res["notes"].append(f"{model}: no joint answer of {day} for its cells")
            continue
        ids = {a: sorted({o["model_id"] for o in obs if o["model"] == model and o["arm"] == a and o["model_id"]})
               for a in ("cell", "joint")}
        if ids["joint"] and ids["cell"] and set(ids["cell"]) != set(ids["joint"]):
            res["notes"].append(f"{model}: the isolated cells ran {', '.join(ids['cell'])}, the joint calls "
                                f"{', '.join(ids['joint'])} -- not the same model id")
        resid = [y - r["iso_mean_y"] for r in rows for y in r["iso_y"]]
        df_iso = sum(r["n"] - 1 for r in rows)
        if df_iso < 1:
            sys.exit(f"{model}: one isolated answer per cell; the test needs the repeats")
        s_iso2 = sum(e * e for e in resid) / df_iso
        noise = unified_noise([o for o in joint if o["model"] == model and o["day"] == day])
        d = [r["iso_mean_y"] - r["uni_y"] for r in rows]
        if noise:
            s_u2, rho = noise["var"], noise["rho"]
        else:
            s_u2, rho = s_iso2, SERIES_RHO
            res["notes"].append(f"{model}: fewer than two joint calls on {day}; the unified noise is "
                                "taken as the isolated one's (rho 0.47)")
        cov = covariance(rows, s_iso2, s_u2, rho)
        test = wald(d, cov)
        alt = wald(d, covariance(rows, s_iso2, s_iso2, SERIES_RHO))
        mean_d = st.fmean(d)
        var_mean = sum(map(sum, cov)) / len(d) ** 2
        mae_p = st.fmean(abs(r["iso_mean_p"] - r["uni_p"]) for r in rows)
        mae_y = st.fmean(abs(x) for x in d)
        draws = simulate(rows, s_iso2, s_u2, rho, sims, rng)
        p_mae_p = (1 + sum(a >= mae_p for a, _ in draws)) / (1 + sims)
        p_mae_y = (1 + sum(b >= mae_y for _, b in draws)) / (1 + sims)
        k = len(rows)
        pooled_sims = ([(a * k, b * k, k) for a, b in draws] if pooled_sims is None else
                       [(pa + a * k, pb + b * k, pk + k) for (pa, pb, pk), (a, b) in zip(pooled_sims, draws)])
        eci = {a: [o["eci50"] for o in obs if o["model"] == model and o["arm"] == a and o["eci50"] is not None
                   and (a == "cell" or o["day"] == day)] for a in ("cell", "joint")}
        for i, (r, di) in enumerate(zip(rows, d)):
            r.update(ae_p=abs(r["iso_mean_p"] - r["uni_p"]), d=di, z=di / math.sqrt(cov[i][i]))
            for x in ("iso_y", "iso_p", "call"):
                r.pop(x)
        res["models"][model] = {
            "cells": rows, "missing_joint": [list(m) for m in missing], "k": k,
            "s_iso": math.sqrt(s_iso2), "df_iso": df_iso,
            "s_u": math.sqrt(s_u2), "rho": rho, "noise_from": noise,
            "mae_p": mae_p, "mae_y": mae_y, "p_mae_p": p_mae_p, "p_mae_y": p_mae_y,
            "mean_d": mean_d, "se_mean_d": math.sqrt(var_mean), "p_mean_d": _normal_p(mean_d / math.sqrt(var_mean)),
            "test": test, "test_iso_noise": alt,
            "eci_p50": {a: st.fmean(v) if v else None for a, v in eci.items()},
        }
    ms = list(res["models"].values())
    if len(ms) > 1:
        x2, df = sum(m["test"]["X2"] for m in ms), sum(m["test"]["df"] for m in ms)
        x2a, dfa = sum(m["test_iso_noise"]["X2"] for m in ms), sum(m["test_iso_noise"]["df"] for m in ms)
        n = sum(m["k"] for m in ms)
        mae_p = sum(m["mae_p"] * m["k"] for m in ms) / n
        mae_y = sum(m["mae_y"] * m["k"] for m in ms) / n
        res["together"] = {
            "k": n, "mae_p": mae_p, "mae_y": mae_y,
            "p_mae_p": (1 + sum(a / kk >= mae_p for a, _, kk in pooled_sims)) / (1 + sims),
            "p_mae_y": (1 + sum(b / kk >= mae_y for _, b, kk in pooled_sims)) / (1 + sims),
            "test": {"X2": x2, "df": df, "p": chi2_p(x2, df)},
            "test_iso_noise": {"X2": x2a, "df": dfa, "p": chi2_p(x2a, dfa)}}
    return res


# ---- the report -------------------------------------------------------------------------

def _pp(p):
    return f"{100 * p:.3g}%"


def print_report(res, question, sims, out=None):
    w = lambda s="": print(s, file=out or sys.stdout)  # noqa: E731
    w(f"== {question}: each isolated cell against the same cell in the unified (joint) call")
    w(f"joint calls of {res['joint_day']}; isolated cells of {', '.join(res['cell_days'])}")
    if res["clipped"]:
        w(f"  {res['clipped']} of {res['answers']} answers at 0 or 1, clipped at 1e-9 before the log-odds")
    for n in res["notes"]:
        w(f"  NOTE {n}")
    for model, m in res["models"].items():
        w()
        w(f"-- {model}: {m['k']} cells")
        w(f"  {'prompt':12}{'horizon':8}{'scenario':14}{'isolated (n, SD)':>24}{'unified':>10}{'AE':>9}"
          f"{'d log-odds':>12}{'z':>7}")
        for r in m["cells"]:
            spread = f", {_pp(r['iso_sd_p'])}" if r["iso_sd_p"] is not None else ""
            isolated = f"{_pp(r['iso_mean_p'])} ({r['n']}{spread})"
            w(f"  {r['prompt']:12}{r['horizon']:8}{r['scenario']:14}{isolated:>24}{_pp(r['uni_p']):>10}"
              f"{100 * r['ae_p']:>7.2f}pp{r['d']:>+12.2f}{r['z']:>+7.2f}")
        if m["missing_joint"]:
            w(f"  no joint answer for: {', '.join('/'.join(x) for x in m['missing_joint'])}")
        w(f"  MAE {100 * m['mae_p']:.2f} pp (simulated p {m['p_mae_p']:.3f}); "
          f"{m['mae_y']:.2f} log-odds (p {m['p_mae_y']:.3f}); {sims} draws")
        w(f"  mean d {m['mean_d']:+.2f} log-odds ({m['se_mean_d']:.2f}), p {m['p_mean_d']:.3f}"
          f"  (+: the isolated cell says more)")
        t, a = m["test"], m["test_iso_noise"]
        nf = m["noise_from"]
        src = (f"from {nf['calls']} joint calls x {nf['cells']} cells" if nf else "taken as the isolated one's")
        w(f"  chi-square X2 = {t['X2']:.1f} on {t['df']} df, p = {t['p']:.4f}   "
          f"[isolated SD {m['s_iso']:.2f} (df {m['df_iso']}); unified SD {m['s_u']:.2f}, "
          f"call share {m['rho']:.2f}, {src}]")
        w(f"  same, unified as noisy as isolated (rho 0.47): X2 = {a['X2']:.1f}, p = {a['p']:.4f}")
        e = m["eci_p50"]
        if e["cell"] is not None and e["joint"] is not None:
            w(f"  ECI p50: isolated ECI steps {e['cell']:.1f}, joint call {e['joint']:.1f} "
              f"(policy and capability cells are conditioned on it)")
    if "together" in res:
        t = res["together"]
        w()
        w(f"-- both models: {t['k']} cells")
        w(f"  MAE {100 * t['mae_p']:.2f} pp (simulated p {t['p_mae_p']:.3f}); {t['mae_y']:.2f} log-odds "
          f"(p {t['p_mae_y']:.3f})")
        w(f"  chi-square X2 = {t['test']['X2']:.1f} on {t['test']['df']} df, p = {t['test']['p']:.4f}; "
          f"unified as noisy as isolated: X2 = {t['test_iso_noise']['X2']:.1f}, p = {t['test_iso_noise']['p']:.4f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Isolated cells against the unified call (see the module docstring).")
    ap.add_argument("paths", nargs="+", help="the download (redlines-data.zip) or joint instrument files, "
                                             "and the cellcheck run's cells log")
    ap.add_argument("--question", default="catastrophe:ai")
    ap.add_argument("--joint-day", help="the joint calls' run date (default: the cells' own, else the latest)")
    ap.add_argument("--sims", type=int, default=10000, help="null draws for the MAE's p")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--json", metavar="PATH", help="also write the numbers here")
    args = ap.parse_args(argv)
    obs, _ = load_obs(args.paths, args.question)
    res = analyse(obs, args.joint_day, args.sims, args.seed)
    print_report(res, args.question, args.sims)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(res, f, indent=1, default=str)
        print(f"-> {args.json}")


if __name__ == "__main__":
    main()
