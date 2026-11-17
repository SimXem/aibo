"""The instrument: a LEAP question set as one prompt, the two answer tools, and the cleaning.

One call per model answers the whole question set. The prompt is the question
set's own wording (question, background, resolution criteria, unit) and the
delivery mechanics; nothing advises the model how to forecast (the Baseline
condition, fri_forecaster.baseline).

A question's entries are numbered e1, e2, ... in the order the submission
lists them, and the model answers by those numbers: the dimension and scenario
names go into the file from the question set, never from what a model typed.
"""
import math


def scenario_name(scenario):
    return scenario["name"] if isinstance(scenario, dict) else scenario


def value_keys(question):
    """What one entry carries: the question's percentiles, or one `forecast`."""
    return list(question["quantiles"]) or ["forecast"]


def entries(question):
    """The question's entries, in submission order: one per dimension x
    scenario x resolution date, an unused axis counting as one null."""
    out = []
    for dimension in question["dimensions"] or [None]:
        for scenario in [scenario_name(s) for s in question["scenarios"]] or [None]:
            for resolution_date in question["resolution_dates"] or [None]:
                out.append({"entry": f"e{len(out) + 1}", "dimension": dimension, "scenario": scenario,
                            "resolution_date": resolution_date})
    return out


def numbered(question_set):
    """{"q1": question, ...} in the question set's order."""
    return {f"q{i}": q for i, q in enumerate(question_set["questions"], 1)}


def n_values(question_set):
    return sum(len(entries(q)) * len(value_keys(q)) for q in question_set["questions"])


def _unit(question):
    u = question["units"]
    if not u.get("display_text") and not u.get("name"):
        return "as the question states"
    text = u.get("display_text") or u["name"]
    lo, hi = u.get("min"), u.get("max")
    if lo is not None and hi is not None:
        return f"{text}, from {lo:g} to {hi:g}"
    if lo is not None:
        return f"{text}, at least {lo:g}"
    if hi is not None:
        return f"{text}, at most {hi:g}"
    return text


def _asks(question):
    if question["quantiles"]:
        return "For each entry: " + ", ".join(question["quantiles"]) + " (those percentiles of your distribution)."
    if question["question_type"] == "probability":
        return "For each entry: forecast (the probability)."
    return "For each entry: forecast (your point estimate)."


def _entry_line(e):
    parts = []
    if e["dimension"] is not None:
        parts.append(e["dimension"].strip())
    if e["scenario"] is not None:
        parts.append(f"under the scenario {e['scenario'].strip()!r}")
    if e["resolution_date"] is not None:
        parts.append(f"resolution date {e['resolution_date']}")
    return f"- {e['entry']}: " + ("; ".join(parts) if parts else "the question as asked")


DELIVERY = """Deliver the forecasts with submit_cells, in as many calls as you like: any subset of
the {n} questions per call, each with every entry's values ({n_values} numbers in all) and a
short rationale; a later call for a question replaces the earlier one. Then call
submit_forecast ONCE, with the sources you used and any questions not yet delivered."""


def build_prompt(question_set, today):
    """-> (prompt, question numbers)."""
    qs = numbered(question_set)
    due = question_set.get("forecast_due_date")
    out = [f"Today is {today.isoformat()}." + (f" Forecasts are due {due}." if due else ""), "",
           f"Below are {len(qs)} forecasting questions. Each asks for a number at one or more entries: the "
           "question at one dimension, scenario and resolution date. Answer every entry of every question.", "",
           "Where a question asks for percentiles (p10, p50, p90 and the like), give those percentiles of your "
           "probability distribution for the quantity. Where it asks for a forecast, give one number. Give "
           "every value in the question's unit; a percentage is a number of percent (42 for 42%), not a "
           "fraction.", ""]
    for number, q in qs.items():
        text = q["question"]
        if due:
            text = text.replace("{forecast_due_date}", due)
        out += [f"===== {number} =====", "", text.strip(), ""]
        if q.get("background"):
            out += ["Background:", q["background"].strip(), ""]
        if q.get("resolution_criteria"):
            out += ["Resolution criteria:", q["resolution_criteria"].strip(), ""]
        described = [s for s in q["scenarios"] if isinstance(s, dict)]
        if q["scenarios"]:
            out += ["Scenarios (a forecast under a scenario assumes it holds" +
                    ("; an entry with no scenario is unconditional" if None in q["scenarios"] else "") + "):"]
            out += [f"- {s['name'].strip()}: " + " ".join(str(s[k]).strip() for k in ("description", "attributes") if s.get(k))
                    for s in described]
            out += [""]
        out += [f"Unit: {_unit(q)}.", _asks(q), "Entries:"] + [_entry_line(e) for e in entries(q)] + [""]
    out += ["=====", "", DELIVERY.format(n=len(qs), n_values=n_values(question_set))]
    return "\n".join(out), list(qs)


# ── the answer tools ─────────────────────────────────────────────────────────

def cell_schema(question_set):
    """One question's answer: {question, entries: [{entry, <value keys>}],
    rationale}. The same shape for every question; which entries and values a
    question wants is in the prompt, and checked in clean_cell."""
    keys = sorted({k for q in question_set["questions"] for k in value_keys(q)})
    entry = {"type": "object",
             "properties": {"entry": {"type": "string", "description": "the entry's number, e.g. e1"},
                            **{k: {"type": "number"} for k in keys}},
             "required": ["entry"]}
    return {"type": "object",
            "properties": {"question": {"type": "string", "enum": list(numbered(question_set))},
                           "entries": {"type": "array", "items": entry},
                           "rationale": {"type": "string"}},
            "required": ["question", "entries", "rationale"]}


def tools(question_set):
    """-> (submit_cells, submit_forecast), each {description, parameters}."""
    cells = {"type": "array", "items": cell_schema(question_set)}
    submit_cells = {
        "description": "Deliver forecasts in pieces: any subset of the questions, each with every entry's "
                       "values and a short rationale. Call it as often as you like; a later call for a "
                       "question replaces the earlier one. Returns how many questions have been received "
                       "and which are still missing.",
        "parameters": {"type": "object", "properties": {"forecasts": cells}, "required": ["forecasts"]}}
    submit_forecast = {
        "description": "Submit your final answer: the key sources you read, and any questions not yet "
                       "delivered with submit_cells.",
        "parameters": {"type": "object",
                       "properties": {"key_sources": {"type": "array", "items": {"type": "string"}},
                                      "forecasts": cells},
                       "required": []}}
    return submit_cells, submit_forecast


# ── cleaning ─────────────────────────────────────────────────────────────────

def _number(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def clean_cell(question, raw):
    """A question's raw answer -> (values, rationale, problems), `values` being
    {entry number: {value key: number}}. An entry is kept whole or not at all:
    one whose value is missing, not a number, outside the unit's range, or
    whose percentiles decrease is left out and named in `problems`, never
    repaired."""
    problems, out = [], {}
    given = raw.get("entries") if isinstance(raw, dict) else None
    by_entry = {}
    for item in given if isinstance(given, list) else []:
        if isinstance(item, dict) and isinstance(item.get("entry"), str):
            by_entry[item["entry"].strip()] = item      # a later one replaces an earlier one
    lo, hi = question["units"].get("min"), question["units"].get("max")
    keys = value_keys(question)
    for e in entries(question):
        item, vals, bad = by_entry.get(e["entry"]), {}, False
        if item is None:
            problems.append(f"{e['entry']}: missing")
            continue
        for k in keys:
            v = _number(item.get(k))
            if v is None:
                problems.append(f"{e['entry']}/{k}: missing")
                bad = True
            elif (lo is not None and v < lo) or (hi is not None and v > hi):
                problems.append(f"{e['entry']}/{k}: {v:g} is outside [{lo}, {hi}]")
                bad = True
            else:
                vals[k] = v
        ordered = [vals[k] for k in keys if k in vals]
        if len(keys) > 1 and ordered != sorted(ordered):
            problems.append(f"{e['entry']}: percentiles decrease {ordered}")
            bad = True
        if not bad:
            out[e["entry"]] = vals
    rationale = raw.get("rationale") if isinstance(raw, dict) else None
    return out, rationale if isinstance(rationale, str) and rationale.strip() else None, problems
