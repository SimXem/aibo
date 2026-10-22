"""Welfare: life expectancy and GDP growth as five percentiles, unconditional
and under the combined set's conditions, drawn by AIRO's own panels on
welfare.html (2026-10-22).

The welfare instrument is AIRO's pipeline asked of another question set
(data/welfare_questions.json): the combined set copied as
data/welfare_conditions.json, asked under experiments/welfare.toml's five
prompts, its rows in results/conditional_runs_welfare.jsonl. As axes.py
reads its own set's log, this view reads that one: the pooled rows of the
current panel (redlines.conditional.load_conditional, redlines.runlog.
panel_rows) under the newest protocol of the set's line.

It builds the blobs index.html's panels read, in their shapes, under their
names -- TIMELINE, GRAPH1, CONDITIONAL, CAPABILITY, METHOD, RATIONALES -- so
the same components draw welfare.html. A cell's valueKind is "percentiles":
`p` is a p50 in the question's unit, `q` the five percentiles, and a
condition's `shift` the change of p50 from the same model's unconditional
(redlines/views/conditional.py's `ratio`, in units). The ensemble is the
median across models of each percentile.

A model's number is the mean over its five pooled calls of a day, each
percentile on its own (redlines.runlog.pool); its eci_forecast is pooled the
same way. A day counts once every model that answered answered all five
prompts: a day short of one would publish a mean of four. The Timeline has
every such day; the other panels the newest. With none, every panel shows
itself unavailable.
"""
import json
import statistics as st
from collections import defaultdict
from datetime import date

from ..conditional import group_view, load_conditional, newest_protocol, protocol_line
from ..config import REPO_ROOT
from ..experiments import load as load_experiment
from ..registry import model_colors
from ..runlog import elicitation_date, panel_rows, pool
from . import capability, method, rationales
from .capability import SHORT_LABELS, _r, _scenario_values
from .timeline import condition_legend

SET = REPO_ROOT / "data" / "welfare_conditions.json"
LOG = REPO_ROOT / "results" / "conditional_runs_welfare.jsonl"
EXPERIMENT = "welfare"
PERCENTILES = ("p10", "p25", "p50", "p75", "p90")
DEFAULT_HORIZON = "2050"          # the one every welfare question is asked over
KIND = "percentiles"


def _day(r):
    """A call's run date: a call that ends past midnight UTC is still its run's."""
    return r.get("run_date") or elicitation_date(r)


def _rows(log_path, spec, experiment):
    """The pooled prompts' rows of every complete day, the protocol and the days."""
    rows = panel_rows(load_conditional(str(log_path), experiment=experiment["name"]))
    rows, proto = newest_protocol(rows, protocol_line(spec["protocol"]))
    rows = [r for r in rows if r.get("condition") in experiment["pooled"]]
    asked = defaultdict(lambda: defaultdict(set))
    for r in rows:
        asked[_day(r)][r["label"]].add(r["condition"])
    days = sorted(d for d in asked if all(set(experiment["pooled"]) <= c for c in asked[d].values()))
    return [r for r in rows if _day(r) in days], proto, days


def _pooled(rows):
    """{(question, model, condition id or None): pooled row}: a day's calls (runlog.pool)."""
    reps = defaultdict(list)
    for r in rows:
        reps[(r["question_id"], r["label"], (r.get("scenario") or {}).get("id"))].append(r)
    return {k: pool(rs, KIND) for k, rs in reps.items()}


def _at(pooled, key, h):
    r = pooled.get(key) or {}
    return next((f[KIND] for f in r.get("forecasts", []) if f["horizon"] == h), None)


def _q(v):
    return {p: _r(v[p], 3) for p in PERCENTILES} if v else None


def _ensemble(qs):
    """The median across models of each percentile."""
    qs = [q for q in qs if q]
    return {p: _r(st.median(q[p] for q in qs), 3) for p in PERCENTILES} if qs else None


def _median(xs):
    xs = [x for x in xs if x is not None]
    return _r(st.median(xs), 3) if xs else None


def _meta(q):
    """A question as every panel's rail, heading and question box read it."""
    return {"id": q["id"], "name": q["heading"], "short": q["short"], "heading": q["heading"],
            "railLabel": q["rail_label"], "group": q["group"], "groupKey": q["group"], "color": q["color"],
            "severity": None, "text": q["text"], "criteria": q["criteria"], "valueKind": KIND,
            "unit": q["unit"], "horizons": q["horizons"]}


def _cells(questions, pooled, labels, colors, conditions):
    """CondDeltaChart's questions for one group's conditions: per horizon each
    model's unconditional and, per condition, its p50, percentiles and shift."""
    out = []
    for q in questions:
        by_h = {}
        for h in q["horizons"]:
            base = {l: _at(pooled, (q["id"], l, None), h) for l in labels}
            draws = {l: [d["p50"] for d in (pooled.get((q["id"], l, None)) or {}).get("draws", {}).get(h, [])]
                     for l in labels}
            bars = []
            for c in conditions:
                models = []
                for l in labels:
                    v = _at(pooled, (q["id"], l, c["id"]), h)
                    if v:
                        models.append({"label": l, "color": colors.get(l), "p": _r(v["p50"], 3), "q": _q(v),
                                       "shift": _r(v["p50"] - base[l]["p50"], 3) if base[l] else None,
                                       "grounded": pooled[(q["id"], l, c["id"])].get("grounded", True)})
                if models:
                    bars.append({"id": c["id"], "label": c["label"], "leapId": c["leapId"],
                                 "shift": _median(m["shift"] for m in models),
                                 "pMedian": _median(m["p"] for m in models),
                                 "nModels": len(models), "models": models})
            by_h[h] = {"valueKind": KIND, "unit": q["unit"],
                       "baselineMedian": _median(b["p50"] for b in base.values() if b),
                       "baselines": [{"label": l, "color": colors.get(l), "p": _r(b["p50"], 3), "q": _q(b),
                                      "n": len(draws[l]), "values": [_r(v, 3) for v in draws[l]]}
                                     for l, b in base.items() if b],
                       "bars": bars, "note": None}
        out.append({**_meta(q), "byHorizon": by_h})
    return out


def _timeline(questions, rows, days, labels, colors, experiment):
    """TIMELINE: per complete day, each model's p50 (its five prompts' mean),
    the ensemble's percentiles, and each prompt's panel median."""
    by_day = {d: _pooled([r for r in rows if _day(r) == d and r.get("scenario") is None]) for d in days}
    prompt = defaultdict(dict)          # (day, question, condition, horizon) -> {model: percentiles}
    for r in rows:
        if r.get("scenario") is None:
            for f in r["forecasts"]:
                prompt[(_day(r), r["question_id"], r["condition"], f["horizon"])][r["label"]] = f[KIND]
    out = []
    for q in questions:
        hs = q["horizons"]
        series = [{"label": l, "color": colors.get(l),
                   "ps": {h: [_r((_at(by_day[d], (q["id"], l, None), h) or {}).get("p50"), 3) for d in days] for h in hs}}
                  for l in labels]
        band = {h: [_ensemble(_at(by_day[d], (q["id"], l, None), h) for l in labels) for d in days] for h in hs}
        models = {c: {h: [{l: _r(v["p50"], 3) for l, v in prompt.get((d, q["id"], c, h), {}).items()} or None
                          for d in days] for h in hs}
                  for c in experiment["pooled"]}
        out.append({**_meta(q), "value_kind": KIND, "series": series,
                    "median": {h: [(e or {}).get("p50") for e in band[h]] for h in hs}, "band": band,
                    "variants": {c: {h: [_median(ms.values()) if ms else None for ms in hs_[h]] for h in hs}
                                 for c, hs_ in models.items()},
                    "variantModels": models,
                    # Each prompt's own ensemble percentiles, drawn as its bar.
                    "variantBands": {c: {h: [_ensemble(prompt.get((d, q["id"], c, h), {}).values()) for d in days]
                                         for h in hs} for c in experiment["pooled"]},
                    "declined": {}})
    return {"snapshots": [{"date": d, "label": f"{date.fromisoformat(d):%b} {date.fromisoformat(d).day}",
                           "draws": 1, "runs": sorted({r["run_id"] for r in rows if _day(r) == d})} for d in days],
            "questions": out if days else [],
            "variants": condition_legend({c: experiment["conditions"][c]["variant"] for c in experiment["pooled"]},
                                         EXPERIMENT),
            "instrumentInfo": {"available": bool(days)}}


def _graph1(questions, pooled, labels, colors, rows, groups):
    """GRAPH1: the newest day's p50 per model per horizon, the ensemble's percentiles."""
    out = []
    for q in questions:
        hs = q["horizons"]
        base = {(l, h): _at(pooled, (q["id"], l, None), h) for l in labels for h in hs}
        band = {h: _ensemble(base[(l, h)] for l in labels) for h in hs}
        out.append({**_meta(q), "category": q["group"], "valueKind": KIND,
                    "horizonLabels": {h: f"{h} ({q['horizon_meaning'][h]})" for h in hs},
                    "resolvesOn": next((r["resolves_on"] for r in rows if r.get("resolves_on")), {}),
                    "series": [{"label": l, "color": colors.get(l),
                                "ps": {h: _r(base[(l, h)]["p50"], 3) for h in hs if base[(l, h)]}} for l in labels],
                    "median": {h: band[h]["p50"] for h in hs if band[h]}, "band": band,
                    "ci": {}, "human": [], "declined": []})
    return {"title": "Forecasts by horizon", "railTitle": "Question",
            "runs": sorted({r["run_id"] for r in rows}),
            "latest": max((r["elicited_at"] for r in rows), default=None),
            "models": [{"label": l, "color": colors.get(l)} for l in labels],
            "categories": [{"key": g["key"], "label": g["key"], "group": g["key"],
                            "color": next(q["color"] for q in questions if q["group"] == g["key"])} for g in groups],
            "questions": out if rows else []}


def build(log_path=None, set_path=None):
    """{blob name: blob} for welfare.html (web/welfare/manifest.json)."""
    spec = json.load(open(set_path or SET))
    qspec = json.load(open(REPO_ROOT / spec["questions"]))
    experiment = load_experiment(EXPERIMENT)
    all_rows, proto, days = _rows(log_path or LOG, spec, experiment)
    rows = [r for r in all_rows if days and _day(r) == days[-1]]
    colors = dict(model_colors())
    labels = [l for l, _ in model_colors() if l in {r["label"] for r in rows}]
    pooled = _pooled(rows)
    questions = qspec["questions"]

    el = spec["elicit"]
    calls = defaultdict(dict)
    for r in rows:
        if (r.get("elicited") or {}).get(el["key"]):
            calls[r["label"]][r["call_id"]] = r["elicited"][el["key"]]
    eci = {l: {f: _r(st.mean(c[f] for c in calls[l].values()), 2) for f in el["fields"]} for l in labels if calls[l]}
    targets = sorted({(r.get("elicited") or {}).get("target_date") for r in rows} - {None})
    target = targets[-1] if targets else None
    # The set's texts as the run's prompt filled them (run_unified.resolve_set).
    if target:
        t = date.fromisoformat(target)
        spec = json.loads(json.dumps(spec).replace("{target_date}", f"{t:%B} {t.day}, {t.year}"))

    common = {"protocol": proto, "runs": sorted({r["run_id"] for r in rows}), "rows": len(rows),
              "repeats": {l: len({r["call_id"] for r in rows if r["label"] == l}) for l in labels},
              "models": [{"label": l, "color": colors.get(l)} for l in labels],
              "horizons": ["2030", "2050", "2100"], "defaultHorizon": DEFAULT_HORIZON,
              "instrumentInfo": {"available": bool(rows)}}
    policy = group_view(spec, "policy")
    conditional = {**common, "title": "Welfare forecasts conditional on LEAP Wave 12 policies",
                   "source": policy["source"], "conditioning": policy["conditioning"],
                   "instrument": {"set": "data/welfare_conditions.json", "group": "policy", "slug": spec["slug"]},
                   "conditions": [{"id": c["id"], "label": c["label"], "leapId": c["leap_id"], "assume": c["assume"],
                                   "description": c.get("description")} for c in policy["conditions"]],
                   "questions": _cells(questions, pooled, labels, colors,
                                       [{"id": c["id"], "label": c["label"], "leapId": c["leap_id"]}
                                        for c in policy["conditions"]]) if rows else []}

    # The capability rows' sub-line is the level each named (median over the
    # day's calls), and their labels the Capability tab's own.
    cap = group_view(spec, "capability")
    levels = _scenario_values(rows)
    cap_conditions = [{"id": c["id"], "label": SHORT_LABELS.get(c["field"], c["label"]), "promptLabel": c["label"],
                       "leapId": f"ECI ≈ {levels[c['id']]:.0f}" if c["id"] in levels else None,
                       "field": c["field"], "assume": c["assume"], "description": el["text"],
                       "levels": {l: eci.get(l, {}).get(c["field"]) for l in labels}}
                      for c in cap["conditions"]]
    trend = capability._trend([target])["at"].get(target) if target else None
    aibo_cap = capability.build()
    variant = {**common, "key": "6mo", "label": "6 months", "targetDate": target,
               "conditioning": cap["conditioning"], "conditions": cap_conditions,
               "questions": _cells(questions, pooled, labels, colors, cap_conditions),
               "forecast": {"models": [{"label": l, "color": colors.get(l), **eci[l],
                                        "n": len(calls[l])} for l in labels if l in eci],
                            "ensemble": {f: _median(eci[l][f] for l in eci) for f in el["fields"]},
                            "trend": trend}}

    return {
        "TIMELINE": _timeline(questions, all_rows, days, labels, colors, experiment),
        "GRAPH1": _graph1(questions, pooled, labels, colors, rows, qspec["groups"]),
        "CONDITIONAL": conditional,
        # AIRO's frontier ECI history, trend and LEAP's ECI forecast, with
        # the welfare day's own forecast and conditions.
        "CAPABILITY": {"eci": aibo_cap["eci"], "leap": aibo_cap["leap"], "subject": "forecasts",
                       "variants": [variant] if rows else [], "defaultVariant": "6mo"},
        "METHOD": method.build(today=date.fromisoformat(days[-1]) if days else None,
                               experiment=EXPERIMENT, rows=rows),
        "RATIONALES": rationales.build(rows=[r for r in all_rows if r.get("scenario") is None]),
        # The day shown and the five prompts each number is the mean of.
        "WELFARE": {"day": days[-1] if days else None, "protocol": proto,
                    "usage": {l: round(sum((r.get("usage") or {}).get("cost_usd") or 0 for r in rows
                                           if r["label"] == l), 2) for l in labels},
                    "prompts": [{"condition": v["id"], "text": v["text"]} for v in condition_legend(
                        {c: experiment["conditions"][c]["variant"] for c in experiment["pooled"]}, EXPERIMENT)]},
    }
