#!/usr/bin/env python3
"""Joint severity-ladder elicitation — the coherence experiment (issue #8).

The production runner of the time (`archive/legacy-questions/run_forecasts.py`)
asks each ladder rung in its own call: 7 rungs x 4 causes x 5 models = 140
independent forecasts. About 10% of adjacent rung pairs come back incoherent
(P rises as the death threshold rises).
Two control runs (2026-08-05, 2026-08-10) each produced exactly 34 violations,
but only 4 of the 34 pairs repeat across them — the incoherence moves. That
points at independent sampling, not a held belief.

This runner asks all 7 rungs of one cause in ONE call, so the model sees the
whole ladder while it answers. Two arms:

    b   joint context only        — no monotonicity instruction
    c   joint context + the rule  — states "P must not increase as the threshold
                                    rises", mirroring the horizon rule that
                                    run_forecasts.py's PROMPT already carries

b and c stay separate on purpose. If b works, the app-wide lesson is "batch
related questions". If only c works, the lesson is "state the constraint",
which is cheaper and does not need batching.

Rung question text is copied VERBATIM from data/severity_ladder_questions.json,
so the elicited quantity is identical to the control arm and the runs compare.

Writes to results/experiments/ — never to results/forecast_runs.jsonl, so no
tracked artifact and no golden test is touched. One row per (model, cause)
call; code/analyze_ladder_joint.py expands them to per-rung rows for the audit.

Run with any interpreter that has the acquisition extra installed
(`pip install -e '.[acquire]'` — it pulls in litellm, the only third-party
dependency the runners need; `python3 -m redlines build` still needs none):

    python code/run_ladder_joint.py --arm b --smoke
    python code/run_ladder_joint.py --arm b
    python code/run_ladder_joint.py --arm c
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import threading
from datetime import date, datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from redlines.llm import call_tools, load_keys           # noqa: E402
from redlines.tools import FORECAST_TOOLS                # noqa: E402
from redlines.registry import frontier_models             # noqa: E402

LADDER = os.path.join(ROOT, "data", "severity_ladder_questions.json")
OUTDIR = os.path.join(ROOT, "results", "experiments")

MODELS = frontier_models()

# Identical to run_forecasts.py's SYSTEM. The arms must differ in ONE place
# only — the user prompt — or we cannot attribute the effect. (2026-09-02: the
# metaculus_lookup clause left with the tool; see redlines/tools.py.)
SYSTEM = """You are a careful probabilistic forecaster producing calibrated
probabilities for catastrophic-risk questions. Ground your forecast in evidence:
use web_search for current events, expert reports, and base rates, and read_page
to read a source in full. Reason from base rates first,
then adjust. These are low-probability questions — beware both dismissing tail
risk as zero and inflating it for vividness. When done, call submit_forecast."""

PROMPT = """Today is {today}.

Below are {n} questions about the SAME cause of catastrophe: {cause}. They differ
only in the death threshold. Forecast all of them together, in one pass.

{blocks}
Give your cumulative probability that each occurs BY THE END OF each of these
years: {horizons}. Probabilities must be non-decreasing across horizons.
{rule}
Search for relevant recent developments before answering. One search pass covers
all {n} thresholds — you do not need to search per threshold. Then call
submit_forecast once, with a probability in [0,1] for every threshold x horizon
pair ({cells} in total), a 2-4 sentence rationale covering the whole ladder, and
the key sources you relied on."""

# Arm C only. Arm B gets "" here — its whole treatment is the shared context.
RULE = """A higher death threshold is a strictly harder event to reach, so within
a horizon your probabilities must be non-increasing as the threshold rises:
P(≥1k) ≥ P(≥100k) ≥ P(≥1M) ≥ P(≥10M) ≥ P(≥100M) ≥ P(≥1B) ≥ P(extinction).
"""


def submit_tool(rungs, horizons, causes=None):
    """causes is None for one-cause calls; a list when every cause is batched."""
    item = {
        "rung": {"type": "string", "enum": rungs},
        "horizon": {"type": "string", "enum": horizons},
        "probability": {"type": "number", "minimum": 0, "maximum": 1},
    }
    req = ["rung", "horizon", "probability"]
    if causes:
        item = {"cause": {"type": "string", "enum": causes}, **item}
        req = ["cause"] + req
    return {
        "name": "submit_forecast",
        "description": "Submit your final calibrated forecast for the whole ladder.",
        "parameters": {
            "type": "object",
            "properties": {
                "forecasts": {
                    "type": "array",
                    "items": {"type": "object", "properties": item, "required": req},
                },
                "rationale": {"type": "string"},
                "key_sources": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["forecasts", "rationale"],
        },
    }


def future_horizons(qs):
    """Horizons still open, in the question set's own order (all rungs agree)."""
    return [h for h in qs[0]["horizons"] if h and int(h) > date.today().year]


def clean_forecasts(raw, rungs, horizons, causes=None):
    """Normalize submit_forecast's payload to a grid, or None.

    -> {rung: {horizon: p}} for a one-cause call, or {cause: {rung: {horizon: p}}}
    when every cause is batched into one call.

    Same JSON-string defence as run_forecasts.py::clean_forecasts (Fable 5 has
    handed the array back as a string), plus a drop of any cell naming a rung or
    horizon we did not ask for. A partial grid is kept — the audit checks
    adjacent pairs and tolerates gaps, exactly as graph2.build does.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, list):
        return None
    grid = {}
    for f in raw:
        if not isinstance(f, dict):
            continue
        r, h, p = f.get("rung"), f.get("horizon"), f.get("probability")
        if r not in rungs or h not in horizons or not isinstance(p, (int, float)):
            continue
        if causes:
            c = f.get("cause")
            if c not in causes:
                continue
            grid.setdefault(c, {}).setdefault(r, {})[h] = p
        else:
            grid.setdefault(r, {})[h] = p
    return grid or None


def build_prompt(cause_qs, cause_label, horizons, arm, order):
    """The one place the arms differ, plus the rung ordering knob."""
    qs = list(cause_qs)
    if order == "shuffled":
        # Fixed, seedless reordering: present the ladder out of severity order so
        # a coherent answer cannot come from mechanically filling a decreasing
        # list. Deterministic (no RNG) so the run stays reproducible.
        qs = [qs[i] for i in (3, 0, 5, 2, 6, 1, 4)[:len(qs)]]
    blocks = "".join(
        f"--- Threshold {q['rung']} (question id {q['id']}) ---\n{q['text']}\n\n"
        for q in qs)
    return PROMPT.format(
        today=date.today().isoformat(), n=len(qs), cause=cause_label,
        blocks=blocks, horizons=", ".join(horizons),
        rule=(RULE if arm == "c" else ""), cells=len(qs) * len(horizons))


ALL_PROMPT = """Today is {today}.

Below are {n} questions covering {ncauses} causes of catastrophe, each asked at
{nrungs} death thresholds. Forecast all of them together, in one pass.

{blocks}
Give your cumulative probability that each occurs BY THE END OF each of these
years: {horizons}. Probabilities must be non-decreasing across horizons.
{rule}
Search for relevant recent developments before answering. One search pass covers
every cause — you do not need to search per cause or per threshold. Then call
submit_forecast once, with a probability in [0,1] for every cause x threshold x
horizon cell ({cells} in total), a 2-4 sentence rationale, and the key sources
you relied on."""

ALL_RULE = """Two constraints your numbers must satisfy. Within a cause, a higher
death threshold is a strictly harder event, so probability must be non-increasing
as the threshold rises. And "All causes" contains every specific cause, so at any
given threshold and horizon no specific cause may exceed it.
"""


def build_all_prompt(by_cause, causes, horizons, arm, order):
    """One prompt covering every cause, so cross-cause nesting is in context too."""
    blocks, n = "", 0
    for c in causes:
        qs = by_cause[c["key"]]
        if order == "shuffled":
            qs = [qs[i] for i in (3, 0, 5, 2, 6, 1, 4)[:len(qs)]]
        blocks += f"===== CAUSE: {c['label']} (cause key: {c['key']}) =====\n\n"
        for q in qs:
            blocks += (f"--- Threshold {q['rung']} (question id {q['id']}) ---\n"
                       f"{q['text']}\n\n")
            n += 1
    return ALL_PROMPT.format(
        today=date.today().isoformat(), n=n, ncauses=len(causes),
        nrungs=len(by_cause[causes[0]["key"]]), blocks=blocks,
        horizons=", ".join(horizons), rule=(ALL_RULE if arm == "c" else ""),
        cells=n * len(horizons))


def run_all(label, model_id, by_cause, causes, horizons, run_id, arm, order):
    """One call per MODEL — every cause, every rung, every horizon."""
    rungs = [q["rung"] for q in by_cause[causes[0]["key"]]]
    keys = [c["key"] for c in causes]
    prompt = build_all_prompt(by_cause, causes, horizons, arm, order)
    answer, evidence = call_tools(
        model_id, prompt, FORECAST_TOOLS, submit_tool(rungs, horizons, keys),
        system=SYSTEM, max_iters=8, max_tokens=32000)
    grid = clean_forecasts(answer.get("forecasts"), rungs, horizons, keys)
    call_id = f"{run_id}:{label}:all"
    rows = []
    for c in causes:
        rows.append({
            "run_id": run_id, "arm": arm, "order": order, "scope": "all",
            "call_id": call_id,
            "elicited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cause": c["key"], "cause_label": c["label"],
            "rungs": rungs, "horizons": horizons,
            "model": model_id, "label": label,
            "grid": (grid or {}).get(c["key"]) or None,
            "raw_forecasts": None if grid else answer.get("forecasts"),
            "rationale": answer.get("rationale"),
            "key_sources": answer.get("key_sources"),
            "grounded": bool(evidence),
            # Evidence belongs to the CALL, not the cause. Attaching it to every
            # row would quadruple the file and quadruple any per-call count.
            "evidence": evidence if c is causes[0] else [],
        })
    return rows


def run_one(label, model_id, cause, cause_qs, horizons, run_id, arm, order):
    rungs = [q["rung"] for q in cause_qs]
    prompt = build_prompt(cause_qs, cause["label"], horizons, arm, order)
    answer, evidence = call_tools(
        model_id, prompt, FORECAST_TOOLS, submit_tool(rungs, horizons),
        system=SYSTEM, max_iters=8, max_tokens=12000)
    grid = clean_forecasts(answer.get("forecasts"), rungs, horizons)
    return {
        "run_id": run_id,
        "arm": arm,
        "order": order,
        "elicited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cause": cause["key"],
        "cause_label": cause["label"],
        "rungs": rungs,
        "horizons": horizons,
        "model": model_id,
        "label": label,
        "grid": grid,
        # Keep the unparsed payload when the grid comes back empty. Gemini 3.1 Pro
        # searched seven times on (arm c, ai) and then submitted nothing; without
        # this we cannot tell a refusal from a schema mismatch. Batching makes
        # that worth knowing — one empty submission now costs 7 rungs, not 1.
        "raw_forecasts": None if grid else answer.get("forecasts"),
        "rationale": answer.get("rationale"),
        "key_sources": answer.get("key_sources"),
        "grounded": bool(evidence),
        "evidence": evidence,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=("b", "c"), required=True,
                    help="b = joint context only; c = joint context + the "
                         "non-increasing rule")
    ap.add_argument("--scope", choices=("cause", "all"), default="cause",
                    help="cause = one call per (model, cause), 21 cells each. "
                         "all = ONE call per model covering every cause, 84 "
                         "cells — the only scope that puts the cross-cause "
                         "nesting constraint (no cause may exceed 'all causes') "
                         "in context.")
    ap.add_argument("--order", choices=("ladder", "shuffled"), default="ladder",
                    help="rung presentation order (default: ascending severity). "
                         "'shuffled' checks whether a coherent answer survives "
                         "when the list cannot be filled in mechanically.")
    ap.add_argument("--smoke", action="store_true", help="one cause x one model")
    ap.add_argument("--models", help="comma-separated label filter")
    ap.add_argument("--causes", help="comma-separated cause keys (e.g. 'ai,nuclear')")
    ap.add_argument("--questions", default=LADDER)
    ap.add_argument("--out", help="output jsonl (default: results/experiments/"
                                  "joint_<arm>_<run_id>.jsonl)")
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args()

    load_keys()
    models = MODELS
    if args.models:
        want = {m.strip().lower() for m in args.models.split(",")}
        models = [(l, m) for l, m in MODELS if l.lower() in want]

    spec = json.load(open(args.questions))
    causes = spec["causes"]
    if args.causes:
        want = {c.strip() for c in args.causes.split(",")}
        causes = [c for c in causes if c["key"] in want]
    rung_order = [r["rung"] for r in spec["rungs"]]
    by_cause = {}
    for c in causes:
        qs = [q for q in spec["questions"] if q["cause"] == c["key"]]
        by_cause[c["key"]] = sorted(qs, key=lambda q: rung_order.index(q["rung"]))
    horizons = future_horizons(spec["questions"])

    if args.smoke:
        # Under scope=all the whole point is that every cause rides in one call,
        # so smoke narrows the MODEL list only.
        models = models[:1]
        if args.scope != "all":
            causes = causes[:1]

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    tag = args.arm if args.scope == "cause" else f"{args.arm}all"
    out = args.out or os.path.join(OUTDIR, f"joint_{tag}_{run_id}.jsonl")
    if args.scope == "all":
        jobs = [(l, m, None) for l, m in models]
        cells = len(causes) * len(rung_order) * len(horizons)
        print(f"run {run_id} arm {args.arm} scope ALL order {args.order}: "
              f"{len(jobs)} calls ({len(models)} models x 1), "
              f"{cells} cells each")
    else:
        jobs = [(l, m, c) for l, m in models for c in causes]
        print(f"run {run_id} arm {args.arm} order {args.order}: {len(jobs)} calls "
              f"({len(models)} models x {len(causes)} causes), "
              f"{len(rung_order)} rungs x {len(horizons)} horizons each")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    lock = threading.Lock()
    done = failed = 0
    with open(out, "a") as f, cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        if args.scope == "all":
            futs = {ex.submit(run_all, l, m, by_cause, causes, horizons,
                              run_id, args.arm, args.order): (l, "all")
                    for l, m, _ in jobs}
        else:
            futs = {ex.submit(run_one, l, m, c, by_cause[c["key"]], horizons,
                              run_id, args.arm, args.order): (l, c["key"])
                    for l, m, c in jobs}
        for fut in cf.as_completed(futs):
            label, ckey = futs[fut]
            try:
                got = fut.result()
            except Exception as e:
                failed += 1
                print(f"  FAIL  {label:16} {ckey}: {type(e).__name__}: {str(e)[:120]}")
                continue
            batch = got if isinstance(got, list) else [got]
            with lock:
                for row in batch:
                    f.write(json.dumps(row) + "\n")
                f.flush()
            done += 1
            row = batch[0] if len(batch) == 1 else None
            if row is None:
                for r in batch:
                    g = r["grid"] or {}
                    cells_n = sum(len(v) for v in g.values())
                    shown = " ".join(
                        f"{k}={g[k][horizons[-1]]:g}" for k in rung_order
                        if k in g and horizons[-1] in g[k])
                    print(f"  done  {label:16} {r['cause']:8}: {cells_n} cells "
                          f"| {horizons[-1]}: {shown}")
                continue
            # A display problem must never abort the run — the calls are paid for.
            try:
                grid = row["grid"] or {}
                cells = sum(len(v) for v in grid.values())
                shown = {r: grid.get(r, {}).get(horizons[-1]) for r in rung_order}
                summary = " ".join(f"{r}={shown[r]}" for r in rung_order
                                   if shown.get(r) is not None)
            except Exception:
                cells, summary = 0, f"<unreadable: {str(row['grid'])[:60]}>"
            print(f"  done  {label:16} {ckey}: {cells} cells, "
                  f"{len(row['evidence'])} evidence | {horizons[-1]}: {summary}")
    print(f"{done} ok, {failed} failed -> {out}")


if __name__ == "__main__":
    main()
