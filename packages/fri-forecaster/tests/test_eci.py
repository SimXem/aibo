"""fri_forecaster.eci: dated snapshots in a directory, the published format
fetched and refused when it does not look like the index, the ranking, the
frontier history, and the CLI a round's eci_ranked can be."""
import csv
import io
import tempfile
import unittest
import urllib.request
from datetime import date
from pathlib import Path

from fri_forecaster import eci

HEADER = ["Model", "Display name", "eci", "eci_ci_low", "eci_ci_high", "date",
          "Organization", "Country (of organization)", "Model accessibility",
          "Accessibility group", "model_versions"]


def published(rows):
    """Epoch's published format: rows are (model, eci, date, country)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADER)
    for m, e, d, c in rows:
        w.writerow([m, m, e, e - 3 if e != "" else "", e + 3 if e != "" else "", d, "Lab", c, "API", "Closed", ""])
    return buf.getvalue()


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class EciTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.real = urllib.request.urlopen
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(setattr, urllib.request, "urlopen", self.real)

    def serve(self, text):
        urllib.request.urlopen = lambda *a, **k: Resp(text.encode())

    def test_fetch_writes_a_dated_snapshot_and_refuses_a_bad_download(self):
        good = published([(f"M{i}", 100 + i, "2025-01-01", eci.US) for i in range(eci.MIN_SCORED)])
        self.serve(good)
        path = eci.fetch(today=date(2026, 10, 1), snapshot_dir=self.dir)
        self.assertEqual(path, self.dir / "epoch_capabilities_index_2026-10-01.csv")
        self.assertEqual(eci.latest(self.dir), (date(2026, 10, 1), path))
        self.assertEqual(eci.latest_published(self.dir)[1], path)
        for bad in (good.splitlines()[0] + "\n" + "\n".join(good.splitlines()[1:10]), "Model,eci\nA,1\n"):
            self.serve(bad)
            with self.assertRaises(ValueError):
                eci.fetch(today=date(2026, 10, 2), snapshot_dir=self.dir)
        self.assertEqual([d for d, _ in eci.snapshots(self.dir)], [date(2026, 10, 1)])
        top = eci.ranked(path)
        self.assertEqual(top[0]["model"], f"M{eci.MIN_SCORED - 1}")
        self.assertEqual([r["rank"] for r in top[:3]], [1, 2, 3])

    def test_snapshots_sort_by_date_and_ignore_strays(self):
        for day in ("2026-02-01", "2026-01-01"):
            (self.dir / f"{eci.SNAPSHOT_PREFIX}{day}.csv").write_text(published([("A", 150, day, eci.US)]))
        (self.dir / f"{eci.SNAPSHOT_PREFIX}notes.csv").write_text("x")
        self.assertEqual([d.isoformat() for d, _ in eci.snapshots(self.dir)], ["2026-01-01", "2026-02-01"])
        self.assertEqual(eci.age_days(date(2026, 2, 11), self.dir), 10)
        self.assertIsNone(eci.stale_message(date(2026, 2, 1), self.dir))
        self.assertIn("days old", eci.stale_message(date(2026, 4, 1), self.dir))
        with self.assertRaises(FileNotFoundError):
            eci.latest(self.dir / "empty")

    def test_frontier_is_new_highs_in_release_order(self):
        p = self.dir / "x.csv"
        p.write_text(published([("Old", 150, "2022-01-01", eci.US), ("Below", 149, "2023-05-01", eci.US),
                                ("First", 151, "2023-06-01", eci.US), ("Foreign", 170, "2023-07-01", "China"),
                                ("SameDayLow", 152, "2024-01-01", eci.US), ("SameDayHigh", 153, "2024-01-01", eci.US),
                                ("Later", 152.5, "2024-02-01", eci.US)]))
        self.assertEqual([m for _, _, m in eci.frontier_history(p, since="2023-03-01")],
                         ["First", "SameDayLow", "SameDayHigh"])

    def test_cli_names_are_the_top_k_best_first(self):
        self.serve(published([(f"M{i}", 100 + i, "2025-01-01", eci.US) for i in range(eci.MIN_SCORED)]))
        out = io.StringIO()
        import contextlib
        with contextlib.redirect_stdout(out):
            rc = eci.main(["--dir", str(self.dir), "--fetch", "--names", "3"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().split(), [f"M{eci.MIN_SCORED - 1}", f"M{eci.MIN_SCORED - 2}", f"M{eci.MIN_SCORED - 3}"])
        self.assertEqual(eci.main(["--dir", str(self.dir / "none")]), 1)      # nothing fetched there


if __name__ == "__main__":
    unittest.main()
