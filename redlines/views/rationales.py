"""Original explanations attached to the calls used by current charts."""
import hashlib
import json
from collections import defaultdict

from ..experiments import DEFAULT_VARIANT, PUBLISHED, VARIANTS, load as load_experiment
from ..runlog import (load_runlog, complete_panel_rows, latest_instrument_rows,
                      current_rows, elicitation_date)


def _call_id(row):
    return row.get('call_id') or f"{row['run_id']}:{row['label']}"


def _prompt_metadata(row, recorded, prompts):
    """Attach the call's identity and archived wording, never a rebuilt prompt.

    The full prompt is recorded only on a call's first question row. Match the
    configured instruction against that record before presenting it verbatim:
    a later edit to VARIANTS must not rewrite what an earlier call was asked.
    Full prompts are shared across models, so store each (system, user) pair once.
    """
    variant = row.get('variant')
    condition = row.get('condition')
    # The log reader maps old prompt variants into `condition`; never treat a
    # scenario dict or an unrecognized condition as a known prompt variant.
    if not variant and isinstance(condition, str) and condition in VARIANTS:
        variant = condition
    label = ('Baseline' if variant == DEFAULT_VARIANT else variant.capitalize()) if variant else 'Unrecorded'
    instruction = VARIANTS.get(variant)
    full_prompt = recorded.get('prompt') if recorded else None
    prompt_id = None
    if full_prompt:
        prompt = {'system': recorded.get('system_prompt'), 'user': full_prompt}
        prompt_id = hashlib.sha256(json.dumps(prompt, sort_keys=True).encode()).hexdigest()
        prompts[prompt_id] = prompt
    return {
        'condition': condition if isinstance(condition, str) else None,
        'promptVariant': variant, 'promptLabel': label,
        'promptInstruction': instruction if instruction and full_prompt and instruction in full_prompt else None,
        'promptId': prompt_id,
        'promptSha256': recorded.get('prompt_sha256') if recorded else None,
    }


def build():
    all_rows = load_runlog()
    rows = current_rows(complete_panel_rows(latest_instrument_rows(all_rows)))
    debriefs = {r['call_id']: r['debrief'] for r in all_rows if r.get('debrief')}
    recorded = {_call_id(r): r for r in all_rows if r.get('prompt')}
    calls, prompts, questions = {}, {}, defaultdict(lambda: defaultdict(list))
    for r in rows:
        cid = _call_id(r)
        if cid not in calls:
            calls[cid] = _prompt_metadata(r, recorded.get(cid), prompts)
        calls[cid].update({
            'model': r['label'], 'modelId': r['model'], 'run': r['run_id'],
            'elicitedAt': r['elicited_at'], 'date': elicitation_date(r),
            'instrument': r.get('instrument_version'), 'protocol': r.get('protocol'),
            'rationale': r.get('rationale') or '', 'sources': r.get('key_sources') or [],
            'debriefs': debriefs.get(cid, {}),
        })
        ids = questions[r['question_id']][r['label']]
        if cid not in ids:
            ids.append(cid)
    order = {condition: i for i, condition in enumerate(load_experiment(PUBLISHED)['pooled'])}
    for models in questions.values():
        for ids in models.values():
            ids.sort(key=lambda cid: (order.get(calls[cid]['condition'], len(order)),
                                     calls[cid]['elicitedAt'], cid))
    return {'calls': calls, 'questions': dict(questions), 'prompts': prompts}
