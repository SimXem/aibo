"""Data Bank: our bottom-line forecasts, optionally with the x-risk CANARIES.

Byte-exact port of code/make_demo_databank.py::bottom_line_rows /
canary_rows / the __main__ blob assembly.

Two kinds of row:

  bottom-line  — the catastrophic questions this dashboard tracks (XPT + our
                 severity ladder). Long horizon, never resolve in time to score.
  canary       — near-term leading indicators generated off the XPT questions in
                 xrisk-canaries (redlines.config.XRISK_CANARIES_ROOT). They
                 RESOLVE (2026-2027), carry explicit resolution criteria and
                 sources, and each one is forecast together with its
                 conditional effect on the bottom-line questions — so "moves
                 the bottom line by X points" is a real, computed number, not
                 a label.

That pairing is the dashboard's argument in miniature: you cannot score a 2100
extinction forecast, but you CAN score the canaries that feed it.

CANARIES ARE OFF BY DEFAULT (build(include_canaries=False)). The 2026-08-10
project call deferred indicator questions to v2 ("too complex for v1, limited
value-add now") — v1 ships the top-level risk decomposition only. The
machinery is gated, not deleted, because v2 wants it back.

"short" for the XPT questions now lives in data/starter_questions.json (see
redlines/questions.py) rather than a local SHORT dict — same migration
graph1's port made.
"""
import json
import statistics

from ..runlog import latest_instrument_rows, complete_panel_rows
from ..runlog import instrument_info
from ..config import XRISK_CANARIES_ROOT
from ..questions import (all_questions, horizon_label, horizon_sort_key,
                         load_ladder, severity_label)
from ..registry import model_colors
from ..runlog import current_rows, latest_pooled, load_runlog

CANARIES = XRISK_CANARIES_ROOT / "data"
CANARY_CORPUS = CANARIES / "xrisk_canary_corpus.jsonl"
CANARY_RUNS = CANARIES / "forecast_runs.jsonl"

# Auto-ARC categories. Nuclear and Climate left the question set; "broad"
# became "crosscutting" and covers the two catastrophe questions plus human
# disempowerment.
DOMAIN_LABEL = {"crosscutting": "Catastrophe", "incident": "AI incident",
                "AI": "AI", "Biorisk": "Bio", "Climate": "Climate"}

# code/make_demo_databank.py imported MODEL_COLORS from make_demo_graph1; now
# sourced from the registry (same frontier-five order, same colors/labels).
MODEL_COLORS = model_colors()


def _jsonl(p):
    with open(p) as f:
        return [json.loads(l) for l in f if l.strip()]


def _bottom_line_rows():
    """Our own forecasts: latest per (question, model) -> ensemble median.

    Returns (rows, horizons). Each row headlines its LONGEST horizon — the
    bottom line — but carries every elicited horizon in `byHorizon`, keyed by
    the raw horizon, because showing only 2100 read as "this is all there is"
    (question-set author, 2026-08-19). `horizons` is the union across rows, in
    resolve order, so the panel can offer them as a toggle without re-deriving.
    """
    rows = complete_panel_rows(latest_instrument_rows(load_runlog()))
    # Newest date per pair, that day's calls pooled to their mean
    # (redlines.runlog.pool) -- identical to latest_per() with one call a day.
    # The current panel's latest reading (redlines.runlog.current_rows).
    latest = latest_pooled(current_rows(rows))

    meta_by_id = all_questions()
    spec = load_ladder()
    seen_h = set()
    out = []
    for qid in sorted({k[0] for k in latest}):
        meta = meta_by_id.get(qid)
        if not meta:
            continue
        is_ladder = qid.startswith("ladder:")
        # headline horizon: the longest one elicited
        per_h = {}
        declined = []
        for label, _ in MODEL_COLORS:
            r = latest.get((qid, label))
            if not r:
                continue
            if not r["forecasts"]:
                declined.append(label)
                continue
            for f in r["forecasts"]:
                per_h.setdefault(f["horizon"], {})[label] = 100 * f["probability"]
        if not per_h:
            continue
        # The longest horizon this row reports. Sorted by the date it RESOLVES,
        # not by string: "6mo" sorts after "2100" alphabetically, which would
        # headline a six-month forecast as the long-horizon number.
        h = max(per_h, key=lambda x: horizon_sort_key(x, spec))
        per = per_h[h]
        seen_h.update(per_h)
        # The human baseline at the SAME horizon this row reports, for both
        # The human columns stay in the schema and stay empty. No panel has
        # forecast this question set (the XPT anchors came out on 2026-08-18
        # for not matching the set's wording), and dropping the columns would
        # churn every consumer for a gap we expect to fill.
        out.append({
            "kind": "bottom-line",
            "question": (f"{meta['cause_label']} — {severity_label(meta)}"
                         if is_ladder else meta.get("short", qid)),
            "category": DOMAIN_LABEL.get(meta.get("category"), meta.get("category")),
            # The threshold as a rendered field, so the table never composes one.
            "severity": severity_label(meta),
            "horizon": horizon_label(h, spec),
            "median": round(statistics.median(per.values()), 3),
            "n_models": len(per),
            # Every horizon, not just the headline. n is per-horizon because a
            # model can answer 2100 and decline 6mo. Per-model values ride
            # along so the page's CSV export is the full grid — every model x
            # every question x every horizon (project lead, 2026-08-19) — not just
            # the medians the table shows.
            "byHorizon": {hh: {"median": round(statistics.median(per_h[hh].values()), 3),
                               "n": len(per_h[hh]),
                               "models": {l: round(p, 3) for l, p in per_h[hh].items()}}
                          for hh in per_h},
            "declined": declined,
            "status": "open",
            "resolves": None,
            "super": None,
            # Which human panel, per row. Blank means no panel has asked this
            # question yet — true of 33 of the 35, until the September round.
            "superSource": None,
            "source": "incident ladder" if is_ladder else "cross-cutting",
        })
    horizons = [{"key": hh, "label": horizon_label(hh, spec)}
                for hh in sorted(seen_h, key=lambda x: horizon_sort_key(x, spec))]
    return out, horizons


def _canary_rows():
    """Canaries that have at least one forecast, with their coupling to the
    bottom-line questions (|P(bottom | canary yes) - P(bottom | canary no)|)."""
    corpus = _jsonl(CANARY_CORPUS)
    runs = _jsonl(CANARY_RUNS)
    by_q = {}
    for r in runs:
        by_q.setdefault(r["question"], []).append(r)

    out = []
    for c in corpus:
        rs = by_q.get(c["question"])
        if not rs:
            continue
        ps, coupling = [], []
        for r in rs:
            b = r.get("bundle") or {}
            if b.get("p_yes") is not None:
                ps.append(100 * b["p_yes"])
            for q in b.get("questions") or []:
                if "cond_yes" in q and "cond_no" in q:
                    coupling.append((abs(q["cond_yes"] - q["cond_no"]), q["id"]))
        if not ps:
            continue
        coupling.sort(reverse=True)
        top = coupling[0] if coupling else None
        out.append({
            "kind": "canary",
            "question": c["question"],
            "category": DOMAIN_LABEL.get(c["parent"].get("domain"), c["parent"].get("domain")),
            "severity": None,
            "horizon": "resolves " + c["resolution_date"][:7],
            "median": round(statistics.median(ps), 3),
            "n_models": len({r["model"] for r in rs}),
            "declined": [],
            "status": "open",
            "resolves": c["resolution_date"],
            "super": None,
            "superSource": None,
            "source": "canary",
            "parent": c["parent"]["id"],
            "criteria": c.get("resolution_criteria"),
            "res_source": c.get("resolution_source"),
            "coupling": round(top[0], 3) if top else None,
            "coupling_to": top[1] if top else None,
            "why": c.get("why_policy_relevant"),
        })
    out.sort(key=lambda r: (-(r["coupling"] or 0), r["resolves"]))
    return out


def build(include_canaries=False):
    bl, horizons = _bottom_line_rows()
    can = _canary_rows() if include_canaries else []
    blob = {
        "rows": bl + can,
        "instrumentInfo": instrument_info(complete_panel_rows(latest_instrument_rows(load_runlog()))),
        "horizons": horizons,
        "counts": {"bottomLine": len(bl), "canary": len(can)},
    }
    if can:
        blob["canaryNote"] = (
            "Near-term leading indicators generated from the XPT questions "
            "(xrisk-canaries). Unlike the bottom-line questions they resolve "
            "in 2026-27, so they can actually be scored. “Moves bottom line” "
            "is the forecast swing in the linked catastrophic question between "
            "the canary resolving yes and no.")
    return blob
