#!/usr/bin/env python3
"""Shim: the real implementation moved to redlines/views/graph2.py.

Graph 2 hydration: full severity ladder + resolution-free coherence check.
Kept so `python3 code/make_demo_graph2.py` keeps working unchanged. See
redlines/views/graph2.py for the actual build() logic/docstring.

    python3 code/make_demo_graph2.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redlines.hydrate import inject  # noqa: E402
from redlines.views.graph2 import build  # noqa: E402

if __name__ == "__main__":
    blob = build()
    path = inject("GRAPH2", blob, json_out="results/graph2_data.json")
    for h, d in blob["byHorizon"].items():
        for leg, s in d["legs"].items():
            print(f"  {h} {leg}: {len(s['causes'])} causes, "
                  f"{sum(len(c['rungs']) for c in s['causes'])} points, "
                  f"{len(s['violations'])} violation(s) / {s['pairsChecked']} pairs"
                  + (f", declines: {d['declines']}" if d["declines"] else ""))
    print(f"GRAPH2 -> {path.name}")
