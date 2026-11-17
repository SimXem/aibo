"""Provider adapters. Each `chat()` takes the conversation so far and returns
(assistant_turn_for_history, text, record) where `record` is the full raw response for the archive.

Study rules applied here:
- No sampling parameters are sent (temperature etc. are rejected by current Claude models; "default").
- `effort` is sent only if the wave config sets it; otherwise the model default applies and is logged.
- No refusal fallbacks: a fallback would silently swap the model that produced a forecast.
  Refusals are returned as-is and recorded.
- Assistant turns are appended unchanged (including thinking blocks), as the API requires.
API keys come from the environment or `.env`; they are never logged.
"""
import json
import os

from .common import ROOT, PipelineError

MAX_TOKENS = 64000

# The models get no tools: no web search, web fetch or code execution, so they cannot look anything up.
# Every request is checked against this list; anything else (e.g. `tools`) stops the run.
ALLOWED_REQUEST_KEYS = {'model', 'max_tokens', 'messages', 'output_config',   # Anthropic
                        'input', 'reasoning'}                                    # OpenAI Responses


def check_no_tools(params):
    extra = set(params) - ALLOWED_REQUEST_KEYS
    if extra:
        raise PipelineError(f'request parameters not allowed in this study: {sorted(extra)} (models get no tools)')
    return params


def load_env():
    p = ROOT / '.env'
    if not p.exists():
        return
    for line in p.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Anthropic:
    def __init__(self):
        import anthropic
        load_env()
        self.sdk = anthropic
        self.client = anthropic.Anthropic(max_retries=5)

    def chat(self, model, messages, effort=None):
        kwargs = {'model': model, 'max_tokens': MAX_TOKENS, 'messages': messages}
        if effort and effort != 'default':
            kwargs['output_config'] = {'effort': effort}
        with self.client.messages.stream(**check_no_tools(kwargs)) as stream:
            msg = stream.get_final_message()
        text = ''.join(b.text for b in msg.content if b.type == 'text')
        rec = {'response': msg.to_dict(), 'request_id': getattr(msg, '_request_id', None),
               'returned_model': msg.model, 'stop_reason': msg.stop_reason,
               'request_params': {k: v for k, v in kwargs.items() if k != 'messages'}}
        turn = {'role': 'assistant', 'content': [b.to_dict() for b in msg.content]}
        return turn, text, rec


class OpenAI:
    """Responses API. UNTESTED: no key was available when this was written."""

    def __init__(self):
        import openai
        load_env()
        self.client = openai.OpenAI(max_retries=5)

    def chat(self, model, messages, effort=None):
        kwargs = {'model': model, 'input': messages}
        if effort and effort != 'default':
            kwargs['reasoning'] = {'effort': effort}
        resp = self.client.responses.create(**check_no_tools(kwargs))
        text = resp.output_text
        rec = {'response': resp.to_dict(), 'request_id': getattr(resp, '_request_id', None),
               'returned_model': resp.model, 'stop_reason': getattr(resp, 'status', None),
               'request_params': {k: v for k, v in kwargs.items() if k != 'input'}}
        return {'role': 'assistant', 'content': text}, text, rec


class Stub:
    """Deterministic offline model for dry runs: answers every forecast with fixed dates."""

    def chat(self, model, messages, effort=None):
        import re
        last = messages[-1]['content'] if isinstance(messages[-1]['content'], str) else ''
        codes = re.findall(r'^\[(P[0-9A-F]{5})\]', last, re.M)
        text = json.dumps([{'id': c, 'best': '2030-01', 'q10': '2027-01', 'q90': 'after-2100'} for c in codes]) if codes else 'OK'
        rec = {'response': {'stub': True}, 'request_id': None, 'returned_model': f'stub:{model}',
               'stop_reason': 'end_turn', 'request_params': {'model': model}}
        return {'role': 'assistant', 'content': text}, text, rec


def provider(name):
    if name == 'anthropic':
        return Anthropic()
    if name == 'openai':
        return OpenAI()
    if name == 'stub':
        return Stub()
    raise PipelineError(f'unknown provider {name}')
