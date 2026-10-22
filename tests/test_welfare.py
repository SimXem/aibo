"""The welfare instrument (2026-10-22): AIRO's pipeline asked of the welfare
questions (data/welfare_questions.json) under the combined set's conditions
and five prompts, each cell five percentiles, drawn on welfare.html
(redlines/views/welfare.py, web/welfare/). Fixtures only: no model is called."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _runner():
    spec = importlib.util.spec_from_file_location("run_unified", REPO / "code" / "run_unified.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ru = _runner()
from redlines import experiments, runlog  # noqa: E402
from redlines.pages import hydrate_page  # noqa: E402
from redlines.views import welfare  # noqa: E402

TODAY = date(2026, 10, 22)
WELFARE = experiments.load("welfare")
SET = os.path.join(ru.ROOT, "data", "welfare_conditions.json")
# The keys the welfare set owns; every other key is the combined set's.
OWN = {"title", "slug", "protocol", "questions", "copied_from"}
LABELS = ("GPT-6 Astra", "Opus 5.5")          # two registry models


def _batch():
    pol = ru.load_policies(SET)
    g, b, h, _, spec = ru.load_questions(pol["questions"])
    return pol, g, b, ru.set_horizons(pol, h), spec


def _prompt(condition="none"):
    pol, g, b, h, spec = _batch()
    p = ru.build_prompt_joint(g, b, h, spec, pol["conditions"], pol, TODAY)[0]
    return ru.condition_prompt(p, WELFARE["conditions"][condition])


def _base(qid):
    return 80.0 if qid.startswith("le:") else 2.0


def _value(qid, cid, label, condition):
    """A call's p50 for one cell: the question's base, a step per condition
    id, a step per model, and a step per prompt (so the pool has a mean)."""
    ids = ["unconditional"] + [c["id"] for c in ru.load_policies(SET)["conditions"]]
    return (_base(qid) + 0.01 * ids.index(cid) + LABELS.index(label)
            + 0.1 * WELFARE["pooled"].index(condition))


def _calls(conditions=None, labels=LABELS, today=TODAY):
    """Rows of one call per (model, condition), through run_one_joint and a
    fake loop that answers every cell with five percentiles around _value."""
    pol, g, b, h, spec = _batch()
    rp = ru.resolve_set(pol, today)
    ids = ["unconditional"] + [c["id"] for c in rp["conditions"]]
    rows = []
    for label in labels:
        for cid in conditions or WELFARE["pooled"]:
            def fake(model, prompt, tools, final_tool, usage=None, partial_tool=None, **kw):
                cells = [{"question_id": q["id"], "horizon": hz,
                          "percentiles": {k: {p: _value(q["id"], k, label, cid) + d
                                              for p, d in zip(ru.PERCENTILE_FIELDS, (-2, -1, 0, 1, 2))}
                                          for k in ids}}
                         for gg in g for q in b[gg["key"]] for hz in h if hz in q["horizons"]]
                partial_tool["fn"](forecasts=cells[:3])           # some cells in pieces
                usage.update(turns=10, cost_usd=1.5)
                return {"forecasts": cells[3:], "rationale": f"{label} {cid}", "key_sources": [],
                        "eci_forecast": {"p10": 168 + LABELS.index(label), "p25": 170, "p50": 172,
                                         "p75": 175, "p90": 178 + WELFARE["pooled"].index(cid)}}, []
            orig = ru.loop_for
            ru.loop_for = lambda harness: fake
            try:
                rows += ru.run_one_joint(label, "x/" + label, g, b, h, f"{today}T0000Z", 0, spec,
                                         pol["conditions"], pol, WELFARE["conditions"][cid], "welfare",
                                         arm="joint#1", panel={"set": "eci_topk", "k": 4}, today=today)
            finally:
                ru.loop_for = orig
    return rows


def _log(rows):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for r in rows:
        f.write(json.dumps(r) + "\n")
    f.close()
    return f.name


class TestTheCopy(unittest.TestCase):
    def test_the_welfare_set_is_the_combined_set(self):
        """Its conditions, groups, elicit and every other shared key are the
        combined set's: a change to one that the copy misses fails here."""
        w, c = json.load(open(SET)), ru.load_policies(ru.COMBINED)
        self.assertEqual(set(w) - OWN, set(c) - OWN)
        for k in set(c) - OWN:
            self.assertEqual(w[k], c[k], k)
        self.assertEqual((w["slug"], w["questions"]), ("welfare", "data/welfare_questions.json"))

    def test_the_experiment_is_five_manual_prompts_on_the_welfare_set(self):
        self.assertEqual(list(WELFARE["conditions"]), WELFARE["pooled"])
        self.assertEqual(WELFARE["pooled"], ["none", "independent", "recent", "critical", "two-step"])
        for c in WELFARE["conditions"].values():
            self.assertEqual((c["scenarios"], c["instrument"], c["harness"], c["publish"], c["cadence"]),
                             ("data/welfare_conditions.json", "minimal", "pi", True, "manual"))
        self.assertEqual({c["variant"] for c in WELFARE["conditions"].values()},
                         {"none", "welfare-independent", "recent", "critical", "welfare-two-step"})
        self.assertIn(("welfare", True, WELFARE["pooled"]), experiments.due(named=["welfare"]))
        self.assertNotIn("welfare", {e for e, _, _ in experiments.due(date(2026, 10, 28))})   # a Wednesday


class TestPrompt(unittest.TestCase):
    def test_the_questions_render_without_a_severity_and_with_units_and_meanings(self):
        p = _prompt()
        self.assertTrue(p.startswith(f"Today is {TODAY}.\n\nBelow are 5 questions. Answer\nall of them"))
        self.assertNotIn("(severity:", p)
        self.assertIn("--- le:us ---\nWhat will the period life expectancy at birth in the U.S.", p)
        self.assertIn("Horizons for this question: 2050 (the year 2050), 2100 (the year 2100)\n"
                      "Answer in years of life expectancy at birth.\n", p)
        self.assertIn("Horizons for this question: 2030 (the five-year period 2026 through 2030), "
                      "2050 (the five-year period 2046 through 2050)\nAnswer in percent per year", p)
        self.assertIn("Horizons: 2030, 2050, 2100. Each question names the ones it is asked over "
                      "and what each means for it -- answer", p)

    def test_step_2_and_delivery_ask_five_percentiles(self):
        p = _prompt()
        self.assertIn("Step 2 -- each question x horizon cell takes five percentiles (p10, p25, p50, p75, "
                      "p90) under each of 14 conditions, keyed by the condition ids below: unconditional", p)
        self.assertIn("Deliver the percentiles with submit_cells", p)
        self.assertIn("the 14 conditions (700 numbers, keyed by condition id)", p)
        self.assertIn("with your eci_forecast (5 numbers) and a short rationale, the sources you used, "
                      "and any cells not yet delivered.", p)
        self.assertNotIn("probabilit", p[p.index("===== CONDITIONS"):].replace(
            "other probabilities given by prominent figures", ""))

    def test_each_variant_lands_before_the_delivery_paragraph(self):
        base = _prompt("none")
        for cid, c in WELFARE["conditions"].items():
            text = ru.VARIANTS[c["variant"]]
            p = _prompt(cid)
            if not text:
                self.assertEqual(p, base)
                continue
            self.assertEqual(p.replace(text + "\n\n", "", 1), base)
            self.assertLess(p.index(text), p.index("Deliver the percentiles"))
            self.assertTrue(p[:p.index("Deliver the percentiles")].endswith(text + "\n\n"))

    def test_the_tools_ask_five_numbers_per_condition(self):
        pol, g, b, h, spec = _batch()
        ids = [c["id"] for c in pol["conditions"]]
        tool = ru.submit_cells_tool([q["id"] for gg in g for q in b[gg["key"]]], h, ids, ru.value_mode(spec))
        cell = tool["parameters"]["properties"]["forecasts"]["items"]
        self.assertEqual(cell["required"], ["question_id", "horizon", "percentiles"])
        per = cell["properties"]["percentiles"]
        self.assertEqual(per["required"], ["unconditional"] + ids)
        self.assertEqual(per["properties"]["sq"]["required"], ["p10", "p25", "p50", "p75", "p90"])
        self.assertIn("with five percentiles under every condition id", tool["description"])
        self.assertEqual(spec["percentiles"], list(ru.PERCENTILE_FIELDS))


class TestPercentileCleaning(unittest.TestCase):
    BOUNDS = {"le:us": [0, 150], "gdp:ae": [-100, 100]}
    GOOD = {"p10": 78, "p25": 80.5, "p50": "82", "p75": 83, "p90": 86}

    def _clean(self, cells):
        return ru.clean_forecasts_joint(cells, {"le:us": {"2050", "2100"}, "gdp:ae": {"2030"}},
                                        ["2030", "2050", "2100"], ["sq"], ru.PERCENTILES, self.BOUNDS)

    def test_a_good_cell_is_kept_as_percentiles(self):
        g = self._clean([{"question_id": "le:us", "horizon": "2050",
                          "percentiles": {"unconditional": self.GOOD, "sq": dict(self.GOOD, p90=86)}}])
        want = {"p10": 78.0, "p25": 80.5, "p50": 82.0, "p75": 83.0, "p90": 86.0}
        self.assertEqual(g, {"unconditional": {"le:us": [{"horizon": "2050", "percentiles": want}]},
                             "sq": {"le:us": [{"horizon": "2050", "percentiles": want}]}})
        # A stringified cell is parsed, as a probability cell is.
        g = self._clean([{"question_id": "gdp:ae", "horizon": "2030",
                          "percentiles": json.dumps({"unconditional": {"p10": -1, "p25": 1, "p50": 2,
                                                                       "p75": 2.5, "p90": 4}})}])
        self.assertEqual(g["unconditional"]["gdp:ae"][0]["percentiles"]["p10"], -1.0)

    def test_missing_unordered_out_of_bounds_and_nan_cells_are_dropped(self):
        bad = {"missing": {"p10": 78, "p25": 80, "p50": 82, "p90": 86},
               "unordered": {"p10": 78, "p25": 84, "p50": 82, "p75": 83, "p90": 86},
               "out": dict(self.GOOD, p90=151),
               "nan": dict(self.GOOD, p50=float("nan")),
               "inf": dict(self.GOOD, p90=float("inf")),
               "bool": dict(self.GOOD, p10=True),
               "scalar": 0.5}
        for why, v in bad.items():
            g = self._clean([{"question_id": "le:us", "horizon": "2050",
                              "percentiles": {"unconditional": v, "sq": self.GOOD}}])
            self.assertNotIn("unconditional", g, why)
            self.assertIn("sq", g, why)                       # the other condition stays
        self.assertIsNone(self._clean([{"question_id": "gdp:ae", "horizon": "2030",
                                        "percentiles": {"unconditional": {"p10": -150, "p25": 1, "p50": 2,
                                                                          "p75": 3, "p90": 4}}}]))
        # Outside the question's horizons, or a probability cell: nothing.
        self.assertIsNone(self._clean([{"question_id": "le:us", "horizon": "2030",
                                        "percentiles": {"unconditional": self.GOOD}}]))
        self.assertIsNone(self._clean([{"question_id": "le:us", "horizon": "2050",
                                        "probabilities": {"unconditional": 0.1}}]))


class TestProbabilityModeUnchanged(unittest.TestCase):
    def test_cleaning_schema_and_pooling_default_to_one_probability(self):
        g = ru.clean_forecasts_joint([{"question_id": "q", "horizon": "2030",
                                       "probabilities": {"unconditional": 0.1, "sq": 1}}],
                                     {"q": {"2030"}}, ["2030"], ["sq"])
        self.assertEqual(g, {"unconditional": {"q": [{"horizon": "2030", "probability": 0.1}]},
                             "sq": {"q": [{"horizon": "2030", "probability": 1}]}})
        cell = ru._cells_schema(["q"], ["2030"], ["sq"])["items"]
        self.assertEqual(cell["required"], ["question_id", "horizon", "probabilities"])
        self.assertEqual(cell["properties"]["probabilities"]["properties"]["sq"],
                         {"type": "number", "minimum": 0, "maximum": 1})
        rows = [{"forecasts": [{"horizon": "2030", "probability": p}], "elicited_at": str(i), "arm": None}
                for i, p in enumerate((0.1, 0.2, 0.6))]
        self.assertAlmostEqual(runlog.pool(rows)["forecasts"][0]["probability"], 0.3)
        self.assertEqual(runlog.pool(rows[:1])["forecasts"], [{"horizon": "2030", "probability": 0.1}])

    def test_airos_prompt_asks_probabilities(self):
        pol = ru.resolve_set(ru.load_policies(ru.COMBINED), TODAY)
        g, b, h, _, spec = ru.load_batch(ru.LADDER, ru.CROSS, ru.UNBATCHED)
        p = ru.build_prompt_joint(g, b, ru.set_horizons(pol, h), spec, pol["conditions"], pol, TODAY)[0]
        self.assertEqual(ru.value_mode(spec), ru.PROBABILITY)
        self.assertIn("Step 2 -- each question x horizon cell takes 14 probabilities, keyed by the condition ids", p)
        self.assertIn("each cell with a\nprobability in [0,1] under each of the 14 conditions\n", p)
        self.assertIn("Each question names the ones it is asked over -- answer\nthose and no others.", p)
        self.assertIn("(severity: ", p)
        m = ru.minimal_joint_prompt(p, "two-step")
        self.assertTrue(m[:m.index("Deliver the probabilities")].endswith(ru.VARIANTS["two-step"] + "\n\n"))


class TestRows(unittest.TestCase):
    def test_a_call_writes_percentile_forecasts_for_every_question_and_condition(self):
        rows = _calls(["two-step"], LABELS[:1])
        self.assertEqual(len(rows), 5 * 14)
        self.assertEqual({r["scenario_set"] for r in rows}, {"welfare"})
        self.assertEqual({r["protocol"] for r in rows}, {"welfare-joint-v1"})
        self.assertEqual({r["instrument_version"] for r in rows}, {"airo-welfare-v1"})
        self.assertEqual({r["variant"] for r in rows}, {"welfare-two-step"})
        self.assertEqual(rows[0]["delivery"], {"cells_calls": 1, "cells_in_pieces": 3, "cells_in_final": 7})
        le = next(r for r in rows if r["question_id"] == "le:us" and r["scenario"] is None)
        self.assertEqual([f["horizon"] for f in le["forecasts"]], ["2050", "2100"])
        self.assertEqual(set(le["forecasts"][0]), {"horizon", "percentiles"})
        self.assertEqual(le["forecasts"][0]["percentiles"]["p50"], _value("le:us", "unconditional", LABELS[0], "two-step"))
        eci = next(r for r in rows if (r["scenario"] or {}).get("id") == "eci_p90")
        self.assertEqual(eci["scenario"]["value"], 182)          # the call's own p90

    def test_airos_forecasts_csv_passes_over_percentile_cells(self):
        """The export reads every conditional_runs_* log, the welfare one too."""
        from redlines import export
        rows = [r for r in _calls(["none"], LABELS[:1]) if r["scenario"]]
        self.assertEqual(list(export._lines(rows, {})), [])
        self.assertEqual(len(list(export._rationale_lines(rows, {}))), len(rows))


class TestView(unittest.TestCase):
    def test_it_pools_five_calls_per_model(self):
        blob = welfare.build(log_path=_log(_calls()))
        self.assertEqual(blob["day"], TODAY.isoformat())
        self.assertEqual([m["label"] for m in blob["models"]], list(LABELS))
        self.assertEqual(blob["rows"], 2 * 5 * 5 * 14)
        self.assertEqual([p["condition"] for p in blob["prompts"]], WELFARE["pooled"])
        self.assertEqual(blob["prompts"][4]["text"], experiments.VARIANTS["welfare-two-step"])
        prompt_step = sum(0.1 * i for i in range(5)) / 5
        q = next(q for q in blob["questions"] if q["id"] == "gdp:ae")
        self.assertEqual(q["horizons"], ["2030", "2050"])
        cell = q["byHorizon"]["2030"]
        for i, label in enumerate(LABELS):
            base = next(b for b in cell["baselines"] if b["label"] == label)["q"]
            mid = 2.0 + i + prompt_step
            self.assertEqual(base, {p: round(mid + d, 3) for p, d in zip(ru.PERCENTILE_FIELDS, (-2, -1, 0, 1, 2))})
            bar = next(b for b in cell["bars"] if b["id"] == "p3a")
            m = next(m for m in bar["models"] if m["label"] == label)
            self.assertAlmostEqual(m["q"]["p50"], mid + 0.01 * 5, places=3)       # p3a is the 5th condition
            self.assertAlmostEqual(m["shift"], 0.05, places=3)
        self.assertEqual(blob["eciForecast"]["Opus 5.5"], {"p10": 169, "p25": 170, "p50": 172, "p75": 175, "p90": 180})
        p90 = next(c for c in blob["conditions"] if c["id"] == "eci_p90")
        self.assertEqual((p90["label"], p90["leapId"], p90["levels"]),
                         ("Own 90th percentile", "ECI ≈ 180", {"GPT-6 Astra": 180, "Opus 5.5": 180}))
        self.assertNotIn("{target_date}", json.dumps(blob))
        self.assertEqual(blob["usage"]["Opus 5.5"], {"turns": 50, "cost_usd": 7.5})
        self.assertEqual(len(blob["rationales"]["questions"]["le:us"]["Opus 5.5"]), 5)

    def test_an_incomplete_day_gives_way_to_the_last_complete_one_and_none_is_empty(self):
        old = _calls(today=date(2026, 10, 21))
        new = _calls(WELFARE["pooled"][:4], today=TODAY)          # a prompt short
        self.assertEqual(welfare.build(log_path=_log(old + new))["day"], "2026-10-21")
        self.assertIsNone(welfare.build(log_path=_log(new)))
        self.assertIsNone(welfare.build(log_path=os.path.join(tempfile.mkdtemp(), "none.jsonl")))


class TestPage(unittest.TestCase):
    def test_the_page_assembles_from_the_shared_chunks_and_the_pilots(self):
        d = REPO / "web" / "welfare"
        manifest = json.loads((d / "manifest.json").read_text())
        self.assertEqual((manifest["target"], manifest["blobs"]), ("welfare.html", ["WELFARE", "CAPABILITY"]))
        self.assertNotIn("../demo/80-app.jsx", manifest["chunks"])
        blob = welfare.build(log_path=_log(_calls(labels=LABELS[:1])))
        for w in (blob, None):
            html = hydrate_page(d, {"WELFARE": w, "CAPABILITY": {"eci": {}}})
            self.assertIn(f"<script>window.__WELFARE__ = {json.dumps(w).replace('</', '<' + chr(92) + '/')};</script>", html)
            self.assertIn('<script>window.__CAPABILITY__ = {"eci": {}};</script>', html)
            self.assertEqual(html.count("function App()"), 1)
            self.assertEqual(html.count("ReactDOM.createRoot"), 1)
        self.assertTrue((REPO / "welfare.html").exists())


if __name__ == "__main__":
    unittest.main()
