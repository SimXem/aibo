"""The instrument: the survey as one prompt, the two answer tools, and the cleaning.

One call per model answers everything: the AI progress questions (the probability of each AI
scenario and three short items) and every economic question, unconditionally
and under each scenario, at every date still ahead (the survey's 2030 and
2050, and the nearer dates FRI added), with a rationale per question as the
survey asks.
The prompt is the survey's own wording (eeai/data/questions.json) and the
delivery mechanics; nothing advises the model how to forecast (the Baseline
condition, fri_forecaster.baseline). What a human respondent saw as a chart,
the model gets as the series.

Every answer is in the question's unit, percentages as numbers of percent.
"""
import math

from . import survey as S

DELIVERY = """Deliver the economic forecasts with submit_cells, in as many calls as you like:
any subset of the {n} questions per call, each with every value the question
asks for ({n_values} numbers in all) and its rationale; a later call for a question replaces
the earlier one. Then call submit_forecast ONCE, with your answers to the AI progress questions,
the sources you used, and any questions not yet delivered."""


def _percentile_words(ps):
    return {("p50",): "the 50th percentile", S.PERCENTILES: "the 10th, 50th and 90th percentiles"}[tuple(ps)]


def _asks(survey, q):
    """One line saying which values the question wants."""
    by = {}
    for s in S.scenario_ids(survey):
        by.setdefault(_percentile_words(S.percentiles(q, s)), []).append(s)
    parts = [f"{words} for {', '.join(scen)}" for words, scen in by.items()]
    return "Asked: " + "; ".join(parts) + "."


def _history_lines(series):
    if not series:
        return "none"
    return "\n".join(f"{d}: {v:g}" for d, v in series)


def build_prompt(survey, history, today):
    """-> (prompt, question ids)."""
    sc = survey["scenarios"]
    qs = survey["questions"]
    out = [f"Today is {today.isoformat()}.", "",
           f"Below are {len(survey['part1'])} questions about AI progress and {len(qs)} forecasting questions "
           "about the U.S. economy, each asked at several dates, unconditionally and under three scenarios "
           "for AI progress. "
           "Answer all of them.", "",
           "===== AI SCENARIOS =====", "", sc["preamble"], ""]
    for s in sc["items"]:
        out += [f"--- {s['id']}: {s['label']} ---"]
        out += [f"{i['name']}: {i['text']}" for i in s["indicators"]]
        out += [""]
    if sc.get("footnote"):
        out += [f"Note on Level-5 autonomy: {sc['footnote']}", ""]

    out += ["===== AI PROGRESS =====", ""]
    for p in survey["part1"]:
        out += [f"--- {p['id']} ({p['title']}) ---", p["text"]]
        if p.get("details"):
            out += ["", p["details"]]
        if p["kind"] in ("probabilities", "allocation"):
            out += ["", f"Answer: one number of percent for each of {', '.join(p['fields'])}, summing to {p['sum']}."]
        else:
            out += ["", "Answer: a probability in percent, 0 to 100."]
        out += [""]

    ins = survey["instructions"]
    out += ["===== ECONOMIC OUTCOMES =====", "", ins["percentiles"], "", ins["conditional"], "",
            "Scenario ids: " + ", ".join(S.scenario_ids(survey)) + ". "
            "Give every value in the question's unit; a percentage is a number of percent (4.2 for 4.2%), "
            "not a fraction.", "",
            f"Rationale, for each question: {ins['rationale']}", ""]
    category = None
    for q in qs:
        if q["category"] != category:
            category = q["category"]
            out += [f"== {category} ==", ""]
        out += [f"--- {q['id']} ({q['title']}) ---"]
        if q.get("preamble"):
            out += [q["preamble"], ""]
        out += [q["stem"]] + [f"- {h['id']}: {h['text']}" for h in S.horizons(q, today)]
        out += [f"Unit: {q['unit']}. {_asks(survey, q)}", "", q["details"], "",
                "Historical data (the survey's chart):", _history_lines(history.get(q["history"])), ""]
    out += ["=====", "", DELIVERY.format(n=len(qs), n_values=S.n_values(survey, today))]
    return "\n".join(out), [q["id"] for q in qs]


# ── the answer tools ─────────────────────────────────────────────────────────

def cell_schema(survey):
    """One question's answer: {question_id, forecasts: {horizon: {scenario:
    {p10?, p50, p90?}}}, rationale}. The same shape for every question; which
    horizons and percentiles a question wants is in the prompt, and checked
    in clean_cell."""
    value = {"type": "object",
             "properties": {p: {"type": "number"} for p in S.PERCENTILES},
             "required": ["p50"]}
    scenarios = {"type": "object", "properties": {s: value for s in S.scenario_ids(survey)},
                 "required": S.scenario_ids(survey)}
    horizons = sorted({h["id"] for q in survey["questions"] for h in q["horizons"]})
    return {"type": "object",
            "properties": {
                "question_id": {"type": "string", "enum": [q["id"] for q in survey["questions"]]},
                "forecasts": {"type": "object",
                              "description": "by horizon id, then scenario id, then percentile (p10, p50, p90)",
                              "properties": {h: scenarios for h in horizons}},
                "rationale": {"type": "string"}},
            "required": ["question_id", "forecasts", "rationale"]}


def _part1_schema(p):
    if p["kind"] in ("probabilities", "allocation"):
        return {"type": "object", "description": f"percent for each field, summing to {p['sum']}",
                "properties": {f: {"type": "number", "minimum": 0, "maximum": 100} for f in p["fields"]},
                "required": list(p["fields"])}
    return {"type": "number", "minimum": 0, "maximum": 100, "description": "a probability in percent"}


def tools(survey):
    """-> (submit_cells, submit_forecast), each {description, parameters}."""
    cells = {"type": "array", "items": cell_schema(survey)}
    submit_cells = {
        "description": "Deliver economic forecasts in pieces: any subset of the questions, each with every "
                       "value it asks for and its rationale. Call it as often as you like; a later call "
                       "for a question replaces the earlier one. Returns how many questions have been "
                       "received and which are still missing.",
        "parameters": {"type": "object", "properties": {"forecasts": cells}, "required": ["forecasts"]}}
    part1 = {p["id"]: _part1_schema(p) for p in survey["part1"]}
    submit_forecast = {
        "description": "Submit your final answer: the AI progress answers, a short rationale for them, the key "
                       "sources you read, and any questions not yet delivered with submit_cells.",
        "parameters": {"type": "object",
                       "properties": {**part1, "rationale": {"type": "string"},
                                      "key_sources": {"type": "array", "items": {"type": "string"}},
                                      "forecasts": cells},
                       "required": [*part1, "rationale"]}}
    return submit_cells, submit_forecast


# ── cleaning ─────────────────────────────────────────────────────────────────

def _number(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def clean_cell(survey, question, raw, today=None):
    """A question's raw answer -> (forecasts, rationale, problems). Keeps
    exactly the values asked for (at `today`: the dates still ahead); a value that is missing, not a number,
    outside the question's bounds, or out of order (p10 <= p50 <= p90) is
    left out and named in `problems`, never repaired."""
    problems, out = [], {}
    given = raw.get("forecasts") if isinstance(raw, dict) else None
    given = given if isinstance(given, dict) else {}
    lo, hi = question["bounds"]
    for h in S.horizons(question, today):
        for s in S.scenario_ids(survey):
            cell = (given.get(h["id"]) or {}).get(s) if isinstance(given.get(h["id"]), dict) else None
            cell = cell if isinstance(cell, dict) else {}
            vals = {}
            for p in S.percentiles(question, s):
                v = _number(cell.get(p))
                if v is None:
                    problems.append(f"{h['id']}/{s}/{p}: missing")
                elif not lo <= v <= hi:
                    problems.append(f"{h['id']}/{s}/{p}: {v:g} is outside [{lo:g}, {hi:g}]")
                else:
                    vals[p] = v
            order = [vals[p] for p in S.PERCENTILES if p in vals]
            if order != sorted(order):
                problems.append(f"{h['id']}/{s}: percentiles out of order {order}")
                vals = {}
            if vals:
                out.setdefault(h["id"], {})[s] = vals
    rationale = raw.get("rationale") if isinstance(raw, dict) else None
    return out, rationale if isinstance(rationale, str) and rationale.strip() else None, problems


def clean_part1(survey, answer):
    """-> (part1, problems). A set of percentages that should sum to 100 is
    kept as given when it is within one point of it, and refused otherwise."""
    out, problems = {}, []
    for p in survey["part1"]:
        raw = (answer or {}).get(p["id"])
        if p["kind"] in ("probabilities", "allocation"):
            vals = {f: _number((raw or {}).get(f)) if isinstance(raw, dict) else None for f in p["fields"]}
            if any(v is None or not 0 <= v <= 100 for v in vals.values()):
                problems.append(f"{p['id']}: missing or out of range")
            elif abs(sum(vals.values()) - p["sum"]) > 1:
                problems.append(f"{p['id']}: sums to {sum(vals.values()):g}, not {p['sum']}")
            else:
                out[p["id"]] = vals
        else:
            v = _number(raw)
            if v is None or not 0 <= v <= 100:
                problems.append(f"{p['id']}: missing or out of range")
            else:
                out[p["id"]] = v
    return out, problems
