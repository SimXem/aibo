#!/usr/bin/env python3
"""The same instrument through two loops, cell by cell: the cron's published
run against a run of the same day through the other loop -- a condition with
another `harness` (redlines/experiments.py) -- (pi since combined-v9, litellm
before; redlines/pi_loop.py says what differs).

    python code/compare_harness.py \\
        --base results/conditional_runs_combined/2026-10-21T1200Z.jsonl \\
        --other results/experiments/litellm-shadow-2026-10-21T1405Z-instrument.jsonl \\
        --prev results/conditional_runs_combined/2026-10-16T1200Z.jsonl

A cell is (model, question, scenario, horizon). Per model: how many cells
both runs answered, the mean and median |difference| in probability, the
share that moved more than 0.1, and the mean signed difference (other minus
published); then each call's research, turns, cost and debrief. One draw per
loop cannot tell a loop effect from run-to-run spread, so `--prev` (the
previous cron run) prints the same numbers for the published loop against
itself: a loop difference that sits inside that spread is not a difference
yet. The loops are named from the rows (usage.harness; none = litellm).
"""
import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from redlines.logs import iter_rows  # noqa: E402


def load(path):
    return list(iter_rows(path))


def cells(rows):
    """{(label, question, scenario, horizon): probability}"""
    out = {}
    for r in rows:
        scenario = (r.get("scenario") or {}).get("id") or "unconditional"
        for f in r.get("forecasts") or []:
            if isinstance(f, dict) and isinstance(f.get("probability"), (int, float)):
                out[(r["label"], r["question_id"], scenario, f.get("horizon"))] = float(f["probability"])
    return out


def calls(rows):
    """{label: the call's first row} (evidence, usage and debrief ride on it)."""
    out = {}
    for r in rows:
        if r.get("usage") is not None:
            out.setdefault(r["label"], r)
    return out


def compare(a_rows, b_rows):
    """{label: {n, mean_abs, median_abs, moved, mean_signed}}: b minus a."""
    a, b = cells(a_rows), cells(b_rows)
    by_label = {}
    for k in a.keys() & b.keys():
        by_label.setdefault(k[0], []).append(b[k] - a[k])
    out = {}
    for label, ds in sorted(by_label.items()):
        ab = [abs(d) for d in ds]
        out[label] = {"n": len(ds), "mean_abs": statistics.fmean(ab), "median_abs": statistics.median(ab),
                      "moved": sum(x > 0.1 for x in ab) / len(ab), "mean_signed": statistics.fmean(ds)}
    return out


def loop_name(rows):
    """The loop a run went through: pi rows carry usage.harness; litellm's none."""
    for r in calls(rows).values():
        h = r["usage"].get("harness")
        return h["name"] if isinstance(h, dict) else "litellm"
    return "?"


def call_line(r):
    u = r.get("usage") or {}
    st = r.get("debrief_status") or {}
    h = u.get("harness") if isinstance(u.get("harness"), dict) else {}
    return (f"{len(r.get('evidence') or []):3d} research  {u.get('turns', 0):3d} turns  "
            f"${u.get('cost_usd') or 0:7.2f}  debrief {'ok' if st.get('complete') else 'INCOMPLETE'}"
            + ("  FORCED" if h.get("forced") else ""))


def table(title, result):
    print(title)
    print(f"  {'model':16} {'cells':>6} {'mean|d|':>8} {'median|d|':>9} {'>0.1':>6} {'mean d':>7}")
    for label, m in result.items():
        print(f"  {label:16} {m['n']:6d} {m['mean_abs']:8.3f} {m['median_abs']:9.3f} "
              f"{m['moved']:6.1%} {m['mean_signed']:+7.3f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", required=True, help="the cron run's instrument rows (the published loop)")
    ap.add_argument("--other", required=True, help="the shadow run's instrument rows (--harness, the other loop)")
    ap.add_argument("--prev", help="the previous cron run's instrument rows: the published loop's own spread")
    args = ap.parse_args(argv)
    base, other = load(args.base), load(args.other)
    b, o = loop_name(base), loop_name(other)
    if not compare(base, other):
        sys.exit("no cells in common: different instruments, or a run without forecasts")
    table(f"{o} vs {b}, same day ({o} minus {b}):", compare(base, other))
    if args.prev:
        table(f"\n{b} vs {b}, previous run (this run minus previous):", compare(load(args.prev), base))
    print("\ncalls:")
    w = max(len(b), len(o))
    for label, r in calls(base).items():
        print(f"  {label:16} {b:{w}} {call_line(r)}")
        p = calls(other).get(label)
        print(f"  {'':16} {o:{w}} {call_line(p) if p else 'no call'}")


if __name__ == "__main__":
    main()
