"""Elicitation runner: every roster model x both conditions of the v2 StarSim bench, via OpenRouter.

Conditions (same 8 items from worlds.json; SEPARATE prompts — a model never sees both):
  baseline      world report + question
  intervention  world report + PLANNED INTERVENTION + question

Usage (from the repo root):
  uv run python results/causal/starsim_causal/run.py --dry-run          # job plan + rough cost, no API calls
  uv run python results/causal/starsim_causal/run.py --pilot            # 2 items/condition x all models x K=1
                                                         #   -> results/{baseline,intervention}_pilot.jsonl + results/pilot_raw_*.txt
                                                         #   READ THE RAW DUMPS before the full run (spec: mandatory gate)
  uv run python results/causal/starsim_causal/run.py                    # full run, K=5, resumable (re-run to fill gaps)
  uv run python results/causal/starsim_causal/run.py --class intervention --models claude,gpt-5-nano --reps 1

Each result line carries the parsed probabilities plus the raw text, finish
reason, token/reasoning-token counts, OpenRouter cost, and latency, so parse
failures and reasoning behaviour can be audited per model afterwards.
Failures that survive retries go to results/errors{_pilot}.jsonl.
"""
import argparse
import asyncio
import datetime as dt
import json
import random
import re
import sys
from pathlib import Path

import litellm

from llm import InsufficientCredits, ModelUnavailable, complete, load_env
from models import Model, load_roster
from prompts import prompt

HERE = Path(__file__).resolve().parent
ITEMS_FILE = HERE / "worlds.json"
ITEMS_PATH = ITEMS_FILE   # overridden by --worlds (v3 rungs: worlds_<tag>.json, same item_ids)
# pilot: item 0 (world 0, Riverton leads, day 40) and item 4 (world 2, Southbay leads, day 40)
CLASSES = {
    "baseline": dict(keys=("p",), pilot_idx=(0, 4),
                     prompt=lambda it: prompt(it["report"], it["question"])),
    "intervention": dict(keys=("p",), pilot_idx=(0, 4),
                         prompt=lambda it: prompt(it["report"], it["question"], it["intervention"])),
}
MAX_ATTEMPTS = 4        # bad-output retries (truncated / unparseable)
# Output cap: --max-tokens (default 65536) clipped to each model's own output
# limit from the catalog (models.csv max_completion_tokens). With parameters
# stated in the report, vendor-default reasoning routinely exceeds 16k tokens
# (v2 pilot 2026-08-27: sonnet-5 truncated 4/4 on an intervention prompt;
# gpt-5, qwen3.5-flash once each; deepseek-v4-flash 10-18k routinely). Models
# that stop naturally are unaffected by the cap. Per-model overrides via
# --max-tokens-override model=N (repeatable).
MAX_TOKENS_OVERRIDE = {}
MAX_TRANSIENT = 8       # 429 / timeout / 5xx retries, exponential backoff
TRANSIENT = (litellm.RateLimitError, litellm.Timeout, litellm.APIConnectionError,
             litellm.InternalServerError, litellm.ServiceUnavailableError)


def parse(txt: str, keys: tuple[str, ...]) -> dict | None:
    """Last well-formed JSON object in the reply with all keys in [0,1].
    Lenient fallbacks (v2 pilot): LaTeX-escaped braces (\\{ "p": 0.7 \\}) and a
    bare trailing `"p": 0.98` with no braces both count."""
    txt = txt.replace("\\{", "{").replace("\\}", "}")
    for o in reversed(re.findall(r"\{[^{}]*\}", txt)):
        try:
            d = json.loads(o)
            vals = {k: float(d[k]) for k in keys}
            if all(0.0 <= v <= 1.0 for v in vals.values()):
                return vals
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    vals = {}
    for k in keys:
        ms = re.findall(rf'"{k}"\s*:\s*(0(?:\.\d+)?|1(?:\.0+)?)', txt)
        if not ms:
            return None
        vals[k] = float(ms[-1])
    return vals


def load_items(cls: str, pilot: bool) -> list[dict]:
    items = json.load(open(ITEMS_PATH))["items"]
    return [items[i] for i in CLASSES[cls]["pilot_idx"]] if pilot else items


def done_keys(path: Path) -> set[tuple]:
    if not path.exists():
        return set()
    return {(r["class"], r["item_id"], r["model"], r["rep"])
            for r in (json.loads(l) for l in open(path) if l.strip())}


def build_jobs(classes, models, reps, pilot, out_dir, suffix):
    """Model-innermost order: consecutive jobs hit different models, so the
    per-model cap rarely stalls a global slot and slow models don't serialize
    the queue (they did: 200 s/call reasoning models hogged the run)."""
    jobs = []
    done = {cls: done_keys(out_dir / f"{cls}{suffix}.jsonl") for cls in classes}
    prompts = {cls: [(it, CLASSES[cls]["prompt"](it)) for it in load_items(cls, pilot)] for cls in classes}
    for rep in range(reps):
        for cls in classes:
            for it, prompt in prompts[cls]:
                for m in models:
                    if (cls, it["item_id"], m.openrouter_id, rep) in done[cls]:
                        continue
                    jobs.append(dict(cls=cls, item=it, model=m, rep=rep, prompt=prompt))
    return jobs


def estimate_cost(jobs) -> tuple[float, float]:
    """Very rough: prompt ~ chars/4 + 50; completion 600 tok (non-reasoning) or
    3000 (reasoning-capable, vendor-default effort). Returns (low, high)."""
    total = 0.0
    for j in jobs:
        m: Model = j["model"]
        p_tok = len(j["prompt"]) / 4 + 50
        c_tok = 3000 if m.reasoning_capable else 600
        total += p_tok / 1e6 * m.prompt_usd_per_m + c_tok / 1e6 * m.completion_usd_per_m
    return total * 0.5, total * 2.0


class Runner:
    def __init__(self, a, out_dir: Path):
        self.a = a
        self.out_dir = out_dir
        self.suffix = a.suffix
        self.files = {cls: open(out_dir / f"{cls}{self.suffix}.jsonl", "a") for cls in CLASSES}
        self.errf = open(out_dir / f"errors{self.suffix}.jsonl", "a")
        self.raw = {cls: open(out_dir / f"pilot_raw_{cls}.txt", "a") for cls in CLASSES} if a.pilot else {}
        self.lock = asyncio.Lock()
        self.gsem = asyncio.Semaphore(a.concurrency)
        self.msem: dict[str, asyncio.Semaphore] = {}
        self.dead: dict[str, str] = {}
        self.abort: str | None = None
        self.n_done = self.n_ok = 0
        self.n_total = 0
        self.spend = 0.0

    async def write(self, cls, rec):
        async with self.lock:
            self.files[cls].write(json.dumps(rec) + "\n"); self.files[cls].flush()

    async def write_err(self, j, err):
        async with self.lock:
            self.errf.write(json.dumps(dict(
                **{"class": j["cls"], "item_id": j["item"]["item_id"],
                   "model": j["model"].openrouter_id, "rep": j["rep"]},
                error=err, ts=dt.datetime.now().isoformat(timespec="seconds"))) + "\n")
            self.errf.flush()

    async def one(self, j):
        m: Model = j["model"]
        cls, item, rep = j["cls"], j["item"], j["rep"]
        keys = CLASSES[cls]["keys"]
        tag = f"{cls} {item['item_id']} {m.openrouter_id} r{rep}"
        sem = self.msem.setdefault(m.openrouter_id, asyncio.Semaphore(self.a.per_model))
        async with sem, self.gsem:  # per-model first: waiting on a model never holds a global slot
            if self.abort or m.openrouter_id in self.dead:
                return
            attempts = transient = 0
            last = "?"
            while attempts < MAX_ATTEMPTS and transient < MAX_TRANSIENT:
                if self.abort:
                    return
                try:
                    # catalog cap is the top provider's only; 16k is proven across the roster
                    max_tokens = self.a.overrides.get(
                        m.openrouter_id, min(self.a.max_tokens, max(m.max_completion_tokens or 0, 16000)))
                    r = await complete(m.openrouter_id, j["prompt"], max_tokens=max_tokens,
                                       reasoning=self.a.reasoning)
                except InsufficientCredits as e:
                    self.abort = str(e); print(f"\nABORT: {e}\n", file=sys.stderr); return
                except ModelUnavailable as e:
                    self.dead[m.openrouter_id] = str(e)
                    print(f"DEAD MODEL {m.openrouter_id}: {str(e)[:200]}", file=sys.stderr)
                    await self.write_err(j, f"model unavailable: {e}"); return
                except TRANSIENT as e:
                    transient += 1
                    wait = min(90, 4 * 2 ** transient) + random.uniform(0, 3)
                    print(f"  transient {type(e).__name__} on {tag}; sleep {wait:.0f}s", file=sys.stderr)
                    await asyncio.sleep(wait); continue
                except Exception as e:  # noqa: BLE001 — unknown provider error: count it, retry
                    attempts += 1; last = f"{type(e).__name__}: {str(e)[:200]}"
                    print(f"  error on {tag}: {last}", file=sys.stderr)
                    await asyncio.sleep(2); continue
                attempts += 1
                self.spend += r["cost_usd"] or 0.0
                if self.raw:
                    async with self.lock:
                        self.raw[cls].write(f"\n===== {item['item_id']} {m.openrouter_id} r{rep} "
                                            f"finish={r['finish_reason']} reasoning_tokens={r['reasoning_tokens']} =====\n"
                                            f"{r['text']}\n"); self.raw[cls].flush()
                if r["finish_reason"] == "length":
                    last = f"truncated (finish_reason=length, completion_tokens={r['completion_tokens']})"
                    print(f"  retry {tag}: {last}", file=sys.stderr); continue
                vals = parse(r["text"], keys)
                if vals is None:
                    last = f"unparseable (finish={r['finish_reason']}, {len(r['text'])} chars)"
                    print(f"  retry {tag}: {last}", file=sys.stderr); continue
                rec = {"class": cls, "item_id": item["item_id"], "model": m.openrouter_id, "rep": rep,
                       **vals, "raw": r["text"], "finish_reason": r["finish_reason"],
                       "prompt_tokens": r["prompt_tokens"], "completion_tokens": r["completion_tokens"],
                       "reasoning_tokens": r["reasoning_tokens"], "cost_usd": r["cost_usd"],
                       "latency_s": r["latency_s"], "response_model": r["response_model"],
                       "reasoning_setting": self.a.reasoning or "vendor-default",
                       "max_tokens": max_tokens, "attempts": attempts,
                       "ts": dt.datetime.now().isoformat(timespec="seconds")}
                await self.write(cls, rec)
                self.n_ok += 1
                shown = " ".join(f"{k}={v:.2f}" for k, v in vals.items())
                print(f"[{self.n_done + 1}/{self.n_total}] {tag}: {shown}  "
                      f"({r['completion_tokens']} tok, rt={r['reasoning_tokens']}, "
                      f"${r['cost_usd'] or 0:.4f}, {r['latency_s']}s)")
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
        for f in list(self.files.values()) + list(self.raw.values()) + [self.errf]:
            f.close()


def main():
    sys.stdout.reconfigure(line_buffering=True)  # progress lines land in logs immediately
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--class", dest="classes", default="all", help="baseline | intervention | all")
    ap.add_argument("--models", default="all", help="'all' or comma-separated OpenRouter ids / substrings")
    ap.add_argument("--reps", type=int, default=5, help="K reps per (item, model); pilot forces 1")
    ap.add_argument("--pilot", action="store_true", help="2 items per class, K=1, raw dumps for human reading")
    ap.add_argument("--reasoning", default=None, choices=[None, "low", "medium", "high"],
                    help="OpenRouter reasoning.effort; default sends nothing (vendor default)")
    ap.add_argument("--max-tokens", type=int, default=65536,
                    help="output cap, clipped to each model's catalog max_completion_tokens")
    ap.add_argument("--max-tokens-override", action="append", default=[], metavar="MODEL=N",
                    help=f"per-model cap; defaults {MAX_TOKENS_OVERRIDE}")
    ap.add_argument("--concurrency", type=int, default=20, help="global in-flight requests")
    ap.add_argument("--per-model", type=int, default=4, help="in-flight requests per model")
    ap.add_argument("--out-dir", default=str(HERE / "results"))
    ap.add_argument("--worlds", default=str(ITEMS_FILE),
                    help="items file; v3 rungs use worlds_<tag>.json (same item_ids, new intervention text/truths)")
    ap.add_argument("--tag", default=None,
                    help="rung tag: results go to <class>_<tag>.jsonl / errors_<tag>.jsonl; implies --class intervention "
                         "unless --class is given (baseline prompts are identical across rungs and are shared)")
    ap.add_argument("--dry-run", action="store_true", help="plan + cost estimate only")
    a = ap.parse_args()

    global ITEMS_PATH
    ITEMS_PATH = Path(a.worlds)
    if a.tag and a.classes == "all":
        a.classes = "intervention"
        print(f"--tag {a.tag}: running the intervention class only (baseline is shared across rungs)")
    a.suffix = "_pilot" if a.pilot else (f"_{a.tag}" if a.tag else "")
    classes = list(CLASSES) if a.classes == "all" else [c.strip() for c in a.classes.split(",")]
    for c in classes:
        if c not in CLASSES:
            sys.exit(f"unknown class {c!r}; choose from {list(CLASSES)}")
    if a.pilot:
        a.reps = 1
    a.overrides = dict(MAX_TOKENS_OVERRIDE)
    for spec in a.max_tokens_override:
        mid, _, n = spec.partition("=")
        a.overrides[mid] = int(n)
    out_dir = Path(a.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    models = load_roster(a.models)
    jobs = build_jobs(classes, models, a.reps, a.pilot, out_dir, a.suffix)

    n_items = {c: len(load_items(c, a.pilot)) for c in classes}
    print(f"classes={classes} items={n_items} models={len(models)} K={a.reps} "
          f"{'PILOT ' if a.pilot else ''}-> {len(jobs)} calls to make "
          f"({sum(n_items.values()) * len(models) * a.reps} total, rest already done)")
    lo, hi = estimate_cost(jobs)
    print(f"rough cost for remaining calls: ${lo:.0f}-${hi:.0f} "
          f"(catalog prices in models.csv; completion-length guess, not a quote)")
    if a.dry_run:
        per_model = {}
        for j in jobs:
            per_model[j["model"].openrouter_id] = per_model.get(j["model"].openrouter_id, 0) + 1
        for m in models:
            print(f"  {m.eci:7.2f}  {m.openrouter_id:44s} {per_model.get(m.openrouter_id, 0):4d} calls  "
                  f"{'reasoning' if m.reasoning_capable else '        '}  "
                  f"${m.prompt_usd_per_m:.2f}/${m.completion_usd_per_m:.2f} per M")
        for c in classes:
            it = load_items(c, a.pilot)[0]
            print(f"\n--- example prompt [{c} / {it['item_id']}] ---\n{CLASSES[c]['prompt'](it)}\n")
        print("dry run: no API calls made")
        return
    if not jobs:
        print("nothing to do"); return
    load_env()
    runner = Runner(a, out_dir)
    asyncio.run(runner.run(jobs))
    print(f"\ndone: {runner.n_ok}/{len(jobs)} ok, spend this session ~${runner.spend:.2f}")
    if runner.dead:
        print("models skipped as unavailable: " + ", ".join(runner.dead))
    if runner.abort:
        sys.exit("run aborted: " + runner.abort[:200])
    if a.pilot:
        print(f"\nPILOT COMPLETE. Read {out_dir}/pilot_raw_*.txt before the full run.")


if __name__ == "__main__":
    main()
