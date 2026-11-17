"""LEAP: the instrument, a run against a made-up model (no calls), and the submission file."""
import json
from datetime import date
from types import SimpleNamespace

import pytest

from leap import build, instrument, run, validate_submission

TODAY = date(2026, 11, 13)
QUESTIONS = {
    "benchmark": "LEAP", "question_set": "recSET", "forecast_due_date": "2026-11-16",
    "questions": [
        {"id": "recA", "question_type": "forecast", "question": "Share of adults by {forecast_due_date}?",
         "background": "Some background.", "resolution_criteria": "Resolves to the published share.",
         "units": {"name": "percent", "display_text": "Percent (%)", "abbreviation": "%", "min": 0, "max": 100},
         "dimensions": ["China", "US "], "scenarios": [], "resolution_dates": ["2026-11-30", "2027-05-31"],
         "quantiles": ["p10", "p50", "p90"]},
        {"id": "recB", "question_type": "forecast", "question": "Shares choosing each option?", "background": None,
         "resolution_criteria": "Resolves to the poll.",
         "units": {"name": "percent", "display_text": "Percent (%)", "abbreviation": "%", "min": 0, "max": 100},
         "dimensions": ["Often", "Rarely"], "scenarios": [], "resolution_dates": ["2026-11-30"], "quantiles": []},
        {"id": "recC", "question_type": "probability", "question": "Chance of the outcome?", "background": None,
         "resolution_criteria": "Resolves YES if it happens.",
         "units": {"name": None, "display_text": None, "abbreviation": None, "min": None, "max": None},
         "dimensions": [], "scenarios": [None, {"name": "Rapid progress", "description": "AI moves fast.", "attributes": None}],
         "resolution_dates": [], "quantiles": []},
    ]}
MEMBERS = [{"key": "m-a", "label": "Model A", "model": "anthropic/m-a", "reasoning": "max"},
           {"key": "m-b", "label": "Model B", "model": "openai/m-b", "reasoning": "xhigh"}]


def answers(shift=0.0, drop=()):
    """A model's cells: every entry of every question, percentiles in order."""
    cells = {}
    for number, q in instrument.numbered(QUESTIONS).items():
        items = []
        for i, e in enumerate(instrument.entries(q)):
            if (number, e["entry"]) in drop:
                continue
            keys = instrument.value_keys(q)
            items.append({"entry": e["entry"], **{k: 10.0 + 10 * j + i + shift for j, k in enumerate(keys)}})
        cells[number] = {"question": number, "entries": items, "rationale": f"why {number}"}
    return cells


def fake_harness(by_model):
    def harness_run(**kw):
        return {"rc": 0, "cells": by_model[kw["model"]], "answer": {"key_sources": ["https://example.org"]},
                "usage": {"turns": 3, "cost_usd": 0.5}, "delivery": {},
                "evidence": [{"tool": "web_search", "args": {"query": "q"}, "result": {"results": [1, 2]}}]}
    return harness_run


def rows_for(by_model, monkeypatch, tmp_path):
    monkeypatch.setenv("LEAP_PI_DIR", str(tmp_path / "pi"))
    out = []
    for m in MEMBERS:
        out += run.ask(m, QUESTIONS, TODAY, "run-1", retries=0, harness_run=fake_harness(by_model))
    return out


def test_entries_follow_the_submission_order_and_count():
    a, b, c = QUESTIONS["questions"]
    assert [(e["entry"], e["dimension"], e["resolution_date"]) for e in instrument.entries(a)] == [
        ("e1", "China", "2026-11-30"), ("e2", "China", "2027-05-31"), ("e3", "US ", "2026-11-30"), ("e4", "US ", "2027-05-31")]
    assert [(e["scenario"], e["resolution_date"]) for e in instrument.entries(c)] == [(None, None), ("Rapid progress", None)]
    assert instrument.value_keys(a) == ["p10", "p50", "p90"] and instrument.value_keys(b) == ["forecast"]
    assert instrument.n_values(QUESTIONS) == 4 * 3 + 2 + 2


def test_the_prompt_is_the_question_sets_wording_and_names_every_entry():
    prompt, numbers = instrument.build_prompt(QUESTIONS, TODAY)
    assert numbers == ["q1", "q2", "q3"]
    assert "Today is 2026-11-13. Forecasts are due 2026-11-16." in prompt
    assert "Share of adults by 2026-11-16?" in prompt and "Some background." in prompt
    assert "- e3: US; resolution date 2026-11-30" in prompt
    assert "Unit: Percent (%), from 0 to 100." in prompt and "Unit: as the question states." in prompt
    assert "- Rapid progress: AI moves fast." in prompt and "an entry with no scenario is unconditional" in prompt
    assert "- e1: the question as asked" in prompt and "- e2: under the scenario 'Rapid progress'" in prompt
    assert "(16 numbers in all)" in prompt


def test_cleaning_keeps_an_entry_whole_or_not_at_all():
    a = QUESTIONS["questions"][0]
    raw = {"entries": [{"entry": "e1", "p10": 10, "p50": 20, "p90": 30},
                       {"entry": "e2", "p10": 30, "p50": 20, "p90": 40},      # out of order
                       {"entry": "e3", "p10": 10, "p50": 20, "p90": 130},     # outside the unit's range
                       {"entry": "e9", "p10": 1, "p50": 2, "p90": 3}],        # not an entry
           "rationale": " because "}
    values, rationale, problems = instrument.clean_cell(a, raw)
    assert values == {"e1": {"p10": 10.0, "p50": 20.0, "p90": 30.0}} and rationale == " because "
    assert [p.split(":")[0] for p in problems] == ["e2", "e3/p90", "e4"]
    assert instrument.clean_cell(a, None) == ({}, None, ["e1: missing", "e2: missing", "e3: missing", "e4: missing"])


def test_the_submission_is_the_mean_of_the_members_and_passes_the_validator(monkeypatch, tmp_path):
    rows = rows_for({"anthropic/m-a": answers(), "openai/m-b": answers(shift=4)}, monkeypatch, tmp_path)
    assert len(rows) == 6 and rows[0]["call"]["values"] == 16 and rows[1]["call"] is None
    assert rows[0]["question_id"] == "recA" and rows[0]["call"]["grounded"]
    built, short = build.submission(QUESTIONS, rows, organization="FRI", model="system-v1", model_organization="FRI")
    assert not short and len(built["forecasts"]) == 8
    first = built["forecasts"][0]
    assert first == {"id": "recA", "dimension": "China", "scenario": None, "resolution_date": "2026-11-30",
                     "p10": 12.0, "p50": 22.0, "p90": 32.0}
    assert built["forecasts"][2]["dimension"] == "US "          # the question set's string, exactly
    assert built["forecasts"][-1] == {"id": "recC", "dimension": None, "scenario": "Rapid progress",
                                      "resolution_date": None, "forecast": 13.0}
    assert validate_submission.validate(built, QUESTIONS) == ([], [])


def test_a_member_short_of_an_entry_stops_the_build(monkeypatch, tmp_path, capsys):
    rows = rows_for({"anthropic/m-a": answers(), "openai/m-b": answers(drop={("q2", "e2")})}, monkeypatch, tmp_path)
    runfile = tmp_path / "run-1.jsonl"
    runfile.write_text("".join(json.dumps(r) + "\n" for r in rows))
    questions = tmp_path / "recSET.json"
    questions.write_text(json.dumps(QUESTIONS))
    args = SimpleNamespace(questions=str(questions), run=str(runfile), model="system-v1", organization="FRI",
                           model_organization="FRI", out=str(tmp_path / "out"), allow_partial=False)
    with pytest.raises(SystemExit, match="1 entries lack a member"):
        build.main(args)
    assert "SHORT   recB e2: 1 of 2 members (Model A)" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()
    args.allow_partial = True
    assert build.main(args) == 0
    written = json.loads((tmp_path / "out/system-v1.recSET.json").read_text())
    assert written["forecasts"][5]["forecast"] == 11.0      # Model A alone


def test_a_call_with_missing_values_is_asked_again(monkeypatch, tmp_path):
    monkeypatch.setenv("LEAP_PI_DIR", str(tmp_path / "pi"))
    replies = [answers(drop={("q1", "e1")}), answers()]
    def harness_run(**kw):
        return {"rc": 0, "cells": replies.pop(0), "answer": {}, "usage": {"cost_usd": 1.0}, "evidence": []}
    rows = run.ask(MEMBERS[0], QUESTIONS, TODAY, "run-1", retries=1, harness_run=harness_run)
    assert rows[0]["call"]["attempts"] == 2 and rows[0]["call"]["values"] == 16 and rows[0]["call"]["cost_usd"] == 2.0
