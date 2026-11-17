"""Paper Figure: what the level of frontier capability does to a forecast
(the Capability tab), from results/capability_data.json.

The same chart as conditional.py -- one panel per horizon, one row per
scenario, ensemble ratio as a bar and per-model dots -- on the
default variant's rows. Scenarios are the model's OWN percentiles of the
frontier ECI at the target date (Step 1 of the prompt asks for them), so a
row label names the percentile and the ensemble's level for it.
"""
from __future__ import annotations

from . import conditional

PCT = {"p10": "10th", "p25": "25th", "p50": "50th (median)", "p75": "75th", "p90": "90th"}


def variant(blob: dict) -> dict:
    key = blob.get("defaultVariant")
    return next(v for v in blob["variants"] if v["key"] == key)


def labels(v: dict, question_id: str, horizon: str) -> dict:
    """scenario id -> 'Own 25th percentile (ECI ~166)'."""
    q = next(q for q in v["questions"] if q["id"] == question_id)
    out = {}
    for b in q["byHorizon"][horizon]["bars"]:
        c = next((c for c in v["conditions"] if c["id"] == b["id"]), {})
        pct = PCT.get(c.get("field"), c.get("field", b["id"]))
        lvl = c.get("level")
        out[b["id"]] = f"Own {pct} pct." + (rf" (ECI $\approx$ {lvl:.0f})" if lvl is not None else "")
    return out


def render(blob: dict, question_id: str = "catastrophe:ai"):
    v = variant(blob)
    h = v["horizons"][0]
    return conditional.render(v, question_id, short=labels(v, question_id, h))
