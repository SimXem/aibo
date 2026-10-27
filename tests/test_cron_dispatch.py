"""code/cron_run.sh runs what is due, group by group, and publishes only when
every group that publishes completed (redlines/experiments.py `due`).

The script runs from a copy under a temp root, with a stub interpreter that
records each call and answers `-m redlines.experiments due` from a file, and
a stub publish_dashboard.sh. No model, network or served file is touched."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

STUB_PY = r'''#!/usr/bin/env bash
echo "$*" >> "$CALLS"
if [ "$1 $2" = "-m redlines.experiments" ]; then
    cat "$DUE_FILE"
    exit "${DUE_RC:-0}"
fi
if [ "$1" = "-c" ]; then echo "A, B"; exit 0; fi
if [ "$1" = "code/prepare_recent_news.py" ]; then
    if [[ "$*" == *"--condition recent-shadow-noairo"* ]]; then
        [ "${NEWS_FAIL:-0}" = 0 ] || exit 1
        echo "/private/snapshot.json"
    fi
fi
if [ "$1" = "code/run_unified.py" ]; then
    for e in ${FAIL:-}; do [ "$3" = "$e" ] && exit 1; done
fi
exit 0
'''


class TestCronDispatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.root, self.home = t / "repo", t / "home"
        (self.root / "code").mkdir(parents=True)
        for f in ("cron_run.sh", "refresh_panel.sh", "notify.sh"):
            shutil.copy(ROOT / "code" / f, self.root / "code" / f)
        publish = self.root / "code" / "publish_dashboard.sh"
        publish.write_text('#!/usr/bin/env bash\necho publish >> "$CALLS"\n')
        publish.chmod(0o755)
        py = t / "py"
        py.write_text(STUB_PY)
        py.chmod(0o755)
        (self.home / ".config" / "redlines").mkdir(parents=True)
        (self.home / ".config" / "redlines" / "env").write_text("TAVILY_API_KEY=x\n")
        self.calls, self.due = t / "calls", t / "due"
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "REDLINES_PY": str(py),
                    "CALLS": str(self.calls), "DUE_FILE": str(self.due)}

    def tearDown(self):
        self.tmp.cleanup()

    def run_cron(self, due, *args, **env):
        self.due.write_text(due)
        r = subprocess.run(["bash", str(self.root / "code" / "cron_run.sh"), *args],
                           env={**self.env, **env}, capture_output=True, text=True)
        calls = self.calls.read_text().splitlines() if self.calls.exists() else []
        logs = sorted((self.home / "logs").glob("forecast-*.log")) if (self.home / "logs").exists() else []
        return r.returncode, calls, logs[-1].read_text() if logs else None

    def runs(self, calls):
        return [c.split()[2] for c in calls if c.startswith("code/run_unified.py")]

    def test_nothing_due_is_a_quiet_day(self):
        rc, calls, log = self.run_cron("")
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ["-m redlines.experiments due"])
        self.assertIsNone(log)                                   # not even a log file

    def test_a_due_group_runs_its_conditions_and_publishes(self):
        rc, calls, log = self.run_cron("airo publish none independent ai-banned\n")
        self.assertEqual(rc, 0, log)
        self.assertIn("code/run_unified.py --experiment airo --condition none --condition independent "
                      "--condition ai-banned --workers 10", calls)
        self.assertEqual(calls[-1], "publish")
        self.assertIn("code/check_eci_snapshot.py --rebuild", calls)   # the ECI preparation still runs

    def test_named_experiments_go_to_due(self):
        rc, calls, _ = self.run_cron("axes publish none\n", "axes")
        self.assertEqual(calls[0], "-m redlines.experiments due axes")
        self.assertEqual(self.runs(calls), ["axes"])

    def test_a_failed_published_group_withholds_publication(self):
        rc, calls, log = self.run_cron("airo publish none\nside aside a\n", FAIL="airo")
        self.assertEqual(rc, 1)
        self.assertEqual(self.runs(calls), ["airo", "side"])       # the rest still run
        self.assertNotIn("publish", calls)
        self.assertIn("FATAL: airo did not complete", log)

    def test_a_failed_unpublished_group_does_not(self):
        rc, calls, log = self.run_cron("airo publish none\nside aside a\n", FAIL="side")
        self.assertEqual(rc, 0, log)
        self.assertEqual(calls[-1], "publish")

    def test_friday_shadow_gets_snapshot_and_failure_does_not_hold_up_publication(self):
        due = "airo publish recent\nairo aside recent-shadow-noairo\n"
        rc, calls, log = self.run_cron(due)
        self.assertEqual(rc, 0, log)
        self.assertIn("code/run_unified.py --experiment airo --condition recent-shadow-noairo "
                      "--news-snapshot /private/snapshot.json --workers 10", calls)
        self.assertEqual(calls[-1], "publish")

    def test_failed_news_preparation_skips_only_shadow(self):
        rc, calls, log = self.run_cron("airo publish recent\nairo aside recent-shadow-noairo\n", NEWS_FAIL="1")
        self.assertEqual(rc, 0, log)
        runs = [c for c in calls if c.startswith("code/run_unified.py")]
        self.assertEqual(runs, ["code/run_unified.py --experiment airo --condition recent --workers 10"])
        self.assertIn("no fallback", log)
        self.assertEqual(calls[-1], "publish")

    def test_only_unpublished_groups_publish_nothing(self):
        rc, calls, log = self.run_cron("side aside a b\n")
        self.assertEqual(rc, 0, log)
        self.assertEqual(self.runs(calls), ["side"])
        self.assertNotIn("publish", calls)

    def test_unreadable_experiments_fail_loudly(self):
        rc, calls, log = self.run_cron("airo.toml: unknown setting(s) ['harnes']\n", DUE_RC="1")
        self.assertEqual(rc, 1)
        self.assertEqual(self.runs(calls), [])
        self.assertIn("FATAL: experiments/ could not be read: airo.toml: unknown setting", log)


if __name__ == "__main__":
    unittest.main()
