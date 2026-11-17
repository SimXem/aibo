"""Made-up answers in the harness's shape, so the page and the tests need no calls.

Not forecasts: each value is the series' last point plus a fixed step per
scenario and a little noise seeded by the model and the date. Rows made this
way are stamped `synthetic` (run.py) and the page says so across the top.
"""
import hashlib
import random
import statistics

from . import survey as S

NOTE = "Synthetic placeholder, not a model's forecast."
STEP = {S.UNCONDITIONAL: 0.25, "slow": -0.4, "moderate": 0.15, "rapid": 1.1}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def answer(survey, history, today, model):
    rng = random.Random(int(hashlib.sha256(f"{model}|{today}".encode()).hexdigest()[:12], 16))
    cells = {}
    for q in survey["questions"]:
        series = [v for _, v in history.get(q["history"], [])]
        last = series[-1]
        spread = statistics.pstdev(series[-15:]) if len(series) > 3 else abs(last) * 0.4
        spread = spread or abs(last) * 0.1 or 1.0
        lo, hi = q["bounds"]
        forecasts = {}
        for h in q["horizons"]:
            n = min((int(h["id"]) - 2025) / 5, 2)       # further out, further from the last point
            for s in S.scenario_ids(survey):
                mid = _clamp(last + spread * n * (STEP[s] + rng.uniform(-0.15, 0.15)), lo, hi)
                vals = {"p50": round(mid, 3)}
                if "p10" in S.percentiles(q, s):
                    vals["p10"] = round(_clamp(mid - 1.2 * spread * n, lo, hi), 3)
                    vals["p90"] = round(_clamp(mid + 1.4 * spread * n, lo, hi), 3)
                forecasts.setdefault(h["id"], {})[s] = vals
        cells[q["id"]] = {"question_id": q["id"], "forecasts": forecasts, "rationale": NOTE}
    slow = round(25 + rng.uniform(-6, 6), 1)
    rapid = round(22 + rng.uniform(-6, 6), 1)
    final = {"scenario_probabilities": {"slow": slow, "moderate": round(100 - slow - rapid, 1), "rapid": rapid},
             "indicator_importance": {"research": 30, "problem_solving": 30, "creativity": 5, "agency": 20, "robotics": 15},
             "household_robot": round(rng.uniform(4, 15), 1), "reliability": round(rng.uniform(35, 65), 1),
             "rationale": NOTE, "key_sources": []}
    return cells, final


def harness_run(survey, history, today):
    """A stand-in for fri_forecaster.harness.run that makes no call."""
    def run(*, model, workdir, **_):
        cells, final = answer(survey, history, today, model)
        return {"rc": 0, "seconds": 0.0, "evidence": [], "cells": cells, "answer": final,
                "usage": {"turns": 0, "cost_usd": 0.0, "harness": "synthetic"},
                "delivery": {"cells_calls": 1, "cells_in_pieces": len(cells), "cells_in_final": 0},
                "forced": False, "debrief": None, "trace": None, "workdir": workdir}
    return run
