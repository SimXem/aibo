"""redlines/views/axes.py: the scatter blob from the axes instrument's rows."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from redlines.views import axes  # noqa: E402
from redlines.instrument import CURRENT_INSTRUMENT

SPEC = json.load(open(REPO / "data" / "axes_conditions.json"))
MODELS = [("Fable 5", "anthropic/claude-fable-5"), ("GPT-5.5 Pro", "openai/gpt-5.5-pro")]


def _rows(day="2026-09-04", experiment=None):
    """Two models, every scenario of the set, catastrophe:ai at the three
    horizons: the conditional probability rises with the level index."""
    rows = []
    scenarios = [None] + SPEC["conditions"]
    for label, model in MODELS:
        base = 0.02 if label == "Fable 5" else 0.05
        elicited = {"revenue_forecast": {"p10": 120, "p50": 250, "p90": 600},
                    "agi_forecast": {"p_before_2100": 0.7, "p5": 2031, "p25": 2038, "p50": 2047, "p75": 2062, "p95": 2092},
                    "eci_forecast": {"p10": 166, "p25": 168, "p50": 171, "p75": 174, "p90": 178},
                    "target_date": "2027-03-04",
                    "targets": {"revenue_forecast": "2030-12-31", "agi_forecast": None, "eci_forecast": "2027-03-04"}}
        for c in scenarios:
            i = 0 if c is None else [x["id"] for x in SPEC["conditions"] if x["group"] == c["group"]].index(c["id"]) + 1
            p = min(0.9, base * (1 + 0.3 * i))
            rows.append({
                "instrument_version": CURRENT_INSTRUMENT,
                "run_id": f"{day}T1200Z", "elicited_at": f"{day}T12:30:00+00:00", "run_date": day,
                "question_id": "catastrophe:ai", "model": model, "label": label,
                "forecasts": [{"horizon": h, "probability": p} for h in ("2030", "2050", "2100")],
                "rationale": "", "key_sources": [], "grounded": True, "search_hits": 12,
                "evidence": [], "usage": None,
                "protocol": SPEC["protocol"], "condition_set": SPEC["slug"],
                "call_id": f"{day}T1200Z:joint#1:{label}", "attempts": 1, "batch_size": 35,
                "cause": None, "group": "crosscutting", "asked_horizons": ["2030", "2050", "2100"],
                "condition": None if c is None else {"id": c["id"], "leap_id": None, "label": c["label"],
                                                     "source": "x", "sha256": "0", "set": SPEC["slug"],
                                                     "group": c["group"], "value": c["value"]},
                "elicited": elicited, "experiment": experiment, "arm": "joint#1",
                "joint_conditions": ["unconditional"] + [x["id"] for x in SPEC["conditions"]],
            })
    return rows


class TestAxesView(unittest.TestCase):
    def _blob(self, rows):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "conditional_runs_axes.jsonl"
            log.write_text("".join(json.dumps(r) + "\n" for r in rows))
            return axes.build(log_path=log)

    def test_empty_log_still_describes_the_axes(self):
        with tempfile.TemporaryDirectory() as d:
            b = axes.build(log_path=Path(d) / "none.jsonl")
        self.assertEqual([a["key"] for a in b["axes"]], ["revenue", "agi", "eci"])
        self.assertEqual(b["questions"], [])
        self.assertIsNone(b["day"])
        rev = b["axes"][0]
        self.assertEqual([l["value"] for l in rev["levels"]], [75, 150, 300, 500, 830])
        self.assertEqual(rev["reference"]["panels"]["superforecaster"]["p50"], 300.0)
        self.assertEqual(rev["reference"]["shown"], "superforecaster")
        self.assertEqual(b["axes"][1]["reference"]["pBefore2100"]["superforecaster"], 0.8)
        self.assertEqual(b["axes"][2]["reference"]["kind"], "trend")

    def test_rows_become_levels_baselines_and_forecasts(self):
        b = self._blob(_rows())
        self.assertEqual(b["day"], "2026-09-04")
        self.assertEqual(b["protocol"], SPEC["protocol"])
        # The models with rows, in model_colors() order (the panel first, in
        # its colors; everyone else after, in the retired gray) -- whatever
        # the panel is on the newest ECI snapshot.
        from redlines.registry import model_colors
        want = [(l, c) for l, c in model_colors() if l in {"Fable 5", "GPT-5.5 Pro"}]
        self.assertEqual([(m["label"], m["color"]) for m in b["models"]], want)
        self.assertEqual([q["id"] for q in b["questions"]], ["catastrophe:ai"])
        eci = next(a for a in b["axes"] if a["key"] == "eci")
        self.assertEqual(eci["targetDate"], "2027-03-04")
        self.assertIn("2027-03-04", eci["xTitle"])
        self.assertEqual(eci["reference"]["at"], "2027-03-04")
        # The trend reference is whatever the tracked trend file says at the
        # target date (redlines.views.capability._trend), not a typed number
        # that goes stale the day the file is refreshed.
        from redlines.views.capability import _trend
        want = _trend(["2027-03-04"])
        self.assertAlmostEqual(eci["reference"]["p50"], want["at"]["2027-03-04"]["p50"], places=6)
        self.assertEqual(eci["reference"]["source"], want["source"])
        self.assertEqual(eci["reference"]["dataDate"], want["dataDate"])
        self.assertEqual(eci["forecast"]["ensemble"]["p50"], 171.0)
        self.assertEqual(eci["forecast"]["fields"], ["p10", "p25", "p50", "p75", "p90"])
        agi = next(a for a in b["axes"] if a["key"] == "agi")
        self.assertEqual(agi["forecast"]["ensemble"]["p_before_2100"], 0.7)
        q = eci["questions"][0]
        cell = q["byHorizon"]["2050"]
        self.assertEqual(cell["valueKind"], "probability")
        self.assertEqual([l["id"] for l in cell["levels"]], [c["id"] for c in SPEC["conditions"] if c["group"] == "eci"])
        first, last = cell["levels"][0], cell["levels"][-1]
        self.assertLess(first["median"], last["median"])          # rises with the level
        self.assertEqual(sorted(m["label"] for m in first["models"]), ["Fable 5", "GPT-5.5 Pro"])
        # Probabilities come out in PERCENT, the conditional summary's unit.
        self.assertAlmostEqual(next(m for m in first["models"] if m["label"] == "Fable 5")["p"], 2.6, places=3)
        self.assertEqual({b_["label"]: b_["p"] for b_ in cell["baselines"]}, {"Fable 5": 2.0, "GPT-5.5 Pro": 5.0})
        # An axis carries only its own scenarios.
        rev = next(a for a in b["axes"] if a["key"] == "revenue")
        self.assertEqual(len(rev["questions"][0]["byHorizon"]["2030"]["levels"]), 5)

    def test_experiment_rows_stay_out_unless_asked(self):
        rows = _rows(experiment="axes-smoke")
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "conditional_runs_axes.jsonl"
            log.write_text("".join(json.dumps(r) + "\n" for r in rows))
            self.assertEqual(axes.build(log_path=log)["questions"], [])
            self.assertEqual(len(axes.build(log_path=log, experiment="axes-smoke")["questions"]), 1)

    def test_newest_day_only(self):
        rows = _rows("2026-09-04") + _rows("2026-09-11")
        b = self._blob(rows)
        self.assertEqual(b["day"], "2026-09-11")
        self.assertEqual(b["generatedAt"], "2026-09-11T12:30:00+00:00")


if __name__ == "__main__":
    unittest.main()

    def test_cells_carry_the_leap_panel_unconditional_on_every_axis(self):
        """Every cell has a `humans` list, and on every axis the AI-catastrophe
        cell carries the LEAP superforecasters' unconditional (percent, like
        the models) when the baselines file has been pulled -- LEAP only, since
        it is the panel whose own forecast of the quantity places it on the x
        axis. The ECI axis got its human x on 2026-09-03: Wave 5's forecast of
        the top US system's ECI at end-2026, carried as `leap` beside the trend
        reference (the LEAP axes carry it as the reference itself)."""
        from redlines.questions import load_human_baselines
        from redlines.views import capability
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "axes.jsonl"
            log.write_text("\n".join(json.dumps(r) for r in _rows()) + "\n")
            b = axes.build(log_path=log)
        by_key = {a["key"]: a for a in b["axes"]}
        eci = by_key["eci"]
        self.assertEqual(eci["reference"]["kind"], "trend")
        self.assertEqual(eci["leap"]["kind"], "leap")
        self.assertEqual(eci["leap"]["at"], "2026-12-31")
        self.assertEqual(eci["leap"]["question"], "U.S. versus China Polarity")
        self.assertEqual(eci["leap"]["dimension"], "United States")
        sf = eci["leap"]["panels"]["superforecaster"]
        self.assertEqual((sf["n"], sf["p25"], sf["p50"], sf["p75"]), (55, 161.0, 169.0, 176.0))
        for k in ("revenue", "agi"):
            self.assertIsNone(by_key[k]["leap"])
        # The frontier chart's copy of the same forecast, every date.
        le = capability.build()["leap"]
        self.assertEqual(sorted(le["dates"]), ["2026-12-31", "2030-12-31", "2040-12-31"])
        self.assertEqual(le["dates"]["2030-12-31"]["superforecaster"]["p50"], 205.0)
        self.assertEqual(le["dates"]["2026-12-31"]["superforecaster"], sf)
        doc = load_human_baselines()
        for a in b["axes"]:
            for q in a["questions"]:
                for h in q["byHorizon"].values():
                    self.assertIsInstance(h["humans"], list)
            if doc["baselines"]:
                cell = a["questions"][0]["byHorizon"]["2030"]
                self.assertEqual({x["panel"] for x in cell["humans"]}, {"LEAP"})
                for x in cell["humans"]:
                    self.assertEqual(x["group"], "superforecaster")
                    self.assertGreater(x["p"], 0)
