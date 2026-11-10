"""Publication must retain ordering and selection while bounding history memory."""
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from redlines.conditional import latest_conditional, load_conditional, newest_protocol
from redlines.export import _sorted_csv
from redlines.instrument import CURRENT_INSTRUMENT, instrument_rows
from redlines.runlog import elicitation_date


class TestPublicationMemory(unittest.TestCase):
    def test_export_does_not_collect_the_source_history(self):
        from redlines.export import _published_rows

        def history():
            yield {'question_id': 'first'}
            raise AssertionError('history was read ahead instead of streamed')

        with patch('redlines.export.iter_runlog', side_effect=history):
            rows = _published_rows()
            self.assertEqual(next(rows), {'question_id': 'first'})
            rows.close()

    def test_disk_sort_matches_stable_python_csv_bytes(self):
        rows = [
            {'key': 'é', 'value': 'comma, quote" and\nnewline'},
            {'key': 'a', 'value': None},
            {'key': 'a', 'value': 0.1234567890123456},
            {'key': '😀', 'value': 'unicode'},
            {'key': '', 'value': False},
        ]
        expected = io.StringIO(newline='')
        writer = csv.DictWriter(expected, fieldnames=['key', 'value'])
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: row['key']))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'export.csv'
            self.assertEqual(_sorted_csv(iter(rows), out, ['key', 'value'], ['key']), len(rows))
            self.assertEqual(out.read_bytes(), expected.getvalue().encode())
            self.assertEqual(list(Path(d).iterdir()), [out])
            self.assertEqual(_sorted_csv(iter(()), out, ['key', 'value'], ['key']), 0)
            self.assertEqual(out.read_bytes(), b'key,value\r\n')

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux address-space limit')
    def test_large_export_completes_under_memory_limit(self):
        # The generated history is over 160 MiB; retaining all rows or sorted
        # output in memory cannot fit under this 96 MiB address-space limit.
        script = '''
import resource, sys
from pathlib import Path
from redlines.export import _sorted_csv
resource.setrlimit(resource.RLIMIT_AS, (96 * 1024**2, 96 * 1024**2))
rows = ({'key': f'{20000-i:06d}', 'value': str(i) + 'x' * 8192} for i in range(20000))
assert _sorted_csv(rows, Path(sys.argv[1]), ['key','value'], ['key']) == 20000
'''
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'large.csv'
            result = subprocess.run([sys.executable, '-c', script, str(out)],
                                    text=True, capture_output=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stderr)
            with out.open() as fh:
                rows = csv.DictReader(fh)
                first = next(rows)
                self.assertEqual(first['key'], '000001')
                for last in rows:
                    pass
                self.assertEqual(last['key'], '020000')

    def test_latest_selection_matches_existing_day_and_protocol_rules(self):
        protocols = ('new', 'old')
        def row(day, proto, **extra):
            return dict(run_date=day, elicited_at=day + 'T12:00:00Z',
                        instrument_version=CURRENT_INSTRUMENT, protocol=proto,
                        forecasts=[], experiment='airo', **extra)
        rows = [row('2026-10-28', 'old'), row('2026-10-21', 'new'),
                row('2026-10-23', 'new'), row('2026-10-23', 'new', call_id='second'),
                row('2026-10-29', 'new', pooled=False),
                {**row('2026-10-30', 'new'), 'instrument_version': 'obsolete'},
                row('2026-10-31', 'unknown')]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'log.jsonl'
            path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
            eligible = instrument_rows(load_conditional(path, 'airo'))
            for prefer in (False, True):
                selected = [r for r in eligible if r['protocol'] in protocols]
                if prefer:
                    selected, _ = newest_protocol(selected, protocols)
                day = max(elicitation_date(r) for r in selected)
                selected = [r for r in selected if elicitation_date(r) == day]
                selected, _ = newest_protocol(selected, protocols)
                self.assertEqual(latest_conditional(path, protocols, 'airo', prefer_protocol=prefer), selected)
