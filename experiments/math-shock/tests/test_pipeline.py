"""Fixture tests for the parsers and rules. Run: .venv/bin/python -m unittest discover -s tests -t ."""
import unittest

from pipeline import erdos, fc, llm, outcomes, parse, run_batch, sample
from pipeline.common import ROOT, PipelineError, load_yaml

RULES = load_yaml(ROOT / 'rules' / 'rules_v1.yaml')


def _no_env():
    raise AssertionError('tests must never load .env or build a real API client')


# Guard: any code path that would read credentials fails the test instead.
llm.load_env = run_batch.load_env = _no_env

LEAN = '''
/-!
# My Problem
-/
namespace Foo

/-- The main question. -/
@[category research open, AMS 11]
theorem foo : True := by
  sorry

set_option linter.style.formal_proof_palomar false in
/-- Solved part, with a multi-line attribute. -/
@[category research solved, AMS 30, formal_proof using lean4 at
  "https://example.org/x]y"]
theorem foo.parts.ii : True := by
  sorry

/-- A variant. -/
@[category research open, AMS 11]
-- a comment between attribute and keyword
theorem foo.variants.weak : True := by
  sorry

@[category research solved, AMS 11]
example : True := trivial

@[category research solved, AMS 11]
instance {K} [Field K] : Nonempty K := by
  sorry

@[category test, AMS 11]
theorem foo_test : True := trivial

namespace Bar
@[category research open, AMS 5]
lemma baz (n : Nat) : n = n := by
  sorry
end Bar

end Foo

@[category research open]
theorem _root_.Top.thm : True := by sorry
'''


class TestFCParser(unittest.TestCase):
    def test_parse(self):
        decls, title, issue = fc.parse_lean(LEAN, RULES)
        names = {d['name']: d['category'] for d in decls}
        self.assertEqual(title, 'My Problem')
        self.assertEqual(issue, '')
        self.assertEqual(names, {'Foo.foo': 'open', 'Foo.foo.parts.ii': 'solved', 'Foo.foo.variants.weak': 'open',
                                 'Foo.Bar.baz': 'open', 'Top.thm': 'open'})
        self.assertEqual([d['doc'] for d in decls if d['name'] == 'Foo.foo'], ['The main question.'])

    def test_headline_rule(self):
        from pipeline.frame import _headline
        decls, _, _ = fc.parse_lean(LEAN, RULES)
        self.assertNotIn('Foo.foo.variants.weak', [d['name'] for d in _headline(decls, RULES)])

    def test_unknown_category_halts(self):
        with self.assertRaises(PipelineError):
            fc.parse_lean('@[category research maybe]\ntheorem x : True := by sorry', RULES)

    def test_attribute_count_mismatch_flagged(self):
        txt = '@[category research open]\naxiom x : True\n'
        _, _, issue = fc.parse_lean(txt, RULES)
        self.assertTrue(issue)


YAML_OLD = '''
- number: "1"
  prize: "$500"
  status:
    state: "open"
    last_update: "2025-08-31"
  tags: ["number theory"]
'''
YAML_NEW = '''
- number: "1"
  prize: "$500"
  informal_status:
    state: "disproved"
    last_update: "2025-08-31"
  status:
    state: "disproved (Lean)"
    last_update: "2026-09-03"
  tags: ["number theory"]
'''


class TestErdos(unittest.TestCase):
    def test_field_precedence_and_suffix(self):
        self.assertEqual(erdos.parse(YAML_OLD, RULES)['1']['class'], 'open')
        e = erdos.parse(YAML_NEW, RULES)['1']
        self.assertEqual((e['state'], e['class']), ('disproved', 'solved'))

    def test_partial_and_unknown(self):
        self.assertEqual(erdos.classify('not disprovable', RULES), 'partial')
        with self.assertRaises(PipelineError):
            erdos.classify('probably true', RULES)


class TestLiteratureRule(unittest.TestCase):
    lr = RULES['literature_rule']

    def test_ref_dates(self):
        refs = outcomes._ref_dates(['[Ab98] old paper (1998)', 'arXiv:2607.01234 new', 'Copyright 2026 x'], self.lr)
        self.assertEqual(sorted(refs), [(1998, None), (1998, None), (2026, 7)])

    def test_predates(self):
        import datetime as dt
        t0 = dt.date(2026, 6, 30)
        self.assertTrue(outcomes._predates((2025, None), t0))
        self.assertFalse(outcomes._predates((2026, None), t0))   # same year without month: not predating
        self.assertTrue(outcomes._predates((2026, 5), t0))
        self.assertFalse(outcomes._predates((2026, 6), t0))


class TestSample(unittest.TestCase):
    def test_largest_remainder(self):
        self.assertEqual(sample._largest_remainder({'a': 316, 'b': 111, 'c': 96}, 50), {'a': 30, 'b': 11, 'c': 9})
        self.assertEqual(sum(sample._largest_remainder({'a': 1, 'b': 1, 'c': 1}, 2).values()), 2)

    def _units(self, n_solved, n_open):
        units, outs = [], []
        for i in range(n_solved + n_open):
            uid = f'erdos:{i}'
            units.append({'unit_id': uid, 'stratum': 'erdos' if i % 2 else 'fc_named', 'collection': 'X',
                          'display_name': uid})
            outs.append({'unit_id': uid, 'solved': int(i < n_solved), 'literature_find': 0})
        return units, outs

    def test_deterministic_and_shortfall(self):
        wave = {'seed': 's', 'n_total': 12, 'n_guaranteed_solved': 5}
        u, o = self._units(3, 40)
        r1, log1 = sample.draw(u, o, wave, RULES)
        r2, _ = sample.draw(list(reversed(u)), list(reversed(o)), wave, RULES)
        self.assertEqual(r1, r2)                       # input order does not matter
        self.assertEqual(log1['guaranteed_shortfall'], 2)
        self.assertEqual(len(r1), 12)
        r3, _ = sample.draw(u, o, {**wave, 'seed': 't'}, RULES)
        self.assertNotEqual({r['unit_id'] for r in r1}, {r['unit_id'] for r in r3})


class TestParse(unittest.TestCase):
    def test_extract_and_validate(self):
        txt = 'Here:\n```json\n[{"id":"PA","best":"2030-01","q10":"2027-01","q90":"after-2100"},' \
              '{"id":"PB","best":"2026-03","q10":"2026-03","q90":"2026-04"},{"id":"PZ","best":"x"}]\n```'
        rows, issues = parse.validate(parse.extract_array(txt), ['PA', 'PB', 'PC'], '2026-06-30')
        by = {r['code']: r for r in rows}
        self.assertEqual(by['PA']['valid'], 1)
        self.assertIn('before T0', by['PB']['issues'])
        self.assertEqual(by['PC']['issues'], 'missing')
        self.assertIn("unknown id 'PZ'", issues)

    def test_order_violation(self):
        rows, _ = parse.validate([{'id': 'PA', 'best': '2030-01', 'q10': '2031-01', 'q90': '2040-01'}], ['PA'], '2026-06-30')
        self.assertIn('not ordered', rows[0]['issues'])


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeBatches:
    """Answers each request from a script: ('ok', text) or ('errored', None)."""

    def __init__(self, script):
        self.script, self.created, self.results_by_id = script, [], {}

    def create(self, requests):
        bid = f'msgbatch_{len(self.created)}'
        self.created.append(requests)
        res = []
        for r in requests:
            kind, text = self.script.pop(0)
            if kind == 'ok':
                msg = _Obj(model=r['params']['model'], stop_reason='end_turn',
                           content=[_Obj(type='text', text=text)],
                           to_dict=lambda t=text: {'content': [{'type': 'text', 'text': t}]})
                res.append(_Obj(custom_id=r['custom_id'], result=_Obj(type='succeeded', message=msg)))
            else:
                res.append(_Obj(custom_id=r['custom_id'], result=_Obj(type='errored', error=None)))
        self.results_by_id[bid] = res
        return _Obj(id=bid)

    def retrieve(self, bid):
        return _Obj(processing_status='ended')

    def results(self, bid):
        return self.results_by_id[bid]


class TestRunBatch(unittest.TestCase):
    def test_submit_collect_retry_error(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock
        from pipeline import run_batch
        good = json.dumps([{'id': 'PA', 'best': '2030-01', 'q10': '2027-01', 'q90': '2040-01'}])
        convs = [{'model': 'm1', 'provider': 'anthropic', 'effort': 'default', 'sample_idx': i, 'order': ['PA'],
                  'forecast_sha256': 'x', 'forecast_prompt': f'prompt {i}'} for i in range(3)]
        convs.append({**convs[0], 'model': 'other', 'provider': 'openai'})
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp); out = d / 'raw'; out.mkdir()
            fake = mock.patch.object(run_batch, 'load_checked',
                                     return_value=({'run_id': 'r'}, d, out, convs, ['forecast']))
            with fake:
                c = _Obj(messages=_Obj(batches=_FakeBatches(
                    [('ok', good), ('ok', 'no array here'), ('errored', None), ('ok', good), ('ok', good)])))
                run_batch.submit('cfg', models=['m1'], client=c)
                self.assertIsNone(run_batch.submit('cfg', models=['m1'], client=c))   # all pending
                run_batch.collect('cfg', client=c)
                self.assertTrue((out / 'm1__s0.json').exists())
                self.assertTrue((out / 'm1__s1.partial.json').exists())
                self.assertTrue((out / 'm1__s2.error.json').exists())
                run_batch.submit('cfg', models=['m1'], client=c)               # retry s1, resubmit s2
                second = c.messages.batches.created[1]
                self.assertEqual(len(second), 2)
                retry = next(r for r in second if len(r['params']['messages']) == 3)
                self.assertEqual(retry['params']['messages'][2]['content'], run_batch.RETRY_MSG)
                run_batch.collect('cfg', client=c)
                r1 = json.loads((out / 'm1__s1.json').read_text())
                self.assertTrue(r1['parse_retry'])
                self.assertEqual(r1['forecast_turn_index'], 3)
                self.assertEqual([t['role'] for t in r1['turns']], ['user', 'assistant', 'user', 'assistant'])
                self.assertFalse((out / 'm1__s1.partial.json').exists())
                self.assertTrue((out / 'm1__s2.json').exists())
                self.assertIsNone(run_batch.submit('cfg', models=['m1'], client=c))   # everything done


class TestFollowup(unittest.TestCase):
    def test_relation_and_messages(self):
        from pipeline import followup
        f = {'valid': '1', 'best': '2030-01', 'q10': '2026-09', 'q90': 'after-2100'}
        self.assertEqual(followup._relation('2026-08-07', f), 'solved before your 10% date')
        self.assertEqual(followup._relation('2026-09-30', f), 'solved inside your 10%-90% range')
        self.assertEqual(followup._relation('2026-09-30', {**f, 'q90': '2026-08'}), 'solved after your 90% date')
        self.assertEqual(followup._relation('2026-09-30', None), 'you gave no valid forecast')
        rec = {'forecast_turn_index': 3, 'turns': [
            {'role': 'user', 'text': 'Q'}, {'role': 'assistant', 'response': {'content': [{'type': 'text', 'text': 'x'}]}},
            {'role': 'user', 'text': 'retry'}, {'role': 'assistant', 'response': {'content': [{'type': 'text', 'text': '[]'}]}},
            {'role': 'user', 'text': 'later stage'}]}
        m = followup.base_messages(rec)
        self.assertEqual([x['role'] for x in m], ['user', 'assistant', 'user', 'assistant'])
        self.assertEqual(m[3]['content'][0]['text'], '[]')


class TestAutoApprove(unittest.TestCase):
    def test_freeze_drafts_and_status(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock
        from pipeline import statements
        from pipeline.common import write_csv
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp); (tmp / 'review').mkdir()
            write_csv(tmp / 'review' / 'q.csv', [
                {'key': 'u_1@aaa', 'unit_id': 'u:1', 'docstrings': 'd', 'lean': 'l', 'draft': 'short text'},
                {'key': 'u_2@bbb', 'unit_id': 'u:2', 'docstrings': 'd', 'lean': 'l', 'draft': ' '.join(['w'] * 60)},
                {'key': 'u_3@ccc', 'unit_id': 'u:3', 'docstrings': 'd', 'lean': 'l', 'draft': ''}],
                statements.REVIEW_FIELDS)
            st = {'batches': [{'collected': True, 'review_file': 'q.csv'}, {'collected': False}]}
            wave = {'statements': {'drafter': {'max_words': 50}}}
            with mock.patch.object(statements, 'ROOT', tmp), mock.patch.object(statements, 'STATEMENTS', tmp / 's'), \
                    mock.patch.object(statements, 'load_run_config', return_value=({'run_id': 'r'}, wave, {})), \
                    mock.patch.object(statements, '_state', return_value=st):
                self.assertEqual(statements.auto_approve('cfg'), 2)       # empty draft skipped
                self.assertEqual(statements.auto_approve('cfg'), 0)       # existing files never rewritten
                r2 = json.loads((tmp / 's' / 'u_2@bbb.json').read_text())
                self.assertTrue(r2['auto_approved'] and r2['auto_checks']['over_word_limit'])
                self.assertEqual(r2['reviewer'], statements.AUTO_REVIEWER)
                units = [{'unit_id': 'u:1', 'fc_blob_t0': 'aaa'}]
                self.assertEqual(statements.approval_status(units), 'auto-approved (no human review)')
                (tmp / 's' / 'u_1@aaa.json').write_text(json.dumps({'approved': True, 'approved_text': 'x'}))
                self.assertEqual(statements.approval_status(units), 'approved')


class TestRunners(unittest.TestCase):
    """Orchestration only: every network / API / build function is mocked."""

    def test_forecast_batches_every_provider_unless_direct(self):
        from unittest import mock
        from pipeline import stage_forecast as sf
        wave = {'models': [{'id': 'a', 'provider': 'anthropic'}, {'id': 'o', 'provider': 'openai'}]}
        with mock.patch.object(sf, 'load_run_config', return_value=({}, wave, {})), \
                mock.patch.object(sf.run_batch, 'submit', side_effect=['b1', 'b2', None]) as sub, \
                mock.patch.object(sf.run_batch, 'collect') as col, mock.patch.object(sf.run, 'run') as direct, \
                mock.patch.object(sf.parse, 'parse_run') as par, mock.patch.object(sf, '_unfinished', return_value=[]):
            sf.forecast('cfg', poll_seconds=0)
        self.assertEqual([c.args[1] for c in sub.call_args_list], [['a', 'o']] * 3)   # both providers batched
        self.assertEqual(col.call_count, 3)                 # leftover batches + after each submitted batch
        direct.assert_not_called()
        par.assert_called_once_with('cfg', stub=False)
        with mock.patch.object(sf, 'load_run_config', return_value=({}, wave, {})), \
                mock.patch.object(sf.run_batch, 'submit') as sub, mock.patch.object(sf.run_batch, 'collect'), \
                mock.patch.object(sf.run, 'run') as direct, mock.patch.object(sf.parse, 'parse_run'), \
                mock.patch.object(sf, '_unfinished', return_value=[]):
            sf.forecast('cfg', direct=True)
        sub.assert_not_called(); direct.assert_called_once_with('cfg', ['a', 'o'], None)

    def test_prepare_drafts_until_complete_then_verifies(self):
        from unittest import mock
        from pipeline import stage_prepare as sp
        from pipeline.common import PipelineError
        def patched(lookups, verified=True):
            return [mock.patch.object(sp.fetch, 'fetch'), mock.patch.object(sp.fetch, 'restore'),
                    mock.patch.object(sp.build, 'build'), mock.patch.object(sp.verify, 'verify', return_value=verified),
                    mock.patch.object(sp, 'load_run_config', return_value=({'run_id': 'r'}, {}, {})),
                    mock.patch.object(sp, 'read_json', return_value={'statements_status': 'approved'}),
                    mock.patch.object(sp, 'run_dir'),
                    mock.patch.object(sp.statements, '_sampled_units'),
                    mock.patch.object(sp.statements, 'lookup', side_effect=lookups),
                    mock.patch.object(sp.statements, 'submit'), mock.patch.object(sp.statements, 'collect'),
                    mock.patch.object(sp.statements, 'auto_approve')]
        import contextlib
        with contextlib.ExitStack() as es:
            m = [es.enter_context(p) for p in patched([({}, [{'unit_id': 'u:1'}]), ({}, []), ({}, [])])]
            sp.prepare('cfg', no_fetch=True)
            m[0].assert_not_called()                          # --no-fetch
            self.assertEqual(m[9].call_count, 1)              # one draft batch
            m[3].assert_called_once_with('cfg', fresh=True)
            self.assertEqual(m[2].call_count, 2)              # build before and after the statements
        with contextlib.ExitStack() as es:
            [es.enter_context(p) for p in patched([({}, [{'unit_id': 'u:1'}])] * 4)]
            with self.assertRaises(PipelineError):            # still missing after all rounds
                sp.prepare('cfg', no_fetch=True, rounds=2)
        with contextlib.ExitStack() as es:
            [es.enter_context(p) for p in patched([({}, []), ({}, [])], verified=False)]
            with self.assertRaises(PipelineError):            # verification failure stops the runner
                sp.prepare('cfg', no_fetch=True)

    def test_followup_builds_once_batches_and_exports(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from pipeline import stage_followup as sfu
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            rows = [{'provider': 'anthropic'}, {'provider': 'openai'}]
            with mock.patch.object(sfu, 'load_yaml', return_value={'base_run': 'b', 'followup_id': 'f'}), \
                    mock.patch.object(sfu, 'load_checked', return_value=(None, d, None, None, None)), \
                    mock.patch.object(sfu.followup, 'build') as bld, \
                    mock.patch.object(sfu.followup, '_checked', return_value=(None, None, None, rows, None)), \
                    mock.patch.object(sfu.followup, 'submit', side_effect=['b1', None, None]) as sub, \
                    mock.patch.object(sfu.followup, 'collect') as col, \
                    mock.patch.object(sfu.followup, 'run_direct') as direct, \
                    mock.patch.object(sfu.followup, 'pending', return_value=[]), \
                    mock.patch.object(sfu.followup, 'parse') as par, mock.patch.object(sfu.followup, 'export') as exp:
                sfu.run_followup('fu.yaml', poll_seconds=0)
                bld.assert_called_once()                      # no lock yet -> build
                self.assertEqual(sub.call_count, 2); self.assertEqual(col.call_count, 2)
                direct.assert_not_called()                    # every provider is batched
                par.assert_called_once(); exp.assert_called_once()
                (d / 'followups' / 'f').mkdir(parents=True); (d / 'followups' / 'f' / 'followup.lock.json').write_text('{}')
                sfu.run_followup('fu.yaml', poll_seconds=0)
                bld.assert_called_once()                      # existing lock is checked, never rebuilt



class TestOrderSalt(unittest.TestCase):
    def test_order_salt_pins_problem_order(self):
        from pipeline import render
        rows = [{'unit_id': f'u:{i}', 'code': f'P{i:05d}', 'display_name': f'U{i}', 'solved': '0'} for i in range(8)]
        st = {r['unit_id']: 'text' for r in rows}
        run = {'templates': 'templates/v1', 'run_date': '2026-11-03', 'snapshot_date': '2026-11-02', 'stages': ['forecast']}
        wave = {'t0': '2026-06-30', 'n_samples': 2, 'models': [{'id': 'm', 'provider': 'anthropic'}]}
        order = lambda w, h: [r['order'] for r in render.render(run, w, rows, st, h)]
        self.assertNotEqual(order(wave, 'hash-a'), order(wave, 'hash-b'))            # default: config hash
        pinned = {**wave, 'order_salt': 'hash-a'}
        self.assertEqual(order(pinned, 'hash-b'), order(wave, 'hash-a'))              # salt overrides it
        more = {**pinned, 'models': wave['models'] + [{'id': 'x', 'provider': 'openai'}]}
        self.assertEqual(order(more, 'hash-c')[:2], order(wave, 'hash-a'))           # adding a model keeps m's order


class TestNoTools(unittest.TestCase):
    def test_requests_carry_no_tools(self):
        from unittest import mock
        from pipeline import llm, run_batch
        with self.assertRaises(PipelineError):
            llm.check_no_tools({'model': 'm', 'max_tokens': 1, 'messages': [], 'tools': [{'type': 'web_search_20260209'}]})
        a = llm.Anthropic.__new__(llm.Anthropic)          # no __init__: no client, no .env
        a.client = mock.MagicMock()
        msg = mock.MagicMock(content=[], model='m', stop_reason='end_turn')
        a.client.messages.stream.return_value.__enter__.return_value.get_final_message.return_value = msg
        a.chat('m', [{'role': 'user', 'content': 'x'}], 'high')
        self.assertEqual(set(a.client.messages.stream.call_args.kwargs), {'model', 'max_tokens', 'messages', 'output_config'})
        jobs = run_batch._forecast_jobs({'run_id': 'r'}, [{'model': 'm', 'effort': 'high', 'sample_idx': 0,
                                                          'forecast_prompt': 'p', 'order': [], 'forecast_sha256': 'h'}])
        self.assertNotIn('tools', jobs[0]['params'])



class _FakeOpenAI:
    """Fake OpenAI client for the Batch API: files up, batches, result files down."""

    def __init__(self, script):
        import json
        self.json, self.script, self.files_up, self.batches_made, self.out = json, script, {}, [], {}
        fake = self

        class Files:
            def create(self, file, purpose):
                fid = f'file-in{len(fake.files_up)}'
                fake.files_up[fid] = [fake.json.loads(l) for l in file[1].decode().splitlines()]
                return _Obj(id=fid)

            def content(self, fid):
                return _Obj(text=fake.out[fid])

        class Batches:
            def create(self, input_file_id, endpoint, completion_window):
                bid = f'batch_{len(fake.batches_made)}'
                lines = fake.files_up[input_file_id]
                fake.batches_made.append((bid, endpoint, lines))
                ok, bad = [], []
                for i, l in enumerate(lines):          # results in reverse order: must be keyed by custom_id
                    kind, text = fake.script.pop(0)
                    if kind == 'ok':
                        body = {'id': f'resp_{i}', 'model': l['body']['model'], 'status': 'completed',
                                'output': [{'type': 'reasoning'}, {'type': 'message', 'role': 'assistant',
                                                                   'content': [{'type': 'output_text', 'text': text}]}]}
                        ok.append({'custom_id': l['custom_id'], 'response': {'status_code': 200, 'request_id': f'req_{i}', 'body': body}, 'error': None})
                    else:
                        bad.append({'custom_id': l['custom_id'], 'response': None, 'error': {'code': 'batch_expired', 'message': 'late'}})
                fake.out[f'out_{bid}'] = '\n'.join(fake.json.dumps(x) for x in reversed(ok))
                fake.out[f'err_{bid}'] = '\n'.join(fake.json.dumps(x) for x in bad)
                return _Obj(id=bid)

            def retrieve(self, bid):
                return _Obj(status='completed', output_file_id=f'out_{bid}', error_file_id=f'err_{bid}', errors=None,
                            request_counts=_Obj(completed=1, total=1, failed=0))

        self.files, self.batches = Files(), Batches()


class TestOpenAIBatch(unittest.TestCase):
    def test_one_batch_per_model_retry_and_errors(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock
        from pipeline import parse, run_batch
        arr = lambda: json.dumps([{'id': 'PA', 'best': '2030-01', 'q10': '2027-01', 'q90': '2040-01'}])
        convs = [{'model': m, 'provider': 'openai', 'effort': 'high', 'sample_idx': i, 'order': ['PA'],
                  'forecast_sha256': 'x', 'forecast_prompt': f'prompt {m} {i}'} for m in ('gpt-a', 'gpt-b') for i in range(2)]
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp); out = d / 'raw'; out.mkdir()
            with mock.patch.object(run_batch, 'load_checked', return_value=({'run_id': 'r'}, d, out, convs, ['forecast'])):
                fake = _FakeOpenAI([('ok', arr()), ('ok', 'no json'), ('ok', arr()), ('err', None),
                                    ('ok', arr()), ('ok', arr())])
                clients = {'openai': fake}
                ids = run_batch.submit('cfg', client=clients)
                self.assertEqual(len(ids), 2)                                  # one batch per model
                for bid, endpoint, lines in fake.batches_made:
                    self.assertEqual(endpoint, '/v1/responses')
                    self.assertEqual(len({l['body']['model'] for l in lines}), 1)
                    self.assertEqual(set(lines[0]['body']), {'model', 'reasoning', 'input'})
                    self.assertEqual(lines[0]['body']['reasoning'], {'effort': 'high'})
                run_batch.collect('cfg', client=clients)
                self.assertTrue((out / 'gpt-a__s0.json').exists())
                self.assertTrue((out / 'gpt-a__s1.partial.json').exists())     # unparseable -> retry
                self.assertTrue((out / 'gpt-b__s1.error.json').exists())       # expired request
                run_batch.submit('cfg', client=clients)
                retry_batch = next(lines for _, _, lines in fake.batches_made[2:] if lines[0]['body']['model'] == 'gpt-a')
                self.assertEqual(retry_batch[0]['body']['input'][1:], [{'role': 'assistant', 'content': 'no json'},
                                                                        {'role': 'user', 'content': run_batch.RETRY_MSG}])
                run_batch.collect('cfg', client=clients)
                for sid in ('gpt-a__s0', 'gpt-a__s1', 'gpt-b__s0', 'gpt-b__s1'):
                    rec = json.loads((out / f'{sid}.json').read_text())
                    self.assertEqual(rec['stage_done'], 'forecast')
                    final = rec['turns'][rec['forecast_turn_index']]
                    self.assertEqual(json.loads(final['text'])[0]['id'], 'PA')
                    self.assertTrue(final['request_id'].startswith('req_'))
                self.assertIsNone(run_batch.submit('cfg', client=clients))


class TestOpenAI(unittest.TestCase):
    """The OpenAI adapter with a mocked client: request shape and multi-turn history."""

    def test_request_and_followup_history(self):
        from unittest import mock
        from pipeline import followup, llm
        o = llm.OpenAI.__new__(llm.OpenAI)                # no __init__: no client, no .env
        o.client = mock.MagicMock()
        o.client.responses.create.return_value = mock.MagicMock(output_text='[]', model='gpt-6.1-terra', status='completed')
        turn, text, raw = o.chat('gpt-6.1-terra', [{'role': 'user', 'content': 'x'}], 'high')
        kw = o.client.responses.create.call_args.kwargs
        self.assertEqual(set(kw), {'model', 'input', 'reasoning'})
        self.assertEqual(kw['reasoning'], {'effort': 'high'})
        self.assertEqual(turn, {'role': 'assistant', 'content': '[]'})
        o.chat('gpt-6.1-terra', [{'role': 'user', 'content': 'x'}], 'default')
        self.assertNotIn('reasoning', o.client.responses.create.call_args.kwargs)   # vendor default: nothing sent
        rec = {'provider': 'openai', 'forecast_turn_index': 1, 'turns': [
            {'role': 'user', 'text': 'Q'}, {'role': 'assistant', 'text': '[1]', 'response': {'output': []}}]}
        self.assertEqual(followup.base_messages(rec), [{'role': 'user', 'content': 'Q'}, {'role': 'assistant', 'content': '[1]'}])


if __name__ == '__main__':
    unittest.main()
