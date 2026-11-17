#!/usr/bin/env python3
"""The context experiment's effects (experiments/context.toml, code/run_cellwise.py).

Does what else a call asks move a forecast? Two analyses, each run when the
cells logs hold its arms.

THE REGRESSION (the alone and horizons arms; experiments/context.toml asks
just these). One observation per target answer, Y its log-odds:

    Y = a + b1 HOR + b2 PROMPT + b3 OTHERHOR + g1 HOR x OTHERHOR
          + g2 HOR x PROMPT + g3 OTHERHOR x PROMPT + model + day + e

HOR and PROMPT are categories (dummies against a reference level: horizon
2030 and prompt none unless --ref-horizon/--ref-prompt say otherwise),
OTHERHOR is 1 when the call asked all the horizons at once, `model` is a
fixed effect per model and `day` one per run date when there is more than
one. Least squares, with standard errors clustered by call (CR1): the six
answers of a horizons call share that call's draw. Then the effect of the
other horizons at each horizon and prompt, b3 + g1[HOR] + g3[PROMPT], and its
average over the prompts, each with its standard error. Plain Python: the
pipeline does without numpy.

THE 2x2 (when the logs also hold the severities arms, which asked the target
with the other AI severities beside it). Each arm asks the same target cells
with a different context, a 2x2 on the call's `bundle`:

    neither     the target at one horizon, alone
    horizons    the target at all its horizons in one call
    severities  the target with the other AI severities beside it
    both        both

On the log-odds scale (positive: the context raises the forecast), per model
and target, each arm's answer averaged over its repeats:

    horizons    = ((horizons - neither) + (both - severities)) / 2
    severities  = ((severities - neither) + (both - horizons)) / 2
    interaction = (both - severities) - (horizons - neither)

Standard errors come from the spread between repeats: within an arm, each
repeat is averaged over the targets first, so answers that shared a call
(the one-call arms put every target in the same call) are not counted as
independent. A repeat counts only when it answered every target in scope.
Each prompt variant (the experiment asks airo's none, independent and recent)
is reported on its own, pooled over its models, and then pooled over every
prompt x model unit: the mean of the units' effects, its standard error from
theirs. Probabilities are clipped to [1e-9, 1 - 1e-9] before the log-odds,
which touches only an exact 0 or 1; the report says how many were.

    python code/analyze_context.py results/experiments/context-<run>-cells.jsonl [more ...]
    python code/analyze_context.py ... --json results/experiments/context-<run>-effects.json
"""
import argparse
import json
import math
import statistics as st
import sys
from collections import defaultdict

# Only an exact 0 or 1 has no log-odds. The published series' catastrophe:ai
# answers run that low on their own: 49 of 70 six-month answers before
# 2026-09-18 were below 1e-4, none was 0. Clipping at 1e-4 would flatten them.
EPS = 1e-9
ARMS = {(): "neither", ("horizons",): "horizons", ("severities",): "severities",
        ("horizons", "severities"): "both"}
# Each effect as weights on the four arms' means.
EFFECTS = {
    "horizons": {"neither": -.5, "horizons": .5, "severities": -.5, "both": .5},
    "severities": {"neither": -.5, "horizons": -.5, "severities": .5, "both": .5},
    "interaction": {"neither": 1, "horizons": -1, "severities": -1, "both": 1},
}
HORIZON_ORDER = ["6mo", "12mo", "2028", "2030", "2050", "2100"]


def arm_of(row):
    return ARMS[tuple(sorted(row.get("bundle") or []))]


def logit(p):
    """-> (log-odds, clipped?)."""
    q = min(max(p, EPS), 1 - EPS)
    return math.log(q / (1 - q)), q != p


# ---- the regression -------------------------------------------------------------

def load_obs(paths):
    """Target answers of the alone and horizons arms -> [{y, hor, prompt,
    other, model, call, day}], and how many answers of other arms were left out."""
    obs, other_arms = [], 0
    for path in paths:
        for line in open(path):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("step") != "cell" or not r.get("target", True) or r.get("scenario_id") != "unconditional":
                continue
            if arm_of(r) not in ("neither", "horizons"):
                other_arms += 1
                continue
            obs.append({"y": logit(r["probability"])[0], "hor": r["horizon"], "prompt": r.get("variant") or "none",
                        "other": int(arm_of(r) == "horizons"), "model": r["label"], "call": r["call_id"],
                        "day": r.get("run_date")})
    return obs, other_arms


def _invert(a):
    """Gauss-Jordan with partial pivoting; ValueError when singular."""
    n = len(a)
    m = [row[:] + [float(i == j) for j in range(n)] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-10:
            raise ValueError(f"the design cannot separate column {c}")
        m[c], m[p] = m[p], m[c]
        piv = m[c][c]
        m[c] = [x / piv for x in m[c]]
        for r in range(n):
            if r != c and m[r][c]:
                f = m[r][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [row[n:] for row in m]


def ols_cluster(X, y, clusters):
    """Least squares with cluster-robust (CR1) covariance -> (beta, V, r2)."""
    n, k = len(X), len(X[0])
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for row, yi in zip(X, y):
        nz = [(i, x) for i, x in enumerate(row) if x]
        for i, xi in nz:
            xty[i] += xi * yi
            for j, xj in nz:
                xtx[i][j] += xi * xj
    inv = _invert(xtx)
    beta = [sum(inv[i][j] * xty[j] for j in range(k)) for i in range(k)]
    resid = [yi - sum(b * x for b, x in zip(beta, row)) for row, yi in zip(X, y)]
    scores = defaultdict(lambda: [0.0] * k)
    for row, u, g in zip(X, resid, clusters):
        s = scores[g]
        for i, x in enumerate(row):
            if x:
                s[i] += x * u
    meat = [[0.0] * k for _ in range(k)]
    for s in scores.values():
        for i in range(k):
            if s[i]:
                for j in range(k):
                    meat[i][j] += s[i] * s[j]
    g = len(scores)
    scale = g / (g - 1) * (n - 1) / (n - k) if g > 1 and n > k else float("nan")
    half = [[sum(inv[i][l] * meat[l][j] for l in range(k)) for j in range(k)] for i in range(k)]
    V = [[scale * sum(half[i][l] * inv[l][j] for l in range(k)) for j in range(k)] for i in range(k)]
    mean = st.mean(y)
    sst = sum((v - mean) ** 2 for v in y)
    r2 = 1 - sum(u * u for u in resid) / sst if sst else float("nan")
    return beta, V, r2


def regression(obs, ref_horizon="2030", ref_prompt="none"):
    """Fit the model to the observations -> a report dict, or None when the
    logs lack a level the model needs (both OTHERHOR levels, two prompts or
    horizons)."""
    hors = [h for h in HORIZON_ORDER if any(o["hor"] == h for o in obs)] + \
        sorted({o["hor"] for o in obs} - set(HORIZON_ORDER))
    prompts = list(dict.fromkeys(o["prompt"] for o in obs))
    models = sorted({o["model"] for o in obs})
    days = sorted({o["day"] for o in obs})
    if {o["other"] for o in obs} != {0, 1}:
        return None
    rh = ref_horizon if ref_horizon in hors else hors[0]
    rp = ref_prompt if ref_prompt in prompts else prompts[0]
    H = [h for h in hors if h != rh]
    P = [p for p in prompts if p != rp]
    names = (["intercept"] + [f"HOR[{h}]" for h in H] + [f"PROMPT[{p}]" for p in P] + ["OTHERHOR"]
             + [f"HOR[{h}] x OTHERHOR" for h in H] + [f"HOR[{h}] x PROMPT[{p}]" for h in H for p in P]
             + [f"OTHERHOR x PROMPT[{p}]" for p in P] + [f"model[{m}]" for m in models[1:]]
             + [f"day[{d}]" for d in days[1:]])

    def row(o):
        hd = [float(o["hor"] == h) for h in H]
        pd = [float(o["prompt"] == p) for p in P]
        x = o["other"]
        return ([1.0] + hd + pd + [float(x)] + [v * x for v in hd] + [a * b for a in hd for b in pd]
                + [v * x for v in pd] + [float(o["model"] == m) for m in models[1:]]
                + [float(o["day"] == d) for d in days[1:]])

    X = [row(o) for o in obs]
    try:
        beta, V, r2 = ols_cluster(X, [o["y"] for o in obs], [o["call"] for o in obs])
    except ValueError as e:
        raise ValueError(f"cannot fit the model: {e} ({names[int(str(e).split()[-1])]})") from None
    at = {n: i for i, n in enumerate(names)}

    def lin(weights):
        w = [0.0] * len(names)
        for t, c in weights.items():
            w[at[t]] += c
        est = sum(a * b for a, b in zip(w, beta))
        var = sum(w[i] * V[i][j] * w[j] for i in range(len(w)) for j in range(len(w)))
        return est, (math.sqrt(var) if var >= 0 else float("nan"))

    effect = {}
    for h in hors:
        effect[h] = {}
        for p in prompts:
            w = {"OTHERHOR": 1.0}
            if h != rh:
                w[f"HOR[{h}] x OTHERHOR"] = 1.0
            if p != rp:
                w[f"OTHERHOR x PROMPT[{p}]"] = 1.0
            effect[h][p] = lin(w)
        avg = {"OTHERHOR": 1.0}
        if h != rh:
            avg[f"HOR[{h}] x OTHERHOR"] = 1.0
        for p in P:
            avg[f"OTHERHOR x PROMPT[{p}]"] = 1.0 / len(prompts)
        effect[h]["all prompts"] = lin(avg)
    overall = {"OTHERHOR": 1.0}
    for h in H:
        overall[f"HOR[{h}] x OTHERHOR"] = 1.0 / len(hors)
    for p in P:
        overall[f"OTHERHOR x PROMPT[{p}]"] = 1.0 / len(prompts)
    return {"n": len(obs), "clusters": len({o["call"] for o in obs}), "models": models, "prompts": prompts,
            "days": days, "reference": {"horizon": rh, "prompt": rp, "model": models[0], "day": days[0]},
            "r2": r2, "coefficients": {n: (beta[i], math.sqrt(V[i][i]) if V[i][i] >= 0 else float("nan"))
                                       for i, n in enumerate(names)},
            "effect_of_other_horizons": effect, "average_effect": lin(overall)}


def print_regression(reg):
    print(f"\n== Regression: Y = log-odds of catastrophe:ai; {reg['n']} answers, {reg['clusters']} calls (clusters), "
          f"{len(reg['models'])} model(s), {len(reg['days'])} day(s); R² {reg['r2']:.3f}")
    ref = reg["reference"]
    print(f"   reference: horizon {ref['horizon']}, prompt {ref['prompt']}, model {ref['model']}"
          + (f", day {ref['day']}" if len(reg["days"]) > 1 else ""))
    print(f"   {'coefficient':34} {'estimate':>9} {'se':>7} {'t':>7}")
    for n, (b, se) in reg["coefficients"].items():
        t = b / se if se and se == se else float("nan")
        print(f"   {n:34} {b:+9.3f} {se:7.3f} {t:7.2f}")
    print("\n== Effect of the other horizons in the call: b3 + g1[HOR] + g3[PROMPT], log-odds ± se (x odds)")
    cols = reg["prompts"] + ["all prompts"]
    print("   " + f"{'horizon':8}" + "".join(f"{c:>26}" for c in cols))
    for h, row in reg["effect_of_other_horizons"].items():
        print("   " + f"{h:8}" + "".join(f"{row[c][0]:+9.3f} ±{row[c][1]:.3f} x{math.exp(row[c][0]):5.2f}".rjust(26)
                                     for c in cols))
    est, se = reg["average_effect"]
    print(f"   averaged over horizons and prompts: {est:+.3f} ±{se:.3f} (x{math.exp(est):.2f} odds)")


def load(paths):
    """-> ({(prompt variant, model): {arm: {replicate: {(question, horizon): log-odds}}}},
    n clipped, n rows)."""
    data = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    clipped = n = 0
    for path in paths:
        for line in open(path):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("step") != "cell" or not r.get("target", True) or r.get("scenario_id") != "unconditional":
                continue
            p = r["probability"]
            if p < EPS or p > 1 - EPS:
                clipped += 1
                p = min(max(p, EPS), 1 - EPS)
            # A repeat of a model under an arm is identified within its run.
            rep = (r["run_id"], r.get("replicate", 1))
            unit = (r.get("variant") or "none", r["label"])
            data[unit][arm_of(r)][rep][(r["question_id"], r["horizon"])] = math.log(p / (1 - p))
            n += 1
    return data, clipped, n


def arm_summary(reps, scope):
    """An arm's repeats -> (mean over repeats of the per-repeat mean over the
    scope's targets, its variance, repeats used); repeats that miss a target
    are left out."""
    means = [st.mean(v[t] for t in scope) for v in reps.values() if all(t in v for t in scope)]
    if not means:
        return None
    var = st.variance(means) / len(means) if len(means) > 1 else float("nan")
    return st.mean(means), var, len(means)


def effects(arms, scope):
    """One model's arms -> {effect: (estimate, se)} over the scope's targets, or None."""
    s = {a: arm_summary(arms.get(a, {}), scope) for a in ("neither", "horizons", "severities", "both")}
    if any(v is None for v in s.values()):
        return None
    out = {}
    for name, w in EFFECTS.items():
        est = sum(w[a] * s[a][0] for a in w)
        var = sum(w[a] ** 2 * s[a][1] for a in w)
        out[name] = (est, math.sqrt(var) if var == var else float("nan"))
    out["repeats"] = {a: s[a][2] for a in s}
    return out


def pooled(per_unit):
    """Effects of (prompt, model) units -> {effect: (mean, se)}, the units
    weighted equally."""
    ms = [m for m in per_unit.values() if m]
    if not ms:
        return None
    out = {}
    for name in EFFECTS:
        ests = [m[name][0] for m in ms]
        ses = [m[name][1] for m in ms]
        out[name] = (st.mean(ests), math.sqrt(sum(se ** 2 for se in ses)) / len(ms))
    out["models"] = len(ms)
    return out


def scopes(data):
    """'all horizons' and each horizon, over the targets every model answered somewhere."""
    targets = sorted({t for arms in data.values() for reps in arms.values() for v in reps.values() for t in v},
                     key=lambda t: (t[0], HORIZON_ORDER.index(t[1]) if t[1] in HORIZON_ORDER else 99))
    out = {"all horizons": targets}
    for h in sorted({t[1] for t in targets}, key=lambda h: HORIZON_ORDER.index(h) if h in HORIZON_ORDER else 99):
        out[h] = [t for t in targets if t[1] == h]
    return out


def noise(data):
    """The spread between repeats of one target in one arm, log-odds (median SD)."""
    sds = defaultdict(list)
    for arms in data.values():
        for arm, reps in arms.items():
            by_t = defaultdict(list)
            for v in reps.values():
                for t, x in v.items():
                    by_t[t].append(x)
            sds[arm] += [st.stdev(xs) for xs in by_t.values() if len(xs) > 1]
    return {a: round(st.median(v), 3) for a, v in sds.items() if v}


def fmt(e):
    est, se = e
    if se != se:
        return f"{est:+.3f} (se n/a)"
    return f"{est:+.3f} ±{se:.3f}  x{math.exp(est):.2f} odds"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Effects of the other horizons and severities in a call.")
    ap.add_argument("cells", nargs="+", help="cells logs of the context experiment (run_cellwise)")
    ap.add_argument("--json", help="also write the effects here")
    ap.add_argument("--ref-horizon", default="2030", help="the regression's reference horizon (default 2030)")
    ap.add_argument("--ref-prompt", default="none", help="the regression's reference prompt (default none)")
    args = ap.parse_args(argv)
    data, clipped, n = load(args.cells)
    if not data:
        sys.exit("no target rows: are these the context experiment's cells logs?")
    variants = list(dict.fromkeys(v for v, _ in data))
    report = {"rows": n, "clipped": clipped, "noise_sd": noise(data), "scopes": {}}
    print(f"{n} target answers: {len(data)} prompt x model unit(s), prompts {', '.join(variants)}; "
          f"{clipped} clipped to [{EPS}, {1 - EPS}]")
    print(f"spread between repeats (median SD, log-odds): {report['noise_sd']}")
    obs, _ = load_obs(args.cells)
    reg = regression(obs, args.ref_horizon, args.ref_prompt) if obs else None
    report["regression"] = reg
    if reg:
        print_regression(reg)
    else:
        print("\n(no regression: it needs answers from both the alone and the horizons arms)")
    with_severities = any(a in arms for arms in data.values() for a in ("severities", "both"))
    for name, scope in (scopes(data).items() if with_severities else ()):
        per_unit = {u: effects(arms, scope) for u, arms in data.items()}
        by_variant = {v: pooled({u: e for u, e in per_unit.items() if u[0] == v}) for v in variants}
        overall = pooled(per_unit)
        report["scopes"][name] = {"targets": [list(t) for t in scope],
                                  "units": {f"{v}|{m}": e for (v, m), e in per_unit.items()},
                                  "by_prompt": by_variant, "pooled": overall}
        print(f"\n== {name} ({len(scope)} target(s)) == effect on log-odds, ± one standard error")
        for v in variants:
            print(f"  prompt {v}")
            for (uv, m), e in per_unit.items():
                if uv != v:
                    continue
                if e is None:
                    print(f"    {m:16} incomplete: an arm has no repeat that answered every target")
                    continue
                print(f"    {m:16} " + "   ".join(f"{k} {fmt(e[k])}" for k in EFFECTS) + f"   repeats {e['repeats']}")
            if by_variant[v]:
                print(f"    {'all models':16} " + "   ".join(f"{k} {fmt(by_variant[v][k])}" for k in EFFECTS))
        if overall:
            print(f"  {'pooled':18} " + "   ".join(f"{k} {fmt(overall[k])}" for k in EFFECTS)
                  + f"   over {overall['models']} prompt x model unit(s)")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=1)
        print(f"\n-> {args.json}")


if __name__ == "__main__":
    main()
