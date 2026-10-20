"""fri_forecaster: the shared pi harness and the ForecastBench driver, against a
fake `pi` (no network, no spend)."""
import json
import os
import stat
import sys
import tempfile
import textwrap
import unittest

from fri_forecaster import forecastbench as fb
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


class HarnessTest(unittest.TestCase):
    def test_run_merges_pieces_and_final(self):
        with tempfile.TemporaryDirectory() as d:
            res = harness.run(model="m/x", system="S", prompt="P", workdir=os.path.join(d, "w"),
                              cell_schema=SCHEMA, key_fields=["k"], allowed_keys=["a", "b", "c"],
                              tool_descriptions=DESC, pi=fake_pi(d))
            self.assertEqual(res["rc"], 0)
            self.assertEqual(open(os.path.join(res["workdir"], "stdin.txt")).read(), "P")   # the prompt, on stdin
            self.assertEqual(res["cells"]["a"]["probability"], 0.1)   # from a piece
            self.assertEqual(res["cells"]["c"]["probability"], 0.3)   # from the final
            self.assertIsNone(res["usage"]["api_error"])
            self.assertEqual(os.listdir(os.path.join(d, "w")), ["attempt-1"])   # one call, no retry
            self.assertNotIn("bogus", res["cells"])                   # pieces filtered to allowed keys
            self.assertEqual(res["delivery"], {"cells_calls": 1, "cells_in_pieces": 1, "cells_in_final": 2})
            self.assertEqual(len(res["evidence"]), 2)                 # submit tools are not evidence
            self.assertEqual(res["evidence"][0]["args"], {"query": "q"})   # args joined from the start event
            self.assertEqual(res["evidence"][1]["error"], "page read failed")
            self.assertEqual((res["usage"]["research_ok"], res["usage"]["research_failed"]), (1, 1))
            self.assertTrue(res["workdir"].endswith("attempt-1"))
            u = res["usage"]
            self.assertEqual((u["turns"], u["input_tokens"], u["output_tokens"], u["cached_tokens"]), (2, 11, 6, 2))
            self.assertAlmostEqual(u["cost_usd"], 0.03)
            self.assertEqual(res["answer"]["rationale"], "because")

    def test_retry_gets_a_fresh_attempt(self):
        """A second call never reads the first call's final.json."""
        with tempfile.TemporaryDirectory() as d:
            kw = dict(model="m/x", system="S", prompt="P", workdir=os.path.join(d, "w"), cell_schema=SCHEMA,
                      key_fields=["k"], allowed_keys=["a", "b"], tool_descriptions=DESC)
            harness.run(pi=fake_pi(d), **kw)
            broken = os.path.join(d, "broken")
            open(broken, "w").write("#!/bin/sh\nexit 1\n")
            os.chmod(broken, 0o755)
            res = harness.run(pi=broken, **kw)
            self.assertTrue(res["workdir"].endswith("attempt-2"))
            self.assertEqual(res["cells"], {})
            self.assertEqual(res["answer"], {})

    def test_final_cells_outside_allowed_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            json.dump({"answer": {"forecasts": [{"k": "a", "probability": 0.2}, {"k": "zzz", "probability": 0.9}]}},
                      open(os.path.join(d, "final.json"), "w"))
            cells, _, _ = harness.collect(d, ["k"], ["a"])
            self.assertEqual(list(cells), ["a"])

    def test_spec_offers_only_requested_tools(self):
        with tempfile.TemporaryDirectory() as d:
            spec = harness.write_spec(d, cell_schema=SCHEMA, key_fields=["k"], allowed_keys=["a"],
                                      tool_descriptions={"submit_forecast": "f"}, research_tools=(),
                                      cells_tool=False)
            self.assertEqual(list(spec["tools"]), ["submit_forecast"])
            self.assertEqual(spec["research_tools"], [])

    def test_command_loads_extension_without_builtins(self):
        cmd = harness.pi_command("m/x", "/w/system.txt", thinking="max", pi="pi")
        for flag in ("--no-builtin-tools", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-context-files"):
            self.assertIn(flag, cmd)
        self.assertEqual(harness.pi_command("m/x", "S", pi="/x/cli.js")[:2], ["node", "/x/cli.js"])
        self.assertEqual(cmd[cmd.index("-e") + 1], harness.EXT)
        self.assertTrue(os.path.exists(harness.EXT))
        # No prompt text in argv: the prompt goes on stdin and the system
        # prompt in a file (harness.PROMPT_ON_STDIN).
        self.assertEqual(cmd[-2:], ["--system-prompt", "/w/system.txt"])
        self.assertTrue(harness.PROMPT_ON_STDIN)


    def test_a_provider_error_is_surfaced_and_retried_in_fresh_attempts(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["FAKE_API_ERROR"] = "400 You're out of extra usage"
            backoff, harness.RETRY_BACKOFF = harness.RETRY_BACKOFF, 0
            try:
                res = harness.run(model="m/x", system="S", prompt="P", workdir=os.path.join(d, "w"),
                                  cell_schema=SCHEMA, key_fields=["k"], allowed_keys=["a"],
                                  tool_descriptions=DESC, pi=fake_pi(d), retries=2)
            finally:
                os.environ.pop("FAKE_API_ERROR")
                harness.RETRY_BACKOFF = backoff
            self.assertEqual(res["cells"], {})
            self.assertEqual(res["rc"], 0)                                         # pi exits 0 on a provider error
            self.assertIn("out of extra usage", res["usage"]["api_error"])
            self.assertEqual(sorted(os.listdir(os.path.join(d, "w"))), ["attempt-1", "attempt-2", "attempt-3"])
            self.assertTrue(res["workdir"].endswith("attempt-3"))

    def test_pi_is_billed_to_api_keys_only(self):
        kw = dict(system="S", prompt="P", cell_schema=SCHEMA, key_fields=["k"], allowed_keys=["a"], tool_descriptions=DESC)
        with tempfile.TemporaryDirectory() as d:
            saved = {k: os.environ.pop(k, None) for k in ("PI_CODING_AGENT_DIR", "ANTHROPIC_API_KEY") + harness.LOGIN_TOKENS}
            os.environ.update(ANTHROPIC_AUTH_TOKEN="bearer", ANTHROPIC_OAUTH_TOKEN="oauth", ANTHROPIC_API_KEY="sk-test")
            try:
                res = harness.run(model="anthropic/x", workdir=os.path.join(d, "w1"), pi=fake_pi(d), **kw)
                seen = json.load(open(os.path.join(res["workdir"], "env.json")))
                self.assertEqual(seen, {"PI_CODING_AGENT_DIR": harness.AGENT_DIR, "ANTHROPIC_AUTH_TOKEN": None,
                                        "ANTHROPIC_OAUTH_TOKEN": None, "ANTHROPIC_API_KEY": "sk-test"})
                self.assertFalse(os.path.exists(os.path.join(harness.AGENT_DIR, "auth.json")))
                # the caller's agent directory is honoured ...
                agent = os.path.join(d, "agent")
                res = harness.run(model="anthropic/x", workdir=os.path.join(d, "w2"), pi=fake_pi(d),
                                  env={"PI_CODING_AGENT_DIR": agent}, **kw)
                self.assertEqual(json.load(open(os.path.join(res["workdir"], "env.json")))["PI_CODING_AGENT_DIR"], agent)
                # ... unless it holds a login
                json.dump({"anthropic": {"type": "oauth", "access": "a", "refresh": "r"}, "openai": {"type": "api_key", "key": "k"}},
                          open(os.path.join(agent, "auth.json"), "w"))
                with self.assertRaises(RuntimeError) as e:
                    harness.run(model="anthropic/x", workdir=os.path.join(d, "w3"), pi=fake_pi(d),
                                env={"PI_CODING_AGENT_DIR": agent}, **kw)
                self.assertIn("login for anthropic", str(e.exception))
                # and the provider's key must be there, before anything is written
                with self.assertRaises(RuntimeError) as e:
                    harness.run(model="anthropic/x", workdir=os.path.join(d, "w4"), pi=fake_pi(d),
                                env={"ANTHROPIC_API_KEY": ""}, **kw)
                self.assertIn("ANTHROPIC_API_KEY is not set", str(e.exception))
                self.assertFalse(os.path.exists(os.path.join(d, "w3")))
                self.assertFalse(os.path.exists(os.path.join(d, "w4")))
                harness.run(model="unknown-provider/x", workdir=os.path.join(d, "w5"), pi=fake_pi(d), **kw)   # no rule, no check
            finally:
                for k, v in saved.items():
                    os.environ.pop(k, None)
                    if v is not None:
                        os.environ[k] = v


QSET = {"forecast_due_date": "2026-10-11", "question_set": "2026-10-11-llm.json", "questions": [
    {"id": "m1", "source": "metaculus", "question": "Will X happen?", "resolution_dates": "N/A",
     "background": "N/A", "freeze_datetime_value": "0.4", "freeze_datetime": "2026-10-01T00:00:00+00:00",
     "freeze_datetime_value_explanation": "The market value.", "resolution_criteria": "rc", "url": "u"},
    {"id": "SPY", "source": "yfinance", "question": "Will SPY be higher on {resolution_date} than on {forecast_due_date}?",
     "resolution_dates": ["2026-10-18", "2026-11-10"], "resolution_criteria": "rc", "url": "u"},
    {"id": ["a", "b"], "source": "acled", "question": "combo", "resolution_dates": ["2026-10-18"]},
]}


class ToolCliTest(unittest.TestCase):
    def test_retries_on_429_only(self):
        from fri_forecaster import tool_cli
        out = iter([{"error": "web search failed: HTTP Error 429: Too Many Requests"}, {"results": []}])
        waits = []
        self.assertEqual(tool_cli.call(lambda **a: next(out), {}, sleep=waits.append), {"results": []})
        self.assertEqual(len(waits), 1)
        waits.clear()
        self.assertEqual(tool_cli.call(lambda **a: {"error": "page read failed: 404"}, {}, sleep=waits.append),
                         {"error": "page read failed: 404"})
        self.assertEqual(waits, [])


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

    def test_torn_results_line_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.jsonl")
            open(p, "w").write(json.dumps({"id": "a", "source": "s", "probabilities": {"x": 0.1}, "wanted": ["x"]}) + "\n{\"id\": \"b")
            self.assertEqual(list(fb.read_results(p)), [("s", "a")])

if __name__ == "__main__":
    unittest.main()


EXAMPLE_REGISTRY = os.path.join(os.path.dirname(__file__), "..", "examples", "names.example.json")


class NamesTest(unittest.TestCase):
    def setUp(self):
        from fri_forecaster import names
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


class SyncTest(unittest.TestCase):
    """names.sync: the registry follows the panel (members and code) with no hand step."""

    def setUp(self):
        import copy
        from fri_forecaster import names
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
