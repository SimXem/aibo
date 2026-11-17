"""Graph 5 (observational conditionals): blob builder.

The observational conditional bench -- code/observational/spec.md, vendored
2026-08-28 from elsehow/llm-conditional-forecasting -- asks a model, for a
pair of ForecastBench station-temperature questions A and B, for P(A), P(B),
P(B|A) and P(B|not A) in one prompt, and scores the association those four
numbers imply against the association measured in two years of resolution
data (deseasonalized phi over 33 resolution sets, block-bootstrap certified;
data/observational/pairs_selected.json). Twenty-one scored pairs: one
near-duplicate, twelve positives in four strength bands, eight independent
controls. Six opposite-hemisphere probe pairs are never scored.

The chart is the spec's "dashboard graph": one number per model, the rank
correlation between implied and measured association across the 21 scored
pairs, against ECI, under the noise ceiling (data/observational/
noise_ceiling.json: what an oracle that knew the true associations would
score against our finite-panel measurements). The four metrics M1-M4 and the
pass bar are computed here exactly as code/observational/score_bench.py
computes them (tests/test_conditional_benches.py pins this module to the
numbers the spec's pass bar was first met on, results_2026-08-20.jsonl); the
per-pair detail behind each dot is carried for the tooltips.

Which run: RUNS below, newest first that exists -- the roster run
(archive/litellm-runners/run_roster.py: the 24-model ECI roster through
OpenRouter) when it has been made, else the 2026-08-20 four-Claude run. A
model's ECI is the roster's (redlines.roster), never the registry's pinned
vintage -- see that module for why.

Pure: build() reads its inputs and returns the blob dict; no writes.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict

from ..config import REPO_ROOT
from ..roster import ANTHROPIC_IDS, by_id as roster_by_id
from ..stats import spearman_p, spearman_ties

PAIRS = REPO_ROOT / "data" / "observational" / "pairs_selected.json"
NOISE = REPO_ROOT / "data" / "observational" / "noise_ceiling.json"
_R = REPO_ROOT / "results" / "observational"
# Newest first. A run is a set of files written by the same instrument on the
# same day: the roster run plus its supplements (run_roster.py --tag, one file
# per process -- the Graph 4 models were added in a second process while the
# first was still writing).
RUNS = ((_R / "results_roster.jsonl", _R / "results_roster_g4.jsonl"),
        (_R / "results_2026-08-20.jsonl",))

# The spec's pre-registered independence bar: median |P(B|A) - P(B|not A)|
# on the control pairs must be under this.
BAR = 0.075
# Pairs whose measured |phi| is at most this are inside our own measurement
# resolution for the controls (spec: "control point estimates <= 0.10").
CONTROL_ZONE = 0.10


def implied_phi(v):
    """The phi coefficient the four elicited probabilities imply
    (score_bench.py::implied_phi): cov(A,B)/sqrt(var A var B) with
    P(A and B) = P(B|A) P(A). None when either marginal is degenerate."""
    pa, pb = v["p_a"], v["p_b"]
    denom = math.sqrt(pa * (1 - pa) * pb * (1 - pb))
    if denom < 1e-9:
        return None
    return max(-1.0, min(1.0, (v["p_b_given_a"] * pa - pa * pb) / denom))


def _median(xs):
    return statistics.median(xs)


def _binom_p_ge(k, n):
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def load_pairs(path=PAIRS):
    return {p["pair_id"]: p for p in json.load(open(path))}


def load_rows(paths):
    """Rows of one run: `paths` is a file or a tuple of files (missing ones
    are skipped -- a supplement that has not been run yet)."""
    if not isinstance(paths, (tuple, list)):
        paths = (paths,)
    rows = []
    for path in paths:
        if not path.exists():
            continue
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


# The instrument's K (spec.md): a model is scored once it has this many
# replies to EVERY pair, so a run in progress (run_roster.py appends as it
# goes, rep-outermost) never shows a model on one rep's worth of answers.
REPS = 5


def complete_models(rows, pairs, reps=REPS):
    """Roster ids with >= `reps` replies to every pair. A run in progress has
    none; a finished run has the whole roster minus any model that gave up
    on a pair."""
    seen = defaultdict(lambda: defaultdict(int))
    for r in rows:
        seen[ANTHROPIC_IDS.get(r["model"], r["model"])][r["pair_id"]] += 1
    return {m for m, ps in seen.items() if all(ps.get(pid, 0) >= reps for pid in pairs)}


def pick_run(runs=RUNS, pairs=None):
    """The newest run with at least one complete model. The roster run is
    written incrementally over an hour or two; until a model has answered
    every pair the file is not a run yet and the previous one is drawn."""
    pairs = pairs or load_pairs()
    for p in runs:
        if complete_models(load_rows(p), pairs):
            return p
    raise FileNotFoundError("no complete observational run under results/observational/")


def classes(pairs):
    pos = {pid for pid, p in pairs.items()
           if p["category"].startswith("associated_pos") or p["category"].startswith("sanity")}
    ctrl = {pid for pid, p in pairs.items() if p["category"] == "control_independent"}
    probe = {pid for pid, p in pairs.items() if p["category"] == "hemispheric_probe"}
    return pos, ctrl, probe


def score_model(rows_by_pair, pairs):
    """One model's metrics from its rows grouped by pair_id --
    score_bench.py's per-model loop, plus the per-pair detail the chart's
    tooltips and any small-multiple view need."""
    pos, ctrl, probe = classes(pairs)
    scored = pos | ctrl
    eps, phi_i, phi_h = [], [], []
    kp = n_pos = 0
    d_ctrl, d_pos = [], []
    sanity = None
    pos_pts, ctrl_pts, probe_pts = [], [], []
    n_resp = 0
    for pid, pair in pairs.items():
        rs = rows_by_pair.get(pid, [])
        if not rs:
            continue
        n_resp += len(rs)
        eps.append(_median([abs(r["p_b"] - (r["p_b_given_a"] * r["p_a"]
                                            + r["p_b_given_not_a"] * (1 - r["p_a"]))) for r in rs]))
        delta = _median([r["p_b_given_a"] - r["p_b_given_not_a"] for r in rs])
        phis = [p for p in (implied_phi(r) for r in rs) if p is not None]
        implied = _median(phis) if phis else None
        if pid in pos:
            n_pos += 1
            kp += int(delta > 0)
            d_pos.append(abs(delta))
        if pid in ctrl:
            d_ctrl.append(abs(delta))
            ctrl_pts.append({"pair": pid, "a": pair["st_a"], "b": pair["st_b"],
                             "shift": round(abs(delta), 4), "measured": pair["phi"]})
        if pid in probe:
            probe_pts.append({"pair": pid, "a": pair["st_a"], "b": pair["st_b"], "delta": round(delta, 4)})
        if pair["category"].startswith("sanity"):
            sanity = {"pair": pid, "a": pair["st_a"], "b": pair["st_b"],
                      "pba": round(_median([r["p_b_given_a"] for r in rs]), 4),
                      "pbna": round(_median([r["p_b_given_not_a"] for r in rs]), 4)}
        if pair["category"].startswith("associated_pos") and implied is not None:
            pos_pts.append({"pair": pid, "a": pair["st_a"], "b": pair["st_b"],
                            "measured": pair["phi"], "implied": round(implied, 4),
                            "hw": round((pair["ci_hi"] - pair["ci_lo"]) / 2, 4)})
        if pid in scored and implied is not None:
            phi_i.append(implied)
            phi_h.append(pair["phi"])
    if not phi_i:
        return None
    rho = spearman_ties(phi_h, phi_i) if len(phi_i) > 2 else None
    m3 = _median(d_ctrl) if d_ctrl else None
    rho_pos = (spearman_ties([p["measured"] for p in pos_pts], [p["implied"] for p in pos_pts])
               if len(pos_pts) > 2 else None)
    return {
        "responses": n_resp,
        "pairsScored": len(phi_i),
        # M1/M3 are stored UNROUNDED: score_bench.py prints them %.3f, and a
        # pre-rounded 0.0135 prints as 0.013 where the raw median prints 0.014.
        "coherence": _median(eps),                                 # M1
        "direction": {"k": kp, "n": n_pos,                         # M2
                      "p": round(_binom_p_ge(kp, n_pos), 4) if n_pos else None},
        "controlShift": m3,                                        # M3
        "pass": (m3 is not None and m3 < BAR),
        "rho": round(rho, 4) if rho is not None else None,         # M4
        "rhoPos": round(rho_pos, 4) if rho_pos is not None else None,
        "posInBand": sum(1 for p in pos_pts if abs(p["implied"] - p["measured"]) <= p["hw"]),
        "sanity": sanity,
        "pos": pos_pts,
        "ctrl": ctrl_pts,
        "probe": probe_pts,
    }


def build(run_path=None, pairs_path=PAIRS, noise_path=NOISE):
    pairs = load_pairs(pairs_path)
    run_path = run_path or pick_run(pairs=pairs)
    run_files = run_path if isinstance(run_path, (tuple, list)) else (run_path,)
    noise = json.load(open(noise_path))
    roster = roster_by_id()
    rows = load_rows(run_path)
    complete = complete_models(rows, pairs)

    by_model = defaultdict(lambda: defaultdict(list))
    for r in rows:
        mid = ANTHROPIC_IDS.get(r["model"], r["model"])
        by_model[mid][r["pair_id"]].append(r)

    models, excluded = [], []
    for mid, by_pair in by_model.items():
        m = roster.get(mid)
        if m is None:
            raise KeyError(f"model {mid!r} in {run_files[0].name} is not on the roster (redlines.roster)")
        if mid not in complete:
            full = sum(1 for pid in pairs if len(by_pair.get(pid, ())) >= REPS)
            excluded.append({"id": mid, "label": m["label"], "pairs": full,
                             "why": f"{full} of {len(pairs)} pairs with all {REPS} replies"})
            continue
        s = score_model(by_pair, pairs)
        models.append({"id": mid, "label": m["label"], "eci": m["eci"], "eciSource": m["eciSource"],
                       "inPanel": m["inPanel"], "color": m["color"], **s})
    models.sort(key=lambda m: m["eci"])
    excluded.sort(key=lambda e: roster[e["id"]]["eci"])

    xs = [m["eci"] for m in models if m["rho"] is not None]
    ys = [m["rho"] for m in models if m["rho"] is not None]
    rho = spearman_ties(xs, ys) if len(xs) > 2 else None
    pos, ctrl, probe = classes(pairs)
    rows = [r for r in rows if ANTHROPIC_IDS.get(r["model"], r["model"]) in complete]
    due = sorted({r["due_date"] for r in rows})
    res = sorted({r["res_date"] for r in rows})
    best = max(models, key=lambda m: m["rho"] if m["rho"] is not None else -2)
    return {
        "source": {
            "bench": "observational conditional bench (code/observational/spec.md, v3)",
            "upstream": "the bench's mining and scoring code, vendored under code/observational/ on 2026-08-28 (the original checkout is not published)",
            "run": [str(p.relative_to(REPO_ROOT)) for p in run_files if p.exists()],
            "pairs": str(pairs_path.relative_to(REPO_ROOT)),
            "eci": "data/causal/models.csv (Epoch Capabilities Index as published 2026-08-27) for the causal roster; "
                   "the pinned 2026-07-07 snapshot for Graph 4's other models (data/observational/roster_extra.csv); "
                   "see redlines/roster.py",
        },
        "run": {"due": due[0] if len(due) == 1 else due, "resolves": res[0] if len(res) == 1 else res,
                "responses": len(rows), "models": len(models),
                "reps": max(r["rep"] for r in rows) + 1 if rows else 0},
        "pairs": {"scored": len(pos | ctrl), "positive": len(pos), "control": len(ctrl), "probe": len(probe),
                  "total": len(pairs)},
        "noise": {"ceiling": noise["ceiling"], "lo": noise["ceiling_lo"], "hi": noise["ceiling_hi"],
                  "splitHalf": noise["split_half"], "band": noise["band"]},
        "bar": BAR,
        "controlZone": CONTROL_ZONE,
        "rho": round(rho, 4) if rho is not None else None,
        "rhoP": round(spearman_p(rho, len(xs)), 4) if rho is not None else None,
        "nPass": sum(1 for m in models if m["pass"]),
        "best": {"label": best["label"], "rho": best["rho"]},
        "excluded": excluded,
        "models": models,
    }
