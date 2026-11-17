#!/usr/bin/env python3
"""Graph 3 hydration: REAL calibration & resolution from ForecastBench.

Three series, each a decile curve of mean forecast against observed frequency:

  Our models, bare   — the models THIS dashboard runs, zero-shot, no retrieval
  Same models + tools— their makers' own tournament entries: full systems with
                       retrieval and scaffolding, which is what our pipeline is
  Superforecasters   — ForecastBench.human_super, the 2024-07-21 round

WHAT THIS PANEL IS FOR
Validating the project's forecasts. An earlier version drew only 2024-era
models (Claude-2.1, GPT-4o), which validated a model set nobody here uses.
ForecastBench ran four of our five (never Fable 5), so we show the real ones.

THE FINDING: THE SPLIT, AND THE SCAFFOLD
ForecastBench holds two kinds of question and they behave nothing alike:

  dataset questions  auto-generated from public series (ACLED, FRED, yfinance,
                     Wikipedia, dbnomics). Largely persistence and trend.
  market questions   Polymarket, Manifold, Metaculus, Infer. Judgmental,
                     news-driven — far closer to what this dashboard asks.

Bare, our models are fine on dataset questions and badly broken on market
questions: on calls under 10% they say 4.3% for events that happen 21.9% of the
time. Every one of the four models shows it; pooled over all rounds it is 3.1%
against 22.9% on 2,019 rows.

That is a SCAFFOLDING failure, not a model failure. The same base models inside
their makers' tournament systems score 0.104 on market questions against 0.228
bare, and their tail is calibrated (3.4% said, 2.8% happened). The cleanest
control is xAI's own Grok 4.20 entry against bare Grok 4.20 on the SAME round
and the SAME questions: market Brier 0.235 -> 0.092, tail 5.4%/18.2% -> 3.9%/2.9%.

This is why the pipeline has Tavily news and Metaculus grounding. The bare line
is what our models would do with their hands tied, and it belongs on the chart
precisely because it shows what the scaffolding is buying.

NO HORIZON FILTER, DELIBERATELY
An earlier version cut every series to 7- and 30-day horizons to match the young
2026 rounds. Only dataset questions resolve on those exact days — market
questions resolve whenever the market closes — so the filter silently deleted
136 of 141 market questions and hid all of the above. Series now use every
horizon they have; the mix is reported instead of enforced.

Source: ~/Projects/forecastbench-datasets (Karger et al., ICLR 2025; CC BY-SA 4.0).
The processed sets are NOT in that git repo — refresh them from
https://www.forecastbench.org/assets/data/processed-forecast-sets/processed_forecast_sets.tar.gz

    python3 code/make_demo_graph3.py
"""
import datetime as dt
import glob
import json
import statistics
from pathlib import Path

from hydrate import inject

FB = Path.home() / "Projects" / "forecastbench-datasets"
PROC = FB / "processed_forecast_sets"
ROUND = "2024-07-21"          # the only round with a human arm
PROCESSED = PROC / ROUND
N_BINS = 10

# The dashboard's own model set. ForecastBench has never run Fable 5.
DASH_MODELS = ["Claude-Opus-4-8", "GPT-5.5-2026-04-23",
               "Gemini-3.1-Pro-Preview", "Grok-4.20-0309-Reasoning"]
DASH_ABSENT = ["Fable 5"]
# A round counts toward the bare series once this many of them are present.
# The result barely moves with the threshold — market Brier is 0.228 / 0.215 /
# 0.206 at >=2 / >=3 / >=4 — so we take the larger sample.
DASH_MIN_MODELS = 2

# Judgmental, news-driven sources. Everything else is auto-generated from a
# public time series.
MARKET_SOURCES = {"polymarket", "manifold", "metaculus", "infer"}


def is_tool_entry(j):
    """Tournament submissions built on model families this dashboard runs.

    Restricted to entries whose maker and model are named outright. Most of the
    tournament ships under codenames ("blue croc", "iron-compass") which cannot
    be attributed to a base model, so they are left out rather than guessed at.
    """
    org, model = j.get("organization"), j.get("model") or ""
    return ((org == "xAI" and model.startswith("Grok 4.20"))
            or (org == "Google DeepMind" and model == "Gemini"))


def load(path):
    d = json.load(open(path))
    return d["model"], d["forecasts"]


def usable(rows):
    """Resolved binary rows keyed by (question id, resolution horizon).

    Skips combination questions (list ids) and imputed forecasts — imputed rows
    are ForecastBench's 0.5 fill-in for unanswered questions, which would
    fabricate calibration the forecaster never exhibited.
    """
    return {(x["id"], x["resolution_date"]): x for x in rows
            if isinstance(x["id"], str) and not x.get("imputed")
            and x["resolved"] and x["resolved_to"] in (0.0, 1.0)}


def wilson(k, n, z=1.96):
    """95% interval for an observed frequency.

    The series carry very different per-decile n. Without an interval a reader
    mistakes small-sample zigzag for miscalibration, which is exactly the error
    this panel invites.
    """
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def tail(pairs, cut=0.10):
    """What the forecaster called unlikely, and how often it happened."""
    lo = [(f, o) for f, o in pairs if f < cut]
    if not lo:
        return {"n": 0, "pred": None, "obs": None}
    return {"n": len(lo),
            "pred": round(sum(f for f, _ in lo) / len(lo), 4),
            "obs": round(sum(o for _, o in lo) / len(lo), 4)}


def series_stats(pairs):
    """Decile dots + Brier + Murphy resolution, matching the mock's deciles()."""
    n = len(pairs)
    obar = sum(o for _, o in pairs) / n
    brier = sum((f - o) ** 2 for f, o in pairs) / n
    ordered = sorted(pairs)
    bins = [b for b in (ordered[round(i * n / N_BINS):round((i + 1) * n / N_BINS)]
                        for i in range(N_BINS)) if b]
    pts = []
    for b in bins:
        hits = sum(o for _, o in b)
        lo95, hi95 = wilson(hits, len(b))
        pts.append({"pred": round(sum(f for f, _ in b) / len(b), 4),
                    "obs": round(hits / len(b), 4), "n": len(b),
                    "lo95": lo95, "hi95": hi95})
    resolution = sum(len(b) * ((sum(o for _, o in b) / len(b)) - obar) ** 2
                     for b in bins) / n
    return {"pts": pts, "n": n, "brier": round(brier, 4),
            "resolution": round(resolution, 4), "base": round(obar, 4),
            "lo": tail(pairs)}


def split_by_kind(trip):
    """Brier and tail for dataset vs market questions. The headline finding."""
    out = {}
    for kind in ("dataset", "market"):
        sel = [(f, o) for f, o, row in trip
               if (row["source"] in MARKET_SOURCES) == (kind == "market")]
        out[kind] = ({"n": len(sel),
                      "brier": round(sum((f - o) ** 2 for f, o in sel) / len(sel), 4),
                      "lo": tail(sel)} if len(sel) >= 20 else {"n": len(sel)})
    return out


def vs_market(trip):
    """On judgmental questions, does the forecaster add anything to the price?

    Everyone who can see a prediction market anchors on it — superforecasters
    correlate 0.96 with the freeze price, the tournament systems 0.95. Raw Brier
    on market questions therefore measures mostly "did you find the market",
    which is a lookup, not a forecast. The only question that means anything is
    whether you BEAT it.

    ForecastBench records the price at freeze time and withholds it from the
    base configs (that is what the `_with_freeze_values` variants are for), so
    forecaster and price can be scored on identical rows.
    """
    rows = [(f, o, r) for f, o, r in trip
            if r["source"] in MARKET_SOURCES
            and isinstance(r.get("market_value_on_due_date"), (int, float))]
    n = len(rows)
    if n < 30:
        return None
    mine = sum((f - o) ** 2 for f, o, _ in rows) / n
    mkt = sum((r["market_value_on_due_date"] - o) ** 2 for _, o, r in rows) / n
    fs = [f for f, _, _ in rows]
    ms = [r["market_value_on_due_date"] for _, _, r in rows]
    mf, mm = sum(fs) / n, sum(ms) / n
    sf = (sum((x - mf) ** 2 for x in fs) / n) ** 0.5
    sm = (sum((x - mm) ** 2 for x in ms) / n) ** 0.5
    corr = (sum((a - mf) * (b - mm) for a, b in zip(fs, ms)) / n) / (sf * sm) if sf and sm else None
    gaps = sorted(abs(f - r["market_value_on_due_date"]) for f, _, r in rows)
    return {"n": n, "brier": round(mine, 4), "market": round(mkt, 4),
            "edge": round(mkt - mine, 4),          # positive = beats the market
            "corr": round(corr, 3) if corr is not None else None,
            "medianGap": round(gaps[n // 2], 3)}


def stats(trip):
    return dict(series_stats([(f, o) for f, o, _ in trip]),
                split=split_by_kind(trip), vsMarket=vs_market(trip))


def crowd(per_model, keys, min_models):
    """Per-question median across models, with the source row kept alongside."""
    out = []
    for k in keys:
        have = [m for m in per_model.values() if k in m]
        if len(have) >= min_models:
            out.append((statistics.median(m[k]["forecast"] for m in have),
                        have[0][k]["resolved_to"], have[0][k]))
    return out


def all_rounds():
    return sorted(x.name for x in PROC.iterdir() if x.is_dir())


def bare_series():
    """Our models, zero-shot, pooled over every round carrying enough of them."""
    trip, models, rounds = [], set(), []
    for d in all_rounds():
        pm = {}
        for p in glob.glob(str(PROC / d / "*_zero_shot.json")):
            name, rows = load(p)
            base = name.replace(" (zero shot)", "")
            if base in DASH_MODELS:
                pm[base] = usable(rows)
        if len(pm) < DASH_MIN_MODELS:
            continue
        models |= set(pm)
        rounds.append(d)
        trip += crowd(pm, set().union(*[set(m) for m in pm.values()]), len(pm))
    return trip, sorted(models), rounds


def tools_series():
    """The same model families inside their makers' own tournament systems."""
    trip, entries, rounds = [], set(), []
    for d in all_rounds():
        for p in glob.glob(str(PROC / d / "*external*.json")):
            j = json.load(open(p))
            if not is_tool_entry(j):
                continue
            u = usable(j["forecasts"])
            if u:
                entries.add(j["model"])
                rounds.append(d)
                trip += [(v["forecast"], v["resolved_to"], v) for v in u.values()]
    return trip, sorted(entries), sorted(set(rounds))


def per_model_confirmation():
    """Each dashboard model alone, every round it appears in.

    The bare series is only as big as the rounds carrying several models. This
    pools each model's own forecasts across all rounds, which is where the
    market result gets its sample — and it holds for every model separately, so
    it is not an artefact of how the ensemble is built.
    """
    acc = {m: [] for m in DASH_MODELS}
    for d in all_rounds():
        for p in glob.glob(str(PROC / d / "*_zero_shot.json")):
            name, rows = load(p)
            base = name.replace(" (zero shot)", "")
            if base in DASH_MODELS:
                acc[base] += [(v["forecast"], v["resolved_to"], v)
                              for v in usable(rows).values()]
    out = {m: dict(split_by_kind(v), n=len(v)) for m, v in acc.items() if v}
    pooled = [p for v in acc.values() for p in v]
    out["pooled"] = dict(split_by_kind(pooled), n=len(pooled))
    return out


def grok_control():
    """xAI's Grok 4.20 entry against bare Grok 4.20, same round, same questions.

    The tightest evidence that retrieval rather than model choice closes the
    market-question gap: one base model, one question set, one round.
    """
    out = []
    for d in all_rounds():
        bare = [p for p in glob.glob(str(PROC / d / "*grok-4.20*reasoning_zero_shot.json"))
                if "non-reasoning" not in p]
        if not bare:
            continue
        z = usable(load(bare[0])[1])
        for p in glob.glob(str(PROC / d / "*external*.json")):
            j = json.load(open(p))
            if j.get("organization") != "xAI" or not (j.get("model") or "").startswith("Grok 4.20"):
                continue
            e = usable(j["forecasts"])
            ks = [k for k in set(z) & set(e) if e[k]["source"] in MARKET_SOURCES]
            if len(ks) < 50:
                continue
            a = series_stats([(z[k]["forecast"], z[k]["resolved_to"]) for k in ks])
            b = series_stats([(e[k]["forecast"], e[k]["resolved_to"]) for k in ks])
            out.append({"round": d, "entry": j["model"], "n": len(ks),
                        "bare": {"brier": a["brier"], "lo": a["lo"]},
                        "tools": {"brier": b["brier"], "lo": b["lo"]}})
    return out


def horizon_mix(rows):
    mix = {}
    for v in rows:
        d = (dt.datetime.fromisoformat(v["resolution_date"])
             - dt.datetime.fromisoformat(v["forecast_due_date"])).days
        mix[d] = mix.get(d, 0) + 1
    return {"ge90d": sum(n for h, n in mix.items() if h >= 90), "total": sum(mix.values())}


def build():
    sup_rows = usable(load(PROCESSED / f"{ROUND}.ForecastBench.human_super.json")[1])
    sup_trip = [(v["forecast"], v["resolved_to"], v) for v in sup_rows.values()]

    bare_trip, bare_models, bare_rounds = bare_series()
    tool_trip, tool_entries, tool_rounds = tools_series()

    return {
        "bare": dict(stats(bare_trip), models=bare_models, rounds=bare_rounds,
                     absent=DASH_ABSENT, minModels=DASH_MIN_MODELS),
        "tools": dict(stats(tool_trip), entries=tool_entries, rounds=tool_rounds),
        "sup": dict(stats(sup_trip), round=ROUND),
        "perModel": per_model_confirmation(),
        "grokControl": grok_control(),
        "horizons": {"bare": horizon_mix([r for _, _, r in bare_trip]),
                     "tools": horizon_mix([r for _, _, r in tool_trip]),
                     "sup": horizon_mix([r for _, _, r in sup_trip])},
        "provenance": {
            "dataset": "ForecastBench (Karger et al., ICLR 2025)",
            "license": "CC BY-SA 4.0",
            "superCaveat": "Superforecasters answered inside a long survey, under "
                           "time pressure — a point the FRI team raises about its "
                           "own data, so we raise it first. Their round is 2024, and "
                           "no later round has a human arm.",
            "crossRound": "The three series come from different rounds and question "
                          "sets. A fixed model swings 0.035 Brier between rounds, so "
                          "distances here are not all skill. "
                          "See code/graph3_comparability.py.",
            "toolsNote": "Tournament entries are full systems — retrieval, scaffolding, "
                         "possibly ensembling — submitted by the model makers. They are "
                         "the closest public analogue to this dashboard's own pipeline, "
                         "which grounds every forecast with Tavily news and Metaculus.",
        },
    }


if __name__ == "__main__":
    blob = build()
    path = inject("GRAPH3", blob, json_out="results/graph3_data.json")
    for k, lbl in (("bare", "bare"), ("tools", "with tools"), ("sup", "superf.")):
        s = blob[k]
        d, m, v = s["split"]["dataset"], s["split"]["market"], s["vsMarket"]
        line = f"  {lbl:11} n={s['n']:6} brier={s['brier']}   dataset={d.get('brier')}"
        if "brier" in m:
            line += f"  market={m['brier']}"
        if v:
            line += (f"   vs price: {v['brier']} vs {v['market']} "
                     f"edge={v['edge']:+.4f} corr={v['corr']} gap={v['medianGap']}")
        print(line)
    p = blob["perModel"]["pooled"]["market"]
    print(f"  per-model pooled market: n={p['n']} brier={p['brier']} "
          f"tail {p['lo']['pred']}->{p['lo']['obs']}")
    for g in blob["grokControl"]:
        print(f"  control {g['round']} {g['entry']:22} n={g['n']:4} "
              f"bare {g['bare']['brier']} -> tools {g['tools']['brier']}")
    print(f"GRAPH3 -> {path.name}")
