"""redlines.logs: a log name resolves to its per-run files."""
import json
import tempfile
import unittest
from pathlib import Path

from redlines import logs


class TestLogs(unittest.TestCase):
    def test_folder_file_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            name = Path(d) / "conditional_runs_x.jsonl"
            self.assertFalse(logs.log_exists(name))
            for run, n in (("2026-09-18T1200Z", 2), ("2026-09-16T1645Z", 1)):
                logs.run_file(name, run).write_text("".join(json.dumps({"run_id": run, "i": i}) + "\n" for i in range(n)))
            self.assertEqual([r["run_id"] for r in logs.iter_rows(name)],
                             ["2026-09-16T1645Z", "2026-09-18T1200Z", "2026-09-18T1200Z"])
            self.assertEqual(logs.log_names(d), [name])
            plain = Path(d) / "experiment.jsonl"
            plain.write_text('{"a": 1}\n\n')
            self.assertEqual(list(logs.iter_rows(plain)), [{"a": 1}])

    def test_an_old_row_reads_with_the_scenario_fields(self):
        stamp = {"id": "p5", "label": "Compute caps", "set": "combined"}
        old = {"question_id": "q", "condition": stamp, "condition_set": "combined",
               "joint_conditions": ["unconditional", "p5"]}
        r = logs.read_row(json.dumps(old))
        self.assertEqual(r["scenario"], stamp)
        self.assertEqual(r["scenario_set"], "combined")
        self.assertEqual(r["joint_scenarios"], ["unconditional", "p5"])
        self.assertEqual(r["condition"], "none")               # before the variants
        self.assertIsNone(logs.read_row(json.dumps({"condition": None}))["scenario"])   # the unconditional
        self.assertEqual(logs.read_row(json.dumps({**old, "variant": "recent"}))["condition"], "recent")
        new = {"question_id": "q", "scenario": stamp, "scenario_set": "combined",
               "experiment": "airo", "condition": "recent", "variant": "recent"}
        self.assertEqual(logs.read_row(json.dumps(new)), new)
        self.assertEqual(logs.read_row('{"a": 1}'), {"a": 1})                          # another runner's row
