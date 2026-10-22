#!/usr/bin/env python3
"""The observational conditional bench (code/observational/spec.md) on the
ECI-ranked roster the causal bench ran -- data/causal/models.csv, 24 models via
OpenRouter -- instead of the four Claude models run_bench.py was written for.

Same instrument, wider roster. The prompt is run_bench.py's PROMPT verbatim,
the pairs are data/observational/pairs_selected.json, K = 5, questions are
future-dated at run time (due = today, resolves = +30 days), and every model is
called through one API path with vendor-default sampling (no temperature, no
system prompt, no reasoning parameter) -- "models as deployed", the causal
bench's policy (code/causal/starsim_causal/llm.py). What differs from the
2026-08-20 run is only the transport (OpenRouter through litellm rather than
the Anthropic SDK) and the roster; the 2026-08-20 rows are kept in
results/observational/results_2026-08-20.jsonl as the record the spec's pass
bar was first met on.

    python3 code/observational/run_roster.py --dry-run     # job plan + rough cost
    python3 code/observational/run_roster.py --pilot       # 3 pairs x roster x K=1 -> *_pilot.jsonl + pilot_raw_roster.txt
                                                           #   READ the raw dump before the full run (spec: mandatory gate)
    python3 code/observational/run_roster.py               # full, resumable: re-run to fill gaps
    python3 code/observational/run_roster.py --models claude,gpt-5-nano --reps 1

Each row carries the four parsed probabilities plus the raw text, finish
reason, token / reasoning-token counts, OpenRouter's cost and latency, so a
parse failure or a runaway reasoning budget can be audited per model later.
Rows that survive every retry unparsed go to errors_roster.jsonl.

Needs OPENROUTER_API_KEY (environment, ~/.config/redlines/env, or the repo's
.env -- redlines.llm.load_keys) and litellm (`pip install -e '.[acquire]'`).
The scorer is redlines.views.observational (the dashboard blob) and, for the
record, score_bench.py.
"""
import argparse
import asyncio
import csv
import datetime as dt
import json
import os
import random
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from redlines.llm import load_keys  # noqa: E402

PAIRS = REPO_ROOT / "data" / "observational" / "pairs_selected.json"
ROSTER = REPO_ROOT / "data" / "causal" / "models.csv"
ROSTER_EXTRA = REPO_ROOT / "data" / "observational" / "roster_extra.csv"   # Graph 4's models not on the causal roster
OUT_DIR = REPO_ROOT / "results" / "observational"

K = 5
HORIZON_DAYS = 30
# The pilot's three pairs: one positive, one probe, one control -- the same
# categories run_bench.py piloted on 2026-08-20 (first pair of each).
PILOT_CATEGORIES = ("associated_pos_0.85", "hemispheric_probe", "control_independent")

# run_bench.py::PROMPT, verbatim.
PROMPT = """You are forecasting two yes/no questions about the same 30-day window.

Question A: {q_a}
Question B: {q_b}

Today is {due_date}. Both questions resolve on {res_date}.

You may reason briefly first. Then end your reply with one JSON object, alone on its final line, with exactly these keys:
  "p_a":             probability that Question A resolves YES
  "p_b":             probability that Question B resolves YES
  "p_b_given_a":     probability that B resolves YES, supposing you learned only that A resolved YES
  "p_b_given_not_a": probability that B resolves YES, supposing you learned only that A resolved NO
All four are numbers in [0,1]."""

KEYS = ("p_a", "p_b", "p_b_given_a", "p_b_given_not_a")

MAX_ATTEMPTS = 4      # truncated / unparseable replies
MAX_TRANSIENT = 8     # 429 / timeout / 5xx, exponential backoff
# Output cap. Reasoning tokens count against it on most reasoning models; the
# causal bench found 16k truncates some of them on a longer prompt, so the cap
# is 32k here, clipped to each model's own catalog limit. deepseek-v4-flash's
# default reasoning stalls past that (it was partial in the causal bench too).
MAX_TOKENS = 32000


def fill(q, due, res):
    return q.replace("{forecast_due_date}", due).replace("{resolution_date}", res)


def parse(txt):
    """The last well-formed JSON object in the reply with all four keys in
    [0, 1]. LaTeX-escaped braces are tolerated (the causal bench's pilot saw
    them)."""
    txt = txt.replace("\\{", "{").replace("\\}", "}")
    for o in reversed(re.findall(r"\{[^{}]*\}", txt)):
        try:
            d = json.loads(o)
            vals = {k: float(d[k]) for k in KEYS}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        if all(0.0 <= v <= 1.0 for v in vals.values()):
            return vals
    return None


def load_roster(select="all", extra=False):
    """The causal roster; with `extra`, Graph 4's other eight as well (run
    those with --tag so they land in their own file)."""
    rows = []
    for path in ((ROSTER, ROSTER_EXTRA) if extra else (ROSTER,)):
        if not path.exists():
            continue
        with open(path) as fh:
            for r in csv.DictReader(fh):
                rows.append({"id": r["openrouter_id"], "name": r["name"], "eci": float(r["eci"]),
                             "reasoning": r["reasoning_capable"].lower() == "true",
                             "max_completion_tokens": int(r["max_completion_tokens"]) if r.get("max_completion_tokens") else None,
                             "prompt_usd_per_m": float(r["prompt_usd_per_m"]),
                             "completion_usd_per_m": float(r["completion_usd_per_m"])})
    rows.sort(key=lambda m: m["eci"])
    if select and select != "all":
        picked = []
        for w in (w.strip() for w in select.split(",") if w.strip()):
            hits = [m for m in rows if m["id"] == w] or [m for m in rows if w in m["id"]]
            if not hits:
                raise SystemExit(f"--models: no roster model matches {w!r}")
            picked += [h for h in hits if h not in picked]
        rows = sorted(picked, key=lambda m: m["eci"])
    return rows


def load_pairs(pilot):
    pairs = json.load(open(PAIRS))
    if pilot:
        return [next(p for p in pairs if p["category"] == c) for c in PILOT_CATEGORIES]
    return pairs


def done_keys(path):
    if not path.exists():
        return set()
    return {(r["pair_id"], r["model"], r["rep"])
            for r in (json.loads(line) for line in open(path) if line.strip())}


def build_jobs(pairs, models, reps, out_path, due_s, res_s):
    """Model-innermost, so consecutive jobs hit different models and a slow
    reasoning model never serializes the queue."""
    done = done_keys(out_path)
    jobs = []
    for rep in range(reps):
        for pair in pairs:
            prompt = PROMPT.format(q_a=fill(pair["q_a"], due_s, res_s), q_b=fill(pair["q_b"], due_s, res_s),
                                   due_date=due_s, res_date=res_s)
            for m in models:
                if (pair["pair_id"], m["id"], rep) in done:
                    continue
                jobs.append({"pair": pair, "model": m, "rep": rep, "prompt": prompt})
    return jobs


def estimate_cost(jobs):
    """Rough: prompt ~ chars/4; completion 500 tokens (non-reasoning) or 2500
    (reasoning-capable at vendor-default effort). Returns (low, high)."""
    total = 0.0
    for j in jobs:
        m = j["model"]
        p_tok = len(j["prompt"]) / 4 + 30
        c_tok = 2500 if m["reasoning"] else 500
        total += p_tok / 1e6 * m["prompt_usd_per_m"] + c_tok / 1e6 * m["completion_usd_per_m"]
    return total * 0.5, total * 2.0


class Runner:
    def __init__(self, a, out_path, err_path, raw_path):
        import litellm
        litellm.suppress_debug_info = True
        self.litellm = litellm
        self.transient = (litellm.RateLimitError, litellm.Timeout, litellm.APIConnectionError,
                          litellm.InternalServerError, litellm.ServiceUnavailableError)
        self.a = a
        self.out = open(out_path, "a")
        self.err = open(err_path, "a")
        self.raw = open(raw_path, "a") if raw_path else None
        self.lock = asyncio.Lock()
        self.gsem = asyncio.Semaphore(a.concurrency)
        self.msem = {}
        self.dead = {}
        self.abort = None
        self.n_done = self.n_ok = self.n_total = 0
        self.spend = 0.0

    async def complete(self, model, prompt, max_tokens):
        t0 = time.monotonic()
        r = await self.litellm.acompletion(model=f"openrouter/{model['id']}",
                                           messages=[{"role": "user", "content": prompt}],
                                           max_tokens=max_tokens, timeout=self.a.timeout)
        msg = r.choices[0].message
        u = r.usage
        det = getattr(u, "completion_tokens_details", None)
        return {"text": msg.content or "", "finish_reason": r.choices[0].finish_reason,
                "prompt_tokens": getattr(u, "prompt_tokens", None),
                "completion_tokens": getattr(u, "completion_tokens", None),
                "reasoning_tokens": getattr(det, "reasoning_tokens", None) if det else None,
                "cost_usd": getattr(u, "cost", None), "response_model": r.model,
                "latency_s": round(time.monotonic() - t0, 2)}

    async def write_err(self, j, err):
        async with self.lock:
            self.err.write(json.dumps({"pair_id": j["pair"]["pair_id"], "model": j["model"]["id"],
                                       "rep": j["rep"], "error": err,
                                       "ts": dt.datetime.now().isoformat(timespec="seconds")}) + "\n")
            self.err.flush()

    async def one(self, j):
        m, pair, rep = j["model"], j["pair"], j["rep"]
        tag = f"{pair['pair_id']} {m['id']} r{rep}"
        sem = self.msem.setdefault(m["id"], asyncio.Semaphore(self.a.per_model))
        async with sem, self.gsem:
            if self.abort or m["id"] in self.dead:
                return
            max_tokens = min(self.a.max_tokens, max(m["max_completion_tokens"] or 0, 16000))
            attempts = transient = 0
            last = "?"
            while attempts < MAX_ATTEMPTS and transient < MAX_TRANSIENT:
                if self.abort:
                    return
                try:
                    r = await self.complete(m, j["prompt"], max_tokens)
                except self.transient as e:
                    transient += 1
                    wait = min(90, 4 * 2 ** transient) + random.uniform(0, 3)
                    print(f"  transient {type(e).__name__} on {tag}; sleep {wait:.0f}s", file=sys.stderr)
                    await asyncio.sleep(wait)
                    continue
                except Exception as e:  # noqa: BLE001 -- classified below
                    s = str(e)
                    code = getattr(e, "status_code", None)
                    if code == 402 or "Insufficient credits" in s:
                        self.abort = s[:300]
                        print(f"\nABORT (credits): {s[:300]}\n", file=sys.stderr)
                        return
                    if isinstance(e, (self.litellm.NotFoundError, self.litellm.BadRequestError)) or code in (400, 404):
                        self.dead[m["id"]] = s[:300]
                        print(f"DEAD MODEL {m['id']}: {s[:200]}", file=sys.stderr)
                        await self.write_err(j, f"model unavailable: {s[:300]}")
                        return
                    attempts += 1
                    last = f"{type(e).__name__}: {s[:200]}"
                    print(f"  error on {tag}: {last}", file=sys.stderr)
                    await asyncio.sleep(2)
                    continue
                attempts += 1
                self.spend += r["cost_usd"] or 0.0
                if self.raw:
                    async with self.lock:
                        self.raw.write(f"\n===== {pair['pair_id']} {m['id']} r{rep} finish={r['finish_reason']} "
                                       f"reasoning_tokens={r['reasoning_tokens']} =====\n{r['text']}\n")
                        self.raw.flush()
                if r["finish_reason"] == "length":
                    last = f"truncated (completion_tokens={r['completion_tokens']})"
                    print(f"  retry {tag}: {last}", file=sys.stderr)
                    continue
                vals = parse(r["text"])
                if vals is None:
                    last = f"unparseable (finish={r['finish_reason']}, {len(r['text'])} chars)"
                    print(f"  retry {tag}: {last}", file=sys.stderr)
                    continue
                rec = {"pair_id": pair["pair_id"], "model": m["id"], "rep": rep,
                       "due_date": self.a.due_s, "res_date": self.a.res_s, **vals,
                       "raw": r["text"], "finish_reason": r["finish_reason"],
                       "prompt_tokens": r["prompt_tokens"], "completion_tokens": r["completion_tokens"],
                       "reasoning_tokens": r["reasoning_tokens"], "cost_usd": r["cost_usd"],
                       "latency_s": r["latency_s"], "response_model": r["response_model"],
                       "reasoning_setting": "vendor-default", "max_tokens": max_tokens,
                       "attempts": attempts, "ts": dt.datetime.now().isoformat(timespec="seconds")}
                async with self.lock:
                    self.out.write(json.dumps(rec) + "\n")
                    self.out.flush()
                self.n_ok += 1
                shown = " ".join(f"{k}={v:.2f}" for k, v in vals.items())
                print(f"[{self.n_done + 1}/{self.n_total}] {tag}: {shown}  ({r['completion_tokens']} tok, "
                      f"rt={r['reasoning_tokens']}, ${r['cost_usd'] or 0:.4f}, {r['latency_s']}s)")
                return
            await self.write_err(j, f"gave up after {attempts} attempts / {transient} transient: {last}")
            print(f"GIVE UP {tag}: {last}", file=sys.stderr)

    async def run(self, jobs):
        self.n_total = len(jobs)

        async def wrapped(j):
            try:
                await self.one(j)
            finally:
                self.n_done += 1
        await asyncio.gather(*(wrapped(j) for j in jobs))
        for f in (self.out, self.err, self.raw):
            if f:
                f.close()


def main():
    sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default="all", help="'all' or comma-separated OpenRouter ids / substrings")
    ap.add_argument("--reps", type=int, default=K, help=f"K reps per (pair, model); default {K}; pilot forces 1")
    ap.add_argument("--pilot", action="store_true", help="3 pairs, K=1, raw dump for human reading")
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    ap.add_argument("--timeout", type=float, default=900.0, help="per-request seconds")
    ap.add_argument("--concurrency", type=int, default=12, help="global in-flight requests")
    ap.add_argument("--per-model", type=int, default=3, help="in-flight requests per model")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--due", default=None, help="forecast due date (default today); resolves +30 days")
    ap.add_argument("--with-extra", action="store_true",
                    help="include data/observational/roster_extra.csv (Graph 4's other models) in the roster")
    ap.add_argument("--tag", default=None, help="write results_roster_<tag>.jsonl instead of results_roster.jsonl "
                                               "(a second process must never append to a file another one holds open)")
    ap.add_argument("--dry-run", action="store_true", help="plan + cost estimate only")
    a = ap.parse_args()

    due = dt.date.fromisoformat(a.due) if a.due else dt.date.today()
    a.due_s, a.res_s = due.isoformat(), (due + dt.timedelta(days=HORIZON_DAYS)).isoformat()
    if a.pilot:
        a.reps = 1
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"_{a.tag}" if a.tag else ""
    suffix = tag + ("_pilot" if a.pilot else "")
    out_path = out_dir / f"results_roster{suffix}.jsonl"
    err_path = out_dir / f"errors_roster{suffix}.jsonl"
    raw_path = out_dir / f"pilot_raw_roster{tag}.txt" if a.pilot else None

    models = load_roster(a.models, extra=a.with_extra)
    pairs = load_pairs(a.pilot)
    jobs = build_jobs(pairs, models, a.reps, out_path, a.due_s, a.res_s)
    print(f"pairs={len(pairs)} models={len(models)} K={a.reps} due={a.due_s} resolves={a.res_s} "
          f"{'PILOT ' if a.pilot else ''}-> {len(jobs)} calls to make "
          f"({len(pairs) * len(models) * a.reps} total, rest already in {out_path.name})")
    lo, hi = estimate_cost(jobs)
    print(f"rough cost for remaining calls: ${lo:.0f}-${hi:.0f} (catalog prices; a guess, not a quote)")
    if a.dry_run:
        per_model = {}
        for j in jobs:
            per_model[j["model"]["id"]] = per_model.get(j["model"]["id"], 0) + 1
        for m in models:
            print(f"  {m['eci']:7.2f}  {m['id']:44s} {per_model.get(m['id'], 0):4d} calls  "
                  f"{'reasoning' if m['reasoning'] else '         '}  "
                  f"${m['prompt_usd_per_m']:.2f}/${m['completion_usd_per_m']:.2f} per M")
        if jobs:
            print(f"\n--- example prompt [{jobs[0]['pair']['pair_id']}] ---\n{jobs[0]['prompt']}\n")
        print("dry run: no API calls made")
        return
    if not jobs:
        print("nothing to do")
        return
    load_keys()
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY not set (environment, ~/.config/redlines/env, or .env)")
    runner = Runner(a, out_path, err_path, raw_path)
    asyncio.run(runner.run(jobs))
    print(f"\ndone: {runner.n_ok}/{len(jobs)} ok, spend this session ~${runner.spend:.2f}")
    if runner.dead:
        print("models skipped as unavailable: " + ", ".join(runner.dead))
    if runner.abort:
        sys.exit("run aborted: " + runner.abort[:200])
    if a.pilot:
        print(f"\nPILOT COMPLETE. Read {raw_path} before the full run.")


if __name__ == "__main__":
    main()
