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

Since 2026-10-27 the set also asks two AI-benefit questions as
probabilities (`value_kind`, run_unified.question_mode), on AIRO's six
horizons. They are drawn exactly as AIRO's probability questions are: their
rows go through AIRO's own builders -- redlines.views.conditional._variant
for Policy levers and Capability (tabs 2030, 2050, 2100), timeline._prob_row
for the Timeline, graph1's series and _ensemble for Graph 1 -- and come
first on every rail.
"""
import json
import statistics as st
from collections import defaultdict
from datetime import date

from ..conditional import (apply_or, group_rows, group_view, level_or, load_conditional, newest_protocol,
                           protocol_line)
from ..config import REPO_ROOT
from ..experiments import load as load_experiment
from ..questions import horizon_label, resolves_on
from ..registry import model_colors
from ..runlog import elicitation_date, panel_rows, pool
from . import capability, method, rationales
from .capability import SHORT_LABELS, _r, _scenario_values
from .conditional import _variant
from .graph1 import _ensemble as _g1_ensemble
from .timeline import _prob_row, condition_cells, condition_legend

SET = REPO_ROOT / "data" / "welfare_conditions.json"
LOG = REPO_ROOT / "results" / "conditional_runs_welfare.jsonl"
EXPERIMENT = "welfare"
PERCENTILES = ("p10", "p25", "p50", "p75", "p90")
DEFAULT_HORIZON = "2050"          # the one every welfare question is asked over
KIND = "percentiles"
PROBABILITY = "probability"
# A probability question's Policy levers and Capability tabs (2026-10-27).
PROB_HORIZONS = ("2030", "2050", "2100")
# _variant's ladder spec: welfare has no causes or rungs to order or fold.
NO_LADDER = {"causes": [], "rungs": []}


def _kind(q):
    """A question's value kind: its own `value_kind` (the AI-benefit
    questions' "probability"), else the set's percentiles."""
    return PROBABILITY if q.get("value_kind") == PROBABILITY else KIND


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
            "severity": None, "text": q["text"], "criteria": q["criteria"], "valueKind": _kind(q),
            "unit": q["unit"], "horizons": q["horizons"], "marks": _today(q)}


def _today(q):
    """The question's latest reported value, a faint dashed line on the
    Timeline and Graph 1 (their `marks`, labelled inside the plot; 2026-10-23)."""
    t = q.get("today")
    if not t:
        return []
    v = f"{t['value']:.1f}" + ("" if q["unit"] == "years" else "%")
    return [{"v": t["value"], "label": f"Today ({t['year']}): {v}", "source": t["source"], "inside": True}]


def _of(rows, questions):
    """The rows of these questions."""
    ids = {q["id"] for q in questions}
    return [r for r in rows if r["question_id"] in ids]


def _as_airo(q):
    """A probability question as AIRO's builders read a cross-cutting one."""
    return {**q, "category": "crosscutting", "name": q["heading"], "severity": {"kind": "none"}}


def _airo_row(row, q):
    """An AIRO builder's question entry, labelled and railed as welfare's."""
    return {**row, **{k: v for k, v in _meta(q).items() if k != "horizons"}}


def _prob_cells(rows, spec, group, questions, colors):
    """The probability questions' Policy levers or Capability cells: AIRO's own
    (conditional._variant) from one group's rows, on PROB_HORIZONS."""
    v = _variant(group_rows(_of(rows, questions), group), group_view(spec, group), PROB_HORIZONS, NO_LADDER,
                 {q["id"]: _as_airo(q) for q in questions}, colors)
    got = {x["id"]: x for x in v["questions"]}
    return [_airo_row(got[q["id"]], q) for q in questions if q["id"] in got]


def _graph1_prob(q, rows, labels, colors, qspec):
    """Graph 1's row for a probability question, as graph1.build makes AIRO's:
    each model's pooled point, its 95% interval from the day's draws (an odds
    ratio on the logit), the ensemble median and interval (graph1._ensemble)."""
    hs = q["horizons"]
    reps = defaultdict(list)
    for r in rows:
        if r["question_id"] == q["id"] and r.get("scenario") is None:
            reps[r["label"]].append(r)
    series = []
    for l in labels:
        if not reps.get(l):
            continue
        r = pool(reps[l], PROBABILITY)
        ps = {f["horizon"]: round(100 * f["probability"], 3) for f in r["forecasts"] if f["horizon"] in hs}
        raw = {h: vs for h, vs in (r.get("draws") or {}).items() if h in hs}
        ci_or = {h: level_or(vs) for h, vs in raw.items()}
        if ps:
            series.append({"label": l, "color": colors.get(l), "ps": ps,
                           "draws": {h: [round(100 * v, 3) for v in vs] for h, vs in raw.items()},
                           "ci": {h: [round(100 * x, 3) for x in apply_or(ps[h] / 100, c)]
                                  for h, c in ci_or.items() if c and h in ps},
                           "ciOr": ci_or})
    median, ci = _g1_ensemble(series, hs)
    as_of = max((_day(r) for r in rows), default=None)
    return {**_meta(q), "category": q["group"], "severityShort": None, "details": None,
            "horizonLabels": {h: horizon_label(h, qspec, as_of) for h in hs},
            "resolvesOn": {h: resolves_on(h, as_of, qspec) for h in hs} if as_of else {},
            "series": series, "declined": [], "median": median, "ci": ci,
            "replicates": max((len(v) for v in reps.values()), default=0), "human": []}


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


def _timeline(questions, rows, days, labels, colors, experiment, qspec):
    """TIMELINE: per complete day, each model's p50 (its five prompts' mean),
    the ensemble's percentiles, and each prompt's panel median. A probability
    question's row is AIRO's (timeline._prob_row)."""
    prob = [q for q in questions if _kind(q) == PROBABILITY]
    uncond = [r for r in _of(rows, prob) if r.get("scenario") is None]
    reps = defaultdict(list)
    for r in uncond:
        reps[(_day(r), r["question_id"], r["label"])].append(r)
    by_day_p = {k: pool(rs, PROBABILITY) for k, rs in reps.items()}
    # condition_cells dates a row by elicitation_date, which reads the run's
    # date only for AIRO's instrument: give it each row's run day (_day).
    prompts = condition_cells([{**r, "elicited_at": _day(r)} for r in uncond])
    prob_rows = {q["id"]: _airo_row(_prob_row(_as_airo(q), {"category": q["group"], "railLabel": q["rail_label"]},
                                               by_day_p, days, q["horizons"], prompts), q)
                 for q in prob}
    questions = [q for q in questions if _kind(q) == KIND]
    rows = _of(rows, questions)
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
    out = [prob_rows[q["id"]] for q in prob] + out
    return {"snapshots": [{"date": d, "label": f"{date.fromisoformat(d):%b} {date.fromisoformat(d).day}",
                           "draws": 1, "runs": sorted({r["run_id"] for r in rows if _day(r) == d})} for d in days],
            "questions": out if days else [],
            "variants": condition_legend({c: experiment["conditions"][c]["variant"] for c in experiment["pooled"]},
                                         EXPERIMENT),
            "instrumentInfo": {"available": bool(days)}}


def _graph1(questions, pooled, labels, colors, rows, qspec):
    """GRAPH1: the newest day's p50 per model per horizon, the ensemble's
    percentiles; a probability question's row is AIRO's (_graph1_prob)."""
    out = []
    for q in questions:
        if _kind(q) == PROBABILITY:
            out.append(_graph1_prob(q, rows, labels, colors, qspec))
            continue
        hs = q["horizons"]
        base = {(l, h): _at(pooled, (q["id"], l, None), h) for l in labels for h in hs}
        band = {h: _ensemble(base[(l, h)] for l in labels) for h in hs}
        out.append({**_meta(q), "category": q["group"], "valueKind": KIND,
                    "horizonLabels": {h: f"{h} ({q['horizon_meaning'][h]})" for h in hs},
                    "resolvesOn": {h: d for h, d in next((r["resolves_on"] for r in rows if r.get("resolves_on")),
                                                         {}).items() if h in hs},
                    "series": [{"label": l, "color": colors.get(l),
                                "ps": {h: _r(base[(l, h)]["p50"], 3) for h in hs if base[(l, h)]}} for l in labels],
                    "median": {h: band[h]["p50"] for h in hs if band[h]}, "band": band,
                    "ci": {}, "human": [], "declined": []})
    return {"title": "Forecasts by horizon", "railTitle": "Question",
            "runs": sorted({r["run_id"] for r in rows}),
            "latest": max((r["elicited_at"] for r in rows), default=None),
            "models": [{"label": l, "color": colors.get(l)} for l in labels],
            "categories": [{"key": g["key"], "label": g["key"], "group": g["key"],
                            "color": next(q["color"] for q in questions if q["group"] == g["key"])}
                           for g in qspec["groups"]],
            "questions": out if rows else []}


def _panels(rows, spec, qspec, colors, labels, proto, eci_history):
    """GRAPH1, CONDITIONAL and the capability variant from one day's `rows`:
    all five prompts' (their mean) or one prompt's."""
    questions = qspec["questions"]
    pct = [q for q in questions if _kind(q) == KIND]
    prob = [q for q in questions if _kind(q) == PROBABILITY]
    pooled = _pooled(_of(rows, pct))
    el = spec["elicit"]
    calls = defaultdict(dict)
    for r in rows:
        if (r.get("elicited") or {}).get(el["key"]):
            calls[r["label"]][r["call_id"]] = r["elicited"][el["key"]]
    eci = {l: {f: _r(st.mean(c[f] for c in calls[l].values()), 2) for f in el["fields"]} for l in labels if calls[l]}
    target = max(((r.get("elicited") or {}).get("target_date") for r in rows), default=None, key=lambda d: d or "")
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
                   "questions": _prob_cells(rows, spec, "policy", prob, colors)
                                + _cells(pct, pooled, labels, colors,
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
    # The probability rows' bars take the same labels and levels.
    prob_cap = _prob_cells(rows, spec, "capability", prob, colors)
    by_cond = {c["id"]: c for c in cap_conditions}
    for q in prob_cap:
        for cell in q["byHorizon"].values():
            for b in cell["bars"]:
                b.update(label=by_cond[b["id"]]["label"], leapId=by_cond[b["id"]]["leapId"])
    variant = {**common, "key": "6mo", "label": "6 months", "targetDate": target,
               "conditioning": cap["conditioning"], "conditions": cap_conditions,
               "questions": prob_cap + _cells(pct, pooled, labels, colors, cap_conditions),
               "forecast": {"models": [{"label": l, "color": colors.get(l), **eci[l],
                                        "n": len(calls[l])} for l in labels if l in eci],
                            "ensemble": {f: _median(eci[l][f] for l in eci) for f in el["fields"]},
                            "trend": capability._trend([target])["at"].get(target) if target else None}}
    graph1 = _graph1(questions, pooled, labels, colors, rows, qspec)
    capability_ = {**eci_history, "subject": "forecasts", "variants": [variant] if rows else [], "defaultVariant": "6mo"}
    return graph1, conditional, capability_


def _rationales(rows):
    """AIRO's rationale blob (views/rationales.build) for the welfare rows. Its
    prompt label comes from the variant; welfare's reworded two
    (welfare-independent, welfare-two-step) are AIRO's conditions, so they
    take AIRO's label for the condition (2026-10-27)."""
    out = rationales.build(rows=rows)
    for c in out["calls"].values():
        if c.get("condition") in ("independent", "two-step"):
            c["promptLabel"] = c["condition"].capitalize()
    return out


def build(log_path=None, set_path=None):
    """{blob name: blob} for welfare.html (web/welfare/manifest.json). GRAPH1,
    CONDITIONAL and CAPABILITY are the five prompts' mean, each with
    `byPrompt`: the same blob from one prompt's calls, which the page's
    prompt toggle shows."""
    spec = json.load(open(set_path or SET))
    qspec = json.load(open(REPO_ROOT / spec["questions"]))
    experiment = load_experiment(EXPERIMENT)
    all_rows, proto, days = _rows(log_path or LOG, spec, experiment)
    rows = [r for r in all_rows if days and _day(r) == days[-1]]
    colors = dict(model_colors())
    labels = [l for l, _ in model_colors() if l in {r["label"] for r in rows}]
    targets = sorted({(r.get("elicited") or {}).get("target_date") for r in rows} - {None})
    # The set's texts as the run's prompt filled them (run_unified.resolve_set).
    if targets:
        t = date.fromisoformat(targets[-1])
        spec = json.loads(json.dumps(spec).replace("{target_date}", f"{t:%B} {t.day}, {t.year}"))
    # AIRO's frontier ECI history, trend and LEAP's ECI forecast, beside the
    # welfare day's own forecast and conditions.
    aibo_cap = capability.build()
    eci_history = {"eci": aibo_cap["eci"], "leap": aibo_cap["leap"]}
    graph1, conditional, cap = _panels(rows, spec, qspec, colors, labels, proto, eci_history)
    for cid in experiment["pooled"]:
        one = _panels([r for r in rows if r["condition"] == cid], spec, qspec, colors, labels, proto, eci_history)
        one[1]["promptId"] = cid
        for v in one[2]["variants"]:
            v["promptId"] = cid
        for blob, part in zip((graph1, conditional, cap), one):
            blob.setdefault("byPrompt", {})[cid] = part
    # Each prompt's ensemble median on every row of the mean's charts, drawn
    # as a dot in the prompt's colour, as on the Timeline.
    for mean, per in ((conditional["questions"], {c: b["questions"] for c, b in conditional["byPrompt"].items()}),
                      *((v["questions"], {c: b["variants"][0]["questions"] for c, b in cap["byPrompt"].items()})
                        for v in cap["variants"])):
        # Percentile cells only: AIRO's probability rows draw no prompt dots.
        for q in mean:
            if q["valueKind"] != KIND:
                continue
            for h, cell in q["byHorizon"].items():
                cells = {c: next(x for x in qs if x["id"] == q["id"])["byHorizon"][h] for c, qs in per.items()}
                cell["baselinePrompts"] = [{"id": c, "p": x["baselineMedian"]} for c, x in cells.items()]
                for bar in cell["bars"]:
                    bar["prompts"] = [{"id": c, "p": next((y["pMedian"] for y in x["bars"] if y["id"] == bar["id"]), None)}
                                      for c, x in cells.items()]

    return {
        "TIMELINE": _timeline(qspec["questions"], all_rows, days, labels, colors, experiment, qspec),
        "GRAPH1": graph1,
        "CONDITIONAL": conditional,
        "CAPABILITY": cap,
        "METHOD": method.build(today=date.fromisoformat(days[-1]) if days else None,
                               experiment=EXPERIMENT, rows=rows),
        "RATIONALES": _rationales([r for r in all_rows if r.get("scenario") is None]),
        # The day shown and the five prompts each number is the mean of.
        "WELFARE": {"day": days[-1] if days else None, "protocol": proto,
                    "prompts": [{"condition": v["id"], "text": v["text"]} for v in condition_legend(
                        {c: experiment["conditions"][c]["variant"] for c in experiment["pooled"]}, EXPERIMENT)]},
    }
