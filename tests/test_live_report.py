"""Live wrapper regressions against synthetic XML and an in-memory source client."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from parser_fixtures import rectangular_report


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "academyinfo-flow" / "scripts"
SPEC = importlib.util.spec_from_file_location("test_acaflow_live_report", SCRIPTS / "live_report.py")
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)
from academyinfo_archive.direct import Exchange


REPORT_URL = "https://www.academyinfo.go.kr/UbiServer.do"
CATALOG_URL = "https://m.academyinfo.go.kr/main/main0780/selectItemList.do"


def schema_strings(metadata):
    """Encode the reviewed Java map format without bypassing its actual parser."""
    result = {}
    for section, rows in metadata.items():
        records = []
        for row in rows:
            fields = {"item_mstr_id": "41", **row}
            records.append("{" + ", ".join(f"{key}={value}" for key, value in fields.items()) + "}")
        result["result" + section.capitalize()] = "[" + ", ".join(records) + "]"
    return result


def command(**overrides):
    return {"command": "report", "year": "2026", "division": "02", "item": "1",
            "level": "department", "max_pages": 100, "limit": 100, "offset": 0,
            **overrides}


class FakeSession:
    def __init__(self, initial, metadata, title):
        self.initial = initial
        self.schema_text = schema_strings(metadata)
        self.title = title
        self._runtime = {"secret": "SYNTHETIC_PRIVATE_RUNTIME_DO_NOT_OUTPUT"}
        self.closed = False
        self.status_calls = 0

    def close(self):
        self.closed = True
        self._runtime.clear()


class FakeViewerClient:
    """Only the source boundary is mocked; catalog/table parsing stays real."""

    def __init__(self, serial, config):
        self.serial = serial
        self.config = copy.deepcopy(config)
        self.catalog_calls = []
        self.start_calls = []
        self.fetch_calls = []
        self.sessions = []
        first, self.metadata = rectangular_report(rows=10, columns=6)
        second = first.replace("시험대학 0".encode(), "시험대학 2".encode()).replace(
            "시험대학 1".encode(), "시험대학 3".encode())
        self.page_bodies = [first, second]
        if "initial_pagenum" in config:
            self.page_bodies[0] = first.replace(b'pagenum=""',
                                                f'pagenum="{config["initial_pagenum"]}"'.encode())

    def exchange(self, body, *, url=REPORT_URL, parameters=None, content_type="application/xml"):
        return Exchange(url=url, method="POST", parameters=parameters or {}, body=body,
                        status=200, content_type=content_type,
                        fetched_at=f"2026-10-11T16:00:00.{self.serial:06d}+00:00", final_url=url)

    def catalog(self, year, division):
        self.catalog_calls.append((year, division))
        if self.config.get("fail_catalog"):
            raise report.SourceError("Synthetic source failure; no live network involved.")
        rows = [{"svy_yr": self.config.get("catalog_year", year), "schl_div_cd": division,
                 "item_id": item, "mjr_use_step_cd": "1", "pdf_use_yn": "N",
                 "pgm_estn_nm": "Synthetic disclosure fixture"} for item in ("1", "2")]
        return self.exchange(json.dumps({"detailItemList": rows}).encode(), url=CATALOG_URL,
                             parameters={"svyYr": year, "schlDivCd": division},
                             content_type="application/json")

    def start_report(self, year, division, item, *, level):
        self.start_calls.append((year, division, item, level))
        session = FakeSession(self.exchange(self.page_bodies[0]), self.metadata,
                              self.config.get("title", "Synthetic disclosure table"))
        self.sessions.append(session)
        return session

    def report_status(self, session):
        session.status_calls += 1
        statuses = self.config.get("statuses", [(True, 2), (True, 2)])
        complete, expected = statuses[min(session.status_calls - 1, len(statuses) - 1)]
        return SimpleNamespace(complete=complete, expected_pages=expected)

    def fetch_page(self, session, page, *, document_local_page_numbers=False):
        self.fetch_calls.append((page, document_local_page_numbers))
        self.assert_open(session)
        if page == self.config.get("fail_page"):
            if self.config.get("connection_error"):
                raise TimeoutError("SYNTHETIC_PRIVATE_CONNECTION_DETAILS")
            raise report.SourceError("SYNTHETIC_PRIVATE_SOURCE_DETAILS")
        return self.exchange(self.page_bodies[page - 1])

    @staticmethod
    def assert_open(session):
        if session.closed:
            raise AssertionError("Closed report session was reused.")


class LiveReportTests(unittest.TestCase):
    def setUp(self):
        self.config = {}
        self.clients = []
        factory_patch = patch.object(report, "ViewerDataClient", side_effect=self.new_client)
        self.factory = factory_patch.start()
        self.addCleanup(factory_patch.stop)

    def new_client(self):
        client = FakeViewerClient(len(self.clients) + 1, self.config)
        self.clients.append(client)
        return client

    def run_report(self, *, batch=None, **overrides):
        return report.run_command(command(**overrides), batch=batch)

    def assert_complete_source(self, result):
        self.assertTrue(result["completeness"]["source_complete"])
        self.assertTrue(result["generation"]["page_count_stable"])
        self.assertEqual(result["generation"]["source_total_pages"], 2)
        self.assertEqual(result["generation"]["fetched_pages"], 2)

    def test_legacy_single_command_preserves_values_columns_and_evidence(self):
        result = self.run_report(school_name="시험대학 0")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["complete"])
        self.assertEqual(result["returned_row_count"], 5)
        self.assert_complete_source(result)
        self.assertEqual(result["filters"]["dimensions"], {"schoolName": "시험대학 0"})
        self.assertEqual(result["filters"]["match"], "exact")
        self.assertEqual([row["values"]["MJR_KRN_NM"] for row in result["rows"]],
                         [f"{number:07d}" for number in range(5)])
        values = {value for row in result["rows"] for value in row["values"].values()}
        self.assertTrue({"", "0", "-"}.issubset(values))
        self.assertTrue(all(isinstance(value, str) for value in values))
        self.assertEqual(len(result["columns"]), 6)
        self.assertEqual(result["columns"][1]["source_field_id"], "SCHL_NM")
        self.assertEqual(len(result["sources"]), 3)
        page_sources = [source for source in result["sources"] if "source_request_page" in source]
        self.assertEqual([source["raw_sha256"] for source in page_sources],
                         [hashlib.sha256(body).hexdigest() for body in self.clients[0].page_bodies])
        self.assertEqual([source["source_request_page"] for source in page_sources], [1, 2])
        self.assertEqual(self.clients[0].fetch_calls, [(2, False)])
        self.assertTrue(self.clients[0].sessions[0].closed)
        self.assertFalse(result["raw_responses_saved"])
        self.assertNotIn("SYNTHETIC_PRIVATE_RUNTIME", json.dumps(result))
        performance = result["performance"]
        self.assertFalse(performance["source_reused"])
        self.assertEqual(performance["fetched_report_pages_this_call"], 2)
        self.assertEqual(performance["source_report_pages"], 2)
        self.assertTrue(all(math.isfinite(value) and value >= 0
                            for value in performance["stages_seconds"].values()))

    def test_one_batch_reuses_source_for_different_schools_and_offsets(self):
        with report.ReportBatch() as batch:
            first = self.run_report(batch=batch, school_name="시험대학 0", limit=2)
            first_before = copy.deepcopy(first)
            second = self.run_report(batch=batch, school_name="시험대학 1")
            third = self.run_report(batch=batch, school_name="시험대학 0", offset=2, limit=3)
            self.assertEqual(first, first_before)
            self.assertEqual(second["returned_row_count"], 5)
            self.assertEqual([row["values"]["MJR_KRN_NM"] for row in third["rows"]],
                             ["0000002", "0000003", "0000004"])
            self.assertEqual(first["status"], "partial")
            self.assertEqual(second["status"], "ok")
            self.assertEqual(third["status"], "partial")
            self.assertEqual(first["sources"], second["sources"])
            self.assertEqual(first["sources"], third["sources"])
            self.assertEqual(first["columns"], third["columns"])
            self.assertEqual(batch.stats["hits"], 2)
            self.assertEqual(batch.stats["misses"], 1)
            self.assertEqual(self.clients[0].catalog_calls, [("2026", "02")])
            self.assertEqual(len(self.clients[0].start_calls), 1)
            self.assertEqual(self.clients[0].fetch_calls, [(2, False)])
            self.assertEqual(self.clients[0].sessions[0].status_calls, 2)
            self.assertTrue(self.clients[0].sessions[0].closed)
            self.assertTrue(third["performance"]["source_reused"])
            self.assertEqual(third["performance"]["fetched_report_pages_this_call"], 0)
            self.assertEqual(third["performance"]["source_report_pages"], 2)
            self.assert_complete_source(third)

    def test_multiple_names_are_exact_or_with_and_between_dimensions(self):
        result = self.run_report(school_names=["시험대학 0", "시험대학 2", "시험대학 0"],
                                 dept_names=["0000000", "0000006"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual([(row["dimensions"]["schoolName"], row["dimensions"]["deptName"])
                          for row in result["rows"]],
                         [("시험대학 0", "0000000"), ("시험대학 2", "0000000")])
        self.assertEqual(result["filters"]["match"], "exact_any")
        self.assertEqual(result["filters"]["dimensions"]["schoolName"], ["시험대학 0", "시험대학 2"])
        self.assertEqual([row["source_request_page"] for row in result["rows"]], [1, 2])
        absent = self.run_report(school_name="시험대학")
        self.assertEqual(absent["rows"], [])
        self.assertEqual(absent["completeness"]["matched_row_count"], 0)
        self.assertEqual(absent["data_availability"], "empty")

    def test_source_key_isolates_year_division_item_level_and_page_cap(self):
        with report.ReportBatch() as batch:
            variants = [{}, {"year": "2025"}, {"division": "01"}, {"item": "2"},
                        {"level": "school"}, {"max_pages": 1}]
            results = [self.run_report(batch=batch, **variant) for variant in variants]
            self.assertEqual(len(self.clients), 1)
            self.assertEqual(len(self.clients[0].start_calls), len(variants))
            self.assertEqual(self.clients[0].catalog_calls,
                             [("2026", "02"), ("2025", "02"), ("2026", "01")])
            self.assertEqual(batch.stats["catalog_hits"], 3)
            self.assertEqual(batch.stats["misses"], len(variants))
            self.assertEqual(batch.stats["hits"], 0)
            for variant, result in zip(variants, results):
                with self.subTest(variant=variant):
                    self.assertFalse(result["performance"]["source_reused"])
                    self.assertEqual(result["selectors"]["pubYear"], variant.get("year", "2026"))
                    self.assertEqual(result["selectors"]["itemId"], variant.get("item", "1"))
                    self.assertEqual(result["selectors"]["level"], variant.get("level", "department"))
            reused = self.run_report(batch=batch, max_pages=1, offset=1)
            self.assertTrue(reused["performance"]["source_reused"])
            self.assertFalse(reused["completeness"]["source_complete"])
            self.assertEqual(reused["generation"]["fetched_pages"], 1)
            self.assertEqual(len(self.clients[0].start_calls), len(variants))

    def test_normal_commands_and_new_batches_always_fetch_afresh(self):
        first = self.run_report()
        second = self.run_report()
        with report.ReportBatch() as first_batch:
            third = self.run_report(batch=first_batch)
        with report.ReportBatch() as second_batch:
            fourth = self.run_report(batch=second_batch)
        self.assertEqual(len(self.clients), 4)
        self.assertTrue(all(len(client.catalog_calls) == 1 and len(client.start_calls) == 1
                            for client in self.clients))
        self.assertTrue(all(not result["performance"]["source_reused"]
                            for result in (first, second, third, fourth)))
        self.assertNotEqual(first["sources"][0]["retrieved_utc"], second["sources"][0]["retrieved_utc"])
        self.assertNotEqual(third["sources"][0]["retrieved_utc"], fourth["sources"][0]["retrieved_utc"])

    def test_closed_batch_clears_material_and_rejects_future_queries(self):
        with report.ReportBatch() as batch:
            result = self.run_report(batch=batch)
            self.assertTrue(batch._snapshots)
            self.assertTrue(batch._catalogs)
        result_before = copy.deepcopy(result)
        self.assertTrue(batch.closed)
        self.assertEqual(batch._snapshots, {})
        self.assertEqual(batch._catalogs, {})
        self.assertIsNone(batch._client)
        rejected = self.run_report(batch=batch)
        self.assertEqual(rejected["status"], "error")
        self.assertEqual(rejected["error"]["code"], "invalid_input")
        self.assertEqual(rejected["sources"], [])
        self.assertEqual(len(self.clients), 1)
        self.assertEqual(result, result_before)
        with self.assertRaises(report.InputError):
            with batch:
                pass

    def test_returned_results_and_compact_views_cannot_mutate_batch_material(self):
        with report.ReportBatch() as batch:
            first = self.run_report(batch=batch, school_name="시험대학 0")
            original = copy.deepcopy(first)
            first["rows"][0]["values"]["MJR_KRN_NM"] = "changed by caller"
            first["sources"][0]["public_parameters"]["svyYr"] = "1900"
            first["columns"][0]["header_path"].append("changed by caller")
            second = self.run_report(batch=batch, school_name="시험대학 0")
            self.assertEqual(second["rows"], original["rows"])
            self.assertEqual(second["sources"], original["sources"])
            self.assertEqual(second["columns"], original["columns"])
            compact = report.compact_result(second)
            compact["rows"][0]["values"]["MJR_KRN_NM"] = "changed compact"
            compact["sources"].clear()
            self.assertEqual(second["rows"], original["rows"])
            self.assertEqual(second["sources"], original["sources"])

    def test_partial_page_cap_remains_partial_for_reused_empty_and_nonempty_views(self):
        with report.ReportBatch() as batch:
            first = self.run_report(batch=batch, max_pages=1, school_name="시험대학 0")
            second = self.run_report(batch=batch, max_pages=1, school_name="시험대학 2")
            for result in (first, second):
                self.assertEqual(result["status"], "partial")
                self.assertFalse(result["complete"])
                self.assertFalse(result["completeness"]["source_complete"])
                self.assertEqual(result["generation"]["source_total_pages"], 2)
                self.assertEqual(result["generation"]["fetched_pages"], 1)
                self.assertIn("page_limit_or_generation_unverified", result["completeness"]["reasons"])
            self.assertEqual(first["returned_row_count"], 5)
            self.assertEqual(second["rows"], [])
            self.assertEqual(first["sources"], second["sources"])

    def test_midstream_source_failure_survives_reprojection_without_retry_or_disclosure(self):
        self.config["fail_page"] = 2
        with report.ReportBatch() as batch:
            first = self.run_report(batch=batch, school_name="시험대학 0")
            second = self.run_report(batch=batch, school_name="시험대학 2")
            third = self.run_report(batch=batch)
            self.assertEqual(first["status"], "partial")
            self.assertEqual(second["status"], "error")
            self.assertEqual(third["status"], "partial")
            for result in (first, second, third):
                self.assertEqual(result["error"]["code"], "source_validation_error")
                self.assertFalse(result["complete"])
                self.assertFalse(result["completeness"]["source_complete"])
                self.assertNotIn("SYNTHETIC_PRIVATE", json.dumps(result))
            self.assertEqual(first["sources"], third["sources"])
            self.assertEqual(len(self.clients[0].start_calls), 1)
            self.assertEqual(self.clients[0].fetch_calls, [(2, False)])
            self.assertTrue(self.clients[0].sessions[0].closed)

    def test_projection_source_failure_survives_safe_empty_and_limited_cached_views(self):
        client = self.new_client()
        client.page_bodies[0] = client.page_bodies[0].replace(
            b">0000000</Text>",
            b">&lt;script&gt;SYNTHETIC_PRIVATE_SOURCE_DETAILS&lt;/script&gt;</Text>")
        self.factory.side_effect = None
        self.factory.return_value = client
        with report.ReportBatch() as batch:
            first = self.run_report(batch=batch, school_name="시험대학 0")
            safe = self.run_report(batch=batch, school_name="시험대학 1")
            empty = self.run_report(batch=batch, school_name="없는 대학")
            limited = self.run_report(batch=batch, school_name="시험대학 1", limit=2)
            for result in (first, safe, empty, limited):
                self.assertEqual(result["error"]["code"], "source_validation_error")
                self.assertFalse(result["complete"])
                self.assertFalse(result["completeness"]["source_complete"])
                self.assertIn("source_validation_error", result["completeness"]["reasons"])
                self.assertNotIn("page_limit_or_generation_unverified",
                                 result["completeness"]["reasons"])
                self.assertTrue(result["generation"]["page_count_stable"])
                self.assertNotIn("SYNTHETIC_PRIVATE", json.dumps(result))
                self.assertEqual(result["sources"], first["sources"])
            self.assertEqual([result["status"] for result in (first, safe, empty, limited)],
                             ["error", "partial", "error", "partial"])
            self.assertEqual([result["returned_row_count"] for result in (first, safe, empty, limited)],
                             [0, 5, 0, 2])
            self.assertTrue(safe["completeness"]["returned_complete"])
            self.assertTrue(empty["completeness"]["returned_complete"])
            self.assertFalse(limited["completeness"]["returned_complete"])
            self.assertIn("return_range", limited["completeness"]["reasons"])
            self.assertNotIn("return_range", safe["completeness"]["reasons"])
            self.assertEqual(len(client.start_calls), 1)
            self.assertEqual(client.fetch_calls, [(2, False)])
            self.assertTrue(client.sessions[0].closed)

    def test_connection_error_remains_an_error_on_reused_partial_result(self):
        self.config.update(fail_page=2, connection_error=True)
        with report.ReportBatch() as batch:
            first = self.run_report(batch=batch)
            second = self.run_report(batch=batch, school_name="시험대학 0")
            for result in (first, second):
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["error"]["code"], "source_connection_error")
                self.assertFalse(result["complete"])
                self.assertFalse(result["completeness"]["source_complete"])
                self.assertNotIn("SYNTHETIC_PRIVATE", json.dumps(result))
            self.assertEqual(len(self.clients[0].fetch_calls), 1)

    def test_changed_generation_status_invalidates_all_cached_projections(self):
        self.config["statuses"] = [(True, 2), (True, 3)]
        with report.ReportBatch() as batch:
            first = self.run_report(batch=batch)
            second = self.run_report(batch=batch, school_name="시험대학 0")
            for result in (first, second):
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["error"]["code"], "source_validation_error")
                self.assertFalse(result["complete"])
                self.assertFalse(result["generation"]["page_count_stable"])
                self.assertFalse(result["completeness"]["source_complete"])
            self.assertEqual(self.clients[0].sessions[0].status_calls, 2)

    def test_incomplete_generation_cannot_become_complete_in_a_second_view(self):
        self.config["statuses"] = [(False, 2)]
        with patch.object(report, "GENERATION_MAX_POLLS", 2), patch.object(report.time, "sleep"):
            with report.ReportBatch() as batch:
                first = self.run_report(batch=batch)
                second = self.run_report(batch=batch, school_name="시험대학 0")
        for result in (first, second):
            self.assertEqual(result["status"], "error")
            self.assertFalse(result["complete"])
            self.assertEqual(result["rows"], [])
            self.assertEqual(result["error"]["code"], "source_validation_error")
            self.assertFalse(result["generation"]["complete_before_fetch"])
        self.assertEqual(self.clients[0].sessions[0].status_calls, 2)
        self.assertEqual(self.clients[0].fetch_calls, [])
        self.assertTrue(self.clients[0].sessions[0].closed)

    def test_wrong_catalog_year_is_rejected_before_report_initialization(self):
        self.config["catalog_year"] = "1900"
        with report.ReportBatch() as batch:
            first = self.run_report(batch=batch)
            second = self.run_report(batch=batch, school_name="시험대학 0")
        for result in (first, second):
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["rows"], [])
            self.assertEqual(result["error"]["code"], "source_validation_error")
        self.assertEqual(self.clients[0].start_calls, [])
        self.assertEqual(len(self.clients[0].catalog_calls), 1)

    def test_unexpected_initial_page_number_is_rejected_and_session_closed(self):
        self.config["initial_pagenum"] = "2"
        result = self.run_report()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["error"]["code"], "source_validation_error")
        self.assertFalse(result["complete"])
        self.assertTrue(self.clients[0].sessions[0].closed)

    def test_invalid_source_title_is_rejected_and_session_closed(self):
        self.config["title"] = "<script>SYNTHETIC_PRIVATE_SOURCE_DETAILS</script>"
        result = self.run_report()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "source_validation_error")
        self.assertNotIn("SYNTHETIC_PRIVATE", json.dumps(result))
        self.assertTrue(self.clients[0].sessions[0].closed)

    def test_compact_keeps_exact_values_evidence_status_and_reduces_serialized_size(self):
        result = self.run_report()
        before = copy.deepcopy(result)
        compact = report.compact_result(result)
        for key in ("sources", "columns", "pages", "status", "complete", "completeness",
                    "validation_warnings", "validation_warning_count", "generation", "page_coverage",
                    "selectors", "filters", "granularity", "performance"):
            with self.subTest(field=key):
                self.assertEqual(compact[key], result[key])
        for original, projected in zip(result["rows"], compact["rows"]):
            for key in ("values", "dimensions", "status", "source_page_index", "source_request_page",
                        "row_number", "source_page_row_number"):
                self.assertEqual(projected[key], original[key])
            self.assertNotIn("cells", projected)
            self.assertNotIn("cell_sources", projected)
        self.assertLess(len(json.dumps(compact, ensure_ascii=False).encode()),
                        len(json.dumps(result, ensure_ascii=False).encode()))
        self.assertEqual(result, before)

    def test_compact_preserves_errors_and_leaves_other_commands_intact(self):
        self.config["fail_page"] = 2
        result = self.run_report()
        compact = report.compact_result(result)
        for key in ("status", "error", "sources", "complete", "completeness", "validation_warnings"):
            self.assertEqual(compact[key], result[key])
        non_report = {"command": "attachments", "rows": [{"cells": ["fixture"], "keys": ["key"]}]}
        non_report_compact = report.compact_result(non_report)
        self.assertEqual(non_report_compact, non_report)
        non_report_compact["rows"][0]["cells"].clear()
        self.assertEqual(non_report["rows"][0]["cells"], ["fixture"])

    def test_invalid_inputs_fail_before_creating_a_client(self):
        for overrides in ({"school_names": "시험대학 0"}, {"school_names": [None]},
                          {"school_names": [""]}, {"school_names": ["valid"] * 101},
                          {"dept_names": [False]}, {"max_pages": 0}, {"offset": -1},
                          {"year": 2026}, {"item": "unknown"}, {"level": "other"}):
            with self.subTest(overrides=overrides):
                result = self.run_report(**overrides)
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["error"]["code"], "invalid_input")
                self.assertEqual(result["sources"], [])
        self.assertEqual(self.clients, [])

    def test_old_cli_syntax_and_repeated_names_with_compact_output(self):
        old_args = ["report", "--year", "2026", "--division", "02", "--item", "1",
                    "--level", "department", "--school-name", "시험대학 0"]
        parsed = report.build_parser().parse_args(old_args)
        legacy = report.run_command(parsed)
        self.assertEqual(legacy["filters"]["dimensions"], {"schoolName": "시험대학 0"})
        stdout = io.StringIO()
        with patch.object(sys, "stdout", stdout):
            exit_code = report.main(old_args + ["--school-name", "시험대학 2", "--compact"])
        result = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["returned_row_count"], 10)
        self.assertEqual(result["output_format"], "compact")
        self.assertEqual(result["filters"]["match"], "exact_any")
        self.assertEqual(result["filters"]["dimensions"]["schoolName"], ["시험대학 0", "시험대학 2"])


if __name__ == "__main__":
    unittest.main()
