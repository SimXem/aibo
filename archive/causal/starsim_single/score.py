"""Score the single-region continuous design.

Per (model, item): median over reps of each quantile -> the model's forecast
quantiles. CRPS (quantile pinball approximation, fbsim_core.metrics.compute_crps)
averaged over the simulator's matched-seed samples y:
  CRPS_model  = mean_y CRPS(model quantiles, y)
  CRPS_oracle = mean_y CRPS(truth quantiles, y)      irreducible floor
  CRPS_ref    = mean_y CRPS(climatology, y): ONE fixed reference for every condition and rung —
                climatology.json, the pooled target distribution over all 4 worlds x coverages
                {0, 25, 50, 75, 90}% at that horizon (knows the simulator and the question, not
                this world's R0 or the coverage)
  recovered   = 1 − (CRPS_model − CRPS_oracle) / (CRPS_ref − CRPS_oracle)
              1 = matches the simulator's distribution, 0 = climatology, < 0 = worse
Per model: mean recovered over items, per condition; effect_recovered = mean over
items of (q50_int − q50_base) / (truth_int.p50 − truth_base.p50), with q50_base
from the model's own baseline prompt.

  uv run python results/causal/starsim_single/score.py [--pilot] [--tag T]
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "starsim_causal"))
from models import load_roster  # noqa: E402
from fbsim_core.metrics import compute_crps  # noqa: E402

KEYS = ("p10", "p25", "p50", "p75", "p90")
TAU = dict(zip(KEYS, (0.10, 0.25, 0.50, 0.75, 0.90)))


def load_results(path):
    reps = {}
    if path.exists():
        for line in open(path):
            if line.strip():
                r = json.loads(line); reps.setdefault((r["model"], r["item_id"]), []).append(r)
    return reps


def crps_vs_samples(q, samples):
    return float(np.mean([compute_crps(q, y) for y in samples]))


CLIM = json.load(open(HERE / "climatology.json"))


def climatology(items, item):
    return {k: CLIM[str(item["horizon"])][k] for k in KEYS}


def recovered(q, item, truth_key, items):
    tr = item[truth_key]; ys = tr["samples"]
    oracle = crps_vs_samples({k: tr[k] for k in KEYS}, ys)
    ref = crps_vs_samples(climatology(items, item), ys)
    return 1 - (crps_vs_samples(q, ys) - oracle) / (ref - oracle)


def medians(reps, mid, items):
    out = {}
    for i in items:
        rs = reps.get((mid, i))
        if rs:
            out[i] = {k: statistics.median(r[k] for r in rs) for k in KEYS}
    return out


def score_condition(med, items, truth_key):
    if not med:
        return None
    rec = {i: recovered(med[i], items[i], truth_key, items) for i in med}
    rel = {i: abs(med[i]["p50"] - items[i][truth_key]["p50"]) / max(items[i][truth_key]["p50"], 1) for i in med}
    return {"n_items": len(med), "complete": len(med) == len(items),
            "recovered": statistics.mean(rec.values()), "median_rel_err": statistics.median(rel.values()),
            "per_item": {i: dict(q=med[i], recovered=rec[i]) for i in med}}


def score_model(m, base, intv, items):
    mid = m.openrouter_id
    mb, mi = medians(base, mid, items), medians(intv, mid, items)
    out = {"eci": m.eci, "fb_overall": m.fb_overall,
           "n_resp_base": sum(len(base.get((mid, i), [])) for i in items),
           "n_resp_int": sum(len(intv.get((mid, i), [])) for i in items),
           "baseline": score_condition(mb, items, "truth_base"),
           "intervention": score_condition(mi, items, "truth_int")}
    both = [i for i in items if i in mb and i in mi]
    if both:
        eff = {i: (mi[i]["p50"] - mb[i]["p50"]) / items[i]["effect_median"] for i in both}
        out["effect_recovered"] = statistics.mean(eff.values()); out["effect_per_item"] = eff
        out["complete"] = len(both) == len(items)
    else:
        out["effect_recovered"] = None; out["complete"] = False
    return out


def gradient(flat, metric, against):
    rows = [(v[against], v[metric]) for v in flat.values()
            if v.get("complete") and v.get(against) is not None and v.get(metric) is not None]
    if len(rows) < 3:
        return {"n": len(rows), "rho": None, "p": None}
    x, y = zip(*rows); rho, p = spearmanr(x, y)
    return {"n": len(rows), "rho": float(rho), "p": float(p)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-dir", default=str(HERE / "results"))
    ap.add_argument("--worlds", default=str(HERE / "worlds.json"))
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    rdir = Path(a.results_dir)
    suffix = "_pilot" if a.pilot else (f"_{a.tag}" if a.tag else "")
    items = {i["item_id"]: i for i in json.load(open(a.worlds))["items"]}
    base = load_results(rdir / f"baseline{'_pilot' if a.pilot else ''}.jsonl")
    intv = load_results(rdir / f"intervention{suffix}.jsonl")
    table = {}
    for m in load_roster():
        t = score_model(m, base, intv, items)
        if t["baseline"] or t["intervention"]:
            table[m.openrouter_id] = t
    print(f"{'ECI':>6s} {'model':40s} | {'BASE recov':>10s} {'relerr':>6s} | {'INT recov':>10s} {'relerr':>6s} | {'effect':>6s}")
    for mid, t in table.items():
        def c(x):
            return f"{x['recovered']:10.3f} {x['median_rel_err']:6.2f}" if x else f"{'-':>10s} {'-':>6s}"
        eff = f"{t['effect_recovered']:6.3f}" if t["effect_recovered"] is not None else f"{'-':>6s}"
        print(f"{t['eci']:6.1f} {mid:40s} | {c(t['baseline'])} | {c(t['intervention'])} | {eff}{'' if t['complete'] else '  (incomplete)'}")
    flat = {mid: {"eci": t["eci"], "fb_overall": t["fb_overall"], "complete": t["complete"],
                  "n_resp_base": t["n_resp_base"], "n_resp_int": t["n_resp_int"],
                  "effect_recovered": t["effect_recovered"],
                  **{f"baseline_{k}": v for k, v in (t["baseline"] or {}).items() if k != "per_item"},
                  **{f"intervention_{k}": v for k, v in (t["intervention"] or {}).items() if k != "per_item"}}
            for mid, t in table.items()}
    grads = {met: {ag: gradient(flat, met, ag) for ag in ("eci", "fb_overall")}
             for met in ("baseline_recovered", "intervention_recovered", "effect_recovered")}
    print("\nSpearman (complete models):")
    for met, ags in grads.items():
        print(f"  {met:24s} " + " | ".join(f"vs {ag}: rho={g['rho']:+.2f} p={g['p']:.3f} n={g['n']}" if g["rho"] is not None
                                           else f"vs {ag}: n={g['n']}" for ag, g in ags.items()))
    json.dump(table, open(rdir / f"scores{suffix}.json", "w"), indent=1)
    json.dump({"models": flat, "gradient": grads}, open(rdir / f"scores_summary{suffix}.json", "w"), indent=1)
    print(f"[saved] scores{suffix}.json, scores_summary{suffix}.json -> {rdir}")


if __name__ == "__main__":
    main()
