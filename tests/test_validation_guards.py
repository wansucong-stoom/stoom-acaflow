"""Fail-closed report validation using only small, synthetic XML fixtures.

No source client, disclosure records, session credentials, or live API are used.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "academyinfo-flow" / "scripts" / "vendor"))
from academyinfo_archive.report_tables import ReportParseError, combine_report_pages, parse_report_xml
from parser_fixtures import document, item, schema


def synthetic_report(*, student_count="10", form="36", pagenum=""):
    """One unambiguous row, with explicit and consistent metadata identities."""
    metadata = copy.deepcopy(schema())
    metadata["master"][0]["col_num"] = "4"
    metadata["header"].append({"col_no": "3", "h_col_hdr_krn_nm": "학생수",
                               "h_celmrg_yn": "Y", "h_row_mrg_cnt": "1",
                               "h_col_mrg_cnt": "1"})
    metadata["body"].append({"col_no": "3", "b_col_hid_yn": "N",
                             "b_col_id": "STUDENT_COUNT", "b_col_cd": ""})
    for records in metadata.values():
        for record in records:
            record.update(item_mstr_id="1", form_clft_cd=form)
    positions = [(0, 10), (10, 20), (30, 30), (60, 10)]
    labels = ["기준연도", "학교명", "학과(전공)", "학생수"]
    values = ["2026", "시험대학", "시험학과", student_count]
    raw = document([item(x, 0, width, 10, label)
                    for (x, width), label in zip(positions, labels)]
                   + [item(x, 10, width, 10, value)
                      for (x, width), value in zip(positions, values)])
    if pagenum is None:
        raw = raw.replace(b' pagenum=""', b"")
    elif pagenum != "":
        raw = raw.replace(b'pagenum=""', f'pagenum="{pagenum}"'.encode())
    return raw, metadata


class MetadataIdentityGuardTests(unittest.TestCase):
    def parse_preserving_source(self, raw, metadata, *, selectors=None):
        original_metadata = copy.deepcopy(metadata)
        parsed = parse_report_xml(raw, metadata=metadata, expected_pages=1,
                                  selectors=selectors)
        self.assertEqual(metadata, original_metadata)
        self.assertEqual(parsed["source_table_metadata"], original_metadata)
        self.assertEqual(parsed["pages"][0]["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(parsed["pages"][0]["source_byte_length"], len(raw))
        return parsed

    def assert_not_validated(self, parsed):
        self.assertIn(parsed["status"], {"raw_only", "partial"})
        self.assertTrue(parsed["warnings"])

    def test_consistent_item_and_form_identity_remain_complete(self):
        for level, form in [("school", "30"), ("department", "36")]:
            with self.subTest(level=level, form=form):
                raw, metadata = synthetic_report(form=form)
                parsed = self.parse_preserving_source(raw, metadata, selectors={"level": level})
                self.assertEqual(parsed["status"], "complete")
                self.assertEqual(parsed["rows"][0]["values"]["STUDENT_COUNT"], "10")

    def test_conflicting_item_id_between_metadata_sections_is_not_complete(self):
        for section in ("master", "header", "body"):
            with self.subTest(section=section):
                raw, metadata = synthetic_report()
                for record in metadata[section]:
                    record["item_mstr_id"] = "2"
                self.assert_not_validated(self.parse_preserving_source(raw, metadata))

    def test_conflicting_form_between_metadata_sections_is_not_complete(self):
        for section in ("master", "header", "body"):
            with self.subTest(section=section):
                raw, metadata = synthetic_report()
                for record in metadata[section]:
                    record["form_clft_cd"] = "30"
                self.assert_not_validated(self.parse_preserving_source(raw, metadata))

    def test_conflicting_identity_within_header_or_body_is_not_complete(self):
        for section in ("header", "body"):
            for field, different in [("item_mstr_id", "2"), ("form_clft_cd", "30")]:
                with self.subTest(section=section, field=field):
                    raw, metadata = synthetic_report()
                    metadata[section][-1][field] = different
                    self.assert_not_validated(self.parse_preserving_source(raw, metadata))

    def test_missing_item_identity_in_any_metadata_section_is_not_complete(self):
        for section in ("master", "header", "body"):
            with self.subTest(section=section):
                raw, metadata = synthetic_report()
                metadata[section][-1].pop("item_mstr_id")
                self.assert_not_validated(self.parse_preserving_source(raw, metadata))

    def test_invalid_master_item_identity_is_not_complete(self):
        for invalid in ("", " ", "null", "undefined", None, 1):
            with self.subTest(item_mstr_id=invalid):
                raw, metadata = synthetic_report()
                for records in metadata.values():
                    for record in records:
                        record["item_mstr_id"] = invalid
                self.assert_not_validated(self.parse_preserving_source(raw, metadata))

    def test_invalid_explicit_form_is_not_complete(self):
        for invalid in ("", " ", "null", "undefined", None):
            with self.subTest(form_clft_cd=invalid):
                raw, metadata = synthetic_report()
                for records in metadata.values():
                    for record in records:
                        record["form_clft_cd"] = invalid
                self.assert_not_validated(self.parse_preserving_source(raw, metadata))

    def test_form_identity_can_be_absent_from_some_metadata_rows(self):
        raw, metadata = synthetic_report()
        metadata["master"][0].pop("form_clft_cd")
        metadata["header"][0].pop("form_clft_cd")
        metadata["body"][0].pop("form_clft_cd")
        parsed = self.parse_preserving_source(raw, metadata, selectors={"level": "department"})
        self.assertEqual(parsed["status"], "complete")

    def test_requested_level_conflicting_with_explicit_form_is_not_complete(self):
        for level, form in [("school", "36"), ("department", "30")]:
            with self.subTest(level=level, form=form):
                raw, metadata = synthetic_report(form=form)
                parsed = self.parse_preserving_source(raw, metadata, selectors={"level": level})
                self.assert_not_validated(parsed)


class RepeatedPageGuardTests(unittest.TestCase):
    def combine_preserving_sources(self, raw_pages, metadata, *, reject=False):
        original_metadata = copy.deepcopy(metadata)
        reports = [parse_report_xml(raw, source_page_index=index, metadata=metadata,
                                    expected_pages=len(raw_pages))
                   for index, raw in enumerate(raw_pages)]
        original_reports = copy.deepcopy(reports)
        if reject:
            with self.assertRaises(ReportParseError):
                combine_report_pages(reports, expected_pages=len(raw_pages))
            combined = None
        else:
            combined = combine_report_pages(reports, expected_pages=len(raw_pages))
        self.assertEqual(metadata, original_metadata)
        self.assertEqual(reports, original_reports)
        self.assertEqual([report["pages"][0]["source_sha256"] for report in reports],
                         [hashlib.sha256(raw).hexdigest() for raw in raw_pages])
        for report in reports:
            self.assertEqual(report["source_table_metadata"], original_metadata)
        if combined is not None:
            self.assertEqual(combined["source_table_metadata"], original_metadata)
            self.assertEqual([page["source_sha256"] for page in combined["pages"]],
                             [hashlib.sha256(raw).hexdigest() for raw in raw_pages])
        return combined, reports

    def test_same_xml_at_different_request_indices_without_pagenum_is_incomplete(self):
        for pagenum in ("", None):
            with self.subTest(pagenum=pagenum):
                raw, metadata = synthetic_report(pagenum=pagenum)
                _, reports = self.combine_preserving_sources([raw, raw], metadata, reject=True)
                self.assertEqual([report["pages"][0]["source_page_index"] for report in reports], [0, 1])
                self.assertEqual(reports[0]["rows"][0]["values"], reports[1]["rows"][0]["values"])

    def test_xml_envelope_difference_does_not_validate_repeated_body(self):
        for pagenum in ("", None):
            raw, metadata = synthetic_report(pagenum=pagenum)
            changed_sources = [
                raw.replace(b'<Doc pagecount="1">', b'<Doc pagecount="1" Docserviceid="fixture-B">'),
                raw.replace(b"</Page>", b"<!-- synthetic envelope difference --></Page>"),
            ]
            for changed in changed_sources:
                with self.subTest(pagenum=pagenum, changed_hash=hashlib.sha256(changed).hexdigest()):
                    self.assertNotEqual(hashlib.sha256(raw).hexdigest(), hashlib.sha256(changed).hexdigest())
                    _, reports = self.combine_preserving_sources([raw, changed], metadata, reject=True)
                    self.assertEqual([row["values"] for row in reports[0]["rows"]],
                                     [row["values"] for row in reports[1]["rows"]])

    def test_different_bodies_without_pagenum_can_complete(self):
        for pagenum in ("", None):
            with self.subTest(pagenum=pagenum):
                first, metadata = synthetic_report(student_count="10", pagenum=pagenum)
                second, _ = synthetic_report(student_count="11", pagenum=pagenum)
                combined, _ = self.combine_preserving_sources([first, second], metadata)
                self.assertEqual(combined["status"], "complete")
                self.assertTrue(combined["coverage"]["complete"])
                self.assertEqual([row["values"]["STUDENT_COUNT"] for row in combined["rows"]], ["10", "11"])

    def test_single_page_without_pagenum_remains_complete(self):
        for pagenum in ("", None):
            with self.subTest(pagenum=pagenum):
                raw, metadata = synthetic_report(pagenum=pagenum)
                combined, reports = self.combine_preserving_sources([raw], metadata)
                self.assertEqual(reports[0]["status"], "complete")
                self.assertEqual(combined["status"], "complete")
                self.assertTrue(combined["coverage"]["complete"])


if __name__ == "__main__":
    unittest.main()
