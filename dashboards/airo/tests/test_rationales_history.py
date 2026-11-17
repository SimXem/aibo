"""Explanations and trails must refer to the forecasts actually displayed."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from redlines.runlog import (load_runlog, complete_panel_rows,
                            latest_instrument_rows, current_rows)
from redlines.views import graph2, rationales
from tests.legs import split_legs

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results" / "runs" / "2026-09-18T1200Z.jsonl"     # a complete 41-question day


def _day(day, scale=1.0):
    """The 2026-09-18 run, as the current instrument writes it, on `day`."""
    rows = split_legs([json.loads(l) for l in RUN.read_text().splitlines() if l.strip()])
    for r in rows:
        r["run_date"] = day
        r["run_id"] = f"{day}T1200Z"
        r["elicited_at"] = f"{day}T12:30:00+00:00"
        r["call_id"] = f"{r['run_id']}:{r['label']}"
        for f in r["forecasts"]:
            f["probability"] = min(1.0, f["probability"] * scale)
    return rows


class TestRationalesAndHistory(unittest.TestCase):
    def test_explanations_use_current_calls_and_question_debriefs(self):
        data = rationales.build()
        rows = current_rows(complete_panel_rows(latest_instrument_rows(load_runlog())))
        for r in rows:
            ids = data['questions'][r['question_id']][r['label']]
            self.assertIn(r['call_id'], ids)
            self.assertEqual(data['calls'][r['call_id']]['rationale'], r['rationale'])
        self.assertEqual(set(data['calls']), {r['call_id'] for r in rows})
        # Every call carries a debrief; a debrief can be partial (Fable 5.1
        # delivered 20 of 41 questions on 2026-09-18), so check what is there.
        for call in data['calls'].values():
            self.assertTrue(call['debriefs'])
            for d in call['debriefs'].values():
                self.assertTrue(d['rationale'])

    def test_history_does_not_change_latest_forecasts(self):
        rows = _day("2026-10-20") + _day("2026-10-22", scale=0.9)
        with_history = graph2.build(rows)
        without_history = graph2.build(rows, include_history=False)
        history = with_history.pop('history')
        without_history.pop('history')
        self.assertEqual(with_history, without_history)
        self.assertEqual([s['date'] for s in history], ["2026-10-20"])
        self.assertEqual(with_history['instrumentInfo']['runDate'], "2026-10-22")
        for snapshot in history:
            self.assertEqual(snapshot['instrumentInfo']['version'],
                             with_history['instrumentInfo']['version'])
            for horizon in snapshot['byHorizon'].values():
                self.assertEqual(set(horizon['legs']), {"deaths", "damages"})
                for leg, side in horizon['legs'].items():
                    self.assertEqual(len(side['causes']), 4)
                    for cause in side['causes']:
                        # The deaths ladder reaches extinction; the damages ladder has no such rung.
                        self.assertEqual(len(cause['rungs']), 9 if leg == "deaths" else 8)

    def test_incomplete_prior_panel_is_not_a_trail(self):
        earlier = _day("2026-10-20")
        gone = earlier[0]["label"]
        rows = [r for r in earlier if r["label"] != gone] + _day("2026-10-22")
        self.assertNotIn("2026-10-20", [s['date'] for s in graph2.build(rows)['history']])
