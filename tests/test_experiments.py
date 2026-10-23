"""Experiments and their conditions (redlines/experiments.py).

experiments/airo.toml is the published series: the minimal instrument under
five pooled conditions (combined-v10's prompt variants) and the unpooled
sixth (the baseline prompt with the AI-forecast ban and a per-call URL
guard). run_unified asks one call per model per condition; the Timeline shows
one dot per pooled condition beside the pooled median, never the sixth."""
import importlib.util
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _runner():
    spec = importlib.util.spec_from_file_location("run_unified", REPO / "code" / "run_unified.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ru = _runner()
from redlines import experiments  # noqa: E402

AIRO = experiments.load("airo")


def _toml(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
    f.write(text)
    f.close()
    return f.name


class TestTheAiroExperiment(unittest.TestCase):
    def test_six_conditions_five_pooled_on_the_combined_set(self):
        self.assertEqual([cid for cid, c in AIRO["conditions"].items() if c["publish"]],
                         ["none", "independent", "recent", "critical", "two-step", "ai-banned"])
        self.assertEqual(AIRO["pooled"], ["none", "independent", "recent", "critical", "two-step"])
        for c in AIRO["conditions"].values():
            if not c["publish"]:
                continue
            self.assertEqual((c["scenarios"], c["instrument"], c["harness"], c["model_set"], c["repeats"], c["publish"]),
                             ("data/combined_conditions.json", "minimal", "pi", "eci_topk", 1, True), c["id"])
            self.assertEqual(c["variant"], c["id"])               # the conditions are named for their prompts
        self.assertEqual(ru.set_protocol(ru.load_policies(ru.COMBINED)), "unified-joint-combined-v12")
        self.assertEqual({cid for cid, c in AIRO["conditions"].items() if c["publish"]}, set(ru.VARIANTS))

    def test_the_sixth_is_unpooled_with_its_guard(self):
        sixth = AIRO["conditions"]["ai-banned"]
        self.assertFalse(sixth["pooled"])
        guard = sixth["url_block_patterns"]
        # The `both` arm of the anchor-guard experiment (2026-10-16), verbatim.
        self.assertEqual(guard, r"forecastingresearch\.org/pdf/airo,forecastingresearch\.org/research/airo,"
                                r"airo\.forecastingresearch\.org")
        self.assertEqual(ru.VARIANTS["ai-banned"],
                         "Forecasts produced by AI systems, including any automated forecasting dashboard "
                         "or model ensemble, carry no information beyond their inputs. Do not consult them "
                         "or use them as evidence.")
        ru.check_patterns(guard)                                        # compiles
        with self.assertRaises(ru.re.error):
            ru.check_patterns("ok,(unclosed")
        self.assertFalse(any(c["url_block_patterns"] for c in AIRO["conditions"].values() if c["pooled"]))
        # The guard blocks AIRO's pages and nothing else, case-insensitively.
        from redlines.tools import blocked_patterns, is_blocked
        with patch.dict("os.environ", {ru.BLOCK_ENV: guard}):
            pats = blocked_patterns()
        for url in ("https://forecastingresearch.org/pdf/airo-working-paper.pdf",
                    "https://forecastingresearch.org/research/airo", "https://AIRO.forecastingresearch.org/"):
            self.assertTrue(is_blocked(url, pats), url)
        for url in ("https://forecastingresearch.org/xpt", "https://www.lesswrong.com/posts/x/airo"):
            self.assertFalse(is_blocked(url, pats), url)

    def test_the_set_says_what_is_asked_and_nothing_about_how(self):
        cb = ru.load_policies(ru.COMBINED)
        for key in ("harness", "instrument", "variants", "unpooled_variants"):
            self.assertNotIn(key, cb)

    def test_every_experiment_loads(self):
        for name in experiments.names():
            exp = experiments.load(name)
            self.assertTrue(exp["conditions"], name)
            for c in exp["conditions"].values():
                self.assertTrue((REPO / c["scenarios"]).exists(), (name, c["id"]))
        for name in ("axes", "paperaxes"):                       # the axes instruments: one standard call
            (c,) = experiments.load(name)["conditions"].values()
            self.assertEqual((c["variant"], c["instrument"], c["harness"], c["pooled"], c["publish"]),
                             ("none", "standard", "pi", True, True))


class TestConditions(unittest.TestCase):
    """What a condition is: the shared settings, its own over them, a hash of what it asks."""

    def test_a_condition_takes_the_shared_settings_and_overrides_its_own(self):
        exp = experiments.load(_toml("""
scenarios = "data/combined_conditions.json"
harness = "pi"
instrument = "minimal"
pooled = ["a"]
publish = true

[conditions.a]
[conditions.b]
variant = "recent"
model_set = "frontier5"
"""))
        a, b = exp["conditions"]["a"], exp["conditions"]["b"]
        self.assertEqual((a["variant"], a["model_set"], a["harness"], a["pooled"]), ("none", "eci_topk", "pi", True))
        self.assertEqual((b["variant"], b["model_set"], b["harness"], b["pooled"]), ("recent", "frontier5", "pi", False))
        self.assertTrue(b["publish"])                            # shared, not overridden

    def test_the_hash_is_what_a_call_is_asked(self):
        base = dict(experiments.DEFAULTS, scenarios="data/combined_conditions.json")
        h = experiments.condition_sha256(base)
        self.assertEqual(h, experiments.condition_sha256(dict(base, publish=True, repeats=3)))
        for k, v in (("variant", "recent"), ("harness", "other"), ("model_set", "frontier5"),
                     ("url_block_patterns", "x"), ("scenarios", "data/axes_conditions.json")):
            self.assertNotEqual(h, experiments.condition_sha256(dict(base, **{k: v})), k)
        self.assertEqual(AIRO["conditions"]["none"]["sha256"],
                         experiments.condition_sha256({k: AIRO["conditions"]["none"][k] for k in experiments.DEFAULTS}))

    def test_what_cannot_run_as_written_is_refused(self):
        head = 'scenarios = "data/combined_conditions.json"\n'
        for body, why in (
                ('[conditions.a]\nharnes = "pi"\n', "unknown setting"),
                ('pooled = ["b"]\n[conditions.a]\n', "not conditions"),
                ('pooled = ["a"]\n[conditions.a]\n', "pooled condition publishes"),
                ('[conditions.a]\nharness = "litellm"\n', "harness 'litellm' is not one of"),
                ('[conditions.a]\nurl_block_patterns = "(x"\n', "bad url_block_patterns"),
                ('[conditions.a]\nvariant = "nope"\n', "unknown variant"),
                ('[conditions.a]\nrepeats = 0\n', "repeats"),
                ('', "no \\[conditions")):
            with self.assertRaisesRegex(ValueError, why):
                experiments.load(_toml(head + body))
        with self.assertRaisesRegex(ValueError, "no scenario set"):
            experiments.load(_toml("[conditions.a]\n"))

    def test_the_baseline_adds_no_instruction(self):
        self.assertEqual(experiments.baseline(AIRO)["id"], "none")


class TestCadence(unittest.TestCase):
    """When the cron runs a condition, and what is due on a day."""

    def test_airo_runs_wednesdays_and_fridays_and_the_axes_by_hand(self):
        self.assertEqual({tuple(c["cadence"]) for c in AIRO["conditions"].values() if c["publish"]}, {("wed", "fri")})
        for name in ("axes", "paperaxes"):
            self.assertEqual({c["cadence"] for c in experiments.load(name)["conditions"].values()}, {"manual"})

    def test_is_due(self):
        c = lambda cadence: {"cadence": cadence}
        wed, thu = date(2026, 10, 21), date(2026, 10, 22)
        self.assertTrue(experiments.is_due(c(["wed", "fri"]), wed))
        self.assertFalse(experiments.is_due(c(["wed", "fri"]), thu))
        self.assertFalse(experiments.is_due(c("manual"), wed))
        self.assertTrue(experiments.is_due(c(["1st wed"]), date(2026, 10, 7)))      # Oct 1 is a Thursday
        self.assertFalse(experiments.is_due(c(["1st wed"]), date(2026, 10, 14)))
        self.assertTrue(experiments.is_due(c(["3rd wed"]), wed))

    def test_the_hash_ignores_when(self):
        base = dict(experiments.DEFAULTS, scenarios="data/combined_conditions.json")
        self.assertEqual(experiments.condition_sha256(base),
                         experiments.condition_sha256(dict(base, cadence=["mon"])))

    def test_what_is_due_groups_by_set_and_destination(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "pub.toml").write_text("""
scenarios = "data/combined_conditions.json"
publish = true
cadence = ["wed", "fri"]
pooled = ["a"]
[conditions.a]
[conditions.b]
cadence = ["fri"]
[conditions.aside]
publish = false
cadence = ["mon", "wed"]
""")
            Path(d, "hand.toml").write_text('scenarios = "data/axes_conditions.json"\n[conditions.x]\n')
            with patch.object(experiments, "EXPERIMENTS_DIR", Path(d)):
                self.assertEqual(experiments.due(date(2026, 10, 21)),                  # a Wednesday
                                 [("pub", True, ["a"]), ("pub", False, ["aside"])])
                self.assertEqual(experiments.due(date(2026, 10, 23)), [("pub", True, ["a", "b"])])
                self.assertEqual(experiments.due(date(2026, 10, 20)), [])
                self.assertEqual(experiments.due(date(2026, 10, 20), ["hand", "pub"]),  # by hand: all of them
                                 [("hand", False, ["x"]), ("pub", True, ["a", "b"]), ("pub", False, ["aside"])])

    def test_the_cli_prints_one_group_a_line(self):
        import subprocess
        r = subprocess.run([sys.executable, "-m", "redlines.experiments", "due", "--date", "2026-10-21"],
                           capture_output=True, text=True, cwd=REPO)
        self.assertEqual(r.stdout, "airo publish none independent recent critical two-step ai-banned\n")

    def test_cadences_that_cannot_be_kept_are_refused(self):
        head = 'scenarios = "data/combined_conditions.json"\npublish = true\ncadence = ["wed"]\npooled = ["a"]\n'
        for body, why in (
                ('[conditions.a]\ncadence = "weekly"\n', "is not"),
                ('[conditions.a]\ncadence = ["wednesday"]\n', "is not"),
                ('[conditions.a]\ncadence = ["6th wed"]\n', "is not"),
                ('[conditions.a]\ncadence = []\n', "is not"),
                ('pooled = ["a", "b"]\n[conditions.a]\n[conditions.b]\ncadence = ["fri"]\n', "different cadences"),
                ('[conditions.a]\n[conditions.b]\ncadence = ["wed", "fri"]\n', "runs only beside them")):
            text = head.replace('pooled = ["a"]\n', "") + body if body.startswith("pooled") else head + body
            with self.assertRaisesRegex(ValueError, why):
                experiments.load(_toml(text))
        ok = head + '[conditions.a]\n[conditions.b]\ncadence = ["2nd wed"]\n[conditions.c]\ncadence = "manual"\n' \
            '[conditions.d]\npublish = false\ncadence = ["sun"]\n'
        self.assertEqual(list(experiments.load(_toml(ok))["conditions"]), ["a", "b", "c", "d"])


class TestMinimalPrompt(unittest.TestCase):
    def _prompt(self):
        today = date(2026, 10, 19)
        pol = ru.resolve_set(ru.load_policies(ru.COMBINED), today)
        g, b, h, _, spec = ru.load_batch(ru.LADDER, ru.CROSS, ru.UNBATCHED)
        h = ru.set_horizons(pol, h)
        return ru.build_prompt_joint(g, b, h, spec, pol["conditions"], pol, today)[0]

    def test_cuts_only_the_guidance(self):
        p = self._prompt()
        m = ru.minimal_joint_prompt(p)
        for gone in ("forecasting questions, grouped by cause", "Research before answering",
                     "3-6 sentence rationale", "After it is accepted"):
            self.assertIn(gone, p)
            self.assertNotIn(gone, m)
        blocks = p[p.index("===== AI-RELATED INCIDENT"):p.index("\nHorizons: ")]
        self.assertIn(blocks, m)                       # questions and scenarios byte for byte
        self.assertIn("Deliver the probabilities with submit_cells", m)
        self.assertLess(len(m.encode()), 131072)       # pi takes the prompt as one argv string

    def test_each_variant_adds_only_its_instruction_before_delivery(self):
        base = ru.minimal_joint_prompt(self._prompt())
        for v, text in ru.VARIANTS.items():
            m = ru.minimal_joint_prompt(self._prompt(), v)
            if not text:
                self.assertEqual(m, base)
                continue
            self.assertEqual(m.replace(text + "\n\n", "", 1), base)
            self.assertLess(m.index(text), m.index("Deliver the probabilities"))

    def test_minimal_tools_drop_cause_and_advice(self):
        research, _ = ru.research_tools([{"key": "ai", "label": "AI"}])
        out = ru.minimal_tools(research)
        ws = next(t for t in out if t["name"] == "web_search")
        self.assertEqual(ws["description"], ru.MINIMAL_TOOLS["web_search"])
        self.assertNotIn("cause", ws["parameters"]["properties"])
        self.assertIn("cause", next(t for t in research if t["name"] == "web_search")["parameters"]["properties"])


class TestRunOneJoint(unittest.TestCase):
    """One call per variant through a fake loop: what the loop is given, and the rows."""

    def _call(self, cid, answer_cells=True, **settings):
        today = date(2026, 10, 19)
        pol = ru.load_policies(ru.COMBINED)
        g, b, h, _, spec = ru.load_batch(ru.LADDER, ru.CROSS, ru.UNBATCHED)
        h = ru.set_horizons(pol, h)
        seen = {}
        rp = ru.resolve_set(pol, today)
        cond_ids = [c["id"] for c in rp["conditions"]]

        def fake(model, prompt, tools, final_tool, **kw):
            seen.update(prompt=prompt, tools=tools, **kw)
            cells = [{"question_id": q["id"], "horizon": hz,
                      "probabilities": {k: 0.01 for k in ["unconditional"] + cond_ids}}
                     for gg in g for q in b[gg["key"]] for hz in h if hz in q["horizons"]] if answer_cells else []
            return {"forecasts": cells, "rationale": "r",
                    "eci_forecast": {"p10": 168, "p25": 170, "p50": 172, "p75": 175, "p90": 178}}, []

        orig = ru.call_tools
        ru.call_tools = fake
        try:
            rows = ru.run_one_joint("M", "anthropic/x", g, b, h, "2026-10-19T0000Z", 0, spec,
                                    pol["conditions"], pol, {**AIRO["conditions"][cid], **settings},
                                    "airo", today=today)
        finally:
            ru.call_tools = orig
        return rows, seen

    def test_rows_and_loop_settings(self):
        rows, seen = self._call("independent")
        self.assertEqual(seen["system"], ru.MINIMAL_SYSTEM)
        self.assertEqual(seen["min_evidence"], 0)
        self.assertIsNone(seen["coverage"])
        self.assertIsNone(seen["debrief"])
        self.assertEqual(seen["max_iters"], ru.MINIMAL_MAX_TURNS)
        self.assertIn(ru.VARIANTS["independent"], seen["prompt"])
        self.assertEqual({r["variant"] for r in rows}, {"independent"})
        self.assertEqual({(r["experiment"], r["condition"], r["condition_sha256"]) for r in rows},
                         {("airo", "independent", AIRO["conditions"]["independent"]["sha256"])})
        self.assertTrue(rows[0]["call_id"].endswith(":independent"))
        self.assertEqual(rows[0]["protocol"], "unified-joint-combined-v12")   # the set's tag
        self.assertEqual(rows[0]["system_prompt"], ru.MINIMAL_SYSTEM)
        self.assertTrue(all(r["forecasts"] for r in rows))
        # A pooled call: no guard reaches the loop, and the rows are as before.
        self.assertNotIn("env", seen)
        self.assertFalse(any("url_block_patterns" in r or "pooled" in r for r in rows))

    def test_the_sixth_runs_guarded_and_its_rows_say_so(self):
        guard = AIRO["conditions"]["ai-banned"]["url_block_patterns"]
        rows, seen = self._call("ai-banned")
        # The sentence where a variant's text goes; the guard to THIS call only.
        self.assertIn(ru.VARIANTS["ai-banned"], seen["prompt"])
        self.assertLess(seen["prompt"].index(ru.VARIANTS["ai-banned"]), seen["prompt"].index("Deliver the probabilities"))
        self.assertEqual(seen["env"], {ru.BLOCK_ENV: guard})
        self.assertNotIn(ru.BLOCK_ENV, ru.os.environ)
        self.assertEqual(seen["system"], ru.MINIMAL_SYSTEM)
        # The rows: the condition, the guard, unpooled; the protocol is the set's.
        self.assertEqual({r["variant"] for r in rows}, {"ai-banned"})
        self.assertEqual({r["url_block_patterns"] for r in rows}, {guard})
        self.assertEqual({r["pooled"] for r in rows}, {False})
        self.assertEqual({r["protocol"] for r in rows}, {"unified-joint-combined-v12"})
        self.assertTrue(rows[0]["call_id"].endswith(":ai-banned"))
        self.assertTrue(all(r["forecasts"] for r in rows))

    def test_a_process_environment_guard_is_stamped_on_every_row(self):
        # #5's stamping: a guard in os.environ reaches every call and every row says so.
        with patch.dict("os.environ", {ru.BLOCK_ENV: "example\\.org"}):
            rows, seen = self._call("none")
        self.assertNotIn("env", seen)
        self.assertEqual({r["url_block_patterns"] for r in rows}, {"example\\.org"})
        self.assertFalse(any("pooled" in r for r in rows))

    def test_baseline_call_id_is_unchanged(self):
        rows, _ = self._call("none")
        self.assertFalse(rows[0]["call_id"].endswith(":none"))

    def test_no_forecasts_is_a_failure(self):
        with self.assertRaisesRegex(RuntimeError, "no forecasts"):
            self._call("none", answer_cells=False)


class TestTimelineConditions(unittest.TestCase):
    def test_condition_cells(self):
        from redlines.views.timeline import condition_cells
        mk = lambda label, c, p: {"run_date": "2026-10-19", "elicited_at": "2026-10-19T12:00:00+00:00",
                                  "question_id": "catastrophe:ai", "label": label, "condition": c,
                                  "forecasts": [{"horizon": "2030", "probability": p}]}
        rows = [mk("A", "none", 0.01), mk("B", "none", 0.03), mk("A", "independent", 0.02), mk("B", "independent", 0.04)]
        out = condition_cells(rows)
        self.assertEqual(out[("2026-10-19", "catastrophe:ai")]["none"]["2030"], {"A": 1.0, "B": 3.0})
        self.assertEqual(out[("2026-10-19", "catastrophe:ai")]["independent"]["2030"], {"A": 2.0, "B": 4.0})
        self.assertEqual(condition_cells(rows[:2]), {})                         # one condition: no dots

    def test_condition_variants_reads_the_variant_off_the_rows(self):
        from redlines.views.timeline import condition_variants
        rows = [{"elicited_at": "2026-10-19T12:00:00+00:00", "condition": "none", "variant": "none"},
                {"elicited_at": "2026-10-19T12:00:00+00:00", "condition": "crit", "variant": "critical"}]
        self.assertEqual(condition_variants(rows), {"none": "none", "crit": "critical"})

    def test_the_legend_is_the_published_experiments_pooled_conditions_in_its_order(self):
        from redlines.views.timeline import condition_legend
        legend = condition_legend({"none": "none"})
        pooled = [c for c, cfg in AIRO["conditions"].items() if cfg["pooled"]]
        self.assertEqual([e["id"] for e in legend], pooled)
        self.assertNotIn("ai-banned", pooled)                              # the sixth is never shown
        self.assertEqual(legend[0]["text"], ru.VARIANTS["none"])
        old = condition_legend({"retired": "recent"})
        self.assertEqual((old[-1]["id"], old[-1]["text"]), ("retired", ru.VARIANTS["recent"]))


class TestPooledRows(unittest.TestCase):
    """The sixth's rows (`pooled: false`) enter no published number."""

    def test_load_runlog_and_load_conditional_drop_them_unless_asked(self):
        import json
        import tempfile
        from redlines import conditional, runlog
        mk = lambda v, **kw: {"elicited_at": "2026-10-19T12:00:00+00:00", "run_date": "2026-10-19",
                              "question_id": "q", "label": "A", "variant": v, "forecasts": [], **kw}
        rows = [mk("none"), mk("ai-banned", pooled=False, url_block_patterns="x")]
        self.assertEqual([r["variant"] for r in runlog.pooled_rows(rows)], ["none"])
        with tempfile.TemporaryDirectory() as d:
            runs = Path(d) / "runs"
            runs.mkdir()
            (runs / "2026-10-19T1200Z.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
            got = runlog.load_runlog(runlog=Path(d) / "none.jsonl", runs_dir=runs)
            self.assertEqual([r["variant"] for r in got], ["none"])
            got = runlog.load_runlog(runlog=Path(d) / "none.jsonl", runs_dir=runs, panel_only=False)
            self.assertEqual([r["variant"] for r in got], ["none", "ai-banned"])
            log = Path(d) / "cond.jsonl"
            log.write_text("".join(json.dumps(r) + "\n" for r in rows))
            self.assertEqual([r["variant"] for r in conditional.load_conditional(log)], ["none"])
            self.assertEqual([r["variant"] for r in conditional.load_conditional(log, pooled_only=False)],
                             ["none", "ai-banned"])


if __name__ == "__main__":
    unittest.main()
