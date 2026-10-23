#!/usr/bin/env python3
"""Red Lines low-probability ECI eval.

Runs the demo model set over the FreeCiv low-probability corpus and scores
calibration/Brier/skill on genuinely rare (1-9% base-rate) resolved questions,
then plots each model's skill against its Epoch Capabilities Index (ECI).

Pipeline (all reproducible):
  1. Load the mined low-prob questions (grouped by game).
  2. Stratified-sample N games, guaranteeing all tail classes are covered.
  3. Cap questions/game (batched under one turn-40 world report -> cheap).
  4. Generate the turn-40 world report per game from data/games/{game}_data.json.
  5. run_batch_evaluation across the models (harness handles rate limits/retries).
  6. Score per model (Brier, BSS vs per-class climatology, decile calibration).
  7. Write results.json + metrics.csv + eci_scatter.png + calibration.png.

Runs inside the forecastbench-sim uv env:
    cd $FBSIM_ROOT/worlds/freeciv
    uv run python /path/to/redlines/code/run_eval.py --smoke
    uv run python /path/to/redlines/code/run_eval.py --games 150
"""
from __future__ import annotations
import os
import argparse, asyncio, json, os, random, sys
from collections import defaultdict
from pathlib import Path

FBSIM_ROOT = Path(os.environ.get("FBSIM_ROOT", os.path.expanduser("~/Projects/forecastbench-sim")))
FREECIV = FBSIM_ROOT / "worlds" / "freeciv"
for p in (FREECIV, FREECIV / "src", FBSIM_ROOT / "packages" / "fbsim-core"):
    sys.path.insert(0, str(p))

def load_harness():
    """Import the model/eval harness. Deferred: it pulls in litellm and the
    FreeCiv gym environment, which only a real forecasting run needs. --rescore
    recomputes metrics from stored predictions and must stay runnable without
    that environment installed.
    """
    import litellm
    litellm.drop_params = True  # fable-5 / gpt-5.5.x / gpt-5 reject temperature -> drop it

    from fbsim_core.evaluation.models import LiteLLMModel, load_api_keys_from_gcp
    from fbsim_core.evaluation import models as _fbmodels
    # These brand-new models reject `temperature` SERVER-SIDE (Anthropic), which
    # litellm.drop_params can't preempt. Mark them so the harness omits temperature.
    for _m in ("claude-opus-4-8", "claude-fable-5", "gpt-5.5", "claude-opus-5", "gpt-5.6-sol"):
        try:
            _fbmodels.MODELS_WITHOUT_TEMPERATURE.add(_m)
        except AttributeError:
            if _m not in _fbmodels.MODELS_WITHOUT_TEMPERATURE:
                _fbmodels.MODELS_WITHOUT_TEMPERATURE.append(_m)
    from freeciv_world.evaluation.rate_limiter import ProviderRateLimiter
    from freeciv_world.evaluation.parallel_evaluator import run_batch_evaluation
    return (LiteLLMModel, load_api_keys_from_gcp, ProviderRateLimiter,
            run_batch_evaluation)


HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from eci_scores import DEMO_MODEL_SET, GAP_FILLERS, demo_set_with_eci  # noqa: E402


# Climatology used when a row has no corpus match: the corpus-wide observed
# yes-rate. Mirrored as redlines.config.CLIM_FREECIV_OBSERVED (see
# docs/architecture.md on why that constant and Graph 4's 0.045 differ).
CLIM_FALLBACK = 0.0458


def class_key(q: dict) -> str:
    return f"{q['template_id']}|{q['target']}|{q['horizon']}"


def stratified_games(questions: list[dict], n_games: int, seed: int) -> list[str]:
    """Pick n_games game_ids so every tail class is represented, then fill."""
    rng = random.Random(seed)
    by_game = defaultdict(list)
    for q in questions:
        by_game[q["game_id"]].append(q)
    games = list(by_game)
    rng.shuffle(games)
    all_classes = {class_key(q) for q in questions}
    chosen, covered = [], set()
    # greedy: first cover every class
    for g in games:
        gc = {class_key(q) for q in by_game[g]}
        if gc - covered:
            chosen.append(g); covered |= gc
        if covered >= all_classes and len(chosen) >= n_games:
            break
    # fill up to n_games
    for g in games:
        if len(chosen) >= n_games:
            break
        if g not in chosen:
            chosen.append(g)
    return chosen[:n_games]


def cap_questions(qs: list[dict], cap: int, seed: int) -> list[dict]:
    """Cap questions/game, keeping class diversity (round-robin over classes)."""
    if len(qs) <= cap:
        return qs
    rng = random.Random(seed)
    by_class = defaultdict(list)
    for q in qs:
        by_class[class_key(q)].append(q)
    for v in by_class.values():
        rng.shuffle(v)
    out, classes = [], list(by_class)
    rng.shuffle(classes)
    i = 0
    while len(out) < cap and any(by_class.values()):
        c = classes[i % len(classes)]
        if by_class[c]:
            out.append(by_class[c].pop())
        i += 1
    return out


def ensure_report(game_id: str, data_dir: Path, turn: int) -> bool:
    """Generate turn-{turn} world report for a game if missing. Returns True if present."""
    out = data_dir / game_id / "world_report" / f"turn_{turn:03d}_report.txt"
    if out.exists():
        return True
    game_json = FBSIM_ROOT / "data" / "games" / f"{game_id}_data.json"
    if not game_json.exists():
        return False
    import scripts.generate_txt_report as gtr
    empty_rec = data_dir / game_id / "_rec"      # empty -> gov/scores NA, rest from json
    empty_rec.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        gtr.generate_txt_report(
            game_data_path=game_json, recording_dir=empty_rec,
            output_dir=out.parent, turn=turn, sample_interval=5, map_interval=10**9)
        return out.exists()
    except Exception as e:
        print(f"  ! report gen failed for {game_id}: {e}")
        return False


def score(results: list[dict], model_ids: list[str]) -> dict:
    """Per-model metrics on the low-prob set."""
    out = {}
    for mid in model_ids:
        pairs = []  # (p, y, climatology)
        for r in results:
            pred = r["predictions"].get(mid, {})
            p = pred.get("probability")
            if p is None:
                continue
            y = 1.0 if r["ground_truth"] else 0.0
            # `or` not `.get(k, default)`: attach_base_rates always SETS the
            # key, to None when a row has no corpus match, and .get would then
            # return that None and blow up the arithmetic below rather than
            # fall back. CLIM_FALLBACK is the corpus-wide observed yes-rate.
            clim = r.get("class_base_rate")
            if clim is None:
                clim = CLIM_FALLBACK
            pairs.append((p, y, clim))
        if not pairs:
            out[mid] = {"n": 0}
            continue
        n = len(pairs)
        brier = sum((p - y) ** 2 for p, y, _ in pairs) / n
        brier_clim = sum((c - y) ** 2 for _, y, c in pairs) / n
        bss = 1 - brier / brier_clim if brier_clim > 0 else None
        mean_p = sum(p for p, _, _ in pairs) / n
        mean_y = sum(y for _, y, _ in pairs) / n
        # decile calibration
        bins = defaultdict(list)
        for p, y, _ in pairs:
            b = min(9, int(p * 10))
            bins[b].append((p, y))
        calib = {b: {"mean_p": sum(pp for pp, _ in v) / len(v),
                     "obs": sum(yy for _, yy in v) / len(v),
                     "n": len(v)} for b, v in sorted(bins.items())}
        # calibration error (weighted |mean_p - obs|)
        ece = sum(len(v) / n * abs(sum(pp for pp, _ in v) / len(v) - sum(yy for _, yy in v) / len(v))
                  for v in bins.values())
        out[mid] = {"n": n, "brier": brier, "brier_climatology": brier_clim,
                    "bss": bss, "mean_pred": mean_p, "mean_obs": mean_y,
                    "ece": ece, "calibration": calib}
    return out


def attach_base_rates(results: list[dict], questions: list[dict]) -> int:
    """Stamp each result row's class_base_rate from the corpus. Returns n changed.

    Keyed on (game_id, question_id). question_id is a PER-GAME index that
    repeats across games — the 25,919 corpus instances carry only 336 distinct
    ids — so keying on it alone silently gives each row an unrelated game's
    base rate, which is then used as the climatology every Brier skill score
    is measured against.
    """
    br = {(q["game_id"], q["question_id"]): q.get("class_base_rate") for q in questions}
    changed = 0
    for r in results:
        was = r.get("class_base_rate")
        now = br.get((r.get("game_id"), r["question_id"]))
        r["class_base_rate"] = now
        if was != now:
            changed += 1
    return changed


def write_outputs(out: Path, tag: str, metadata: dict, results: list[dict],
                  metrics: dict, model_ids: list[str]) -> None:
    """Write eval_{tag}.json + metrics_{tag}.csv. Shared by a run and a rescore."""
    out.mkdir(parents=True, exist_ok=True)
    json.dump({"metadata": metadata, "results": results, "metrics": metrics},
              open(out / f"eval_{tag}.json", "w"), indent=2, default=str)
    with open(out / f"metrics_{tag}.csv", "w") as f:
        f.write("model,eci,n,brier,brier_climatology,bss,mean_pred,mean_obs,ece\n")
        for mid in model_ids:
            m = metrics[mid]
            f.write(f"{mid},{m.get('eci','')},{m.get('n',0)},{m.get('brier','')},"
                    f"{m.get('brier_climatology','')},{m.get('bss','')},"
                    f"{m.get('mean_pred','')},{m.get('mean_obs','')},{m.get('ece','')}\n")


def print_metrics(metrics: dict, model_ids: list[str], eci_lookup: dict) -> None:
    print("\n=== per-model metrics ===")
    print(f"{'model':40s} {'ECI':>4} {'n':>5} {'Brier':>7} {'BSS':>7} {'meanP':>6} {'obs':>6} {'ECE':>6}")
    for mid in sorted(model_ids, key=lambda m: eci_lookup.get(m, 0)):
        m = metrics[mid]
        if not m.get("n"):
            print(f"{mid:40s}  (no predictions)")
            continue
        eci = m.get("eci")
        print(f"{mid:40s} {str(eci if eci is not None else '?'):>4} {m['n']:>5} {m['brier']:>7.4f} "
              f"{(m['bss'] or 0):>7.3f} {m['mean_pred']:>6.3f} {m['mean_obs']:>6.3f} {m['ece']:>6.3f}")


def rescore(args, questions) -> int:
    """Recompute metrics from an EXISTING eval file. No API calls, no cost.

    The models never see class_base_rate — build_batch_prompt sends only
    question_text and the world report — so a bad base-rate join corrupts the
    climatology and every metric derived from it, but leaves the forecasts
    themselves untouched. That makes the metrics recoverable from the stored
    predictions; nothing needs re-forecasting.
    """
    tag = "smoke" if args.smoke else "full"
    path = args.out / f"eval_{tag}.json"
    if not path.exists():
        print(f"{path}: nothing to rescore")
        return 1
    doc = json.load(open(path))
    results, meta = doc["results"], doc.get("metadata", {})
    model_ids = args.models or meta.get("models") or []
    eci_lookup = meta.get("eci", {})
    if not model_ids:
        print(f"{path}: no model list in metadata; pass --models")
        return 1

    changed = attach_base_rates(results, questions)
    print(f"rescore: {len(results)} rows, {changed} base rate(s) corrected")

    metrics = score(results, model_ids)
    for mid in model_ids:
        metrics[mid]["eci"] = eci_lookup.get(mid)
    write_outputs(args.out, tag, meta, results, metrics, model_ids)
    print_metrics(metrics, model_ids, eci_lookup)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=Path,
                    default=FBSIM_ROOT / "data" / "lowprob" / "lowprob_questions.json")
    ap.add_argument("--games", type=int, default=150)
    ap.add_argument("--cap-per-game", type=int, default=12)
    ap.add_argument("--turn", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--models", nargs="*", help="override model ids")
    ap.add_argument("--with-gap-fillers", action="store_true", default=True)
    ap.add_argument("--no-gap-fillers", dest="with_gap_fillers", action="store_false")
    ap.add_argument("--out", type=Path, default=REPO / "results")
    ap.add_argument("--report-cache", type=Path, default=REPO / "results" / "reports")
    ap.add_argument("--concurrent-batches", type=int, default=6)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--smoke", action="store_true", help="1 cheap model, 5 games, cap 8")
    ap.add_argument("--dry-run", action="store_true", help="sample + reports only, no API")
    ap.add_argument("--rescore", action="store_true",
                    help="recompute metrics from the existing eval file "
                         "(re-joins class_base_rate from the corpus); no API calls")
    args = ap.parse_args()

    if args.smoke:
        args.games, args.cap_per_game = 5, 8
        args.models = args.models or ["openai/gpt-4o"]

    doc = json.load(open(args.questions))
    questions = doc["questions"]
    print(f"corpus: {len(questions)} instances, {doc['meta']['n_classes_selected']} classes")

    if args.rescore:
        return rescore(args, questions)

    # model set
    if args.models:
        model_rows = [(mid, mid.split("/")[-1], None, mid.split("/")[0]) for mid in args.models]
        eci_lookup = {}
    else:
        rows = demo_set_with_eci(include_gap_fillers=args.with_gap_fillers)
        model_rows = [(r["model_id"], r["label"], r["epoch_name"], r["access"]) for r in rows]
        eci_lookup = {r["model_id"]: r["eci"] for r in rows}
    model_ids = [m[0] for m in model_rows]
    print(f"models ({len(model_ids)}): " + ", ".join(model_ids))

    games = stratified_games(questions, args.games, args.seed)
    by_game = defaultdict(list)
    for q in questions:
        by_game[q["game_id"]].append(q)

    # generate reports + build batches
    print(f"generating turn-{args.turn} reports for {len(games)} games...")
    batches, skipped = [], []
    for gi, g in enumerate(games):
        if not ensure_report(g, args.report_cache, args.turn):
            skipped.append(g); continue
        qs = cap_questions(by_game[g], args.cap_per_game, args.seed + gi)
        for q in qs:
            q["parameters"] = {"snapshot_turn": args.turn}
            q.setdefault("question_type", "binary")
        batches.append(qs)
        if (gi + 1) % 25 == 0:
            print(f"  ...{gi+1}/{len(games)} games")
    n_q = sum(len(b) for b in batches)
    print(f"batches: {len(batches)} games, {n_q} questions, {len(skipped)} skipped")
    print(f"planned API calls: {len(batches) * len(model_ids)} "
          f"({len(batches)} batches x {len(model_ids)} models)")

    if args.dry_run:
        cov = {class_key(q) for b in batches for q in b}
        print(f"dry-run: class coverage {len(cov)} classes; no API calls made.")
        return 0

    LiteLLMModel, load_api_keys_from_gcp, ProviderRateLimiter, run_batch_evaluation = load_harness()
    load_api_keys_from_gcp()
    models = [LiteLLMModel(id=mid) for mid in model_ids]
    rate_limiter = ProviderRateLimiter(custom_limits={
        "OpenAIProvider": 6, "AnthropicProvider": 4, "GoogleProvider": 4})

    args.out.mkdir(parents=True, exist_ok=True)
    ckpt = args.out / ("checkpoint_smoke.json" if args.smoke else "checkpoint.json")
    results = asyncio.run(run_batch_evaluation(
        batches, models, rate_limiter, data_dir=args.report_cache,
        checkpoint_file=ckpt, checkpoint_interval=5,
        metadata={"seed": args.seed, "games": len(batches)},
        timeout=args.timeout, concurrent_batches=args.concurrent_batches))

    attach_base_rates(results, [q for b in batches for q in b])

    metrics = score(results, model_ids)
    for mid in model_ids:
        metrics[mid]["eci"] = eci_lookup.get(mid)

    tag = "smoke" if args.smoke else "full"
    write_outputs(args.out, tag,
                  {"games": len(batches), "questions": n_q, "seed": args.seed,
                   "models": model_ids, "eci": eci_lookup},
                  results, metrics, model_ids)
    print_metrics(metrics, model_ids, eci_lookup)

    if not args.smoke and eci_lookup:
        try:
            plot(metrics, model_rows, eci_lookup, args.out)
        except Exception as e:
            print("plot failed:", e)
    print(f"\nwrote {args.out}/eval_{tag}.json + metrics_{tag}.csv")
    return 0


def plot(metrics, model_rows, eci_lookup, out: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    labels = {m[0]: m[1] for m in model_rows}
    pts = [(eci_lookup[mid], metrics[mid]["bss"], labels[mid])
           for mid in eci_lookup if metrics[mid].get("bss") is not None]
    pts.sort()
    fig, ax = plt.subplots(figsize=(8, 6))
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    ax.scatter(xs, ys, s=60, zorder=3)
    for x, y, lab in pts:
        ax.annotate(lab, (x, y), textcoords="offset points", xytext=(6, 4), fontsize=8)
    ax.axhline(0, color="gray", lw=0.8, ls="--")
    ax.set_xlabel("Epoch Capabilities Index (ECI)")
    ax.set_ylabel("Brier Skill Score vs per-class climatology")
    ax.set_title("Low-probability forecasting skill vs ECI (FreeCiv tail corpus)")
    fig.tight_layout(); fig.savefig(out / "eci_scatter.png", dpi=140)

    # calibration grid
    n = len(pts)
    cols = 3; rows = (n + cols - 1) // cols
    fig2, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3.2 * rows), squeeze=False)
    for i, (_, _, lab) in enumerate(pts):
        mid = next(m for m in eci_lookup if labels[m] == lab)
        ax = axes[i // cols][i % cols]
        cal = metrics[mid]["calibration"]
        px = [v["mean_p"] for v in cal.values()]
        py = [v["obs"] for v in cal.values()]
        ax.plot([0, 0.3], [0, 0.3], color="gray", lw=0.8, ls="--")
        ax.scatter(px, py, s=[min(120, v["n"]) for v in cal.values()])
        ax.set_title(f"{lab} (ECI {eci_lookup[mid]})", fontsize=9)
        ax.set_xlim(0, 0.3); ax.set_ylim(0, 0.3)
        ax.set_xlabel("mean predicted"); ax.set_ylabel("observed freq")
    for j in range(n, rows * cols):
        axes[j // cols][j % cols].axis("off")
    fig2.tight_layout(); fig2.savefig(out / "calibration.png", dpi=140)
    print(f"wrote {out}/eci_scatter.png + calibration.png")


if __name__ == "__main__":
    raise SystemExit(main())
