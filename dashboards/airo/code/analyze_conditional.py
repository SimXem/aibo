#!/usr/bin/env python3
"""Print what each LEAP policy does to a question, per model and ensembled.

Thin shim over redlines/conditional.py, the same way code/audit_coherence.py
fronts redlines/coherence.py. Reads results/conditional_runs.jsonl.

    python3 code/analyze_conditional.py                       # the two catastrophe questions, 2030 + 2050
    python3 code/analyze_conditional.py --question ladder:ai:1M --horizon 2050 --measure ratio
    python3 code/analyze_conditional.py --experiment leap-wave12-pilot --json results/conditional_summary.json
    python3 code/analyze_conditional.py --protocol unified-batch-v2   # the separate-call rows only
    python3 code/analyze_conditional.py --compare                     # joint vs separate, side by side
    python3 code/analyze_conditional.py --scenarios data/eci_conditions.json   # the capability set (its own log + protocol)

The log holds two protocols (separate calls, unified-batch-v2; the single
instrument, unified-joint-v1) whose unconditional arms are different
elicitations. A table is always of one protocol: --protocol picks it, and
without it the joint rows are preferred when present.
"""
import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from redlines.conditional import (CONDITIONAL_LOG, POLICIES, load_conditional,  # noqa: E402
                                  protocols_in, summarize, table)

PILOT = ("catastrophe:ai", "catastrophe:general")
PREFER = ("unified-joint-v1", "unified-batch-v2")


def _fmt(kind, v):
    if v is None:
        return "-"
    if kind == "loss":
        from redlines.conditional import fmt_loss
        return fmt_loss(v)
    return f"{100 * v:.3f}%"


def compare(log, experiment, qid, h, measure="ratio"):
    """Both protocols on one question x horizon: per model, unconditional and
    the per-scenario ratio, joint beside separate; ensemble last."""
    have = protocols_in(log)
    sums = {}
    for proto in PREFER:
        if proto in have:
            rows = load_conditional(log, experiment, protocol=proto)
            if rows:
                sums[proto] = summarize(rows, horizons=(h,))
    if len(sums) < 2:
        return f"(need both protocols in {log}; have {sorted(sums)})"
    j, sp = sums["unified-joint-v1"], sums["unified-batch-v2"]
    ej, es = (x["questions"].get(qid, {}).get(h) for x in (j, sp))
    if not ej or not es:
        return f"(no rows for {qid} @ {h} in both)"
    kind = ej.get("value_kind", "probability")
    models = [m for m in ej["models"] if m in es["models"]]
    lines = [f"{qid} @ {h}  [{measure}]  joint | separate   (* outside noise, † no search evidence)"]
    w = 17
    lines.append("  ".join(["scenario".ljust(30)] + [m[:w].rjust(w) for m in models] + ["ensemble".rjust(w)]))
    def cell(entry, m, cid):
        v = entry["models"][m]["conditions"].get(cid)
        if not v or v.get(measure) is None:
            return "-"
        s = f"{v[measure]:.2f}x" if measure == "ratio" else f"{v[measure]:+.2f}"
        return s + ("*" if v.get("outside") else "") + ("†" if not v.get("grounded", True) else "")
    def ens(entry, cid):
        e = entry["ensemble"].get(cid)
        if not e or e.get(measure) is None:
            return "-"
        s = f"{e[measure]:.2f}x" if measure == "ratio" else f"{e[measure]:+.2f}"
        return s + ("*" if e.get("outside") else "")
    row = ["unconditional".ljust(30)]
    for m in models:
        row.append(f"{_fmt(kind, ej['models'][m]['baseline'])} | {_fmt(kind, es['models'][m]['baseline'])}".rjust(w))
    row.append(f"{_fmt(kind, ej['baseline_median'])} | {_fmt(kind, es['baseline_median'])}".rjust(w))
    lines.append("  ".join(row))
    nj, ns = ej.get("noise") or {}, es.get("noise") or {}
    lines.append("  ".join(["noise (max/min of repeats)".ljust(30)]
                           + [f"{(ej['models'][m]['noise'] or {}).get('ratio') or 0:.2f} | {(es['models'][m]['noise'] or {}).get('ratio') or 0:.2f}".rjust(w) for m in models]
                           + [f"{nj.get('ratio') or 0:.2f} | {ns.get('ratio') or 0:.2f}".rjust(w)]))
    for c in j["conditions"]:
        cid = c["id"]
        row = [f"{cid:4} {c['label'][:24]}".ljust(30)]
        for m in models:
            row.append(f"{cell(ej, m, cid)} | {cell(es, m, cid)}".rjust(w))
        row.append(f"{ens(ej, cid)} | {ens(es, cid)}".rjust(w))
        lines.append("  ".join(row))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", help="default: the scenario set's own log "
                                  "(results/conditional_runs.jsonl for the policies, "
                                  "results/conditional_runs_<slug>.jsonl otherwise)")
    ap.add_argument("--scenarios", default=str(POLICIES),
                    help="the scenario set (default the LEAP policies)")
    ap.add_argument("--experiment")
    ap.add_argument("--question", action="append")
    ap.add_argument("--horizon", action="append")
    ap.add_argument("--measure", default="delta_pp",
                    choices=["delta_pp", "ratio", "dlogit", "p"])
    ap.add_argument("--json", help="also write the full summary here")
    ap.add_argument("--protocol",
                    help="which elicitation's rows (default: the set's own protocol; for "
                         "the policies, joint if present, else separate)")
    ap.add_argument("--compare", action="store_true",
                    help="print both protocols side by side for each question x horizon")
    args = ap.parse_args()
    policies = json.load(open(args.scenarios))
    slug = policies.get("slug", "leap")
    if not args.log:
        args.log = str(CONDITIONAL_LOG) if slug == "leap" else \
            os.path.join(ROOT, "results", f"conditional_runs_{slug}.jsonl")
    prefer = (policies["protocol"],) if policies.get("protocol") else PREFER

    horizons = tuple(args.horizon) if args.horizon else ("2030", "2050")
    if args.compare:
        for qid in (args.question or PILOT):
            for h in horizons:
                print()
                print(compare(args.log, args.experiment, qid, h, "ratio" if args.measure == "delta_pp" else args.measure))
        return
    have = protocols_in(args.log)
    proto = args.protocol or next((p for p in prefer if p in have), None)
    rows = load_conditional(args.log, args.experiment, protocol=proto)
    if not rows:
        sys.exit(f"no rows in {args.log}" + (f" for experiment {args.experiment}" if args.experiment else "")
                 + (f" under protocol {proto}" if proto else ""))
    s = summarize(rows, policies=policies, horizons=horizons)
    m = s["meta"]
    print(f"{m['rows']} rows, set {slug}, protocol {proto}, runs {', '.join(m['runs'])}, experiments {m['experiments'] or '-'}"
          + (f"   (log also holds: {', '.join(sorted(set(have) - {proto}))})" if len(have) > 1 else ""))
    for qid in (args.question or PILOT):
        for h in horizons:
            print()
            print(table(s, qid, h, args.measure))
    if args.json:
        json.dump(s, open(args.json, "w"), indent=1)
        print(f"\n-> {args.json}")


if __name__ == "__main__":
    main()
