"""Streaming page recovery remains bounded to the same public report job."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/academyinfo-flow/scripts'
sys.path.insert(0, str(SCRIPTS / 'vendor'))
from academyinfo_archive.direct import Exchange, SourceError
from academyinfo_archive.viewer_data import ViewerDataClient, DATA_URL


def session():
    return SimpleNamespace(_runtime={key: 'synthetic' for key in
        ('cHJvY2lk', 'key', 'ubiserverurl', 'jrffile', 'resid', 'exportseq', 'issvg')},
        _server_url=DATA_URL, _service_id='synthetic',
        selectors={'pubYear': '2026', 'schoolDivision': '02', 'itemId': '1', 'level': 'department'})


def exchange(body=b'<Doc><Page pagenum="5"/></Doc>'):
    return Exchange(url=DATA_URL, method='POST', parameters={}, body=body, status=200,
        content_type='application/xml', fetched_at='2026-10-20T00:00:00+00:00', final_url=DATA_URL)


def source_error(status, *, policy=False):
    error = SourceError('SYNTHETIC_PRIVATE_RESPONSE')
    error.transport_diagnostic = {'http_status': status}
    error.policy_refusal = policy
    return error


class StreamingRecoveryTests(unittest.TestCase):
    def test_transient_server_failures_retry_same_page_twice_then_return_validated_page(self):
        client = ViewerDataClient(interval=0)
        job, page = session(), exchange()
        with patch.object(client, '_runtime_post', side_effect=[source_error(503), source_error(502), (page, '')]) as post, \
                patch('academyinfo_archive.viewer_data.time.sleep') as sleep:
            received = client.fetch_page(job, 5)
        self.assertIs(received, page)
        self.assertEqual(post.call_count, 3)
        self.assertEqual(len(client.page_recovery_events), 2)
        self.assertEqual([event['retry_attempt'] for event in client.page_recovery_events], [1, 2])
        self.assertEqual(sleep.call_count, 2)
        for call in post.call_args_list:
            self.assertEqual(call.args[0], job._server_url)
            self.assertEqual(call.args[1]['reqtype'], '91#5')
            self.assertEqual(call.args[1]['exportseq'], 'synthetic')

    def test_third_server_failure_stops_and_retains_public_stage_and_page(self):
        client = ViewerDataClient(interval=0)
        with patch.object(client, '_runtime_post', side_effect=source_error(503)) as post, \
                patch('academyinfo_archive.viewer_data.time.sleep'):
            with self.assertRaises(SourceError) as raised:
                client.fetch_page(session(), 5)
        self.assertEqual(post.call_count, 3)
        self.assertEqual(raised.exception.requested_page, 5)
        self.assertEqual(raised.exception.source_stage, 'report_page_transport')

    def test_access_refusal_and_policy_error_are_never_retried(self):
        for status, policy in ((403, False), (401, True), (503, True)):
            client = ViewerDataClient(interval=0)
            with self.subTest(status=status, policy=policy), \
                    patch.object(client, '_runtime_post', side_effect=source_error(status, policy=policy)) as post, \
                    patch('academyinfo_archive.viewer_data.time.sleep') as sleep:
                with self.assertRaises(SourceError):
                    client.fetch_page(session(), 5)
                self.assertEqual(post.call_count, 1)
                sleep.assert_not_called()

    def test_wrong_page_is_rejected_without_recovery(self):
        client = ViewerDataClient(interval=0)
        with patch.object(client, '_runtime_post', return_value=(exchange(b'<Doc><Page pagenum="4"/></Doc>'), '')) as post, \
                patch('academyinfo_archive.viewer_data.time.sleep') as sleep:
            with self.assertRaises(SourceError):
                client.fetch_page(session(), 5)
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    def test_blank_page_recheck_rejects_changed_generation_before_retry(self):
        client = ViewerDataClient(interval=0)
        job = session()
        job._last_generation_status = SimpleNamespace(complete=True, expected_pages=10)
        with patch.object(client, '_runtime_post', return_value=(exchange(b''), '')) as post, \
                patch.object(client, 'report_status', return_value=SimpleNamespace(complete=True, expected_pages=11)), \
                patch('academyinfo_archive.viewer_data.time.sleep') as sleep:
            with self.assertRaises(SourceError) as raised:
                client.fetch_page(job, 5)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(raised.exception.source_stage, 'generation_recheck')
        self.assertEqual(raised.exception.requested_page, 5)
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
