"""Welfare: life expectancy and GDP growth as five percentiles, unconditional
and under the combined set's conditions (welfare.html, 2026-10-22).

The welfare instrument is AIRO's pipeline asked of another question set
(data/welfare_questions.json): the combined set copied as
data/welfare_conditions.json, asked under experiments/welfare.toml's five
prompts, its rows in results/conditional_runs_welfare.jsonl. As axes.py
reads its own set's log, this view reads that one: the pooled rows of the
current panel (redlines.conditional.load_conditional, redlines.runlog.
panel_rows), the newest protocol of the set's line, one day's calls. The
blob is the published pilot's window.__WELFARE__ (welfare-v1-pilot,
2026-10-01), so the pilot's own components (web/welfare/85-welfare.jsx)
draw it, plus the day, the condition each call ran and the prompts.

A model's number is the mean over its five pooled calls of the day, each
percentile on its own (redlines.runlog.pool), and its eci_forecast is pooled
the same way. A condition's shift is its p50 minus the same model's
unconditional p50. The day is the newest on which every model that answered
answered all five prompts: a day short of one would publish a mean of four.
With no such day the blob is None, which the page shows as unavailable.
"""
import json
import statistics as st
from collections import defaultdict
from datetime import date

from ..conditional import load_conditional, newest_protocol, protocol_line
from ..config import REPO_ROOT
from ..experiments import VARIANTS, load as load_experiment
from ..registry import model_colors
from ..runlog import elicitation_date, panel_rows, pool
from . import rationales
from .capability import SHORT_LABELS, _r, _scenario_values

SET = REPO_ROOT / "data" / "welfare_conditions.json"
LOG = REPO_ROOT / "results" / "conditional_runs_welfare.jsonl"
EXPERIMENT = "welfare"
PERCENTILES = ("p10", "p25", "p50", "p75", "p90")


def _day(r):
    """A call's run date: a call that ends past midnight UTC is still its run's."""
    return r.get("run_date") or elicitation_date(r)


def _rows(log_path, spec, experiment):
    """The pooled prompts' rows of the newest complete day, its protocol and the day."""
    rows = panel_rows(load_conditional(str(log_path), experiment=experiment["name"]))
    rows, proto = newest_protocol(rows, protocol_line(spec["protocol"]))
    rows = [r for r in rows if r.get("condition") in experiment["pooled"]]
    asked = defaultdict(lambda: defaultdict(set))
    for r in rows:
        asked[_day(r)][r["label"]].add(r["condition"])
    day = next((d for d in sorted(asked, reverse=True)
                if all(set(experiment["pooled"]) <= c for c in asked[d].values())), None)
    return [r for r in rows if _day(r) == day], proto, day


def _dated(text, target):
    """The set's {target_date}, as the run's prompt filled it (run_unified.resolve_set)."""
    if not target or not isinstance(text, str):
        return text
    d = date.fromisoformat(target)
    return text.replace("{target_date}", f"{d.strftime('%B')} {d.day}, {d.year}")


def _q(v):
    return {p: _r(v[p], 3) for p in PERCENTILES} if v else None


def build(log_path=None, set_path=None):
    spec = json.load(open(set_path or SET))
    experiment = load_experiment(EXPERIMENT)
    rows, proto, day = _rows(log_path or LOG, spec, experiment)
    if not rows:
        return None
    questions = json.load(open(REPO_ROOT / spec["questions"]))["questions"]
    colors = dict(model_colors())
    labels = [l for l, _ in model_colors() if l in {r["label"] for r in rows}]

    # Each (question, model, condition): the day's calls, pooled.
    reps = defaultdict(list)
    for r in rows:
        reps[(r["question_id"], r["label"], (r.get("scenario") or {}).get("id"))].append(r)
    pooled = {k: pool(rs, "percentiles") for k, rs in reps.items()}

    def cell(qid, label, cid, h):
        r = pooled.get((qid, label, cid)) or {}
        return next((f["percentiles"] for f in r.get("forecasts", []) if f["horizon"] == h), None)

    el = spec["elicit"]
    calls = defaultdict(dict)
    for r in rows:
        if (r.get("elicited") or {}).get(el["key"]):
            calls[r["label"]][r["call_id"]] = r["elicited"][el["key"]]
    eci = {l: {f: _r(st.mean(c[f] for c in cs.values()), 2) for f in el["fields"]}
           for l, cs in calls.items()}
    targets = sorted({(r.get("elicited") or {}).get("target_date") for r in rows} - {None})
    target = targets[-1] if targets else None

    # The capability rows' sub-line is the level each named (median over the
    # day's calls), as on the main page's Capability tab.
    levels = _scenario_values(rows)
    conditions = [{"id": c["id"], "label": SHORT_LABELS.get(c.get("field"), c["label"]),
                   "group": c["group"],
                   "leapId": c.get("leap_id") or (f"ECI ≈ {levels[c['id']]:.0f}" if c["id"] in levels else None),
                   "assume": _dated(c["assume"], target), "description": c.get("description") or "",
                   "levels": {l: (eci.get(l) or {}).get(c["field"]) if c.get("field") else None
                              for l in labels}}
                  for c in spec["conditions"]]

    out = []
    for q in questions:
        by_h = {}
        for h in q["horizons"]:
            base = {l: cell(q["id"], l, None, h) for l in labels}
            bars = []
            for c in conditions:
                models = []
                for l in labels:
                    v = cell(q["id"], l, c["id"], h)
                    if v:
                        models.append({"label": l, "color": colors.get(l), "q": _q(v),
                                       "shift": _r(v["p50"] - base[l]["p50"], 3) if base[l] else None,
                                       "grounded": pooled[(q["id"], l, c["id"])].get("grounded", True)})
                bars.append({"id": c["id"], "group": c["group"], "label": c["label"],
                             "leapId": c["leapId"], "models": models})
            by_h[h] = {"baselines": [{"label": l, "color": colors.get(l), "q": _q(base[l])}
                                     for l in labels if base[l]],
                       "bars": bars}
        out.append({"id": q["id"], "short": q["short"], "heading": q["heading"],
                    "railLabel": q["rail_label"], "group": q["group"], "color": q["color"],
                    "unit": q["unit"], "horizons": q["horizons"], "text": q["text"],
                    "criteria": q["criteria"], "byHorizon": by_h})

    # What the day's calls cost and read: usage rides on each call's first row.
    usage, hits = {}, {}
    for r in rows:
        if r.get("usage"):
            u = usage.setdefault(r["label"], {"turns": 0, "cost_usd": 0.0})
            u["turns"] += r["usage"].get("turns") or 0
            u["cost_usd"] = round(u["cost_usd"] + (r["usage"].get("cost_usd") or 0.0), 6)
            hits[r["label"]] = hits.get(r["label"], 0) + (r.get("search_hits") or 0)

    return {
        "run": max(r["run_id"] for r in rows),
        "runs": sorted({r["run_id"] for r in rows}),
        "day": day,
        "protocol": proto,
        "rows": len(rows),
        "models": [{"label": l, "color": colors.get(l)} for l in labels],
        "conditions": conditions,
        "conditioning": {g["key"]: {"instruction": _dated(g["instruction"], target),
                                    "assumption": _dated(g["assumption"], target)} for g in spec["groups"]},
        "groups": [{"key": g["key"], "heading": g["heading"]} for g in spec["groups"]],
        "questions": out,
        "targetDate": target,
        "eciForecast": eci,
        "usage": usage,
        "searchHits": hits,
        "rationales": rationales.build(rows=[r for r in rows if r.get("scenario") is None]),
        # The five prompts whose mean each number is, in the experiment's order.
        "prompts": [{"condition": cid, "variant": experiment["conditions"][cid]["variant"],
                     "text": VARIANTS[experiment["conditions"][cid]["variant"]]}
                    for cid in experiment["pooled"]],
    }
