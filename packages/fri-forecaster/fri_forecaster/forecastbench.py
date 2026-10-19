#!/usr/bin/env python3
"""Forecast a ForecastBench question set with the FRI Forecaster (pi harness)
and write forecast sets ready to upload.

Two steps, both resumable:

  run     forecast every question with ONE member (a model, a thinking
          level, research on or off) and cache it under
          <root>/members/<member>/. A member's folder carries a manifest
          (model, thinking, research, prompts, question set, pi version);
          resuming with different settings is refused.

  build   combine members into one forecast set: the per-cell MEAN of the
          members that answered it (pre-committed 2026-10-05; the median
          was the alternative). One member = a single-model arm. Writes
          <root>/<due>.<org>.<N>.json and fails (exit 1) below the 95%
          coverage rule.

    M=openai-codex/gpt-6-astra
    python -m fri_forecaster.forecastbench run   --root R --model $M
    python -m fri_forecaster.forecastbench run   --root R --model $M --no-research
    python -m fri_forecaster.forecastbench build --root R --set-number 2 \
        --member $M --name "<leaderboard name>" --org "<team name>"   # -> <due>.<team-name>.<N>.json

Submission rules (wiki: How-to-submit-to-ForecastBench): the question set
`<due>-llm.json` appears at 00:00 UTC on the due date (every two weeks), the
forecast set is due by 23:59:59 UTC the same day, at most 3 sets per round
per person, >=95% of market AND dataset questions answered (missing = 0.5),
file name `<due>.<org>.<N>.json`.

One pi call per question per member: market questions want one forecast,
dataset questions one per resolution date. Each attempt gets a fresh
folder (harness.new_attempt_dir), so a retry never reads an older answer.
"""
import argparse
import hashlib
import json
import os
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from fri_forecaster import harness
from fri_forecaster.keys import load_keys

QSETS = "https://raw.githubusercontent.com/forecastingresearch/forecastbench-datasets/main/datasets/question_sets"
MARKET = {"kalshi", "manifold", "metaculus", "polymarket", "infer"}
DATASET = {"acled", "dbnomics", "fred", "wikipedia", "yfinance"}

SYSTEM = """You are a careful, calibrated forecaster. You will be given one forecasting question and must give a probability that it resolves Yes.

Work like a superforecaster: establish the base rate, find the latest relevant facts with web_search and read_page (read the pages that matter, then search again on what they say), weigh the evidence, and avoid both overconfidence and timidity. Probabilities are scored with the Brier score, so extreme values are rewarded only when the evidence warrants them.

When you are done, call submit_forecast exactly once with one forecast per resolution date asked for, a short rationale, and the URLs you relied on in key_sources."""

SYSTEM_NO_RESEARCH = SYSTEM.replace(
    "find the latest relevant facts with web_search and read_page (read the pages that matter, then search again on what they say), ",
    "use what you know, ").replace(", and the URLs you relied on in key_sources", "")

TOOL_DESCRIPTIONS = {
    "web_search": "Search the web. Returns titles, URLs, snippets and dates. Use `recent_days` to restrict to recent news.",
    "read_page": "Read the text of one web page (in windows: pass `offset` to continue a long page).",
    "submit_forecast": "Submit your final forecasts: one {resolution_date, probability} per resolution date asked for (resolution_date 'final' for a market question), plus your rationale. Call once, at the end.",
}

CELL_SCHEMA = {"type": "object", "required": ["resolution_date", "probability"],
               "properties": {"resolution_date": {"type": "string"},
                              "probability": {"type": "number", "minimum": 0, "maximum": 1}}}


def load_question_set(src):
    if src.startswith("http") or not os.path.exists(src):
        url = src if src.startswith("http") else f"{QSETS}/{src}"
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.load(r)
    return json.load(open(src))


def questions_of(qset):
    """Single questions only: sets before 2025-10-26 carry combination questions (list ids)."""
    return [q for q in qset["questions"] if not isinstance(q.get("id"), list)]


def is_market(q):
    return q["source"] in MARKET or q.get("resolution_dates") in ("N/A", None, [])


def sample_of(qs, n):
    """n questions, half market and half dataset, evenly spaced through each
    (so the sources vary). Deterministic: every member gets the same ones."""
    def spread(xs, k):
        return [xs[i * len(xs) // k] for i in range(k)] if k < len(xs) else xs
    market = [q for q in qs if is_market(q)]
    dataset = [q for q in qs if not is_market(q)]
    k = min(n // 2, len(market))
    return spread(market, k) + spread(dataset, min(n - k, len(dataset)))


def dates_of(q):
    return ["final"] if is_market(q) else list(q["resolution_dates"])


def _field(q, k):
    v = q.get(k)
    return None if v in (None, "", "N/A") else v


def build_prompt(q, due):
    dates = dates_of(q)
    text = q["question"]
    if not is_market(q):
        text = text.replace("{forecast_due_date}", due).replace("{resolution_date}", "the resolution date")
    lines = [f"Today is {due}.", "", f"Question ({q['source']}): {text}", ""]
    for label, k in (("Source", "source_intro"), ("Resolution criteria", "resolution_criteria"),
                     ("Market resolution criteria", "market_info_resolution_criteria"),
                     ("Background", "background"), ("Market closes", "market_info_close_datetime"),
                     ("URL", "url")):
        if _field(q, k) is not None:
            lines.append(f"{label}: {q[k]}")
    if _field(q, "freeze_datetime_value") is not None:
        lines.append(f"Value on {str(q.get('freeze_datetime', ''))[:10]}: {q['freeze_datetime_value']} "
                     f"({q.get('freeze_datetime_value_explanation') or ''})")
    lines.append("")
    if is_market(q):
        lines.append("Give one forecast with resolution_date \"final\": the probability the question resolves Yes.")
    else:
        lines.append("Give one forecast for EACH of these resolution dates (the probability the question resolves Yes "
                     "when evaluated on that date): " + ", ".join(dates))
    return "\n".join(lines)


PROMPT_VERSION = "fb-v1"   # bump when SYSTEM / build_prompt change


def slug(s):
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in s)


def member_dir(root, model, thinking, research):
    return os.path.join(root, "members", slug(f"{model}--{thinking}--{'research' if research else 'noresearch'}"))


def manifest_of(qset, model, thinking, research, min_research, pi):
    system = SYSTEM if research else SYSTEM_NO_RESEARCH
    return {"model": model, "thinking": thinking, "research": research,
            "min_research": min_research if research else 0,
            "question_set": qset["question_set"],
            "question_set_sha256": hashlib.sha256(json.dumps(qset, sort_keys=True).encode()).hexdigest(),
            "system_sha256": hashlib.sha256(system.encode()).hexdigest(),
            "prompt_version": PROMPT_VERSION, "pi": pi, "pi_version": harness.pi_version(pi)}


def check_manifest(path, want):
    """Write the manifest on first use; refuse to resume under different settings."""
    if os.path.exists(path):
        have = json.load(open(path))
        diff = {k: (have.get(k), want[k]) for k in want if have.get(k) != want[k]}
        if diff:
            sys.exit(f"{path}: this member was run with different settings, refusing to resume: {diff}")
    else:
        json.dump(want, open(path, "w"), indent=1)


def read_results(log):
    """results.jsonl -> {(source, id): most complete attempt}. Skips a torn last line."""
    results = {}
    if not os.path.exists(log):
        return results
    for line in open(log):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        k = (r["source"], str(r["id"]))
        if k not in results or len(r["probabilities"]) >= len(results[k]["probabilities"]):
            results[k] = r
    return results


def complete(r):
    return bool(r) and set(r["wanted"]) <= set(r["probabilities"])


def forecast_one(q, due, mdir, args):
    dates = dates_of(q)
    research = not args.no_research
    res = harness.run(model=args.model, system=SYSTEM if research else SYSTEM_NO_RESEARCH,
                      prompt=build_prompt(q, due),
                      workdir=os.path.join(mdir, "calls", slug(f"{q['source']}__{q['id']}")),
                      cell_schema=CELL_SCHEMA, key_fields=["resolution_date"], allowed_keys=dates,
                      cells_tool=False, tool_descriptions=TOOL_DESCRIPTIONS,
                      research_tools=harness.RESEARCH_TOOLS if research else (),
                      min_research=args.min_research if research else 0,
                      thinking=args.thinking, pi=args.pi, timeout=args.timeout)
    probs = {}
    for d in dates:
        c = res["cells"].get(d)
        p = c.get("probability") if c else None
        if isinstance(p, (int, float)) and not isinstance(p, bool) and 0 <= p <= 1:
            probs[d] = float(p)
    return {"id": q["id"], "source": q["source"], "probabilities": probs, "wanted": dates,
            "rationale": res["answer"].get("rationale"), "rc": res["rc"], "usage": res["usage"],
            "n_evidence": len(res["evidence"]), "attempt": os.path.relpath(res["workdir"], mdir)}


def coverage(qset, results):
    """Share of market and dataset questions with every wanted forecast (the 95% rule)."""
    out = {}
    for kind, pred in (("market", is_market), ("dataset", lambda q: not is_market(q))):
        qs = [q for q in questions_of(qset) if pred(q)]
        out[kind] = (sum(1 for q in qs if complete(results.get((q["source"], str(q["id"]))))), len(qs))
    return out


def combine(qset, members):
    """{member: results} -> {(source, id): result} with each cell the MEAN of
    the members that answered it; `n_members` per cell is kept."""
    out = {}
    for q in questions_of(qset):
        k = (q["source"], str(q["id"]))
        rs = [m[k] for m in members.values() if k in m]
        if not rs:
            continue
        probs, n = {}, {}
        for d in dates_of(q):
            vals = [r["probabilities"][d] for r in rs if d in r["probabilities"]]
            if vals:
                probs[d] = sum(vals) / len(vals)
                n[d] = len(vals)
        out[k] = {"id": q["id"], "source": q["source"], "wanted": dates_of(q), "probabilities": probs,
                  "n_members": n, "rationale": rs[0].get("rationale") if len(rs) == 1 else None}
    return out


def file_org(org):
    """ForecastBench's file-name form of the team name: 'Example Team' -> 'example-team'."""
    return "-".join(org.lower().split())


def build_forecast_set(qset, results, org, name, model_org, reasoning=False):
    """The upload: one row per (question, resolution date) we have a forecast for."""
    rows = []
    for q in questions_of(qset):
        r = results.get((q["source"], str(q["id"])))
        if not r:
            continue
        for d in r["wanted"]:
            if d in r["probabilities"]:
                rows.append({"id": q["id"], "source": q["source"], "forecast": r["probabilities"][d],
                             "resolution_date": None if d == "final" else d,
                             "reasoning": r.get("rationale") if reasoning else None})
    return {"organization": org, "model": name, "model_organization": model_org,
            "question_set": qset["question_set"], "forecasts": rows}


def validate(fs, qset):
    """Problems that would make ForecastBench reject or mis-score the set."""
    errs = []
    if set(fs) != {"organization", "model", "model_organization", "question_set", "forecasts"}:
        errs.append(f"keys {sorted(fs)}")
    if fs["question_set"] != qset["question_set"]:
        errs.append("question_set mismatch")
    wanted = {(q["source"], str(q["id"]), None if d == "final" else d) for q in questions_of(qset) for d in dates_of(q)}
    seen = set()
    for r in fs["forecasts"]:
        k = (r["source"], str(r["id"]), r["resolution_date"])
        if k not in wanted:
            errs.append(f"unknown forecast {k}")
        if k in seen:
            errs.append(f"duplicate forecast {k}")
        seen.add(k)
        if not (isinstance(r["forecast"], float) and 0 <= r["forecast"] <= 1):
            errs.append(f"bad forecast value {k}: {r['forecast']!r}")
    return errs[:20]


def cmd_run(args):
    harness.pi_argv(args.pi)             # no pi: fail here, not once per question
    load_keys()
    root = os.path.abspath(args.root)
    os.makedirs(root, exist_ok=True)
    qpath = os.path.join(root, "question_set.json")
    if os.path.exists(qpath):            # a round's root is pinned to one question set
        qset = json.load(open(qpath))
        if args.question_set != "latest-llm.json" and load_question_set(args.question_set)["question_set"] != qset["question_set"]:
            sys.exit(f"{root} holds {qset['question_set']}; use another --root")
    else:
        qset = load_question_set(args.question_set)
        json.dump(qset, open(qpath, "w"))
    due = qset["forecast_due_date"]
    research = not args.no_research
    mdir = member_dir(root, args.model, args.thinking, research)
    os.makedirs(mdir, exist_ok=True)
    check_manifest(os.path.join(mdir, "manifest.json"),
                   manifest_of(qset, args.model, args.thinking, research, args.min_research, args.pi))
    qs = questions_of(qset)[: args.limit]
    if args.sample:
        qs = sample_of(qs, args.sample)
    log = os.path.join(mdir, "results.jsonl")
    results = read_results(log)
    todo = [q for q in qs if not complete(results.get((q["source"], str(q["id"]))))]
    print(f"{qset['question_set']} (due {due}) member {os.path.basename(mdir)}: {len(qs)} questions, "
          f"{len(qs) - len(todo)} done, {len(todo)} to go")

    lock, spent = threading.Lock(), [0.0]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(forecast_one, q, due, mdir, args): q for q in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            q = futs[fut]
            try:
                r = fut.result()
            except Exception as e:  # one bad call must not sink the round
                print(f"  [{i}/{len(todo)}] {q['source']}/{q['id']}: ERROR {e!r}")
                continue
            with lock:
                with open(log, "a") as f:
                    f.write(json.dumps(r) + "\n")
                spent[0] += r["usage"].get("cost_usd") or 0
            u = r["usage"]
            print(f"  [{i}/{len(todo)}] {q['source']}/{q['id']}: {len(r['probabilities'])}/{len(r['wanted'])} forecasts, "
                  f"research {u.get('research_ok')} ok / {u.get('research_failed')} failed, "
                  f"{u.get('seconds')}s, ${u.get('cost_usd')} (total ${spent[0]:.2f})")
    for kind, (done, n) in coverage(qset, read_results(log)).items():
        print(f"  {kind}: {done}/{n} complete")


def cmd_build(args):
    root = os.path.abspath(args.root)
    qset = json.load(open(os.path.join(root, "question_set.json")))
    members = {}
    for spec in args.member:
        head, *flags = spec.split(",")
        model, _, thinking = head.partition("@")
        thinking, research = thinking or args.thinking, not args.no_research
        for part in flags:
            if part not in ("research", "noresearch"):
                sys.exit(f"--member {spec!r}: unknown flag {part!r}")
            research = part == "research"
        mdir = member_dir(root, model, thinking, research)
        if not os.path.exists(os.path.join(mdir, "manifest.json")):
            sys.exit(f"no member run at {mdir}")
        members[os.path.basename(mdir)] = read_results(os.path.join(mdir, "results.jsonl"))
    results = combine(qset, members)
    model_org = args.model_org or args.org
    fs = build_forecast_set(qset, results, args.org, args.name, model_org, args.reasoning)
    path = os.path.join(root, f"{qset['forecast_due_date']}.{file_org(args.org)}.{args.set_number}.json")
    json.dump(fs, open(path, "w"), indent=1)
    json.dump({"members": list(members), "aggregate": "mean", "name": args.name},
              open(path + ".provenance.json", "w"), indent=1)
    print(f"{len(fs['forecasts'])} forecasts from {len(members)} member(s) -> {path}")
    errs = validate(fs, qset)
    cov = coverage(qset, results)
    for kind, (done, n) in cov.items():
        print(f"  {kind}: {done}/{n} complete")
    short = [k for k, (done, n) in cov.items() if n and done / n < 0.95]
    for e in errs:
        print(f"  INVALID: {e}")
    if errs or short:
        print(f"NOT READY TO UPLOAD: {'invalid rows' if errs else ''}{' and ' if errs and short else ''}"
              f"{'below 95% on ' + ', '.join(short) if short else ''}")
        return 1
    print("ready to upload")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="forecast every question with one member")
    r.add_argument("--root", required=True, help="the round's folder, shared by every member and arm")
    r.add_argument("--question-set", default="latest-llm.json", help="file name in forecastbench-datasets, a URL, or a local path")
    r.add_argument("--model", required=True, help="pi model id, e.g. openai-codex/gpt-6-astra")
    r.add_argument("--thinking", default="high")
    r.add_argument("--no-research", action="store_true", help="no research tools, only submit_forecast")
    r.add_argument("--min-research", type=int, default=2, help="successful research calls before submitting")
    r.add_argument("--workers", type=int, default=8)
    r.add_argument("--limit", type=int, default=None, help="only the first N questions (smoke test)")
    r.add_argument("--sample", type=int, default=None, help="N questions, half market and half dataset (practice run)")
    r.add_argument("--timeout", type=int, default=900, help="seconds per pi call")
    r.add_argument("--pi", default=harness.DEFAULT_PI)
    b = sub.add_parser("build", help="combine members into a forecast set (mean per cell)")
    b.add_argument("--root", required=True)
    b.add_argument("--member", action="append", required=True,
                   help="MODEL[@THINKING][,research|,noresearch]; repeat for an ensemble")
    b.add_argument("--thinking", default="high", help="default thinking for --member")
    b.add_argument("--no-research", action="store_true", help="default research mode for --member: off")
    b.add_argument("--name", required=True, help="the leaderboard `model` field (cannot be changed later); 'ensemble' for ensembles")
    b.add_argument("--model-org", default=None, help="the leaderboard `model_organization` field (default: --org; ForecastBench asks for the team name unless the model is off the shelf)")
    b.add_argument("--org", required=True, help="the team name ForecastBench assigned at registration")
    b.add_argument("--set-number", type=int, required=True)
    b.add_argument("--reasoning", action="store_true", help="include rationales (single-member sets only)")
    args = ap.parse_args(argv)
    return cmd_run(args) if args.cmd == "run" else cmd_build(args)


if __name__ == "__main__":
    sys.exit(main())
