#!/usr/bin/env python3
"""Run news-grounded frontier forecasts on the starter question set (issue #1).

ARCHIVED AND UNRUNNABLE — kept for the record, not for use. It imports
`STABLE_SUBSET`, which left redlines/config.py when the Auto-ARC swap retired the
XPT starter set, and its ROOT still resolves as if the file sat in code/. Read it
as history; run code/run_unified.py instead.

Machinery was borrowed from the cruxgen module of an internal FRI checkout
(xrisk-canaries, not published): the `call_tools` agentic loop
plus the shared Tavily/Metaculus grounding tools, so every model used the SAME
search backend (no provider-native-search confound) and every forecast carried an
auditable evidence[] trail. Those two modules were VENDORED into this repo on
2026-08-28 as redlines/llm.py and redlines/tools.py; the imports below still name
their old home, which is the shape the runs in results/ were actually produced
under. Keys then: Anthropic from .env; the rest from GCP Secret Manager via ADC.

Appends one JSONL row per (model, question) to results/forecast_runs.jsonl —
append-only; the dashboard materializes its view from this log.
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import threading
from datetime import date, datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CANARIES = os.path.expanduser("~/Projects/xrisk-canaries")  # internal FRI checkout, not published; see docstring
sys.path.insert(0, CANARIES)
sys.path.insert(0, ROOT)

from forecast.cruxgen._llm import call_tools, load_keys  # noqa: E402
from forecast.cruxgen.tools import FORECAST_TOOLS        # noqa: E402
from redlines.registry import frontier_models             # noqa: E402
from redlines.config import STABLE_SUBSET                 # noqa: E402

QUESTIONS = os.path.join(ROOT, "data", "starter_questions.json")
RUNLOG = os.path.join(ROOT, "results", "forecast_runs.jsonl")

# Frontier ensemble: >=3 labs so the dashboard isn't one lab's worldview.
# (label, litellm id) — fable-5/gpt-5.5/opus-4-8 verified reachable 2026-07-07;
# gemini/grok verified by --probe. Single source of truth: redlines/registry.py
# (ECI 161, 159, 158, 155, 154 respectively).
MODELS = frontier_models()

SYSTEM = """You are a careful probabilistic forecaster producing calibrated
probabilities for catastrophic-risk questions. Ground your forecast in evidence:
use web_search for current events, expert reports, and base rates, and
metaculus_lookup as a cross-check (never copy it). Reason from base rates first,
then adjust. These are low-probability questions — beware both dismissing tail
risk as zero and inflating it for vividness. When done, call submit_forecast."""

PROMPT = """Today is {today}.

Forecast the following question (from the Existential Risk Persuasion Tournament;
its published resolution criteria apply):

{text}

Give your cumulative probability that this occurs BY THE END OF each of these
years: {horizons}. Probabilities must be non-decreasing across horizons.
{quantity_note}
Search for relevant recent developments before answering. Then call
submit_forecast with a probability in [0,1] for each horizon, a 2-4 sentence
rationale, and the key sources you relied on."""

QUANTITY_NOTE = """NOTE: the original question asks "how many times"; forecast
the probability of AT LEAST ONE qualifying event by each horizon instead.
"""


def submit_tool(horizons):
    return {
        "name": "submit_forecast",
        "description": "Submit your final calibrated forecast.",
        "parameters": {
            "type": "object",
            "properties": {
                "forecasts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "horizon": {"type": "string", "enum": horizons},
                            "probability": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "required": ["horizon", "probability"],
                    },
                },
                "rationale": {"type": "string"},
                "key_sources": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["forecasts", "rationale"],
        },
    }


def future_horizons(q):
    return [h for h in q["horizons"] if h and int(h) > date.today().year]


def clean_forecasts(raw):
    """Normalize the submit_forecast payload to a list of dicts, or None.

    Models occasionally hand back the array as a JSON *string* rather than a
    parsed array (seen from Fable 5, 2026-08-10). Left alone it poisons the run
    log: every downstream materializer indexes fc["horizon"] and dies.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, list):
        return None
    ok = [f for f in raw
          if isinstance(f, dict) and "horizon" in f and "probability" in f]
    return ok or None


def run_one(label, model_id, q, run_id):
    horizons = future_horizons(q)
    prompt = PROMPT.format(
        today=date.today().isoformat(), text=q["text"], horizons=", ".join(horizons),
        quantity_note=QUANTITY_NOTE if q.get("value_kind") == "quantity" else "")
    answer, evidence = call_tools(
        model_id, prompt, FORECAST_TOOLS, submit_tool(horizons),
        system=SYSTEM, max_iters=8)
    return {
        "run_id": run_id,
        "elicited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question_id": q["id"],
        "model": model_id,
        "label": label,
        "forecasts": clean_forecasts(answer.get("forecasts")),
        "rationale": answer.get("rationale"),
        "key_sources": answer.get("key_sources"),
        "grounded": bool(evidence),
        "evidence": evidence,
    }


def probe(models):
    """Minimal reachability check per model (reasoning models need token headroom)."""
    import litellm
    litellm.drop_params = True
    for label, mid in models:
        try:
            litellm.completion(model=mid, max_tokens=512,
                               messages=[{"role": "user", "content": "hi"}])
            print(f"  ok       {label:16} {mid}")
        except Exception as e:
            print(f"  FAIL     {label:16} {mid}  {type(e).__name__}: {str(e)[:120]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="one question x one model")
    ap.add_argument("--probe", action="store_true", help="reachability check only")
    ap.add_argument("--models", help="comma-separated label filter")
    ap.add_argument("--only", help="comma-separated question-id prefixes (e.g. '6.,10.')")
    ap.add_argument("--stable", action="store_true",
                    help="shorthand for --only over redlines.config.STABLE_SUBSET "
                         "(the cron job's question set)")
    ap.add_argument("--questions", default=QUESTIONS,
                    help="question-set json (default: the XPT starter set)")
    ap.add_argument("--out", default=RUNLOG,
                    help="run log to append to (default: results/forecast_runs.jsonl). "
                         "Scheduled runs pass their own dated file under results/runs/ "
                         "so two machines never append to the same tracked file.")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    load_keys()
    models = MODELS
    if args.models:
        want = {m.strip().lower() for m in args.models.split(",")}
        models = [(l, m) for l, m in MODELS if l.lower() in want]
    if args.probe:
        return probe(models)

    questions = json.load(open(args.questions))["questions"]
    pre = STABLE_SUBSET if args.stable else (
        tuple(p.strip() for p in args.only.split(",")) if args.only else None)
    if pre:
        questions = [q for q in questions if q["id"].startswith(pre)]
    if args.smoke:
        models, questions = models[:1], questions[:1]

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    jobs = [(l, m, q) for l, m in models for q in questions]
    print(f"run {run_id}: {len(jobs)} forecasts ({len(models)} models x {len(questions)} questions)")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    lock = threading.Lock()
    done = failed = 0
    with open(args.out, "a") as f, cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one, l, m, q, run_id): (l, q["id"]) for l, m, q in jobs}
        for fut in cf.as_completed(futs):
            label, qid = futs[fut]
            try:
                row = fut.result()
            except Exception as e:
                failed += 1
                print(f"  FAIL  {label:16} {qid}: {type(e).__name__}: {str(e)[:120]}")
                continue
            with lock:
                f.write(json.dumps(row) + "\n")
                f.flush()
            done += 1
            # Never let a display problem abort the run — the forecasts are paid for.
            try:
                ps = {fc["horizon"]: fc["probability"] for fc in (row["forecasts"] or [])}
            except Exception:
                ps = f"<unreadable: {str(row['forecasts'])[:60]}>"
            print(f"  done  {label:16} {qid}: {ps} ({len(row['evidence'])} evidence)")
    print(f"{done} ok, {failed} failed -> {args.out}")


if __name__ == "__main__":
    main()
