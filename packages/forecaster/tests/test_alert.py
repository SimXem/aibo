"""fri_forecaster.alert: callers say what happened, the installation's file
says where it goes. No network: the transport is replaced."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from fri_forecaster import alert


class TestAlert(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.tmp.name, "alerts.json")
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        patch = mock.patch.dict(os.environ, {"FRI_ALERTS_FILE": self.file, "FRI_ALERT_LEDGER": self.ledger})
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        self.posts = []
        patch = mock.patch.object(alert, "_post", lambda url, body, headers, timeout=20: self.posts.append((url, body, headers)))
        patch.start()
        self.addCleanup(patch.stop)

    def channels(self, *channels):
        with open(self.file, "w") as f:
            json.dump({"channels": list(channels)}, f)

    def quiet(self, fn, *args, **kw):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            return fn(*args, **kw), err.getvalue()

    def test_without_a_file_nothing_is_sent_and_the_line_is_printed(self):
        sent, err = self.quiet(alert.send, "airo", "run failed", "exit 1")
        self.assertEqual((sent, self.posts), (0, []))
        self.assertIn("no channel configured", err)
        self.assertIn("airo: run failed", err)
        self.assertEqual(self.quiet(alert.main, ["check"])[0], 1)

    def test_a_page_goes_to_ntfy_at_high_priority_with_the_log(self):
        self.channels({"kind": "ntfy", "topic": "t0pic"})
        sent, _ = self.quiet(alert.send, "forecastbench", "key refused", "fix the key", log="/x/round.log")
        self.assertEqual(sent, 1)
        url, body, headers = self.posts[0]
        self.assertEqual(url, "https://ntfy.sh/t0pic")
        self.assertEqual(headers["Title"], "forecastbench: key refused")
        self.assertEqual(headers["Priority"], "high")
        self.assertIn("fix the key\nlog: /x/round.log\non ", body.decode())
        self.quiet(alert.send, "airo", "panel changed", "A, B", severity="notice")
        self.assertEqual(self.posts[1][2]["Priority"], "default")
        self.assertEqual(self.quiet(alert.main, ["check"])[0], 0)

    def test_a_channel_takes_only_what_it_names(self):
        self.channels({"kind": "ntfy", "topic": "all"},
                      {"kind": "ntfy", "topic": "fb-pages", "deployments": ["forecastbench"], "severities": ["page"]})
        for deployment, severity in (("airo", "page"), ("forecastbench", "notice"), ("forecastbench", "page")):
            self.quiet(alert.send, deployment, "x", "y", severity=severity)
        self.assertEqual([url.rsplit("/", 1)[1] for url, _, _ in self.posts], ["all", "all", "all", "fb-pages"])

    def test_a_dead_channel_neither_raises_nor_stops_the_next(self):
        self.channels({"kind": "ntfy", "topic": "dead"}, {"kind": "ntfy", "topic": "alive"})
        def post(ch, title, body, severity):
            if ch["topic"] == "dead":
                raise OSError("no route")
            self.posts.append(ch["topic"])
        sent, err = self.quiet(alert.send, "airo", "run failed", "exit 1", post=post)
        self.assertEqual((sent, self.posts), (1, ["alive"]))
        self.assertIn("not delivered", err)
        self.assertEqual(self.quiet(alert.main, ["send", "--deployment", "airo", "--title", "t", "m"])[0], 0)

    def test_a_bad_file_fails_the_check_but_not_the_job(self):
        self.channels({"kind": "carrier-pigeon"})
        self.assertEqual(self.quiet(alert.main, ["check"])[0], 1)
        sent, err = self.quiet(alert.send, "airo", "run failed", "exit 1")
        self.assertEqual(sent, 0)
        self.assertIn("ALERT NOT SENT", err)
        # A channel that takes only one deployment's pages leaves the others with nobody.
        self.channels({"kind": "ntfy", "topic": "t", "deployments": ["airo"]})
        self.assertEqual(self.quiet(alert.main, ["check"])[0], 1)

    def test_the_ledger_records_what_a_job_said(self):
        self.channels({"kind": "ntfy", "topic": "t"})
        self.quiet(alert.send, "airo", "panel changed", "A, B", severity="notice")
        self.quiet(alert.send, "airo", "run failed", "exit 1")
        with open(self.ledger) as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual([(r["severity"], r["title"], r["sent"]) for r in rows],
                         [("notice", "airo: panel changed", 1), ("page", "airo: run failed", 1)])

    def test_the_test_command_reaches_every_channel_whatever_it_filters(self):
        self.channels({"kind": "ntfy", "topic": "all"}, {"kind": "ntfy", "topic": "fb", "deployments": ["forecastbench"]})
        self.assertEqual(self.quiet(alert.main, ["test"])[0], 0)
        self.assertEqual(len(self.posts), 2)


if __name__ == "__main__":
    unittest.main()
