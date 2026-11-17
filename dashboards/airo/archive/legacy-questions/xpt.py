"""XPT quantity questions -> a probability comparable with the model forecasts.

Four of the thirteen starter questions (#15-#18, the bioweapon severity rungs)
are `value_kind == "quantity"`: XPT asked "how many times will a state actor
use..." and elicited a five-point percentile ladder over the EVENT COUNT
(questionType `multiYearDistrib`, answerText "5th %".."95th %"). The dashboard
asks the models a probability -- will this happen at all by the horizon -- so
the stored median count (1.0 events, 0.15 events, ...) is not comparable with
it, and every view has suppressed the human baseline on these four rather than
print an event count in a percent column.

The comparable quantity IS recoverable from the ladder: the models' question is
P(N >= 1), and the ladder is five points of the forecaster's CDF over N. This
module turns one into the other.

METHOD (pure; no I/O -- code/xpt_build_exceedance.py does the reading):

  per forecaster  interpolate the CDF at the threshold. The ladder gives
                  F(q_p) = p at p in {.05, .25, .50, .75, .95}; linear
                  interpolation between the two points bracketing x yields
                  F(x), and P(N >= x) = 1 - F(x).

  censoring       a forecaster whose whole ladder sits below the threshold has
                  only told us P(N >= x) <= 0.05; one whose whole ladder sits
                  at or above it, only P(N >= x) >= 0.95. These are BOUNDS, not
                  estimates. They are kept as bounds and never invented into
                  point values.

  group           median across forecasters, which is how every other XPT
                  baseline in this repo is aggregated (see the internal, unpublished
                  xrisk-canaries checkout's forecast/xpt_seed.py::compute_gaps,
                  "group median").

WHY THE MEDIAN SURVIVES CENSORING. A bound is order-correct even though its
value is unknown -- a forecaster bounded above by 0.05 really does belong below
every interpolated forecaster above 0.05 -- so bounded forecasters can be
ranked, and the median is unaffected by HOW MANY sit in the tail as long as the
median itself is not one of them. group_exceedance() therefore returns the
median and reports whether it landed inside a bounded block. When it did, the
result is an upper (or lower) bound and is labelled as one; it is never
silently rendered as a point estimate. Two of the four questions do land there
-- see data/starter_questions.json's `xpt_exceedance` blocks.
"""
from __future__ import annotations

import statistics

# The XPT elicitation ladder for multiYearDistrib questions: answerText in the
# upstream panel -> the percentile of the count distribution it fixes.
LADDER = (("5th %", 0.05), ("25th %", 0.25), ("50th %", 0.50),
          ("75th %", 0.75), ("95th %", 0.95))

# The models' bottom-line question is "does this happen at all", i.e. at least
# one event. Exposed as a constant so a future "at least N" reading is a call
# argument rather than an edit.
THRESHOLD = 1.0

INTERP = "interp"
BOUND_UPPER = "bound-upper"   # p <= value: the whole ladder is below x
BOUND_LOWER = "bound-lower"   # p >= value: the whole ladder is at or above x


def p_at_least(ladder, x=THRESHOLD):
    """P(N >= x) for ONE forecaster's percentile ladder.

    `ladder` maps the LADDER answer texts to that forecaster's elicited count.
    Returns (p, kind) with kind one of INTERP / BOUND_UPPER / BOUND_LOWER; for
    the two bound kinds, p is the bound, not an estimate.

    Raises ValueError if the ladder is incomplete or not non-decreasing -- a
    malformed ladder is a data problem to surface, not to interpolate through.
    """
    missing = [name for name, _ in LADDER if name not in ladder]
    if missing:
        raise ValueError(f"incomplete percentile ladder, missing {missing}: {ladder!r}")
    pts = [(float(ladder[name]), p) for name, p in LADDER]
    if any(a[0] > b[0] for a, b in zip(pts, pts[1:])):
        raise ValueError(f"percentile ladder is not non-decreasing: {ladder!r}")

    if x <= pts[0][0]:            # even the 5th percentile reaches x
        return 1.0 - pts[0][1], BOUND_LOWER
    if x >= pts[-1][0]:           # even the 95th percentile falls short of x
        return 1.0 - pts[-1][1], BOUND_UPPER
    for (q0, p0), (q1, p1) in zip(pts, pts[1:]):
        if q0 <= x <= q1:
            # q1 == q0 only when the ladder is flat across the bracket; the
            # lower percentile is then the tightest statement available.
            f = p0 if q1 == q0 else p0 + (p1 - p0) * (x - q0) / (q1 - q0)
            return 1.0 - f, INTERP
    raise ValueError(f"threshold {x} not bracketed by ladder {ladder!r}")


def group_exceedance(ladders, x=THRESHOLD):
    """Median P(N >= x) across a group of forecasters.

    `ladders` is an iterable of per-forecaster ladders. Returns a dict:

        p          the median (a bound when `censored` is set)
        censored   None | "upper" | "lower" -- whether the median forecaster is
                   one whose ladder never crosses x, so p is only a bound
        n          forecasters with a usable ladder
        n_bounded  how many of them are bounds rather than interpolations

    Returns None if no forecaster has a usable ladder.
    """
    vals = []
    for lad in ladders:
        try:
            vals.append(p_at_least(lad, x))
        except ValueError:
            continue          # incomplete/degenerate ladder: not a forecaster
    if not vals:
        return None
    vals.sort(key=lambda t: t[0])
    n = len(vals)
    p = statistics.median([v for v, _ in vals])
    # Which kind the median sits on. For an even n the median is the mean of
    # the two central entries; the result is a bound only if BOTH are.
    mid = [vals[n // 2]] if n % 2 else [vals[n // 2 - 1], vals[n // 2]]
    kinds = {k for _, k in mid}
    censored = None
    if kinds == {BOUND_UPPER}:
        censored = "upper"
    elif kinds == {BOUND_LOWER}:
        censored = "lower"
    return {"p": p, "censored": censored, "n": n,
            "n_bounded": sum(1 for _, k in vals if k != INTERP)}


def format_percent(entry, digits=1):
    """Render an `xpt_exceedance` group entry for display: "50.0%", "<5.0%".

    One renderer, so the databank table, Graph 1's anchor labels and Graph 2's
    ladder all spell a censored bound the same way.
    """
    if entry is None:
        return None
    pct = 100.0 * entry["p"]
    prefix = {"upper": "<", "lower": ">", None: ""}[entry.get("censored")]
    return f"{prefix}{pct:.{digits}f}%"
