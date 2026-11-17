"""Graph 3 blob builder: REAL calibration & resolution from ForecastBench.

Three series, each a decile curve of mean forecast against observed frequency:

  Our models, bare   — the models THIS dashboard runs, zero-shot, no retrieval
  Same models + tools— their makers' own tournament entries: full systems with
                       retrieval and scaffolding, which is what our pipeline is
  Superforecasters   — ForecastBench.human_super, the 2024-07-21 round

Ported from code/make_demo_graph3.py::build (and its helpers) with paths and
the dashboard's model set repointed to redlines.config / redlines.registry;
the shared estimators (Wilson interval, tail-bin summary, Brier) come from
redlines.stats. Arithmetic and rounding are unchanged from the original —
this module is a pure blob builder: build() computes and returns the blob
dict, no argparse, no file writes, no hydration.

NO HORIZON FILTER, DELIBERATELY (see docs/methodology.md)
An earlier version cut every series to 7- and 30-day horizons to match the
young 2026 rounds. Only dataset questions resolve on those exact days — market
questions resolve whenever the market closes — so the filter silently deleted
136 of 141 market questions and hid the calibration split below. Series here
use every horizon they have; horizon_mix() reports the mix instead of
enforcing one. A horizon filter on ForecastBench is a question-type filter in
disguise — that regression is recorded in docs/methodology.md and must not
come back.

THE FINDING: THE SPLIT, AND THE SCAFFOLD
ForecastBench holds two kinds of question and they behave nothing alike:
dataset questions (auto-generated from public series — largely persistence
and trend) and market questions (Polymarket, Manifold, Metaculus, Infer —
judgmental, news-driven, far closer to what this dashboard asks). Bare, our
models are calibrated on dataset questions and badly broken on market
questions; the same base models inside their makers' tournament systems are
calibrated on both. That is a SCAFFOLDING failure, not a model failure, and
it is why the pipeline grounds every forecast with Tavily news and Metaculus.

Source: ~/Projects/forecastbench-datasets (Karger et al., ICLR 2025; CC BY-SA
4.0). The processed sets are NOT in that git repo — refresh them from
https://www.forecastbench.org/assets/data/processed-forecast-sets/processed_forecast_sets.tar.gz
"""
import datetime as dt
import glob
import json
import statistics

from ..config import FB_DATASETS_ROOT, GRAPH3_ROUND
from ..registry import by_role
from ..runlog import GROUNDING_AGENTIC
from ..stats import brier_mean, tail_stats, wilson_interval

FB = FB_DATASETS_ROOT
PROC = FB / "processed_forecast_sets"
ROUND = GRAPH3_ROUND          # the only round with a human arm
PROCESSED = PROC / ROUND
N_BINS = 10

# The dashboard's own model set, as ForecastBench display names. Sourced from
# redlines.registry's "graph3_dash" role (fb_name field) rather than a local
# literal — MODELS' declaration order matches the original hand-typed
# DASH_MODELS list exactly (Opus 4.8, GPT-5.5, Gemini 3.1 Pro, Grok 4.20).
DASH_MODELS = [m["fb_name"] for m in by_role("graph3_dash")]
# ForecastBench has never run this dashboard model; not in the registry's
# graph3_dash role, so it can't be derived the way DASH_MODELS is.
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


def series_stats(pairs):
    """Decile dots + Brier + Murphy resolution, matching the mock's deciles().

    The decile CI (wilson_interval) and tail summary (tail_stats) delegate to
    redlines.stats; the equal-count bin split stays local because the
    resolution term needs each bin's UNROUNDED mean (redlines.stats'
    deciles_equal_count only returns 4-decimal-rounded points, and squaring a
    pre-rounded mean would not reproduce the original's arithmetic exactly —
    see stats.deciles_equal_count's own docstring, which flags this exact
    resolution term as out of its scope).
    """
    n = len(pairs)
    obar = sum(o for _, o in pairs) / n
    brier = brier_mean(pairs)
    ordered = sorted(pairs)
    bins = [b for b in (ordered[round(i * n / N_BINS):round((i + 1) * n / N_BINS)]
                        for i in range(N_BINS)) if b]
    pts = []
    for b in bins:
        hits = sum(o for _, o in b)
        lo95, hi95 = wilson_interval(hits, len(b))
        pts.append({"pred": round(sum(f for f, _ in b) / len(b), 4),
                    "obs": round(hits / len(b), 4), "n": len(b),
                    "lo95": lo95, "hi95": hi95})
    resolution = sum(len(b) * ((sum(o for _, o in b) / len(b)) - obar) ** 2
                     for b in bins) / n
    return {"pts": pts, "n": n, "brier": round(brier, 4),
            "resolution": round(resolution, 4), "base": round(obar, 4),
            "lo": tail_stats(pairs)}


def split_by_kind(trip):
    """Brier and tail for dataset vs market questions. The headline finding."""
    out = {}
    for kind in ("dataset", "market"):
        sel = [(f, o) for f, o, row in trip
               if (row["source"] in MARKET_SOURCES) == (kind == "market")]
        out[kind] = ({"n": len(sel), "brier": round(brier_mean(sel), 4),
                      "lo": tail_stats(sel)} if len(sel) >= 20 else {"n": len(sel)})
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
    mine = brier_mean([(f, o) for f, o, _ in rows])
    mkt = brier_mean([(r["market_value_on_due_date"], o) for _, o, r in rows])
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


# --- THE PANEL'S OWN RULE, REPLAYED ON FORECASTBENCH (2026-09-02) -------------
# The dashboard's panel is the k highest-ECI models the registry can run, pooled
# by the median (redlines.registry.panel). None of the current four has run on
# ForecastBench, so the panel itself cannot be scored there. What CAN be scored
# is the RULE: at every round, take the k highest-ECI models among the bare
# configs ForecastBench ran that round, median-pool them, and score the pool on
# that round's resolved questions. That is the calibration of "whatever this
# rule would have picked", which is the honest analogue of the panel's own.
#
# Bare = ForecastBench's own zero-shot / scratchpad runs (organization
# "ForecastBench"), never the freeze-value or with-news variants, never the
# dummies. One config per base model (the plainest name), so a model's zero-shot
# and scratchpad runs cannot both be "members". ECI is the PINNED snapshot
# (redlines.eci.PINNED, 2026-07-07, 188 models) applied to every round: one
# vintage, so a past round's pick is by today's scale, not the scale of the day.
# Ties break by name. A model-round is dropped when more than IMPUTED_CUTOFF_PCT
# of its forecasts are ForecastBench's 0.5 fill-in, overall or within the market
# or resolved-dataset subsets -- ForecastBench's own leaderboard rule, mirrored
# from ~/Projects/forecastbench-ensembling/etl.py.
PANEL_K = 4
PANEL_MIN_MEMBERS = 3        # a question counts when at least this many members answered it
IMPUTED_CUTOFF_PCT = 5
# Display-name tags (to 2026-06-21) and slug tags (from the 2026-07-05 rename).
BENCH_VARIANT_TAGS = ("with freeze values", "with news", "with SECOND news", "with web search",
                      "with-freeze-values", "-with-news", "web-search")
BENCH_DUMMIES = {"Always 0", "Always 1", "Always 0.5", "Random Uniform",
                 "Imputed Forecaster", "Naive Forecaster"}
# Name-matching junk between ForecastBench config names and Epoch display names,
# same list as forecastbench-ensembling/exp_eci.py so the two agree.
_ECI_JUNK = ["scratchpad", "adaptive-thinking", "web-search", "high", "preview", "instruct",
             "turbo", "reasoning", "non-", "beta", "fp8", "tput", "chat", "hf", "latest",
             "max", "128000", "24000", "16000", "12000", "1024"]


def _eci_key(name):
    """'Claude-Opus-4-7 (zero shot)' and 'Claude Opus 4.7' -> 'claudeopus47'."""
    import re
    s = name.split("(")[0].lower()
    s = re.sub(r"20\d{2}[-/]?\d{0,2}[-/]?\d{0,2}", "", s)
    s = re.sub(r"[-_]0[0-9]{3}\b", "", s)
    for j in _ECI_JUNK:
        s = s.replace(j, "")
    return re.sub(r"[^a-z0-9]", "", s)


def _eci_table():
    from .. import eci as eci_mod
    idx = eci_mod.load(eci_mod.snapshot_path(eci_mod.PINNED))
    out = {}
    for rec in idx.values():
        k = _eci_key(rec["model"])
        if k not in out or rec["eci"] > out[k]:
            out[k] = rec["eci"]
    return out, eci_mod.PINNED.isoformat()


def _is_bare_bench_entry(j):
    model = j.get("model") or ""
    return (j.get("organization") == "ForecastBench" and model not in BENCH_DUMMIES
            and "median forecast" not in model
            and not any(t in model for t in BENCH_VARIANT_TAGS))


def _passes_imputed_test(rows):
    """ForecastBench's leaderboard rule: drop the model-round if the 0.5 fill-in
    exceeds the cutoff overall, on market questions, or on resolved dataset ones."""
    rows = [x for x in rows if isinstance(x["id"], str)]
    if not rows:
        return False

    def share(sub):
        return 100.0 * sum(1 for x in sub if x.get("imputed")) / len(sub) if sub else 0.0

    market = [x for x in rows if x["source"] in MARKET_SOURCES]
    data_resolved = [x for x in rows if x["source"] not in MARKET_SOURCES and x.get("resolved")]
    return all(share(sub) <= IMPUTED_CUTOFF_PCT for sub in (rows, market, data_resolved))


def panel_rule_series(k=PANEL_K, min_members=PANEL_MIN_MEMBERS):
    """(trip, picks): the rule's median pool per round, and who it picked."""
    table, vintage = _eci_table()
    trip, picks, unmatched = [], [], set()
    for d in all_rounds():
        configs = {}
        for p in glob.glob(str(PROC / d / "*.json")):
            j = json.load(open(p))
            if not _is_bare_bench_entry(j) or not _passes_imputed_test(j["forecasts"]):
                continue
            u = usable(j["forecasts"])
            if u:
                configs[j["model"]] = u
        # one config per base model: the plainest (shortest) name
        by_base = {}
        for name in configs:
            b = _eci_key(name)
            if b not in by_base or (len(name), name) < (len(by_base[b]), by_base[b]):
                by_base[b] = name
        scored = []
        for b, name in by_base.items():
            if b in table:
                scored.append((-table[b], name))
            else:
                unmatched.add(name)
        members = [name for _, name in sorted(scored)[:k]]
        if len(members) < k:
            picks.append({"round": d, "members": [], "n": 0})
            continue
        pm = {m: configs[m] for m in members}
        rows = crowd(pm, set().union(*[set(x) for x in pm.values()]), min_members)
        picks.append({"round": d, "n": len(rows),
                      "members": [{"model": m, "eci": table[_eci_key(m)]} for m in members]})
        trip += rows
    return trip, {"k": k, "minMembers": min_members, "eciVintage": vintage,
                  "rounds": [p for p in picks if p["n"]],
                  "unmatched": sorted(unmatched)}


def build():
    sup_rows = usable(load(PROCESSED / f"{ROUND}.ForecastBench.human_super.json")[1])
    sup_trip = [(v["forecast"], v["resolved_to"], v) for v in sup_rows.values()]

    bare_trip, bare_models, bare_rounds = bare_series()
    tool_trip, tool_entries, tool_rounds = tools_series()
    panel_trip, panel_meta = panel_rule_series()

    return {
        "bare": dict(stats(bare_trip), models=bare_models, rounds=bare_rounds,
                     absent=DASH_ABSENT, minModels=DASH_MIN_MODELS),
        "tools": dict(stats(tool_trip), entries=tool_entries, rounds=tool_rounds),
        "panel": dict(stats(panel_trip), **panel_meta),
        "sup": dict(stats(sup_trip), round=ROUND),
        "perModel": per_model_confirmation(),
        "grokControl": grok_control(),
        "horizons": {"bare": horizon_mix([r for _, _, r in bare_trip]),
                     "tools": horizon_mix([r for _, _, r in tool_trip]),
                     "panel": horizon_mix([r for _, _, r in panel_trip]),
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
                         f"whose grounding is {GROUNDING_AGENTIC}.",
        },
    }
