"""Network-free batch regressions: reuse boundaries, evidence, and safe input."""
from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "academyinfo-flow" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import live_batch
import live_report
from academyinfo_archive.viewer_data import ViewerDataClient, DATA_URL


def report_query(**changes):
    return {"command": "report", "year": "2026", "division": "02", "item": "001",
            "level": "school", **changes}


def public_result(command="schools", **changes):
    return {"command": command, "status": "ok", "complete": True,
            "sources": [{"source_url": "https://www.academyinfo.go.kr/",
                         "raw_sha256": "a" * 64, "retrieved_utc": "2026-10-11T16:00:00+00:00"}],
            "rows": [{"name": "한남대학교", "value": "0"}],
            "completeness": {"source_complete": True, "returned_complete": True}, **changes}


class BatchInputTests(unittest.TestCase):
    def test_invalid_later_query_prevents_all_live_calls(self):
        handler, factory = Mock(), Mock()
        result = live_batch.run_queries([
            {"command": "schools", "year": "2026"},
            report_query(password="private-value"),
        ], json_handler=handler, report_handler=handler, batch_factory=factory)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["query_index"], 1)
        self.assertEqual(result["results"], [])
        self.assertNotIn("private-value", json.dumps(result))
        handler.assert_not_called()
        factory.assert_not_called()

    def test_invalid_schema_and_selector_types(self):
        malformed = [None, [], {}, {"queries": [], "token": "private-value"},
                     [{"command": "pdf"}], [{"command": "attachments"}],
                     [{"command": "schools"}], [{"command": "scope", "division": []}],
                     [{"command": "metric", "year": "2026", "school_code": 1}],
                     [report_query(offset=-1)], [report_query(max_pages=True)],
                     [report_query(limit=1.0)], [report_query(school_names="한남대학교")],
                     [report_query(school_names=[""])],
                     [report_query(school_names=["대학"] * 101)],
                     [{"command": "scope"}] * (live_batch.MAX_QUERIES + 1)]
        for payload in malformed:
            with self.subTest(payload=payload):
                handler = Mock()
                result = live_batch.run_queries(payload, json_handler=handler, report_handler=handler)
                self.assertEqual(result["error"]["code"], "invalid_input")
                self.assertFalse(result["complete"])
                handler.assert_not_called()

    def test_public_selectors_are_normalized_without_mutating_input(self):
        payload = {"queries": [report_query(max_pages="100", school_names=["한남대학교", "학교 B"])]}
        original = deepcopy(payload)
        queries = live_batch.validate_queries(payload)
        self.assertEqual(queries[0]["item"], "1")
        self.assertEqual(queries[0]["max_pages"], 100)
        self.assertEqual(queries[0]["school_names"], ["한남대학교", "학교 B"])
        self.assertEqual(payload, original)

    def test_cli_rejects_invalid_json_without_traceback_or_untrusted_values(self):
        bad_inputs = [b"not-json-private-value", b'{"queries":[],"queries":[]}',
                      b'{"queries":[{"command":"scope","year":NaN}]}',
                      b'[{"command":"scope","cookie":"private-value"}]', b"\xff"]
        for content in bad_inputs:
            with self.subTest(content=content):
                process = subprocess.run([sys.executable, str(SCRIPTS / "live_batch.py")],
                                         input=content, capture_output=True, timeout=10)
                self.assertEqual(process.returncode, 2)
                result = json.loads(process.stdout)
                self.assertEqual(result["error"]["code"], "invalid_input")
                self.assertEqual(process.stderr, b"")
                self.assertNotIn(b"private-value", process.stdout)

    def test_cli_rejects_oversized_files_and_missing_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queries.json"
            path.write_bytes(b" " * (live_batch.MAX_INPUT_BYTES + 1))
            for target in (path, path.with_name("private-value.json")):
                process = subprocess.run([sys.executable, str(SCRIPTS / "live_batch.py"),
                                          "--input", str(target)], capture_output=True, timeout=10)
                self.assertEqual(process.returncode, 2)
                self.assertEqual(json.loads(process.stdout)["error"]["code"], "invalid_input")
                self.assertNotIn(b"private-value", process.stdout + process.stderr)

    def test_cli_full_output_option_and_success_exit(self):
        for flags, expected in (([], False), (["--full-output"], True)):
            with self.subTest(flags=flags):
                with patch.object(sys, "stdin", io.StringIO('[{"command":"scope"}]')), \
                     patch.object(sys, "stdout", io.StringIO()) as output, \
                     patch.object(live_batch, "run_queries", return_value={
                         "status": "ok", "complete": True}) as runner:
                    self.assertEqual(live_batch.main(flags), 0)
                    self.assertEqual(json.loads(output.getvalue())["status"], "ok")
                    runner.assert_called_once_with([{"command": "scope"}], full_output=expected)


class BatchExecutionTests(unittest.TestCase):
    def test_equivalent_json_queries_run_once_and_results_are_independent(self):
        calls = []

        def handler(query):
            calls.append(query)
            return public_result(rows=[{"name": query["name"], "value": "0"}])

        queries = [{"command": "schools", "year": "2026", "name": "한남"},
                   {"command": "schools", "year": "2026", "name": "한남", "max_pages": "1000"},
                   {"command": "schools", "year": "2026", "name": "다른 대학"}]
        result = live_batch.run_queries({"queries": queries}, json_handler=handler)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["performance"]["repeated_json_queries_avoided"], 1)
        self.assertEqual([item["rows"][0]["name"] for item in result["results"]],
                         ["한남", "한남", "다른 대학"])
        self.assertTrue(result["complete"])
        result["results"][0]["rows"][0]["value"] = "changed"
        self.assertEqual(result["results"][1]["rows"][0]["value"], "0")

    def test_repeated_invocations_always_fetch_fresh_json(self):
        handler = Mock(return_value=public_result())
        queries = [{"command": "schools", "year": "2026"}] * 2
        first = live_batch.run_queries(queries, json_handler=handler)
        second = live_batch.run_queries(queries, json_handler=handler)
        self.assertEqual(handler.call_count, 2)
        self.assertEqual(first["performance"]["repeated_queries_avoided"], 1)
        self.assertEqual(second["performance"]["repeated_queries_avoided"], 1)

    def test_mixed_partial_and_failed_queries_keep_order_and_evidence(self):
        warning = "일부 페이지만 반환했습니다."

        def handler(query):
            if query["command"] == "info":
                raise RuntimeError("private-value cookie=do-not-print")
            return public_result(query["command"], status="partial", complete=False,
                                 validation_warnings=[warning], completeness={
                                     "source_complete": False, "returned_complete": True})

        info = {"command": "info", "year": "2026", "school_code": "0000001",
                "dept_code": "0000002", "major_code": "0000003"}
        result = live_batch.run_queries([
            {"command": "schools", "year": "2026"}, info,
            {"command": "schools", "year": "2026"}], json_handler=handler)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["complete"])
        self.assertEqual([item["command"] for item in result["results"]], ["schools", "info", "schools"])
        self.assertEqual(result["results"][0]["validation_warnings"], [warning])
        self.assertEqual(result["results"][2]["sources"], result["results"][0]["sources"])
        self.assertFalse(result["results"][2]["completeness"]["source_complete"])
        self.assertEqual(result["completeness"]["error_query_count"], 1)
        self.assertNotIn("private-value", json.dumps(result))

    def test_identical_failures_are_not_silently_retried(self):
        handler = Mock(side_effect=RuntimeError("private-value"))
        result = live_batch.run_queries([{ "command": "scope", "year": "2026"}] * 2,
                                        json_handler=handler)
        self.assertEqual(handler.call_count, 1)
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["complete"])
        self.assertEqual(result["performance"]["repeated_json_queries_avoided"], 1)
        self.assertNotIn("private-value", json.dumps(result))

    def test_report_batch_initialization_failure_does_not_block_json(self):
        factory = Mock(side_effect=RuntimeError("private-value"))
        report = Mock()
        result = live_batch.run_queries([report_query(), {"command": "scope", "year": "2026"}],
                                        batch_factory=factory, report_handler=report,
                                        json_handler=lambda q: public_result(q["command"]))
        self.assertEqual(result["status"], "partial")
        self.assertEqual([item["status"] for item in result["results"]], ["error", "ok"])
        report.assert_not_called()
        self.assertNotIn("private-value", json.dumps(result))

    def test_actual_report_context_reuses_sources_and_keeps_compact_evidence(self):
        combined = {
            "rows": [{"dimensions": {"schoolName": name},
                      "values": {"value": "0", "null": None, "empty": "", "dash": "-"},
                      "keys": {"duplicate": name}, "cells": [{"text": "0"}],
                      "cell_sources": [{"source_col_no": 0}], "source_page_index": index,
                      "source_sha256": str(index) * 64}
                     for index, name in enumerate(("한남대학교", "학교 B"))],
            "columns": [{"key": "value", "header_path": ["원천 값"]}],
            "status": "complete", "warnings": [],
        }

        def catalog(args, client, result, batch):
            result["catalog_item"] = {"mjr_use_step_cd": "1"}

        def collect(args, client, result, *, capture, performance):
            result["sources"] = deepcopy(public_result()["sources"])
            result["generation"] = {"fetched_pages": 2, "source_total_pages": 2}
            capture.update(combined=deepcopy(combined), source_complete=True)
            live_report._numeric_result(args, result, capture["combined"], True)

        queries = [report_query(school_name="한남대학교"),
                   {"command": "scope", "year": "2026"},
                   report_query(school_name="학교 B"),
                   report_query(school_name="한남대학교", max_pages=2)]
        with patch.object(live_report, "ViewerDataClient"), \
             patch.object(live_report, "_catalog", side_effect=catalog), \
             patch.object(live_report, "_collect", side_effect=collect) as fetch:
            compact = live_batch.run_queries(queries, json_handler=lambda q: public_result(q["command"]))
            full = live_batch.run_queries(queries, full_output=True,
                                          json_handler=lambda q: public_result(q["command"]))
        self.assertEqual(fetch.call_count, 4)  # Two sources per fresh invocation.
        self.assertEqual(compact["status"], "ok")
        self.assertEqual(compact["performance"]["repeated_report_sources_avoided"], 1)
        self.assertEqual(compact["performance"]["source_report_fetches"], 2)
        self.assertEqual(compact["results"][2]["rows"][0]["dimensions"]["schoolName"], "학교 B")
        self.assertTrue(compact["results"][2]["performance"]["source_reused"])
        self.assertEqual(compact["results"][0]["sources"], compact["results"][2]["sources"])
        self.assertEqual(compact["results"][0]["columns"], full["results"][0]["columns"])
        self.assertEqual(compact["results"][0]["completeness"], full["results"][0]["completeness"])
        for compact_item, full_item in zip(compact["results"], full["results"]):
            if compact_item["command"] != "report":
                continue
            self.assertNotIn("cells", compact_item["rows"][0])
            self.assertIn("cells", full_item["rows"][0])
            self.assertEqual(compact_item["rows"][0]["values"], full_item["rows"][0]["values"])
            self.assertEqual(compact_item["rows"][0]["source_sha256"],
                             full_item["rows"][0]["source_sha256"])
        self.assertGreaterEqual(compact["performance"]["stages_seconds"]["total"], 0)


class BatchPacingTests(unittest.TestCase):
    """Exercise the real JSON and HTTP adapters against a fake clock/opener."""

    def setUp(self):
        self.now = 100.0
        self.request_times = []
        self.clients = []
        self.contexts = []
        self.addCleanup(patch.stopall)
        patch("academyinfo_archive.direct.time.monotonic", side_effect=lambda: self.now).start()
        patch("academyinfo_archive.direct.time.sleep", side_effect=self.sleep).start()
        patch.object(live_report, "ViewerDataClient", side_effect=self.new_client).start()

    def sleep(self, seconds):
        self.now += seconds

    def new_client(self):
        client = ViewerDataClient(opener=self, interval=1.0)
        self.clients.append(client)
        return client

    def new_context(self):
        context = live_report.ReportBatch()
        self.contexts.append(context)
        return context

    def open(self, request, *, timeout):
        self.request_times.append(self.now)
        body = json.dumps({"resultList": [{"schl_id": "0000001", "schl_nm": "시험대학"}],
                           "paginationInfo": {"totalPageCount": 1, "currentPageNo": 1,
                                              "totalRecordCount": 1}}).encode()
        response = io.BytesIO(body)
        response.code = 200
        response.headers = {"Content-Type": "application/json"}
        response.geturl = lambda: request.full_url
        return response

    def test_distinct_json_queries_keep_interval_and_separate_evidence(self):
        queries = [{"command": "schools", "year": "2026", "name": name}
                   for name in ("학교 A", "학교 B")]
        result = live_batch.run_queries(queries, batch_factory=self.new_context)
        self.assertTrue(result["complete"])
        self.assertEqual(len(self.clients), 1)
        self.assertEqual(self.request_times, [100.0, 101.0])
        self.assertEqual([item["sources"][0]["public_parameters"]["searchVal"]
                          for item in result["results"]], ["학교 A", "학교 B"])
        self.assertTrue(all(len(item["sources"]) == 1 for item in result["results"]))
        self.assertTrue(self.contexts[0].closed)
        self.assertIsNone(self.contexts[0]._client)

    def test_json_report_and_report_json_boundaries_keep_interval(self):
        def report_handler(query, *, batch):
            batch.client()._runtime_post(DATA_URL, {}, {})
            return public_result("report")

        result = live_batch.run_queries([
            {"command": "schools", "year": "2026", "name": "학교 A"},
            report_query(),
            {"command": "schools", "year": "2026", "name": "학교 B"},
        ], report_handler=report_handler, batch_factory=self.new_context)
        self.assertTrue(result["complete"])
        self.assertEqual(len(self.clients), 1)
        self.assertEqual(self.request_times, [100.0, 101.0, 102.0])
        self.assertEqual([len(item["sources"]) for item in result["results"]], [1, 1, 1])

    def test_duplicate_json_has_no_request_and_new_invocation_gets_new_client(self):
        query = {"command": "schools", "year": "2026"}
        first = live_batch.run_queries([query, query], batch_factory=self.new_context)
        second = live_batch.run_queries([query], batch_factory=self.new_context)
        self.assertTrue(first["complete"] and second["complete"])
        self.assertEqual(len(self.request_times), 2)
        self.assertEqual(len(self.clients), 2)
        self.assertIsNot(self.clients[0], self.clients[1])
        self.assertTrue(all(context.closed and context._client is None
                            for context in self.contexts))
        self.assertEqual(first["performance"]["repeated_json_queries_avoided"], 1)


if __name__ == "__main__":
    unittest.main()
