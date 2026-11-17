#!/usr/bin/env python3
"""Smoke eval of the pandemic low-prob corpus — is the tail bias like FreeCiv?

Batches each run's threshold questions under one Day-20 situation report, queries a
model ladder across the ECI range, and scores calibration/BSS on the rare-event set.
Hardened: per-provider concurrency limits, retry/backoff, temperature-aware calls,
refusal-tolerant (Anthropic frontier models sometimes refuse pandemic-death prompts).

    cd $FBSIM_ROOT/worlds/pandemic && uv run python <redlines>/code/pandemic_smoke.py
"""
from __future__ import annotations
import os
import argparse, asyncio, json, os, sys
from collections import defaultdict
from pathlib import Path

FBSIM = Path(os.environ.get("FBSIM_ROOT", os.path.expanduser("~/Projects/forecastbench-sim")))
for p in (FBSIM / "worlds" / "freeciv", FBSIM / "worlds" / "freeciv" / "src",
          FBSIM / "packages" / "fbsim-core"):
    sys.path.insert(0, str(p))
import litellm
litellm.drop_params = True
from fbsim_core.evaluation.models import LiteLLMModel, load_api_keys_from_gcp
from fbsim_core.evaluation import models as _fbmodels
for _m in ("claude-opus-4-8", "claude-fable-5", "claude-opus-4-6", "gpt-5.5", "claude-opus-5", "gpt-5.6-sol"):
    try: _fbmodels.MODELS_WITHOUT_TEMPERATURE.add(_m)
    except AttributeError:
        if _m not in _fbmodels.MODELS_WITHOUT_TEMPERATURE: _fbmodels.MODELS_WITHOUT_TEMPERATURE.append(_m)
from freeciv_world.evaluation.parallel_evaluator import parse_batch_probabilities

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from redlines.registry import MODELS as _MODELS  # noqa: E402

# (litellm model_id, label, ECI) -- ECI now comes from redlines/registry.py's
# CSV join (data/epoch_capabilities_index_2026-07-07.csv), not hand-typed.
# Cross-checked against the previous hand-typed values: all 9 matched exactly
# (114, 127, 129, 133, 137, 143, 147, 150, 156) -- no corrections were needed.
SMOKE_MODELS = [
    (m["litellm_id"], m["label"], m["eci"])
    for m in sorted((m for m in _MODELS if "pandemic_smoke" in m["roles"]),
                    key=lambda m: m["eci"])
]
# claude-fable-5 (161) & claude-opus-4-8 (158) REFUSE pandemic-death forecasting even with
# the synthetic-sim disclaimer (finish_reason=refusal) — a genuine finding; excluded to score.
PROVIDER_LIMITS = {"openai": 16, "anthropic": 4, "deepinfra": 6, "gemini": 6, "xai": 6, "default": 3}

DISCLAIMER = (
    "NOTE: This is a synthetic epidemiological SIMULATION exercise (a Starsim model). "
    "No real people are involved; the agents are simulated. Please answer the forecasting "
    "questions with numeric probabilities.\n\n")


def build_prompt(report: str, questions: list[dict]) -> str:
    qs = "\n".join(f"{i+1}. {q['question_text']}" for i, q in enumerate(questions))
    return (
        DISCLAIMER +
        "You are an expert epidemic forecaster, familiar with the work of Tetlock and "
        "compartmental (SIR) epidemic models. Read the situation report and forecast.\n"
        "You MUST give a probability between 0 and 1 for each question.\n\n"
        f"## Situation report\n{report}\n\n## Questions\n{qs}\n\n"
        "End your response with one probability per line, in order, in this exact format:\n"
        "<<<PROBABILITIES>>>\n0.05\n0.02\n<<<END>>>")


def provider_of(mid): return mid.split("/", 1)[0]


def score(preds_by_model, model_ids):
    out = {}
    for mid in model_ids:
        pairs = [t for t in preds_by_model[mid] if t[0] is not None]
        if not pairs:
            out[mid] = {"n": 0}; continue
        n = len(pairs)
        brier = sum((p - y) ** 2 for p, y, _ in pairs) / n
        brier_clim = sum((c - y) ** 2 for _, y, c in pairs) / n
        bss = 1 - brier / brier_clim if brier_clim > 0 else None
        mp = sum(p for p, _, _ in pairs) / n
        mo = sum(y for _, y, _ in pairs) / n
        bins = defaultdict(list)
        for p, y, _ in pairs:
            bins[min(9, int(p * 10))].append((p, y))
        ece = sum(len(v) / n * abs(sum(p for p, _ in v) / len(v) - sum(y for _, y in v) / len(v))
                  for v in bins.values())
        out[mid] = {"n": n, "brier": brier, "bss": bss, "mean_pred": mp,
                    "mean_obs": mo, "ece": ece}
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=REPO / "results" / "pandemic" / "corpus.json")
    ap.add_argument("--limit-runs", type=int, default=0)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=90.0,
                    help="seconds per call; GPT-5.5 reasons for ~100s on these prompts, so pass 300 for it")
    ap.add_argument("--models", nargs="*", help="litellm ids to run (default: every pandemic_smoke model)")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "pandemic",
                    help="output dir for smoke_metrics.json + smoke_preds.json")
    args, _unknown = ap.parse_known_args()
    smoke_models = [m for m in SMOKE_MODELS if not args.models or m[0] in args.models]
    if args.models and len(smoke_models) != len(args.models):
        missing = set(args.models) - {m[0] for m in smoke_models}
        raise SystemExit(f"not in the pandemic_smoke role: {sorted(missing)}")

    doc = json.load(open(args.corpus))
    reports, questions = doc["reports"], doc["questions"]
    by_run = defaultdict(list)
    for q in questions:
        by_run[q["run_id"]].append(q)
    runs = list(by_run)
    if args.limit_runs:
        runs = runs[:args.limit_runs]
    print(f"pandemic smoke: {len(runs)} runs, {sum(len(by_run[r]) for r in runs)} questions, "
          f"{len(smoke_models)} models")

    load_api_keys_from_gcp()
    models = [(LiteLLMModel(id=mid), mid, lbl, eci) for mid, lbl, eci in smoke_models]
    sems = {p: asyncio.Semaphore(n) for p, n in PROVIDER_LIMITS.items()}
    preds_by_model = {mid: [] for _, mid, _, _ in models}
    refusals = defaultdict(int)
    errors = defaultdict(int)          # exception class -> count, printed at the end
    lock = asyncio.Lock()

    async def call_model(model, mid, prompt, k):
        sem = sems.get(provider_of(mid), sems["default"])
        kw = {"temperature": 0.0} if getattr(model, "supports_temperature", True) else {}
        for attempt in range(args.retries):
            async with sem:
                try:
                    resp = await asyncio.wait_for(model.get_response_async(prompt, **kw), timeout=args.timeout)
                    probs = parse_batch_probabilities(resp, k)
                    if any(p is not None for p in probs):
                        return probs
                except Exception as e:
                    errors[f"{mid} {type(e).__name__}"] += 1
                    if "refus" in str(e).lower():
                        refusals[mid] += 1; return [None] * k
            await asyncio.sleep(1.5 * (attempt + 1) ** 2)
        return [None] * k

    async def do_run(run_id):
        qs = by_run[run_id]
        prompt = build_prompt(reports[run_id], qs)
        async def q_model(model, mid):
            probs = await call_model(model, mid, prompt, len(qs))
            async with lock:
                for q, p in zip(qs, probs):
                    preds_by_model[mid].append(
                        (p, 1.0 if q["ground_truth"] else 0.0, q["class_base_rate"]))
        await asyncio.gather(*(q_model(m, mid) for m, mid, _, _ in models))

    done = 0
    for coro in asyncio.as_completed([do_run(r) for r in runs]):
        await coro; done += 1
        if done % 10 == 0:
            print(f"  ...{done}/{len(runs)} runs")

    metrics = score(preds_by_model, [mid for _, mid, _, _ in models])
    print("\n=== PANDEMIC tail-risk smoke (deaths-threshold corpus) ===")
    print(f"{'model':12s} {'ECI':>4} {'n':>5} {'Brier':>7} {'BSS':>8} {'meanP':>6} {'obs':>6} {'ECE':>6}  refus")
    for _, mid, lbl, eci in models:
        m = metrics[mid]
        if not m.get("n"):
            print(f"{lbl:12s} {eci:>4}  (no preds; refusals={refusals[mid]})"); continue
        print(f"{lbl:12s} {eci:>4} {m['n']:>5} {m['brier']:>7.4f} {(m['bss'] or 0):>8.2f} "
              f"{m['mean_pred']:>6.3f} {m['mean_obs']:>6.3f} {m['ece']:>6.3f}  {refusals[mid]}")
    if errors:
        print("errors:", dict(errors))
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / "smoke_metrics.json"
    json.dump({"metrics": {lbl: metrics[mid] for _, mid, lbl, _ in models},
               "refusals": {mid: refusals[mid] for _, mid, _, _ in models}},
              open(out, "w"), indent=2, default=str)
    # per-question predictions (for calibration-curve building in the demo)
    labels = {mid: lbl for _, mid, lbl, _ in models}
    ecis = {mid: eci for _, mid, _, eci in models}
    preds_out = {mid: {"label": labels[mid], "eci": ecis[mid],
                       "samples": [[p, y, c] for (p, y, c) in preds_by_model[mid] if p is not None]}
                 for _, mid, _, _ in models}
    pout = args.out / "smoke_preds.json"
    json.dump(preds_out, open(pout, "w"))
    print(f"wrote {out}\nwrote {pout}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
