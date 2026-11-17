#!/usr/bin/env python3
"""Shim: the real implementation moved to redlines/coherence.py.

Audit every coherence constraint the question set implies — no resolution
needed. See that module for what each constraint means and why the BRACKET row
rests on wording judgments.

    python3 code/audit_coherence.py                                # live log
    python3 code/audit_coherence.py archive/legacy-forecasts/forecast_runs.jsonl
    python3 code/audit_coherence.py --compare                      # both

tests/test_coherence.py imports redlines.coherence directly and fails the build
if a protocol regression puts the violation rates back near the legacy ones.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redlines.coherence import audit, read, totals  # noqa: E402
from redlines.config import REPO_ROOT  # noqa: E402

LEGACY = REPO_ROOT / "archive" / "legacy-forecasts" / "forecast_runs.jsonl"
LEGACY_RUNS = REPO_ROOT / "archive" / "legacy-forecasts" / "runs"

TITLES = {
    "HORIZON": "P non-decreasing over time",
    "LADDER": "P non-increasing over severity",
    "CROSS": "cause <= all causes",
    "BRACKET": "catastrophe question vs its ladder rung",
    "SUBSET": "narrower question <= broader",
}


def report(name, results, show):
    print(f"\n{name}")
    for key, title in TITLES.items():
        r = results[key]
        label = f"{key:8} {title}"
        if not r["n"]:
            print(f"  {label:44} {'—':>12}  (nothing to check)")
            continue
        print(f"  {label:44} {r['bad']:4d}/{r['n']:<5d} ({r['rate']:5.1f}%)")
        for e in r["examples"][:show]:
            print(f"       {e}")
        if len(r["examples"]) > show:
            print(f"       ... and {len(r['examples']) - show} more")
    t = totals(results)
    print(f"  {'TOTAL':44} {t['bad']:4d}/{t['n']:<5d} ({t['rate']:5.1f}%)")
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="run log to audit (default: the live one)")
    ap.add_argument("--compare", action="store_true",
                    help="audit the retired per-question log alongside the live one")
    ap.add_argument("--show", type=int, default=3, help="examples per constraint")
    args = ap.parse_args()

    print("=" * 74)
    print("COHERENCE AUDIT — every constraint the question set implies")
    print("=" * 74)

    if args.compare:
        a = report(f"LEGACY  one call per question  ({LEGACY.name})",
                   audit(read(LEGACY, LEGACY_RUNS)), args.show)
        b = report("UNIFIED one call per model     (live log)",
                   audit(read()), args.show)
        print(f"\n  {a['rate']:.1f}%  ->  {b['rate']:.1f}%")
        return

    path = Path(args.path) if args.path else None
    P = read(path) if path else read()
    report(path.name if path else "live log", audit(P), args.show)


if __name__ == "__main__":
    main()
