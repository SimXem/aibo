"""code/refresh_panel.sh pages a panel change once: whichever job fetches it
first, the AIRO cron or a ForecastBench round.

The script runs from a copy under a temp root, with a stub interpreter whose
panel is $BEFORE until the stub's fetch has run and $AFTER from then on (the
fetched snapshot stays on disk, as data/ does), and a stub curl that records
each page. No model, network or snapshot is touched."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

STUB_PY = r'''#!/usr/bin/env bash
if [ "$1 $2" = "-m redlines.eci" ]; then
    [ -n "${FETCH_FAILS:-}" ] && exit 1
    touch "$FETCHED"; exit 0
fi
if [ "$1 $2" = "-m redlines.autoreg" ]; then echo -n "${ADDED:-}"; exit 0; fi
if [ "$1" = "-c" ]; then
    case "$2" in
        *panel_warnings*) echo -n "${UNRUNNABLE:-}" ;;
        *) if [ -e "$FETCHED" ]; then echo "$AFTER"; else echo "$BEFORE"; fi ;;
    esac
    exit 0
fi
exit 0
'''

STUB_CURL = '#!/usr/bin/env bash\necho "$*" >> "$PAGES"\n'


class TestRefreshPanel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        root, bin_ = t / "repo", t / "bin"
        (root / "code").mkdir(parents=True)
        bin_.mkdir()
        for f in ("refresh_panel.sh", "notify.sh"):
            shutil.copy(ROOT / "code" / f, root / "code" / f)
        self.script = root / "code" / "refresh_panel.sh"
        for path, text in ((t / "py", STUB_PY), (bin_ / "curl", STUB_CURL)):
            path.write_text(text)
            path.chmod(0o755)
        self.pages = t / "pages"
        self.env = {"PATH": f"{bin_}:{os.environ['PATH']}", "HOME": str(t / "home"),
                    "REDLINES_PY": str(t / "py"), "NTFY_TOPIC": "test", "PAGES": str(self.pages),
                    "FETCHED": str(t / "fetched"), "BEFORE": "A, B", "AFTER": "A, B"}

    def tearDown(self):
        self.tmp.cleanup()

    def refresh(self, **env):
        r = subprocess.run(["bash", str(self.script)], env={**self.env, **env},
                           capture_output=True, text=True)
        pages = self.pages.read_text().splitlines() if self.pages.exists() else []
        self.pages.unlink(missing_ok=True)
        return r.returncode, r.stdout, pages

    def test_an_unchanged_panel_pages_nothing(self):
        rc, out, pages = self.refresh()
        self.assertEqual(rc, 0)
        self.assertIn("panel: A, B", out)
        self.assertEqual(pages, [])

    def test_a_changed_panel_pages_once_whoever_fetches_first(self):
        rc, out, pages = self.refresh(AFTER="A, C")
        self.assertEqual(rc, 0)
        self.assertIn("panel: A, C", out)
        self.assertTrue(any("AIRO panel changed" in p for p in pages), pages)
        # The next job's refresh starts from the snapshot the first one fetched.
        _, _, pages = self.refresh(AFTER="A, C")
        self.assertEqual(pages, [])

    def test_a_failed_fetch_pages_and_goes_on(self):
        rc, out, pages = self.refresh(FETCH_FAILS="1")
        self.assertEqual(rc, 0)
        self.assertIn("panel: A, B", out)
        self.assertTrue(any("ECI fetch failed" in p for p in pages), pages)

    def test_a_new_model_pages(self):
        rc, out, pages = self.refresh(ADDED="added Model X as x-1")
        self.assertEqual(rc, 0)
        self.assertIn("added Model X", out)
        self.assertTrue(any("new model joins" in p for p in pages), pages)

    def test_an_unrunnable_model_pages(self):
        _, _, pages = self.refresh(UNRUNNABLE="the index ranks X above the panel's cut but the registry cannot run them")
        self.assertTrue(any("no registry row" in p for p in pages), pages)


if __name__ == "__main__":
    unittest.main()
