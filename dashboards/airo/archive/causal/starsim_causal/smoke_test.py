"""Smoke-test the OpenRouter key and the roster.

  uv run python results/causal/starsim_causal/smoke_test.py         # key -> /auth/key, /credits, one tiny call on the cheapest roster model
  uv run python results/causal/starsim_causal/smoke_test.py --all   # one tiny call on EVERY roster model (verifies ids are live; cents)

Prints reasoning_tokens per model so you can see which models think by
default under vendor settings — that is what the bench will run with.
"""
import argparse
import asyncio
import os

import httpx

from llm import InsufficientCredits, ModelUnavailable, complete, load_env
from models import load_roster

PROMPT = "Reply with exactly the word OK."


def key_info(key: str) -> None:
    h = {"Authorization": f"Bearer {key}"}
    k = httpx.get("https://openrouter.ai/api/v1/auth/key", headers=h, timeout=30)
    print(f"/auth/key  -> HTTP {k.status_code}", end="")
    if k.status_code == 200:
        d = k.json()["data"]
        print(f"  label={d.get('label')} free_tier={d.get('is_free_tier')} "
              f"usage_monthly=${d.get('usage_monthly', 0):.2f} limit={d.get('limit')}")
    else:
        print(f"  {k.text[:200]}")
    c = httpx.get("https://openrouter.ai/api/v1/credits", headers=h, timeout=30)
    if c.status_code == 200:
        d = c.json()["data"]
        bal = d["total_credits"] - d["total_usage"]
        print(f"/credits   -> purchased=${d['total_credits']:.2f} used=${d['total_usage']:.2f} "
              f"balance=${bal:.2f}" + ("   <-- NO CREDITS: paid models will 402" if bal <= 0 else ""))
    else:
        print(f"/credits   -> HTTP {c.status_code} {c.text[:200]}")


async def ping(m):
    try:
        r = await complete(m.openrouter_id, PROMPT, max_tokens=4000)
        ok = "OK" in (r["text"] or "").upper()
        return (m, "ok" if ok else "odd-reply", r)
    except InsufficientCredits as e:
        return (m, "402 no credits", None)
    except ModelUnavailable as e:
        return (m, f"unavailable: {str(e)[:120]}", None)
    except Exception as e:  # noqa: BLE001
        return (m, f"{type(e).__name__}: {str(e)[:120]}", None)


async def main_async(a):
    models = load_roster()
    if not a.all:
        models = [min(models, key=lambda m: m.prompt_usd_per_m + m.completion_usd_per_m)]
    print(f"\ncompletion smoke test on {len(models)} model(s) via litellm openrouter/...\n")
    res = await asyncio.gather(*(ping(m) for m in models))
    print(f"{'ECI':>6s} {'model':44s} {'status':16s} {'finish':7s} {'tok':>5s} {'rtok':>5s} {'$':>8s} {'s':>5s}  reply")
    for m, status, r in res:
        if r:
            print(f"{m.eci:6.1f} {m.openrouter_id:44s} {status:16s} {str(r['finish_reason']):7s} "
                  f"{r['completion_tokens'] or 0:5d} {str(r['reasoning_tokens']):>5s} "
                  f"{r['cost_usd'] or 0:8.5f} {r['latency_s']:5.1f}  {r['text'][:40]!r}")
        else:
            print(f"{m.eci:6.1f} {m.openrouter_id:44s} {status}")
    bad = [s for _, s, _ in res if s != "ok"]
    print(f"\n{len(res) - len(bad)}/{len(res)} ok")
    return 0 if not bad else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    load_env()
    key_info(os.environ["OPENROUTER_API_KEY"])
    raise SystemExit(asyncio.run(main_async(a)))


if __name__ == "__main__":
    main()
