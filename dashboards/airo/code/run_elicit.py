#!/usr/bin/env python3
"""Elicitation calls: a scenario set's elicited quantities (its `elicits`)
asked on their own, with no question grid and no conditions -- one call per
model per repeat (2026-11-18; experiments/acceleration-elicit.toml).

A call is run_cellwise's ECI step, unchanged: the set's definitions, each
elicited quantity's text, the condition's variant and the delivery sentence
(run_cellwise.eci_prompt), its tool (eci_tool), the minimal instrument's
loop and tools, the retry until every quantity is complete and in order
(run_eci, run_unified.clean_elicit). Nothing from any other call is in the
prompt, and no other call sees its answer.

The experiment's conditions have unit = "elicit" (redlines/experiments.py);
run_unified and run_cellwise refuse them.

    python code/run_elicit.py --experiment acceleration-elicit --dry-run   # the prompt; free
    python code/run_elicit.py --experiment acceleration-elicit             # repeats x models paid calls

Rows (one per call) go to results/experiments/<experiment>-<run>.jsonl:
the model, the condition and repeat (`replicate`), `elicited` (each
quantity's numbers), the rationale and sources, the evidence, the prompt and
the call's tokens and price.
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import threading
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "code"))
import run_cellwise as rc  # noqa: E402
import run_unified as ru  # noqa: E402
from redlines import experiments  # noqa: E402

UNIT = "elicit"
# research_tools wants the question groups for web_search's `cause`; the
# minimal tools drop that field, so one placeholder group serves.
GROUPS = [{"key": "elicit", "label": "Elicited quantities"}]


def context(exp, policies, today, run_id, panels):
    """What run_cellwise.run_eci reads."""
    return {"run_id": run_id, "today": today, "spec": {}, "policies": policies, "groups": GROUPS,
            "experiment": exp["name"], "panels": panels}


def run_one(ctx, label, model_id, condition, retries, rep):
    """One elicitation call -> its row (run_eci's, stamped as this unit's)."""
    row = rc.run_eci(ctx, label, model_id, condition, retries, rep)
    slug = ru.set_slug(ctx["policies"])
    return {**row, "unit": UNIT, "step": UNIT, "protocol": f"{UNIT}:{ru.set_protocol(ctx['policies'])}",
            "call_id": (f"{ctx['run_id']}:{slug}:{UNIT}:{label}"
                        + (f":{condition['id']}" if condition["id"] != ru.DEFAULT_VARIANT else "")
                        + (f"#{rep}" if condition["repeats"] > 1 else ""))}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ask a scenario set's elicited quantities alone (see the module docstring).")
    ap.add_argument("--experiment", required=True, help="experiments/<name>.toml; its conditions must have unit = \"elicit\"")
    ap.add_argument("--condition", action="append", default=[], help="run only this condition (repeatable)")
    ap.add_argument("--models", help="comma-separated label filter")
    ap.add_argument("--smoke", action="store_true", help="one model only")
    ap.add_argument("--max-repeats", type=int, default=None, help="ask at most this many of each condition's repeats")
    ap.add_argument("--retries", type=int, default=2, help="re-ask a call that errs or answers unusably")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--allow-ungrounded", action="store_true", help="run a researching condition without Tavily")
    ap.add_argument("--dry-run", action="store_true", help="print each condition's prompt; no model is called")
    args = ap.parse_args(argv)

    try:
        exp = experiments.load(args.experiment)
    except (OSError, ValueError) as e:
        sys.exit(f"experiment {args.experiment!r}: {e}")
    unknown = [c for c in args.condition if c not in exp["conditions"]]
    if unknown:
        sys.exit(f"unknown --condition {unknown}; {exp['name']} has {', '.join(exp['conditions'])}")
    conditions = [exp["conditions"][c] for c in (args.condition or exp["conditions"])]
    other = [c["id"] for c in conditions if c["unit"] != UNIT]
    if other:
        sys.exit(f"refusing: {exp['name']} condition(s) {other} are not elicitation conditions (unit = \"elicit\")")
    if len({c["scenarios"] for c in conditions}) > 1:
        sys.exit("refusing: these conditions ask different scenario sets; run each with its own --condition list")
    path = os.path.join(ROOT, conditions[0]["scenarios"])
    today = datetime.now(timezone.utc).date()
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    policies = ru.resolve_set(ru.load_policies(path), today)
    es = ru.set_elicits(policies)
    if not es:
        sys.exit(f"scenario set {ru.set_slug(policies)!r} elicits nothing")
    for e in es:
        print(f"    elicits {e['key']} {e['fields']}")

    if args.dry_run:
        for c in conditions:
            p = rc.eci_prompt(policies, today, c["variant"])
            print(f"##### {exp['name']} / {c['id']} [{ru.set_slug(policies)}: {UNIT}:{ru.set_protocol(policies)}; "
                  f"{ru.condition_line(c)}]: {len(p)} chars #####")
            print(p)
            print(f"##### URL GUARD ({ru.BLOCK_ENV}): {c['url_block_patterns'] or os.environ.get(ru.BLOCK_ENV) or 'off'} #####")
        return

    panels = {ms: ru.select_models(ms, argparse.Namespace(models=args.models, smoke=args.smoke))
              for ms in dict.fromkeys(c["model_set"] for c in conditions)}
    calls = [(c, label, model, rep) for c in conditions
             for rep in range(1, min(c["repeats"], args.max_repeats or c["repeats"]) + 1)
             for label, model in panels[c["model_set"]][0]]
    print(f"run {run_id} experiment {exp['name']}, protocol {UNIT}:{ru.set_protocol(policies)}: {len(calls)} calls")
    for c in conditions:
        print(f"    {c['id']:12} {ru.condition_line(c)}")
    ru.eci_preflight(path)
    ru.load_keys()
    if any(c["research"] for c in conditions) and not os.environ.get("TAVILY_API_KEY") and not args.allow_ungrounded:
        sys.exit("refusing to run: TAVILY_API_KEY is unset, so every web_search fails and the "
                 "forecasts would be ungrounded.\n  override: --allow-ungrounded")

    exp_dir = os.path.join(ROOT, "results", "experiments")
    os.makedirs(exp_dir, exist_ok=True)
    out = os.path.join(exp_dir, f"{exp['name']}-{run_id}.jsonl")
    ctx = context(exp, policies, today, run_id, {ms: p[1] for ms, p in panels.items()})
    lock = threading.Lock()
    done = failed = 0
    spent = 0.0
    with open(out, "a") as f, cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one, ctx, l, m, c, args.retries, rep): (c, l, rep) for c, l, m, rep in calls}
        for fut in cf.as_completed(futs):
            c, l, rep = futs[fut]
            tag = f"{l}:{c['id']}#{rep}"
            try:
                row = fut.result()
            except Exception as e:
                failed += 1
                print(f"  FAIL  {tag}: {type(e).__name__}: {str(e)[:160]}")
                continue
            with lock:
                f.write(json.dumps(row) + "\n")
                f.flush()
            done += 1
            spent = ru.tally_spend(spent, [row])
            got = {e["key"]: row["elicited"][e["key"]] for e in es}
            print(f"  done  {tag} {got}, {ru.usage_line([row])}")
    print(f"{done} ok, {failed} failed, ${spent:.2f} priced spend -> {out}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
