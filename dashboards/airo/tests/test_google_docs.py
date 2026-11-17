"""Guardrails for writes to collaboratively edited Google documents."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'code/google_docs.py'
spec = importlib.util.spec_from_file_location('google_docs', MODULE)
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


class TestGoogleDocsWrites(unittest.TestCase):
    def test_changed_revision_never_posts(self):
        with patch.object(docs, 'fetch', return_value={'revisionId': 'new'}), \
             patch.object(docs, 'request_json') as post:
            with self.assertRaisesRegex(RuntimeError, 'changed since review'):
                docs.apply('document', {'writeControl': {'requiredRevisionId': 'old'}, 'requests': [{}]})
            post.assert_not_called()

    def test_no_unconditional_or_merge_writes(self):
        for control in ({}, {'targetRevisionId': 'old'},
                        {'requiredRevisionId': 'old', 'targetRevisionId': 'old'}):
            with patch.object(docs, 'request_json') as post:
                with self.assertRaises(ValueError):
                    docs.apply('document', {'writeControl': control, 'requests': [{}]})
                post.assert_not_called()

    def test_revision_still_sent_for_atomic_server_check(self):
        batch = {'writeControl': {'requiredRevisionId': 'reviewed'}, 'requests': [{}]}
        with patch.object(docs, 'fetch', return_value={'revisionId': 'reviewed'}), \
             patch.object(docs, 'access_token', return_value='test-token'), \
             patch.object(docs, 'request_json', return_value={'replies': [{}]}) as post:
            docs.apply('document', batch)
            self.assertEqual(post.call_args.kwargs['payload'], batch)
            self.assertEqual(post.call_count, 1)

    def test_token_file_is_private_even_when_replacing_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'token.json'
            destination.write_text('{}')
            destination.chmod(0o644)
            docs.private_write(destination, {'placeholder': True})
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

    def test_document_url_cannot_change_api_host(self):
        self.assertEqual(docs.document_id('https://docs.google.com/document/d/abc-123/edit?tab=t.x'), 'abc-123')
        with self.assertRaises(ValueError):
            docs.document_id('https://example.com/unrelated')


if __name__ == '__main__':
    unittest.main()
