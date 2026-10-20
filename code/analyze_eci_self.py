#!/usr/bin/env python3
"""The self-elicited ECI instrument, read three ways.

    python3 code/analyze_eci_self.py                 # all three tables, 2030
    python3 code/analyze_eci_self.py --horizon 2050  # the conditional tables at another horizon

1. ECI FORECASTS. Each call's p25 / p50 / p75 for the frontier ECI at end of
   2030, per model and repeat; the per-model medians; the ensemble median;
   and metr_graph's projection at the same date (data/eci_projection_*.json,
   via the set's `trend`) beside them.
2. CONDITIONALS. What each model's own p25 / p50 / p75 world does to the
   headline cells -- redlines.conditional.summarize on the set, the same
   arithmetic as the policy tab.
3. UNCONDITIONALS ACROSS INSTRUMENTS. The same cells' unconditional under
   every joint instrument that ran on the same day(s): the policy instrument
   (results/conditional_runs.jsonl), the fixed ECI set
   (results/conditional_runs_eci.jsonl) and this one -- per model mean over
   repeats, n, and the ensemble median. Does asking for an ECI forecast move
   the unconditional?
"""
import argparse
import json
import os
import statistics as st
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from redlines.conditional import load_conditional, summarize, table  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "code"))
from eci_projection_metrgraph import project  # noqa: E402

PROJ_CSV = os.path.join(ROOT, "data", "epoch_capabilities_index_2026-08-21.csv")
PROJ_N, PROJ_SEED = 400000, 1     # data/eci_projection_2026-08-21.json's run

SET = os.path.join(ROOT, "data", "eci_self_conditions.json")
LOG = os.path.join(ROOT, "results", "conditional_runs_eciself.jsonl")
INSTRUMENTS = [
    ("policy (LEAP)", os.path.join(ROOT, "results", "conditional_runs.jsonl"), "unified-joint-v1"),
    ("fixed ECI 174/186/210", os.path.join(ROOT, "results", "conditional_runs_eci.jsonl"), "unified-joint-eci-v1"),
    ("self ECI 2030", LOG, "unified-joint-eciself-v1"),
    ("self ECI +6mo", os.path.join(ROOT, "results", "conditional_runs_eciself6mo.jsonl"), "unified-joint-eciself6mo-v1"),
]
CELLS = ("catastrophe:ai", "catastrophe:general", "disempowerment")


def forecasts(rows, elicit_key):
    """{label: {arm: {field: value}}} -- one per call."""
    out = defaultdict(dict)
    for r in rows:
        e = (r.get("elicited") or {}).get(elicit_key)
        if e:
            out[r["label"]][r["arm"]] = e
    return out


def trend_at(rows, spec):
    """metr_graph's percentiles at the target date: the set's own `trend`
    for a fixed date, else computed for the run's stamped target_date(s)
    (a rolling set) with the recorded projection's N and seed."""
    if spec.get("trend"):
        return spec["trend"]
    dates = sorted({(r.get("elicited") or {}).get("target_date") for r in rows} - {None})
    if not dates:
        return None
    from datetime import datetime
    tab = project(PROJ_CSV, PROJ_N, PROJ_SEED, [(d, datetime.fromisoformat(d)) for d in dates])
    out = {"source": f"metr_graph ECI tab at its defaults, code/eci_projection_metrgraph.project at "
                     f"{', '.join(dates)} (N={PROJ_N}, seed={PROJ_SEED})", "date": dates[-1]}
    out.update({k: tab[dates[-1]][k] for k in spec["elicit"]["fields"]})
    if len(dates) > 1:
        out["by_date"] = tab
    return out


def forecast_table(rows, spec):
    el = spec["elicit"]
    fields = el["fields"]
    fc = forecasts(rows, el["key"])
    trend = trend_at(rows, spec)
    target = el.get("target_date") or trend["date"]
    lines = [f"Frontier ECI on {target}: the models' own percentiles, per call"]
    lines.append("  ".join(["model / call".ljust(26)] + [f.rjust(7) for f in fields] + ["  IQR".rjust(7)]))
    per_model = {}
    for label in sorted(fc):
        arms = fc[label]
        for arm in sorted(arms):
            v = arms[arm]
            lines.append("  ".join([f"{label} {arm}".ljust(26)] + [f"{v[f]:7.0f}" for f in fields]
                                   + [f"{v[fields[-1]] - v[fields[0]]:7.0f}"]))
        med = {f: st.median(a[f] for a in arms.values()) for f in fields}
        per_model[label] = med
        lines.append("  ".join([f"{label} median".ljust(26)] + [f"{med[f]:7.0f}" for f in fields]
                               + [f"{med[fields[-1]] - med[fields[0]]:7.0f}"]))
    ens = {f: st.median(m[f] for m in per_model.values()) for f in fields}
    lines.append("  ".join(["ENSEMBLE (median of models)".ljust(26)] + [f"{ens[f]:7.0f}" for f in fields]
                           + [f"{ens[fields[-1]] - ens[fields[0]]:7.0f}"]))
    if trend:
        lines.append("  ".join(["metr_graph trend (same date)".ljust(26)] + [f"{trend[f]:7.1f}" for f in fields]
                               + [f"{trend[fields[-1]] - trend[fields[0]]:7.1f}"]))
        lines.append(f"  ({trend['source']})")
    return "\n".join(lines), per_model, ens


def uncond_by_model(path, proto, qids, horizon, runs=None):
    """{qid: {label: [p, ...]}} -- unconditional rows only."""
    out = {q: defaultdict(list) for q in qids}
    if not os.path.exists(path):
        return out, set()
    seen_runs = set()
    for r in load_conditional(path, protocol=proto):
        if r.get("scenario") or r["question_id"] not in out:
            continue
        if runs and r["run_id"] not in runs:
            continue
        for f in r["forecasts"]:
            if f["horizon"] == horizon:
                out[r["question_id"]][r["label"]].append(f["probability"])
                seen_runs.add(r["run_id"])
    return out, seen_runs


def uncond_table(horizon, runs_filter):
    lines = []
    data = []
    for name, path, proto in INSTRUMENTS:
        d, seen = uncond_by_model(path, proto, CELLS, horizon, runs_filter.get(proto))
        data.append((name, d, seen))
    for q in CELLS:
        lines.append(f"\n{q} @ {horizon} -- unconditional, mean over repeats (n)")
        labels = sorted({l for _, d, _ in data for l in d[q]})
        w = 24
        lines.append("  ".join(["model".ljust(16)] + [n[:w].rjust(w) for n, _, _ in data]))
        for l in labels:
            row = [l.ljust(16)]
            for _, d, _ in data:
                v = d[q].get(l)
                row.append((f"{100 * st.fmean(v):.3f}% ({len(v)})" if v else "-").rjust(w))
            lines.append("  ".join(row))
        row = ["ensemble median".ljust(16)]
        for _, d, _ in data:
            ms = [st.fmean(v) for v in d[q].values() if v]
            row.append((f"{100 * st.median(ms):.3f}%" if ms else "-").rjust(w))
        lines.append("  ".join(row))
    lines.append("\n  runs: " + "; ".join(f"{n}: {', '.join(sorted(s)) or '-'}" for n, _, s in data))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", help="default: results/conditional_runs_<slug>.jsonl for the set")
    ap.add_argument("--scenarios", default=SET)
    ap.add_argument("--horizon", default="2030")
    ap.add_argument("--question", action="append")
    ap.add_argument("--measure", default="ratio", choices=["ratio", "p", "delta_pp", "dlogit"])
    ap.add_argument("--policy-runs", help="comma-separated run ids of the policy instrument to "
                                          "compare against (default: all)")
    ap.add_argument("--json", help="write the summarize() output here")
    args = ap.parse_args()
    spec = json.load(open(args.scenarios))
    if not args.log:
        args.log = os.path.join(ROOT, "results", f"conditional_runs_{spec['slug']}.jsonl")
    rows = load_conditional(args.log, protocol=spec["protocol"])
    if not rows:
        sys.exit(f"no rows in {args.log} under {spec['protocol']}")
    runs = sorted({r["run_id"] for r in rows})
    print(f"{len(rows)} rows, protocol {spec['protocol']}, runs {', '.join(runs)}\n")

    ft, per_model, ens = forecast_table(rows, spec)
    print(ft)

    s = summarize(rows, policies=spec, horizons=(args.horizon,))
    for q in (args.question or CELLS):
        print()
        print(table(s, q, args.horizon, args.measure))
    if args.json:
        json.dump(s, open(args.json, "w"), indent=1)
        print(f"\n-> {args.json}")

    print()
    filt = {}
    if args.policy_runs:
        filt["unified-joint-v1"] = set(args.policy_runs.split(","))
    print(uncond_table(args.horizon, filt))


if __name__ == "__main__":
    main()
