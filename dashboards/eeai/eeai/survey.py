"""The question set (eeai/data/questions.json, from eeai/make_questions.py) and what it asks for."""
import csv
import json

from .config import HISTORY, QUESTIONS

UNCONDITIONAL = "unconditional"
PERCENTILES = ("p10", "p50", "p90")
# The survey's "uncertainty" tag: the 10th and 90th percentiles are asked for
# the unconditional forecast and the rapid scenario only.
UNCERTAINTY_SCENARIOS = (UNCONDITIONAL, "rapid")


def load(path=QUESTIONS):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def history(path=HISTORY):
    """{series: [(date, value)]}, oldest first."""
    out = {}
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["series"], []).append((r["date"], float(r["value"])))
    return out


def scenario_ids(survey):
    return [UNCONDITIONAL] + [s["id"] for s in survey["scenarios"]["items"]]


def percentiles(question, scenario):
    return PERCENTILES if question["uncertainty"] and scenario in UNCERTAINTY_SCENARIOS else ("p50",)


def horizons(question, today=None):
    """The question's dates; with `today` (a date), only those still ahead.
    A date is the beginning of its year, as the survey words it: once it has
    passed, the panel is no longer asked about it and its last forecast stands."""
    return [h for h in question["horizons"] if today is None or int(h["id"]) > today.year
            or (int(h["id"]) == today.year and (today.month, today.day) == (1, 1))]


def asked(survey, question, today=None):
    """Every value the question asks for, as (horizon, scenario, percentile)."""
    return [(h["id"], s, p) for h in horizons(question, today) for s in scenario_ids(survey)
            for p in percentiles(question, s)]


def n_values(survey, today=None):
    return sum(len(asked(survey, q, today)) for q in survey["questions"])


def instruments(survey):
    """The instrument and the earlier ones whose rows it continues."""
    return [survey["instrument"]] + list(survey.get("continues") or [])


def actual(series, horizon):
    """The record's value for a horizon: the point nearest the beginning of
    that year, within 45 days (the survey's series are dated that way), or None."""
    from datetime import date
    target = date(int(horizon), 1, 1)
    near = [(abs((date.fromisoformat(d) - target).days), d, v) for d, v in series or []]
    near = [x for x in near if x[0] <= 45]
    return min(near)[1:] if near else None
