"""Offline checks for the user-authored shadow prompt and pinned news reader."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from redlines import experiments, news_shadow, recent_news
from tests.test_recent_news import FEEDS, FakeJev, fake_get, fake_resolve

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("news_shadow_runner", ROOT / "code/run_unified.py")
ru = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ru)
CONDITION = experiments.load("recent-shadow-noairo")["conditions"]["recent-shadow-noairo"]


class Shadow(unittest.TestCase):
    def test_exact_prompt_addition(self):
        groups, batch, horizons, _, instrument = ru.load_batch(ru.LADDER, ru.CROSS, ru.UNBATCHED)
        policies = ru.load_policies(ru.COMBINED)
        from datetime import date
        prompt, _, _ = ru.build_prompt_joint(groups, batch, horizons, instrument,
                                              policies["conditions"], policies, date(2026, 10, 13))
        baseline = ru.minimal_joint_prompt(prompt, "recent")
        actual = ru.condition_prompt(prompt, CONDITION)
        expected = baseline.replace(experiments.VARIANTS["recent"], experiments.VARIANTS["recent"] +
            "\n\nFor convenience, some relevant recent news stories are provided in file:///news/recent.json.\n\n" +
            experiments.VARIANTS["ai-banned"], 1)
        self.assertEqual(actual, expected)
        self.assertFalse(CONDITION["publish"])
        self.assertFalse(CONDITION["pooled"])
        self.assertEqual(CONDITION["cadence"], "manual")
        self.assertEqual(CONDITION["url_block_patterns"],
                         experiments.load("airo")["conditions"]["ai-banned"]["url_block_patterns"])

    def test_friday_condition_uses_normal_panel_and_has_no_turn_cap(self):
        from datetime import date
        exp = experiments.load("airo")
        c, baseline = exp["conditions"]["recent-shadow-noairo"], exp["conditions"]["recent"]
        for key in ("model_set", "repeats", "harness", "instrument", "scenarios"):
            self.assertEqual(c[key], baseline[key], key)
        self.assertEqual(c["max_turns"], 0)
        self.assertFalse(c["pooled"])
        self.assertFalse(c["publish"])
        self.assertIn(("airo", False, ["recent-shadow-noairo"]), experiments.due(date(2026, 10, 23)))
        self.assertNotIn(("airo", False, ["recent-shadow-noairo"]), experiments.due(date(2026, 10, 21)))
        self.assertEqual(c["sha256"], CONDITION["sha256"])

    def test_probe_recent_is_unmodified_but_unpublished(self):
        spec = importlib.util.spec_from_file_location("news_probe", ROOT / "code/probe_recent_news.py")
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        actual = probe.probe_condition("recent")
        expected = dict(experiments.load("airo")["conditions"]["recent"])
        expected.update(publish=False, pooled=False, cadence="manual")
        self.assertEqual(actual, expected)
        self.assertFalse(actual["news_cache"])
        self.assertIsNone(actual["url_block_patterns"])
        self.assertNotIn("_news_snapshot", actual)
        with self.assertRaisesRegex(ValueError, "requires --snapshot"):
            probe.probe_condition("recent-shadow-noairo")

    def test_old_condition_hashes_unchanged(self):
        for c in experiments.load("airo")["conditions"].values():
            if c["news_cache"]:
                continue
            old = {k: c[k] for k in experiments.DEFAULTS if k not in experiments.UNHASHED and k not in ("news_cache", "max_turns")}
            self.assertEqual(c["sha256"], hashlib.sha256(json.dumps(old, sort_keys=True).encode()).hexdigest())

    def prepare(self, folder):
        recent_news.poll(FEEDS, folder, get=fake_get, resolve=fake_resolve, now="2026-10-12T16:00:00Z")
        recent_news.run_reduce(folder, ask=FakeJev(), now="2026-10-12T16:05:00Z")
        return news_shadow.snapshot(folder, "2026-10-06", "2026-10-13", CONDITION["url_block_patterns"])

    def test_snapshot_guard_and_cutoff(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.prepare(folder)
            self.assertEqual(len(data["stories"]), 2)
            self.assertNotIn("screen", json.dumps(data))
            with self.assertRaises(ValueError):
                news_shadow.snapshot(folder, "2026-10-06", "2026-10-12T16:01:00Z", CONDITION["url_block_patterns"])
            guarded = news_shadow.snapshot(folder, "2026-10-06", "2026-10-13", "example-wire")
            self.assertNotIn("example-wire.test", json.dumps(guarded))
            path = Path(folder) / "input.json"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "guard"):
                news_shadow.pin(path, "different", Path(folder) / "pins")

    def test_reader_subprocess_pagination_and_tamper(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.prepare(folder)
            # Long synthetic summary exercises the existing read_page pagination.
            data["stories"][0]["reports"][0]["summary"] = "synthetic " * 1500
            path = Path(folder) / "input.json"
            path.write_text(json.dumps(data))
            pinned = news_shadow.pin(path, CONDITION["url_block_patterns"], Path(folder) / "pins")
            env = dict(os.environ, FORECASTER_NEWS_SNAPSHOT=pinned["path"], FORECASTER_NEWS_SHA256=pinned["sha256"])
            cli = ROOT / "packages/fri-forecaster/fri_forecaster/tool_cli.py"
            def read(offset=0):
                result = subprocess.run([sys.executable, str(cli), "read_page",
                    json.dumps({"url": news_shadow.URL, "offset": offset})], env=env,
                    capture_output=True, text=True, check=True)
                return json.loads(result.stdout)
            first = read()
            self.assertEqual(first["snapshot_sha256"], pinned["sha256"])
            self.assertEqual(first["next_offset"], 7000)
            second = read(7000)
            self.assertEqual(first["text"] + second["text"], path.read_text()[:14000])
            Path(pinned["path"]).write_text("modified")
            self.assertIn("error", read())

    def test_runner_stamps_snapshot_and_passes_guard_per_call(self):
        from datetime import date
        groups, batch, horizons, _, instrument = ru.load_batch(ru.LADDER, ru.CROSS, ru.UNBATCHED)
        policies = ru.load_policies(ru.COMBINED)
        condition = dict(CONDITION)
        seen = {}
        def fake(model, prompt, tools, final_tool, **kw):
            seen.update(kw)
            seen["names"] = [t["name"] for t in tools]
            cells = [{"question_id": q["id"], "horizon": h, "probabilities": {"unconditional": 0.01}}
                     for g in groups for q in batch[g["key"]] for h in horizons if h in q["horizons"]]
            return {"forecasts": cells, "rationale": "synthetic",
                    "eci_forecast": {"p10": 168, "p25": 170, "p50": 172, "p75": 175, "p90": 178}}, []
        with tempfile.TemporaryDirectory() as folder:
            data = self.prepare(folder)
            path = Path(folder) / "snapshot.json"
            path.write_text(json.dumps(data))
            condition["_news_snapshot"] = news_shadow.pin(path, condition["url_block_patterns"], Path(folder) / "pins")
            with patch.object(ru, "call_tools", fake):
                rows = ru.run_one_joint("fake", "fake/model", groups, batch, horizons, "test", 0,
                    instrument, [], policies, condition, "recent-shadow-noairo", today=date(2026, 10, 13))
            self.assertEqual(seen["env"][news_shadow.HASH_ENV], condition["_news_snapshot"]["sha256"])
            self.assertEqual(seen["env"][ru.BLOCK_ENV], condition["url_block_patterns"])
            self.assertEqual(seen["names"], ["web_search", "read_page"])
            self.assertEqual(seen["max_iters"], 0)
            self.assertTrue(all(r["news_snapshot"]["sha256"] == condition["_news_snapshot"]["sha256"] for r in rows))
            self.assertTrue(all(r["pooled"] is False for r in rows))
            self.assertNotIn("path", rows[0]["news_snapshot"])

    def test_scheduled_preparation_is_fresh_and_never_falls_back(self):
        from datetime import datetime, timezone
        spec = importlib.util.spec_from_file_location("prepare_news", ROOT / "code/prepare_recent_news.py")
        prep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prep)
        with tempfile.TemporaryDirectory() as folder:
            self.prepare(folder)
            with patch.object(recent_news, "run_reduce") as reduce:
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    prep.prepare(folder, CONDITION["url_block_patterns"], poll=lambda **kw: [
                        {"feed": "wire", "entries": 0, "error": "HTTP 403"}])
                reduce.assert_not_called()
            pinned = prep.prepare(folder, CONDITION["url_block_patterns"],
                poll=lambda **kw: recent_news.poll(FEEDS, get=fake_get, resolve=fake_resolve,
                                                  now="2026-10-13T12:00:00Z", **kw),
                reduce=lambda **kw: recent_news.run_reduce(ask=FakeJev(), now="2026-10-13T12:01:00Z", **kw),
                now=datetime(2026, 10, 13, 12, 2, tzinfo=timezone.utc))
            data = json.loads(Path(pinned).read_text())
            self.assertEqual(data["since"], "2026-10-06T12:02:00Z")
            self.assertEqual(data["built_at"], "2026-10-13T12:01:00Z")
            self.assertEqual(len(data["stories"]), 2)
        p = subprocess.run([sys.executable, str(ROOT / "code/prepare_recent_news.py"),
                            "--experiment", "airo", "--condition", "recent"], capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_pi_does_not_offer_extra_tools(self):
        # Cache access reuses read_page, not new model-visible tool instructions.
        from fri_forecaster.tool_cli import read_page
        with patch.dict(os.environ, {news_shadow.PATH_ENV: "", news_shadow.HASH_ENV: ""}):
            self.assertIn("error", read_page(news_shadow.URL))
        with patch("fri_forecaster.tools.read_page", return_value={"text": "ordinary web"}) as web:
            self.assertEqual(read_page("https://example.test"), {"text": "ordinary web"})
            web.assert_called_once_with("https://example.test", 0)


if __name__ == "__main__":
    unittest.main()
