"""Synthetic live-boundary checks; no source queries, statistics or sessions saved."""
import hashlib
import unittest
from unittest.mock import patch

from test_live_report import FakeViewerClient, command, report


class ValidationBoundaryTests(unittest.TestCase):
    def run_source(self, *, expected_identity=None, repeat_body=False, repeat_xml=False):
        client = FakeViewerClient(1, {})
        if repeat_xml:
            client.page_bodies[1] = client.page_bodies[0]
        elif repeat_body:
            client.page_bodies[1] = client.page_bodies[0].replace(b'<Doc ', b'<Doc different="synthetic" ')
        original_start = client.start_report

        def start(*args, **kwargs):
            session = original_start(*args, **kwargs)
            if expected_identity is not None:
                session.schema_identity = expected_identity
            return session

        with patch.object(client, 'start_report', side_effect=start), patch.object(report, 'ViewerDataClient', return_value=client):
            result = report.run_command(command())
        return result, client

    def assert_unverified(self, result, client):
        self.assertEqual(result['status'], 'error')
        self.assertFalse(result['complete'])
        self.assertFalse(result['completeness']['source_complete'])
        self.assertEqual(result['rows'], [])
        self.assertTrue(client.sessions[0].closed)
        self.assertEqual(client.sessions[0]._runtime, {})
        xml_sources = [source for source in result['sources'] if source.get('source_request_page')]
        self.assertEqual(xml_sources[0]['raw_sha256'], hashlib.sha256(client.page_bodies[0]).hexdigest())
        self.assertNotIn('SYNTHETIC_PRIVATE', str(result))

    def test_bootstrap_master_identity_conflict_preserves_hash_and_never_projects_rows(self):
        for master in ('another-template', '', 'null', 'undefined'):
            with self.subTest(master=master):
                result, client = self.run_source(expected_identity={'item_mstr_id': master})
                self.assert_unverified(result, client)
                self.assertEqual(result['metadata_validation']['status'], 'failed')

    def test_bootstrap_form_conflict_preserves_metadata_before_source_close(self):
        client = FakeViewerClient(1, {})
        for section in ('master', 'body', 'header'):
            for row in client.metadata[section]:
                row['form_clft_cd'] = '36'
        original_start = client.start_report

        def start(*args, **kwargs):
            session = original_start(*args, **kwargs)
            session.schema_identity = {'form_clft_cd': '30'}
            return session

        with patch.object(client, 'start_report', side_effect=start), patch.object(report, 'ViewerDataClient', return_value=client):
            result = report.run_command(command())
        self.assert_unverified(result, client)
        self.assertIn('form_clft_cd=36', client.sessions[0].schema_text['resultMaster'])

    def test_bootstrap_form_must_match_selector_even_when_metadata_form_is_absent(self):
        result, client = self.run_source(expected_identity={'form_clft_cd': '30'})
        self.assert_unverified(result, client)
        self.assertEqual(result['metadata_validation']['status'], 'failed')

    def test_repeated_xml_never_becomes_complete_report_even_when_request_indices_cover_total(self):
        result, client = self.run_source(repeat_xml=True)
        self.assert_unverified(result, client)
        hashes = [source['raw_sha256'] for source in result['sources'] if source.get('source_request_page')]
        self.assertEqual(hashes[0], hashes[1])

    def test_changed_doc_wrapper_with_same_body_never_becomes_complete_report(self):
        result, client = self.run_source(repeat_body=True)
        self.assert_unverified(result, client)
        hashes = [source['raw_sha256'] for source in result['sources'] if source.get('source_request_page')]
        self.assertNotEqual(hashes[0], hashes[1])


if __name__ == '__main__':
    unittest.main()
