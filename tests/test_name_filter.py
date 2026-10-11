"""Name filtering trims outer whitespace without changing source observations."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "academyinfo-flow" / "scripts"
SPEC = importlib.util.spec_from_file_location("test_acaflow_name_filter_live_report", SCRIPTS / "live_report.py")
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


class NameFilterTests(unittest.TestCase):
    def test_outer_whitespace_matches_single_and_multiple_names_preserving_raw_values(self):
        def row(school, department):
            return {"dimensions": {"schoolName": school, "deptName": department},
                    "values": {"count": "17"}, "source_page_index": 0}

        source_rows = [row(" 한남대학교 \t", " 컴퓨터공학과 "),
                       row("학교 B ", "컴퓨터공학과\t"),
                       row("한남대학교 캠퍼스", "컴퓨터공학과"),
                       row("한남대학교 ", "다른학과")]
        combined = {"rows": source_rows, "columns": [], "status": "complete", "warnings": []}
        for names, expected_count, match in ((["한남대학교"], 1, "exact"),
                                             ([" 한남대학교 ", "학교 B"], 2, "exact_any")):
            with self.subTest(names=names):
                args = argparse.Namespace(school_names=names, dept_names=[" 컴퓨터공학과 "],
                                          offset=0, limit=50, level="department")
                result = {"catalog_item": {"mjr_use_step_cd": "1"}}
                report._numeric_result(args, result, combined, True)
                self.assertTrue(result["complete"])
                self.assertEqual(len(result["rows"]), expected_count)
                self.assertEqual(result["completeness"]["matched_row_count"], expected_count)
                self.assertEqual(result["filters"]["match"], match)
                self.assertEqual(result["filters"]["normalization"], "outer_whitespace_trim")
                self.assertEqual(result["rows"][0]["dimensions"], source_rows[0]["dimensions"])
                self.assertEqual(result["rows"][0]["values"], source_rows[0]["values"])
                self.assertNotIn("한남대학교 캠퍼스", [r["dimensions"]["schoolName"] for r in result["rows"]])
        self.assertEqual(source_rows[0]["dimensions"]["schoolName"], " 한남대학교 \t")


if __name__ == "__main__":
    unittest.main()
