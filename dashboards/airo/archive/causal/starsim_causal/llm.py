"""OpenRouter client for the bench (litellm underneath, "openrouter/<id>").

Sampling policy — "models as deployed": no temperature, no system prompt, and
no reasoning parameter unless the caller asks for one, so each provider's
defaults apply uniformly through the same API path. max_tokens defaults to
16000 because reasoning tokens count against it on most reasoning models
(4096 truncates).

OPENROUTER_API_KEY is read from ./.env (by default a symlink to
../forecastbench-sim/.env), falling back to that fbsim .env directly.
"""
import os
import time
import warnings
from pathlib import Path

import litellm
from dotenv import load_dotenv

litellm.suppress_debug_info = True
# litellm's logging re-serializes OpenRouter responses through pydantic and
# emits a harmless "Expected 10 fields but got 5" UserWarning per call.
warnings.filterwarnings("ignore", message="Pydantic serializer warnings", category=UserWarning)

REPO = Path(__file__).resolve().parents[1]
ENV_CANDIDATES = (REPO / ".env", REPO.parent / "forecastbench-sim" / ".env")


class InsufficientCredits(Exception):
    """OpenRouter 402 — the whole run must stop; nothing else will succeed."""


class ModelUnavailable(Exception):
    """400/404 — bad id or no provider; skip this model, not the run."""


def load_env() -> None:
    for p in ENV_CANDIDATES:
        if p.exists():
            load_dotenv(p)
            break
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY not set. Put it in .env "
                         f"(looked in {', '.join(map(str, ENV_CANDIDATES))}).")


def _kwargs(model_id: str, prompt: str, max_tokens: int, reasoning: str | None,
            timeout: float) -> dict:
    kw = dict(model=f"openrouter/{model_id}",
              messages=[{"role": "user", "content": prompt}],
              max_tokens=max_tokens, timeout=timeout)
    if reasoning:
        kw["reasoning_effort"] = reasoning  # litellm -> OpenRouter reasoning.effort
    return kw


def _classify(e: Exception) -> Exception:
    s = str(e)
    if isinstance(e, litellm.RateLimitError):
        return e
    code = getattr(e, "status_code", None)
    if code == 402 or "Insufficient credits" in s or '"code":402' in s:
        return InsufficientCredits(s[:400])
    if isinstance(e, (litellm.NotFoundError, litellm.BadRequestError)) or code in (400, 404):
        return ModelUnavailable(s[:400])
    return e


def _unpack(r, t0: float) -> dict:
    msg = r.choices[0].message
    u = r.usage
    det = getattr(u, "completion_tokens_details", None)
    return {
        "text": msg.content or "",
        "finish_reason": r.choices[0].finish_reason,
        "prompt_tokens": getattr(u, "prompt_tokens", None),
        "completion_tokens": getattr(u, "completion_tokens", None),
        "reasoning_tokens": getattr(det, "reasoning_tokens", None) if det else None,
        "cost_usd": getattr(u, "cost", None),
        "response_model": r.model,
        "latency_s": round(time.monotonic() - t0, 2),
    }


async def complete(model_id: str, prompt: str, *, max_tokens: int = 16000,
                   reasoning: str | None = None, timeout: float = 900) -> dict:
    """One chat completion. Raises RateLimitError (retry), InsufficientCredits
    (abort run), ModelUnavailable (skip model), or other litellm errors
    (transient; caller retries)."""
    t0 = time.monotonic()
    try:
        r = await litellm.acompletion(**_kwargs(model_id, prompt, max_tokens, reasoning, timeout))
    except Exception as e:  # noqa: BLE001 — reclassified, then re-raised
        raise _classify(e) from e
    return _unpack(r, t0)


def complete_sync(model_id: str, prompt: str, *, max_tokens: int = 16000,
                  reasoning: str | None = None, timeout: float = 900) -> dict:
    t0 = time.monotonic()
    try:
        r = litellm.completion(**_kwargs(model_id, prompt, max_tokens, reasoning, timeout))
    except Exception as e:  # noqa: BLE001
        raise _classify(e) from e
    return _unpack(r, t0)
