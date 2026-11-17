"""Graph 2: the severity ladders, and the coherence check that needs no resolution.

Four AI incident types, nine rungs each, one wording per cause with the
threshold as the only variable — so every curve spans the whole severity axis
and causes are directly comparable at equal severity.

TWO LADDERS SINCE 2026-10-19 (Ezra Karger: separate deaths and damages). Every
rung used to be one question resolving on deaths OR damages; it is now two,
one resolving on deaths (or equivalent morbidity) and one on economic damages,
so the panel is two charts -- a deaths ladder and a damages ladder -- each with
its own axis, rung ticks and historical marks (`legs`). Since 2026-10-21
damages exclude monetized mortality, so the two ladders measure different
harms and neither bounds the other (until then the damages question contained
the deaths question, and the audit checked it as LEG).

Cyber is on both ladders. It was held out by design while the axis was
deaths-only (per the paper's lead author, 2026-08-03: cyber belongs on a
DAMAGES ladder); the damages ladder is that ladder, and its deaths ladder is
asked alongside like every cause's.

The container is "any AI-related incident", not "all causes". The set's
definition makes that class contain the other three, so it plays the role the
old slate "All causes" curve played. But it is NOT an all-cause ceiling —
nuclear and natural pandemics are outside this question set entirely — so the
CROSS check it anchors is AI-internal. That is a real narrowing and the panel
says so rather than letting the slate curve imply a totality it does not have.

The catastrophe and extinction questions are NOT drawn here: the catastrophe
pair came off on 2026-08-18 (marks belonging to no curve, and nobody had asked
for them) and the extinction pair on 2026-09-16, the day the extinction RUNG
joined every deaths ladder (project lead: "just show us the probabilities like
normal"). Both pairs are their own questions on Graph 1; the BRACKET and
SUBSET relations that tie them to the ladder are audited here regardless.

Coherence is REPORTED here, never enforced. The prompt states no relation
between these questions (code/run_unified.py), so a violation is a measurement.
"""
import statistics

from ..coherence import audit as full_audit
from ..historical import markers as historical_markers
from ..questions import (DAMAGES_AXIS, SEVERITY_AXIS, cause_category, horizon_label,
                         horizon_sort_key, ladder_index, load_ladder)
from ..registry import model_colors as _model_colors
from ..conditional import apply_or, level_or
from ..runlog import current_rows, latest_pooled, load_runlog, instrument_info
from ..runlog import latest_instrument_rows, complete_panel_rows
from ..runlog import elicitation_date, instrument_rows, rows_by_day


def probs(latest, model_colors, qid, horizon):
    """{model_label: percent} for one question at one horizon (declines omitted)."""
    out = {}
    for label, _ in model_colors:
        r = latest.get((qid, label))
        if not r or not r["forecasts"]:
            continue
        for f in r["forecasts"]:
            if f["horizon"] == horizon:
                out[label] = round(100 * f["probability"], 4)
    return out


def point_ci(latest, model_colors, qid, horizon, median_pct):
    """95% CI of the ensemble median at one rung point, in percent, or None.

    The Conditional-on tab's band and Graph 1's grey bar, at a point: per
    model a t-interval on the LOGIT of its same-day draws (an odds ratio
    about the centre; redlines.conditional.level_or), the ensemble's
    interval the median across models of those, placed on the ensemble
    median's odds -- bounded in 0-100% by construction. Re-elicitation
    uncertainty, not model disagreement. None until a day holds more than
    one draw per model.
    """
    ors = []
    for label, _ in model_colors:
        r = latest.get((qid, label))
        d = (r or {}).get("draws", {}).get(horizon) if r else None
        c = level_or(d) if d and len(d) > 1 else None
        if c:
            ors.append(c)
    if not ors or median_pct is None:
        return None
    orr = [statistics.median(c[0] for c in ors), statistics.median(c[1] for c in ors)]
    lo, hi = apply_or(median_pct / 100, orr)
    return [round(100 * lo, 4), round(100 * hi, 4)]


DISPLAY_ROWS = (
    ("HORIZON", ("HORIZON",),
     "An event that has happened by 2030 has also happened by 2050."),
    ("LADDER", ("LADDER",),
     "The probability of reaching a higher severity threshold is never higher than "
     "the probability of reaching a lower one."),
    ("SUBSET", ("SUBSET", "CROSS", "BRACKET"),
     "Some questions are special cases of another, and a special case can "
     "never be likelier than the general one."),
)

# Each leg's axis (redlines.questions), keyed as the spec keys its legs.
LEG_AXES = {"deaths": SEVERITY_AXIS, "damages": DAMAGES_AXIS}


def _display_rows(res):
    """The audit as the panel prints it: DISPLAY_ROWS, pairs pooled per row."""
    rows = []
    for key, keys, title in DISPLAY_ROWS:
        parts = [res[k] for k in keys if k in res]
        bad = sum(v["bad"] for v in parts)
        n = sum(v["n"] for v in parts)
        rows.append({"key": key, "title": title, "constraints": list(keys),
                     "bad": bad, "n": n,
                     "rate": round(100 * (1 - bad / n), 2) if n else None,
                     "examples": [e for v in parts for e in v["examples"]][:6]})
    return rows


def _rung_value(r, leg):
    """Where a rung sits on one ladder's axis."""
    return r["deaths"] if leg == "deaths" else r["damages_usd"]


def _leg_rungs(spec, leg):
    """The rung ticks of one ladder: every rung with that leg, in order, with
    the leg's own label and short label from the spec."""
    return [{"rung": r["short"], "value": _rung_value(r, leg),
             "label": r["legs"][leg]["label"], "short": r["legs"][leg]["short"]}
            for r in spec["rungs"] if leg in r["legs"]]


def build(source_rows=None, include_history=True):
    model_colors = _model_colors()
    source_rows = load_runlog() if source_rows is None else source_rows
    rows = complete_panel_rows(latest_instrument_rows(source_rows))
    # Newest date per pair, that day's calls pooled to their mean
    # (redlines.runlog.pool) -- identical to latest_per() with one call a day.
    latest = latest_pooled(current_rows(rows))    # the current panel's latest reading
    # Only the models with rows: the registry's list is every drawable model
    # (the current ECI panel first), and pairsChecked, the audit's labels and
    # the legend must all count the models that answered, not the roster.
    present = {label for _, label in latest}
    model_colors = [(l, c) for l, c in model_colors if l in present]
    spec = load_ladder()
    as_of = max((elicitation_date(r) for r in rows), default=None)

    # From the spec, not from questions[0]: the set has questions on different
    # horizon grids, and reading the first question's list silently truncated
    # every other question to it.
    horizons = sorted([h for h in spec["horizons"] if h],
                      key=lambda h: horizon_sort_key(h, spec))
    index = ladder_index(spec)
    container = spec["relations"]["cross"]["container"]
    legs = [l["key"] for l in spec["legs"]]

    out_h = {}
    for h in horizons:
        declines, by_leg = {}, {}
        for leg in legs:
            causes, violations = [], []
            for c in spec["causes"]:
                rungs = []
                for r in spec["rungs"]:
                    q = index.get((c["key"], r["short"], leg))
                    if not q or h not in q["horizons"]:
                        continue
                    per = probs(latest, model_colors, q["id"], h)
                    for label, _ in model_colors:
                        row = latest.get((q["id"], label))
                        if row and not row["forecasts"]:
                            declines[label] = declines.get(label, 0) + 1
                    if not per:
                        continue
                    med = round(statistics.median(per.values()), 4)
                    rungs.append({"rung": r["short"], "value": _rung_value(r, leg),
                                  "label": q["severity"]["label"], "short": q["severity"]["short"],
                                  "qid": q["id"], "per_model": per,
                                  "median": med,
                                  "ci": point_ci(latest, model_colors, q["id"], h, med)})
                if len(rungs) < 2:
                    continue
                for a, b in zip(rungs, rungs[1:]):
                    for m in sorted(set(a["per_model"]) & set(b["per_model"])):
                        if b["per_model"][m] > a["per_model"][m]:
                            violations.append({
                                "model": m, "cause": cause_category(c), "leg": leg, "horizon": h,
                                "broader": a["rung"], "narrower": b["rung"],
                                "broaderLabel": a["label"], "narrowerLabel": b["label"],
                                "p_broader": a["per_model"][m],
                                "p_narrower": b["per_model"][m]})
                causes.append({"key": c["key"], "label": cause_category(c),
                               "color": c["color"],
                               "container": bool(c.get("container")),
                               "rungs": rungs})
            by_leg[leg] = {"causes": causes, "violations": violations,
                           # Adjacent-rung pairs per cause, times the models:
                           # the LADDER constraint at this horizon on this leg.
                           "pairsChecked": sum(len(c["rungs"]) - 1 for c in causes) * len(model_colors)}
        out_h[h] = {"legs": by_leg, "declines": declines}

    # What each incident type MEANS, for the definitions modal. The set's own
    # first sentence, trimmed — the modal used to carry a hand-written taxonomy
    # (AI-enabled CBRN, geopolitical/nuclear, a non-AI baseline) that described
    # a question set this dashboard no longer asks.
    cause_defs = []
    for c in spec["causes"]:
        q = next((x for x in spec["questions"] if x["cause"] == c["key"]), None)
        first = ""
        if q and q.get("criteria"):
            for line in q["criteria"].splitlines():
                line = line.strip().lstrip("*").strip()
                if len(line) > 40:
                    first = line.split(". E.g.")[0].split(". This")[0].rstrip(".") + "."
                    break
        cause_defs.append({"key": c["key"], "label": cause_category(c),
                           "color": c["color"], "definition": first,
                           "container": bool(c.get("container"))})

    # THE WHOLE AUDIT, not just the constraint this chart happens to draw.
    #
    # The panel used to headline "Coherence rate 100%" off `pairsChecked`,
    # which counts adjacent-rung pairs within a cause at ONE horizon -- the
    # LADDER constraint alone. LADDER really is clean. The 2026-08-18 run's
    # seven violations are all in CROSS (a specific cause above the AI
    # container) and BRACKET (the catastrophe question above the rung that
    # contains it), neither of which this chart checks. So a reader saw 100%
    # while the measured rate was 99.7%, on a panel whose whole claim is that
    # coherence is measured rather than imposed. Report every constraint.
    P = {}
    for (qid, lab), r in latest.items():
        if r["forecasts"]:
            P[(qid, lab)] = {f["horizon"]: f["probability"]
                             for f in r["forecasts"]}
    labels = [l for l, _ in model_colors]
    res = full_audit(P, spec=spec, labels=labels, horizons=horizons) if P else {}
    bad = sum(v["bad"] for v in res.values())
    n = sum(v["n"] for v in res.values())

    history = []
    if include_history and rows:
        for day, day_rows in sorted(rows_by_day(instrument_rows(source_rows)).items()):
            if day >= as_of or not complete_panel_rows(day_rows, labels):
                continue
            previous = build(day_rows, include_history=False)
            history.append({"date": day, "instrumentInfo": previous["instrumentInfo"],
                            "byHorizon": {h: {"legs": {leg: {"causes": [
                                {"key": c["key"], "rungs": [
                                    {k: r[k] for k in ("rung", "value", "median")}
                                    for r in c["rungs"]]}
                                for c in side["causes"]]}
                                for leg, side in d["legs"].items()}}
                                for h, d in previous["byHorizon"].items()}})

    general = next(q for q in spec["questions"] if q["cause"] == container)
    return {
        "history": history[-2:],
        "horizons": horizons,
        "instrumentInfo": instrument_info(rows),
        "causeDefs": cause_defs,
        # Every constraint the question set implies, across all models and all
        # horizons -- the number the dashboard should be judged on.
        "audit": {
            "byConstraint": {k: {"bad": v["bad"], "n": v["n"],
                                 "rate": v["rate"],
                                 "examples": v["examples"][:6]}
                             for k, v in res.items()},
            "bad": bad, "n": n,
            "rate": round(100 * (1 - bad / n), 2) if n else None,
            # What the panel prints: three rows, one plain sentence each
            # (question-set author, 2026-08-19: the old titles — "P non-decreasing
            # over time" — explained nothing to a reader who is not already us;
            # project lead, 2026-08-27: CROSS and BRACKET were not intuitive either).
            # Those ARE special-case orderings — an epidemic is one kind of
            # AI-related incident, a 10%-of-population catastrophe is one way
            # to pass the 100M rung — so their pairs fold into the SUBSET row
            # rather than vanishing. The headline above stays the whole audit;
            # byConstraint keeps the five-way split for the paper and for
            # tests/test_coherence.py.
            "rows": _display_rows(res),
        },
        "horizonLabels": {h: horizon_label(h, spec, as_of) for h in horizons},
        "models": [{"label": l, "color": c} for l, c in model_colors],
        # The two ladders: each leg's axis and rung ticks, from the spec. The
        # page draws one chart per entry and types none of these numbers.
        "legs": [{"key": l["key"], "label": l["label"], "unit": l["unit"],
                  "axis": LEG_AXES[l["key"]], "rungs": _leg_rungs(spec, l["key"])}
                 for l in spec["legs"]],
        # The rung index -- both thresholds of each severity level -- for the
        # Definitions modal's list.
        "rungs": [{"rung": r["short"], "deaths": r["deaths"],
                   "damages": r["damages_usd"], "label": r["label"]}
                  for r in spec["rungs"]],
        "byHorizon": out_h,
        "container": container,
        "notes": spec["notes"],
        # The ladder's resolution criteria, verbatim, for the Definitions
        # modal (project lead, 2026-09-10: the modal had paraphrased the onset
        # window, the QALY rate and the damages accounting by hand). Every
        # question of a cause shares one criteria/details block; the
        # container's is the general one.
        "ladder": {"criteria": general["criteria"], "details": general["details"]},
        # The deaths axis the expected-deaths panels share (Graph 1, the
        # Timeline, the Policy-levers tab), so a loss reads at its rung.
        "severityAxis": SEVERITY_AXIS,
        # Historical events on the severity axes, as shaded bands, each on the
        # ladder(s) it has a figure for. The paper's lead author asked for these
        # on 2026-08-17 so a reader can tell whether a threshold is frightening;
        # the band, not a line, because the published estimates for two of the
        # three disagree by a factor approaching two.
        #
        # They are severity-axis context ONLY. Every curve here is an
        # AI-related incident inside a horizon window; the events are non-AI
        # and accumulated over years. `historical.caveat` says so and the
        # panel renders it — without that a reader compares curve height
        # against the Black Death, which is not a comparison this chart makes.
        "historical": historical_markers(),
        # Coherence is measured, not imposed. The page must say so where it
        # shows the number, or a reader will reasonably assume we filtered.
        "coherence": {
            "enforced": False,
            "note": "The models are told nothing about how these questions "
                    "relate. Every rung of every cause, on both ladders, is "
                    "answered in one call, and the orderings are checked "
                    "afterwards. No forecast is adjusted or discarded for "
                    "failing one.",
        },
    }
