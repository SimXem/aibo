#!/usr/bin/env python3
"""Run ONE forecasting call through pi (badlogic/earendil pi coding agent)
instead of our own loop, on the same prompt, the same tools and the same
condition set, and write rows in the same schema -- the pi side-by-side
trial (project lead, 2026-09-02).

    ~/Projects/xrisk-canaries/.venv/bin/python code/pi_harness/run_pi.py \
        --model anthropic/claude-fable-5 --label "Fable 5" --thinking max \
        --conditions data/combined_conditions.json \
        --out results/experiments/pi_trial/<stamp>.jsonl

What is the same: the prompt and system text (run_unified.build_prompt_joint,
SYSTEM), the questions, the conditions, the tool implementations
(tool_cli.py -> redlines.tools), the research floor, the cell cleaning and
the row schema. What differs: the loop. pi drives the model, handles the
provider, retries and the context; its JSON event stream is the trace, kept
whole beside the rows (events.jsonl) and folded into `evidence` and `usage`.

Since 2026-10-05 the loop itself is the FRI Forecaster package
(fri_forecaster: harness.py + pi_tools.ts, github.com/forecastingresearch/
fri-forecaster, private for now), shared with the ForecastBench runs; this
file is the AIRO side: prompt, conditions, cell cleaning and the row schema.
It is the ONLY AIRO file that needs the package -- install it into the venv
that runs this (`pip install -e ../fri-forecaster`, or
`pip install git+ssh://git@github.com/forecastingresearch/fri-forecaster.git`).
AIRO's core does not depend on it: main is published to a public repo.

Rows carry protocol "pi-joint-<slug>-v1" and experiment "pi-trial", so no
view ever pools them with the cron's series.
"""
import argparse
import importlib.util
import json
import os
import sys
from datetime import date, datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

try:
    from fri_forecaster import harness  # noqa: E402
except ImportError:  # optional: AIRO's cron, tests and rebuild never need it
    harness = None

# One AIRO cell: a question at a horizon, probabilities keyed by condition.
CELL_SCHEMA = {"type": "object", "required": ["question_id", "horizon", "probabilities"],
               "properties": {"question_id": {"type": "string"}, "horizon": {"type": "string"},
                              "probabilities": {"type": "object",
                                                "additionalProperties": {"type": "number", "minimum": 0, "maximum": 1}}}}
KEY_FIELDS = ["question_id", "horizon"]


def load_runner():
    spec = importlib.util.spec_from_file_location("run_unified", os.path.join(ROOT, "code", "run_unified.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="pi model id, e.g. anthropic/claude-fable-5")
    ap.add_argument("--label", required=True, help="the dashboard label, e.g. 'Fable 5'")
    ap.add_argument("--thinking", default="max", help="pi thinking level: off|minimal|low|medium|high|xhigh|max")
    ap.add_argument("--conditions", default=os.path.join(ROOT, "data", "combined_conditions.json"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", default=None, help="where the trace and pieces go (default: beside --out)")
    ap.add_argument("--pi", default=harness.DEFAULT_PI if harness else None)
    ap.add_argument("--experiment", default="pi-trial")
    ap.add_argument("--groups", default=None, help="comma-separated question groups to keep (a cheap partial call)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if harness is None:
        sys.exit("run_pi.py needs the FRI Forecaster package (fri_forecaster); see the docstring")

    ru = load_runner()
    from redlines.llm import load_keys
    from redlines.questions import resolves_on
    load_keys()
    today = date.today()
    policies = ru.resolve_set(ru.load_policies(args.conditions), today)
    conds = list(policies["conditions"])
    groups, by_group, horizons, skipped, spec = ru.load_batch(ru.LADDER, ru.CROSS, ru.UNBATCHED)
    if args.groups:
        keep = args.groups.split(",")
        unknown = [k for k in keep if k not in by_group]
        if unknown:
            sys.exit(f"unknown groups {unknown}; have {list(by_group)}")
        groups = [g for g in groups if g["key"] in keep]
    horizons = ru.set_horizons(policies, horizons)
    prompt, n, want_cells = ru.build_prompt_joint(groups, by_group, horizons, spec, conds, policies, today)
    qids = [q["id"] for g in groups for q in by_group[g["key"]]]
    allowed = {q["id"]: [h for h in horizons if h in q["horizons"]] for g in groups for q in by_group[g["key"]]}
    cond_ids = [c["id"] for c in conds]
    elicits = ru.set_elicits(policies)
    slug = ru.set_slug(policies)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    work = args.workdir or os.path.join(os.path.dirname(os.path.abspath(args.out)), f"{stamp}-{args.label.replace(' ', '_')}")
    final_tool = ru.submit_tool_joint(qids, horizons, cond_ids, elicits)
    cells_tool = ru.submit_cells_tool(qids, horizons, cond_ids)
    harness_args = dict(
        cell_schema=CELL_SCHEMA, key_fields=KEY_FIELDS,
        allowed_keys=[f"{q}|{h}" for q, hs in allowed.items() for h in hs],
        tool_descriptions={"web_search": ru.FORECAST_TOOLS[0]["description"],
                           "read_page": ru.FORECAST_TOOLS[1]["description"],
                           "submit_cells": cells_tool["description"],
                           "submit_forecast": final_tool["description"]},
        min_research=ru.MIN_RESEARCH,
        final_extra={e["key"]: {"type": "object", "additionalProperties": {"type": "number"}} for e in elicits})
    print(f"pi trial [{slug}] {args.label} ({args.model}, thinking {args.thinking}): {n} questions, "
          f"{want_cells} cells x {len(conds) + 1} keys, prompt {len(prompt)} chars -> {work}")
    if args.dry_run:
        harness.write_spec(work, **harness_args)
        open(os.path.join(work, "prompt.txt"), "w").write(prompt)
        open(os.path.join(work, "system.txt"), "w").write(ru.SYSTEM)
        cmd = harness.pi_command(args.model, ru.SYSTEM, prompt, thinking=args.thinking, pi=args.pi)
        print(" ".join(cmd[:-2]), "<prompt>")
        return
    res = harness.run(model=args.model, system=ru.SYSTEM, prompt=prompt, workdir=work,
                      thinking=args.thinking, pi=args.pi, **harness_args)
    print(f"  pi exited {res['rc']} after {res['seconds']:.0f}s")
    evidence, usage, delivery, answer = res["evidence"], res["usage"], res["delivery"], res["answer"]
    turns = usage["turns"]
    answer["forecasts"] = list(res["cells"].values())
    grids = ru.clean_forecasts_joint(answer.get("forecasts"), {q: set(h) for q, h in allowed.items()}, horizons, cond_ids)
    got = sum(len(v) for g in (grids or {}).values() for v in g.values())
    elicited = {e["key"]: ru.clean_elicit(answer.get(e["key"]), e) for e in elicits} if elicits else None
    print(f"  {got}/{want_cells * (len(conds) + 1)} cells x conditions; delivery {delivery}; "
          f"elicited {[k for k, v in (elicited or {}).items() if v]}; {len(evidence)} evidence; "
          f"{turns} turns; ${usage['cost_usd']}")
    read = {(e.get("args") or {}).get("url") for e in evidence if e["tool"] == "read_page"}
    unread = [u for u in (answer.get("key_sources") or []) if isinstance(u, str) and u not in read]
    hits = sum(len((e.get("result") or {}).get("results") or []) for e in evidence if e["tool"] == "web_search" and isinstance(e.get("result"), dict))
    block = ru.conditions_block(conds, policies)
    import hashlib
    sha = hashlib.sha256(block.encode()).hexdigest()
    cgroups = {g["key"]: g for g in ru.set_groups(policies)}
    stamps = {ru.UNCONDITIONAL_KEY: None}
    for c in conds:
        g = cgroups.get(c.get("group")) if cgroups else None
        stamps[c["id"]] = {"id": c["id"], "leap_id": c.get("leap_id"), "label": c["label"],
                           "source": ((g or {}).get("source") or {}).get("wave") or policies["source"]["wave"],
                           "sha256": sha, "set": slug, **({"group": c["group"]} if cgroups else {})}
        if c.get("value") is not None:
            stamps[c["id"]]["value"] = c["value"]
        elif c.get("field"):
            key = c.get("elicit") or (elicits[0]["key"] if elicits else None)
            stamps[c["id"]]["value"] = ((elicited or {}).get(key) or {}).get(c["field"])
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_id = stamp
    call_id = f"{run_id}:pi#1:{args.label}"
    rows, first = [], True
    for key in [ru.UNCONDITIONAL_KEY] + cond_ids:
        grid = (grids or {}).get(key) or {}
        for g in groups:
            for q in by_group[g["key"]]:
                rows.append({
                    "run_id": run_id, "elicited_at": at, "question_id": q["id"], "model": args.model,
                    "label": args.label, "forecasts": grid.get(q["id"]),
                    "rationale": answer.get("rationale"), "key_sources": answer.get("key_sources"),
                    "grounded": hits > 0, "search_hits": hits,
                    "evidence": evidence if first else [], "usage": usage if first else None,
                    "delivery": dict(delivery) if first else None, "unread_sources": unread if first else None,
                    "resolves_on": {h: resolves_on(h, today, spec) for h in horizons},
                    "run_date": today.isoformat(), "protocol": f"pi-joint-{slug}-v1",
                    "condition_set": slug, "call_id": call_id, "attempts": 1, "batch_size": len(qids),
                    "cause": q.get("cause"), "group": g["key"], "asked_horizons": q.get("horizons"),
                    "raw_forecasts": (None if grids else answer.get("forecasts")) if first else None,
                    "condition": stamps[key],
                    "elicited": ({**(elicited or {}), "target_date": next((e.get("target_date") for e in elicits if e.get("target_months")), elicits[0].get("target_date") if elicits else None),
                                  "targets": {e["key"]: e.get("target_date") for e in elicits}} if elicits else None),
                    "experiment": args.experiment, "arm": "pi#1",
                    "joint_conditions": [ru.UNCONDITIONAL_KEY] + cond_ids,
                    "panel": None, "harness": {"name": "pi", "thinking": args.thinking, "trace": os.path.relpath(res["trace"], ROOT)},
                })
                first = False
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"  {len(rows)} rows -> {args.out}")


if __name__ == "__main__":
    main()
