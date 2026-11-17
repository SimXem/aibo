"""The Timeline's series start: redlines.runlog.SERIES_START / series_rows.

Since 2026-09-08 the over-time panel draws only rows elicited on or after
the agentic-harness cutover (2026-09-02); earlier elicitations (the
frontier five's batch, the joint pilots, the three-draw pilot of
2026-08-28) are a different method and stay in the log undrawn.

Run with:  python3 -m unittest tests.test_runlog_series -v   (from the repo root)
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from redlines.runlog import SERIES_START, load_runlog, series_rows  # noqa: E402
from redlines.instrument import CURRENT_INSTRUMENT


def _row(day, **kw):
    return {"elicited_at": f"{day}T12:00:00Z", "question_id": "q", "label": "m",
            "forecasts": [], "instrument_version": CURRENT_INSTRUMENT, **kw}


class TestSeriesRows(unittest.TestCase):
    def test_cut_is_inclusive_of_the_start_day(self):
        rows = [_row("2026-08-28"), _row("2026-09-01"), _row(SERIES_START), _row("2026-09-04")]
        kept = series_rows(rows)
        self.assertEqual([r["elicited_at"][:10] for r in kept], [SERIES_START, "2026-09-04"])

    def test_empty_log_stays_empty(self):
        self.assertEqual(series_rows([]), [])

    def test_the_tracked_log_has_no_pilot_left_in_the_series(self):
        """The 2026-08-28 three-draw pilot is in results/runs/ (and so in the
        panel's log) but not in the series the Timeline draws."""
        rows = load_runlog()
        days = {r["elicited_at"][:10] for r in rows}
        self.assertIn("2026-08-28", days, "the pilot should still be in the log")
        series_days = {r["elicited_at"][:10] for r in series_rows(rows)}
        self.assertNotIn("2026-08-28", series_days)
        expected = {r['elicited_at'][:10] for r in rows
                    if r.get('instrument_version') == CURRENT_INSTRUMENT
                    and r['elicited_at'][:10] >= SERIES_START}
        self.assertEqual(series_days, expected)
        self.assertTrue(all(d >= SERIES_START for d in series_days))


if __name__ == "__main__":
    unittest.main()


class TestPanelRows(unittest.TestCase):
    """A model that leaves the panel keeps its rows (project lead, 2026-09-08);
    the latest-reading views take the current panel's through current_rows()."""

    def _log(self):
        stamp = {"set": "eci_topk", "k": 2}
        return [
            {"elicited_at": "2026-08-20T12:00:00Z", "question_id": "q", "label": "Old Five", "forecasts": []},
            {"elicited_at": "2026-09-02T12:00:00Z", "question_id": "q", "label": "A", "forecasts": [], "panel": stamp},
            {"elicited_at": "2026-09-02T12:00:00Z", "question_id": "q", "label": "B", "forecasts": [], "panel": stamp},
            {"elicited_at": "2026-09-08T12:00:00Z", "question_id": "q", "label": "A", "forecasts": [], "panel": stamp},
            {"elicited_at": "2026-09-08T12:00:00Z", "question_id": "q", "label": "C", "forecasts": [], "panel": stamp},
        ]

    def test_panel_rows_keeps_every_panel_member_ever_and_drops_the_unstamped(self):
        from redlines.runlog import panel_rows
        kept = panel_rows(self._log())
        self.assertEqual(sorted({r["label"] for r in kept}), ["A", "B", "C"])
        self.assertEqual(len(kept), 4)

    def test_current_panel_is_the_newest_day_and_current_rows_follow_it(self):
        from redlines.runlog import current_panel, current_rows, panel_rows
        rows = panel_rows(self._log())
        self.assertEqual(current_panel(rows), {"A", "C"})
        self.assertEqual(sorted((r["label"], r["elicited_at"][:10]) for r in current_rows(rows)),
                         [("A", "2026-09-02"), ("A", "2026-09-08"), ("C", "2026-09-08")])

    def test_unstamped_log_is_left_alone(self):
        from redlines.runlog import current_panel, current_rows, panel_rows
        rows = [_row("2026-08-20", label="X"), _row("2026-08-21", label="Y")]
        self.assertEqual(panel_rows(rows), rows)
        self.assertEqual(current_panel(rows), {"X", "Y"})
        self.assertEqual(current_rows(rows), rows)
