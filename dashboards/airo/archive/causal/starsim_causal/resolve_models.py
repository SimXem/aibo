"""Resolve the ECI roster (data/model_scores.csv) to OpenRouter model ids.

Usage:
  uv run python results/causal/starsim_causal/resolve_models.py                 # live catalog
  uv run python results/causal/starsim_causal/resolve_models.py --catalog f.json # saved GET /api/v1/models

Resolution, in order: MANUAL override -> exact match on the catalog's display
name -> the LiteLLM slug used as an id. Anything else is an error listing the
candidates: we never guess a model id silently. Writes starsim_causal/models.csv
with pricing/context/reasoning flags as of the catalog snapshot (pricing feeds
`run.py --dry-run` cost estimates only).
"""
import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[2] / "data" / "model_scores.csv"   # repo-root data/
OUT = HERE / "models.csv"
CATALOG_URL = "https://openrouter.ai/api/v1/models"

# Display names that are ambiguous in the catalog. Kimi K2: ForecastBench ran
# `kimi-k2-instruct`, i.e. the original July-2025 K2, which is
# moonshotai/kimi-k2 (not -0905, -thinking, k2.5/2.6/2.7).
MANUAL = {
    "MoonshotAI: Kimi K2": "moonshotai/kimi-k2",
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", help="path to a saved /api/v1/models response")
    a = ap.parse_args()
    if a.catalog:
        cat = json.load(open(a.catalog))["data"]
    else:
        cat = httpx.get(CATALOG_URL, timeout=60).raise_for_status().json()["data"]
    by_name = {m["name"]: m for m in cat}
    by_id = {m["id"]: m for m in cat}

    rows, errors = [], []
    with open(SRC) as fh:
        src = list(csv.DictReader(fh))
    for r in src:
        nm, slug = r["OpenRouterName"], r["LiteLLMSlug"]
        m = None
        if nm in MANUAL:
            m = by_id.get(MANUAL[nm])
            if m is None:
                errors.append(f"{nm}: MANUAL id {MANUAL[nm]} not in catalog"); continue
        elif nm in by_name:
            m = by_name[nm]
        elif slug and slug in by_id:
            m = by_id[slug]
        else:
            key = norm(nm.split(":")[-1])
            cands = [x["id"] for x in cat if key in norm(x["name"]) or norm(x["name"]) in norm(nm)]
            errors.append(f"{nm}: no exact match; candidates: {cands[:8]} — add to MANUAL")
            continue
        p = m.get("pricing", {})
        rows.append({
            "eci": r["ECI"], "name": nm, "openrouter_id": m["id"], "litellm_slug": slug,
            "fb_name": r["FBName"], "fb_overall": r["FBOverall"],
            "fb_ci_lo": r["FBOverallCILo"], "fb_ci_hi": r["FBOverallCIHi"],
            "context_length": m.get("context_length") or 0,
            "prompt_usd_per_m": round(float(p.get("prompt", 0)) * 1e6, 4),
            "completion_usd_per_m": round(float(p.get("completion", 0)) * 1e6, 4),
            "reasoning_capable": "reasoning" in m.get("supported_parameters", []),
            "max_completion_tokens": (m.get("top_provider") or {}).get("max_completion_tokens") or "",
            "resolved_at": dt.date.today().isoformat(),
        })
    if errors:
        print("UNRESOLVED:\n  " + "\n  ".join(errors), file=sys.stderr)
        sys.exit(1)
    rows.sort(key=lambda x: float(x["eci"]))
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"{'ECI':>7s}  {'openrouter_id':44s} {'$in/M':>6s} {'$out/M':>6s}  reasoning")
    for x in rows:
        print(f"{float(x['eci']):7.2f}  {x['openrouter_id']:44s} {x['prompt_usd_per_m']:6.2f} "
              f"{x['completion_usd_per_m']:6.2f}  {x['reasoning_capable']}")
    print(f"[saved] {len(rows)} models -> {OUT}")


if __name__ == "__main__":
    main()
