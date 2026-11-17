"""Tests for the XPT quantity -> probability conversion (redlines/xpt.py).

Two layers, neither of which needs the 18 MB upstream panel:

  * the METHOD, against hand-computed ladders -- interpolation, both bound
    kinds, malformed input, and the censoring rule that decides whether a
    group median is a point estimate or only a bound;
  * the VENDORED NUMBERS in data/starter_questions.json -- present for every
    quantity question at every elicited horizon, self-consistent, and with
    panel sizes matching the n_super/n_expert the same file already records
    from the same source.

Reproducing the vendored numbers FROM the panel is a separate, heavier check
that needs the download; that one lives in the build script:

    python3 code/xpt_build_exceedance.py --fetch --check

Run with:  python3 -m unittest tests.test_xpt -v   (from the repo root)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from redlines.questions import load_starter                      # noqa: E402
from redlines.xpt import (BOUND_LOWER, BOUND_UPPER, INTERP,      # noqa: E402
                          format_percent, group_exceedance, p_at_least)


def ladder(*counts):
    """A percentile ladder from five counts, lowest percentile first."""
    return dict(zip(("5th %", "25th %", "50th %", "75th %", "95th %"), counts))


class TestPAtLeast(unittest.TestCase):
    def test_threshold_at_the_median_gives_one_half(self):
        # 50th percentile is exactly 1 event: half the forecaster's mass is at
        # or above 1, so P(N >= 1) = 0.5 exactly, no interpolation needed.
        p, kind = p_at_least(ladder(0, 0.2, 1, 3, 20))
        self.assertEqual(kind, INTERP)
        self.assertAlmostEqual(p, 0.5)

    def test_interpolates_between_bracketing_percentiles(self):
        # 1 sits midway between the 25th (0) and 50th (2) percentiles, so
        # F(1) = 0.25 + (0.50-0.25) * (1-0)/(2-0) = 0.375.
        p, kind = p_at_least(ladder(0, 0, 2, 5, 30))
        self.assertEqual(kind, INTERP)
        self.assertAlmostEqual(p, 1 - 0.375)

    def test_whole_ladder_below_threshold_is_an_upper_bound(self):
        p, kind = p_at_least(ladder(0, 0, 0.01, 0.1, 0.4))
        self.assertEqual(kind, BOUND_UPPER)
        self.assertAlmostEqual(p, 0.05)

    def test_whole_ladder_above_threshold_is_a_lower_bound(self):
        p, kind = p_at_least(ladder(2, 4, 9, 20, 100))
        self.assertEqual(kind, BOUND_LOWER)
        self.assertAlmostEqual(p, 0.95)

    def test_flat_bracket_takes_the_lower_percentile(self):
        # 25th == 50th == 1: the tightest defensible statement is F(1) = 0.25.
        p, kind = p_at_least(ladder(0, 1, 1, 4, 10))
        self.assertEqual(kind, INTERP)
        self.assertAlmostEqual(p, 0.75)

    def test_incomplete_ladder_raises(self):
        with self.assertRaises(ValueError):
            p_at_least({"5th %": 0, "50th %": 1})

    def test_non_monotonic_ladder_raises(self):
        with self.assertRaises(ValueError):
            p_at_least(ladder(0, 5, 1, 6, 9))


class TestGroupExceedance(unittest.TestCase):
    def test_median_across_forecasters(self):
        got = group_exceedance([ladder(0, 0.2, 1, 3, 20),      # 0.50
                                ladder(0, 0, 2, 5, 30),        # 0.625
                                ladder(0, 0, 0.5, 1, 4)])      # 0.25
        self.assertIsNone(got["censored"])
        self.assertAlmostEqual(got["p"], 0.50)
        self.assertEqual(got["n"], 3)
        self.assertEqual(got["n_bounded"], 0)

    def test_minority_of_bounds_does_not_censor_the_median(self):
        # Two bounded forecasters sort below the three interpolated ones, so
        # the median is still a real estimate -- bounds are order-correct.
        got = group_exceedance([ladder(0, 0, 0, 0.1, 0.5),     # bound <= 0.05
                                ladder(0, 0, 0, 0.2, 0.9),     # bound <= 0.05
                                ladder(0, 0, 0.5, 1, 4),       # 0.25
                                ladder(0, 0.2, 1, 3, 20),      # 0.50
                                ladder(0, 0, 2, 5, 30)])       # 0.625
        self.assertIsNone(got["censored"])
        self.assertAlmostEqual(got["p"], 0.25)
        self.assertEqual(got["n_bounded"], 2)

    def test_majority_of_bounds_censors_the_median(self):
        got = group_exceedance([ladder(0, 0, 0, 0.1, 0.5),
                                ladder(0, 0, 0, 0.2, 0.9),
                                ladder(0, 0, 0, 0.05, 0.3),
                                ladder(0, 0.2, 1, 3, 20),
                                ladder(0, 0, 2, 5, 30)])
        self.assertEqual(got["censored"], "upper")
        self.assertAlmostEqual(got["p"], 0.05)

    def test_lower_censoring_is_reported_separately(self):
        got = group_exceedance([ladder(2, 4, 9, 20, 100),
                                ladder(1, 3, 8, 15, 60),
                                ladder(0, 0, 0.5, 1, 4)])
        self.assertEqual(got["censored"], "lower")
        self.assertAlmostEqual(got["p"], 0.95)

    def test_even_group_is_censored_only_if_both_central_entries_are(self):
        got = group_exceedance([ladder(0, 0, 0, 0.1, 0.5),     # bound
                                ladder(0, 0, 0, 0.2, 0.9),     # bound
                                ladder(0, 0, 0.5, 1, 4),       # 0.25
                                ladder(0, 0.2, 1, 3, 20)])     # 0.50
        self.assertIsNone(got["censored"])

    def test_unusable_ladders_are_skipped(self):
        got = group_exceedance([{"5th %": 0}, ladder(0, 0.2, 1, 3, 20)])
        self.assertEqual(got["n"], 1)

    def test_empty_group_is_none(self):
        self.assertIsNone(group_exceedance([]))


class TestFormatPercent(unittest.TestCase):
    def test_point_estimate(self):
        self.assertEqual(format_percent({"p": 0.5, "censored": None}), "50.0%")

    def test_bounds_carry_their_sign(self):
        self.assertEqual(format_percent({"p": 0.05, "censored": "upper"}), "<5.0%")
        self.assertEqual(format_percent({"p": 0.95, "censored": "lower"}), ">95.0%")

    def test_none_passes_through(self):
        self.assertIsNone(format_percent(None))


class TestVendoredBlocks(unittest.TestCase):
    """The derived values committed in data/starter_questions.json."""

    @classmethod
    def setUpClass(cls):
        cls.quantity = [q for q in load_starter() if q.get("value_kind") == "quantity"]

    def test_every_quantity_question_has_a_block(self):
        self.assertTrue(self.quantity, "expected quantity questions in the starter set")
        for q in self.quantity:
            self.assertIn("xpt_exceedance", q, q["id"])
            self.assertIn("source", q["xpt_exceedance"], q["id"])
            self.assertEqual(q["xpt_exceedance"]["threshold"], 1.0, q["id"])

    def test_every_elicited_horizon_is_covered_for_both_groups(self):
        for q in self.quantity:
            for h in q["horizons"]:
                entry = q["xpt_exceedance"].get(str(h))
                self.assertIsNotNone(entry, f"{q['id']} @ {h}")
                for group in ("super", "expert"):
                    self.assertIn(group, entry, f"{q['id']} @ {h}")

    def test_values_are_well_formed(self):
        for q in self.quantity:
            for h in q["horizons"]:
                for group, e in q["xpt_exceedance"][str(h)].items():
                    where = f"{q['id']} @ {h} {group}"
                    self.assertGreaterEqual(e["p"], 0.0, where)
                    self.assertLessEqual(e["p"], 1.0, where)
                    self.assertIn(e["censored"], (None, "upper", "lower"), where)
                    self.assertGreater(e["n"], 0, where)
                    self.assertLessEqual(e["n_bounded"], e["n"], where)
                    # A censored median means the bound sits at the ladder's
                    # outermost percentile, by construction.
                    if e["censored"] == "upper":
                        self.assertAlmostEqual(e["p"], 0.05, msg=where)
                    if e["censored"] == "lower":
                        self.assertAlmostEqual(e["p"], 0.95, msg=where)

    def test_panel_sizes_match_the_medians_from_the_same_source(self):
        # n_super/n_expert were computed from the same isCurrent rows of the
        # same pinned panel, so the exceedance panel at the gap year must be
        # the same set of forecasters.
        for q in self.quantity:
            e = q["xpt_exceedance"][str(q["gap_year"])]
            self.assertEqual(e["super"]["n"], q["n_super"], q["id"])
            self.assertEqual(e["expert"]["n"], q["n_expert"], q["id"])

    def test_exceedance_is_non_decreasing_over_horizons(self):
        # These are cumulative "by end of YEAR" questions, so a later horizon
        # cannot be less likely. Bounds are compared at their bound value,
        # which is the only ordering they license.
        for q in self.quantity:
            for group in ("super", "expert"):
                ps = [q["xpt_exceedance"][str(h)][group]["p"] for h in q["horizons"]]
                self.assertEqual(ps, sorted(ps), f"{q['id']} {group}: {ps}")


if __name__ == "__main__":
    unittest.main()
