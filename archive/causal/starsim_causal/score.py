"""Score the v2 bench for every model, then test the capability gradient.

Per item, the median over the K reps first. Then, per model:
  baseline      direction (median p on the truth side of 0.5), MAE, Brier vs
                truth_base, and
                recovered = 1 - Σ(p̂-P*)² / Σ(½-P*)²  — Brier skill against the
                simulator's certified P*: 1 = ceiling (forecasts P* exactly),
                0 = uninformed (always ½), < 0 = confidently wrong.
  intervention  the same four against truth_int, plus
                effect_recovered = mean_i 1 − |(p̂_int_i − p̂_base_i) − Δ_do_i| —
                share of the unit causal effect the model got right, with
                p̂_base taken from the model's own BASELINE prompt (separate
                call). On full-flip items (Δ_do = ±1) this equals
                (p̂_int − p̂_base)/Δ_do exactly: 1 = full flip, 0 = ignored the
                intervention, < 0 = moved the wrong way. On no-flip items
                (Δ_do = 0; v3 sub-threshold rungs) it is 1 − |p̂_int − p̂_base|:
                1 = held, 0 = flipped anyway.
                flip_dir = among items with Δ_do ≠ 0, those where
                sign(p̂_int − p̂_base) = sign(Δ_do) and |p̂_int − p̂_base| > 0.05.
Gradient: Spearman rho of each metric against ECI across models with every
item answered in both conditions (descriptive; n ≈ 24, models not independent).

Usage:
  uv run python results/causal/starsim_causal/score.py            # results/{baseline,intervention}.jsonl -> results/scores_*.json
  uv run python results/causal/starsim_causal/score.py --pilot
  uv run python results/causal/starsim_causal/score.py --worlds starsim_causal/worlds_c50.json --tag c50
        # v3 rung: baseline.jsonl (shared) + intervention_c50.jsonl -> scores_c50.json, scores_summary_c50.json
"""
import argparse
import json
import statistics
from pathlib import Path

from scipy.stats import spearmanr

from models import load_roster

HERE = Path(__file__).resolve().parent


def load_results(path: Path) -> dict[tuple[str, str], list[dict]]:
    reps: dict[tuple[str, str], list[dict]] = {}
    if not path.exists():
        return reps
    for line in open(path):
        if line.strip():
            r = json.loads(line)
            reps.setdefault((r["model"], r["item_id"]), []).append(r)
    return reps


def recovered_score(pairs) -> float | None:
    """pairs: (p_hat, p_star). Brier skill vs the 0.5 forecast, against P*."""
    pairs = list(pairs)
    denom = sum((0.5 - t) ** 2 for _, t in pairs)
    if not pairs or denom == 0:
        return None
    return 1 - sum((p - t) ** 2 for p, t in pairs) / denom


def medians(reps, model_id, items):
    return {i: statistics.median(r["p"] for r in reps[(model_id, i)])
            for i in items if reps.get((model_id, i))}


def score_condition(med, items, truth_key):
    if not med:
        return None
    errs = {i: abs(med[i] - items[i][truth_key]) for i in med}
    hits = sum((med[i] > 0.5) == (items[i][truth_key] > 0.5) for i in med)
    return {"n_items": len(med), "complete": len(med) == len(items),
            "direction": f"{hits}/{len(med)}", "direction_frac": hits / len(med),
            "mae": statistics.median(errs.values()),
            "brier": statistics.mean(e ** 2 for e in errs.values()),
            "recovered": recovered_score((med[i], items[i][truth_key]) for i in med),
            "per_item": med}


def score_model(m, base, intv, items):
    mb, mi = medians(base, m.openrouter_id, items), medians(intv, m.openrouter_id, items)
    out = {"eci": m.eci, "fb_overall": m.fb_overall,
           "n_resp_base": sum(len(base.get((m.openrouter_id, i), [])) for i in items),
           "n_resp_int": sum(len(intv.get((m.openrouter_id, i), [])) for i in items),
           "baseline": score_condition(mb, items, "truth_base"),
           "intervention": score_condition(mi, items, "truth_int")}
    both = [i for i in items if i in mb and i in mi]
    if both:
        deltas = {i: mi[i] - mb[i] for i in both}
        out["effect_recovered"] = statistics.mean(1 - abs(deltas[i] - items[i]["delta_do"]) for i in both)
        flip_items = [i for i in both if abs(items[i]["delta_do"]) >= 0.5]   # certified flips only
        flips = sum((deltas[i] > 0) == (items[i]["delta_do"] > 0) and abs(deltas[i]) > 0.05 for i in flip_items)
        out["flip_dir"] = f"{flips}/{len(flip_items)}" if flip_items else None
        out["flip_frac"] = flips / len(flip_items) if flip_items else None
        out["delta_per_item"] = deltas
        out["complete"] = len(both) == len(items)
    else:
        out["effect_recovered"] = None; out["complete"] = False
    return out


def gradient(table, metric, against):
    rows = [(v[against], v[metric]) for v in table.values()
            if v.get("complete") and v.get(against) is not None and v.get(metric) is not None]
    if len(rows) < 3:
        return {"n": len(rows), "rho": None, "p": None}
    x, y = zip(*rows)
    if len(set(x)) < 2 or len(set(y)) < 2:
        return {"n": len(rows), "rho": None, "p": None, "note": "constant input"}
    rho, p = spearmanr(x, y)
    return {"n": len(rows), "rho": float(rho), "p": float(p)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-dir", default=str(HERE / "results"))
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--worlds", default=str(HERE / "worlds.json"))
    ap.add_argument("--tag", default=None, help="v3 rung tag (see Usage)")
    a = ap.parse_args()
    rdir = Path(a.results_dir)
    suffix = "_pilot" if a.pilot else (f"_{a.tag}" if a.tag else "")
    items = {i["item_id"]: i for i in json.load(open(a.worlds))["items"]}
    base = load_results(rdir / f"baseline{'_pilot' if a.pilot else ''}.jsonl")   # shared across rungs
    intv = load_results(rdir / f"intervention{suffix}.jsonl")
    table = {}
    for m in load_roster():
        t = score_model(m, base, intv, items)
        if t["baseline"] or t["intervention"]:
            table[m.openrouter_id] = t

    print(f"{'ECI':>6s} {'model':40s} | {'BASELINE':^26s} | {'INTERVENTION':^26s} | {'effect':>6s} {'flip':>4s}")
    print(f"{'':>6s} {'':40s} | {'dir':>4s} {'MAE':>6s} {'Brier':>6s} {'recov':>6s} | "
          f"{'dir':>4s} {'MAE':>6s} {'Brier':>6s} {'recov':>6s} |")
    for mid, t in table.items():
        def cell(c):
            return (f"{c['direction']:>4s} {c['mae']:6.3f} {c['brier']:6.4f} {c['recovered']:6.3f}" if c
                    else f"{'-':>4s} {'-':>6s} {'-':>6s} {'-':>6s}")
        eff = f"{t['effect_recovered']:6.3f} {t.get('flip_dir') or '-':>4s}" if t["effect_recovered"] is not None else f"{'-':>6s} {'-':>4s}"
        flag = "" if t["complete"] else "  (incomplete)"
        print(f"{t['eci']:6.1f} {mid:40s} | {cell(t['baseline'])} | {cell(t['intervention'])} | {eff}{flag}")

    flat = {mid: {"eci": t["eci"], "fb_overall": t["fb_overall"], "complete": t["complete"],
                  "n_resp_base": t["n_resp_base"], "n_resp_int": t["n_resp_int"],
                  "effect_recovered": t["effect_recovered"], "flip_dir": t.get("flip_dir"),
                  "flip_frac": t.get("flip_frac"),
                  **{f"baseline_{k}": v for k, v in (t["baseline"] or {}).items() if k != "per_item"},
                  **{f"intervention_{k}": v for k, v in (t["intervention"] or {}).items() if k != "per_item"}}
            for mid, t in table.items()}
    grads = {met: {ag: gradient(flat, met, ag) for ag in ("eci", "fb_overall")}
             for met in ("baseline_recovered", "intervention_recovered", "effect_recovered", "flip_frac")}
    print("\nCapability gradient (Spearman rho, complete models only; descriptive):")
    for met, ags in grads.items():
        cells = [f"vs {ag}: " + (f"rho={g['rho']:+.2f} p={g['p']:.3f} n={g['n']}" if g["rho"] is not None
                                 else f"n={g['n']} ({g.get('note', 'too few')})") for ag, g in ags.items()]
        print(f"  {met:24s} " + " | ".join(cells))

    json.dump(table, open(rdir / f"scores{suffix}.json", "w"), indent=1)
    json.dump({"models": flat, "gradient": grads}, open(rdir / f"scores_summary{suffix}.json", "w"), indent=1)
    print(f"\n[saved] scores{suffix}.json, scores_summary{suffix}.json -> {rdir}")


if __name__ == "__main__":
    main()
