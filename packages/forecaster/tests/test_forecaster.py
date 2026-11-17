"""fri_forecaster: the shared pi harness, against a fake `pi` (no network, no spend)."""
import json
import os
import stat
import sys
import tempfile
import textwrap
import unittest
import unittest.mock

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


if __name__ == "__main__":
    unittest.main()
