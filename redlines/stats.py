"""Shared statistical estimators for the redlines dashboard.

Ported byte-exact (same arithmetic, same rounding, same edge-case behavior)
from the forked copies that used to live scattered across code/*.py. Each
function below names its source script and states which semantic it
implements: EQUAL-COUNT vs. WEIGHTED-equal-mass binning is a real distinction
here, and a mislabeled decile method was a real bug in this codebase.

No function here bakes in a climatology constant. The historical scripts
disagreed on the FreeCiv climatology constant (0.0458 in
archive/make_demo_data.py and archive/litellm-runners/run_eval.py vs. 0.045 in
code/make_demo_combined.py) — that constant belongs in redlines/config.py.
stats.py stays constant-free; bss() below takes climatology's Brier score as
an explicit argument.
"""


def wilson_interval(k, n, z=1.96):
    """95% Wilson score interval for an observed frequency k/n.

    Source: code/make_demo_graph3.py::wilson.

    Used so a reader doesn't mistake small-sample zigzag (very different
    per-decile n) for miscalibration.

    Returns (lo, hi), each rounded to 4 places, clamped to [0, 1]. (0.0, 1.0)
    when n == 0.
    """
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def tail_stats(pairs, cut=0.10):
    """Summarize the low-probability bin: forecasts below `cut`.

    Source: code/make_demo_graph3.py::tail.

    `pairs` is an iterable of (forecast, observed) tuples. Returns
    {"n": len, "pred": mean forecast, "obs": mean observed}, pred/obs rounded
    to 4 places, or {"n": 0, "pred": None, "obs": None} when nothing in
    `pairs` falls under `cut`.
    """
    lo = [(f, o) for f, o in pairs if f < cut]
    if not lo:
        return {"n": 0, "pred": None, "obs": None}
    return {"n": len(lo),
            "pred": round(sum(f for f, _ in lo) / len(lo), 4),
            "obs": round(sum(o for _, o in lo) / len(lo), 4)}


def deciles_equal_count(pairs, n_bins=10):
    """EQUAL-COUNT (fixed row-count, NOT fixed-width or weighted) decile
    points, each with a Wilson 95% CI.

    Source: code/make_demo_graph3.py::series_stats — specifically its
    `bins`/`pts` binning (the whole-series brier/resolution summary that
    series_stats also computed is out of scope here; the view layer builds
    that directly with brier_mean()).

    `pairs` is a sized iterable of (forecast, observed) tuples. Sorted by
    forecast (then observed, via tuple ordering), then split into `n_bins`
    bins at index boundaries round(i*n/n_bins) .. round((i+1)*n/n_bins) — an
    EQUAL-COUNT split (as close to n/n_bins rows per bin as the rounding
    allows), NOT equal-width probability bins. Empty bins (possible when
    n < n_bins) are dropped, so the result can have fewer than n_bins points.
    This exact rounding is what the dashboard's JS deciles() replicates.

    Returns a list of {"pred", "obs", "n", "lo95", "hi95"} dicts, one per
    non-empty bin in ascending-forecast order; pred/obs rounded to 4 places.
    """
    n = len(pairs)
    ordered = sorted(pairs)
    bins = [b for b in (ordered[round(i * n / n_bins):round((i + 1) * n / n_bins)]
                        for i in range(n_bins)) if b]
    pts = []
    for b in bins:
        hits = sum(o for _, o in b)
        lo95, hi95 = wilson_interval(hits, len(b))
        pts.append({"pred": round(sum(f for f, _ in b) / len(b), 4),
                    "obs": round(hits / len(b), 4), "n": len(b),
                    "lo95": lo95, "hi95": hi95})
    return pts


def deciles_weighted(weighted, n_bins=10):
    """WEIGHTED equal-MASS decile points (each bin carries ~1/n_bins of the
    total weight; the row COUNT per bin is uneven).

    Source: code/make_demo_combined.py::wdeciles (there `n_bins` was
    hardcoded to 10 — generalized here as a parameter, byte-identical at the
    default).

    `weighted` is an iterable of (pred, obs, weight) triples. Sorted by pred,
    then walked in ascending order accumulating weight; a row starts a new
    bin once cumulative weight crosses the next 1/n_bins-of-total-weight
    step. This is a DIFFERENT semantic from deciles_equal_count (which
    balances row count, not weight) — confusing the two was a real bug in
    this codebase.

    Returns a list of {"pred", "obs", "n"} dicts (weighted means), one per
    non-empty bin. pred/obs are left UNROUNDED, matching wdeciles — callers
    round at the point of use. Returns [] if total weight is <= 0.
    """
    s = sorted(weighted, key=lambda t: t[0])
    W = sum(w for _, _, w in s)
    if W <= 0:
        return []
    step = W / n_bins
    bins = [[] for _ in range(n_bins)]
    cum = 0.0
    for p, o, w in s:
        bins[min(n_bins - 1, int(cum / step))].append((p, o, w))
        cum += w
    pts = []
    for b in bins:
        if not b:
            continue
        ww = sum(w for _, _, w in b)
        pts.append({"pred": sum(p * w for p, _, w in b) / ww,
                    "obs": sum(o * w for _, o, w in b) / ww, "n": len(b)})
    return pts


def brier_mean(pairs):
    """Mean squared error over (value, observed) pairs — a Brier score.

    Source: code/make_demo_combined.py::bss_of, split out of its `b`/`bc`
    computation so the forecaster's Brier and climatology's Brier are
    computed by the same code, and so bss() below can take climatology as an
    explicit argument instead of a constant baked into the estimator (see
    module docstring).

    `pairs` is a non-empty iterable of (value, observed) tuples — pass
    (forecast, observed) pairs for the forecaster's Brier, or
    (climatology, observed) pairs for climatology's. Raises
    ZeroDivisionError on an empty iterable (the ungated `sum(...)/n` style
    used throughout the source scripts; bss_of's own `if not pairs` guard is
    the caller's responsibility to replicate if needed).
    """
    pairs = list(pairs)
    n = len(pairs)
    return sum((p - o) ** 2 for p, o in pairs) / n


def bss(brier, clim_brier):
    """Brier Skill Score: 1 - brier / clim_brier, or None if clim_brier <= 0.

    Source: code/make_demo_combined.py::bss_of — the skill-score ratio half
    of it (see brier_mean() above for the other half).

    Takes climatology's Brier score as an EXPLICIT argument rather than a
    baked-in constant: the historical scripts disagreed on the FreeCiv
    climatology constant (0.0458 vs 0.045 — see module docstring), and that
    constant belongs in redlines/config.py, not here.

    To reproduce bss_of(pairs) exactly, where each element of `pairs` is a
    (forecast, observed, climatology) triple:

        bss(brier_mean([(p, o) for p, o, c in pairs]),
            brier_mean([(c, o) for p, o, c in pairs]))

    (guarding the empty-`pairs` case yourself, as bss_of did).
    """
    if clim_brier is None or clim_brier <= 0:
        return None
    return round(1 - brier / clim_brier, 3)


def spearman(xs, ys):
    """Spearman rank correlation coefficient.

    Source: code/make_demo_combined.py::spearman — the one copy of this
    estimator (of five forked copies in this codebase) with an n<2 guard;
    the other four raise ZeroDivisionError on fewer than 2 points, this one
    returns 0.0.
    """
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for k, i in enumerate(s):
            r[i] = k
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    if n < 2:
        return 0.0
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - 6 * d2 / (n * (n * n - 1))


def spearman_ties(xs, ys):
    """Spearman rank correlation with TIED values given their average rank.

    Source: code/observational/score_bench.py::spearman (the observational
    conditional bench's scorer, vendored 2026-08-28). spearman() above ranks
    ties in input order, which is what Graph 4's golden output was built on
    and is left alone; the bench's implied associations tie often (several
    control pairs come back at exactly 0), so its rank statistic needs the
    average-rank convention -- the one scipy.stats.spearmanr uses -- to
    match the numbers the spec's pass bar was set against.

    Returns 0.0 when either side has no variance (all tied).
    """
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    if len(xs) < 2:
        return 0.0
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


def _betacf(a, b, x, max_iter=300, eps=3e-14):
    """Continued fraction for the regularized incomplete beta (Numerical
    Recipes betacf, modified Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) >= tiny else tiny)
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) >= tiny else tiny)
        c = 1.0 + aa / (c if abs(c) >= tiny else tiny)
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) >= tiny else tiny)
        c = 1.0 + aa / (c if abs(c) >= tiny else tiny)
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betainc(a, b, x):
    """Regularized incomplete beta I_x(a, b), stdlib only (math.lgamma +
    the continued fraction above). Accurate to ~1e-12 on the t-distribution
    tails this module needs."""
    import math
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def spearman_p(rho, n):
    """Two-sided p-value for a Spearman rho on n pairs, by the t-distribution
    approximation t = rho * sqrt((n-2) / (1-rho^2)) on n-2 degrees of freedom
    -- exactly what scipy.stats.spearmanr reports, so the causal bench's
    locked headline (rho=+0.68, p=0.0003, n=23; data/causal/README.md)
    reproduces here without scipy. Returns 1.0 for n < 3 or |rho| >= 1 gives
    0.0. Models are not independent samples: treat as descriptive, as the
    bench's own README says."""
    import math
    if n < 3:
        return 1.0
    if abs(rho) >= 1.0:
        return 0.0
    df = n - 2
    t = rho * math.sqrt(df / (1.0 - rho * rho))
    # two-sided: P(|T| > |t|) = I_{df/(df+t^2)}(df/2, 1/2)
    return betainc(df / 2.0, 0.5, df / (df + t * t))
