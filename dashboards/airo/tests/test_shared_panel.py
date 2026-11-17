"""AIRO reads its panel and its Baseline condition from the harness (fri_forecaster.panel,
fri_forecaster.baseline), where other dashboards read them too: these pin that the two agree."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO, REPO.parents[1] / "packages" / "forecaster"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from fri_forecaster import baseline, panel  # noqa: E402


class TestSharedWithAiro(unittest.TestCase):
    def test_airo_rows_are_the_shared_rows(self):
        from redlines import registry
        hand = [m for m in registry.MODELS if not m.get("auto")]
        self.assertEqual([(m["key"], m["family"], m["label"], m["litellm_id"], m["epoch_name"]) for m in hand],
                         [tuple(m[f] for f in panel._FIELDS) for m in panel.MODELS])
        self.assertEqual(registry.PANEL_K, panel.PANEL_K)

    def test_airo_minimal_instrument_is_the_baseline_condition(self):
        sys.path.insert(0, str(REPO / "code"))
        import run_unified as ru
        self.assertEqual((ru.MINIMAL_SYSTEM, ru.MINIMAL_MAX_TURNS), (baseline.SYSTEM, baseline.MAX_TURNS))
        airo = ru.minimal_tools(ru.research_tools([{"key": "a", "label": "A"}])[0])
        self.assertEqual([{k: t[k] for k in ("name", "description", "parameters")} for t in airo], baseline.research_tools())


if __name__ == "__main__":
    unittest.main()
