#!/usr/bin/env python3
"""Shim: the canonical ECI table + demo model set now live in redlines/registry.py.

This file exists only so `from eci_scores import ...` (run_eval.py,
make_demo_combined.py -- both running inside the forecastbench-sim uv env with
no third-party deps) keeps working unchanged. See redlines/registry.py for the
model table itself, and docs/model-set.md for the ECI-sourcing policy (always
from data/epoch_capabilities_index_2026-07-07.csv, never hand-copied).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redlines.registry import (  # noqa: E402
    EPOCH_CSV,
    load_epoch_index,
    demo_set_with_eci,
    MODELS as _MODELS,
)

# ── Demo model set: (model_id, label, official Epoch name, access) ──────────
# ECI is looked up from the CSV via the Epoch name -- no hand-copied numbers.
# Reconstructed from redlines.registry.MODELS; order matches the original
# literal exactly (both are ascending-ECI, and every value here is distinct).
DEMO_MODEL_SET = [
    (m["litellm_id"], m["label"], m["epoch_name"], m["litellm_id"].split("/", 1)[0])
    for m in sorted((m for m in _MODELS if "g4_ladder" in m["roles"]), key=lambda m: m["eci"])
]

# Optional gap-fillers for the 137-145 band (official spread has a 133->147 gap).
GAP_FILLERS = [
    (m["litellm_id"], m["label"], m["epoch_name"], m["litellm_id"].split("/", 1)[0])
    for m in sorted((m for m in _MODELS if "g4_gapfiller" in m["roles"]), key=lambda m: m["eci"])
]

# Alt OpenAI 161 anchor (slow reasoning model, pricier than fable-5):
_alt = next(m for m in _MODELS if m["key"] == "gpt-5.5-pro")
ALT_HIGH_ANCHOR = (_alt["litellm_id"], _alt["label"], _alt["epoch_name"],
                   _alt["litellm_id"].split("/", 1)[0])
del _alt


if __name__ == "__main__":
    for gf in (False, True):
        rows = demo_set_with_eci(include_gap_fillers=gf)
        lo, hi = rows[0]["eci"], rows[-1]["eci"]
        print(f"\nDemo set{' + gap-fillers' if gf else ''} "
              f"({len(rows)} models, ECI {lo} -> {hi}):")
        for r in rows:
            print(f"  {r['eci']:>3}  {r['label']:14s}  {r['model_id']:52s} [{r['access']}]")
