"""The ForecastBench driver and its name registry, against a fake `pi` (no network, no spend)."""
import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import textwrap
import unittest
import unittest.mock

import forecastbench as fb
from fri_forecaster import harness

FAKE_PI = textwrap.dedent("""\
    #!{py}
    import json, os, sys
    out = os.environ["FORECASTER_OUT"]
    open(os.path.join(out, "stdin.txt"), "w").write(sys.stdin.read())   # the prompt, as pi would read it
    json.dump({{k: os.environ.get(k) for k in ("PI_CODING_AGENT_DIR", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_OAUTH_TOKEN", "ANTHROPIC_API_KEY")}},
              open(os.path.join(out, "env.json"), "w"))
    if os.environ.get("FAKE_API_ERROR"):   # a provider error: pi ends the turn, exit 0, no cells
        print(json.dumps({{"type": "message_end", "message": {{"role": "assistant", "stopReason": "error",
                                                             "errorMessage": os.environ["FAKE_API_ERROR"], "usage": {{"input": 3}}}}}}))
        sys.exit(0)
    spec = json.load(open(os.path.join(out, "spec.json")))
    keys = spec["allowed_keys"]
    field = spec["key_fields"][0]
    if spec["tools"].get("submit_cells"):
        with open(os.path.join(out, "pieces.jsonl"), "w") as f:
            f.write(json.dumps({{"forecasts": [{{field: keys[0], "probability": 0.1}}, {{field: "bogus", "probability": 0.9}}]}}) + "\\n")
    p = float(os.environ.get("FAKE_P", "0.3"))
    final = [{{field: k, "probability": p}} for k in keys[(0 if os.environ.get("FAKE_ALL") else 1):]]
    json.dump({{"answer": {{"forecasts": final, "rationale": "because", "key_sources": ["u"]}}}}, open(os.path.join(out, "final.json"), "w"))
    ev = [{{"type": "tool_execution_start", "toolCallId": "c1", "toolName": "web_search", "args": {{"query": "q"}}}},
          {{"type": "tool_execution_end", "toolCallId": "c1", "toolName": "web_search", "result": {{"details": {{"results": [1, 2]}}}}}},
          {{"type": "tool_execution_start", "toolCallId": "c2", "toolName": "read_page", "args": {{"url": "u"}}}},
          {{"type": "tool_execution_end", "toolCallId": "c2", "toolName": "read_page", "result": {{"details": {{"text": "", "error": "page read failed"}}}}}},
          {{"type": "tool_execution_end", "toolName": "submit_forecast", "args": {{}}, "result": {{}}}},
          {{"type": "message_end", "message": {{"role": "assistant", "usage": {{"input": 10, "output": 5, "cacheRead": 2, "cost": {{"total": 0.01}}}}}}}},
          {{"type": "message_end", "message": {{"role": "assistant", "usage": {{"input": 1, "output": 1, "cost": {{"total": 0.02}}}}}}}}]
    for e in ev:
        print(json.dumps(e))
    """)


def fake_pi(d):
    p = os.path.join(d, "pi")
    open(p, "w").write(FAKE_PI.format(py=sys.executable))
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
    return p


SCHEMA = {"type": "object", "properties": {"k": {"type": "string"}, "probability": {"type": "number"}}}
DESC = {"web_search": "s", "read_page": "r", "submit_cells": "c", "submit_forecast": "f"}


QSET = {"forecast_due_date": "2026-10-11", "question_set": "2026-10-11-llm.json", "questions": [
    {"id": "m1", "source": "metaculus", "question": "Will X happen?", "resolution_dates": "N/A",
     "background": "N/A", "freeze_datetime_value": "0.4", "freeze_datetime": "2026-10-01T00:00:00+00:00",
     "freeze_datetime_value_explanation": "The market value.", "resolution_criteria": "rc", "url": "u"},
    {"id": "SPY", "source": "yfinance", "question": "Will SPY be higher on {resolution_date} than on {forecast_due_date}?",
     "resolution_dates": ["2026-10-18", "2026-11-10"], "resolution_criteria": "rc", "url": "u"},
    {"id": ["a", "b"], "source": "acled", "question": "combo", "resolution_dates": ["2026-10-18"]},
]}


class ForecastBenchTest(unittest.TestCase):
    def test_combination_questions_dropped(self):
        self.assertEqual([q["id"] for q in fb.questions_of(QSET)], ["m1", "SPY"])

    def test_sample_splits_market_and_dataset(self):
        qs = [{"source": "manifold", "id": f"m{i}"} for i in range(10)] + \
             [{"source": "fred", "id": f"d{i}", "resolution_dates": ["2026-10-04"]} for i in range(10)]
        got = fb.sample_of(qs, 6)
        self.assertEqual([q["id"] for q in got], ["m0", "m3", "m6", "d0", "d3", "d6"])
        self.assertEqual(len(fb.sample_of(qs[:2] + qs[10:], 6)), 6)  # few markets: dataset fills in

    def test_prompt(self):
        m, ds = fb.questions_of(QSET)
        pm = fb.build_prompt(m, "2026-10-11")
        self.assertIn("Value on 2026-10-01: 0.4", pm)
        self.assertIn('resolution_date "final"', pm)
        self.assertNotIn("Background", pm)                 # N/A fields omitted
        pd = fb.build_prompt(ds, "2026-10-11")
        self.assertIn("higher on the resolution date than on 2026-10-11", pd)
        self.assertIn("2026-10-18, 2026-11-10", pd)

    def test_prompt_keeps_a_zero_value(self):
        q = dict(QSET["questions"][0], freeze_datetime_value=0)
        self.assertIn("Value on 2026-10-01: 0 ", fb.build_prompt(q, "2026-10-11"))

    def _round(self, d):
        qpath = os.path.join(d, "qs.json")
        json.dump(QSET, open(qpath, "w"))
        return qpath, os.path.join(d, "round")

    def test_run_and_build(self):
        with tempfile.TemporaryDirectory() as d:
            qpath, root = self._round(d)
            pi = fake_pi(d)
            os.environ["FAKE_ALL"] = "1"
            try:
                os.environ["FAKE_P"] = "0.2"
                fb.main(["run", "--root", root, "--question-set", qpath, "--model", "a/one", "--pi", pi])
                os.environ["FAKE_P"] = "0.6"
                fb.main(["run", "--root", root, "--question-set", qpath, "--model", "b/two", "--pi", pi])
            finally:
                os.environ.pop("FAKE_ALL"); os.environ.pop("FAKE_P")
            rc = fb.main(["build", "--root", root, "--member", "a/one", "--member", "b/two",
                          "--name", "ensemble", "--model-org", "FRI", "--org", "Example Team", "--set-number", "3"])
            self.assertEqual(rc, 0)
            fs = json.load(open(os.path.join(root, "2026-10-11.example-team.3.json")))
            by = {(r["id"], r["resolution_date"]): r["forecast"] for r in fs["forecasts"]}
            self.assertEqual(set(by), {("m1", None), ("SPY", "2026-10-18"), ("SPY", "2026-11-10")})
            for v in by.values():
                self.assertAlmostEqual(v, 0.4)              # the mean of 0.2 and 0.6
            self.assertEqual(fb.validate(fs, QSET), [])

    def test_build_fails_below_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            qpath, root = self._round(d)
            fb.main(["run", "--root", root, "--question-set", qpath, "--model", "a/one", "--pi", fake_pi(d)])
            # the fake leaves the first key unanswered: neither question complete
            rc = fb.main(["build", "--root", root, "--member", "a/one", "--name", "x", "--model-org", "X", "--org", "Example Team", "--set-number", "1"])
            self.assertEqual(rc, 1)
            fs = json.load(open(os.path.join(root, "2026-10-11.example-team.1.json")))
            self.assertEqual([(r["id"], r["resolution_date"]) for r in fs["forecasts"]], [("SPY", "2026-11-10")])

    def test_resume_refuses_changed_settings(self):
        with tempfile.TemporaryDirectory() as d:
            qpath, root = self._round(d)
            fb.main(["run", "--root", root, "--question-set", qpath, "--model", "a/one", "--pi", fake_pi(d)])
            with self.assertRaises(SystemExit):
                fb.main(["run", "--root", root, "--question-set", qpath, "--model", "a/one",
                         "--min-research", "5", "--pi", fake_pi(d)])

    def test_member_spec(self):
        with tempfile.TemporaryDirectory() as d:
            qpath, root = self._round(d)
            fb.main(["run", "--root", root, "--question-set", qpath, "--model", "a/one", "--no-research",
                     "--thinking", "low", "--pi", fake_pi(d)])
            self.assertEqual(fb.main(["build", "--root", root, "--member", "a/one@low,noresearch", "--name", "x",
                                      "--model-org", "X", "--org", "Example Team", "--set-number", "1"]), 1)  # found; short coverage
            with self.assertRaises(SystemExit):
                fb.main(["build", "--root", root, "--member", "a/one", "--name", "x", "--model-org", "X", "--org", "Example Team", "--set-number", "1"])

    def test_an_airo_condition_is_the_baseline_loop_plus_its_instruction(self):
        from fri_forecaster import baseline
        from fri_forecaster.variants import VARIANTS
        with tempfile.TemporaryDirectory() as d:
            qpath, root = self._round(d)
            # a known provider needs its key set (harness.pi_env); the fake pi never uses it
            with unittest.mock.patch.dict(os.environ, {"FAKE_ALL": "1", "OPENAI_API_KEY": "unused"}):
                self.assertEqual(fb.main(["run", "--root", root, "--question-set", qpath, "--model", "openai/one",
                                          "--airo", "two-step", "--pi", fake_pi(d)]), 0)
            mdir = os.path.join(root, "members", "openai_one--xhigh--airo-two-step")   # openai's top level
            man = json.load(open(os.path.join(mdir, "manifest.json")))
            self.assertEqual((man["condition"], man["prompt_version"], man["thinking"], man["min_research"]),
                             ("two-step", fb.AIRO_PROMPT_VERSION, "xhigh", 0))
            call = os.path.join(mdir, "calls", "metaculus__m1", "attempt-1")
            self.assertEqual(open(os.path.join(call, "system.txt")).read(), baseline.SYSTEM)   # no system prompt
            prompt = open(os.path.join(call, "prompt.txt")).read()
            plain = fb.build_prompt(fb.questions_of(QSET)[0], "2026-10-11")
            head, _, delivery = plain.rpartition("\n")
            self.assertEqual(prompt, f"{head}\n{VARIANTS['two-step']}\n\n{delivery}")   # verbatim, before the delivery line
            spec = json.load(open(os.path.join(call, "spec.json")))
            self.assertEqual(list(spec["tools"]), ["web_search", "read_page", "submit_forecast"])  # one answer tool
            self.assertEqual(spec["tools"]["web_search"]["description"], baseline.WEB_SEARCH)
            self.assertEqual((spec["min_research"], spec["max_turns"]), (0, baseline.MAX_TURNS))
            self.assertEqual(fb.main(["build", "--root", root, "--member", "openai/one,airo-two-step", "--name", "x",
                                      "--org", "Example Team", "--set-number", "1"]), 0)

    def test_airo_none_adds_nothing_and_other_settings_are_refused(self):
        q = fb.questions_of(QSET)[0]
        self.assertEqual(fb.airo_prompt(q, "2026-10-11", "none"), fb.build_prompt(q, "2026-10-11"))
        with tempfile.TemporaryDirectory() as d:
            qpath, root = self._round(d)
            for extra in (["--thinking", "high"], ["--no-research"]):   # not the Baseline loop
                with self.assertRaises(SystemExit):
                    fb.main(["run", "--root", root, "--question-set", qpath, "--model", "openai/one", "--airo", "none",
                             "--pi", fake_pi(d)] + extra)

    def test_a_short_member_makes_a_complete_set_not_ready(self):
        with tempfile.TemporaryDirectory() as d:
            qpath, root = self._round(d)
            pi = fake_pi(d)
            os.environ["FAKE_ALL"] = "1"
            try:
                self.assertEqual(fb.main(["run", "--root", root, "--question-set", qpath, "--model", "a/one", "--pi", pi]), 0)
            finally:
                os.environ.pop("FAKE_ALL")
            # b/two leaves the first key of each question unanswered: short, exit 1
            self.assertEqual(fb.main(["run", "--root", root, "--question-set", qpath, "--model", "b/two", "--pi", pi]), 1)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = fb.main(["build", "--root", root, "--member", "a/one", "--member", "b/two", "--name", "x",
                              "--org", "Example Team", "--set-number", "1"])
            self.assertEqual(rc, 1)                                   # every cell has a forecast, from a/one alone
            self.assertIn("market: 1/1 complete", out.getvalue())
            self.assertIn("SHORT MEMBER b_two--high--research: market 0/1, dataset 0/1", out.getvalue())
            self.assertIn("NOT READY TO UPLOAD: 1 member(s) below 95%", out.getvalue())
            prov = json.load(open(os.path.join(root, "2026-10-11.example-team.1.json.provenance.json")))
            self.assertEqual(prov["member_coverage"]["a_one--high--research"], {"market": [1, 1], "dataset": [1, 1]})

    def test_a_refused_key_stops_the_member_without_retries(self):
        refused = '401 {"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}'
        self.assertTrue(harness.auth_error({"api_error": refused}))
        self.assertFalse(harness.auth_error({"api_error": "429 rate limit"}))
        self.assertFalse(harness.auth_error({"api_error": None}))
        with tempfile.TemporaryDirectory() as d:
            qpath, root = self._round(d)
            os.environ["FAKE_API_ERROR"] = refused
            try:   # a retry would wait harness.RETRY_BACKOFF seconds: this returns at once
                rc = fb.main(["run", "--root", root, "--question-set", qpath, "--model", "a/one", "--workers", "1",
                              "--pi", fake_pi(d)])
            finally:
                os.environ.pop("FAKE_API_ERROR")
            self.assertEqual(rc, 2)
            mdir = os.path.join(root, "members", "a_one--high--research")
            self.assertFalse(os.path.exists(os.path.join(mdir, "results.jsonl")))      # nothing to resume around
            calls = os.path.join(mdir, "calls")                                        # a call under way may finish:
            self.assertEqual({tuple(os.listdir(os.path.join(calls, c))) for c in os.listdir(calls)}, {("attempt-1",)})  # none is retried

    def test_torn_results_line_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.jsonl")
            open(p, "w").write(json.dumps({"id": "a", "source": "s", "probabilities": {"x": 0.1}, "wanted": ["x"]}) + "\n{\"id\": \"b")
            self.assertEqual(list(fb.read_results(p)), [("s", "a")])

EXAMPLE_REGISTRY = os.path.join(os.path.dirname(__file__), "..", "examples", "names.example.json")


class NamesTest(unittest.TestCase):
    def setUp(self):
        from forecastbench import names
        self.names, self.reg = names, names.load(EXAMPLE_REGISTRY)

    def test_registered_names_match_the_code(self):
        for ch in self.reg["conditions"]:
            name = self.names.current(self.reg, ch)
            self.assertEqual(name, name.lower())
            self.assertTrue(name.startswith(ch + "-"))

    def test_drift_is_refused_and_points_to_the_next_place(self):
        import copy
        reg = copy.deepcopy(self.reg)
        reg["names"]["solo-oak"]["members"][0]["options"]["thinking"] = "medium"
        with self.assertRaises(SystemExit) as e:
            self.names.current(reg, "solo")
        self.assertIn("solo-elm", str(e.exception))

    def test_member_specs(self):
        self.assertEqual(self.names.member_specs(self.reg, "solo"), ["anthropic/claude-opus-5-5@high,research"])
        self.assertTrue(all(s.endswith(",noresearch") for s in self.names.member_specs(self.reg, "unaided")))

    def test_places_unique(self):
        self.assertEqual(len(self.reg["places"]), len(set(self.reg["places"])))

    def test_an_entry_with_prompts_runs_every_member_under_each(self):
        specs = self.names.member_specs(self.reg, "pooled")
        self.assertEqual(len(specs), 4 * 5)
        self.assertEqual(specs[0], "anthropic/claude-opus-5-5@max,airo-none")          # each model's top level
        self.assertEqual(specs[-1], "anthropic/claude-sonnet-5-5@max,airo-two-step")
        self.assertIn("openai/gpt-6-astra@xhigh,airo-critical", specs)

    def test_an_instruction_is_part_of_the_fingerprint(self):
        from fri_forecaster import variants
        old = variants.VARIANTS["recent"]
        variants.VARIANTS["recent"] = old + " And cite them."
        try:
            with self.assertRaises(SystemExit):
                self.names.current(self.reg, "pooled")
            self.names.current(self.reg, "ensemble")       # the ForecastBench prompt's names do not move
        finally:
            variants.VARIANTS["recent"] = old

    def test_submitted_and_public_conditions(self):
        self.assertEqual(self.names.submitted(self.reg), ["ensemble", "solo", "pooled"])   # unaided only runs
        self.assertEqual(self.names.public_of(self.reg), ["ensemble"])

    def test_forecastbench_limits_are_refused(self):
        import copy
        four = copy.deepcopy(self.reg)
        four["conditions"]["unaided"].pop("submit")
        with self.assertRaises(SystemExit) as e:
            self.names.submitted(four)
        self.assertIn("at most 3 sets", str(e.exception))
        two_public = copy.deepcopy(self.reg)
        two_public["conditions"]["solo"]["public"] = True
        with self.assertRaises(SystemExit):
            self.names.submitted(two_public)


class SyncTest(unittest.TestCase):
    """names.sync: the registry follows the panel (members and code) with no hand step."""

    def setUp(self):
        import copy
        from forecastbench import names
        self.names = names
        self.reg = copy.deepcopy(names.load(EXAMPLE_REGISTRY))
        self.have = [m["eci_name"] for m in self.reg["names"]["ensemble-oak"]["members"]]
        self.panel = [(m["eci_name"], m["pi_model"], m["lab"]) for m in self.reg["names"]["ensemble-oak"]["members"]]
        self.panel.append(("GPT-5.5 Pro", "openai/gpt-5.5-pro", "OpenAI"))

    def lines(self, panel):
        return ["\t".join(p) + "\n" for p in panel]

    def test_unchanged_panel_keeps_every_name(self):
        import copy
        before = copy.deepcopy(self.reg)
        panel = self.names.parse_panel(self.lines(self.panel))
        for cond in self.reg["conditions"]:
            name, note = self.names.sync(self.reg, cond, panel)
            self.assertEqual(name, f"{cond}-oak")
            self.assertIn("code unchanged", note)
        self.assertEqual(self.reg, before)

    def test_a_moved_top_n_registers_the_next_place_for_each_condition(self):
        newcomer = ("Claude Fable 5.1", "anthropic/claude-fable-5-1", "Anthropic")
        panel = self.names.parse_panel(self.lines(self.panel[:3] + [newcomer] + self.panel[3:]))
        self.assertEqual(self.names.sync(self.reg, "ensemble", panel, today="2026-10-19")[0], "ensemble-elm")
        self.assertEqual(self.names.sync(self.reg, "unaided", panel)[0], "unaided-elm")
        self.assertEqual(self.names.sync(self.reg, "solo", panel)[0], "solo-oak")       # the top model is the same
        e = self.reg["names"]["ensemble-elm"]
        self.assertEqual(self.names.current(self.reg, "ensemble"), "ensemble-elm")    # its fingerprint matches the code
        self.assertEqual([m["eci_name"] for m in e["members"]], self.have[:3] + ["Claude Fable 5.1"])
        new = e["members"][3]
        self.assertEqual((new["pi_model"], new["model_key"], new["provider"], new["provider_model_id"], new["lab"]),
                         ("anthropic/claude-fable-5-1", "claude-fable-5-1", "anthropic", "claude-fable-5-1", "Anthropic"))
        self.assertEqual(new["options"], e["members"][0]["options"])                   # the condition's options
        self.assertEqual(new["one_shot_baseline"], None)                               # unknown for a newcomer
        for i in range(3):                                                             # kept for the models it already knew,
            self.assertEqual(e["members"][i]["one_shot_baseline"],                     # from the research entries, not unaided's None
                             self.reg["names"]["ensemble-oak"]["members"][i]["one_shot_baseline"])
            self.assertIsNotNone(e["members"][i]["one_shot_baseline"])
        self.assertEqual(self.reg["names"]["unaided-elm"]["members"][3]["options"]["tools"], ["submit_forecast"])
        self.assertEqual([m["one_shot_baseline"] for m in self.reg["names"]["unaided-elm"]["members"]],   # a no-research
                         [m["one_shot_baseline"] for m in self.reg["names"]["unaided-oak"]["members"][:3]] + [None])  # entry's own
        self.assertEqual(e["reason"], "sync 2026-10-19: members " + ", ".join(self.have) + " -> " +
                         ", ".join(self.have[:3] + ["Claude Fable 5.1"]))
        self.assertEqual(self.reg["names"]["ensemble-oak"]["members"][3]["eci_name"], self.have[3])  # never edited
        self.assertEqual(self.names.member_specs(self.reg, "ensemble")[3], "anthropic/claude-fable-5-1@high,research")
        self.assertEqual(self.names.sync(self.reg, "pooled", panel)[0], "pooled-elm")
        p = self.reg["names"]["pooled-elm"]
        self.assertEqual(p["prompts"], self.reg["names"]["pooled-oak"]["prompts"])     # the same five prompts
        self.assertEqual(p["harness"]["prompt_version"], fb.AIRO_PROMPT_VERSION)
        self.assertEqual(p["members"][3]["options"]["thinking"], "max")                # Anthropic's top level, not a copy
        self.assertEqual(p["members"][1]["options"]["thinking"], "xhigh")
        self.assertEqual(self.names.current(self.reg, "pooled"), "pooled-elm")
        self.assertEqual(self.names.member_specs(self.reg, "pooled")[3], "anthropic/claude-fable-5-1@max,airo-none")

    def test_names_alone_cannot_register_so_the_current_name_is_kept_with_a_warning(self):
        panel = self.names.parse_panel([f"{n}\n" for n in self.have[:3] + ["Claude Fable 5.1"]])
        name, note = self.names.sync(self.reg, "ensemble", panel)
        self.assertEqual(name, "ensemble-oak")
        self.assertTrue(note.startswith("WARNING"))
        self.assertIn("Claude Fable 5.1", note)
        self.assertNotIn("ensemble-elm", self.reg["names"])

    def test_code_drift_registers_the_next_place_with_the_same_members(self):
        self.reg["names"]["solo-oak"]["fingerprint"] = "0000000000000000"
        panel = self.names.parse_panel(self.lines(self.panel))
        name, note = self.names.sync(self.reg, "solo", panel)
        self.assertEqual(name, "solo-elm")
        self.assertIn("fingerprint", note)
        self.assertEqual(self.reg["names"]["solo-elm"]["members"], self.reg["names"]["solo-oak"]["members"])
        self.assertEqual(self.names.current(self.reg, "solo"), "solo-elm")

    def test_cli_saves_unless_dry_run(self):
        import io
        import shutil
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "names.json")
            shutil.copy(EXAMPLE_REGISTRY, path)
            os.environ["FORECASTER_NAMES"] = path
            try:
                moved = self.lines(self.panel[:3] + [("Claude Fable 5.1", "anthropic/claude-fable-5-1", "Anthropic")])
                self.names.main(["sync", "--dry-run"], stdin=io.StringIO("".join(moved)))
                self.assertEqual(json.load(open(path))["conditions"]["ensemble"]["current"], "ensemble-oak")
                self.names.main(["sync"], stdin=io.StringIO("".join(moved)))
                reg = json.load(open(path))
                self.assertEqual(reg["conditions"]["ensemble"]["current"], "ensemble-elm")
                self.assertEqual(reg["conditions"]["solo"]["current"], "solo-oak")
                self.assertFalse(os.path.exists(path + ".tmp"))
            finally:
                os.environ.pop("FORECASTER_NAMES")



if __name__ == "__main__":
    unittest.main()
