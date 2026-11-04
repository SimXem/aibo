"""Run the forecast stage through the Anthropic Message Batches API (asynchronous, half price;
usually < 1 h, max 24 h). Writes the same raw/<model>__s<i>.json records as `pipeline.run`, so
`pipeline.parse` works unchanged, and the two runners can be mixed: each skips finished samples.

    python -m pipeline.run_batch submit  config/runs/w1-r1.yaml --models claude-opus-5-5
    python -m pipeline.run_batch collect config/runs/w1-r1.yaml --wait
    python -m pipeline.run_batch submit  config/runs/w1-r1.yaml --models claude-opus-5-5   # parse retries / failures

Same study rules as `pipeline.run`: prompts must match run.lock.json, real runs need approved
statements, and an unparseable answer gets exactly one retry turn. Here the retry is a second batch:
`collect` keeps the first answer in raw/<model>__s<i>.partial.json, and the next `submit` sends the
conversation so far plus the retry message. Errored, expired or cancelled requests are archived as
.error.json, do not count as samples, and are resubmitted by the next `submit`.

Batch IDs and the custom_id -> (model, sample, turn) map are kept in runs/<run>/forecast_batches.json.
Only the anthropic provider and the forecast stage are supported (the reveal stage is multi-turn).

The engine (`submit_jobs` / `collect_jobs`) is generic: a job is one conversation whose last user
turn is to be answered. `pipeline.followup` uses it for the follow-up stage.
"""
import argparse
import datetime as dt
import sys
import time

from .common import PipelineError, read_json, write_json
from .llm import MAX_TOKENS, load_env
from .parse import extract_array
from .run import RETRY_MSG, load_checked, new_record, now, selected


def _client():
    import anthropic
    load_env()
    return anthropic.Anthropic(max_retries=5)


def params_for(model, effort):
    p = {'model': model, 'max_tokens': MAX_TOKENS}
    if effort and effort != 'default':
        p['output_config'] = {'effort': effort}
    return p


# ---------- generic engine ----------
# job = {'sid': '<model>__s<i>', 'params': {...}, 'messages': [... ending with the user turn to answer],
#        'start_record': callable -> fresh record dict whose turns end with that user turn,
#        'stage': value written to record['stage_done'] when finished}

def _paths(out, sid):
    return out / f'{sid}.json', out / f'{sid}.partial.json', out / f'{sid}.error.json'


def _state(p):
    return read_json(p) if p.exists() else {'batches': []}


def submit_jobs(jobs, out, state_path, client=None, collect_hint=''):
    """One batch for every job that is not finished and not in an uncollected batch."""
    st = _state(state_path)
    pending = {r['sid'] for b in st['batches'] if not b['collected'] for r in b['requests'].values()}
    requests, meta = [], {}
    for j in jobs:
        final, partial, _ = _paths(out, j['sid'])
        if (final.exists() and read_json(final).get('stage_done') == j['stage']) or j['sid'] in pending:
            continue
        messages, turn = list(j['messages']), 'first'
        if partial.exists():
            last = read_json(partial)['turns'][-1]
            messages += [{'role': 'assistant', 'content': last['response']['content']},
                         {'role': 'user', 'content': RETRY_MSG}]
            turn = 'retry'
        cid = f'r{len(requests):03d}'           # custom_id allows only [A-Za-z0-9_-]
        requests.append({'custom_id': cid, 'params': {**j['params'], 'messages': messages}})
        meta[cid] = {'sid': j['sid'], 'turn': turn}
    if not requests:
        print('nothing to submit (all selected conversations finished or in a pending batch)'); return None
    batch = (client or _client()).messages.batches.create(requests=requests)
    st['batches'].append({'batch_id': batch.id, 'collected': False, 'requests': meta,
                          'created_utc': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()})
    write_json(state_path, st)
    n_retry = sum(m['turn'] == 'retry' for m in meta.values())
    print(f'submitted batch {batch.id}: {len(requests)} requests ({n_retry} parse retries)'
          + (f'; collect with: {collect_hint}' if collect_hint else ''))
    return batch.id


def _assistant_turn(msg, params, batch_id, cid):
    return {'role': 'assistant', 'text': ''.join(x.text for x in msg.content if x.type == 'text'),
            'returned_model': msg.model, 'stop_reason': msg.stop_reason, 'request_id': None,
            'batch_id': batch_id, 'custom_id': cid, 'request_params': params,
            'response': msg.to_dict(), 'utc': now()}


def collect_jobs(jobs, out, state_path, client=None, wait=False, poll_seconds=60):
    """Fetch ended batches and write records: final, partial (awaiting the parse retry) or error."""
    by_sid = {j['sid']: j for j in jobs}
    client = client or _client()
    st = _state(state_path)
    for b in [b for b in st['batches'] if not b['collected']]:
        while True:
            info = client.messages.batches.retrieve(b['batch_id'])
            if info.processing_status == 'ended' or not wait:
                break
            n = info.request_counts
            print(f"{b['batch_id']}: {info.processing_status} (processing {n.processing}, succeeded {n.succeeded})")
            time.sleep(poll_seconds)
        if info.processing_status != 'ended':
            print(f"{b['batch_id']}: {info.processing_status}; not collected (use --wait to poll)")
            continue
        counts = {'done': 0, 'retry_needed': 0, 'error': 0}
        for res in client.messages.batches.results(b['batch_id']):
            m = b['requests'][res.custom_id]
            j = by_sid[m['sid']]
            final, partial, errp = _paths(out, j['sid'])
            if m['turn'] == 'retry':
                rec = read_json(partial)
            else:
                rec = j['start_record']()
                rec['started_utc'] = b['created_utc']
                rec['transport'] = 'batch'
            r = res.result
            if r.type != 'succeeded':
                err = getattr(getattr(r, 'error', None), 'error', None)
                rec['error'] = f'batch result {r.type}' + (f': {err.type}: {err.message}' if err else '')
                rec['error_batch'] = {'batch_id': b['batch_id'], 'custom_id': res.custom_id, 'turn': m['turn']}
                write_json(errp, rec)
                counts['error'] += 1
                continue
            if m['turn'] == 'retry':
                rec['turns'].append({'role': 'user', 'text': RETRY_MSG, 'utc': b['created_utc']})
            turn = _assistant_turn(r.message, j['params'], b['batch_id'], res.custom_id)
            rec['turns'].append(turn)
            if m['turn'] == 'first':
                try:
                    extract_array(turn['text'])
                except ValueError:
                    rec['parse_retry'] = True
                    write_json(partial, rec)
                    counts['retry_needed'] += 1
                    continue
            rec['forecast_turn_index'] = len(rec['turns']) - 1
            rec['stage_done'] = j['stage']
            rec['finished_utc'] = now()
            write_json(final, rec)
            if partial.exists():
                partial.unlink()
            counts['done'] += 1
        b.update(collected=True, collected_utc=now(), counts=counts)
        write_json(state_path, st)
        print(f"{b['batch_id']}: {counts['done']} done, {counts['retry_needed']} need a parse retry, "
              f"{counts['error']} errored")
        if counts['retry_needed'] or counts['error']:
            print('run submit again to send the retries / resubmit the errors')


# ---------- forecast stage ----------

def _forecast_jobs(run_cfg, convs):
    jobs = []
    for c in convs:
        def start(c=c):
            rec = new_record(run_cfg, c, 'anthropic')
            rec['turns'].append({'role': 'user', 'text': c['forecast_prompt'], 'utc': now()})
            return rec
        jobs.append({'sid': f"{c['model']}__s{c['sample_idx']}", 'params': params_for(c['model'], c['effort']),
                     'messages': [{'role': 'user', 'content': c['forecast_prompt']}],
                     'start_record': start, 'stage': 'forecast'})
    return jobs


def check_anthropic_only(convs):
    other = sorted({c['provider'] for c in convs} - {'anthropic'})
    if other:
        raise PipelineError(f'batch mode supports the anthropic provider only; select models with --models ({other} found)')


def submit(run_cfg_path, models=None, samples=None, allow_unreviewed=False, client=None):
    run_cfg, d, out, convs, stages = load_checked(run_cfg_path, allow_unreviewed=allow_unreviewed)
    convs = selected(convs, models, samples)
    if not convs:
        raise PipelineError(f'no conversations match models={models} samples={samples}')
    if stages != ['forecast']:
        raise PipelineError(f'batch mode runs the forecast stage only; run config has stages={stages}')
    check_anthropic_only(convs)
    return submit_jobs(_forecast_jobs(run_cfg, convs), out, d / 'forecast_batches.json', client,
                       f'python -m pipeline.run_batch collect {run_cfg_path} --wait')


def collect(run_cfg_path, wait=False, poll_seconds=60, client=None):
    run_cfg, d, out, convs, _ = load_checked(run_cfg_path, allow_unreviewed=True)
    collect_jobs(_forecast_jobs(run_cfg, convs), out, d / 'forecast_batches.json', client, wait, poll_seconds)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['submit', 'collect'])
    ap.add_argument('run_config')
    ap.add_argument('--models', nargs='*', help='submit: restrict to these model ids')
    ap.add_argument('--samples', type=int, help='submit: only sample_idx < N')
    ap.add_argument('--allow-unreviewed', action='store_true')
    ap.add_argument('--wait', action='store_true', help='collect: poll until each batch has ended')
    a = ap.parse_args()
    if a.cmd == 'submit':
        submit(a.run_config, a.models, a.samples, a.allow_unreviewed)
    else:
        collect(a.run_config, a.wait)
    sys.exit(0)
