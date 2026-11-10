"""Cache behavior in both copies; all network traffic is fake."""
import importlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch


class CacheTests:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tools = importlib.import_module(self.module)
        self.env = patch.dict(os.environ, {
            'TAVILY_API_KEY': 'test-cache-key',
            'FORECASTER_TAVILY_CACHE_DIR': self.tmp.name,
            'FORECASTER_TAVILY_CACHE_TTL': '3600',
            'FORECASTER_BLOCK_URL_PATTERNS': '',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.data = {'answer': 'answer', 'results': [
            {'title': 'Source', 'url': 'https://example.org/a', 'content': 'text'}]}
        net_patch = patch('urllib.request.urlopen', side_effect=self.reply)
        self.net = net_patch.start()
        self.addCleanup(net_patch.stop)

    def reply(self, *a, **kw):
        return io.BytesIO(json.dumps(self.data).encode())

    def test_search_reused_with_current_cause_and_no_mutation(self):
        a = self.tools.web_search('risk', cause='ai')
        a['results'].clear()
        b = self.tools.web_search('risk', cause='bio')
        self.assertEqual(b['cause'], 'bio')
        self.assertEqual(len(b['results']), 1)
        self.assertEqual(self.net.call_count, 1)
        with sqlite3.connect(Path(self.tmp.name) / 'responses.sqlite3') as db:
            dump = '\n'.join(db.iterdump())
        self.assertNotIn('test-cache-key', dump)

    def test_parameters_dates_and_account_partition_cache(self):
        from datetime import date
        self.tools.web_search('risk')
        self.tools.web_search('other')
        self.tools.web_search('risk', max_results=2)
        self.tools.web_search('risk', recent_days=7)
        with patch.object(self.tools, 'date') as day:
            day.today.return_value = date(2040, 1, 1)
            self.tools.web_search('risk', recent_days=7)
        with patch.dict(os.environ, {'TAVILY_API_KEY': 'different'}):
            self.tools.web_search('risk')
        self.assertEqual(self.net.call_count, 6)

    def test_current_guard_applies_on_hit(self):
        self.tools.web_search('risk')
        with patch.dict(os.environ, {'FORECASTER_BLOCK_URL_PATTERNS': 'example.org'}):
            out = self.tools.web_search('risk')
            self.assertEqual(out['results'], [])
            self.assertIsNone(out['answer'])
        self.assertEqual(self.net.call_count, 1)

    def test_whole_page_cached_across_offsets_and_guarded(self):
        self.data = {'results': [{'raw_content': 'x' * 7100}]}
        a = self.tools.read_page('https://example.org/a')
        b = self.tools.read_page('https://example.org/a', a['next_offset'])
        self.assertEqual(len(b['text']), 100)
        self.assertEqual(self.net.call_count, 1)
        with patch.dict(os.environ, {'FORECASTER_BLOCK_URL_PATTERNS': 'example.org'}):
            self.assertIn('error', self.tools.read_page('https://example.org/a'))
        self.assertEqual(self.net.call_count, 1)

    def test_errors_and_empty_extracts_not_cached(self):
        self.net.side_effect = urllib.error.URLError('429')
        self.assertIn('error', self.tools.web_search('risk'))
        self.net.side_effect = self.reply
        self.tools.web_search('risk')
        self.assertEqual(self.net.call_count, 2)
        self.data = {'results': [], 'failed_results': [{'error': 'unavailable'}]}
        for _ in range(2):
            self.assertIn('error', self.tools.read_page('https://example.org/a'))
        self.assertEqual(self.net.call_count, 4)

    def test_expiry_disabled_and_unwritable(self):
        with patch.object(self.tools.time, 'time', return_value=10000):
            self.tools.web_search('risk')
        with patch.object(self.tools.time, 'time', return_value=13601):
            self.tools.web_search('risk')
        self.assertEqual(self.net.call_count, 2)
        with patch.dict(os.environ, {'FORECASTER_TAVILY_CACHE_TTL': '0'}):
            self.tools.web_search('risk')
            self.tools.web_search('risk')
        self.assertEqual(self.net.call_count, 4)
        bad = Path(self.tmp.name) / 'not-a-directory'
        bad.write_text('x')
        with patch.dict(os.environ, {'FORECASTER_TAVILY_CACHE_DIR': str(bad)}):
            self.assertNotIn('error', self.tools.web_search('risk'))
        self.assertEqual(self.net.call_count, 5)

    def test_corrupt_database_fails_open(self):
        (Path(self.tmp.name) / 'responses.sqlite3').write_text('broken')
        self.assertNotIn('error', self.tools.web_search('risk'))
        self.assertEqual(self.net.call_count, 1)

    def test_concurrent_processes_coalesce_miss(self):
        script = '''
import importlib, io, json, os, time
from pathlib import Path
from unittest.mock import patch
tools = importlib.import_module(os.environ['CACHE_TEST_MODULE'])
def fetch(*args, **kwargs):
    with (Path(os.environ['FORECASTER_TAVILY_CACHE_DIR']) / 'calls').open('a') as f:
        f.write('call\\n')
    time.sleep(.2)
    return io.BytesIO(b'{"results": []}')
with patch('urllib.request.urlopen', side_effect=fetch):
    assert 'error' not in tools.web_search('concurrent')
'''
        env = dict(os.environ, CACHE_TEST_MODULE=self.module)
        procs = [subprocess.Popen([sys.executable, '-c', script], env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(6)]
        for proc in procs:
            _, err = proc.communicate(timeout=20)
            self.assertEqual(proc.returncode, 0, err.decode())
        self.assertEqual((Path(self.tmp.name) / 'calls').read_text(), 'call\n')


class AiroCacheTests(CacheTests, unittest.TestCase):
    module = 'redlines.tools'


class ForecasterCacheTests(CacheTests, unittest.TestCase):
    module = 'fri_forecaster.tools'
