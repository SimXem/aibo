"""Definition changes partition display series and preserve versioned archives."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from redlines.instrument import CURRENT_INSTRUMENT, counting_windows
from redlines.questions import all_questions, load_ladder
from redlines.runlog import (current_panel, instrument_info, latest_instrument_rows,
                             latest_pooled, rows_by_day, series_rows, complete_panel_rows)
from redlines.views import axes, capability, conditional, databank, graph1, graph2, method, timeline
from redlines import export
from tests.legs import split_legs

ROOT = Path(__file__).resolve().parents[1]


def current(rows):
    rows = split_legs(rows)       # the real files predate the two-leg ladder
    spec, qs = load_ladder(), all_questions()
    for r in rows:
        r['instrument_version'] = CURRENT_INSTRUMENT
        r['run_date'] = '2026-09-10'
        r['run_id'] = '2026-09-10T2300Z'
        r['elicited_at'] = '2026-09-10T23:59:00Z'
        r['protocol'] = 'unified-joint-combined-v5'
        q = qs[r['question_id']]
        windows = counting_windows(q, q['horizons'], r['run_date'], spec)
        if windows:
            r['counting_window'] = windows
        if r.get('elicited'):
            r['elicited']['target_date'] = '2027-03-10'
    return rows


class TestInstrumentViews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = [json.loads(s) for s in (ROOT / 'results/runs/2026-09-08T1717Z.jsonl').read_text().splitlines()]
        cls.new = current(cls.old)

    def test_old_rows_never_fill_current_readings_or_timeline(self):
        for view in (graph1, graph2, timeline, databank):
            with self.subTest(view=view.__name__), patch.object(view, 'load_runlog', return_value=self.old):
                b = view.build()
                self.assertFalse(b['instrumentInfo']['available'])
                if view == graph1:
                    self.assertFalse(any(q['median'] for q in b['questions']))
                elif view == graph2:
                    self.assertFalse(any(s['causes'] for h in b['byHorizon'].values() for s in h['legs'].values()))
                elif view == timeline:
                    # The timeline keeps the headline questions' earlier
                    # readings as explicitly legacy snapshots (2026-09-10
                    # decision); none of them is a current reading.
                    self.assertTrue(b['snapshots'])
                    self.assertTrue(all(s['instrumentVersion'] == 'legacy' for s in b['snapshots']))
                else:
                    self.assertEqual(b['rows'], [])

    def test_new_and_old_are_never_aggregated_even_if_old_row_is_later(self):
        later_old = copy.deepcopy(self.old)
        for r in later_old:
            r['elicited_at'] = '2026-09-12T00:00:00Z'
            for f in r['forecasts']:
                f['probability'] = 0.99
        for view in (graph1, graph2, timeline, databank):
            with self.subTest(view=view.__name__):
                with patch.object(view, 'load_runlog', return_value=self.new):
                    expected = view.build()
                with patch.object(view, 'load_runlog', return_value=self.new + later_old):
                    actual = view.build()
                if view == timeline:
                    # Legacy rows add their own legacy-flagged day; every
                    # current day's snapshot, series point and median must be
                    # exactly what the current rows alone produce.
                    keep = [i for i, s in enumerate(actual['snapshots'])
                            if s['instrumentVersion'] != 'legacy']
                    self.assertEqual([actual['snapshots'][i] for i in keep], expected['snapshots'])
                    self.assertEqual(len(keep) + 1, len(actual['snapshots']))
                    self.assertEqual(actual['instrumentInfo'], expected['instrumentInfo'])
                    for qa, qe in zip(actual['questions'], expected['questions']):
                        self.assertEqual(qa['id'], qe['id'])
                        for h in qe['median']:
                            self.assertEqual([qa['median'][h][i] for i in keep], qe['median'][h])
                        by_label = {s['label']: s for s in qa['series']}
                        for se in qe['series']:
                            sa = by_label[se['label']]
                            for h in se['ps']:
                                self.assertEqual([sa['ps'][h][i] for i in keep], se['ps'][h])
                else:
                    self.assertEqual(actual, expected)
                self.assertTrue(actual['instrumentInfo']['available'])

    def test_batch_crossing_midnight_keeps_dates_and_panel(self):
        rows = copy.deepcopy(self.new)
        for r in rows[len(rows) // 2:]:
            r['elicited_at'] = '2026-09-11T00:01:00Z'
        self.assertEqual(set(rows_by_day(rows)), {'2026-09-10'})
        self.assertEqual(current_panel(rows), {r['label'] for r in rows})
        self.assertEqual(len(latest_pooled(rows)), len(self.new))
        info = instrument_info(rows)
        self.assertEqual(info['runDate'], '2026-09-10')
        self.assertEqual(info['countingWindows']['2030'], [{'start': '2026-09-10', 'end': '2030-12-31', 'timezone': 'UTC', 'harm_years': 3}])

    def test_newest_batch_cannot_borrow_missing_older_windows(self):
        later = copy.deepcopy(self.new[0]);later['run_date'] = '2026-09-11'
        self.assertEqual(latest_instrument_rows(self.new + [later]), [later])
        self.assertEqual(series_rows(self.old + self.new), self.new)

    def test_conditional_sources_exclude_unstamped_even_with_current_protocol(self):
        stale = copy.deepcopy(self.old)
        for r in stale:
            r['protocol'] = 'unified-joint-combined-v5'
        with patch('redlines.conditional.iter_conditional', return_value=stale):
            self.assertIsNone(conditional.pick_source())
        with patch('redlines.conditional.iter_conditional', return_value=stale):
            self.assertEqual(capability._pick(capability.VARIANTS[0][1])[1], [])
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / 'axes.jsonl';log.write_text('')
            spec = json.loads(axes.SET.read_text())
            for r in stale:
                r['protocol'] = spec['protocol']
            with patch.object(axes, 'load_conditional', return_value=stale):
                self.assertEqual(axes._rows(log, spec, None)[0], [])

    def test_launch_requires_four_models_all_questions_and_same_date(self):
        self.assertEqual(complete_panel_rows(self.new), self.new)
        labels = sorted({r['label'] for r in self.new})
        incomplete = [r for r in self.new if r['label'] != labels[-1]]
        missing_question = [r for r in self.new if r['question_id'] != 'catastrophe:ai']
        missing_cell = copy.deepcopy(self.new)
        missing_cell[0]['forecasts'] = missing_cell[0]['forecasts'][1:]
        mismatched_dates = copy.deepcopy(self.new)
        for r in mismatched_dates:
            if r['label'] == labels[-1]: r['run_date'] = '2026-09-11'
        for rows in (incomplete, missing_question, missing_cell, mismatched_dates):
            self.assertEqual(complete_panel_rows(rows), [])
            for view in (graph1, graph2, databank, timeline):
                with self.subTest(view=view.__name__), patch.object(view, 'load_runlog', return_value=rows):
                    b = view.build()
                    self.assertFalse(b['instrumentInfo']['available'])
        # The newest partial date cannot be presented using yesterday's panel.
        with patch.object(graph1, 'load_runlog', return_value=self.new + [next(r for r in mismatched_dates if r['run_date'] == '2026-09-11')]):
            self.assertFalse(graph1.build()['instrumentInfo']['available'])

    def test_axis_gate_uses_recorded_instrument_horizons(self):
        rows = copy.deepcopy(self.new)
        horizons = {'2030', '2050', '2100'}
        for r in rows:
            # Match real axes output: question-level asked_horizons has six,
            # but the instrument resolves and forecasts only these three.
            r['protocol'] = 'unified-joint-axes-v3'
            r['resolves_on'] = {h: d for h, d in r['resolves_on'].items() if h in horizons}
            r['forecasts'] = [f for f in r['forecasts'] if f['horizon'] in horizons]
        self.assertEqual(len(rows[0]['asked_horizons']), 6)
        self.assertEqual(complete_panel_rows(rows), rows)
        for mode in ('absent', 'extra', 'missing', 'date_mismatch'):
            broken = copy.deepcopy(rows)
            if mode == 'absent': broken[0].pop('resolves_on')
            elif mode == 'extra': broken[0]['resolves_on']['6mo'] = '2027-03-10'
            elif mode == 'missing': broken[0]['resolves_on'].pop('2030')
            else: broken[0]['resolves_on']['2030'] = '2030-12-30'
            with self.subTest(mode=mode):
                self.assertEqual(complete_panel_rows(broken), [])

    def test_partial_conditional_panel_is_unavailable_in_all_current_views(self):
        from tests.test_forecast_panel import _current_fixture
        rows = _current_fixture()
        removed = rows[0]['label']
        partial = [r for r in rows if r['label'] != removed]
        with patch('redlines.conditional.iter_conditional', return_value=partial):
            self.assertFalse(conditional.build()['instrumentInfo']['available'])
        with patch('redlines.conditional.iter_conditional', return_value=partial):
            self.assertFalse(any(v['questions'] for v in capability.build()['variants']))
        self.assertEqual(conditional.current_forecast_rows(partial), [])
        # A late row for the fourth model must not bridge two onset dates.
        mixed = copy.deepcopy(rows)
        for r in mixed:
            if r['label'] == removed: r['run_date'] = '2026-09-11'
        self.assertEqual(conditional.current_forecast_rows(mixed), [])
        missing_eci = copy.deepcopy(rows)
        for r in missing_eci:
            if r['label'] == removed: r['elicited'] = None
        self.assertEqual(conditional.current_forecast_rows(missing_eci), [])

    def test_versioned_export_retains_legacy_without_relabeling(self):
        qs = all_questions()
        old = next(r for r in self.old if r['question_id'].startswith('ladder:cyber'))
        new = current([old])[0]
        unknown = copy.deepcopy(old);unknown['protocol'] = 'unified-batch-v1'
        rows = list(export._lines([old, new, unknown], qs))
        by = {r['instrument_version']: r for r in rows if r['horizon'] == '2030'}
        archived = by['legacy-2026-08-31']
        self.assertEqual(archived['instrument_version_source'], 'protocol-mapped')
        self.assertEqual(archived['question'], export._archived_questions('legacy-2026-08-31')[old['question_id']]['text'])
        # A row of the previous instrument reads its own archived wording, never today's.
        v1 = copy.deepcopy(old);v1['instrument_version'] = 'airo-incidents-prospective-v1'
        self.assertEqual(next(export._lines([v1], qs))['question'],
                         export._archived_questions('airo-incidents-prospective-v1')[old['question_id']]['text'])
        self.assertEqual(export._archived_questions('legacy-unversioned'), {})
        self.assertEqual(archived['onset_start'], '')
        self.assertEqual(by['legacy-unversioned']['question'], '')
        revised = by[CURRENT_INSTRUMENT]
        self.assertEqual(revised['onset_start'], '2026-09-10')
        self.assertEqual(revised['onset_end'], '2030-12-31')
        self.assertEqual(revised['probability'], archived['probability'])
        self.assertEqual(len(rows), sum(len(r['forecasts']) for r in (old, new, unknown)))

    def test_archive_contains_original_definitions(self):
        paths = dict(export._bundle_members())
        self.assertIn('questions/instruments/legacy-2026-08-31/autoarc_ladder.json', paths)
        self.assertIn('questions/instruments/airo-incidents-prospective-v1/autoarc_ladder.json', paths)
        self.assertIn('questions/instruments/airo-incidents-prospective-v2/autoarc_ladder.json', paths)
        self.assertIn('questions/sources/definitions-2026-09-10.md', paths)

    def test_prompt_is_explicitly_preview_or_recorded(self):
        with patch.object(method, 'load_runlog', return_value=self.old):
            preview = method.build()
        self.assertFalse(preview['promptRecorded'])
        self.assertEqual(preview['today'], '2026-10-21')   # the current definitions' date
        row = copy.deepcopy(self.new[0]);row['prompt'] = 'Exact recorded new prompt';row['prompt_sha256'] = 'example-hash'
        with patch.object(method, 'load_runlog', return_value=[row]):
            recorded = method.build()
        self.assertTrue(recorded['promptRecorded'])
        self.assertEqual(recorded['prompt'], row['prompt'])
        self.assertEqual(recorded['promptSha256'], row['prompt_sha256'])
