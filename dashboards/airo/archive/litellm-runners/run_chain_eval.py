#!/usr/bin/env python3
"""Does joint elicitation improve ACCURACY, or only tidiness? (issue #8, part 2)

The severity-ladder experiment (code/run_ladder_joint.py) showed that asking a
nested chain of questions in one call removes coherence violations completely:
0 of 702 pairs, against 46% of ladders broken under separate calls. It could not
show whether the forecasts got BETTER, because catastrophic-risk questions
resolve in 2030-2100.

The FreeCiv corpus has the same nested structure and DOES resolve. Every mined
target appears at 7 horizons, and "discovered by turn 90" implies "discovered by
turn 130" exactly as ">=1M deaths" implies ">=100k deaths". A recorded game gives
deterministic ground truth, so both arms can be scored on Brier, not just on
self-consistency.

    SEP    one call per question  (7 calls per chain)  <- forced separate
    JOINT  one call per chain     (1 call per chain)   <- all 7 horizons together

Both arms use the harness's own build_batch_prompt and parse_batch_probabilities;
that builder already handles n=1 and n>1, so the arms differ in BATCH COMPOSITION
and nothing else — same wording, same world report, same parser.

Every question is forecast by the same model under both arms, so the comparison
is paired.

Runs inside the forecastbench-sim uv env (it owns litellm and the FreeCiv world):

    cd ~/Projects/forecastbench-sim
    uv run python ~/Projects/redlines/code/run_chain_eval.py --smoke
    uv run python ~/Projects/redlines/code/run_chain_eval.py --chains 12 --games 4
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

FBSIM_ROOT = Path(os.environ.get("FBSIM_ROOT",
                                 str(Path.home() / "Projects" / "forecastbench-sim")))
FREECIV = FBSIM_ROOT / "worlds" / "freeciv"
for p in (FREECIV, FREECIV / "src", FBSIM_ROOT / "packages" / "fbsim-core"):
    sys.path.insert(0, str(p))

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from redlines.registry import frontier_models  # noqa: E402

# Cumulative templates only. "Will X be in Monarchy AT turn 220?" is a
# point-in-time question — a government can be left as well as entered, so
# government_at carries no implication between horizons and cannot be audited.
NESTED_TEMPLATES = ("wonder_completed", "tech_discovered")

SNAPSHOT_TURN = 40


def load_harness():
    import litellm
    litellm.drop_params = True
    from fbsim_core.evaluation.models import LiteLLMModel, load_api_keys_from_gcp
    from fbsim_core.evaluation import models as _fbmodels
    # Same server-side temperature refusal run_eval.py works around.
    for _m in ("claude-opus-4-8", "claude-fable-5"):
        try:
            _fbmodels.MODELS_WITHOUT_TEMPERATURE.add(_m)
        except AttributeError:
            if _m not in _fbmodels.MODELS_WITHOUT_TEMPERATURE:
                _fbmodels.MODELS_WITHOUT_TEMPERATURE.append(_m)
    # MODELS_WITH_EXTENDED_REASONING stops at o4-mini, so every newer reasoning
    # model gets the non-reasoning token budget, burns it on thinking, and is
    # cut off before it emits the <<<PROBABILITIES>>> block. The call succeeds
    # and the parse returns nothing — silent data loss, not an error. GPT-5.5
    # lost 7/7 cells on some chains this way.
    for _m in ("gpt-5", "gpt-5.5", "gpt-5.5-mini"):
        _fbmodels.MODELS_WITH_EXTENDED_REASONING.add(_m)
    from freeciv_world.evaluation.parallel_evaluator import (
        build_batch_prompt, parse_batch_probabilities)
    return (LiteLLMModel, load_api_keys_from_gcp,
            build_batch_prompt, parse_batch_probabilities)


def chains_from_corpus(path: Path, horizons: int = 7):
    """-> {(game_id, template, target): [question, ...] in resolution-turn order}"""
    qs = json.load(open(path))["questions"]
    g = defaultdict(list)
    for q in qs:
        if q["template_id"] in NESTED_TEMPLATES:
            g[(q["game_id"], q["template_id"], q["target"])].append(q)
    out = {}
    for k, v in g.items():
        v = sorted(v, key=lambda q: q["resolution_turn"])
        if len(v) == horizons:
            out[k] = v
    return out


def select(chains, n_chains, n_games, seed):
    """Pick chains, concentrated in few games so few world reports are needed.

    Stratified on the FLIP TURN — the horizon where ground truth first turns 1.
    A chain that is all-0 or all-1 is coherent under any monotone guess and
    separates the arms weakly; a chain that flips in the middle is the one that
    discriminates. Sampling across flip points keeps the Brier comparison from
    being decided by whichever arm happens to be more timid.
    """
    rng = random.Random(seed)
    by_game = defaultdict(list)
    for k, v in chains.items():
        by_game[k[0]].append((k, v))
    games = sorted(by_game)
    rng.shuffle(games)
    games = games[:n_games]

    def flip(v):
        gts = [bool(q["ground_truth"]) for q in v]
        return gts.index(True) if any(gts) else len(gts)

    pool = [(k, v) for g in games for k, v in by_game[g]]
    strata = defaultdict(list)
    for k, v in pool:
        strata[flip(v)].append((k, v))
    for s in strata.values():
        rng.shuffle(s)
    keys, out, i = sorted(strata), [], 0
    while len(out) < n_chains and any(strata.values()):
        s = strata[keys[i % len(keys)]]
        if s:
            out.append(s.pop())
        i += 1
    return out


def ensure_report(game_id: str, data_dir: Path, turn: int) -> Path | None:
    """Generate the turn-{turn} world report for a game if missing.

    Lifted from code/run_eval.py::ensure_report — same generator, same empty
    _rec directory, so the report text these arms see is byte-identical to what
    the tracked eval sees.
    """
    out = data_dir / game_id / "world_report" / f"turn_{turn:03d}_report.txt"
    if out.exists():
        return out
    game_json = FBSIM_ROOT / "data" / "games" / f"{game_id}_data.json"
    if not game_json.exists():
        return None
    import scripts.generate_txt_report as gtr
    empty_rec = data_dir / game_id / "_rec"
    empty_rec.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        gtr.generate_txt_report(game_data_path=game_json, recording_dir=empty_rec,
                                output_dir=out.parent, turn=turn,
                                sample_interval=5, map_interval=10 ** 9)
    except Exception as e:
        print(f"  ! report gen failed for {game_id}: {e}")
        return None
    return out if out.exists() else None


async def ask(model, prompt, parse, n):
    """One call -> list of n probabilities (None where the parse failed)."""
    try:
        # Reasoning models spend the budget on thinking before they emit the
        # delimited block, so give them the harness's own headroom rule.
        text = await model.get_response_async(
            prompt, max_tokens=model.effective_max_tokens(1000 + 200 * n))
    except Exception as e:
        return [None] * n, f"{type(e).__name__}: {str(e)[:160]}"
    try:
        return parse(text, n), None
    except Exception as e:
        return [None] * n, f"parse: {type(e).__name__}: {str(e)[:160]}"


async def run_model(label, model_id, picked, reports, arms, build, parse,
                    LiteLLMModel, sem):
    model = LiteLLMModel(model_id)
    rows = []
    for (key, qs) in picked:
        game, template, target = key
        report = reports[game]
        if "joint" in arms:
            async with sem:
                ps, err = await ask(model, build(qs, report), parse, len(qs))
            rows.append({"arm": "joint", "label": label, "model": model_id,
                         "game_id": game, "template_id": template, "target": target,
                         "probs": ps, "error": err,
                         "question_ids": [q["question_id"] for q in qs],
                         "turns": [q["resolution_turn"] for q in qs],
                         "ground_truth": [bool(q["ground_truth"]) for q in qs],
                         "class_base_rate": [q.get("class_base_rate") for q in qs]})
        if "sep" in arms:
            got = []
            for q in qs:
                async with sem:
                    ps, err = await ask(model, build([q], report), parse, 1)
                got.append((ps[0] if ps else None, err))
            rows.append({"arm": "sep", "label": label, "model": model_id,
                         "game_id": game, "template_id": template, "target": target,
                         "probs": [p for p, _ in got],
                         "error": next((e for _, e in got if e), None),
                         "question_ids": [q["question_id"] for q in qs],
                         "turns": [q["resolution_turn"] for q in qs],
                         "ground_truth": [bool(q["ground_truth"]) for q in qs],
                         "class_base_rate": [q.get("class_base_rate") for q in qs]})
        done = [r for r in rows if r["game_id"] == game]
        print(f"  {label:16} {target[:34]:34} "
              + "  ".join(f"{r['arm']}=" + ",".join(
                  "--" if p is None else f"{p:.2f}" for p in r["probs"])
                  for r in done))
    return rows


async def amain(args):
    (LiteLLMModel, load_api_keys_from_gcp,
     build, parse) = load_harness()
    load_api_keys_from_gcp()
    # GCP holds a stale Anthropic key and load_api_keys_from_gcp overwrites the
    # environment with it, so every Anthropic model 401s. The legacy runner
    # (archive/legacy-questions/run_forecasts.py) has the same split — Anthropic
    # from .env, everything else from Secret Manager.
    # Apply it in that order, GCP first and .env last.
    for ln in (REPO / ".env").read_text().splitlines():
        if ln.startswith("ANTHROPIC_API_KEY="):
            os.environ["ANTHROPIC_API_KEY"] = ln.split("=", 1)[1].strip().strip('"\'')

    chains = chains_from_corpus(args.corpus)
    print(f"corpus: {len(chains)} complete 7-horizon chains")
    picked = select(chains, args.chains, args.games, args.seed)
    if args.smoke:
        picked = picked[:1]
    games = sorted({k[0] for k, _ in picked})
    print(f"selected {len(picked)} chains across {len(games)} games: {', '.join(games)}")

    reports = {}
    for g in games:
        p = ensure_report(g, args.data_dir, SNAPSHOT_TURN)
        if p is None:
            sys.exit(f"no world report for {g} — cannot run")
        reports[g] = p.read_text()
    print(f"world reports: {len(reports)}, "
          f"{sum(len(v) for v in reports.values())//len(reports)} chars each")

    models = frontier_models()
    if args.models:
        want = {m.strip().lower() for m in args.models.split(",")}
        models = [(l, m) for l, m in models if l.lower() in want]
    if args.smoke:
        models = models[:1]

    arms = tuple(a.strip() for a in args.arms.split(","))
    n_sep = len(picked) * 7 * len(models) if "sep" in arms else 0
    n_joint = len(picked) * len(models) if "joint" in arms else 0
    print(f"{len(models)} models x {len(picked)} chains -> "
          f"{n_sep} SEP calls + {n_joint} JOINT calls")

    sem = asyncio.Semaphore(args.concurrency)
    out = await asyncio.gather(*[
        run_model(l, m, picked, reports, arms, build, parse, LiteLLMModel, sem)
        for l, m in models])

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    path = args.out if args.out.suffix else args.out / f"chain_eval_{run_id}.jsonl"
    with open(path, "w") as f:
        for rows in out:
            for r in rows:
                f.write(json.dumps({**r, "run_id": run_id}) + "\n")
    print(f"\n-> {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, required=True,
                    help="wide-band mined corpus (rate-lo 0 rate-hi 1) holding "
                         "COMPLETE chains; the tracked 1-9% artifact truncates "
                         "them to length 1-2 and cannot be used")
    ap.add_argument("--data-dir", type=Path,
                    default=FBSIM_ROOT / "data" / "questions_chain",
                    help="where world reports are written")
    ap.add_argument("--chains", type=int, default=12)
    ap.add_argument("--games", type=int, default=4,
                    help="draw the chains from this many games — each game needs "
                         "one world report, and the report dominates input cost")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--models", help="comma-separated label filter")
    ap.add_argument("--arms", default="joint,sep")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--smoke", action="store_true", help="one chain x one model")
    ap.add_argument("--out", type=Path,
                    default=REPO / "results" / "experiments")
    args = ap.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
