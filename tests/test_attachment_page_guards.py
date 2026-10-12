"""Raw-only attachment pages must not be confused with empty numeric tables."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/academyinfo-flow/scripts/vendor'))
from academyinfo_archive.report_tables import ReportParseError, combine_report_pages, parse_report_xml
from test_live_report import FakeViewerClient, command, report


def listing_page(file_name):
    # Source-provided hyperlink protocol, synthetic file name and campus label.
    return ('<Doc enableNoPage="true" pagecount="1"><Page pagenum="1">'
            '<Item classname="UbiTextItem" x="0" y="0" width="300" height="20" '
            'linkfilename="fn_hLink(&quot;fp=/infofile/PDF_UPLOAD/PBNF_ITEM_UPLOAD/2026/01/1/'
            '&amp;fn=' + file_name + '&amp;sn=synthetic&quot;, '
            '&quot;https://academyinfo.go.kr/#spl#' + file_name + '&quot;, &quot;test&quot;)">'
            '<Text border="1">' + file_name + '</Text></Item></Page></Doc>').encode('utf-8')


class AttachmentPageTests(unittest.TestCase):
    def test_distinct_raw_only_pdf_list_pages_can_cover_two_pages(self):
        originals = [listing_page('synthetic-a.pdf'), listing_page('synthetic-b.pdf')]
        pages = [parse_report_xml(raw, source_page_index=index, metadata=None)
                 for index, raw in enumerate(originals)]
        before = copy.deepcopy(pages)
        combined = combine_report_pages(pages, expected_pages=2)
        self.assertEqual(combined['status'], 'raw_only')
        self.assertEqual(combined['rows'], [])
        self.assertTrue(combined['coverage']['complete'])
        self.assertEqual(pages, before)
        self.assertEqual([page['source_sha256'] for page in combined['pages']],
                         [hashlib.sha256(raw).hexdigest() for raw in originals])

    def test_same_original_raw_only_page_still_rejected(self):
        raw = listing_page('synthetic-a.pdf')
        pages = [parse_report_xml(raw, source_page_index=index, metadata=None) for index in range(2)]
        with self.assertRaises(ReportParseError):
            combine_report_pages(pages, expected_pages=2)

    def test_attachments_collects_distinct_pdf_links_without_numeric_body(self):
        client = FakeViewerClient(1, {})
        client.page_bodies = [listing_page('synthetic-a.pdf'), listing_page('synthetic-b.pdf')]
        with patch.object(report, 'ViewerDataClient', return_value=client):
            result = report.run_command(command(command='attachments'))
        self.assertEqual(result['status'], 'ok')
        self.assertTrue(result['complete'])
        self.assertTrue(result['completeness']['listing_complete'])
        self.assertFalse(result['completeness']['pdf_content_extracted'])
        self.assertFalse(result['completeness']['pdf_content_validation_complete'])
        self.assertEqual([row['parameters']['fileName'] for row in result['rows']],
                         ['synthetic-a.pdf', 'synthetic-b.pdf'])

    def test_attachments_repeated_original_is_error_with_hashes_preserved(self):
        client = FakeViewerClient(1, {})
        raw = listing_page('synthetic-a.pdf')
        client.page_bodies = [raw, raw]
        with patch.object(report, 'ViewerDataClient', return_value=client):
            result = report.run_command(command(command='attachments'))
        self.assertEqual(result['status'], 'error')
        self.assertFalse(result['complete'])
        self.assertFalse(result['completeness']['source_complete'])
        self.assertEqual(result['rows'], [])
        hashes = [source['raw_sha256'] for source in result['sources'] if source.get('source_request_page')]
        self.assertEqual(hashes, [hashlib.sha256(raw).hexdigest()] * 2)


if __name__ == '__main__':
    unittest.main()
