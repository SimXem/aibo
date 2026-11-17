"""Tests for redlines.stats.

Two kinds of coverage per function:

  * a fixture test with a hand-computable (or hand-verifiable-by-formula)
    expected value, so a reader can sanity-check the estimator without
    trusting any other code;
  * a differential test that replays the SAME function against the original,
    forked implementation it was ported from. The originals are extracted,
    unmodified, from `git show HEAD:code/make_demo_graph3.py` and
    `git show HEAD:code/make_demo_combined.py` into orig_graph3.py /
    orig_combined.py under ORIGINALS_DIR (see that directory's module
    docstrings) — this file does not modify or re-derive them.

Run with:  python3 -m unittest tests.test_stats -v   (from the repo root)
"""
import importlib.util
import random
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from redlines import stats  # noqa: E402

# The pre-package scripts these estimators were ported from, vendored verbatim
# (git show e6de830^:code/make_demo_graph3.py and make_demo_combined.py). They
# import two sibling helpers from code/ at module level, hence the path insert.
ORIGINALS_DIR = REPO_ROOT / "tests" / "fixtures" / "originals"
if str(REPO_ROOT / "code") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "code"))

N_TRIALS = 200


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_orig_g3 = _orig_cb = None
_ORIGINALS_ERR = None
try:
    _orig_g3 = _load_module("orig_graph3", ORIGINALS_DIR / "orig_graph3.py")
    _orig_cb = _load_module("orig_combined", ORIGINALS_DIR / "orig_combined.py")
except Exception as exc:  # pragma: no cover - environment-dependent
    _ORIGINALS_ERR = exc

requires_originals = unittest.skipIf(
    _ORIGINALS_ERR is not None,
    f"original implementations unavailable under {ORIGINALS_DIR}: {_ORIGINALS_ERR}",
)


def _rand_pairs(rng, n):
    """n random (forecast, observed 0/1) pairs."""
    return [(rng.random(), float(rng.randint(0, 1))) for _ in range(n)]


def _rand_weighted(rng, n):
    """n random (pred, observed 0/1, weight) triples, weight always > 0."""
    return [(rng.random(), float(rng.randint(0, 1)), rng.uniform(0.01, 5.0))
            for _ in range(n)]


def _rand_triples(rng, n):
    """n random (forecast, observed 0/1, climatology) triples."""
    return [(rng.random(), float(rng.randint(0, 1)), rng.random())
            for _ in range(n)]


class TestWilsonInterval(unittest.TestCase):
    """Source: code/make_demo_graph3.py::wilson."""

    def test_fixture_k5_n10(self):
        # Standard Wilson score interval, z=1.96, p=0.5, n=10:
        #   d = 1 + 1.96^2/10 = 1.38416
        #   centre = (0.5 + 1.96^2/20) / d = 0.5 approx-ish -> 0.5/1.38416-ish
        #   (values below independently reproduced with a calculator using
        #   the same closed-form Wilson formula the function implements)
        self.assertEqual(stats.wilson_interval(5, 10), (0.2366, 0.7634))

    def test_zero_n_returns_full_interval(self):
        self.assertEqual(stats.wilson_interval(0, 0), (0.0, 1.0))

    def test_all_hits(self):
        # k == n: lower bound pulled below 1 by the continuity correction,
        # upper bound clamped at the 1.0 ceiling.
        self.assertEqual(stats.wilson_interval(2, 2), (0.3424, 1.0))

    def test_no_hits(self):
        self.assertEqual(stats.wilson_interval(0, 2), (0.0, 0.6576))

    @requires_originals
    def test_differential(self):
        rng = random.Random(20260813)
        for _ in range(N_TRIALS):
            n = rng.randint(0, 400)
            k = rng.randint(0, n) if n else 0
            z = rng.choice([1.96, 1.645, 2.576, 1.0])
            self.assertEqual(
                stats.wilson_interval(k, n, z), _orig_g3.wilson(k, n, z),
                msg=f"k={k} n={n} z={z}",
            )


class TestTailStats(unittest.TestCase):
    """Source: code/make_demo_graph3.py::tail."""

    def test_fixture(self):
        pairs = [(0.05, 0.0), (0.2, 1.0), (0.08, 1.0), (0.5, 0.0)]
        # below cut=0.10: (0.05, 0.0) and (0.08, 1.0)
        #   pred = (0.05 + 0.08) / 2 = 0.065
        #   obs  = (0.0 + 1.0) / 2  = 0.5
        self.assertEqual(stats.tail_stats(pairs, cut=0.10),
                         {"n": 2, "pred": 0.065, "obs": 0.5})

    def test_nothing_under_cut(self):
        pairs = [(0.5, 0.0), (0.9, 1.0)]
        self.assertEqual(stats.tail_stats(pairs, cut=0.10),
                         {"n": 0, "pred": None, "obs": None})

    def test_empty_input(self):
        self.assertEqual(stats.tail_stats([]), {"n": 0, "pred": None, "obs": None})

    @requires_originals
    def test_differential(self):
        rng = random.Random(202608132)
        for _ in range(N_TRIALS):
            n = rng.randint(0, 300)
            pairs = _rand_pairs(rng, n)
            cut = rng.choice([0.05, 0.10, 0.15, 0.5])
            self.assertEqual(
                stats.tail_stats(pairs, cut), _orig_g3.tail(pairs, cut),
                msg=f"n={n} cut={cut}",
            )


class TestDecilesEqualCount(unittest.TestCase):
    """Source: code/make_demo_graph3.py::series_stats binning."""

    def test_fixture_two_bins_of_two(self):
        pairs = [(0.1, 0.0), (0.2, 0.0), (0.7, 1.0), (0.8, 1.0)]
        # n=4, n_bins=2 -> exact boundaries round(i*4/2): bin0 = pairs[0:2],
        # bin1 = pairs[2:4]. bin0 is fully miscalibrated (pred~0.15, obs 0),
        # bin1 fully calibrated (pred~0.75, obs 1) -- both hand-checkable
        # from the input; lo95/hi95 follow from wilson_interval(hits, n).
        pts = stats.deciles_equal_count(pairs, n_bins=2)
        self.assertEqual(pts, [
            {"pred": 0.15, "obs": 0.0, "n": 2, "lo95": 0.0, "hi95": 0.6576},
            {"pred": 0.75, "obs": 1.0, "n": 2, "lo95": 0.3424, "hi95": 1.0},
        ])

    def test_empty_bins_are_dropped(self):
        # n=3 pairs split into 10 bins: most boundary slices are empty and
        # must be dropped rather than emitted as zero-count points.
        pairs = [(0.1, 0.0), (0.5, 1.0), (0.9, 0.0)]
        pts = stats.deciles_equal_count(pairs, n_bins=10)
        self.assertEqual(len(pts), 3)
        self.assertTrue(all(p["n"] == 1 for p in pts))

    @requires_originals
    def test_differential(self):
        rng = random.Random(2026081303)
        for _ in range(N_TRIALS):
            n = rng.randint(1, 250)
            pairs = _rand_pairs(rng, n)
            got = stats.deciles_equal_count(pairs, n_bins=10)
            want = _orig_g3.series_stats(pairs)["pts"]
            self.assertEqual(got, want, msg=f"n={n}")


class TestDecilesWeighted(unittest.TestCase):
    """Source: code/make_demo_combined.py::wdeciles."""

    def test_fixture(self):
        weighted = [(0.1, 0.0, 1.0), (0.3, 0.0, 1.0),
                    (0.6, 1.0, 2.0), (0.9, 1.0, 2.0)]
        # total weight W=6, n_bins=2 -> step=3.0. Walking in ascending-pred
        # order, cumulative weight is 1, 2, 4, 6 -> the first three rows
        # (cum 0,1,2 all < 3) land in bin0, the last (cum=4 >= 3) in bin1.
        #   bin0: weight 1+1+2=4, pred=(0.1*1+0.3*1+0.6*2)/4=0.4, obs=(0+0+2)/4=0.5
        #   bin1: weight 2, pred=0.9, obs=1.0
        pts = stats.deciles_weighted(weighted, n_bins=2)
        self.assertEqual(len(pts), 2)
        self.assertAlmostEqual(pts[0]["pred"], 0.4)
        self.assertAlmostEqual(pts[0]["obs"], 0.5)
        self.assertEqual(pts[0]["n"], 3)
        self.assertAlmostEqual(pts[1]["pred"], 0.9)
        self.assertAlmostEqual(pts[1]["obs"], 1.0)
        self.assertEqual(pts[1]["n"], 1)

    def test_zero_total_weight_returns_empty(self):
        self.assertEqual(stats.deciles_weighted([(0.5, 1.0, 0.0)]), [])

    @requires_originals
    def test_differential(self):
        rng = random.Random(2026081304)
        for _ in range(N_TRIALS):
            n = rng.randint(1, 250)
            weighted = _rand_weighted(rng, n)
            got = stats.deciles_weighted(weighted, n_bins=10)
            want = _orig_cb.wdeciles(weighted)
            self.assertEqual(got, want, msg=f"n={n}")


class TestBrierMeanAndBss(unittest.TestCase):
    """Source: code/make_demo_combined.py::bss_of, split into its two halves."""

    def test_brier_mean_fixture(self):
        pairs = [(0.2, 0.0), (0.6, 1.0), (0.9, 1.0), (0.1, 0.0)]
        # (0.2-0)^2 + (0.6-1)^2 + (0.9-1)^2 + (0.1-0)^2
        #   = 0.04 + 0.16 + 0.01 + 0.01 = 0.22, / 4 = 0.055
        self.assertAlmostEqual(stats.brier_mean(pairs), 0.055)

    def test_bss_fixture(self):
        # brier=0.055 (as above), clim_brier=0.25 (climatology always
        # predicts 0.5): bss = 1 - 0.055/0.25 = 1 - 0.22 = 0.78
        self.assertEqual(stats.bss(0.055, 0.25), 0.78)

    def test_bss_nonpositive_climatology_is_none(self):
        self.assertIsNone(stats.bss(0.1, 0.0))
        self.assertIsNone(stats.bss(0.1, -0.5))
        self.assertIsNone(stats.bss(0.1, None))

    @requires_originals
    def test_differential_against_bss_of(self):
        rng = random.Random(2026081305)
        for _ in range(N_TRIALS):
            n = rng.randint(1, 200)
            triples = _rand_triples(rng, n)
            want = _orig_cb.bss_of(triples)
            brier = stats.brier_mean([(p, o) for p, o, c in triples])
            clim_brier = stats.brier_mean([(c, o) for p, o, c in triples])
            got = stats.bss(brier, clim_brier)
            self.assertEqual(got, want, msg=f"n={n}")


class TestSpearman(unittest.TestCase):
    """Source: code/make_demo_combined.py::spearman (the copy with an n<2 guard)."""

    def test_perfect_positive_correlation(self):
        self.assertEqual(stats.spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]), 1.0)

    def test_perfect_negative_correlation(self):
        self.assertEqual(stats.spearman([1, 2, 3, 4, 5], [50, 40, 30, 20, 10]), -1.0)

    def test_n_less_than_2_returns_zero(self):
        self.assertEqual(stats.spearman([], []), 0.0)
        self.assertEqual(stats.spearman([1], [2]), 0.0)

    def test_mixed_fixture(self):
        # one adjacent transposition each side: xs ranks [0,1,2,3,4,5],
        # ys=[2,1,4,3,6,5] ranks [1,0,3,2,5,4] -> d = [-1,1,-1,1,-1,1],
        # d2 sum = 6 -> rho = 1 - 6*6/(6*35) = 1 - 36/210 = 174/210
        self.assertAlmostEqual(stats.spearman([1, 2, 3, 4, 5, 6], [2, 1, 4, 3, 6, 5]),
                               174 / 210)

    @requires_originals
    def test_differential(self):
        rng = random.Random(2026081306)
        for _ in range(N_TRIALS):
            n = rng.randint(0, 100)
            xs = [rng.random() for _ in range(n)]
            ys = [rng.random() for _ in range(n)]
            self.assertEqual(stats.spearman(xs, ys), _orig_cb.spearman(xs, ys),
                             msg=f"n={n}")


if __name__ == "__main__":
    unittest.main()
