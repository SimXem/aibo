#!/usr/bin/env python3
"""Build Graph 4 data from the PANDEMIC smoke preds — same blob shape as FreeCiv.

    uv run python code/make_demo_pandemic.py            # -> jason-demo.live.html (sparse)
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAMP = ["#9aa7b3", "#7d93c8", "#5f86d6", "#4f9bc0", "#4bb39b", "#8bb84e",
        "#c9b03a", "#e08b3e", "#dd6140", "#cf3f4e", "#b52a55"]


def deciles(samples):
    s = sorted(samples, key=lambda t: t[0])
    N = len(s)
    if N == 0:
        return {"pts": [], "brier": 0.0, "base": 0.0}
    k = max(1, N // 10)
    pts = []
    for i in range(0, N, k):
        sl = s[i:i + k]
        if not sl:
            continue
        mp = sum(p for p, _ in sl) / len(sl)
        mo = sum(y for _, y in sl) / len(sl)
        pts.append({"pred": mp, "obs": mo, "n": len(sl)})
    brier = sum((p - y) ** 2 for p, y in s) / N
    base = sum(y for _, y in s) / N
    return {"pts": pts, "brier": brier, "base": base}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", type=Path, default=REPO / "results" / "pandemic" / "smoke_preds.json")
    ap.add_argument("--template", type=Path, default=REPO / "jason-demo.html")
    ap.add_argument("--out-html", type=Path, default=REPO / "jason-demo.live.html")
    ap.add_argument("--out-json", type=Path, default=REPO / "results" / "pandemic" / "graph4_pandemic.json")
    ap.add_argument("--final", action="store_true", help="drop the preliminary tag")
    ap.add_argument("--min-n", type=int, default=400, help="exclude models with < min-n predictions (thin coverage)")
    args = ap.parse_args()

    doc = json.load(open(args.preds))
    order = sorted(doc.items(), key=lambda kv: kv[1]["eci"])

    models_out, scatter, all_samples = [], [], []
    total_q = 0
    for i, (mid, m) in enumerate(order):
        samples = [(p, y) for p, y, _ in m["samples"]]
        clim = [(c, y) for p, y, c in m["samples"]]
        if len(samples) < args.min_n:
            print(f"  skip {m['label']}: only {len(samples)} preds (< {args.min_n})")
            continue
        d = deciles(samples)
        n = len(samples)
        total_q = max(total_q, n)
        brier_clim = sum((c - y) ** 2 for c, y in clim) / n
        bss = 1 - d["brier"] / brier_clim if brier_clim > 0 else None
        color = RAMP[min(len(RAMP) - 1, round(i * (len(RAMP) - 1) / max(1, len(order) - 1)))]
        entry = {"key": mid, "label": m["label"], "eci": m["eci"], "color": color,
                 "n": n, "brier": round(d["brier"], 4),
                 "bss": round(bss, 3) if bss is not None else None,
                 "meanPred": round(sum(p for p, _ in samples) / n, 4),
                 "meanObs": round(sum(y for _, y in samples) / n, 4),
                 "pts": [{"pred": round(p["pred"], 5), "obs": round(p["obs"], 5), "n": p["n"]}
                         for p in d["pts"]]}
        models_out.append(entry)
        scatter.append({"eci": m["eci"], "bss": entry["bss"], "label": m["label"],
                        "color": color, "meanPred": entry["meanPred"], "meanObs": entry["meanObs"]})
        all_samples.extend(samples)

    all_clim = [c for _, m in order for _, _, c in m["samples"]]
    band_lo, band_hi = min(all_clim), max(all_clim)
    band_label = f"{band_lo*100:.0f}–{band_hi*100:.0f}%"
    base = sum(y for _, y in all_samples) / len(all_samples)
    max_pred = max(m["pts"][-1]["pred"] for m in models_out)
    domain_max = min(0.9, (int(max_pred / 0.05) + 1) * 0.05)

    blob = {"preliminary": not args.final, "world": "pandemic", "bandLabel": band_label,
            "corpusLabel": "resolved Starsim pandemic tail events (cumulative-deaths thresholds, 1\u20135% base rates)",
            "base": round(base, 4), "domainMax": round(domain_max, 3),
            "nModels": len(models_out), "nQuestions": total_q,
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

    print(f"[PANDEMIC/sparse] wrote {args.out_json.name} + {args.out_html.name}")
    print(f"models: {len(models_out)}  questions: {total_q}  base: {base*100:.2f}%  domainMax: {domain_max}")
    for m in models_out:
        print(f"  {m['label']:12s} ECI {m['eci']}  BSS {m['bss']:>6.2f}  meanP {m['meanPred']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
