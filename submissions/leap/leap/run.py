"""Ask the panel: one Baseline call per panel member, one row per (model, question).

Rows go to <out>/<stamp>.jsonl as each call lands, so one failed model does not
lose the others; the run exits 1 if any call failed. A call's first row carries
what belongs to the whole call under `call`: the sources, the research
evidence, what it cost, the prompt.

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

from . import config, instrument


def ask(member, question_set, today, run_id, *, panel=None, retries=1, harness_run=None, env=None):
    """One call, asked again (up to `retries` times) while any value is
    missing. -> rows, one per question, the first carrying `call`."""
    from fri_forecaster import baseline
    prompt, numbers = instrument.build_prompt(question_set, today)
    submit_cells, submit_forecast = instrument.tools(question_set)
    questions = instrument.numbered(question_set)
    want = instrument.n_values(question_set)
    base = os.environ.get("LEAP_PI_DIR") or os.path.join(tempfile.gettempdir(), "leap-pi")
    attempts, usage = 0, []
    while True:
        attempts += 1
        res = baseline.run(member["model"], prompt,
                           workdir=os.path.join(base, f"{member['key']}-{time.time_ns()}"),
                           cell_schema=instrument.cell_schema(question_set), key_fields=["question"],
                           allowed_keys=numbers, submit_cells=submit_cells, submit_forecast=submit_forecast,
                           env=env, harness_run=harness_run)
        usage.append(res.get("usage") or {})
        cleaned = {n: instrument.clean_cell(q, res["cells"].get(n) or {}) for n, q in questions.items()}
        got = sum(len(vals) for values, _, _ in cleaned.values() for vals in values.values())
        if got >= want or attempts > retries:
            break
        print(f"  retry {member['label']:16} attempt {attempts}: {got}/{want} values", flush=True)
    if not got:
        raise RuntimeError(f"no forecasts after {attempts} attempt(s) (pi exit {res.get('rc')}; trace {res.get('trace')})")
    answer = res.get("answer") or {}
    evidence = [{k: e.get(k) for k in ("tool", "args", "result")} for e in res.get("evidence") or []]
    hits = sum(len((e.get("result") or {}).get("results") or []) for e in evidence if e["tool"] == "web_search")
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    call = {"key_sources": answer.get("key_sources"), "evidence": evidence, "search_hits": hits,
            "grounded": hits > 0, "usage": usage, "cost_usd": round(sum(u.get("cost_usd") or 0 for u in usage), 6),
            "delivery": res.get("delivery"), "attempts": attempts, "values": got, "values_asked": want,
            "prompt": prompt, "system_prompt": baseline.SYSTEM, "reasoning": member.get("reasoning")}
    rows = []
    for i, (number, q) in enumerate(questions.items()):
        values, rationale, problems = cleaned[number]
        rows.append({"run_id": run_id, "run_date": today.isoformat(), "elicited_at": stamp,
                     "benchmark": question_set["benchmark"], "question_set": question_set["question_set"],
                     "condition": config.CONDITION, "model": member["model"], "key": member["key"],
                     "label": member["label"], "question_id": q["id"], "question": number,
                     "values": values, "rationale": rationale, "problems": problems,
                     "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                     "panel": panel, "call_id": f"{run_id}:{member['key']}",
                     "call": call if i == 0 else None})
    return rows


def select_members(args):
    from fri_forecaster import panel
    members, provenance = panel.panel(snapshot_dir=config.ECI_DIR)
    if args.models:
        want = [m.strip() for m in args.models.split(",")]
        by = {m["key"]: m for m in members} | {m["label"]: m for m in members}
        unknown = [w for w in want if w not in by]
        if unknown:
            sys.exit(f"not in the panel: {', '.join(unknown)} (the panel is {', '.join(m['key'] for m in members)})")
        members = [by[w] for w in want]
    return members, provenance


def load_rows(path):
    with open(path, encoding="utf-8") as f:
        # split("\n"), not splitlines(): fetched pages carry U+2028 and the like inside strings.
        return [json.loads(line) for line in f.read().split("\n") if line.strip()]


def main(args, harness_run=None):
    with open(args.questions, encoding="utf-8") as f:
        question_set = json.load(f)
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    members, provenance = select_members(args)
    if harness_run is None:
        from fri_forecaster import keys
        if "TAVILY_API_KEY" not in keys.load_keys() and not args.allow_ungrounded:
            sys.exit("TAVILY_API_KEY is not set: the models would answer from memory with no search. "
                     "Set it (fri_forecaster.keys says where) or pass --allow-ungrounded.")
    os.makedirs(args.out, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    path = os.path.join(args.out, f"{run_id}.jsonl")
    if args.resume:
        # Finish an earlier run: same run id, same run date (so the same
        # prompt), and only the models it does not have yet.
        run_id, path = args.resume, os.path.join(args.out, f"{args.resume}.jsonl")
        if not os.path.exists(path):
            sys.exit(f"--resume {args.resume}: no {path}")
        have = load_rows(path)
        today = date.fromisoformat(have[0]["run_date"])
        done = {r["key"] for r in have}
        members = [m for m in members if m["key"] not in done]
        if not members:
            sys.exit(f"--resume {args.resume}: every selected model has already answered")
    print(f"LEAP {question_set['question_set']} / {config.CONDITION}: {len(question_set['questions'])} questions, "
          f"{instrument.n_values(question_set)} values, {len(members)} model(s): "
          f"{', '.join(m['label'] for m in members)}", flush=True)
    lock, failed, spent = threading.Lock(), [], 0.0

    def one(member):
        rows = ask(member, question_set, today, run_id, panel=provenance, retries=args.retries, harness_run=harness_run)
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
