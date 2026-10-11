"""Parser regression tests adapted from STOOM's stoom-academyinfo tests.

Copyright (c) 2026 STOOM. MIT license; the original notice is preserved in
skills/academyinfo-flow/scripts/vendor/academyinfo_archive/LICENSE.
Schema/coverage failures must not become publishable numerical facts.
"""
import copy
from collections import Counter
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'academyinfo-flow' / 'scripts' / 'vendor'))
from academyinfo_archive import report_tables
from parser_fixtures import item, sample, schema, regression_cases, rectangular_report, strip_raw_trees

from academyinfo_archive.report_tables import (
    ReportParseError, combine_report_pages, parse_java_map_list, parse_report_xml,
)








class ReportTableTests(unittest.TestCase):
    def test_raw_xml_structure_and_original_string_values(self):
        parsed = parse_report_xml(sample(), metadata=schema(), expected_pages=1,
                                  selectors={"pubYear": "2025"})
        self.assertEqual(parsed["status"], "complete")
        self.assertEqual(len(parsed["rows"]), 2)
        self.assertEqual(parsed["rows"][0]["values"]["MJR_KRN_NM"], "0005891")
        self.assertEqual(parsed["rows"][1]["values"]["MJR_KRN_NM"], "")
        self.assertTrue(parsed["rows"][1]["cell_sources"]["SCHL_NM"]["expanded_rowspan"])
        self.assertEqual(parsed["rows"][1]["dimensions"],
                         {"pubYear": "2025", "refYear": "2024", "schoolName": "한남대학교", "deptName": ""})
        self.assertNotIn("schoolCode", parsed["rows"][0]["dimensions"])
        tree = parsed["pages"][0]["xml_tree"]
        self.assertEqual(tree["attributes"], {"pagecount": "1"})
        self.assertEqual(tree["children"][0]["attributes"], {"pagenum": ""})
        self.assertEqual(len(parsed["pages"][0]["cells"]), 7)

    def test_fragment_pagecount_is_not_report_total(self):
        unknown = parse_report_xml(sample(), metadata=schema())
        self.assertEqual(unknown["status"], "partial")
        self.assertIsNone(unknown["coverage"]["expected_pages"])
        missing = parse_report_xml(sample(), metadata=schema(), expected_pages=3)
        self.assertEqual(missing["coverage"]["missing_pages"], [1, 2])
        self.assertEqual(missing["status"], "partial")

    def test_missing_and_overlapping_cells_are_detected(self):
        for xml in [sample(missing=True), sample(overlap=True)]:
            parsed = parse_report_xml(xml, metadata=schema(), expected_pages=1)
            self.assertEqual(parsed["status"], "partial")
            self.assertTrue(parsed["warnings"])
            self.assertTrue(any(r["status"] == "ambiguous" for r in parsed["rows"]))

    def test_no_metadata_keeps_raw_cells_without_guessing_columns(self):
        parsed = parse_report_xml(sample(), expected_pages=1)
        self.assertEqual(parsed["status"], "raw_only")
        self.assertEqual(parsed["rows"], [])
        self.assertEqual(len(parsed["pages"][0]["cells"]), 7)

    def test_schema_drift_keeps_data_but_prevents_complete(self):
        first = parse_report_xml(sample(), metadata=schema())
        second = parse_report_xml(sample(label="학과 명칭 변경"), metadata=schema(), source_page_index=1)
        combined = combine_report_pages([first, second], expected_pages=2)
        self.assertEqual(combined["status"], "partial")
        self.assertIn("페이지 사이에서 표 컬럼 구조가 변경되었습니다.", combined["warnings"])

    def test_missing_duplicate_and_unexpected_page_detection(self):
        first = parse_report_xml(sample(), metadata=schema())
        last = parse_report_xml(sample(), metadata=schema(), source_page_index=2)
        incomplete = combine_report_pages([last, first], expected_pages=3)
        self.assertEqual(incomplete["coverage"]["missing_pages"], [1])
        duplicated = combine_report_pages([first, first], expected_pages=1)
        self.assertEqual(duplicated["coverage"]["duplicate_pages"], [0])
        self.assertEqual(duplicated["status"], "partial")
        unexpected = combine_report_pages([last], expected_pages=2)
        self.assertEqual(unexpected["coverage"]["unexpected_pages"], [2])

    def test_complete_combination_and_stable_original_row_numbers(self):
        first = parse_report_xml(sample(), metadata=schema())
        second = parse_report_xml(sample(), metadata=schema(), source_page_index=1)
        original_second_row = copy.deepcopy(second["rows"][0])
        combined = combine_report_pages([second, first], expected_pages=2)
        self.assertEqual(combined["status"], "complete")
        self.assertEqual([r["row_number"] for r in combined["rows"]], [1, 2, 3, 4])
        self.assertEqual(combined["rows"][2]["source_page_row_number"], 1)
        self.assertEqual(second["rows"][0], original_second_row)

    def test_unequal_header_band_heights_are_matched_by_explicit_spans(self):
        metadata = schema()
        metadata["master"][0]["row_num"] = "1"
        metadata["header"] = [
            {"col_no": "0", "h_col_hdr_krn_nm": "기준연도", "h_celmrg_yn": "Y", "h_row_mrg_cnt": "2", "h_col_mrg_cnt": "1"},
            {"col_no": "1", "h_col_hdr_krn_nm": "분류", "h_celmrg_yn": "Y", "h_row_mrg_cnt": "1", "h_col_mrg_cnt": "2"},
            {"col_no": "2", "h_col_hdr_krn_nm": "분류", "h_celmrg_yn": "N"},
            {"col_no": "3", "h_col_hdr_krn_nm": "기준연도", "h_celmrg_yn": "N"},
            {"col_no": "4", "h_col_hdr_krn_nm": "학교명", "h_celmrg_yn": "Y", "h_row_mrg_cnt": "1", "h_col_mrg_cnt": "1"},
            {"col_no": "5", "h_col_hdr_krn_nm": "학과(전공)", "h_celmrg_yn": "Y", "h_row_mrg_cnt": "1", "h_col_mrg_cnt": "1"},
        ]
        xml = ('<Doc><Page>' + item(0, 0, 10, 22, "기준연도") + item(10, 0, 50, 10, "분류")
               + item(10, 10, 20, 12, "학교명") + item(30, 10, 30, 12, "학과(전공)")
               + item(0, 22, 10, 10, "2025") + item(10, 22, 20, 10, "한남대학교")
               + item(30, 22, 30, 10, "기계공학과") + '</Page></Doc>').encode()
        parsed = parse_report_xml(xml, metadata=metadata, expected_pages=1)
        self.assertEqual(parsed["status"], "complete")
        self.assertEqual(parsed["columns"][1]["header_path"], ["분류", "학교명"])
        self.assertEqual(parsed["rows"][0]["dimensions"]["deptName"], "기계공학과")
        metadata["header"][4]["h_col_hdr_krn_nm"] = "임의 변경"
        self.assertEqual(parse_report_xml(xml, metadata=metadata, expected_pages=1)["status"], "raw_only")

    def test_stale_master_count_requires_full_explicit_header_and_body_agreement(self):
        metadata = schema()
        metadata["master"][0]["col_num"] = "5"
        metadata["body"][0]["b_col_id"] = "APY_YR"
        metadata["body"][0]["b_col_cd"] = ""
        parsed = parse_report_xml(sample(), metadata=metadata, expected_pages=1)
        self.assertEqual(parsed["status"], "complete")
        self.assertEqual(parsed["columns"][0]["source_master_column_count"], 5)
        self.assertEqual(parsed["columns"][0]["source_body_column_count"], 3)
        self.assertEqual(parsed["rows"][0]["dimensions"]["refYear"], "2024")
        metadata["header"].append({"col_no": "3"})
        rejected = parse_report_xml(sample(), metadata=metadata, expected_pages=1)
        self.assertEqual(rejected["status"], "raw_only")
        self.assertTrue(rejected["warnings"])

    def test_java_map_preserves_korean_commas_formula_braces_and_empty(self):
        text = '[{item_mstr_id=6966, h_col_hdr_krn_nm=취업률, (%)\\n[B/{A-(C+D)}]x100, h_col_hdr_ofcfmla=expr="a,b", h_bgd_clr_cd=}, {item_mstr_id=6966, h_col_hdr_krn_nm=한남대학교, h_col_hdr_ofcfmla=, h_bgd_clr_cd=}]'
        parsed = parse_java_map_list(text)
        self.assertEqual(parsed[0]["h_col_hdr_krn_nm"], '취업률, (%)\\n[B/{A-(C+D)}]x100')
        self.assertEqual(parsed[0]["h_col_hdr_ofcfmla"], 'expr="a,b"')
        self.assertEqual(parsed[0]["h_bgd_clr_cd"], "")
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parse_java_map_list("[]"), [])


    def test_invalid_metadata_and_non_report_xml_fail_closed(self):
        for text in ['[{item_mstr_id=1, item_mstr_id=2}]', '[{item_mstr_id=1, unknown=2}]', '{}']:
            with self.assertRaises(ReportParseError):
                parse_java_map_list(text)
        for raw in [b'<Error>not ready</Error>', b'<!DOCTYPE Doc [<!ENTITY x "value">]><Doc><Page/></Doc>', b'<Doc><Page/><Page/></Doc>']:
            with self.assertRaises(ReportParseError):
                parse_report_xml(raw)
        bad_schema = schema()
        bad_schema["body"][0]["b_col_id"] = "SCHL_NM"
        parsed = parse_report_xml(sample(), metadata=bad_schema, expected_pages=1)
        self.assertEqual(parsed["status"], "raw_only")


class ParserOptimizationTests(unittest.TestCase):
    def test_lightweight_mode_changes_only_raw_tree_fields(self):
        for name, raw, kwargs in regression_cases():
            with self.subTest(layout=name):
                try:
                    expected = parse_report_xml(raw, **copy.deepcopy(kwargs))
                except ReportParseError as error:
                    with self.assertRaises(ReportParseError) as rejected:
                        parse_report_xml(raw, include_raw_tree=False, **copy.deepcopy(kwargs))
                    self.assertEqual(str(rejected.exception), str(error))
                else:
                    actual = parse_report_xml(raw, include_raw_tree=False, **copy.deepcopy(kwargs))
                    self.assertEqual(actual, strip_raw_trees(expected))

    def test_lightweight_mode_does_not_construct_discarded_trees(self):
        with patch.object(report_tables, '_tree', side_effect=AssertionError('raw tree must not be built')):
            parsed = parse_report_xml(sample(), metadata=schema(), expected_pages=1, include_raw_tree=False)
        self.assertEqual(parsed['status'], 'complete')
        self.assertNotIn('xml_tree', parsed['pages'][0])
        self.assertTrue(all('children' not in cell for cell in parsed['pages'][0]['cells']))

    def test_comments_processing_instructions_and_nested_text_preserve_item_indices(self):
        _, raw, kwargs = next(case for case in regression_cases() if case[0] == 'comments-pis-and-nested-text')
        full = parse_report_xml(raw, **kwargs)
        slim = parse_report_xml(raw, **kwargs, include_raw_tree=False)
        self.assertEqual(full['pages'][0]['cells'][0]['item_index'], 2)
        self.assertEqual(slim['rows'], full['rows'])
        self.assertEqual(slim['rows'][0]['values']['MJR_KRN_NM'], '0005891')
        self.assertEqual(slim['pages'][0]['source_sha256'], full['pages'][0]['source_sha256'])
        self.assertEqual(full['pages'][0]['cells'][5]['source_text'], '00')

    def test_geometry_conversion_is_bounded_per_cell_and_not_cached_across_parses(self):
        raw, metadata = rectangular_report(rows=32, columns=24, rowspans=True, seed=7)
        with patch.object(report_tables, '_rect', wraps=report_tables._rect) as convert:
            first = parse_report_xml(raw, metadata=metadata, expected_pages=1, include_raw_tree=False)
            counts = Counter(id(call.args[0]) for call in convert.call_args_list)
            self.assertEqual(max(counts.values()), 1)
            self.assertEqual(sum(counts.values()), len(first['pages'][0]['cells']))
            convert.reset_mock()
            second = parse_report_xml(raw, metadata=metadata, expected_pages=1, include_raw_tree=False)
            self.assertEqual(convert.call_count, len(second['pages'][0]['cells']))
        self.assertEqual(first, second)
        self.assertEqual(first['status'], 'complete')
        self.assertEqual(len(first['rows']), 32)

    def test_staggered_rowspans_decimal_boundaries_and_unordered_cells(self):
        raw, metadata = rectangular_report(rows=13, columns=11, rowspans=True, seed=42, decimal=True)
        parsed = parse_report_xml(raw, metadata=metadata, expected_pages=1)
        self.assertEqual(parsed['status'], 'complete')
        self.assertEqual(len(parsed['rows']), 13)
        self.assertEqual([row['values']['MJR_KRN_NM'] for row in parsed['rows']],
                         [f'{row:07}' for row in range(13)])
        self.assertTrue(all(row['cell_sources']['APY_YR']['expanded_rowspan'] for row in parsed['rows']))

    def test_event_sweep_retains_duplicates_even_for_identical_cell_object(self):
        cells = parse_report_xml(sample())['pages'][0]['cells']
        cells.append(cells[5])
        _, rows, warnings = report_tables._parse_table(cells, schema(), 0, None)
        self.assertEqual(rows[0]['ambiguous_columns'], ['MJR_KRN_NM'])
        self.assertIsNone(rows[0]['values']['MJR_KRN_NM'])
        self.assertTrue(warnings)

    def test_preserves_supported_and_unverifiable_layout_statuses(self):
        expected = {'hidden-column': 'complete', 'unique-bottom-colspan-partition': 'complete',
                    'ambiguous-bottom-colspan-partition': 'raw_only', 'formula-label-variation': 'complete',
                    'ignored-body-cell': 'partial', 'adjacent-row': 'complete', 'line-item': 'complete',
                    'stale-master-count': 'complete', 'duplicate-field-id': 'raw_only',
                    'out-of-bounds-header-span': 'raw_only', 'duplicate-header-metadata': 'raw_only',
                    'rounded-zero-forward-interval': 'partial'}
        for name, raw, kwargs in regression_cases():
            if name in expected:
                with self.subTest(layout=name):
                    result = parse_report_xml(raw, **kwargs)
                    self.assertEqual(result['status'], expected[name])
                    if expected[name] != 'complete':
                        self.assertTrue(result['warnings'])


if __name__ == "__main__":
    unittest.main()
