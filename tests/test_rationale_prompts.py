"""Prompt labels must describe the archived call behind each explanation."""
import copy
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from redlines.experiments import DEFAULT_VARIANT, PUBLISHED, VARIANTS, load
from redlines.views import rationales


def call_rows(condition, variant, model="Example model"):
    """Two questions, with the prompt/debrief recorded only on the first row."""
    instruction = VARIANTS.get(variant)
    prompt = "Forecast these questions.\n" + (instruction or "")
    first = {
        "call_id": f"example:{model}:{condition}", "run_id": "example",
        "label": model, "model": model, "elicited_at": "2026-10-22T12:00:00Z",
        "question_id": "first", "condition": condition, "variant": variant,
        "prompt": prompt, "system_prompt": "Recorded system instruction.",
        "rationale": "Original batch rationale.",
        "key_sources": ["https://example.org/source"],
        "debrief": {"second": {"rationale": "Original question explanation."}},
    }
    second = {**first, "question_id": "second", "prompt": None,
              "system_prompt": None, "debrief": None}
    return [first, second]


def build_rows(rows, selected=None):
    """Isolate metadata from panel eligibility (covered by instrument tests)."""
    with ExitStack() as stack:
        stack.enter_context(patch.object(rationales, "load_runlog", return_value=rows))
        stack.enter_context(patch.object(rationales, "latest_instrument_rows",
                                        return_value=rows if selected is None else selected))
        for name in ("complete_panel_rows", "current_rows"):
            stack.enter_context(patch.object(rationales, name, side_effect=lambda value: value))
        return rationales.build()


class TestRationalePrompts(unittest.TestCase):
    def test_pooled_prompt_order_and_original_explanations(self):
        experiment = load(PUBLISHED)
        rows = []
        for condition in reversed(experiment["pooled"]):
            rows.extend(call_rows(condition, experiment["conditions"][condition]["variant"]))
        original = copy.deepcopy(rows)
        data = build_rows(rows + [rows[-1]])  # duplicate question must not repeat a call
        ids = data["questions"]["second"]["Example model"]
        self.assertEqual([data["calls"][cid]["condition"] for cid in ids], experiment["pooled"])
        self.assertEqual(data["conditionOrder"], experiment["pooled"])
        self.assertEqual(len(data["calls"]), len(experiment["pooled"]))
        for row in rows:
            call = data["calls"][row["call_id"]]
            self.assertEqual(call["rationale"], row["rationale"])
            self.assertEqual(call["sources"], row["key_sources"])
            self.assertEqual(call["debriefs"]["second"]["rationale"], "Original question explanation.")
            self.assertEqual(call["promptInstruction"], VARIANTS[row["variant"]])
            expected = "Baseline" if row["variant"] == DEFAULT_VARIANT else row["variant"].capitalize()
            self.assertEqual(call["promptLabel"], expected)
        self.assertEqual(rows, original)

    def test_recovers_first_row_prompt_for_later_question(self):
        rows = call_rows("independent", "independent")
        data = build_rows(rows, selected=[rows[1]])
        call = data["calls"][rows[1]["call_id"]]
        self.assertEqual(data["prompts"][call["promptId"]],
                         {"system": rows[0]["system_prompt"], "user": rows[0]["prompt"]})
        self.assertEqual(call["debriefs"], rows[0]["debrief"])

    def test_shares_identical_prompts_but_keeps_different_system_instructions(self):
        first = call_rows("independent", "independent", model="First model")
        second = call_rows("independent", "independent", model="Second model")
        data = build_rows(first + second)
        self.assertEqual(len(data["prompts"]), 1)
        second[0]["system_prompt"] = "A different system instruction."
        self.assertEqual(len(build_rows(first + second)["prompts"]), 2)

    def test_does_not_substitute_new_instruction_for_archived_wording(self):
        rows = call_rows("independent", "independent")
        with patch.dict(rationales.VARIANTS, {"independent": "A later instruction."}):
            data = build_rows(rows)
        call = data["calls"][rows[0]["call_id"]]
        self.assertIsNone(call["promptInstruction"])
        self.assertEqual(data["prompts"][call["promptId"]]["user"], rows[0]["prompt"])

    def test_missing_prompt_does_not_invent_full_text(self):
        rows = call_rows("independent", "independent")[1:]
        data = build_rows(rows)
        call = data["calls"][rows[0]["call_id"]]
        self.assertEqual(call["promptLabel"], "Independent")
        self.assertIsNone(call["promptInstruction"])
        self.assertIsNone(call["promptId"])
        self.assertEqual(data["prompts"], {})

    def test_missing_variant_uses_known_condition_but_never_guesses_baseline(self):
        for condition, expected in (("independent", "Independent"), ("none", "Baseline"),
                                    (None, "Unrecorded"), ({"id": "ai"}, "Unrecorded"),
                                    ("unrecognized", "Unrecorded")):
            with self.subTest(condition=condition):
                row = call_rows("example", None)[0]
                row["condition"] = condition
                data = build_rows([row])
                self.assertEqual(data["calls"][row["call_id"]]["promptLabel"], expected)

    def test_preserves_last_row_batch_rationale_behavior(self):
        rows = call_rows("none", DEFAULT_VARIANT)
        rows[-1]["rationale"] = "Last recorded batch rationale."
        rows[-1]["key_sources"] = ["https://example.org/last-source"]
        data = build_rows(rows)
        call = data["calls"][rows[0]["call_id"]]
        self.assertEqual(call["rationale"], rows[-1]["rationale"])
        self.assertEqual(call["sources"], rows[-1]["key_sources"])

    def test_forecasts_remain_separate_by_call_condition_and_question(self):
        baseline = call_rows("none", DEFAULT_VARIANT)
        baseline[0]["forecasts"] = [{"horizon": "2030", "probability": 0},
                                    {"horizon": "2100", "probability": 1}]
        baseline[1]["forecasts"] = [{"horizon": "2030", "probability": 0.2}]
        independent = call_rows("independent", "independent")
        independent[0]["forecasts"] = [{"horizon": "2030", "probability": 0.8}]
        repeat = copy.deepcopy(baseline[0])
        repeat["call_id"] += ":repeat"
        repeat["forecasts"] = [{"horizon": "2030", "probability": 0.6}]
        rows = baseline + independent + [repeat]
        original = copy.deepcopy(rows)
        data = build_rows(rows)
        self.assertEqual(data["calls"][baseline[0]["call_id"]]["forecasts"],
                         {"first": {"2030": 0, "2100": 1}, "second": {"2030": 0.2}})
        self.assertEqual(data["calls"][independent[0]["call_id"]]["forecasts"],
                         {"first": {"2030": 0.8}, "second": {}})
        self.assertEqual(data["calls"][repeat["call_id"]]["forecasts"],
                         {"first": {"2030": 0.6}})
        self.assertEqual(rows, original)
