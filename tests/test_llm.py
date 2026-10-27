"""Guard the two modules vendored out of xrisk-canaries on 2026-08-28.

They arrived here as the acquisition half of the pipeline (redlines/llm.py,
redlines/tools.py) so that a fresh clone can RE-ELICIT and not merely rebuild.
Nothing tested them before the move: they lived in a private sibling checkout
that this repo reached into over sys.path.

load_keys() is the piece worth pinning: it replaced an upstream one that read
GCP Secret Manager through a hardcoded macOS path, and it has to agree with
`set -a; . file` on the SAME env file, because code/cron_run.sh sources that
file with the shell before running us and the two must not drift. The loop
itself is pi's (redlines/pi_loop.py; tests/test_pi_loop.py), since the litellm
loop left on 2026-10-22.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from redlines import llm, tools  # noqa: E402


class TestTools(unittest.TestCase):
    def test_forecast_tools_are_the_two_grounding_tools(self):
        """Search and read, nothing else: the Metaculus lookup left on 2026-09-02
        (redlines/tools.py says why), and a runner that still named it in a
        prompt would be asking for a tool the loop cannot serve."""
        self.assertEqual([t["name"] for t in tools.FORECAST_TOOLS],
                         ["web_search", "read_page"])
        for t in tools.FORECAST_TOOLS:
            self.assertTrue(callable(t["fn"]))
            self.assertIn("parameters", t)
        self.assertFalse(hasattr(tools, "metaculus_lookup"))
        self.assertNotIn("METACULUS_API_KEY", llm.PROVIDER_KEYS)

    def test_runner_prompts_name_only_tools_the_loop_serves(self):
        import importlib.util
        names = {t["name"] for t in tools.FORECAST_TOOLS}
        for runner in ("run_unified",):
            spec = importlib.util.spec_from_file_location(runner, REPO / "code" / f"{runner}.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for text in (mod.SYSTEM, mod.PROMPT):
                self.assertNotIn("metaculus", text.lower(), runner)
            for name in names:
                self.assertIn(name, mod.SYSTEM, f"{runner}: SYSTEM does not offer {name}")

    def test_recent_days_bounds_the_news_index_by_exact_dates(self):
        """Probed 2026-09-02: exact dates filter on Tavily's news index and not
        on the general one. So recent_days means news + start/end, and no
        recent_days means the general index with no date at all."""
        from datetime import date
        b = tools.search_body("q", 5, recent_days=90, today=date(2026, 9, 2))
        self.assertEqual((b["topic"], b["start_date"], b["end_date"]), ("news", "2026-06-04", "2026-09-02"))
        b = tools.search_body("q", 5)
        self.assertNotIn("topic", b)
        self.assertNotIn("start_date", b)
        self.assertIn("recent_days", tools.WEB_SEARCH_TOOL["parameters"]["properties"])

    def test_prompt_states_the_floor_but_no_maximum(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("ru", REPO / "code" / "run_unified.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertIn(str(mod.MIN_RESEARCH), mod.SYSTEM)
        self.assertNotIn(str(mod.MAX_ROUNDS), mod.SYSTEM)
        self.assertNotIn("rounds of tool calls", mod.SYSTEM)
        self.assertIn("recent_days", mod.SYSTEM)

    def test_research_tools_narrow_cause_to_the_batch_groups(self):
        """The forecasting run's web_search carries `cause` as a required enum
        of the batch's group keys and the loop's coverage keys are the same
        list; the shared tool definition stays generic and optional."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("ru", REPO / "code" / "run_unified.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        groups = [{"key": "ai", "label": "AI-related incident"},
                  {"key": "crosscutting", "label": "Cross-cutting"}]
        research, keys = mod.research_tools(groups)
        cause = research[0]["parameters"]["properties"]["cause"]
        self.assertEqual(keys, ["ai", "crosscutting"])
        self.assertEqual(cause["enum"], keys)
        self.assertIn("AI-related incident", cause["description"])
        self.assertEqual(research[0]["parameters"]["required"], ["query", "cause"])
        self.assertIs(research[0]["fn"], tools.web_search)
        self.assertEqual(research[1:], tools.FORECAST_TOOLS[1:])
        self.assertNotIn("enum", tools.WEB_SEARCH_TOOL["parameters"]["properties"]["cause"])
        self.assertEqual(tools.WEB_SEARCH_TOOL["parameters"]["required"], ["query"])
        self.assertIn("cause", mod.SYSTEM)
        self.assertEqual(mod.coverage_line([{"evidence": [
            {"tool": "web_search", "args": {"query": "q", "cause": "ai", "recent_days": 30}, "result": {}},
            {"tool": "web_search", "args": {"query": "q", "cause": "bio"}, "result": {}}]}]),
            "coverage ai:1")

    def test_read_page_degrades_without_a_key(self):
        """Same contract as web_search: no key -> an {error} result, never a raise,
        so the loop carries on ungrounded and the runner's TAVILY guard is the
        thing that stops that from being published."""
        saved = os.environ.pop("TAVILY_API_KEY", None)
        try:
            r = tools.read_page("https://example.org/")
        finally:
            if saved is not None:
                os.environ["TAVILY_API_KEY"] = saved
        self.assertIn("error", r)
        self.assertEqual(r["text"], "")

    def test_read_page_windows_a_long_page(self):
        """A page longer than PAGE_CHARS comes back in windows the model can page
        through with `offset`; the loop caps a tool reply at 8000 characters,
        so a window plus its envelope must fit."""
        import json as _json
        import urllib.request as _ur
        long_text = "x" * (tools.PAGE_CHARS * 2 + 10)

        class _Resp:
            def __init__(self, payload):
                self._p = payload
            def read(self):
                return _json.dumps(self._p).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            return _Resp({"results": [{"url": "u", "raw_content": long_text}],
                          "failed_results": []})

        os.environ["TAVILY_API_KEY"] = "t"
        real = _ur.urlopen
        _ur.urlopen = fake_urlopen
        try:
            first = tools.read_page("u")
            second = tools.read_page("u", offset=first["next_offset"])
            last = tools.read_page("u", offset=second["next_offset"])
        finally:
            _ur.urlopen = real
            os.environ.pop("TAVILY_API_KEY", None)
        self.assertEqual(len(first["text"]), tools.PAGE_CHARS)
        self.assertEqual(first["total_chars"], len(long_text))
        self.assertEqual(second["offset"], tools.PAGE_CHARS)
        self.assertNotIn("next_offset", last)
        self.assertEqual(len(_json.dumps(first)), len(_json.dumps(first)))
        self.assertLess(len(_json.dumps(first)), 8000)

    def test_web_search_echoes_cause_and_never_sends_it(self):
        self.assertNotIn("cause", tools.search_body("q", recent_days=7))
        out = tools.web_search("q", recent_days=7, cause="bio")   # no key: an {error} result
        self.assertEqual(out["cause"], "bio")
        self.assertIn("error", out)
        self.assertNotIn("cause", tools.web_search("q"))


class TestLoadKeys(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        for k in llm.PROVIDER_KEYS + ("REDLINES_ENV_FILE",):
            os.environ.pop(k, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def _write(self, text):
        import tempfile
        p = Path(tempfile.mkdtemp()) / "env"
        p.write_text(text)
        os.environ["REDLINES_ENV_FILE"] = str(p)
        return p

    def test_parses_the_shapes_the_shell_accepts(self):
        self._write('# a comment\n\nexport TAVILY_API_KEY=tav-123\n'
                    'OPENAI_API_KEY="oa-456"\nXAI_API_KEY=\'xa-789\'\nJUNK\n')
        got = llm.load_keys()
        self.assertEqual(os.environ["TAVILY_API_KEY"], "tav-123")
        self.assertEqual(os.environ["OPENAI_API_KEY"], "oa-456")
        self.assertEqual(os.environ["XAI_API_KEY"], "xa-789")
        self.assertEqual(got, ["OPENAI_API_KEY", "TAVILY_API_KEY", "XAI_API_KEY"])

    def test_agrees_with_the_shell_on_the_same_file(self):
        """cron_run.sh does `set -a; . "$ENVFILE"` and then runs us; if these two
        parsers disagreed, a key would mean one thing to the cron and another to a
        hand-run of the same command."""
        p = self._write('export TAVILY_API_KEY=tav-123\nOPENAI_API_KEY="oa-456"\n'
                        "XAI_API_KEY='xa-789'\n")
        llm.load_keys()
        r = subprocess.run(
            ["bash", "-c", f'set -a; . "{p}"; set +a; '
                           'echo "$TAVILY_API_KEY|$OPENAI_API_KEY|$XAI_API_KEY"'],
            capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(),
                         "|".join(os.environ[k] for k in
                                  ("TAVILY_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY")))

    def test_environment_beats_the_file(self):
        """cron_run.sh has already sourced the file by the time we run. An
        override on the command line has to survive that."""
        self._write("TAVILY_API_KEY=from-file\n")
        os.environ["TAVILY_API_KEY"] = "from-env"
        llm.load_keys()
        self.assertEqual(os.environ["TAVILY_API_KEY"], "from-env")

    def test_missing_file_is_not_an_error(self):
        """Best-effort by design: a caller that needs a specific key checks for it
        itself (run_unified.py refuses to start without TAVILY_API_KEY)."""
        os.environ["REDLINES_ENV_FILE"] = "/nonexistent/redlines/env"
        self.assertEqual(llm.load_keys(), [])


class TestReasoningLevel(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("REDLINES_REASONING", None)

    def tearDown(self):
        os.environ.pop("REDLINES_REASONING", None)
        if self._saved is not None:
            os.environ["REDLINES_REASONING"] = self._saved

    def test_top_rung_per_provider_family(self):
        self.assertEqual(llm.reasoning_for("anthropic/claude-fable-5"), "max")
        self.assertEqual(llm.reasoning_for("openai/gpt-5.6-sol"), "xhigh")
        self.assertEqual(llm.reasoning_for("gemini/gemini-3.1-pro-preview"), llm.REASONING_DEFAULT)

    def test_override_and_none(self):
        os.environ["REDLINES_REASONING"] = "low"
        self.assertEqual(llm.reasoning_for("anthropic/claude-fable-5"), "low")
        os.environ["REDLINES_REASONING"] = "none"
        self.assertIsNone(llm.reasoning_for("anthropic/claude-fable-5"))



class TestResearchCoverage(unittest.TestCase):
    def test_counts_recent_window_searches_per_group(self):
        """Only a search tagged with a group AND a window counts."""
        ev = [{"tool": "web_search", "args": {"query": "a", "cause": "ai", "recent_days": 30}},
              {"tool": "web_search", "args": {"query": "b", "cause": "bio"}},
              {"tool": "web_search", "args": {"query": "c", "cause": "bio", "recent_days": 7}},
              {"tool": "read_page", "args": {"url": "https://example.org"}},
              {"tool": "web_search", "args": {"query": "d", "cause": "ai", "recent_days": 14}}]
        self.assertEqual(llm.research_coverage(ev), {"ai": 2, "bio": 1})
        self.assertEqual(llm.research_coverage(None), {})
