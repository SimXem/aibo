"""Protect scientific scope, forecast windows and provenance across the cutover."""
import hashlib
import importlib.util
import json
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from redlines.instrument import CURRENT_INSTRUMENT, counting_windows
from redlines.questions import ladder_index, load_ladder

ROOT = Path(__file__).resolve().parent.parent


class TestCountingInstrument(unittest.TestCase):
    V1 = ROOT / 'data/instruments/airo-incidents-prospective-v1'
    V2 = ROOT / 'data/instruments/airo-incidents-prospective-v2'

    def test_scientific_change_is_limited_to_dates_and_cyber_boundaries(self):
        """The 2026-09-10 change, pinned between its two archives."""
        old = json.loads((ROOT / 'data/instruments/legacy-2026-08-31/autoarc_ladder.json').read_text())
        new = json.loads((self.V1 / 'autoarc_ladder.json').read_text())
        # 2026-09-16: the extinction rung is an addendum's, beside the archived eight.
        self.assertEqual(old['rungs'], [r for r in new['rungs'] if not r.get('since')])
        # 2026-09-15: the extinction addendum ADDS one subset relation; every
        # relation of the archived instrument is still present and unchanged.
        self.assertEqual(old['relations']['cross'], new['relations']['cross'])
        self.assertEqual(old['relations']['bracket'], new['relations']['bracket'])
        for rel in old['relations']['subset']:
            self.assertIn(rel, new['relations']['subset'])
        # The extinction rung's four questions (an addendum, 2026-09-16) are new;
        # every archived question is still there, in order, unchanged.
        current = [q for q in new['questions'] if not q.get('since')]
        self.assertEqual(len(current), len(old['questions']))
        for before, after in zip(old['questions'], current):
            self.assertEqual(before['id'], after['id'])
            self.assertEqual(before['text'], after['text'])
            self.assertEqual(before['details']['severity'], after['details']['severity'])
            self.assertEqual(before['details']['perfect_knowledge'], after['details']['perfect_knowledge'])
            if after['cause'] != 'cyber':
                self.assertEqual(before['criteria'], after['criteria'])
        old_cross = json.loads((ROOT / 'data/instruments/legacy-2026-08-31/autoarc_crosscutting.json').read_text())
        new_cross = json.loads((self.V1 / 'autoarc_crosscutting.json').read_text())
        # The workbook's three questions are unchanged; the only additions are
        # the addendum's extinction pair, each stamped with its `since`.
        new_by_id = {q['id']: q for q in new_cross['questions']}
        for q in old_cross['questions']:
            self.assertEqual(q, new_by_id[q['id']])
        added = [q for q in new_cross['questions'] if q['id'] not in {o['id'] for o in old_cross['questions']}]
        self.assertEqual([q['id'] for q in added], ['extinction:general', 'extinction:ai'])
        self.assertTrue(all(q.get('since') == '2026-09-15' for q in added))

    def test_the_legs_split_changes_only_the_severity_slot(self):
        """The 2026-10-19 change: every v1 question becomes a deaths question
        and, unless it is the extinction rung, a damages question. Thresholds,
        criteria, details and horizons are v1's; the text differs only in the
        severity slot; the cross-cutting questions are untouched. Pinned
        between its two archives."""
        v1 = json.loads((self.V1 / 'autoarc_ladder.json').read_text())
        cur = json.loads((self.V2 / 'autoarc_ladder.json').read_text())
        self.assertEqual([(r['short'], r['deaths'], r['damages_usd']) for r in v1['rungs']],
                         [(r['short'], r['deaths'], r['damages_usd']) for r in cur['rungs']])
        self.assertEqual([l['key'] for l in cur['legs']], ['deaths', 'damages'])
        index = ladder_index(cur)
        for q in v1['questions']:
            d = index[(q['cause'], q['rung'], 'deaths')]
            if q['severity']['kind'] == 'extinction':
                self.assertNotIn((q['cause'], q['rung'], 'damages'), index)
                self.assertEqual(d['text'], q['text'])
                # v1 copied the rung record whole, `since`/`source` included; those are question fields now.
                self.assertEqual(d['severity'], {k: v for k, v in q['severity'].items() if k not in ('since', 'source')})
                continue
            m = index[(q['cause'], q['rung'], 'damages')]
            deaths_text, damages_text = q['severity']['source_text'].split(' or ')
            slot = f"{deaths_text} or {damages_text} in economic damages"
            self.assertIn(slot, q['text'])
            self.assertEqual(d['text'], q['text'].replace(slot, deaths_text))
            self.assertEqual(m['text'], q['text'].replace(slot, f"{damages_text} in economic damages"))
            self.assertEqual((d['severity']['deaths'], d['severity']['damages_usd']), (q['severity']['deaths'], None))
            self.assertEqual((m['severity']['deaths'], m['severity']['damages_usd']), (None, q['severity']['damages_usd']))
            for leg_q in (d, m):
                for k in ('criteria', 'details', 'horizons', 'cause_label', 'human_comparisons'):
                    self.assertEqual(leg_q[k], q[k], (leg_q['id'], k))
        self.assertEqual(len(cur['questions']), 2 * len(v1['questions']) - len(cur['causes']))
        v1_cross = json.loads((self.V1 / 'autoarc_crosscutting.json').read_text())
        cur_cross = json.loads((self.V2 / 'autoarc_crosscutting.json').read_text())
        self.assertEqual(v1_cross['questions'], cur_cross['questions'])

    def test_damages_without_mortality_changes_only_the_damages_accounting(self):
        """The 2026-10-21 change: the Severity definitions' damages accounting
        drops monetized mortality, in every question's severity details and
        nowhere else. Thresholds, legs, ids, texts, criteria and the
        cross-cutting questions are v2's; the damages-contains-deaths relation
        and the damages-leg bracket go with it."""
        v2 = json.loads((self.V2 / 'autoarc_ladder.json').read_text())
        cur = load_ladder()
        self.assertEqual((v2['rungs'], v2['legs']), (cur['rungs'], cur['legs']))
        old = ("Monetized mortality, using a value of a statistical life (VSL) of $2.2 million, "
               "regardless of the geographic distribution of fatalities.")
        new = ("Do not count the monetized value of lives lost or of morbidity (no value of a "
               "statistical life); deaths and illness count only through their real economic "
               "costs, such as lost output and medical costs.")
        self.assertEqual([q['id'] for q in v2['questions']], [q['id'] for q in cur['questions']])
        for before, after in zip(v2['questions'], cur['questions']):
            self.assertIn(old, before['details']['severity'])
            self.assertEqual(after['details']['severity'], before['details']['severity'].replace(old, new))
            self.assertEqual({k: v for k, v in before.items() if k != 'details'},
                             {k: v for k, v in after.items() if k != 'details'})
            self.assertEqual({k: v for k, v in before['details'].items() if k != 'severity'},
                             {k: v for k, v in after['details'].items() if k != 'severity'})
        self.assertIn('legs', v2['relations'])
        self.assertNotIn('legs', cur['relations'])
        self.assertEqual([b for b in v2['relations']['bracket'] if b['leg'] == 'deaths'],
                         cur['relations']['bracket'])
        v2_cross = json.loads((self.V2 / 'autoarc_crosscutting.json').read_text())
        cur_cross = json.loads((ROOT / 'data/autoarc_crosscutting.json').read_text())
        self.assertEqual(v2_cross['questions'], cur_cross['questions'])
        self.assertEqual(CURRENT_INSTRUMENT, 'airo-incidents-prospective-v3')

    def test_windows_advance_for_every_incident_horizon_and_handle_short_months(self):
        spec = load_ladder()
        q = spec['questions'][0]
        first = counting_windows(q, ['6mo', '12mo', '2030'], date(2026, 8, 31), spec)
        second = counting_windows(q, ['6mo', '12mo', '2030'], date(2027, 1, 10), spec)
        self.assertEqual(first['6mo']['end'], '2027-02-28')
        self.assertEqual(first['12mo']['end'], '2027-08-31')
        self.assertEqual(first['2030']['end'], second['2030']['end'])
        self.assertEqual(first['2030']['start'], '2026-08-31')
        self.assertEqual(second['2030']['start'], '2027-01-10')
        self.assertEqual(first['2030']['harm_years'], 3)
        self.assertIsNone(counting_windows({'category': 'crosscutting'}, ['2030'], date(2026, 9, 10), spec))

    def test_joint_rows_retain_the_batch_date_and_exact_prompt(self):
        module_spec = importlib.util.spec_from_file_location('counting_runner', ROOT / 'code/run_unified.py')
        runner = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(runner)
        groups, by_group, horizons, _, spec = runner.load_batch(runner.LADDER, runner.CROSS, runner.UNBATCHED)
        policies = runner.load_policies(runner.COMBINED)
        scenarios = list(policies['conditions'])
        keys = [runner.UNCONDITIONAL_KEY] + [c['id'] for c in scenarios]
        answer = {'rationale': 'fixture', 'eci_forecast': {'p10': 170, 'p25': 172, 'p50': 175, 'p75': 180, 'p90': 190},
                  'forecasts': [{'question_id': q['id'], 'horizon': h, 'probabilities': {k: .1 for k in keys}}
                                for qs in by_group.values() for q in qs for h in horizons if h in q['horizons']]}
        from redlines import experiments
        condition = {**experiments.DEFAULTS, 'id': 'none', 'scenarios': 'data/combined_conditions.json',
                     'pooled': True, 'sha256': 'fixture'}     # a standard call
        with patch.object(runner, 'call_tools', return_value=(answer, [])) as call:
            rows = runner.run_one_joint('fixture', 'fixture', groups, by_group, horizons,
                                       'after-midnight', 0, spec, scenarios, policies,
                                       condition, 'fixture', today=date(2026, 9, 10))
        prompt = call.call_args.args[1]
        self.assertIn('2030: 2026-09-10 through 2030-12-31', prompt)
        self.assertEqual({r['run_date'] for r in rows}, {'2026-09-10'})
        self.assertEqual({r['instrument_version'] for r in rows}, {CURRENT_INSTRUMENT})
        self.assertEqual({r['prompt_sha256'] for r in rows}, {hashlib.sha256(prompt.encode()).hexdigest()})
        self.assertEqual([r['prompt'] for r in rows if r['prompt']], [prompt])
        self.assertEqual([r['system_prompt'] for r in rows if r['system_prompt']], [runner.SYSTEM])
        self.assertTrue(all(':combined:' in r['call_id'] for r in rows))
        for row in rows:
            if row['question_id'].startswith('ladder:'):
                self.assertEqual(row['counting_window']['2030']['start'], '2026-09-10')
            else:
                self.assertIsNone(row['counting_window'])


if __name__ == '__main__':
    unittest.main()
