#!/usr/bin/env python3
"""Shim: the real implementation moved to redlines/views/databank.py.

Kept so `python3 code/make_demo_databank.py [--canaries]` keeps working
unchanged. See redlines/views/databank.py for the blob-building logic.

CANARIES ARE OFF BY DEFAULT. The 2026-08-10 project call deferred indicator
questions to v2 ("too complex for v1, limited value-add now") — v1 ships the
top-level risk decomposition only. The machinery is gated, not deleted, because
v2 wants it back: pass --canaries to restore them.

    python3 code/make_demo_databank.py              # v1 — bottom-line only
    python3 code/make_demo_databank.py --canaries   # v2 preview
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redlines.hydrate import inject  # noqa: E402
from redlines.views.databank import build  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--canaries", action="store_true",
                    help="include canary rows (v2; deferred out of v1 on 2026-08-10)")
    args = ap.parse_args()

    blob = build(include_canaries=args.canaries)
    bl_n = blob["counts"]["bottomLine"]
    can_n = blob["counts"]["canary"]
    path = inject("DATABANK", blob, json_out="results/databank_data.json")
    tail = f" + {can_n} canary" if can_n else " (canaries off — v2)"
    print(f"DATABANK: {bl_n} bottom-line{tail} rows -> {path.name}")
