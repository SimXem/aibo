#!/usr/bin/env python3
"""Graph 4 (Jason's calibration format) fed the TWO-SIM AVERAGE.

Keeps Jason's original Graph-4 design (per-model calibration curves + Brier skill).
For each model, pools its forecasts from BOTH simulators, weighting each simulator
EQUALLY (so it's an average, not a count-weighted pool):
  - CivBench (FreeCiv): H2-H4 horizon x 5-9% base-rate subset of the full eval.
  - Starsim pandemic: the deaths-threshold smoke (per-question preds).
Where only one simulator scored a model, that one is used.

Emits window.__GRAPH4__ (calibration-curve blob, same shape make_demo_pandemic used)
+ graph4_combined.json, and splices into jason-demo.live.html.

    uv run python code/make_demo_combined.py --final
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FBSIM = Path.home() / "Projects" / "forecastbench-sim"
sys.path.insert(0, str(REPO / "code"))
from eci_scores import demo_set_with_eci


def spearman(xs, ys):
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i]); r = [0] * len(v)
        for k, i in enumerate(s): r[i] = k
        return r
    rx, ry = rank(xs), rank(ys); n = len(xs)
    if n < 2: return 0.0
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - 6 * d2 / (n * (n * n - 1))

FC_HORIZONS = {"H2", "H3", "H4"}
FC_BAND = (0.05, 0.09)
PAN_MIN_N = 400
RAMP = ["#9aa7b3", "#7d93c8", "#5f86d6", "#4f9bc0", "#4bb39b", "#8bb84e",
        "#c9b03a", "#e08b3e", "#dd6140", "#cf3f4e", "#b52a55"]


def freeciv_pairs(eval_path, questions_path):
    """label -> list of (pred, obs, clim) on the CivBench subset."""
    results = json.load(open(eval_path))["results"]
    qm = {q["question_id"]: q for q in json.load(open(questions_path))["questions"]}
    rows = []
    for r in results:
        q = qm.get(r["question_id"], {})
        if q.get("horizon") in FC_HORIZONS and FC_BAND[0] <= q.get("class_base_rate", 0.045) < FC_BAND[1]:
            r["_br"] = q["class_base_rate"]; rows.append(r)
    out = {}
    for m in demo_set_with_eci(include_gap_fillers=True):
        mid = m["model_id"]; pairs = []
        for r in rows:
            p = r.get("predictions", {}).get(mid, {}).get("probability")
            if p is None: continue
            pairs.append((p, 1.0 if r["ground_truth"] else 0.0, r["_br"]))
        if pairs: out[m["label"]] = pairs
    return out


def pandemic_pairs(preds_path):
    doc = json.load(open(preds_path))
    return {m["label"]: [(p, y, c) for p, y, c in m["samples"]]
            for m in doc.values() if len(m["samples"]) >= PAN_MIN_N}


def wdeciles(weighted):
    """weighted list of (pred, obs, w) -> 10 equal-weight decile points."""
    s = sorted(weighted, key=lambda t: t[0])
    W = sum(w for _, _, w in s)
    if W <= 0: return []
    step = W / 10.0
    bins = [[] for _ in range(10)]
    cum = 0.0
    for p, o, w in s:
        bins[min(9, int(cum / step))].append((p, o, w))
        cum += w
    pts = []
    for b in bins:
        if not b: continue
        ww = sum(w for _, _, w in b)
        pts.append({"pred": sum(p * w for p, _, w in b) / ww,
                    "obs": sum(o * w for _, o, w in b) / ww, "n": len(b)})
    return pts


def bss_of(pairs):
    if not pairs: return None
    n = len(pairs)
    b = sum((p - o) ** 2 for p, o, c in pairs) / n
    bc = sum((c - o) ** 2 for p, o, c in pairs) / n
    return round(1 - b / bc, 3) if bc > 0 else None


def combine(fc, pan):
    """equal-weight per simulator -> weighted pairs (pred, obs, clim, w)."""
    parts = []
    for src in (fc, pan):
        if src:
            w = 0.5 / len(src) if (fc and pan) else 1.0 / len(src)
            parts += [(p, o, c, w) for p, o, c in src]
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", type=Path, default=REPO / "results" / "eval_full.json")
    ap.add_argument("--questions", type=Path, default=FBSIM / "data" / "lowprob" / "lowprob_questions.json")
    ap.add_argument("--pandemic-preds", type=Path, default=REPO / "results" / "pandemic" / "smoke_preds.json")
    ap.add_argument("--template", type=Path, default=REPO / "jason-demo.html")
    ap.add_argument("--out-html", type=Path, default=REPO / "jason-demo.live.html")
    ap.add_argument("--out-json", type=Path, default=REPO / "results" / "graph4_combined.json")
    ap.add_argument("--final", action="store_true")
    args = ap.parse_args()

    fc = freeciv_pairs(args.eval, args.questions)
    pan = pandemic_pairs(args.pandemic_preds)
    order = sorted(demo_set_with_eci(include_gap_fillers=True), key=lambda m: m["eci"])

    models_out, scatter, all_w = [], [], []
    for i, m in enumerate(order):
        lbl = m["label"]
        comb = combine(fc.get(lbl, []), pan.get(lbl, []))
        if not comb: continue
        wpairs = [(p, o, w) for p, o, c, w in comb]
        pts = wdeciles(wpairs)
        W = sum(w for _, _, _, w in comb)
        brier = sum(w * (p - o) ** 2 for p, o, c, w in comb) / W
        brier_clim = sum(w * (c - o) ** 2 for p, o, c, w in comb) / W
        bss = 1 - brier / brier_clim if brier_clim > 0 else None
        mean_p = sum(w * p for p, o, c, w in comb) / W
        mean_o = sum(w * o for p, o, c, w in comb) / W
        color = RAMP[min(len(RAMP) - 1, round(i * (len(RAMP) - 1) / max(1, len(order) - 1)))]
        entry = {"key": m["model_id"], "label": lbl, "eci": m["eci"], "color": color,
                 "n": len(comb), "brier": round(brier, 4),
                 "bss": round(bss, 3) if bss is not None else None,
                 "meanPred": round(mean_p, 4), "meanObs": round(mean_o, 4),
                 "sims": ("civbench+starsim" if (lbl in fc and lbl in pan) else ("civbench" if lbl in fc else "starsim")),
                 "pts": [{"pred": round(p["pred"], 5), "obs": round(p["obs"], 5), "n": p["n"]} for p in pts]}
        models_out.append(entry)
        scatter.append({"eci": m["eci"], "bss": entry["bss"], "label": lbl, "color": color,
                        "meanPred": entry["meanPred"], "meanObs": entry["meanObs"],
                        "bssCiv": bss_of(fc.get(lbl, [])), "bssStar": bss_of(pan.get(lbl, []))})
        all_w += comb

    base = sum(w * o for p, o, c, w in all_w) / sum(w for p, o, c, w in all_w)
    max_pred = max(m["pts"][-1]["pred"] for m in models_out)
    domain_max = min(0.9, (int(max_pred / 0.05) + 1) * 0.05)

    rho = round(spearman([s["eci"] for s in scatter], [s["bss"] for s in scatter]), 2)
    blob = {"preliminary": not args.final, "world": "combined", "rho": rho,
            "bandLabel": "1\u20139%",
            "corpusLabel": "two-sim average (CivBench tail + Starsim pandemic)",
            "base": round(base, 4), "domainMax": round(domain_max, 3),
            "nModels": len(models_out), "nQuestions": sum(m["n"] for m in models_out),
            "models": models_out, "scatter": scatter}
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    json.dump(blob, open(args.out_json, "w"), indent=2)

    template = args.template.read_text()
    inject = f"<script>window.__GRAPH4__ = {json.dumps(blob)};</script>\n"
    marker = "<!--GRAPH4_DATA-->"
    if marker in template:
        template = re.sub(r"<!--GRAPH4_DATA-->.*?<!--/GRAPH4_DATA-->",
                          f"{marker}\n{inject}<!--/GRAPH4_DATA-->", template, flags=re.S)
    else:
        template = template.replace("</head>", f"{marker}\n{inject}<!--/GRAPH4_DATA-->\n</head>", 1)
    args.out_html.write_text(template)

    print(f"{'[FINAL] ' if args.final else '[prelim] '}wrote {args.out_json.name} + {args.out_html.name}")
    print(f"base {base*100:.2f}%  domainMax {domain_max}  nModels {len(models_out)}")
    print(f"\n{'model':14s} {'ECI':>4} {'BSS':>7} {'meanP':>6} sims")
    for m in models_out:
        print(f"{m['label']:14s} {m['eci']:>4} {(m['bss'] or 0):>7.2f} {m['meanPred']:>6.3f}  {m['sims']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
