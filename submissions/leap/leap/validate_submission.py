#!/usr/bin/env python3
"""Check a LEAP submission file against the question set it answers.

    python validate_submission.py submission.json question_set.json

Prints every problem found and ends with a one-line verdict. Exit status is 1 when
the submission has errors (it would be rejected), 0 otherwise. Warnings do not fail
the check but are worth a look. Needs Python 3.9 or later and nothing else.

This file is sent out next to every question set and must stay standard-library
only, so teams can run it as is.
"""

import json
import math
import sys
from collections import defaultdict

HEADER_FIELDS = ("organization", "model", "model_organization", "benchmark", "question_set", "forecasts")
ENTRY_KEYS = ("id", "dimension", "scenario", "resolution_date")


def validate(submission, question_set):
    """(errors, warnings) for a submission dict against a question set dict."""
    errors, warnings = [], []
    if not isinstance(submission, dict):
        return ["the submission is not a JSON object"], warnings
    for field in HEADER_FIELDS:
        if field not in submission:
            errors.append(f"missing top-level field {field!r}")
    if errors:
        return errors, warnings
    for field in HEADER_FIELDS[:-1]:
        if not isinstance(submission[field], str) or not submission[field].strip():
            errors.append(f"top-level field {field!r} must be a non-empty string")
    if submission["benchmark"] != question_set["benchmark"]:
        errors.append(f"benchmark is {submission['benchmark']!r}, the question set's is {question_set['benchmark']!r}")
    if submission["question_set"] != question_set["question_set"]:
        errors.append(
            f"question_set is {submission['question_set']!r}, the question set's is {question_set['question_set']!r}"
        )
    if not isinstance(submission["forecasts"], list):
        errors.append("'forecasts' must be a list")
        return errors, warnings

    questions = {q["id"]: q for q in question_set["questions"]}
    seen = defaultdict(dict)  # id -> (dimension, scenario, date) -> {quantile: value}
    for position, entry in enumerate(submission["forecasts"]):
        where = f"forecasts[{position}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: not a JSON object")
            continue
        missing = [k for k in ENTRY_KEYS if k not in entry]
        if missing:
            errors.append(f"{where}: missing {', '.join(repr(k) for k in missing)}")
            continue
        question = questions.get(entry["id"])
        if question is None:
            errors.append(f"{where}: id {entry['id']!r} is not in the question set")
            continue
        where = f"{where} (id {entry['id']})"
        point = _check_axes(entry, question, where, errors)
        if point is None:
            continue
        if point in seen[entry["id"]]:
            errors.append(f"{where}: duplicate entry for dimension={point[0]!r}, scenario={point[1]!r}, resolution_date={point[2]!r}")
            continue
        seen[entry["id"]][point] = _check_values(entry, question, where, errors, warnings)
        if "rationale" in entry and entry["rationale"] is not None and not isinstance(entry["rationale"], str):
            errors.append(f"{where}: 'rationale' must be a string or null")

    _check_coverage(questions, seen, warnings)
    return errors, warnings


def _check_axes(entry, question, where, errors):
    """The entry's (dimension, scenario, resolution_date), or None after reporting errors."""
    ok = True
    axes = {
        "dimension": question["dimensions"] or [None],
        "scenario": [s["name"] if isinstance(s, dict) else s for s in question["scenarios"]] or [None],
        "resolution_date": question["resolution_dates"] or [None],
    }
    for key, allowed in axes.items():
        if entry[key] not in allowed:
            errors.append(f"{where}: {key}={entry[key]!r} is not one of {allowed}")
            ok = False
    return (entry["dimension"], entry["scenario"], entry["resolution_date"]) if ok else None


def _check_values(entry, question, where, errors, warnings):
    """Check the value keys of one entry; returns {quantile or 'forecast': value}."""
    quantiles = question["quantiles"]
    expected = set(quantiles) if quantiles else {"forecast"}
    present = {k for k in entry if k.startswith("p") and k[1:].replace(".", "", 1).isdigit()} | ({"forecast"} if "forecast" in entry else set())
    if present != expected:
        errors.append(f"{where}: value keys are {sorted(present)}, expected {sorted(expected)}")
    values = {}
    for key in present & expected:
        value = entry[key]
        if value is None:
            warnings.append(f"{where}: {key} is null (no forecast)")
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            errors.append(f"{where}: {key}={value!r} is not a finite number")
            continue
        values[key] = value
        low, high = question["units"]["min"], question["units"]["max"]
        if (low is not None and value < low) or (high is not None and value > high):
            warnings.append(f"{where}: {key}={value} is outside the unit range [{low}, {high}]")
    if quantiles:
        ordered = [values[q] for q in quantiles if q in values]
        if any(a > b for a, b in zip(ordered, ordered[1:])):
            warnings.append(f"{where}: quantiles decrease with the percentile: {ordered}")
    return values


def _check_coverage(questions, seen, warnings):
    missing_entries = 0
    for qid, question in questions.items():
        dims = question["dimensions"] or [None]
        scenarios = [s["name"] if isinstance(s, dict) else s for s in question["scenarios"]] or [None]
        dates = question["resolution_dates"] or [None]
        expected = {(d, s, r) for d in dims for s in scenarios for r in dates}
        missing = expected - set(seen.get(qid, {}))
        if missing:
            missing_entries += len(missing)
            if len(missing) == len(expected):
                warnings.append(f"id {qid}: no entries at all ({len(expected)} expected)")
            else:
                warnings.append(f"id {qid}: {len(missing)} of {len(expected)} entries missing, e.g. dimension={missing and sorted(missing, key=str)[0]}")
    if missing_entries:
        warnings.append(f"{missing_entries} entries missing in total; every combination should be present (use null for no forecast)")


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    try:
        with open(argv[1], encoding="utf-8") as f:
            submission = json.load(f)
        with open(argv[2], encoding="utf-8") as f:
            question_set = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"ERROR   could not read the files: {exc}")
        return 1
    errors, warnings = validate(submission, question_set)
    for line in errors:
        print(f"ERROR   {line}")
    for line in warnings:
        print(f"WARNING {line}")
    if errors:
        print(f"\nNOT OK: {len(errors)} errors, {len(warnings)} warnings. Fix the errors before submitting.")
        return 1
    if warnings:
        print(f"\nOK with {len(warnings)} warnings: the file can be submitted, but check the warnings.")
    else:
        print("\nOK: all is good.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
