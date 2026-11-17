"""Ask the panel: one Baseline call per panel member, one row per (model, question).

    python3 -m eeai run                 # the panel; PAID: model and search calls
    python3 -m eeai run --smoke         # the panel's top model only
    python3 -m eeai run --resume RUN_ID # the models that run does not have yet
    python3 -m eeai run --synthetic --out DIR   # no calls: made-up answers, for the page and tests

Rows go to eeai/results/runs/<stamp>.jsonl (config.RUNS) as each call lands, so
one failed model does not lose the others; the run exits 1 if any call failed.
A call's first row carries what belongs to the whole call under `call`: the
Part 1 answers, the sources, the research evidence, what it cost, the prompt.

Search is not optional: without TAVILY_API_KEY every model still answers, from
memory with no current evidence, and the run looks the same from outside, so
the runner refuses unless told --allow-ungrounded.
"""
import concurrent.futures as cf
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
from datetime import date, datetime, timezone

from . import config, instrument, survey as S

# A call that delivers less than this share of the values is asked again.
COMPLETE = 0.9


def ask(member, survey, history, today, run_id, *, panel=None, retries=1, harness_run=None, env=None,
        synthetic=False):
    """One call. -> rows, one per question, the first carrying `call`."""
    from fri_forecaster import baseline
    prompt, qids = instrument.build_prompt(survey, history, today)
    submit_cells, submit_forecast = instrument.tools(survey)
    want = S.n_values(survey, today)
    base = os.environ.get("EEAI_PI_DIR") or os.path.join(tempfile.gettempdir(), "eeai-pi")
    from fri_forecaster.tools import BLOCK_ENV
    blocked = [p for p in (os.environ.get(BLOCK_ENV) or "").replace(",", "\n").split("\n") if p.strip()]
    blocked += [p for p in config.BLOCKED_URLS if p not in blocked]
    env = dict(env or {}, **{BLOCK_ENV: "\n".join(blocked)})
    attempts, usage = 0, []
    while True:
        attempts += 1
        res = baseline.run(member["model"], prompt,
                           workdir=os.path.join(base, f"{member['key']}-{time.time_ns()}"),
                           cell_schema=instrument.cell_schema(survey), key_fields=["question_id"],
                           allowed_keys=qids, submit_cells=submit_cells, submit_forecast=submit_forecast,
                           env=env, harness_run=harness_run)
        usage.append(res.get("usage") or {})
        cleaned = {q["id"]: instrument.clean_cell(survey, q, res["cells"].get(q["id"]) or {}, today)
                   for q in survey["questions"]}
        got = sum(len(ps) for f, _, _ in cleaned.values() for scen in f.values() for ps in scen.values())
        part1, part1_problems = instrument.clean_part1(survey, res.get("answer"))
        if (got >= COMPLETE * want and "scenario_probabilities" in part1) or attempts > retries:
            break
        print(f"  retry {member['label']:16} attempt {attempts}: {got}/{want} values"
              f"{'' if 'scenario_probabilities' in part1 else ', no scenario probabilities'}", flush=True)
    if not got:
        raise RuntimeError(f"no forecasts after {attempts} attempt(s) (pi exit {res.get('rc')}; trace {res.get('trace')})")
    answer = res.get("answer") or {}
    evidence = [{k: e.get(k) for k in ("tool", "args", "result")} for e in res.get("evidence") or []]
    hits = sum(len((e.get("result") or {}).get("results") or []) for e in evidence if e["tool"] == "web_search")
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    call = {"part1": part1, "part1_problems": part1_problems, "rationale": answer.get("rationale"),
            "key_sources": answer.get("key_sources"), "evidence": evidence, "search_hits": hits,
            "grounded": hits > 0, "usage": usage, "cost_usd": round(sum(u.get("cost_usd") or 0 for u in usage), 6),
            "delivery": res.get("delivery"), "attempts": attempts, "values": got, "values_asked": want,
            "prompt": prompt, "system_prompt": baseline.SYSTEM, "reasoning": member.get("reasoning"),
            "blocked_urls": blocked}
    rows = []
    for i, q in enumerate(survey["questions"]):
        forecasts, rationale, problems = cleaned[q["id"]]
        rows.append({"run_id": run_id, "run_date": today.isoformat(), "elicited_at": stamp,
                     "experiment": config.EXPERIMENT, "condition": config.CONDITION,
                     "instrument": survey["instrument"],
                     "model": member["model"], "key": member["key"], "label": member["label"],
                     "question_id": q["id"], "forecasts": forecasts, "rationale": rationale,
                     "problems": problems, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                     "panel": panel, "call_id": f"{run_id}:{member['key']}",
                     **({"synthetic": True} if synthetic else {}),
                     "call": call if i == 0 else None})
    return rows


def select_members(args):
    from fri_forecaster import panel
    members, provenance = panel.panel(snapshot_dir=config.ECI_DIR)
    if args.smoke:
        members = members[:1]
    if args.models:
        want = [m.strip() for m in args.models.split(",")]
        by = {m["key"]: m for m in members} | {m["label"]: m for m in members}
        unknown = [w for w in want if w not in by]
        if unknown:
            sys.exit(f"not in the panel: {', '.join(unknown)} (the panel is {', '.join(m['key'] for m in members)})")
        members = [by[w] for w in want]
    return members, provenance


def main(args):
    survey, history = S.load(), S.history()
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    members, provenance = select_members(args)
    harness_run = None
    if args.synthetic:
        if not args.out:
            sys.exit("--synthetic rows are made up: give them a directory with --out (never results/)")
        from . import synthetic
        harness_run = synthetic.harness_run(survey, history, today)
    else:
        from fri_forecaster import keys
        have = keys.load_keys()
        if "TAVILY_API_KEY" not in have and not args.allow_ungrounded:
            sys.exit("TAVILY_API_KEY is not set: the models would answer from memory with no search. "
                     "Set it (fri_forecaster.keys says where) or pass --allow-ungrounded.")
    runs = args.out or config.RUNS
    os.makedirs(runs, exist_ok=True)
    now = datetime.now(timezone.utc)
    run_id = (f"{today.isoformat()}T0000Z" if args.synthetic else now.strftime("%Y-%m-%dT%H%MZ"))
    path = os.path.join(runs, f"{run_id}.jsonl")
    if args.resume:
        # Finish an earlier run: same run id, same run date (so the same
        # prompt), and only the models it does not have yet.
        run_id, path = args.resume, os.path.join(runs, f"{args.resume}.jsonl")
        if not os.path.exists(path):
            sys.exit(f"--resume {args.resume}: no {path}")
        with open(path, encoding="utf-8") as f:
            have = [json.loads(line) for line in f if line.strip()]
        today = date.fromisoformat(have[0]["run_date"])
        done = {r["key"] for r in have}
        members = [m for m in members if m["key"] not in done]
        if not members:
            sys.exit(f"--resume {args.resume}: every selected model has already answered")
    print(f"{config.EXPERIMENT} / {config.CONDITION} [{survey['instrument']}]: {len(survey['questions'])} questions, "
          f"{S.n_values(survey, today)} values + Part 1, {len(members)} model(s): {', '.join(m['label'] for m in members)}"
          f"{' -- SYNTHETIC, no calls' if args.synthetic else ''}", flush=True)
    lock, failed, spent = threading.Lock(), [], 0.0

    def one(member):
        rows = ask(member, survey, history, today, run_id, panel=provenance, retries=args.retries,
                   harness_run=harness_run, synthetic=args.synthetic)
        with lock, open(path, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return rows

    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(one, m): m for m in members}
        for fut in cf.as_completed(futures):
            m = futures[fut]
            try:
                call = fut.result()[0]["call"]
            except Exception as exc:
                failed.append(m["label"])
                print(f"  FAILED {m['label']:16} {type(exc).__name__}: {str(exc)[:300]}", flush=True)
                continue
            spent += call["cost_usd"]
            turns = sum(u.get("turns") or 0 for u in call["usage"])
            print(f"  done   {m['label']:16} {call['values']}/{call['values_asked']} values, "
                  f"{turns} turns, {call['search_hits']} search hits, ${call['cost_usd']:.2f}", flush=True)
    print(f"{path}: {len(members) - len(failed)} of {len(members)} calls, ${spent:.2f}"
          + (f"; FAILED: {', '.join(failed)}" if failed else ""), flush=True)
    return 1 if failed else 0
