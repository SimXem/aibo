#!/usr/bin/env python3
"""Graph 4 = TWO-SIM AVERAGE of tail skill (Brier skill score) vs capability (ECI).

Per model, average the Brier skill across the two simulators we have:
  - CivBench (FreeCiv): the H2-H4 horizon x 5-9% base-rate subset of the full eval.
  - Starsim pandemic: the deaths-threshold smoke.
Where only ONE sim has a usable score for a model, use that one (per user: fine for now).

Emits window.__GRAPH4__ (mode="avg_scatter") + graph4_avg.json, and splices into
jason-demo.live.html. Fully reproducible from eval_full.json + smoke_metrics.json.

    uv run python code/make_demo_avg.py --final
"""
from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FBSIM = Path(os.path.expanduser("~/Projects/forecastbench-sim"))  # sibling forecastbench-sim checkout
sys.path.insert(0, str(REPO / "code"))
from eci_scores import demo_set_with_eci

# --- FreeCiv subset definition (explicit + changeable; selected on mechanism: ---
#     mid-horizon, less-rare questions are the forecastable slice) ---
FC_HORIZONS = {"H2", "H3", "H4"}
FC_BAND = (0.05, 0.09)
PAN_MIN_N = 400  # drop thin-coverage pandemic models (e.g. GPT-5 timeouts)

RAMP = ["#9aa7b3", "#7d93c8", "#5f86d6", "#4f9bc0", "#4bb39b", "#8bb84e",
        "#c9b03a", "#e08b3e", "#dd6140", "#cf3f4e", "#b52a55"]


def spearman(xs, ys):
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i]); r = [0] * len(v)
        for k, i in enumerate(s): r[i] = k
        return r
    rx, ry = rank(xs), rank(ys); n = len(xs)
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - 6 * d2 / (n * (n * n - 1))


def freeciv_subset_bss(eval_path, questions_path):
    results = json.load(open(eval_path))["results"]
    qm = {q["question_id"]: q for q in json.load(open(questions_path))["questions"]}
    rows = []
    for r in results:
        q = qm.get(r["question_id"], {})
        h = q.get("horizon"); br = q.get("class_base_rate", 0.045)
        if h in FC_HORIZONS and FC_BAND[0] <= br < FC_BAND[1]:
            r["_br"] = br; rows.append(r)
    out = {}
    for m in demo_set_with_eci(include_gap_fillers=True):
        mid = m["model_id"]; s = []; c = []
        for r in rows:
            p = r.get("predictions", {}).get(mid, {}).get("probability")
            if p is None: continue
            y = 1.0 if r["ground_truth"] else 0.0
            s.append((p, y)); c.append((r["_br"], y))
        if len(s) < 15: continue
        n = len(s)
        b = sum((p - y) ** 2 for p, y in s) / n
        bc = sum((cb - y) ** 2 for cb, y in c) / n
        out[m["label"]] = 1 - b / bc if bc > 0 else None
    return out


def pandemic_bss(metrics_path):
    doc = json.load(open(metrics_path))["metrics"]
    return {lbl: m["bss"] for lbl, m in doc.items()
            if m.get("n") and m["n"] >= PAN_MIN_N and m.get("bss") is not None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", type=Path, default=REPO / "results" / "eval_full.json")
    ap.add_argument("--questions", type=Path, default=FBSIM / "data" / "lowprob" / "lowprob_questions.json")
    ap.add_argument("--pandemic", type=Path, default=REPO / "results" / "pandemic" / "smoke_metrics.json")
    ap.add_argument("--template", type=Path, default=REPO / "jason-demo.html")
    ap.add_argument("--out-html", type=Path, default=REPO / "jason-demo.live.html")
    ap.add_argument("--out-json", type=Path, default=REPO / "results" / "graph4_avg.json")
    ap.add_argument("--final", action="store_true")
    args = ap.parse_args()

    fc = freeciv_subset_bss(args.eval, args.questions)
    pan = pandemic_bss(args.pandemic)
    order = sorted(demo_set_with_eci(include_gap_fillers=True), key=lambda m: m["eci"])

    scatter = []
    for i, m in enumerate(order):
        lbl = m["label"]
        vals, sims = [], []
        if lbl in fc and fc[lbl] is not None:
            vals.append(fc[lbl]); sims.append("freeciv")
        if lbl in pan:
            vals.append(pan[lbl]); sims.append("starsim")
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        color = RAMP[min(len(RAMP) - 1, round(i * (len(RAMP) - 1) / max(1, len(order) - 1)))]
        scatter.append({"eci": m["eci"], "label": lbl, "bss": round(avg, 3), "color": color,
                        "freeciv": round(fc[lbl], 3) if lbl in fc and fc[lbl] is not None else None,
                        "starsim": round(pan[lbl], 3) if lbl in pan else None,
                        "nSims": len(vals), "sims": sims})

    rho = spearman([p["eci"] for p in scatter], [p["bss"] for p in scatter])
    blob = {"mode": "avg_scatter", "preliminary": not args.final,
            "nModels": len(scatter), "rho": round(rho, 2),
            "subsetLabel": "CivBench H2\u2013H4 / 5\u20139% band  +  Starsim pandemic (deaths thresholds)",
            "scatter": scatter}
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

    print(f"{'[FINAL] ' if args.final else '[preliminary] '}wrote {args.out_json.name} + {args.out_html.name}")
    print(f"rho(ECI, avg BSS) = {rho:+.2f}  over {len(scatter)} models")
    print(f"\n{'model':14s} {'ECI':>4} {'freeciv':>9} {'starsim':>9} {'avg':>8} sims")
    for p in scatter:
        cb = f"{p['freeciv']:+.2f}" if p['freeciv'] is not None else "   -"
        ss = f"{p['starsim']:+.2f}" if p['starsim'] is not None else "   -"
        print(f"{p['label']:14s} {p['eci']:>4} {cb:>9} {ss:>9} {p['bss']:>+8.2f}  {'+'.join(p['sims'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
