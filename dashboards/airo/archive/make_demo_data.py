#!/usr/bin/env python3
"""Turn eval results into the live data blob for jason-demo Graph 4.

Emits results/graph4_data.json AND splices it into jason-demo.live.html so the
self-contained demo shows REAL numbers (file:// can't fetch, so we inline).

Graph 4 (Option A): all demo models' calibration curves on the rare-event domain,
colored by ECI, plus an ECI-vs-skill scatter (the headline).

    uv run python code/make_demo_data.py            # uses results/eval_full.json
    uv run python code/make_demo_data.py --input results/checkpoint.json --preliminary
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from eci_scores import demo_set_with_eci

FBSIM = Path(os.path.expanduser("~/Projects/forecastbench-sim"))  # sibling forecastbench-sim checkout


def deciles(samples: list[tuple[float, float]]) -> dict:
    """Replicate the demo's JS deciles(): 10 equal-count bins by predicted prob."""
    s = sorted(samples, key=lambda x: x[0])
    N, G = len(s), 10
    obar = sum(o for _, o in s) / N
    pts, res = [], 0.0
    for g in range(G):
        lo, hi = (g * N) // G, ((g + 1) * N) // G
        sl = s[lo:hi]
        if not sl:
            continue
        mp = sum(p for p, _ in sl) / len(sl)
        mo = sum(o for _, o in sl) / len(sl)
        pts.append({"pred": mp, "obs": mo, "n": len(sl)})
        res += len(sl) * (mo - obar) ** 2
    brier = sum((p - o) ** 2 for p, o in s) / N
    return {"pts": pts, "resolution": res / N, "brier": brier, "base": obar,
            "spread": pts[-1]["pred"] - pts[0]["pred"]}


# ECI-ordered color ramp (low = cool grey-blue -> high = warm red)
RAMP = ["#9aa7b3", "#7d93c8", "#5f86d6", "#4f9bc0", "#4bb39b", "#8bb84e",
        "#c9b03c", "#e39336", "#e46b3f", "#d94452", "#b5316a"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=REPO / "results" / "eval_full.json")
    ap.add_argument("--questions", type=Path,
                    default=FBSIM / "data" / "lowprob" / "lowprob_questions.json")
    ap.add_argument("--template", type=Path, default=REPO / "jason-demo.html")
    ap.add_argument("--out-html", type=Path, default=REPO / "jason-demo.live.html")
    ap.add_argument("--out-json", type=Path, default=REPO / "results" / "graph4_data.json")
    ap.add_argument("--preliminary", action="store_true")
    args = ap.parse_args()

    doc = json.load(open(args.input))
    # eval_full.json -> {"results":[...]}; checkpoint.json -> {"results":[...]}
    results = doc["results"] if isinstance(doc, dict) else doc

    # base-rate join (game_id, question_id) -> class_base_rate
    qdoc = json.load(open(args.questions))
    br = {(q["game_id"], q["question_id"]): q["class_base_rate"] for q in qdoc["questions"]}

    rows = demo_set_with_eci(include_gap_fillers=True)
    order = sorted(rows, key=lambda r: r["eci"])

    models_out, scatter = [], []
    all_samples = []  # for overall base rate
    for i, r in enumerate(order):
        mid = r["model_id"]
        samples, clim_pairs = [], []
        for res in results:
            pred = res.get("predictions", {}).get(mid, {})
            p = pred.get("probability")
            if p is None:
                continue
            y = 1.0 if res["ground_truth"] else 0.0
            samples.append((p, y))
            c = br.get((res["game_id"], res["question_id"]), 0.0458)
            clim_pairs.append((c, y))
        if len(samples) < 20:
            continue
        d = deciles(samples)
        n = len(samples)
        brier = d["brier"]
        brier_clim = sum((c - y) ** 2 for c, y in clim_pairs) / n
        bss = 1 - brier / brier_clim if brier_clim > 0 else None
        mean_p = sum(p for p, _ in samples) / n
        mean_o = sum(o for _, o in samples) / n
        color = RAMP[min(len(RAMP) - 1, round(i * (len(RAMP) - 1) / max(1, len(order) - 1)))]
        entry = {"key": mid, "label": r["label"], "eci": r["eci"], "color": color,
                 "n": n, "brier": round(brier, 4), "bss": round(bss, 3) if bss is not None else None,
                 "meanPred": round(mean_p, 4), "meanObs": round(mean_o, 4),
                 "pts": [{"pred": round(p["pred"], 5), "obs": round(p["obs"], 5), "n": p["n"]}
                         for p in d["pts"]]}
        models_out.append(entry)
        scatter.append({"eci": r["eci"], "bss": entry["bss"], "label": r["label"],
                        "color": color, "meanPred": entry["meanPred"], "meanObs": entry["meanObs"]})
        all_samples.extend(samples)

    base = sum(o for _, o in all_samples) / len(all_samples)
    # adaptive x-domain: cover the models' top decile (overconfidence runs high)
    max_pred = max(m["pts"][-1]["pred"] for m in models_out)
    domain_max = min(0.6, (int(max_pred / 0.05) + 1) * 0.05)

    blob = {"preliminary": args.preliminary,
            "base": round(base, 4), "domainMax": round(domain_max, 3),
            "nModels": len(models_out), "nQuestions": len(results),
            "models": models_out, "scatter": scatter}
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    json.dump(blob, open(args.out_json, "w"), indent=2)

    # splice into HTML
    template = args.template.read_text()
    inject = (f"<script>window.__GRAPH4__ = "
              f"{json.dumps(blob)};</script>\n")
    marker = "<!--GRAPH4_DATA-->"
    if marker in template:
        import re
        template = re.sub(r"<!--GRAPH4_DATA-->.*?<!--/GRAPH4_DATA-->",
                          f"{marker}\n{inject}<!--/GRAPH4_DATA-->", template, flags=re.S)
    else:
        template = template.replace("</head>",
            f"{marker}\n{inject}<!--/GRAPH4_DATA-->\n</head>", 1)
    args.out_html.write_text(template)

    print(f"{'[PRELIMINARY] ' if args.preliminary else ''}wrote {args.out_json.name} + {args.out_html.name}")
    print(f"models: {len(models_out)}  questions: {len(results)}  base: {base*100:.2f}%  domainMax: {domain_max}")
    print(f"\n{'model':14s} {'ECI':>4} {'n':>5} {'Brier':>7} {'BSS':>7} {'meanP':>6} {'obs':>6}")
    for m in models_out:
        print(f"{m['label']:14s} {m['eci']:>4} {m['n']:>5} {m['brier']:>7.4f} "
              f"{(m['bss'] if m['bss'] is not None else 0):>7.3f} {m['meanPred']:>6.3f} {m['meanObs']:>6.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
