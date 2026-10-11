"""Guide batching regressions using synthetic in-memory HTTP/PDF readers."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import math
from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "skills" / "academyinfo-flow" / "scripts" / "live_guide.py"
SPEC = importlib.util.spec_from_file_location("test_acaflow_live_guide", SCRIPT_PATH)
guide = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guide)

PUBLIC_URL = "https://www.academyinfo.go.kr/public-test-guide.pdf"
SYNTHETIC_PDF = b"%PDF-1.7\nSynthetic reader fixture, not a source document.\n"


class FakeResponse:
    code = 200
    headers = {"Content-Type": "application/pdf"}

    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return PUBLIC_URL

    def read(self, limit):
        return self.body[:limit]


class FakeOpener:
    def __init__(self, body=SYNTHETIC_PDF):
        self.body = body
        self.calls = []

    def open(self, request, *, timeout):
        self.calls.append((request, timeout))
        return FakeResponse(self.body)


class FakePage:
    width = 595
    height = 842

    def __init__(self, number):
        self.number = number
        self.text = f"Synthetic guide page {number}"
        self.images = []
        self.text_calls = 0
        self.table_calls = 0

    def extract_text(self):
        self.text_calls += 1
        return self.text

    def find_tables(self):
        self.table_calls += 1
        return []


class FakePdf:
    def __init__(self, count=12):
        self.pages = [FakePage(number) for number in range(1, count + 1)]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class FakePdfOpen:
    def __init__(self, document):
        self.document = document
        self.bodies = []

    def __call__(self, stream):
        self.bodies.append(stream.getvalue())
        return self.document


def navigation_for(body=SYNTHETIC_PDF):
    return {
        "edition_year": 2026,
        "source": {"sha256": hashlib.sha256(body).hexdigest()},
        "families": [
            {"code": "4-다", "title": "Fixture A", "pdf_pages": [6, 3]},
            {"code": "5-가", "title": "Fixture B", "pdf_pages": [9, 6]},
        ],
    }


class GuideBatchTests(unittest.TestCase):
    def setUp(self):
        self.opener = FakeOpener()
        self.document = FakePdf()
        self.pdf_open = FakePdfOpen(self.document)
        self.navigation = navigation_for()

    def run_guide(self, selectors=None, *, navigation=None):
        return guide.run_command(
            {"url": PUBLIC_URL, **(selectors or {})}, opener=self.opener,
            pdf_open=self.pdf_open,
            navigation=self.navigation if navigation is None else navigation,
        )

    def assert_pages_extracted_once(self, expected):
        for page in self.document.pages:
            with self.subTest(pdf_page=page.number):
                expected_calls = 1 if page.number in expected else 0
                self.assertEqual(page.text_calls, expected_calls)
                self.assertEqual(page.table_calls, expected_calls)

    def test_codes_share_one_fresh_download_open_and_exact_page_union(self):
        result = self.run_guide({"codes": ["5-가", "4-다", "5-가"]})
        self.assertEqual(len(self.opener.calls), 1)
        self.assertEqual(self.pdf_open.bodies, [SYNTHETIC_PDF])
        self.assertEqual(result["selected_pages"], [3, 6, 9])
        self.assertEqual([page["pdf_page"] for page in result["pages"]], [3, 6, 9])
        self.assert_pages_extracted_once([3, 6, 9])
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["selected_page_extraction_complete"])
        self.assertTrue(result["navigation"]["automatic_page_mapping_applied"])
        self.assertEqual(result["navigation"]["selection_mode"], "hash_verified_item_families")
        self.assertEqual(result["navigation"]["requested_codes"], ["5-가", "4-다"])
        self.assertIsNone(result["navigation"]["requested_code"])
        self.assertEqual(result["navigation"]["selected_families"], [
            {"code": "5-가", "title": "Fixture B", "pdf_pages": [6, 9]},
            {"code": "4-다", "title": "Fixture A", "pdf_pages": [3, 6]},
        ])
        self.assertFalse(result["semantic_verification"])
        self.assertTrue(result["semantic_validation_required"])
        self.assertFalse(result["pdf_original_archived"])
        self.assertFalse(result["full_text_corpus_saved"])
        performance = result["performance"]
        self.assertEqual(performance["fetched_response_count"], 1)
        self.assertEqual(performance["fetched_response_bytes"], len(SYNTHETIC_PDF))
        self.assertEqual(performance["pdf_open_count"], 1)
        self.assertEqual(performance["selected_page_count"], 3)
        self.assertEqual(performance["extracted_page_count"], 3)
        stages = performance["stages_seconds"]
        self.assertEqual(set(stages), {"download", "extraction", "total"})
        self.assertTrue(all(math.isfinite(value) and value >= 0 for value in stages.values()))
        self.assertGreaterEqual(stages["total"], max(stages["download"], stages["extraction"]))

    def test_separate_commands_each_fetch_and_open_a_fresh_pdf(self):
        first = self.run_guide({"codes": ["4-다", "5-가"]})
        second = self.run_guide({"codes": ["4-다", "5-가"]})
        self.assertEqual(len(self.opener.calls), 2)
        self.assertEqual(len(self.pdf_open.bodies), 2)
        self.assertEqual(first["selected_pages"], second["selected_pages"])
        self.assertEqual(first["performance"]["fetched_response_count"], 1)
        self.assertEqual(second["performance"]["fetched_response_count"], 1)

    def test_legacy_code_retains_title_mapping_and_pages(self):
        result = self.run_guide({"code": "4-다"})
        self.assertEqual(result["selected_pages"], [3, 6])
        self.assertEqual(result["navigation"]["selection_mode"], "hash_verified_item_family")
        self.assertEqual(result["navigation"]["requested_code"], "4-다")
        self.assertEqual(result["navigation"]["family_title"], "Fixture A")
        self.assert_pages_extracted_once([3, 6])

    def test_explicit_pages_and_default_table_of_contents_are_unchanged(self):
        explicit = self.run_guide({"page_start": 9, "page_end": 11})
        self.assertEqual(explicit["selected_pages"], [9, 10, 11])
        self.assertEqual(explicit["navigation"]["selection_mode"], "explicit_pdf_pages")
        self.assertFalse(explicit["navigation"]["automatic_page_mapping_applied"])
        default = self.run_guide()
        self.assertEqual(default["selected_pages"], list(range(2, 9)))
        self.assertEqual(default["navigation"]["selection_mode"], "hash_verified_table_of_contents")

    def test_hash_mismatch_disables_all_automatic_family_mapping(self):
        self.navigation["source"]["sha256"] = "0" * 64
        for selectors in ({"code": "4-다"}, {"codes": ["4-다", "5-가"]}):
            with self.subTest(selectors=selectors):
                result = self.run_guide(selectors)
                self.assertEqual(result["status"], "needs_revision_page_lookup")
                self.assertFalse(result["complete"])
                self.assertEqual(result["selected_pages"], [])
                self.assertEqual(result["pages"], [])
                self.assertFalse(result["navigation"]["source_hash_matches_navigation"])
                self.assertFalse(result["navigation"]["automatic_page_mapping_applied"])
                self.assertTrue(result["warnings"])
                self.assertEqual(result["performance"]["extracted_page_count"], 0)
        self.assert_pages_extracted_once([])

    def test_mismatched_default_reads_only_cover_and_explicit_pages_still_work(self):
        self.navigation["source"]["sha256"] = "0" * 64
        default = self.run_guide()
        self.assertEqual(default["selected_pages"], [1])
        self.assertEqual(default["navigation"]["selection_mode"], "document_identity_page")
        self.assertTrue(default["warnings"])
        explicit = self.run_guide({"page_start": 4})
        self.assertEqual(explicit["selected_pages"], [4])
        self.assertFalse(explicit["navigation"]["automatic_page_mapping_applied"])

    def test_missing_or_ambiguous_family_does_not_extract_partial_pages(self):
        for ambiguous in (False, True):
            with self.subTest(ambiguous=ambiguous):
                navigation = copy.deepcopy(self.navigation)
                if ambiguous:
                    navigation["families"].append(copy.deepcopy(navigation["families"][1]))
                    missing = "5-가"
                else:
                    missing = "9-차"
                result = self.run_guide({"codes": ["4-다", missing]}, navigation=navigation)
                self.assertEqual(result["status"], "needs_revision_page_lookup")
                self.assertFalse(result["complete"])
                self.assertEqual(result["pages"], [])
                self.assertEqual(result["navigation"]["unresolved_codes"], [missing])
                self.assertFalse(result["navigation"]["automatic_page_mapping_applied"])
        self.assert_pages_extracted_once([])

    def test_invalid_later_family_pages_fail_before_any_page_extraction(self):
        for invalid in ([], [0], [13], [True], [6.0], [6, 6], "6", None):
            with self.subTest(pdf_pages=invalid):
                navigation = copy.deepcopy(self.navigation)
                navigation["families"][1]["pdf_pages"] = invalid
                with self.assertRaises(guide.GuideError) as raised:
                    self.run_guide({"codes": ["4-다", "5-가"]}, navigation=navigation)
                self.assertEqual(raised.exception.code, "navigation_unavailable")
        self.assert_pages_extracted_once([])

    def test_missing_or_invalid_navigation_hash_fails_before_download(self):
        for source in ({}, {"sha256": 123}, {"sha256": ""}, {"sha256": "bad-hash"}):
            with self.subTest(source=source):
                navigation = copy.deepcopy(self.navigation)
                navigation["source"] = source
                with self.assertRaises(guide.GuideError) as raised:
                    self.run_guide({"codes": ["4-다", "5-가"]}, navigation=navigation)
                self.assertEqual(raised.exception.code, "navigation_unavailable")
        self.assertEqual(self.opener.calls, [])
        self.assertEqual(self.pdf_open.bodies, [])

    def test_invalid_or_conflicting_selectors_fail_before_download(self):
        cases = [
            {"codes": []}, {"codes": "4-다"}, {"codes": ["4-다", "invalid"]},
            {"codes": ["4-다", None]}, {"codes": ["4-다", 4]}, {"code": ""},
            {"code": "4-다", "codes": ["5-가"]},
            {"codes": ["4-다"], "page_start": 1},
            {"codes": ["4-다"], "page_end": 2},
            {"code": "4-다", "page_start": 1},
            {"page_end": 2}, {"page_start": 0}, {"page_start": 5, "page_end": 4},
        ]
        for selectors in cases:
            with self.subTest(selectors=selectors):
                with self.assertRaises(guide.InputError):
                    self.run_guide(selectors)
        self.assertEqual(self.opener.calls, [])
        self.assertEqual(self.pdf_open.bodies, [])

    def test_explicit_page_overflow_is_rejected(self):
        with self.assertRaises(guide.InputError):
            self.run_guide({"page_start": 1, "page_end": 13})
        self.assert_pages_extracted_once([])

    def test_warning_and_interpretation_requirements_survive_batching(self):
        self.document.pages[2].text = ""
        self.document.pages[5].text = "Synthetic \ufffd (cid:1)"
        self.document.pages[5].images = [{"synthetic": True}]
        result = self.run_guide({"codes": ["4-다", "5-가"]})
        self.assertEqual(len(result["warnings"]), 3)
        self.assertTrue(any("텍스트 없음" in warning["reason"] for warning in result["warnings"]))
        self.assertTrue(any("인코딩" in warning["reason"] for warning in result["warnings"]))
        self.assertTrue(any("이미지 내부" in warning["reason"] for warning in result["warnings"]))
        self.assertFalse(result["semantic_verification"])
        self.assertTrue(result["semantic_validation_required"])
        self.assertEqual(result["completion_scope"], "selected_page_extraction_only")
        self.assertFalse(result["ocr_implemented"])
        self.assertEqual(len(result["interpretation_rules"]), 5)

    def test_cli_parses_multiple_codes_and_rejects_empty_or_conflicting_options(self):
        parser = guide.build_parser()
        args = parser.parse_args(["--url", PUBLIC_URL, "--codes", "4-다", "5-가"])
        result = guide.run_command(args, opener=self.opener, pdf_open=self.pdf_open,
                                   navigation=self.navigation)
        self.assertEqual(result["selected_pages"], [3, 6, 9])
        legacy = parser.parse_args(["--url", PUBLIC_URL, "--code", "4-다"])
        self.assertEqual(legacy.code, "4-다")
        for options in (["--codes"], ["--code", "4-다", "--codes", "5-가"]):
            with self.subTest(options=options):
                with self.assertRaises(guide.InputError):
                    parser.parse_args(["--url", PUBLIC_URL, *options])


if __name__ == "__main__":
    unittest.main()
