#!/usr/bin/env python3
"""Does a forecast in the published joint call differ from the same cell asked
alone? (experiments/percell.toml, code/run_cellwise.py; 2026-11-17)

The published call asks every question x horizon x scenario at once. The
per-cell runner asks one question at one horizon under one scenario per call
(a "cell"). For one question (default the headline, catastrophe:ai), per model
and prompt, on the log-odds scale:

    joint answer = alone answer + common shift + cell shift + noise

  alone answer   p(estimate): the cell asked by itself
  common shift   p(context): how far being asked in the whole call moves
                 every cell of it, the mean over the cells of (joint - alone)
  cell shift     p(estimate x context): how far this cell moves beyond the
                 common shift, by horizon, by scenario and cell by cell

A REPLICATE is a (model, prompt) pair: its joint call (the mean of its joint
calls when the files hold more, e.g. two publication days) set beside that
pair's cell calls (the mean of their repeats). Every estimate is a mean over
replicates, and its standard error the spread between replicates over their
square root (t with n-1 degrees of freedom), so model and prompt differences
in the shifts count as noise and no noise model is assumed. Joint tests (all
horizons alike, all scenarios alike) are Hotelling's T^2 across replicates,
which needs more replicates than the test has dimensions.

WHY THE TWO SHIFTS ARE MEASURED DIFFERENTLY WELL. Every answer of one joint
call shares that call's draw (about 0.4 log-odds SD for the series'
same-day repeats), which a joint call gives once per replicate: it is part
of that replicate's common shift, so the common shift is known only across
many replicates. It cancels from the cell shifts, which compare answers of
the same call. So does anything else common to the call's cells: a joint
call from another day than the cells (the Friday run beside a later cell
run) puts what changed between the days into the common shift, not the cell
shifts, unless the change differs between cells. The report says when the
days differ.

The levels: an answer at or near 0 or 1 is clipped at 1e-9 before the
log-odds (as code/analyze_context.py); a mean of log-odds is reported as the
probability with those odds (the geometric mean of the odds).

Usage, with the dashboard's download (redlines-data.zip, saved somewhere
gitignored such as private/; or a joint instrument file from production,
state/results/conditional_runs_combined/<run>.jsonl) and the cell run's log
(experiments/percell/README.md says how to run it):

    python code/analyze_percell.py private/redlines-data.zip \\
        results/experiments/percell-<run>-cells.jsonl [--json out.json]

Each row says its own arm (`unit: "cell"` or not); a cells log
(percell-<run>-cells.jsonl) reads as well as the assembled file. Joint and
cell rows are paired by model label and condition name (percell's five
conditions carry airo's names), so airo's sixth prompt and the news shadow
find no partner and are left out. Plain Python: the pipeline does without
numpy.
"""
import argparse
import io
import json
import math
import os
import statistics as st
import sys
import zipfile
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_context import HORIZON_ORDER, _invert, logit  # noqa: E402

UNCONDITIONAL = "unconditional"


# ---- distributions (plain Python) -------------------------------------------------

def _betacf(a, b, x):
    """The continued fraction of the incomplete beta function (Lentz)."""
    tiny = 1e-300
    c, d = 1.0, 1 - (a + b) * x / (a + 1)
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((a - 1 + m2) * (a + m2)),
                   -(a + m) * (a + b + m) * x / ((a + m2) * (a + 1 + m2))):
            d = 1 + aa * d
            d = 1 / (d if abs(d) > tiny else tiny)
            c = 1 + aa / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1) < 3e-14:
            break
    return h


def betainc(a, b, x):
    """The regularized incomplete beta function I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1 - front * _betacf(b, a, 1 - x) / b


def t_p(t, df):
    """Two-sided p of Student's t."""
    return 0.0 if math.isinf(t) else betainc(df / 2, 0.5, df / (df + t * t))


def f_p(f, d1, d2):
    """Upper-tail p of F(d1, d2)."""
    return betainc(d2 / 2, d1 / 2, d2 / (d2 + d1 * f))


def gammaincc(a, x):
    """The regularized upper incomplete gamma function Q(a, x)."""
    if x <= 0:
        return 1.0
    front = math.exp(-x + a * math.log(x) - math.lgamma(a))
    if x < a + 1:                          # the series, for P
        term = total = 1 / a
        n = a
        for _ in range(1000):
            n += 1
            term *= x / n
            total += term
            if abs(term) < abs(total) * 3e-14:
                break
        return 1 - front * total
    tiny = 1e-300                          # the continued fraction, for Q (Lentz)
    b = x + 1 - a
    c, d = 1 / tiny, 1 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1 / (d if abs(d) > tiny else tiny)
        c = b + an / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        if abs(d * c - 1) < 3e-14:
            break
    return front * h


def chi2_p(x, k):
    """Upper-tail p of chi-square with k degrees of freedom."""
    return gammaincc(k / 2, x / 2)


def bh(ps):
    """Benjamini-Hochberg q-values, in the order given."""
    m = len(ps)
    q, prev = [None] * m, 1.0
    for rank, i in reversed(list(enumerate(sorted(range(m), key=lambda i: ps[i]), 1))):
        prev = min(prev, ps[i] * m / rank)
        q[i] = prev
    return q


def mean_se(xs):
    """-> {est, se, n, t, p}: a mean over replicates and its t test against 0."""
    n = len(xs)
    out = {"est": st.fmean(xs) if xs else None, "se": None, "n": n, "t": None, "p": None}
    if n >= 2:
        out["se"] = st.stdev(xs) / math.sqrt(n)
        out["t"] = out["est"] / out["se"] if out["se"] > 0 else math.copysign(math.inf, out["est"] or 1)
        out["p"] = t_p(out["t"], n - 1)
    return out


def hotelling(vectors):
    """H0: the replicates' mean vector is 0. -> {T2, F, df1, df2, p}, or
    {why} when there are too few replicates or the spread is singular."""
    n, k = len(vectors), len(vectors[0]) if vectors else 0
    if n <= k:
        return {"why": f"{n} replicate(s) for {k} dimension(s): needs at least {k + 1}"}
    m = [st.fmean(v[i] for v in vectors) for i in range(k)]
    s = [[sum((v[i] - m[i]) * (v[j] - m[j]) for v in vectors) / (n - 1) for j in range(k)] for i in range(k)]
    try:
        si = _invert(s)
    except ValueError:
        return {"why": "the replicates' spread is singular"}
    t2 = n * sum(m[i] * si[i][j] * m[j] for i in range(k) for j in range(k))
    f = (n - k) / (k * (n - 1)) * t2
    return {"T2": t2, "F": f, "df1": k, "df2": n - k, "p": f_p(f, k, n - k)}


def prob(y):
    return 1 / (1 + math.exp(-y))


# ---- the rows -----------------------------------------------------------------------

def _p50(elicited):
    """The p50 of the first elicited quantity in a row's `elicited`."""
    for v in (elicited or {}).values():
        if isinstance(v, dict) and "p50" in v:
            return v["p50"]
    return None


# The published download (redlines-data.zip, redlines/export.py): its raw
# joint-call logs. Only the instrument logs: the unconditional slice under
# raw/runs/ repeats their unconditional rows.
ZIP_MEMBERS = "raw/conditional_runs_combined/"


def _lines(path):
    """A JSONL file's lines, or for a .zip the lines of its raw joint-call logs."""
    if str(path).endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            for name in sorted(n for n in z.namelist() if n.startswith(ZIP_MEMBERS) and n.endswith(".jsonl")):
                with z.open(name) as f:
                    for line in io.TextIOWrapper(f, encoding="utf-8"):
                        yield line
    else:
        with open(path, encoding="utf-8") as f:
            yield from f


def load_obs(paths, question):
    """Rows of `question` -> [{arm, model, model_id, cond, sid, group, h, p,
    y, clipped, call, day, rep, pooled, experiment, set_protocol, eci50}].
    Joint rows and assembled cell rows hold `forecasts` over horizons; a cells
    log holds one probability a row; a .zip is the published download. An
    answer read twice (a cells log and its assembled file, say) counts once."""
    obs, skipped, seen = [], defaultdict(int), set()
    for path in paths:
        for line in _lines(path):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("question_id") != question or r.get("step") == "eci":
                continue
            if isinstance(r.get("condition"), dict) or not isinstance(r.get("forecasts", []), list):
                skipped["rows of the pre-2026-10-21 schema or malformed"] += 1
                continue
            cell = r.get("unit") == "cell"
            if cell and (r.get("bundle") or not r.get("target", True)):
                skipped["cell rows asked with other cells (bundle)"] += 1
                continue
            if "scenario_id" in r:
                sid, group = r["scenario_id"], (r.get("scenario") or {}).get("group")
            else:
                sc = r.get("scenario")
                sid, group = (sc["id"], sc.get("group")) if sc else (UNCONDITIONAL, None)
            if "forecasts" in r:
                answers = [(f["horizon"], f["probability"], (r.get("cell_calls") or {}).get(f["horizon"], r.get("call_id")))
                           for f in r["forecasts"] if f.get("probability") is not None]
            else:
                answers = [(r["horizon"], r["probability"], r.get("call_id"))]
            base = {"arm": "cell" if cell else "joint", "model": r["label"], "model_id": r.get("model"),
                    "cond": r.get("condition") or "none",
                    "sid": sid, "group": group or ("unconditional" if sid == UNCONDITIONAL else "?"),
                    "day": r.get("run_date"), "rep": r.get("replicate", 1),
                    "pooled": r.get("pooled", True), "experiment": r.get("experiment"),
                    "set_protocol": r.get("set_protocol") or r.get("protocol"), "eci50": _p50(r.get("elicited"))}
            for h, p, call in answers:
                key = (base["arm"], base["model"], base["cond"], sid, h, call, base["rep"], base["day"])
                if key in seen:
                    continue
                seen.add(key)
                y, clipped = logit(p)
                obs.append({**base, "h": h, "p": p, "y": y, "clipped": clipped, "call": call})
    return obs, dict(skipped)


def _order(values, first=()):
    """`values` in the order of `first`, then the rest sorted."""
    first = list(dict.fromkeys(first))
    return [v for v in first if v in values] + sorted(v for v in values if v not in first)


# ---- the decomposition ------------------------------------------------------------

def decompose(obs):
    """Pair the arms by (model, condition) and split joint - alone into the
    common shift and the cell shifts (the module docstring)."""
    arms = {"joint": defaultdict(lambda: defaultdict(list)), "cell": defaultdict(lambda: defaultdict(list))}
    days = {"joint": defaultdict(set), "cell": defaultdict(set)}
    eci = {"joint": defaultdict(list), "cell": defaultdict(list)}
    group_of = {}
    joint_by_day = defaultdict(lambda: defaultdict(list))
    for o in obs:
        u, c = (o["model"], o["cond"]), (o["h"], o["sid"])
        arms[o["arm"]][u][c].append(o["y"])
        days[o["arm"]][u].add(o["day"])
        if o["eci50"] is not None:
            eci[o["arm"]][u].append(o["eci50"])
        if o["arm"] == "joint":
            joint_by_day[u][(o["day"], c)].append(o["y"])
        group_of[o["sid"]] = o["group"] if o["group"] != "?" else group_of.get(o["sid"], "?")
    units = sorted(set(arms["joint"]) & set(arms["cell"]))
    unpaired = {"joint only": sorted(set(arms["joint"]) - set(arms["cell"])),
                "cells only": sorted(set(arms["cell"]) - set(arms["joint"]))}
    if not units:
        return {"units": [], "unpaired": unpaired}

    mean = {a: {u: {c: st.fmean(v) for c, v in arms[a][u].items()} for u in units} for a in arms}
    shared = {u: set(mean["joint"][u]) & set(mean["cell"][u]) for u in units}
    common = set.intersection(*shared.values())
    if not common:
        # A design that is not a grid (experiments/cellcheck.toml): no cell
        # every replicate has, so no common shift; analyze_cellcheck.py reads it.
        return {"units": units, "unpaired": unpaired, "no_grid": True}
    horizons = _order({h for h, _ in common}, HORIZON_ORDER)
    # Scenarios in the order the rows give them (the instrument's), unconditional first.
    sids = _order({s for _, s in common}, [UNCONDITIONAL] + list(dict.fromkeys(o["sid"] for o in obs)))
    cells = [(h, s) for h in horizons for s in sids if (h, s) in common]
    d = {u: {c: mean["joint"][u][c] - mean["cell"][u][c] for c in shared[u]} for u in units}

    # The common shift: each replicate's mean over the cells every replicate has.
    level = {u: st.fmean(d[u][c] for c in cells) for u in units}
    common_shift = mean_se(list(level.values()))
    by = {"model": defaultdict(list), "prompt": defaultdict(list)}
    for u in units:
        by["model"][u[0]].append(level[u])
        by["prompt"][u[1]].append(level[u])
    by = {k: {name: mean_se(v) for name, v in sorted(g.items())} for k, g in by.items()}

    def margin(axis, keys):
        """Per key: the total shift there (common + cell) and the cell part,
        and Hotelling's test that the cell part is 0 at every key."""
        dev = {u: {k: st.fmean(d[u][c] for c in cells if c[axis] == k) - level[u] for k in keys} for u in units}
        rows = {k: {"total": mean_se([dev[u][k] + level[u] for u in units]),
                    "cell": mean_se([dev[u][k] for u in units])} for k in keys}
        test = hotelling([[dev[u][k] for k in keys[:-1]] for u in units]) if len(keys) > 1 else None
        return rows, test

    by_horizon, horizon_test = margin(0, horizons)
    by_scenario, scenario_test = margin(1, sids)
    groups = _order({group_of.get(s, "?") for s in sids}, ["unconditional", "policy", "capability"])
    gdev = {u: {g: st.fmean(d[u][c] for c in cells if group_of.get(c[1], "?") == g) - level[u] for g in groups}
            for u in units}
    by_group = {g: {"total": mean_se([gdev[u][g] + level[u] for u in units]),
                    "cell": mean_se([gdev[u][g] for u in units])} for g in groups}
    group_test = hotelling([[gdev[u][g] for g in groups[:-1]] for u in units]) if len(groups) > 1 else None

    # Cell by cell: every replicate that has the cell.
    per_cell = []
    for c in sorted(set.union(*shared.values()), key=lambda c: (
            HORIZON_ORDER.index(c[0]) if c[0] in HORIZON_ORDER else 99,
            sids.index(c[1]) if c[1] in sids else 99, c)):
        us = [u for u in units if c in shared[u]]
        alone = st.fmean(mean["cell"][u][c] for u in us)
        joint = st.fmean(mean["joint"][u][c] for u in us)
        per_cell.append({"horizon": c[0], "scenario": c[1], "group": group_of.get(c[1], "?"),
                         "alone": alone, "joint": joint, "shift": mean_se([d[u][c] for u in us]),
                         "cell_shift": (mean_se([d[u][c] - level[u] for u in us]) if c in common else None)})
    testable = [r for r in per_cell if r["shift"]["p"] is not None]
    for r, q in zip(testable, bh([r["shift"]["p"] for r in testable])):
        r["shift"]["q"] = q

    # How big each part is, past the noise: the spread of the alone answers
    # over the cells, and the SDs of the cell shifts (all, horizon part,
    # scenario part, the rest), each less its estimation noise.
    def spread(rows):
        ests = [r["est"] for r in rows if r["se"] is not None]
        if len(ests) < 2:
            return None
        return math.sqrt(max(0.0, st.pvariance(ests) - st.fmean(r["se"] ** 2 for r in rows if r["se"] is not None)))

    sizes = {
        "alone_spread_over_cells": st.pstdev([r["alone"] for r in per_cell if (r["horizon"], r["scenario"]) in common])
        if len(cells) > 1 else None,
        "common_shift": common_shift["est"],
        "cell_shift_sd": spread([r["cell_shift"] for r in per_cell if r["cell_shift"]]),
        "horizon_part_sd": spread([v["cell"] for v in by_horizon.values()]),
        "scenario_part_sd": spread([v["cell"] for v in by_scenario.values()]),
    }
    parts = [sizes[k] for k in ("cell_shift_sd", "horizon_part_sd", "scenario_part_sd")]
    sizes["rest_sd"] = (math.sqrt(max(0.0, parts[0] ** 2 - parts[1] ** 2 - parts[2] ** 2))
                        if None not in parts else None)

    # The yardsticks: what the days were, and for replicates with joint calls
    # on more than one day, how much a joint call's level and its cells moved
    # between the days.
    day_pairs = sorted({(tuple(sorted(days["joint"][u])), tuple(sorted(days["cell"][u]))) for u in units})
    day_level, day_cell = [], []
    for u in units:
        ds = sorted({day for day, _ in joint_by_day[u]})
        if len(ds) < 2:
            continue
        per_day = {day: {c: st.fmean(joint_by_day[u][(day, c)]) for c in cells if (day, c) in joint_by_day[u]}
                   for day in ds}
        if any(len(per_day[day]) < len(cells) for day in ds):
            continue
        lv = {day: st.fmean(per_day[day].values()) for day in ds}
        day_level.append(st.stdev(lv.values()))
        day_cell.append(math.sqrt(st.fmean(st.variance([per_day[day][c] - lv[day] for day in ds]) for c in cells)))
    eci_gap = [st.fmean(eci["cell"][u]) - st.fmean(eci["joint"][u]) for u in units if eci["cell"][u] and eci["joint"][u]]

    return {"units": units, "unpaired": unpaired, "horizons": horizons, "scenarios": sids, "groups": groups,
            "cells": cells, "missing": {f"{u[0]} / {u[1]}": len(set(cells) ^ shared[u]) for u in units
                                        if shared[u] != set(cells)},
            "common_shift": common_shift, "common_shift_by": by, "level_by_replicate": level,
            "by_horizon": by_horizon, "horizon_test": horizon_test,
            "by_scenario": by_scenario, "scenario_test": scenario_test,
            "by_group": by_group, "group_test": group_test,
            "per_cell": per_cell, "sizes": sizes, "days": day_pairs,
            "joint_day_sd": {"level": st.fmean(day_level) if day_level else None,
                             "cells": st.fmean(day_cell) if day_cell else None, "replicates": len(day_level)},
            "eci_p50_gap": mean_se(eci_gap) if eci_gap else None}


# ---- the report ------------------------------------------------------------------

def _f(e, digits=2):
    """'+0.31 (0.12) p=0.03' for a mean_se."""
    if e is None or e.get("est") is None:
        return "-"
    s = f"{e['est']:+.{digits}f}"
    if e.get("se") is not None:
        s += f" ({e['se']:.{digits}f})"
    if e.get("p") is not None:
        s += f" p={e['p']:.3f}"
    return s


def _test(t):
    if t is None:
        return "one level only"
    if "why" in t:
        return f"not testable: {t['why']}"
    return f"F({t['df1']}, {t['df2']}) = {t['F']:.2f}, p = {t['p']:.3f}"


def _pct(p):
    return f"{100 * p:.3g}%"


def print_report(res, question, out=None):
    w = lambda s="": print(s, file=out or sys.stdout)  # noqa: E731
    if res.get("no_grid"):
        w(f"No cell of {question} is in every replicate (model x prompt): the cells are not a grid, so there "
          "is no common shift to split off. For a fixed list of cells (experiments/cellcheck.toml) use "
          "code/analyze_cellcheck.py.")
        return
    if not res["units"]:
        w(f"No (model, prompt) has both a joint and a cell answer to {question}.")
        for k, v in res["unpaired"].items():
            if v:
                w(f"  {k}: {', '.join(f'{m} / {c}' for m, c in v)}")
        return
    n = len(res["units"])
    w(f"== {question}: joint call vs the cell asked alone, log-odds (joint - alone; + means the joint call says more)")
    w(f"{n} replicate(s) (model x prompt): " + ", ".join(f"{m} / {c}" for m, c in res["units"]))
    for k, v in res["unpaired"].items():
        if v:
            w(f"  left out, {k}: {', '.join(f'{m} / {c}' for m, c in v)}")
    w(f"{len(res['cells'])} cell(s) in every replicate: {len(res['horizons'])} horizon(s) x {len(res['scenarios'])} scenario(s)")
    if res["missing"]:
        w("  replicates with other cells (cell-by-cell rows use them; the rest does not): "
          + ", ".join(f"{k} ({v})" for k, v in res["missing"].items()))
    for jd, cd in res["days"]:
        same = set(jd) == set(cd)
        w(f"  joint call(s) of {', '.join(jd)}; cells of {', '.join(cd)}"
          + ("" if same else "  -- different days: the common shift includes what changed between them"))
    jd = res["joint_day_sd"]
    if jd["replicates"]:
        w(f"  between the joint days ({jd['replicates']} replicate(s)): the level moved SD {jd['level']:.2f}, "
          f"the cells about it SD {jd['cells']:.2f}")
    if res["eci_p50_gap"]:
        w(f"  ECI p50, the cell run's ECI step minus the joint call's own: {_f(res['eci_p50_gap'], 1)} "
          "(the capability scenarios are levels of it)")

    s = res["sizes"]
    w()
    w("-- How big each part is (log-odds; the cell shifts' SDs less their estimation noise)")
    if s["alone_spread_over_cells"] is not None:
        w(f"  p(estimate)          the alone answers spread over the cells   SD {s['alone_spread_over_cells']:.2f}")
    w(f"  p(context)           the common shift                         {s['common_shift']:+.2f}")
    for k, label in (("cell_shift_sd", "p(estimate x context) the cell shifts                      SD "),
                     ("horizon_part_sd", "   by horizon                                                SD "),
                     ("scenario_part_sd", "   by scenario                                               SD "),
                     ("rest_sd", "   horizon x scenario                                        SD ")):
        if s[k] is not None:
            w(f"  {label}{s[k]:.2f}")

    w()
    w(f"-- The common shift: {_f(res['common_shift'])}" + ("" if n >= 2 else "  (one replicate: no error)"))
    for k in ("model", "prompt"):
        w(f"  by {k}: " + "; ".join(f"{name} {_f(e)}" for name, e in res["common_shift_by"][k].items()))

    for title, rows, test in (("horizon", res["by_horizon"], res["horizon_test"]),
                              ("scenario group", res["by_group"], res["group_test"]),
                              ("scenario", res["by_scenario"], res["scenario_test"])):
        w()
        w(f"-- By {title}: the shift there (common + cell) and its cell part")
        for k, e in rows.items():
            w(f"  {k:14} total {_f(e['total']):28} cell part {_f(e['cell'])}")
        w(f"  all {title}s' cell parts 0: {_test(test)}")

    w()
    w("-- Cell by cell: alone and joint (probability at the mean log-odds), the shift, q (Benjamini-Hochberg)")
    w(f"  {'horizon':8}{'scenario':14}{'alone':>11}{'joint':>11}   shift (SE) p, q")
    for r in res["per_cell"]:
        e = r["shift"]
        q = f" q={e['q']:.3f}" if e.get("q") is not None else ""
        flag = "  *" if e.get("q") is not None and e["q"] < 0.1 else ""
        w(f"  {r['horizon']:8}{r['scenario']:14}{_pct(prob(r['alone'])):>11}{_pct(prob(r['joint'])):>11}   "
          f"{_f(e)}{q}{flag}")
    w("  * q < 0.1")


def main(argv=None):
    ap = argparse.ArgumentParser(description="The joint call against the cells asked alone (see the module docstring).")
    ap.add_argument("paths", nargs="+", help="joint instrument files and cell runs (assembled or cells logs)")
    ap.add_argument("--question", default="catastrophe:ai")
    ap.add_argument("--json", metavar="PATH", help="also write the numbers here")
    args = ap.parse_args(argv)
    obs, skipped = load_obs(args.paths, args.question)
    if not obs:
        sys.exit(f"no answers to {args.question} in {', '.join(args.paths)}")
    sets = {(o["arm"], o["set_protocol"]) for o in obs}
    protos = {p.split(":", 1)[-1] if p else p for _, p in sets}
    if len(protos) > 1:
        print(f"WARNING: the rows come from different instruments: {sorted(map(str, protos))}", file=sys.stderr)
    clipped = sum(o["clipped"] for o in obs)
    if clipped:
        print(f"note: {clipped} of {len(obs)} answer(s) clipped at 1e-9 / 1 - 1e-9 before the log-odds", file=sys.stderr)
    for k, v in skipped.items():
        print(f"note: {v} {k} left out", file=sys.stderr)
    res = decompose(obs)
    print_report(res, args.question)
    if args.json:
        with open(args.json, "w") as f:
            json.dump({**res, "units": [list(u) for u in res["units"]],
                       "level_by_replicate": {f"{m} / {c}": v for (m, c), v in res.get("level_by_replicate", {}).items()},
                       "cells": [list(c) for c in res.get("cells", [])],
                       "unpaired": {k: [list(u) for u in v] for k, v in res["unpaired"].items()},
                       "days": [list(map(list, p)) for p in res.get("days", [])]},
                      f, indent=1, default=str)
        print(f"-> {args.json}")


if __name__ == "__main__":
    main()
