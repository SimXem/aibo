"""The shared panel (top k by ECI, one seat per family) and the Baseline condition."""
import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from fri_forecaster import baseline, eci, panel


def _snapshot(tmp, day, rows):
    """A rank-format snapshot: rows are (model, eci)."""
    p = Path(tmp) / f"{eci.SNAPSHOT_PREFIX}{day}.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "model", "eci", "ci_low", "ci_high", "retrieved"])
        for i, (m, e) in enumerate(rows, 1):
            w.writerow([i, m, e, e - 3, e + 3, day])
    return date.fromisoformat(day), p


class TestRule(unittest.TestCase):
    TABLE = [{"epoch_name": "A 2", "family": "a"}, {"epoch_name": "A 1", "family": "a"},
             {"epoch_name": "B 1", "family": "b"}, {"epoch_name": "C 1", "family": "c"}]

    def _ranked(self, rows):
        return [{"model": m, "eci": e, "rank": i} for i, (m, e) in enumerate(rows, 1)]

    def test_top_k_one_seat_per_family_and_what_it_says(self):
        ranked = self._ranked([("A 2", 170), ("X 9", 169), ("A 1", 168), ("B 1", 160), ("C 1", 150)])
        members, warnings = panel.select(ranked, self.TABLE, 2, "snap.csv")
        self.assertEqual([m["epoch_name"] for m, _ in members], ["A 2", "B 1"])
        self.assertTrue(any("passed over A 1 (168)" in w and "A 2" in w for w in warnings), warnings)
        self.assertTrue(any("X 9" in w and "cannot run" in w for w in warnings), warnings)

    def test_a_tie_at_the_cut_and_a_short_panel(self):
        ranked = self._ranked([("B 1", 160), ("C 1", 160)])
        members, warnings = panel.select(ranked, self.TABLE, 1, "snap.csv")
        self.assertEqual(members[0][0]["epoch_name"], "B 1")
        self.assertTrue(any(w.startswith("tie at the cut") and "C 1" in w for w in warnings), warnings)
        _, warnings = panel.select(ranked, self.TABLE, 4, "snap.csv", stale="old")
        self.assertEqual(warnings[0], "old")
        self.assertTrue(any("only 2 of the top 4 in snap.csv" in w and "panel is short" in w for w in warnings))

    def test_a_new_run_refuses_a_top_model_it_holds_a_key_for_and_cannot_run(self):
        # X 9 ranks second, has no row, and its lab's key is held: no other model stands in for it.
        ranked = self._ranked([("A 2", 170), ("X 9", 169), ("B 1", 160)])
        ranked[1]["organization"] = "Google DeepMind"
        with self.assertRaises(panel.PanelError) as e:
            panel.require(ranked, self.TABLE, 2, "snap.csv", held=lambda provider: True)
        self.assertIn("X 9", str(e.exception))
        self.assertIn("GEMINI_API_KEY is set", str(e.exception))
        # Without that key X 9 is not in the ensemble at all: left out, and the run goes ahead.
        omitted = panel.require(ranked, self.TABLE, 2, "snap.csv", held=lambda provider: provider != "google")
        self.assertEqual(len(omitted), 1)
        self.assertIn("X 9 is left out of the ensemble: no API key for its lab (GEMINI_API_KEY)", omitted[0])
        # So is a model from a lab no key can be held for.
        ranked[1]["organization"] = "Moonshot"
        self.assertIn("Moonshot", panel.require(ranked, self.TABLE, 2, held=lambda provider: True)[0])

    def test_what_does_not_stop_a_new_run(self):
        held = lambda provider: True   # noqa: E731
        # A short panel is refused; a family pass-over or a tie is the rule working.
        self.assertRaises(panel.PanelError, panel.require, self._ranked([("B 1", 160)]), self.TABLE, 2, "snap.csv", held)
        ranked = self._ranked([("A 2", 170), ("A 1", 168), ("B 1", 160), ("C 1", 160)])
        self.assertTrue(panel.select(ranked, self.TABLE, 2)[1])
        self.assertEqual(panel.require(ranked, self.TABLE, 2, held=held), [])
        # An unrunnable model BELOW the cut costs nothing.
        ranked = self._ranked([("A 2", 170), ("B 1", 160), ("X 9", 150)])
        ranked[2]["organization"] = "OpenAI"
        self.assertEqual(panel.require(ranked, self.TABLE, 2, held=held), [])

    def test_gemini_goes_to_pi_under_its_own_provider_name(self):
        self.assertEqual(panel.pi_model("gemini/gemini-4-carbon"), "google/gemini-4-carbon")
        self.assertEqual(panel.pi_model("openai/responses/gpt-6-astra"), "openai/gpt-6-astra")
        self.assertEqual(panel.pi_model("anthropic/claude-fable-5-2"), "anthropic/claude-fable-5-2")

    def test_rows_come_back_as_given(self):
        table = [dict(r, color="#123456") for r in self.TABLE]
        members, _ = panel.select(self._ranked([("C 1", 150)]), table, 1)
        self.assertEqual(members[0][0]["color"], "#123456")


class TestPanel(unittest.TestCase):
    def test_table_is_well_formed(self):
        keys = [m["key"] for m in panel.MODELS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len({m["epoch_name"] for m in panel.MODELS}), len(panel.MODELS))
        for m in panel.MODELS:
            self.assertTrue(all(m[f] for f in panel._FIELDS), m)
            self.assertIn("/", m["model"])

    def test_panel_from_a_snapshot_directory_with_an_automatic_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = _snapshot(tmp, "2026-11-01", [("Nova 9", 180), ("Claude Opus 5.5", 167), ("Claude Opus 5", 163),
                                                 ("GPT-6 Astra", 166), ("Claude Fable 5.1", 164)])
            members, prov = panel.panel(3, snapshot=snap, snapshot_dir=tmp, warn=False)
            self.assertEqual([m["key"] for m in members], ["claude-opus-5-5", "gpt-6-astra", "claude-fable-5-1"])
            self.assertTrue(any("Nova 9" in w for w in prov["warnings"]))
            # A box's automatic row (AIRO's autoreg spells `model` litellm_id) makes Nova runnable.
            (Path(tmp) / panel.AUTO_MODELS).write_text(json.dumps([
                {"key": "nova-9", "family": "nova", "label": "Nova 9", "litellm_id": "openai/responses/nova-9",
                 "epoch_name": "Nova 9", "color": "#000000"},
                {"key": "claude-opus-5-5", "family": "x", "label": "x", "litellm_id": "x/x", "epoch_name": "Claude Opus 5.5"}]))
            members, prov = panel.panel(3, snapshot=snap, snapshot_dir=tmp, warn=False)
            self.assertEqual([m["key"] for m in members], ["nova-9", "claude-opus-5-5", "gpt-6-astra"])
            self.assertEqual(members[0]["pi_model"], "openai/nova-9")
            self.assertEqual(members[0]["reasoning"], "xhigh")
            self.assertEqual(members[1]["family"], "claude-opus")     # the hand row wins
            self.assertEqual(prov["snapshot"], "2026-11-01")
            self.assertEqual([m["label"] for m in prov["members"]], ["Nova 9", "Opus 5.5", "GPT-6 Astra"])

    def test_ids_and_reasoning(self):
        self.assertEqual(panel.pi_model("openai/responses/gpt-6-astra"), "openai/gpt-6-astra")
        self.assertEqual(panel.pi_model("anthropic/claude-opus-5-5"), "anthropic/claude-opus-5-5")
        self.assertEqual(panel.reasoning_for("anthropic/claude-opus-5-5"), "max")
        self.assertEqual(panel.reasoning_for("gemini/gemini-3.1-pro-preview"), "high")


class TestBaseline(unittest.TestCase):
    def test_research_is_offered_plainly(self):
        search, read = baseline.research_tools()
        self.assertEqual((search["name"], read["name"]), ("web_search", "read_page"))
        self.assertEqual(search["description"], baseline.WEB_SEARCH)
        self.assertNotIn("cause", search["parameters"]["properties"])
        self.assertEqual(search["parameters"]["required"], ["query"])

    def test_run_is_the_minimal_loop(self):
        seen = {}

        def fake(**kw):
            seen.update(kw)
            return {"cells": {}}
        tool = {"description": "d", "parameters": {"type": "object"}}
        with tempfile.TemporaryDirectory() as tmp:
            baseline.run("openai/responses/gpt-6-astra", "P", workdir=tmp, cell_schema={"type": "object"},
                         key_fields=["question_id"], allowed_keys=["a"], submit_cells=tool, submit_forecast=tool,
                         cwd=tmp, harness_run=fake)
        self.assertEqual(seen["model"], "openai/gpt-6-astra")
        self.assertEqual(seen["system"], " ")
        self.assertEqual(seen["thinking"], "xhigh")
        self.assertEqual(seen["research_tools"], ("web_search", "read_page"))
        self.assertEqual({k: seen[k] for k in baseline.LOOP},
                         {"min_research": 0, "floor_counts": "returned", "withhold_final": True,
                          "warn_missing_keys": False, "max_turns": 100})
        self.assertEqual(set(seen["tool_parameters"]), {"web_search", "read_page", "submit_cells", "submit_forecast"})


if __name__ == "__main__":
    unittest.main()
