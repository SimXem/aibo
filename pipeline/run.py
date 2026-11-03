"""Execute the rendered conversations and archive every raw response.

    python -m pipeline.run config/runs/w1-r1.yaml                    # all models x samples (resumable)
    python -m pipeline.run config/runs/w1-r1.yaml --models claude-opus-5-5 --samples 1
    python -m pipeline.run config/runs/w1-r1.yaml --stub              # offline dry run -> raw_stub/

Rules: prompts must match the hashes in run.lock.json; real runs need approved statements;
transport failures do not count as samples; one retry if the forecast is not parseable (logged).
"""
import argparse
import datetime as dt
import json

from .common import PipelineError, load_run_config, read_json, run_dir, sha256_file, write_json
from .llm import provider
from .parse import extract_array

RETRY_MSG = 'Reply with the JSON array only, exactly as specified above.'


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _turn(llm, model, effort, messages, rec):
    turn, text, raw = llm.chat(model, messages, effort)
    messages.append(turn)
    rec['turns'].append({'role': 'assistant', 'text': text, 'returned_model': raw['returned_model'],
                         'stop_reason': raw['stop_reason'], 'request_id': raw['request_id'],
                         'request_params': raw['request_params'], 'response': raw['response'], 'utc': now()})
    return text, raw


def load_checked(run_cfg_path, stub=False, allow_unreviewed=False):
    """Lock and approval checks shared by the direct and the batch runner.
    -> (run_cfg, run dir, raw output dir, conversations, stages)"""
    run_cfg, wave, _ = load_run_config(run_cfg_path)
    d = run_dir(run_cfg)
    lock = read_json(d / 'run.lock.json')
    if sha256_file(d / 'prompts.jsonl') != lock['artifacts'].get('prompts.jsonl'):
        raise PipelineError('prompts.jsonl differs from run.lock.json; rebuild before running')
    if lock['statements_status'] != 'approved' and not (stub or allow_unreviewed):
        raise PipelineError('statements are not approved; real runs are blocked (use --stub for a dry run)')
    out = d / ('raw_stub' if stub else 'raw')
    out.mkdir(exist_ok=True)
    stages = run_cfg.get('stages', ['forecast'])
    if 'reveal' in stages and not run_cfg.get('stage3_question'):
        raise PipelineError("stage 'reveal' needs stage3_question in the run config")
    convs = [json.loads(l) for l in open(d / 'prompts.jsonl', encoding='utf-8')]
    return run_cfg, d, out, convs, stages


def selected(convs, models=None, samples=None):
    return [c for c in convs if (not models or c['model'] in models)
            and (samples is None or c['sample_idx'] < samples)]


def raw_path(out, c):
    return out / f"{c['model']}__s{c['sample_idx']}.json"


def is_done(out, c, stages):
    p = raw_path(out, c)
    return p.exists() and read_json(p).get('stage_done') == stages[-1]


def new_record(run_cfg, c, prov):
    return {'run_id': run_cfg['run_id'], 'model': c['model'], 'provider': prov, 'effort': c['effort'],
            'sample_idx': c['sample_idx'], 'order': c['order'], 'forecast_sha256': c['forecast_sha256'],
            'started_utc': now(), 'turns': [], 'parse_retry': False, 'stage_done': None}


def run(run_cfg_path, models=None, samples=None, stub=False, allow_unreviewed=False):
    run_cfg, d, out, convs, stages = load_checked(run_cfg_path, stub, allow_unreviewed)
    clients = {}
    for c in selected(convs, models, samples):
        p = raw_path(out, c)
        if is_done(out, c, stages):
            continue
        prov = 'stub' if stub else c['provider']
        llm = clients.setdefault(prov, provider(prov))
        rec = new_record(run_cfg, c, prov)
        messages = [{'role': 'user', 'content': c['forecast_prompt']}]
        rec['turns'].append({'role': 'user', 'text': c['forecast_prompt'], 'utc': now()})
        try:
            text, raw = _turn(llm, c['model'], c['effort'], messages, rec)
            try:
                extract_array(text)
            except ValueError:
                rec['parse_retry'] = True
                messages.append({'role': 'user', 'content': RETRY_MSG})
                rec['turns'].append({'role': 'user', 'text': RETRY_MSG, 'utc': now()})
                text, raw = _turn(llm, c['model'], c['effort'], messages, rec)
            rec['forecast_turn_index'] = len(rec['turns']) - 1
            rec['stage_done'] = 'forecast'
            if 'reveal' in stages:
                messages.append({'role': 'user', 'content': c['reveal_prompt']})
                rec['turns'].append({'role': 'user', 'text': c['reveal_prompt'], 'utc': now()})
                _turn(llm, c['model'], c['effort'], messages, rec)
                rec['stage_done'] = 'reveal'
        except PipelineError:
            raise
        except Exception as e:  # transport/API failure: archive it, do not count the sample
            rec['error'] = f'{type(e).__name__}: {e}'
            write_json(out / f"{c['model']}__s{c['sample_idx']}.error.json", rec)
            print('ERROR', c['model'], c['sample_idx'], rec['error'][:200])
            continue
        rec['finished_utc'] = now()
        write_json(p, rec)
        print('done', c['model'], 's', c['sample_idx'], 'stop:', rec['turns'][-1]['stop_reason'],
              '(retry)' if rec['parse_retry'] else '')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('run_config')
    ap.add_argument('--models', nargs='*')
    ap.add_argument('--samples', type=int)
    ap.add_argument('--stub', action='store_true')
    ap.add_argument('--allow-unreviewed', action='store_true')
    a = ap.parse_args()
    run(a.run_config, a.models, a.samples, a.stub, a.allow_unreviewed)
