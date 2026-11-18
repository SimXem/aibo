"""Prior snapshots are optional, isolated, complete, and immutable."""
import hashlib
import importlib.util
import json
from datetime import date
from pathlib import Path
import pytest
from redlines import experiments, prior_shadow
from fri_forecaster import prior_forecast


def fixture(tmp_path, monkeypatch):
    site = tmp_path / 'site'; site.mkdir()
    results = tmp_path / 'results'; (results / 'runs').mkdir(parents=True)
    q = dict(id='q', text='Will it happen?', criteria='Rule', value_kind='probability',
             horizons=['2030'], variants={'none': {'2030': [20]}},
             variantModels={'none': {'2030': [{'A': 10, 'B': 30}]}})
    from redlines import questions
    monkeypatch.setattr(questions, 'questions_asked_on', lambda d: {'q':q})
    snap = dict(instrumentVersion='airo-incidents-prospective-v3', date='2026-11-13', runs=['run-old'], instrumentInfo={'countingWindows': {'2030': [{'start': '2026-11-13', 'end': '2030-12-31'}]}})
    (site/'index.html').write_text('<script>window.__TIMELINE__ = '+json.dumps(dict(snapshots=[snap],questions=[q]))+';</script>')
    rows = [dict(run_id='run-old', question_id='q', model=m, condition='none', run_date='2026-11-13',
                 elicited=dict(target_date='2027-05-13',eci_forecast={k:v for k in ['p10','p25','p50','p75','p90']}),
                 resolves_on={'2030':'2030-12-31'}, forecasts=[dict(horizon='2030',probability=v/100)]) for m,v in [('A',10),('B',30)]]
    (results/'runs/run-old.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    return site,results,rows


def test_published_baseline_only_and_immutable(tmp_path,monkeypatch):
    site,results,rows=fixture(tmp_path,monkeypatch)
    (results/'runs/new-unpublished.jsonl').write_text('bad input')
    frozen=prior_shadow.freeze(site,results)
    data=json.loads(Path(frozen['path']).read_text())
    assert data['questions'][0]['probability_percent']=={'2030':20}
    assert data['eci_forecast']['p50']==20
    monkeypatch.setenv(prior_forecast.PATH_ENV,frozen['path'])
    monkeypatch.setenv(prior_forecast.HASH_ENV,frozen['sha256'])
    assert prior_forecast.read_snapshot('file:///etc/passwd') is None
    assert prior_forecast.read_snapshot(prior_forecast.URL)['snapshot_sha256']==frozen['sha256']
    assert prior_forecast.read_snapshot(prior_forecast.URL,7)['text']==Path(frozen['path']).read_text()[7:7007]
    Path(frozen['path']).write_text('tampered')
    assert 'error' in prior_forecast.read_snapshot(prior_forecast.URL)


def test_reader_unavailable_without_explicit_access(monkeypatch):
    monkeypatch.delenv(prior_forecast.PATH_ENV,raising=False)
    assert 'error' in prior_forecast.read_snapshot(prior_forecast.URL)


def test_self_requires_bootstrap_and_advances_only_complete_panel(tmp_path,monkeypatch):
    site,results,rows=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='bootstrap'):
        prior_shadow.load_self(results,site)
    seed=prior_shadow.load_self(results,site,True)
    condition=dict(id='prior-recent-shadow',_prior_snapshot=seed)
    output=tmp_path/'output.jsonl'
    for r in rows:
        r.update(run_id='shadow-new',condition=condition['id'],run_date='2026-11-16',counting_window={'2030':{'start':'2026-11-16','end':'2030-12-31'}})
    output.write_text(json.dumps(rows[0])+'\n')
    panel=[('A','A'),('B','B')]
    with pytest.raises(ValueError,match='incomplete'):
        prior_shadow.save_self(output,'shadow-new',condition,panel,results)
    assert not (results/'experiments/prior-recent-shadow/latest.json').exists()
    output.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    saved=prior_shadow.save_self(output,'shadow-new',condition,panel,results)
    assert prior_shadow.load_self(results,site)==saved
    assert saved['forecast_date']=='2026-11-16'
    assert saved['sha256']!=seed['sha256']


def test_missing_baseline_panel_rejected(tmp_path,monkeypatch):
    site,results,rows=fixture(tmp_path,monkeypatch)
    (results/'runs/run-old.jsonl').write_text(json.dumps(rows[0])+'\n')
    with pytest.raises(ValueError,match='panels differ'):
        prior_shadow.freeze(site,results)


def test_prompt_additions_and_schedule():
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('prior_runner',root/'code/run_unified.py')
    ru=importlib.util.module_from_spec(spec);spec.loader.exec_module(ru)
    groups,batch,horizons,_,instrument=ru.load_batch(ru.LADDER,ru.CROSS,ru.UNBATCHED)
    policies=ru.load_policies(ru.COMBINED)
    prompt,_,_=ru.build_prompt_joint(groups,batch,horizons,instrument,policies['conditions'],policies,date(2026,11,16))
    base=ru.minimal_joint_prompt(prompt,'none')
    for name in ['prior-baseline-shadow','prior-recent-shadow']:
        c=experiments.load(name)['conditions'][name]
        assert not c['publish'] and not c['pooled'] and not c['url_block_patterns']
        assert c['max_turns'] is None
        actual=ru.condition_prompt(prompt,c)
        if name == 'prior-recent-shadow':
            paired = dict(c, id='prior-recent-rationale', rationale_revision=True)
            assert ru.condition_prompt(prompt, paired) == actual.rstrip() + '\n\n' + ru.REVISION_SENTENCE + '\n'
        assert actual.startswith(base+'\n\n')
        assert prior_forecast.URL in actual[len(base):]
        assert experiments.VARIANTS['ai-banned'] not in actual
        for d in [date(2026,11,18),date(2026,11,20)]:
            assert (name,False,[name]) in experiments.due(d)
            assert not any('recent-shadow-noairo' in ids for _,_,ids in experiments.due(d))
        assert (name,False,[name]) not in experiments.due(date(2026,11,16))

@pytest.mark.parametrize('name', ['prior-baseline-shadow','prior-recent-shadow'])
def test_call_scoped_files_and_baseline_settings(name,monkeypatch):
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('prior_call_runner',root/'code/run_unified.py')
    ru=importlib.util.module_from_spec(spec);spec.loader.exec_module(ru)
    groups,batch,horizons,_,instrument=ru.load_batch(ru.LADDER,ru.CROSS,ru.UNBATCHED)
    policies=ru.load_policies(ru.COMBINED)
    c=dict(experiments.load(name)['conditions'][name])
    c['_prior_snapshot']=dict(path='/private/prior.json',sha256='a'*64,forecast_date='2026-11-13')
    c['_news_snapshot']=dict(path='/private/news.json',sha256='b'*64)
    seen={}
    def fake(model,prompt,tools,final_tool,**kw):
        seen.update(kw)
        cells=[dict(question_id=q['id'],horizon=h,probabilities={'unconditional':.01})
               for g in groups for q in batch[g['key']] for h in horizons if h in q['horizons']]
        return dict(forecasts=cells,rationale='synthetic',eci_forecast=dict(p10=168,p25=170,p50=172,p75=175,p90=178)),[]
    monkeypatch.setattr(ru,'call_tools',fake)
    rows=ru.run_one_joint('fake','fake/model',groups,batch,horizons,'test',0,instrument,[],policies,c,name,today=date(2026,11,16))
    assert seen['env'][prior_forecast.PATH_ENV]=='/private/prior.json'
    assert ru.BLOCK_ENV not in seen['env']
    assert seen['max_iters']==ru.MINIMAL_MAX_TURNS
    assert seen['min_evidence']==0
    assert all(r['pooled'] is False for r in rows)
    assert all('path' not in r['prior_baseline_snapshot'] for r in rows)
    if c['recent_news']:
        assert seen['env']['FORECASTER_NEWS_SNAPSHOT']=='/private/news.json'
    else:
        assert 'FORECASTER_NEWS_SNAPSHOT' not in seen['env']
