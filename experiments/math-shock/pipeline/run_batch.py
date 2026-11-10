"""Run forecasts through the providers' batch APIs (asynchronous, half price, results within 24 h):
Anthropic Message Batches and the OpenAI Batch API (`/v1/responses`). Writes the same
raw/<model>__s<i>.json records as `pipeline.run`, so `pipeline.parse` works unchanged, and the two
runners can be mixed: each skips finished samples.

    python -m pipeline.run_batch submit  config/runs/<run>.yaml [--models ...]
    python -m pipeline.run_batch collect config/runs/<run>.yaml --wait
    python -m pipeline.run_batch submit  config/runs/<run>.yaml          # parse retries / failed requests

Same study rules as `pipeline.run`: prompts must match run.lock.json, real runs need approved
statements, and an unparseable answer gets exactly one retry turn. Here the retry goes in the next
batch: `collect` keeps the first answer in raw/<model>__s<i>.partial.json, and the next `submit` sends
the conversation so far plus the retry message. Errored, expired or cancelled requests are archived as
.error.json, do not count as samples, and are resubmitted by the next `submit`.

One `submit` creates one batch per provider (OpenAI: one per model, as its Batch API requires).
Batch IDs and the custom_id -> conversation map are kept in runs/<run>/forecast_batches.json.

The engine (`submit_jobs` / `collect_jobs`) is generic: a job is one conversation whose last user
turn is to be answered. `pipeline.followup` uses it for follow-up turns.
"""
import argparse
import datetime as dt
import json
import sys
import time

from .common import PipelineError, read_json, write_json
from .llm import MAX_TOKENS, check_no_tools, load_env
from .parse import extract_array
from .run import RETRY_MSG, load_checked, new_record, now, selected

BATCH_PROVIDERS = ('anthropic', 'openai')


def params_for(model, effort, provider='anthropic'):
    """Request parameters without the messages; the same values the direct adapters send."""
    if provider == 'openai':
        p = {'model': model}
        if effort and effort != 'default':
            p['reasoning'] = {'effort': effort}
        return p
    p = {'model': model, 'max_tokens': MAX_TOKENS}
    if effort and effort != 'default':
        p['output_config'] = {'effort': effort}
    return p


# ---------- provider backends ----------

class AnthropicBatches:
    """Anthropic Message Batches API."""
    messages_key = 'messages'

    def __init__(self, client=None):
        if client is None:
            import anthropic
            load_env()
            client = anthropic.Anthropic(max_retries=5)
        self.c = client

    def create(self, requests):
        return self.c.messages.batches.create(
            requests=[{'custom_id': cid, 'params': p} for cid, p in requests]).id

    def poll(self, bid):
        info = self.c.messages.batches.retrieve(bid)
        n = getattr(info, 'request_counts', None)
        prog = info.processing_status + (f' (processing {n.processing}, succeeded {n.succeeded})' if n else '')
        return info.processing_status == 'ended', prog

    def results(self, bid):
        """-> iterable of (custom_id, turn or None, error or None)"""
        for res in self.c.messages.batches.results(bid):
            r = res.result
            if r.type != 'succeeded':
                err = getattr(getattr(r, 'error', None), 'error', None)
                yield res.custom_id, None, f'batch result {r.type}' + (f': {err.type}: {err.message}' if err else '')
                continue
            msg = r.message
            yield res.custom_id, {'text': ''.join(x.text for x in msg.content if x.type == 'text'),
                                  'returned_model': msg.model, 'stop_reason': msg.stop_reason, 'request_id': None,
                                  'response': msg.to_dict()}, None

    @staticmethod
    def history(turn):
        return {'role': 'assistant', 'content': turn['response']['content']}   # thinking blocks included


class OpenAIBatches:
    """OpenAI Batch API on /v1/responses: requests go up as a JSONL file, results come back as files."""
    messages_key = 'input'
    ENDED = ('completed', 'failed', 'expired', 'cancelled')

    def __init__(self, client=None):
        if client is None:
            import openai
            load_env()
            client = openai.OpenAI(max_retries=5)
        self.c = client

    def create(self, requests):
        lines = [json.dumps({'custom_id': cid, 'method': 'POST', 'url': '/v1/responses', 'body': p},
                            ensure_ascii=False) for cid, p in requests]
        f = self.c.files.create(file=('batch.jsonl', ('\n'.join(lines) + '\n').encode('utf-8'), 'application/jsonl'),
                                purpose='batch')
        return self.c.batches.create(input_file_id=f.id, endpoint='/v1/responses', completion_window='24h').id

    def poll(self, bid):
        b = self.c.batches.retrieve(bid)
        n = getattr(b, 'request_counts', None)
        prog = f'{b.status}' + (f' (completed {n.completed}/{n.total}, failed {n.failed})' if n else '')
        return b.status in self.ENDED, prog

    @staticmethod
    def _text(body):
        return ''.join(c.get('text', '') for item in body.get('output', []) if item.get('type') == 'message'
                       for c in item.get('content', []) if c.get('type') == 'output_text')

    def results(self, bid):
        b = self.c.batches.retrieve(bid)
        seen = set()
        for fid in (b.output_file_id, b.error_file_id):
            if not fid:
                continue
            for line in self.c.files.content(fid).text.splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                cid, resp = rec['custom_id'], rec.get('response') or {}
                seen.add(cid)
                body = resp.get('body') or {}
                if resp.get('status_code') == 200 and not rec.get('error'):
                    yield cid, {'text': self._text(body), 'returned_model': body.get('model'),
                                'stop_reason': body.get('status'), 'request_id': resp.get('request_id'),
                                'response': body}, None
                else:
                    err = rec.get('error') or body.get('error') or {}
                    yield cid, None, f"batch result error: {err.get('code')}: {err.get('message')} (HTTP {resp.get('status_code')})"
        if b.status != 'completed':
            errs = '; '.join(f'{e.code}: {e.message}' for e in (b.errors.data if b.errors and b.errors.data else []))
            yield None, None, f'batch {b.status}' + (f': {errs}' if errs else '')   # requests without a line

    @staticmethod
    def history(turn):
        return {'role': 'assistant', 'content': turn['text']}       # reasoning items are not sent back


BACKENDS = {'anthropic': AnthropicBatches, 'openai': OpenAIBatches}


def _backend(provider, clients):
    if provider not in clients:
        clients[provider] = BACKENDS[provider]()
    elif not isinstance(clients[provider], tuple(BACKENDS.values())):
        clients[provider] = BACKENDS[provider](clients[provider])   # a raw (test) client was passed
    return clients[provider]


# ---------- generic engine ----------
# job = {'sid': '<model>__s<i>', 'provider': ..., 'params': {...}, 'messages': [... ending with the user turn],
#        'start_record': callable -> fresh record dict whose turns end with that user turn,
#        'stage': value written to record['stage_done'] when finished}

def _paths(out, sid):
    return out / f'{sid}.json', out / f'{sid}.partial.json', out / f'{sid}.error.json'


def _state(p):
    return read_json(p) if p.exists() else {'batches': []}


def _clients(client):
    """`client`: None, a dict {provider: backend or raw client}, or one raw client (Anthropic, for tests)."""
    if client is None:
        return {}
    return dict(client) if isinstance(client, dict) else {'anthropic': client}


def submit_jobs(jobs, out, state_path, client=None, collect_hint=''):
    """One batch per provider (OpenAI: per model) for every job that is not finished and not in an
    uncollected batch. Returns the list of new batch IDs, or None if there was nothing to send."""
    clients = _clients(client)
    st = _state(state_path)
    pending = {r['sid'] for b in st['batches'] if not b['collected'] for r in b['requests'].values()}
    groups = {}
    for j in jobs:
        final, partial, _ = _paths(out, j['sid'])
        if (final.exists() and read_json(final).get('stage_done') == j['stage']) or j['sid'] in pending:
            continue
        prov = j.get('provider', 'anthropic')
        if prov not in BACKENDS:
            raise PipelineError(f"no batch API for provider {prov!r} ({j['sid']}); use direct calls")
        messages, turn = list(j['messages']), 'first'
        if partial.exists():
            messages += [BACKENDS[prov].history(read_json(partial)['turns'][-1]), {'role': 'user', 'content': RETRY_MSG}]
            turn = 'retry'
        key = (prov, j['params']['model'] if prov == 'openai' else '')
        groups.setdefault(key, []).append((j, messages, turn))
    if not groups:
        print('nothing to submit (all selected conversations finished or in a pending batch)'); return None
    ids = []
    for (prov, _), items in sorted(groups.items()):
        be = _backend(prov, clients)
        requests, meta = [], {}
        for j, messages, turn in items:
            cid = f'r{len(requests):03d}'       # custom_id: only [A-Za-z0-9_-] (Anthropic)
            requests.append((cid, check_no_tools({**j['params'], be.messages_key: messages})))
            meta[cid] = {'sid': j['sid'], 'turn': turn}
        bid = be.create(requests)
        st['batches'].append({'batch_id': bid, 'provider': prov, 'collected': False, 'requests': meta,
                              'created_utc': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()})
        write_json(state_path, st)
        n_retry = sum(m['turn'] == 'retry' for m in meta.values())
        models = sorted({j['params']['model'] for j, _, _ in items})
        print(f'submitted {prov} batch {bid}: {len(requests)} requests ({n_retry} parse retries) for {models}')
        ids.append(bid)
    if collect_hint:
        print(f'collect with: {collect_hint}')
    return ids


def collect_jobs(jobs, out, state_path, client=None, wait=False, poll_seconds=60):
    """Fetch ended batches and write records: final, partial (awaiting the parse retry) or error."""
    by_sid = {j['sid']: j for j in jobs}
    st = _state(state_path)
    if not any(not b['collected'] for b in st['batches']):
        return                                   # nothing pending: no client, no credentials needed
    clients = _clients(client)
    for b in [b for b in st['batches'] if not b['collected']]:
        prov = b.get('provider', 'anthropic')
        be = _backend(prov, clients)
        while True:
            ended, progress = be.poll(b['batch_id'])
            if ended or not wait:
                break
            print(f"{b['batch_id']}: {progress}")
            time.sleep(poll_seconds)
        if not ended:
            print(f"{b['batch_id']}: {progress}; not collected (use --wait to poll)")
            continue
        counts = {'done': 0, 'retry_needed': 0, 'error': 0}
        got = set()

        def error(cid, msg):
            m = b['requests'][cid]
            j = by_sid[m['sid']]
            final, partial, errp = _paths(out, j['sid'])
            rec = read_json(partial) if m['turn'] == 'retry' else j['start_record']()
            rec['error'] = msg
            rec['error_batch'] = {'batch_id': b['batch_id'], 'custom_id': cid, 'turn': m['turn']}
            write_json(errp, rec)
            counts['error'] += 1

        for cid, turn, err in be.results(b['batch_id']):
            if cid is None:                      # batch-level failure: every request without a line
                for c in b['requests']:
                    if c not in got:
                        got.add(c); error(c, err)
                continue
            got.add(cid)
            if err:
                error(cid, err)
                continue
            m = b['requests'][cid]
            j = by_sid[m['sid']]
            final, partial, _ = _paths(out, j['sid'])
            if m['turn'] == 'retry':
                rec = read_json(partial)
                rec['turns'].append({'role': 'user', 'text': RETRY_MSG, 'utc': b['created_utc']})
            else:
                rec = j['start_record']()
                rec['started_utc'] = b['created_utc']
                rec['transport'] = 'batch'
            rec['turns'].append({'role': 'assistant', **turn, 'batch_id': b['batch_id'], 'custom_id': cid,
                                 'request_params': j['params'], 'utc': now()})
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


# ---------- forecasts ----------

def _forecast_jobs(run_cfg, convs):
    jobs = []
    for c in convs:
        def start(c=c):
            rec = new_record(run_cfg, c, c.get('provider', 'anthropic'))
            rec['turns'].append({'role': 'user', 'text': c['forecast_prompt'], 'utc': now()})
            return rec
        prov = c.get('provider', 'anthropic')
        jobs.append({'sid': f"{c['model']}__s{c['sample_idx']}", 'provider': prov,
                     'params': params_for(c['model'], c['effort'], prov),
                     'messages': [{'role': 'user', 'content': c['forecast_prompt']}],
                     'start_record': start, 'stage': 'forecast'})
    return jobs


def submit(run_cfg_path, models=None, samples=None, allow_unreviewed=False, client=None):
    run_cfg, d, out, convs, stages = load_checked(run_cfg_path, allow_unreviewed=allow_unreviewed)
    convs = selected(convs, models, samples)
    if not convs:
        raise PipelineError(f'no conversations match models={models} samples={samples}')
    if stages != ['forecast']:
        raise PipelineError(f'batch mode runs the forecast stage only; run config has stages={stages}')
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
