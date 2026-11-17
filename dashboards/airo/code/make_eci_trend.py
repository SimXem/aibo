#!/usr/bin/env python3
"""Write data/eci_trend_2026-08-21.json: metr_graph's ECI projection, DAILY
p25 / p50 / p75 from the anchor to end-2030, precomputed.

The anchor is the last frontier point (the projection's own start: a normal
around the fitted-trend score on that day, 80% CI +/-2, then the sampled
pace), so the file begins on that date and the tab's cone grows out of the
history rather than floating off the run date (project lead, 2026-08-28: the
cone and the history should touch).

The Capability tab (redlines/views/capability.py) draws the trend beside
the models' own ECI forecasts and looks up the trend at each run's target
date. It reads this file rather than running the replica because the page
is rebuilt on the box by code/publish_dashboard.sh under a python with no
numpy; the replica (code/eci_projection_metrgraph.py) needs it. Same CSV,
N and seed as data/eci_projection_2026-08-21.json, so every number here
agrees with that table to the tenth.

    python3 code/make_eci_trend.py           # writes the file (~20 s)
    python3 code/make_eci_trend.py --check   # verify it is current
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "code"))
from eci_projection_metrgraph import project  # noqa: E402

CSV = os.path.join(ROOT, "data", "epoch_capabilities_index_2026-08-21.csv")
PROJECTION = os.path.join(ROOT, "data", "eci_projection_2026-08-21.json")
OUT = os.path.join(ROOT, "data", "eci_trend_2026-08-21.json")
N, SEED = 400000, 1
END = "2030-12-31"


def build():
    proj = json.load(open(PROJECTION))
    start = proj["fit"]["anchor"]["date"]
    d, stop = datetime.fromisoformat(start), datetime.fromisoformat(END)
    targets = []
    while d <= stop:
        targets.append((d.strftime("%Y-%m-%d"), d))
        d += timedelta(days=1)
    table = project(CSV, N, SEED, targets)
    return {
        "what": "metr_graph ECI-tab projection at its defaults, daily p25/p50/p75 of the US-frontier ECI",
        "source": {**proj["source"], "replica": "code/eci_projection_metrgraph.py",
                   "n_samples": N, "seed": SEED, "table": os.path.relpath(PROJECTION, ROOT)},
        "fit": proj["fit"],
        "from": start, "to": END,
        "daily": [{"date": lab, "p25": r["p25"], "p50": r["p50"], "p75": r["p75"]} for lab, r in table.items()],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = json.dumps(build(), indent=0) + "\n"
    if args.check:
        cur = open(OUT).read() if os.path.exists(OUT) else ""
        if cur != text:
            sys.exit(f"{OUT} is stale — rerun {os.path.relpath(__file__, ROOT)}")
        print("ok")
        return
    open(OUT, "w").write(text)
    print(f"-> {OUT}: {len(json.loads(text)['daily'])} days")


if __name__ == "__main__":
    main()
