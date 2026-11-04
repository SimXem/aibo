"""Problem statements (D10): drafted once by a pinned model from the T0 docstring + Lean statement,
checked by a human who does not see the outcome, then frozen in statements/<key>.json.

The cache key contains the FC blob SHA at T0, so a statement can only ever come from T0 text.

Drafting runs through the Message Batches API (asynchronous, half price; usually < 1 h, max 24 h):

    python -m pipeline.statements submit  config/runs/<run>.yaml          # one batch for all missing drafts
    python -m pipeline.statements collect config/runs/<run>.yaml --wait   # -> review/<run>__<batch>_review_queue.csv
    python -m pipeline.statements ingest  review/<file>.csv               # approved rows -> frozen cache

Batch IDs, request parameters and prompt hashes are kept in review/<run>_batches.json. Failed or expired
requests are listed there; running `submit` again resubmits only those.

Review checklist (all must hold to approve; write 'yes' in checklist_ok and your name in reviewer):
  1. every quantifier, hypothesis and constant of the Lean statement is present;
  2. nothing about history, attribution, partial results, difficulty or solution status;
  3. at most the configured number of words;
  4. where docstring and Lean differ, the text follows Lean.
"""
import argparse
import datetime as dt
import re
import sys

from . import fc
from .common import (ROOT, STATEMENTS, PipelineError, hash_rank, load_run_config, read_csv, read_json, run_dir,
                     sha256_text, write_csv, write_json)
from .snapshot import CatFile

REVIEW_FIELDS = ['key', 'unit_id', 'display_name', 'docstrings', 'lean', 'draft', 'approved_text', 'reviewer', 'checklist_ok']


def key_of(unit):
    return re.sub(r'[^A-Za-z0-9]+', '_', unit['unit_id']).strip('_') + '@' + unit['fc_blob_t0'][:12]


def path_of(key):
    return STATEMENTS / f'{key}.json'


def source_text(unit, rules):
    """Docstrings and Lean statements of the headline theorems, from the T0 blob."""
    cf = CatFile(fc.REPO)
    try:
        _, text = cf.get(unit['fc_blob_t0'])
    finally:
        cf.close()
    decls, _, _ = fc.parse_lean(text, rules)
    names = unit['headline'].split(';')
    ds = [d for n in names for d in decls if d['name'] == n]
    if len(ds) != len(names):
        raise PipelineError(f"{unit['unit_id']}: headline theorem not found in T0 blob")
    return '\n\n'.join(d['doc'] for d in ds if d['doc']), '\n\n'.join(d['stmt'] for d in ds)


def fallback_text(docstrings, max_words=80):
    """Deterministic cleanup used only for --allow-unreviewed dry runs."""
    t = re.sub(r'\$+', '', docstrings)
    t = re.sub(r'\\(mathbb|mathrm|operatorname|text)\{([^}]*)\}', r'\2', t)
    t = ' '.join(t.split())
    w = t.split()
    return ' '.join(w[:max_words]) + (' ...' if len(w) > max_words else '')


def lookup(units):
    """-> (found {unit_id: text}, missing [unit])"""
    found, missing = {}, []
    for u in units:
        p = path_of(key_of(u))
        if p.exists():
            rec = read_json(p)
            if rec.get('approved'):
                found[u['unit_id']] = rec['approved_text']
                continue
        missing.append(u)
    return found, missing


DRAFT_MAX_TOKENS = 16000


def _state_path(run):
    return ROOT / 'review' / f"{run['run_id']}_batches.json"


def _state(run):
    p = _state_path(run)
    return read_json(p) if p.exists() else {'batches': []}


def _client():
    import anthropic
    from .llm import load_env
    load_env()
    return anthropic.Anthropic(max_retries=5)


def _sampled_units(run):
    d = run_dir(run)
    sample_ids = {r['unit_id'] for r in read_csv(d / 'sample.csv')}
    return [u for u in read_csv(d / 'frame.csv') if u['unit_id'] in sample_ids]


def submit(run_cfg_path):
    """Submit one Message Batch with a draft request for every sampled statement that is not yet
    approved, not waiting in an uncollected batch, and not already drafted into a review queue."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    run, wave, rules = load_run_config(run_cfg_path)
    cfg = wave['statements']
    if cfg['drafter']['provider'] != 'anthropic':
        raise PipelineError('batch drafting is implemented for the anthropic provider only')
    _, missing = lookup(_sampled_units(run))
    st = _state(run)
    taken = {k for b in st['batches'] for k in (b['keys'].values() if not b.get('collected') else b.get('drafted', []))}
    todo = [u for u in missing if key_of(u) not in taken]
    if not todo:
        print('nothing to submit (all sampled statements approved, drafted, or in a pending batch)'); return
    tmpl = (ROOT / cfg['template']).read_text(encoding='utf-8')
    params_common = {'model': cfg['drafter']['id'], 'max_tokens': DRAFT_MAX_TOKENS}
    effort = cfg['drafter'].get('effort', 'high')       # 'default' = vendor default (not sent)
    if effort != 'default':
        params_common['output_config'] = {'effort': effort}
    requests, keys, prompt_sha = [], {}, {}
    for i, u in enumerate(sorted(todo, key=key_of)):
        docs, lean = source_text(u, rules)
        prompt = tmpl.format(max_words=cfg['drafter']['max_words'], display_name=u['display_name'],
                             docstrings=docs or '(none)', lean=lean)
        cid = f'r{i:03d}'                       # custom_id allows only [A-Za-z0-9_-]; map back via `keys`
        keys[cid], prompt_sha[cid] = key_of(u), sha256_text(prompt)
        requests.append(Request(custom_id=cid, params=MessageCreateParamsNonStreaming(
            **params_common, messages=[{'role': 'user', 'content': prompt}])))
    batch = _client().messages.batches.create(requests=requests)
    st['batches'].append({'batch_id': batch.id, 'created_utc': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
                          'params': params_common, 'template': cfg['template'], 'template_sha256': sha256_text(tmpl),
                          'keys': keys, 'prompt_sha256': prompt_sha, 'collected': False})
    _state_path(run).parent.mkdir(exist_ok=True)
    write_json(_state_path(run), st)
    print(f'submitted batch {batch.id} with {len(requests)} draft requests; '
          f'collect with: python -m pipeline.statements collect {run_cfg_path} --wait')


def collect(run_cfg_path, wait=False, poll_seconds=60):
    """Fetch finished batches and write one blind review queue CSV per batch."""
    import time
    run, wave, rules = load_run_config(run_cfg_path)
    st = _state(run)
    if not any(not b['collected'] for b in st['batches']):
        return                                   # nothing pending: no client, no credentials needed
    client = _client()
    units = {key_of(u): u for u in _sampled_units(run)}
    for b in [b for b in st['batches'] if not b['collected']]:
        while True:
            info = client.messages.batches.retrieve(b['batch_id'])
            if info.processing_status == 'ended' or not wait:
                break
            c = info.request_counts
            print(f"{b['batch_id']}: {info.processing_status} (processing {c.processing}, succeeded {c.succeeded})")
            time.sleep(poll_seconds)
        if info.processing_status != 'ended':
            print(f"{b['batch_id']}: {info.processing_status}; not collected (use --wait to poll)")
            continue
        rows, failed = [], {}
        for res in client.messages.batches.results(b['batch_id']):
            key = b['keys'][res.custom_id]
            r = res.result
            if r.type != 'succeeded':
                failed[key] = r.type
                continue
            msg = r.message
            text = ''.join(x.text for x in msg.content if x.type == 'text').strip()
            if msg.stop_reason != 'end_turn' or not text:
                failed[key] = f'stop_reason={msg.stop_reason}'
                continue
            u = units[key]
            docs, lean = source_text(u, rules)
            rows.append({'key': key, 'unit_id': u['unit_id'], 'display_name': u['display_name'],
                         'docstrings': docs, 'lean': lean, 'draft': text, 'approved_text': text,
                         'reviewer': '', 'checklist_ok': '',
                         '_meta': {'drafter_model': msg.model, 'drafter_prompt_sha256': b['prompt_sha256'][res.custom_id],
                                   'template': b['template'], 'batch_id': b['batch_id'], 'custom_id': res.custom_id,
                                   'request_params': b['params']}})
        # Blind review: no outcome columns; order by hash, not by sample role.
        rows.sort(key=lambda r: hash_rank(wave['seed'], 'review|' + r['key']))
        out = ROOT / 'review' / f"{run['run_id']}__{b['batch_id']}_review_queue.csv"
        if out.exists():
            raise PipelineError(f'{out} exists; refusing to overwrite a review file')
        if rows:
            write_csv(out, rows, REVIEW_FIELDS)
            write_json(out.with_suffix('.meta.json'), {r['key']: r['_meta'] for r in rows})
        b.update(collected=True, collected_utc=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
                 drafted=sorted(r['key'] for r in rows), failed=failed, review_file=out.name if rows else None)
        write_json(_state_path(run), st)
        print(f"{b['batch_id']}: {len(rows)} drafts -> {out.name if rows else '(none)'}; {len(failed)} failed"
              + (f' {failed} (run submit again to retry them)' if failed else ''))
        if rows:
            print(f'review, then: python -m pipeline.statements ingest {out}')


def ingest(csv_path):
    meta_p = csv_path.with_suffix('.meta.json')
    meta = read_json(meta_p) if meta_p.exists() else {}
    n = 0
    for r in read_csv(csv_path):
        if r['checklist_ok'].strip().lower() not in ('yes', 'y', '1', 'true') or not r['reviewer'].strip():
            continue
        if not r['approved_text'].strip():
            raise PipelineError(f"{r['key']}: approved but empty text")
        p = path_of(r['key'])
        if p.exists() and read_json(p).get('approved_text') != r['approved_text'].strip():
            raise PipelineError(f'{p} exists with different text; frozen statements are never overwritten')
        STATEMENTS.mkdir(exist_ok=True)
        write_json(p, {'key': r['key'], 'unit_id': r['unit_id'], 'approved': True,
                       'approved_text': r['approved_text'].strip(), 'draft': r['draft'],
                       'source_docstrings': r['docstrings'], 'source_lean': r['lean'],
                       'reviewer': r['reviewer'].strip(), 'checklist_ok': True,
                       'approved_utc': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
                       **meta.get(r['key'], {})})
        n += 1
    print(f'{n} statements frozen in {STATEMENTS}')



AUTO_REVIEWER = 'none (auto-approved, no human review)'


def auto_approve(run_cfg_path):
    """No-human-review path (used by pipeline.stage_prepare): freeze every collected draft that has no
    statement file yet, with the draft text as approved text. Each file is marked auto_approved and
    records an automatic word-count check; nothing else is checked (quantifiers, attribution etc.)."""
    run, wave, _ = load_run_config(run_cfg_path)
    max_words = wave['statements']['drafter']['max_words']
    n = over = 0
    for b in _state(run)['batches']:
        if not b.get('collected') or not b.get('review_file'):
            continue
        csv_path = ROOT / 'review' / b['review_file']
        meta_p = csv_path.with_suffix('.meta.json')
        meta = read_json(meta_p) if meta_p.exists() else {}
        for r in read_csv(csv_path):
            p = path_of(r['key'])
            text = r['draft'].strip()
            if p.exists() or not text:
                continue
            words = len(text.split())
            over += words > max_words
            STATEMENTS.mkdir(exist_ok=True)
            write_json(p, {'key': r['key'], 'unit_id': r['unit_id'], 'approved': True, 'auto_approved': True,
                           'approved_text': text, 'draft': r['draft'],
                           'source_docstrings': r['docstrings'], 'source_lean': r['lean'],
                           'reviewer': AUTO_REVIEWER, 'checklist_ok': False,
                           'auto_checks': {'words': words, 'max_words': max_words, 'over_word_limit': words > max_words},
                           'approved_utc': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
                           **meta.get(r['key'], {})})
            n += 1
    print(f'{n} statements auto-approved without human review ({over} over the {max_words}-word limit)')
    return n


def approval_status(units):
    """'approved' if every statement was human-reviewed, else 'auto-approved (no human review)'."""
    auto = any(read_json(path_of(key_of(u))).get('auto_approved') for u in units if path_of(key_of(u)).exists())
    return 'auto-approved (no human review)' if auto else 'approved'


if __name__ == '__main__':
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['submit', 'collect', 'ingest'])
    ap.add_argument('path', help='run config (submit/collect) or review CSV (ingest)')
    ap.add_argument('--wait', action='store_true', help='collect: poll until the batch has ended')
    a = ap.parse_args()
    if a.cmd == 'submit':
        submit(a.path)
    elif a.cmd == 'collect':
        collect(a.path, a.wait)
    else:
        ingest(Path(a.path))
    sys.exit(0)
