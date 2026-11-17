"""Replicate pooling: redlines.runlog.pool / latest_pooled and the Timeline's
re-run band (redlines.views.timeline.rerun_band, noise_floor).

From 2026-08-28 the weekly run asks each model three times (code/cron_run.sh,
--unconditional 3). These tests pin the contract every view relies on:

  * one draw pools to itself, exactly -- the 2026-08-18 / 08-21 numbers must
    not move by a rounding step when the pooling path replaces latest-row-wins;
  * several draws pool to their mean, keep every raw draw, and count both the
    calls made and the calls that answered;
  * latest_pooled() takes the newest DATE per (question, model) and pools all
    of that date, never one arbitrary call from it;
  * the band is None with a single draw and spans the replicate-wise panel
    medians otherwise.

Run with:  python3 -m unittest tests.test_replicates -v   (from the repo root)
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from redlines.runlog import latest_pooled, pool  # noqa: E402
from redlines.views.timeline import noise_floor, rerun_band  # noqa: E402


def row(q, label, day, k, fcs, arm=None):
    return {
        "question_id": q, "label": label, "run_id": f"{day}T1200Z",
        "elicited_at": f"{day}T12:0{k}:00+00:00",
        "call_id": f"{day}T1200Z:{arm + ':' if arm else ''}{label}", "arm": arm,
        "forecasts": [{"horizon": h, "probability": p} for h, p in fcs.items()],
        "rationale": f"r{k}",
    }


class TestPool(unittest.TestCase):
    def test_single_draw_is_identity(self):
        r = row("q", "M", "2026-08-21", 0, {"2030": 0.07, "2050": 0.19})
        p = pool([r])
        self.assertEqual(p["forecasts"], r["forecasts"])
        self.assertEqual(p["replicates"], 1)
        self.assertEqual(p["answered"], 1)
        self.assertEqual(p["draws"], {"2030": [0.07], "2050": [0.19]})

    def test_three_draws_pool_to_mean_and_keep_draws(self):
        rs = [row("q", "M", "2026-08-28", k, {"2030": p}, arm=f"unconditional#{k + 1}")
              for k, p in enumerate([0.19, 0.72, 0.93])]
        p = pool(rs[::-1])  # order of arrival must not matter
        self.assertEqual(p["draws"], {"2030": [0.19, 0.72, 0.93]})
        self.assertAlmostEqual(p["forecasts"][0]["probability"], (0.19 + 0.72 + 0.93) / 3)
        self.assertEqual((p["replicates"], p["answered"]), (3, 3))
        self.assertEqual(p["rationale"], "r2")  # scalars come from the last draw

    def test_declined_draw_counts_as_a_call_not_an_answer(self):
        rs = [row("q", "M", "2026-08-28", 0, {"2030": 0.2}, arm="unconditional#1"),
              row("q", "M", "2026-08-28", 1, {}, arm="unconditional#2")]
        p = pool(rs)
        self.assertEqual((p["replicates"], p["answered"]), (2, 1))
        self.assertEqual(p["forecasts"], [{"horizon": "2030", "probability": 0.2}])


class TestLatestPooled(unittest.TestCase):
    def test_newest_date_pooled_whole(self):
        rows = [row("q", "M", "2026-08-21", 0, {"2030": 0.5})]
        rows += [row("q", "M", "2026-08-28", k, {"2030": p}, arm=f"unconditional#{k + 1}")
                 for k, p in enumerate([0.1, 0.2, 0.6])]
        rows += [row("q", "N", "2026-08-21", 0, {"2030": 0.9})]
        out = latest_pooled(rows)
        self.assertAlmostEqual(out[("q", "M")]["forecasts"][0]["probability"], 0.3)
        self.assertEqual(out[("q", "M")]["replicates"], 3)
        self.assertEqual(out[("q", "N")]["forecasts"][0]["probability"], 0.9)
        self.assertEqual(out[("q", "N")]["replicates"], 1)


class TestRerunBand(unittest.TestCase):
    def test_none_without_replicates(self):
        self.assertIsNone(rerun_band([[5.0], [7.0], [9.0]]))
        self.assertIsNone(rerun_band([]))

    def test_spans_replicate_wise_medians(self):
        # draw 1 medians: median(1, 5, 9) = 5; draw 2: median(3, 7, 11) = 7
        self.assertEqual(rerun_band([[1.0, 3.0], [5.0, 7.0], [9.0, 11.0]]), [5.0, 7.0])

    def test_short_model_drops_out_of_later_medians(self):
        # draw 2 only has two models: median(7, 11) = 9
        self.assertEqual(rerun_band([[1.0], [5.0, 7.0], [9.0, 11.0]]), [5.0, 9.0])


class TestNoiseFloor(unittest.TestCase):
    def test_none_until_a_replicated_date_exists(self):
        by_day = {("2026-08-21", "q", "M"): pool([row("q", "M", "2026-08-21", 0, {"2030": 0.5})])}
        self.assertIsNone(noise_floor(by_day, ["2026-08-21"]))

    def test_pairwise_differences_on_latest_replicated_date(self):
        reps = [row("q", "M", "2026-08-28", k, {"2030": p}, arm=f"unconditional#{k + 1}")
                for k, p in enumerate([0.10, 0.20, 0.60])]
        by_day = {("2026-08-21", "q", "M"): pool([row("q", "M", "2026-08-21", 0, {"2030": 0.5})]),
                  ("2026-08-28", "q", "M"): pool(reps)}
        nf = noise_floor(by_day, ["2026-08-21", "2026-08-28"])
        # |10-20|, |10-60|, |20-60| = 10, 50, 40 pp
        self.assertEqual(nf["date"], "2026-08-28")
        self.assertEqual((nf["draws"], nf["cells"]), (3, 1))
        self.assertEqual((nf["median"], nf["max"]), (40.0, 50.0))


if __name__ == "__main__":
    unittest.main()
