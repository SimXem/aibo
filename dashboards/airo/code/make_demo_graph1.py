#!/usr/bin/env python3
"""Shim: the real implementation moved to redlines/views/graph1.py.

Kept so `python3 code/make_demo_graph1.py` (no flags, same as before) and
`from make_demo_graph1 import MODEL_COLORS, load_runlog` (code/make_demo_graph2.py's
original import) keep working unchanged. See redlines/views/graph1.py for the
blob-building logic; SHORT + per-question category now live in
data/starter_questions.json (see redlines/questions.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redlines.hydrate import REPO, inject  # noqa: E402,F401
from redlines.runlog import load_runlog  # noqa: E402,F401
from redlines.views.graph1 import MODEL_COLORS, build  # noqa: E402,F401

if __name__ == "__main__":
    blob = build()
    path = inject("GRAPH1", blob, json_out="results/graph1_data.json")
    n = sum(len(q["series"]) for q in blob["questions"])
    print(f"GRAPH1: {len(blob['questions'])} questions, {n} model series, "
          f"{len(blob['runs'])} run(s) -> {path.name}")
