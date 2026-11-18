"""The acceleration experiments, two independent prompts:
experiments/acceleration.toml (data/acceleration_conditions.json):
catastrophe:ai alone, at every horizon, under 12 self-sustaining
acceleration conditions, asked through run_unified as the published series
is; experiments/acceleration-elicit.toml (data/acceleration_elicit.json):
the probability of each condition, asked alone through code/run_elicit.py
(run_cellwise's ECI step). No model is called."""
import importlib.util
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ru = _load("run_unified", REPO / "code" / "run_unified.py")
sys.path.insert(0, str(REPO / "code"))
import run_cellwise as rc  # noqa: E402
import run_elicit as rel  # noqa: E402
mk = _load("make_acceleration_conditions", REPO / "code" / "make_acceleration_conditions.py")
from redlines import experiments  # noqa: E402

EXP = experiments.load("acceleration")
EXP_ELICIT = experiments.load("acceleration-elicit")
SET = REPO / "data" / "acceleration_conditions.json"
ELICIT_SET = REPO / "data" / "acceleration_elicit.json"
TODAY = date(2026, 11, 18)


def _prompt():
    pol = ru.load_policies(str(SET))
    g, b, h, _, spec = ru.set_questions(pol)
    h = ru.set_horizons(pol, h)
    prompt, n, cells = ru.build_prompt_joint(g, b, h, spec, pol["conditions"], pol, TODAY)
    return pol, (g, b, h, spec), ru.condition_prompt(prompt, EXP["conditions"]["recent"]), n, cells


class TestTheSet(unittest.TestCase):
    def test_the_file_is_what_the_generator_writes(self):
        r = subprocess.run([sys.executable, "code/make_acceleration_conditions.py", "--check"],
                           cwd=REPO, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_three_kinds_at_four_dates(self):
        pol = ru.load_policies(str(SET))
        ids = [c["id"] for c in pol["conditions"]]
        self.assertEqual(ids, [f"{k}_{y}" for k in ("sw", "econ", "none") for y in (2027, 2028, 2030, 2040)])
        self.assertEqual([g["key"] for g in ru.set_groups(pol)], ["software", "economic", "none"])

    def test_the_definitions_are_the_agreed_ones_verbatim_and_shared(self):
        d = ru.load_policies(str(SET))["conditioning"]["definitions"]
        self.assertIn(mk.SW_DEF, d)
        self.assertIn(mk.EC_DEF, d)
        self.assertEqual(ru.load_policies(str(ELICIT_SET))["conditioning"]["definitions"], d)

    def test_the_catastrophe_set_elicits_nothing_and_the_elicit_set_conditions_nothing(self):
        self.assertEqual(ru.set_elicits(ru.load_policies(str(SET))), [])
        e = ru.load_policies(str(ELICIT_SET))
        self.assertEqual(e["conditions"], [])
        self.assertEqual([x["key"] for x in ru.set_elicits(e)], ["p_software_only", "p_with_economic_feedback"])


class TestTheExperiments(unittest.TestCase):
    def test_two_models_five_calls_unpublished(self):
        for exp, unit in ((EXP, "joint"), (EXP_ELICIT, "elicit")):
            c = exp["conditions"]["recent"]
            self.assertEqual((c["repeats"], c["model_set"], c["publish"], c["cadence"], c["unit"]),
                             (5, "cellcheck", False, "manual", unit))
            self.assertEqual(len(experiments.MODEL_SETS[c["model_set"]]()), 2)
            self.assertEqual((c["instrument"], c["harness"], c["variant"]), ("minimal", "pi", "recent"))

    def test_each_runner_refuses_the_others_unit(self):
        for runner, exp, why in (("run_unified.py", "acceleration-elicit", "run them with code/run_elicit.py"),
                                 ("run_cellwise.py", "acceleration-elicit", "code/run_elicit.py"),
                                 ("run_elicit.py", "acceleration", "not elicitation conditions")):
            r = subprocess.run([sys.executable, f"code/{runner}", "--experiment", exp, "--dry-run"],
                               cwd=REPO, capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0, runner)
            self.assertIn(why, r.stdout + r.stderr, runner)

    def test_an_elicit_condition_must_be_unpublished_and_hand_run(self):
        import tempfile
        f = Path(tempfile.mkdtemp()) / "elicit_check.toml"
        f.write_text('scenarios = "data/acceleration_elicit.json"\nunit = "elicit"\ninstrument = "minimal"\n'
                     'publish = true\n[conditions.a]\n')
        try:
            with self.assertRaisesRegex(ValueError, 'unit "elicit" requires'):
                experiments.load(str(f))
        finally:
            f.unlink()


class TestThePrompt(unittest.TestCase):
    def test_one_question_six_horizons_thirteen_conditions(self):
        _, (g, b, h, _), prompt, n, cells = _prompt()
        self.assertEqual([q["id"] for qs in b.values() for q in qs], ["catastrophe:ai"])
        self.assertEqual(h, ["6mo", "12mo", "2028", "2030", "2050", "2100"])
        self.assertEqual((n, cells), (1, 6))
        self.assertIn("Below is one question. Answer it\n-- and answer every", prompt)
        self.assertIn("(78 probabilities, keyed by condition id)", prompt)

    def test_the_question_is_the_published_one(self):
        g, b, h, _, spec = ru.load_batch(ru.LADDER, ru.CROSS, ru.UNBATCHED)
        q = next(q for qs in b.values() for q in qs if q["id"] == "catastrophe:ai")
        _, _, prompt, _, _ = _prompt()
        self.assertIn(q["text"], prompt)
        self.assertIn(q["criteria"], prompt)

    def test_the_catastrophe_prompt_asks_no_probability_of_acceleration(self):
        _, _, prompt, _, _ = _prompt()
        for gone in ("Step 1", "p_software_only", "p_with_economic_feedback"):
            self.assertNotIn(gone, prompt)
        self.assertIn("Each question x horizon cell takes 13 probabilities", prompt)
        self.assertIn("Then call submit_forecast ONCE,\nwith a short rationale", prompt)
        self.assertIn(ru.VARIANTS["recent"], prompt)

    def test_the_elicitation_prompt_asks_only_the_two_probabilities(self):
        pol = ru.resolve_set(ru.load_policies(str(ELICIT_SET)), TODAY)
        p = rc.eci_prompt(pol, TODAY, "recent")
        self.assertTrue(p.startswith("Today is 2026-11-18.\n\nDefinitions."))
        self.assertIn("p_software_only (by_2027, by_2028, by_2030, by_2040", p)
        self.assertIn("p_with_economic_feedback (by_2027", p)
        self.assertIn(ru.VARIANTS["recent"], p)
        self.assertIn("Call submit_forecast ONCE, with your p_software_only (4 numbers) and "
                      "p_with_economic_feedback (4 numbers)", p)
        for gone in ("catastrophe", "--- sw_", "Horizon"):
            self.assertNotIn(gone, p)

    def test_published_prompts_are_untouched(self):
        # The singular head and the three-group list apply to this set alone.
        pol = ru.load_policies(ru.COMBINED)
        g, b, h, _, spec = ru.load_batch(ru.LADDER, ru.CROSS, ru.UNBATCHED)
        p, _, _ = ru.build_prompt_joint(g, b, ru.set_horizons(pol, h), spec, pol["conditions"], pol, TODAY)
        m = ru.minimal_joint_prompt(p)
        self.assertIn("(policy conditions and capability conditions)", p)
        self.assertNotIn("Below is one question", m)
        self.assertEqual(ru.set_questions(pol)[1], b)


class TestElicitCleaning(unittest.TestCase):
    def setUp(self):
        self.es = {e["key"]: e for e in ru.set_elicits(ru.load_policies(str(ELICIT_SET)))}

    def test_software_only_must_not_fall_with_the_date(self):
        e = self.es["p_software_only"]
        self.assertIsNotNone(ru.clean_elicit({"by_2027": .01, "by_2028": .02, "by_2030": .05, "by_2040": .2}, e))
        self.assertIsNone(ru.clean_elicit({"by_2027": .05, "by_2028": .02, "by_2030": .05, "by_2040": .2}, e))
        self.assertIsNone(ru.clean_elicit({"by_2027": .01, "by_2028": .02, "by_2030": .05, "by_2040": 1.2}, e))

    def test_economic_feedback_must_not_fall_with_the_date_either(self):
        e = self.es["p_with_economic_feedback"]
        self.assertIsNotNone(ru.clean_elicit({"by_2027": .05, "by_2028": .08, "by_2030": .12, "by_2040": .3}, e))
        self.assertIsNone(ru.clean_elicit({"by_2027": .1, "by_2028": .08, "by_2030": .12, "by_2040": .3}, e))

    def test_both_prompts_exclude_software_only_in_the_same_words(self):
        e = ru.load_policies(str(ELICIT_SET))
        text = next(x["text"] for x in ru.set_elicits(e) if x["key"] == "p_with_economic_feedback")
        self.assertIn(f"and that {mk.NOT_BEFORE}.", text)
        for c in ru.load_policies(str(SET))["conditions"]:
            if c["group"] == "economic":
                self.assertTrue(c["assume"].endswith(f"and that {mk.NOT_BEFORE}."), c["id"])
        self.assertNotIn("conditional on", text)


class TestOneElicitationCall(unittest.TestCase):
    """run_elicit.run_one through a fake loop: what the loop is given, and the row."""

    def test_row(self):
        pol = ru.resolve_set(ru.load_policies(str(ELICIT_SET)), TODAY)
        c = EXP_ELICIT["conditions"]["recent"]
        seen = {}

        def fake(model, prompt, tools, final_tool, **kw):
            seen.update(prompt=prompt, tools=[t["name"] for t in tools], final_tool=final_tool, **kw)
            return {"rationale": "r",
                    "p_software_only": {"by_2027": .01, "by_2028": .03, "by_2030": .08, "by_2040": .25},
                    "p_with_economic_feedback": {"by_2027": .03, "by_2028": .04, "by_2030": .1, "by_2040": .3}}, []

        orig = rc.call_tools
        rc.call_tools = fake
        try:
            ctx = rel.context(EXP_ELICIT, pol, TODAY, "2026-11-18T0000Z", {"cellcheck": {"set": "cellcheck"}})
            row = rel.run_one(ctx, "M", "anthropic/x", c, 0, 2)
        finally:
            rc.call_tools = orig
        self.assertEqual(seen["prompt"], rc.eci_prompt(pol, TODAY, "recent"))
        self.assertEqual(seen["system"], ru.MINIMAL_SYSTEM)
        self.assertIn("web_search", seen["tools"])
        self.assertEqual(seen["final_tool"]["parameters"]["required"][:2],
                         ["p_software_only", "p_with_economic_feedback"])
        self.assertEqual((row["unit"], row["step"], row["protocol"], row["replicate"]),
                         ("elicit", "elicit", "elicit:elicit-acceleration-v1", 2))
        self.assertEqual(row["call_id"], "2026-11-18T0000Z:acceleration-elicit:elicit:M:recent#2")
        self.assertEqual(row["elicited"]["p_with_economic_feedback"]["by_2028"], .04)
        self.assertEqual(row["experiment"], "acceleration-elicit")


class TestOneCatastropheCall(unittest.TestCase):
    """run_one_joint through a fake loop: what the rows hold."""

    def test_rows(self):
        pol, (g, b, h, spec), _, _, _ = _prompt()
        ids = [c["id"] for c in pol["conditions"]]
        seen = {}

        def fake(model, prompt, tools, final_tool, **kw):
            seen.update(prompt=prompt, final_tool=final_tool)
            return {"forecasts": [{"question_id": "catastrophe:ai", "horizon": hz,
                                   "probabilities": {k: 0.01 for k in ["unconditional"] + ids}} for hz in h],
                    "rationale": "r"}, []

        orig = ru.call_tools
        ru.call_tools = fake
        try:
            rows = ru.run_one_joint("M", "anthropic/x", g, b, h, "2026-11-18T0000Z", 0, spec,
                                    pol["conditions"], pol, EXP["conditions"]["recent"], "acceleration",
                                    arm="joint#1", today=TODAY)
        finally:
            ru.call_tools = orig
        self.assertEqual(len(rows), 13)
        self.assertEqual({r["scenario_set"] for r in rows}, {"acceleration"})
        self.assertEqual({r["protocol"] for r in rows}, {"unified-joint-acceleration-v1"})
        self.assertIsNone(rows[0]["elicited"])
        self.assertEqual({r["scenario"]["group"] for r in rows[1:]}, {"software", "economic", "none"})
        self.assertEqual(seen["final_tool"]["parameters"]["required"], ["rationale"])


if __name__ == "__main__":
    unittest.main()
