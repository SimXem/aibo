"""Golden test for `python3 -m redlines assemble`.

For the page (demo -> index.html; timeline.html was folded into it on
2026-09-08), freshly rebuilding its manifest blobs and calling
redlines.pages.hydrate_page must reproduce the TRACKED page file BYTE FOR
BYTE -- the same self-referential-golden idea as tests/test_build_golden.py,
just checked at the whole-page level instead of per-blob. This is what makes
web/<page>/ + the view build()s the full SOURCE of the tracked pages: if
hydrate_page's output ever drifted from the committed page (a chunking bug,
a view regression, a manifest edit that didn't match the page), this test
catches it without needing a second "expected page" fixture to keep in sync
by hand.

The tracked page is committed, so it exists on a fresh clone. What is NOT
guaranteed on a fresh clone is the external data feeding its GRAPH3 and
GRAPH4 blobs:

  * GRAPH3 (redlines.views.graph3) reads processed ForecastBench rounds from
    FB_DATASETS_ROOT, a sibling checkout (see docs/methodology.md).
  * GRAPH4 (redlines.views.graph4) reads FBSIM_ROOT's low-probability
    question set (another sibling checkout) AND results/eval_full.json,
    which is gitignored (regenerated, not tracked) so it is absent right
    after cloning even though the repo itself is complete.

So the test skipTest's cleanly when either input is missing, exactly like
TestGraph3Golden / TestGraph4Golden in test_build_golden.py.

Run with:  python3 -m unittest tests.test_assemble_golden -v   (from the repo root)
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from redlines.pages import hydrate_page  # noqa: E402


def _tracked_bytes(name):
    """Load the tracked page's bytes. It is tracked in git, so a missing
    file here means something is wrong with the checkout -- fail loudly
    rather than skip."""
    path = REPO_ROOT / name
    if not path.exists():
        raise AssertionError(
            f"{path} is missing but should be tracked in git -- "
            f"check `git ls-files {path.relative_to(REPO_ROOT)}`"
        )
    return path.read_bytes()


class TestDemoPageGolden(unittest.TestCase):
    def test_hydrate_page_matches_tracked_page(self):
        # The same blob set `python3 -m redlines assemble` splices in. Graph 3
        # and Graph 4 come from their tracked mirrors when their external
        # inputs are absent (redlines.__main__.g3_blob / g4_blob), so this
        # page-level golden runs on a fresh clone too; the per-view goldens in
        # test_build_golden.py still check the rebuild when the inputs exist.
        from redlines.__main__ import _blobs_for_demo

        html = hydrate_page(REPO_ROOT / "web" / "demo", _blobs_for_demo())
        self.assertEqual(html.encode("utf-8"), _tracked_bytes("index.html"))


if __name__ == "__main__":
    unittest.main()
