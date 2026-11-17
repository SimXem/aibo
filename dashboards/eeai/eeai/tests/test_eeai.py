"""EEAI: the question set, the prompt, the cleaning, a run without calls, the page's data, the site."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from eeai import build, config, instrument, run, survey as S, synthetic  # noqa: E402
from fri_forecaster import baseline, panel  # noqa: E402

TODAY = date(2026, 11, 11)
MEMBERS = [{"key": "m-a", "label": "Model A", "model": "anthropic/m-a", "reasoning": "max"},
           {"key": "m-b", "label": "Model B", "model": "openai/m-b", "reasoning": "xhigh"},
           {"key": "m-c", "label": "Model C", "model": "openai/m-c", "reasoning": "xhigh"}]


class TestQuestionSet(unittest.TestCase):
    def setUp(self):
        self.survey, self.history = S.load(), S.history()

    def test_what_is_asked(self):
        s = self.survey
        self.assertEqual(len(s["questions"]), 15)
        self.assertEqual(S.n_values(s), 396)
        # The survey's own dates alone: its 156 values.
        self.assertEqual(sum(1 for q in s["questions"] for h, _, _ in S.asked(s, q) if h in ("2030", "2050")), 156)
        self.assertEqual(S.scenario_ids(s), ["unconditional", "slow", "moderate", "rapid"])
        gdp = s["questions"][0]
        self.assertEqual(gdp["id"], "gdp")
        self.assertEqual(S.percentiles(gdp, "rapid"), ("p10", "p50", "p90"))
        self.assertEqual(S.percentiles(gdp, "slow"), ("p50",))
        self.assertEqual({q["id"] for q in s["questions"] if q["uncertainty"]},
                         {"gdp", "lfpr", "unemployment", "wealth_inequality", "median_household_income"})
        hours = next(q for q in s["questions"] if q["id"] == "work_hours_assisted")
        self.assertEqual([h["id"] for h in hours["horizons"]], ["2027", "2028", "2029", "2030"])
        self.assertEqual([(h["id"], h["added"]) for h in gdp["horizons"]],
                         [("2027", True), ("2028", True), ("2029", True), ("2030", False), ("2050", False)])
        # A near date is the survey's 2030 wording moved back; a five-year window stays five years.
        self.assertEqual(gdp["horizons"][0]["text"], "the beginning of 2022 and the beginning of 2027?")
        self.assertEqual(gdp["horizons"][3]["text"], "the beginning of 2025 and the beginning of 2030?")
        self.assertEqual([p["id"] for p in s["part1"]],
                         ["scenario_probabilities", "indicator_importance", "household_robot", "reliability"])

    def test_a_date_that_has_passed_is_no_longer_asked(self):
        s, gdp = self.survey, self.survey["questions"][0]
        self.assertEqual([h["id"] for h in S.horizons(gdp, date(2026, 11, 11))], ["2027", "2028", "2029", "2030", "2050"])
        self.assertEqual([h["id"] for h in S.horizons(gdp, date(2027, 1, 1))], ["2027", "2028", "2029", "2030", "2050"])
        self.assertEqual([h["id"] for h in S.horizons(gdp, date(2027, 2, 1))], ["2028", "2029", "2030", "2050"])
        later = date(2028, 6, 1)
        prompt, _ = instrument.build_prompt(s, self.history, later)
        self.assertNotIn("- 2027:", prompt)
        self.assertNotIn("- 2028:", prompt)
        self.assertIn(f"{S.n_values(s, later)} numbers in all", prompt)
        full = synthetic.answer(s, self.history, later, "m")[0]["gdp"]
        out, _, problems = instrument.clean_cell(s, gdp, full, later)
        self.assertEqual((sorted(out), problems), (["2029", "2030", "2050"], []))

    def test_the_record_gives_a_date_its_outcome(self):
        series = [("2024-12-31", 3.35), ("2027-01-01", 5.0), ("2028-03-01", 9.0)]
        self.assertEqual(S.actual(series, "2025"), ("2024-12-31", 3.35))
        self.assertEqual(S.actual(series, "2027"), ("2027-01-01", 5.0))
        self.assertEqual(S.actual(series, "2028"), None)

    def test_every_question_has_its_history_and_no_markdown_left(self):
        for q in self.survey["questions"]:
            self.assertTrue(self.history.get(q["history"]), q["id"])
            for text in (q["stem"], q["details"]):
                self.assertNotIn("![", text)
                self.assertNotIn("\\", text)
                self.assertNotIn("**", text)

    def test_generated_files_match_the_survey_documents(self):
        if not (config.DATA / "source" / "survey.md").exists():
            self.skipTest("internal survey documents not present; the tracked set stands")
        r = subprocess.run([sys.executable, str(REPO / "eeai" / "make_questions.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestInstrument(unittest.TestCase):
    def setUp(self):
        self.survey, self.history = S.load(), S.history()

    def test_prompt_carries_the_survey_and_nothing_about_how_to_forecast(self):
        prompt, qids = instrument.build_prompt(self.survey, self.history, TODAY)
        self.assertEqual(prompt, instrument.build_prompt(self.survey, self.history, TODAY)[0])
        self.assertTrue(prompt.startswith("Today is 2026-11-11."))
        for q in self.survey["questions"]:
            self.assertIn(f"--- {q['id']} ({q['title']}) ---", prompt)
            self.assertIn(q["stem"], prompt)
        for s in ("--- slow: Slow Progress ---", "--- rapid: Rapid Progress ---", "The most commonly selected option is the assumed scenario."):
            self.assertIn(s, prompt)
        self.assertIn("2025-01-01: 2.39", prompt)
        self.assertIn("396 numbers in all", prompt)
        self.assertNotIn("superforecaster\n", prompt)
        self.assertNotIn("base rate", prompt.lower())
        self.assertEqual(len(qids), 15)

    def test_tools(self):
        cells, final = instrument.tools(self.survey)
        item = cells["parameters"]["properties"]["forecasts"]["items"]
        self.assertEqual(item["required"], ["question_id", "forecasts", "rationale"])
        self.assertEqual(set(item["properties"]["forecasts"]["properties"]), {"2027", "2028", "2029", "2030", "2050"})
        self.assertEqual(final["parameters"]["required"],
                         ["scenario_probabilities", "indicator_importance", "household_robot", "reliability", "rationale"])

    def test_clean_cell_keeps_what_was_asked_and_names_the_rest(self):
        q = self.survey["questions"][0]
        cells, _ = synthetic.answer(self.survey, self.history, TODAY, "m")
        raw = copy.deepcopy(cells["gdp"])
        raw["forecasts"]["2030"]["slow"].update(p10=0.1, p90=9.0)       # not asked: dropped
        raw["forecasts"]["2030"]["rapid"] = {"p10": 5, "p50": 4, "p90": 6}  # out of order: refused
        raw["forecasts"]["2050"]["moderate"] = {"p50": 5000}             # out of bounds
        del raw["forecasts"]["2050"]["unconditional"]["p90"]
        out, rationale, problems = instrument.clean_cell(self.survey, q, raw)
        self.assertEqual(set(out["2030"]["slow"]), {"p50"})
        self.assertNotIn("rapid", out["2030"])
        self.assertNotIn("moderate", out["2050"])
        self.assertEqual(set(out["2050"]["unconditional"]), {"p10", "p50"})
        self.assertEqual(rationale, synthetic.NOTE)
        self.assertEqual(len(problems), 3)
        self.assertEqual(instrument.clean_cell(self.survey, q, {})[0], {})

    def test_clean_part1(self):
        ok = {"scenario_probabilities": {"slow": 30, "moderate": 50, "rapid": 20.5},
              "indicator_importance": {"research": 20, "problem_solving": 20, "creativity": 20, "agency": 20, "robotics": 20},
              "household_robot": 5, "reliability": 150}
        out, problems = instrument.clean_part1(self.survey, ok)
        self.assertEqual(set(out), {"scenario_probabilities", "indicator_importance", "household_robot"})
        self.assertEqual(problems, ["reliability: missing or out of range"])
        bad = dict(ok, scenario_probabilities={"slow": 0.3, "moderate": 0.5, "rapid": 0.2})
        self.assertIn("scenario_probabilities: sums to 1, not 100", instrument.clean_part1(self.survey, bad)[1])


class TestRunAndBuild(unittest.TestCase):
    def setUp(self):
        self.survey, self.history = S.load(), S.history()

    def _rows(self, day, members=MEMBERS, harness_run=None):
        fake = harness_run or synthetic.harness_run(self.survey, self.history, day)
        rows = []
        for m in members:
            rows += run.ask(m, self.survey, self.history, day, f"{day}T0000Z", panel={"members": [{"label": x["label"]} for x in members]},
                            harness_run=fake, synthetic=True)
        return rows

    def test_a_call_becomes_one_row_per_question(self):
        rows = self._rows(TODAY, MEMBERS[:1])
        self.assertEqual([r["question_id"] for r in rows], [q["id"] for q in self.survey["questions"]])
        self.assertTrue(rows[0]["call"] and all(r["call"] is None for r in rows[1:]))
        call = rows[0]["call"]
        self.assertEqual((call["values"], call["values_asked"], call["attempts"]), (396, 396, 1))
        self.assertEqual(call["system_prompt"], " ")
        self.assertEqual(rows[0]["condition"], "baseline")
        self.assertEqual(rows[0]["instrument"], self.survey["instrument"])
        self.assertTrue(all(r["problems"] == [] for r in rows))

    def test_the_models_cannot_read_fris_own_pages(self):
        import re
        from fri_forecaster import tools
        seen = {}
        full = synthetic.harness_run(self.survey, self.history, TODAY)

        def spy(**kw):
            seen.update(kw["env"])
            return full(**kw)

        rows = self._rows(TODAY, MEMBERS[:1], harness_run=spy)
        self.assertEqual(rows[0]["call"]["blocked_urls"], list(config.BLOCKED_URLS))
        guard = [re.compile(p, re.I) for p in seen[tools.BLOCK_ENV].split("\n")]
        for url in ("https://forecastingresearch.org/research/economic-effects-of-ai",
                    "https://leap.forecastingresearch.org/forecasts/baseline-scenarios",
                    "https://forecastingresearch.substack.com/p/anything",
                    "https://web.archive.org/web/2026/https://forecastingresearch.org/research"):
            self.assertTrue(tools.is_blocked(url, guard), url)
        for url in ("https://www.bls.gov/news.release/empsit.nr0.htm", "https://metr.org/blog/x"):
            self.assertFalse(tools.is_blocked(url, guard), url)

    def test_a_thin_answer_is_asked_again_and_an_empty_one_fails(self):
        full = synthetic.harness_run(self.survey, self.history, TODAY)
        calls = []

        def thin_then_full(**kw):
            calls.append(1)
            res = full(**kw)
            if len(calls) == 1:
                res["cells"] = dict(list(res["cells"].items())[:3])
            return res
        rows = self._rows(TODAY, MEMBERS[:1], thin_then_full)
        self.assertEqual((len(calls), rows[0]["call"]["attempts"], rows[0]["call"]["values"]), (2, 2, 396))

        def empty(**kw):
            return dict(full(**kw), cells={})
        with self.assertRaises(RuntimeError):
            self._rows(TODAY, MEMBERS[:1], empty)

    def test_the_page_data_is_the_panel_median_and_the_page_carries_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            for day in (date(2026, 11, 4), TODAY):
                with open(Path(tmp) / f"{day}T0000Z.jsonl", "w") as f:
                    f.writelines(json.dumps(r) + "\n" for r in self._rows(day))
            runs = build.load_runs(tmp, self.survey["instrument"])
            blob = build.build(self.survey, self.history, runs)
        self.assertTrue(blob["synthetic"])
        self.assertEqual(blob["latest"]["date"], "2026-11-11")
        self.assertEqual(blob["latest"]["models"], ["Model A", "Model B", "Model C"])
        gdp = blob["questions"][0]
        mids = sorted(m["forecasts"]["2030"]["unconditional"]["p50"] for m in gdp["models"])
        self.assertAlmostEqual(gdp["ensemble"]["2030"]["unconditional"]["p50"], mids[1], places=3)
        self.assertEqual([s["date"] for s in gdp["series"]], ["2026-11-04", "2026-11-11"])
        # The history view places a run by when it was asked.
        self.assertEqual([s["at"] for s in gdp["series"]], ["2026-11-04T00:00:00Z", "2026-11-11T00:00:00Z"])
        self.assertEqual(build._asked_at("2026-11-11T2258Z", "2026-11-11"), "2026-11-11T22:58:00Z")
        self.assertEqual(build._asked_at("r1", "2026-11-11"), "2026-11-11T00:00:00Z")
        # ... and carries each model's own answers, for the tooltips' breakdown.
        last = gdp["series"][-1]["models"]
        self.assertEqual(sorted(last), sorted(m["label"] for m in MEMBERS))
        self.assertEqual({m["label"]: m["forecasts"] for m in gdp["models"]}, last)
        self.assertEqual(set(gdp["ensemble"]["2030"]["slow"]), {"p50"})
        probs = blob["part1"]["scenario_probabilities"]["ensemble"]
        self.assertAlmostEqual(sum(probs.values()), 100, places=1)
        page = build.page(blob)
        self.assertIn("window.__EEAI__ = {", page)
        self.assertEqual(page.count("<!--EEAI_DATA-->"), 1)
        self.assertEqual(build.build(self.survey, self.history, [])["latest"], None)

    def test_a_settled_date_keeps_its_last_forecast_beside_the_outcome(self):
        # Asked in 2026 about 2027..2050 and in 2027 (after the date) about 2028..2050;
        # the record then gets its 2027 value.
        early, late = date(2026, 11, 11), date(2027, 3, 1)
        runs = [("r1", self._rows(early)), ("r2", self._rows(late))]
        history = {k: list(v) for k, v in self.history.items()}
        history["gdp"].append(("2027-01-01", 2.0))
        gdp = build.build(self.survey, history, runs)["questions"][0]
        h27 = gdp["horizons"][0]
        self.assertEqual((h27["id"], h27["asked"], h27["actual"]), ("2027", "2026-11-11", {"date": "2027-01-01", "value": 2.0}))
        self.assertEqual((gdp["horizons"][1]["asked"], gdp["horizons"][1]["actual"]), ("2027-03-01", None))
        first, second = (s["ensemble"] for s in gdp["series"])
        self.assertNotIn("2027", second)
        self.assertEqual(gdp["ensemble"]["2027"], first["2027"])
        self.assertEqual(gdp["ensemble"]["2030"], second["2030"])

    def test_rows_of_the_instrument_it_continues_still_count(self):
        import tempfile
        rows = self._rows(TODAY, MEMBERS[:1])
        for r in rows:
            r["instrument"] = "eeai-survey-v1"
            r["forecasts"] = {h: v for h, v in r["forecasts"].items() if h in ("2030", "2050")}
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "old.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            self.assertEqual(len(build.load_runs(tmp, S.instruments(self.survey))), 1)
            self.assertEqual(build.load_runs(tmp, "some-other-instrument"), [])
            gdp = build.build(self.survey, self.history, build.load_runs(tmp, S.instruments(self.survey)))["questions"][0]
            self.assertEqual(sorted(gdp["ensemble"]), ["2030", "2050"])

    def test_the_site_folder_is_self_contained(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._rows(TODAY, MEMBERS[:1])
            runs = Path(tmp) / "runs"
            runs.mkdir()
            (runs / "r1.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            site = Path(tmp) / "site"
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                build.main(SimpleNamespace(runs=str(runs), out=None, json=None, site=str(site)))
            # (a box that has the licensed fonts under web/fonts gets them too)
            have = sorted(str(p.relative_to(site)) for p in site.rglob("*") if p.is_file() and "fonts" not in p.parts)
            self.assertEqual(have, ["eeai-data.zip", "index.html", "web/img/fri-logo.svg"])
            page = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn('"download": "eeai-data.zip"', page)
            self.assertIn("web/img/fri-logo.svg", page)

    def test_the_download_holds_every_number(self):
        import csv, io, tempfile, zipfile
        from eeai import export
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._rows(TODAY)
            (Path(tmp) / "r1.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            runs = build.load_runs(tmp)
            self.assertEqual(build.build(self.survey, self.history, runs)["download"], export.NAME)
            self.assertEqual(build.build(self.survey, self.history, [])["download"], None)
            names = export.bundle(Path(tmp) / export.NAME, self.survey, runs, tmp)
            self.assertEqual(names, ["README.md", "forecasts.csv", "rationales.csv", "ai_progress.csv",
                                     "questions.json", "history.csv", "runs/r1.jsonl"])
            with zipfile.ZipFile(Path(tmp) / export.NAME) as z:
                lines = list(csv.DictReader(io.StringIO(z.read("forecasts.csv").decode())))
                self.assertEqual(len(lines), len(MEMBERS) * S.n_values(self.survey))
                self.assertEqual(len(list(csv.reader(io.StringIO(z.read("rationales.csv").decode())))) - 1,
                                 len(MEMBERS) * len(self.survey["questions"]))
                self.assertIn("PLACEHOLDER", z.read("README.md").decode())
                probs = [l for l in csv.DictReader(io.StringIO(z.read("ai_progress.csv").decode()))
                         if l["item"] == "scenario_probabilities" and l["model"] == MEMBERS[0]["label"]]
                self.assertAlmostEqual(sum(float(l["value"]) for l in probs), 100, places=1)

    def test_synthetic_rows_never_go_to_results(self):
        args = SimpleNamespace(today="2026-11-11", smoke=True, models=None, synthetic=True, out=None,
                               allow_ungrounded=False, retries=0, workers=1, resume=None)
        with self.assertRaises(SystemExit):
            run.main(args)

    def test_resume_adds_only_the_models_a_run_lacks(self):
        import contextlib, io, tempfile
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(io.StringIO()):
            args = SimpleNamespace(today="2026-11-11", smoke=True, models=None, synthetic=True, out=out,
                                   allow_ungrounded=False, retries=0, workers=1, resume=None)
            self.assertEqual(run.main(args), 0)
            args.smoke, args.resume, args.today = False, "2026-11-11T0000Z", "2026-11-12"
            self.assertEqual(run.main(args), 0)
            # A fetched page can carry U+2028 inside a string: still one row per line.
            path = next(Path(out).glob("*.jsonl"))
            first, _, rest = path.read_text(encoding="utf-8").partition("\n")
            row = json.loads(first)
            row["call"]["evidence"] = [{"tool": "read_page", "args": {}, "result": {"text": "a\u2028b\x85c"}}]
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n" + rest, encoding="utf-8")
            runs = build.load_runs(out)
            self.assertEqual(len(runs), 1)
            rows = runs[0][1]
            self.assertEqual(len({r["key"] for r in rows}), panel.PANEL_K)
            self.assertEqual(len(rows), panel.PANEL_K * len(self.survey["questions"]))
            self.assertEqual({(r["run_id"], r["run_date"]) for r in rows}, {("2026-11-11T0000Z", "2026-11-11")})
            self.assertEqual(len({r["prompt_sha256"] for r in rows}), 1)
            with self.assertRaises(SystemExit):
                run.main(args)


if __name__ == "__main__":
    unittest.main()
