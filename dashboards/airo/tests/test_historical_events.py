"""The historical markers must be generated, never edited, and must stay on the
severity axes the question set defines.

Two failure modes this guards, both of which would put a wrong number in front
of a reader with nothing to catch it:

  1. Someone corrects a death toll in the JSON instead of in the generator, and
     the citation in the generator no longer matches the figure on the page.
     test_generated_file_is_current diffs byte-for-byte.

  2. A mark lands on a ladder it has no figure for, or off a chart's axis.
     Until 2026-10-19 the two legs were one axis joined by the ladder's value
     of a statistical life and this file pinned that rate; since the legs are
     asked apart nothing converts, and TestTwoLadders pins that instead.

Run with:  python3 -m unittest tests.test_historical_events -v
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

GEN = REPO / "code" / "make_historical_events.py"
EVENTS = REPO / "data" / "historical_events.json"

from redlines.historical import load_events, markers  # noqa: E402


def load_generator():
    spec = importlib.util.spec_from_file_location("hist_gen", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestGeneratedFile(unittest.TestCase):
    def test_generated_file_is_current(self):
        """Regenerate and diff. A hand-edit to the JSON fails here, by name."""
        gen = load_generator()
        expected = json.dumps(gen.build(), indent=2) + "\n"
        self.assertEqual(
            EVENTS.read_text(), expected,
            f"{EVENTS.name} differs from what {GEN.name} produces. Edit the "
            f"generator — where the citation lives — and re-run it.")

    def test_loads_and_validates(self):
        doc = load_events()
        self.assertTrue(doc["events"])
        self.assertTrue(doc["caveat"].strip())


class TestTwoLadders(unittest.TestCase):
    """Since 2026-10-19 an event is drawn on the ladder(s) it has a figure for,
    and nothing converts between deaths and dollars."""

    def test_every_event_has_a_band_on_at_least_one_ladder(self):
        for e in markers()["events"]:
            self.assertTrue(e["deaths"] or e["damagesUsd"], e["id"])

    def test_covid_is_on_both_ladders_and_notpetya_on_damages_alone(self):
        by = {e["id"]: e for e in markers()["events"]}
        self.assertAlmostEqual(by["covid-19"]["deaths"]["central"], 14.83e6, delta=1)
        self.assertAlmostEqual(by["covid-19"]["damagesUsd"]["central"], 12.5e12, delta=1)
        self.assertIsNone(by["notpetya"]["deaths"])
        self.assertEqual(by["notpetya"]["damagesUsd"]["central"], 10e9)
        for i in ("black-death", "world-war-ii", "black-death-share", "extinction"):
            self.assertIsNone(by[i]["damagesUsd"], i)

    def test_nothing_converts_between_the_ladders(self):
        gen = load_generator()
        self.assertFalse(hasattr(gen, "VSL_USD"))
        self.assertFalse(hasattr(gen, "coordinate"))
        self.assertNotIn("conversion", load_events())
        self.assertNotIn("death-equivalent", markers()["caveat"])

    def test_events_land_inside_the_plotted_axes(self):
        """A band outside a chart's x-domain would render as a sliver at the
        edge and read as a real position. The axes are the ones the chunk
        draws (redlines.questions, carried in the Graph 2 blob)."""
        from redlines.questions import DAMAGES_AXIS, SEVERITY_AXIS
        for e in markers()["events"]:
            for band, axis in ((e["deaths"], SEVERITY_AXIS), (e["damagesUsd"], DAMAGES_AXIS)):
                if not band:
                    continue
                self.assertGreater(band["low"], axis["lo"], f"{e['id']} falls off the left edge")
                self.assertLess(band["high"], axis["hi"], f"{e['id']} falls off the right edge")

    def test_bands_are_ordered_and_positive(self):
        for e in markers()["events"]:
            for band in (e["deaths"], e["damagesUsd"]):
                if not band:
                    continue
                self.assertLessEqual(band["low"], band["central"], e["id"])
                self.assertLessEqual(band["central"], band["high"], e["id"])
                self.assertGreater(band["low"], 0, e["id"])


class TestSourcing(unittest.TestCase):
    def test_every_event_carries_a_citation(self):
        """The whole point of the SSOT: no figure without its source."""
        for e in load_events()["events"]:
            for key in ("org", "title", "url"):
                self.assertTrue(e["source"][key].strip(),
                                f"{e['id']} has an empty source.{key}")
            self.assertTrue(e["source"]["url"].startswith("https://"),
                            f"{e['id']} source url is not https")
            self.assertTrue(e["note"].strip(), f"{e['id']} has no note")
            self.assertTrue(e["verified"], f"{e['id']} has no verified date")

    def test_every_event_has_a_chart_label(self):
        """`short` is what the chart draws; `label` is what the tooltip says."""
        for e in load_events()["events"]:
            self.assertTrue(e["short"].strip(), f"{e['id']} has no short label")
            self.assertLessEqual(len(e["short"]), len(e["label"]), e["id"])
            self.assertLessEqual(len(e["short"]), 16,
                                 f"{e['id']} short label is too long to sit "
                                 f"rotated inside the plot")

    def test_markers_carry_the_caveat(self):
        """The panel renders this. If it can go missing, it will go missing."""
        self.assertIn("NOT", markers()["caveat"])


if __name__ == "__main__":
    unittest.main()
