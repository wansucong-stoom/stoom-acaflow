"""Offline protocol, failure, provenance, and one-file write tests."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.parse
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "academyinfo-flow" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import live_files


FILE = {"std_dta_div_cd": "042", "accm_schl_div_cd": "02",
        "file_dtl_nm": "official_selected_file.xlsx", "file_nm": "학과별 입학정원.xlsx",
        "file_crtn_stt_dtm": "2026-10-12", "file_pth_nm": "/infofile/SCHEDULER/EXCEL/",
        "item_id": 29}


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def xlsx_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '</Types>')
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="자료" sheetId="1"/></sheets></workbook>')
        # Some actual exports report dimension A1 despite having thousands of
        # rows. Download validation must not infer sheet completeness from it.
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<dimension ref="A1"/><sheetData><row r="35"><c r="AI35"><v>1</v></c></row></sheetData></worksheet>')
    return buffer.getvalue()


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, *, timeout):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("Unexpected network request")
        expected_url, body, headers, status = self.responses.pop(0)
        if request.full_url != expected_url:
            raise AssertionError("Unexpected endpoint")
        response = io.BytesIO(body)
        response.code = status
        response.headers = headers
        response.geturl = lambda: request.full_url
        return response


def catalog_responses(rows=None):
    return [(live_files.CATALOG_URL, json_bytes({"resultList": rows if rows is not None else [FILE]}),
             {"Content-Type": "application/json;charset=UTF-8"}, 200)]


def download_responses(*, purpose=None, body=None, filename=None, content_type=None):
    name = urllib.parse.quote(filename or FILE["file_nm"])
    return [(live_files.PURPOSE_URL, json_bytes(purpose if purpose is not None else {"result": "success"}),
             {"Content-Type": "application/json"}, 200),
            (live_files.DOWNLOAD_URL, body if body is not None else xlsx_bytes(),
             {"Content-Type": content_type or "application/x-msdownload;charset=UTF-8",
              "Content-Disposition": 'attachment; filename="' + name + '"'}, 200)]


class LiveFileTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(__file__).resolve().parents[1]
        self.directory = tempfile.TemporaryDirectory(prefix="test-live-files-", dir=workspace)
        self.assertTrue(Path(self.directory.name).resolve().is_relative_to(workspace))
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / "selected.xlsx"

    def run_download(self, responses, **extra):
        opener = FakeOpener(responses)
        client = live_files.FileClient(opener=opener, interval=0)
        args = {"command": "download", "division": "02", "code": "042", "output": str(self.output), **extra}
        return live_files.run_command(args, network_client=client), opener

    def test_one_selected_file_uses_exact_protocol_and_preserves_provenance(self):
        result, opener = self.run_download(catalog_responses() + download_responses())
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["complete"])
        self.assertEqual(len(opener.requests), 3)
        self.assertEqual([request.method for request in opener.requests], ["POST", "POST", "POST"])
        purpose = dict(urllib.parse.parse_qsl(opener.requests[1].data.decode(), keep_blank_values=True))
        self.assertEqual(purpose, {"schlDivCd": "02", "itemId": "29", "dwldUsrDivCd": "008",
            "dwldEtcUsrNm": "대학 공시자료 연구", "dwldPrpsCd": "003", "dwldEtcPrpsCtnt": "",
            "dwldDtlCtnt": "전국 대학 학과 및 입학정원 변화 비교 분석"})
        download = dict(urllib.parse.parse_qsl(opener.requests[2].data.decode(), keep_blank_values=True))
        self.assertEqual(download, {"schl_div_cd": "02", "searchValue": "", "file_nm": FILE["file_nm"],
            "file_path": FILE["file_pth_nm"], "file_dtl_nm": FILE["file_dtl_nm"], "std_dta_div_cd": "042"})
        self.assertEqual(result["selected_file"], FILE)
        self.assertEqual(result["catalog_metadata_origin"], "fresh_lookup")
        self.assertEqual(result["data"]["sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertEqual(result["sources"][-1]["raw_sha256"], result["data"]["sha256"])
        self.assertTrue(all(source["retrieved_utc"] for source in result["sources"]))
        self.assertIn("lookup_started_utc", result)
        self.assertIn("lookup_completed_utc", result)
        self.assertNotIn("<html>", json.dumps(result))

    def test_catalog_outputs_only_selected_public_fields_and_can_be_partial(self):
        first = {**FILE, "cookie": "private-value", "sql": "private-query", "html": "<html>private</html>"}
        second = {**FILE, "std_dta_div_cd": "043", "item_id": 30}
        opener = FakeOpener(catalog_responses([first, second]))
        result = live_files.run_command({"command": "catalog", "division": "02", "keyword": "학과", "limit": 1},
            network_client=live_files.FileClient(opener=opener, interval=0))
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["complete"])
        self.assertTrue(result["completeness"]["source_complete"])
        self.assertFalse(result["completeness"]["returned_complete"])
        self.assertEqual(result["rows"], [FILE])
        self.assertNotIn("private", json.dumps(result))
        params = dict(urllib.parse.parse_qsl(opener.requests[0].data.decode(), keep_blank_values=True))
        self.assertEqual(params, {"schl_div_cd": "02", "searchValue": "학과"})

    def test_purpose_failure_stops_before_download_or_write(self):
        responses = catalog_responses() + download_responses(purpose={"result": "failure", "cookie": "private-value"})
        result, opener = self.run_download(responses)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["phase"], "purpose")
        self.assertEqual(len(opener.requests), 2)
        self.assertFalse(self.output.exists())
        self.assertNotIn("private-value", json.dumps(result))

    def test_wrong_html_bad_zip_and_wrong_attachment_are_rejected(self):
        examples = ({"body": b"<html>private-value</html>", "content_type": "text/html"},
                    {"body": b"PK\x03\x04invalid zip"},
                    {"filename": "different.xlsx"},
                    {"body": b"PK\x03\x04invalid zip", "content_type": "text/html"})
        for example in examples:
            with self.subTest(example=tuple(example)):
                result, _ = self.run_download(catalog_responses() + download_responses(**example))
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["error"]["phase"], "validation")
                self.assertFalse(self.output.exists())
                self.assertNotIn("private-value", json.dumps(result))

    def test_missing_actual_item_id_or_unknown_code_does_not_guess(self):
        bad = deepcopy(FILE)
        del bad["item_id"]
        result, opener = self.run_download(catalog_responses([bad]))
        self.assertEqual(result["status"], "error")
        self.assertEqual(len(opener.requests), 1)
        result, opener = self.run_download(catalog_responses(), code="not-in-live-list")
        self.assertEqual(result["status"], "error")
        self.assertEqual(len(opener.requests), 1)
        self.assertFalse(self.output.exists())

    def test_existing_and_relative_output_are_rejected_before_requests(self):
        self.output.write_bytes(b"keep this existing file")
        for output in (str(self.output), "relative.xlsx", str(Path(self.directory.name) / "wrong.txt")):
            with self.subTest(output=output):
                result, opener = self.run_download([], output=output)
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["error"]["phase"], "input")
                self.assertEqual(opener.requests, [])
        self.assertEqual(self.output.read_bytes(), b"keep this existing file")

    def test_same_question_catalog_input_reuses_only_public_metadata(self):
        client = live_files.FileClient(opener=FakeOpener(catalog_responses()), interval=0)
        catalog = live_files.run_command({"command": "catalog", "division": "02"}, network_client=client)
        catalog["cookie"] = "private-value"
        catalog["sources"][0]["cookie"] = "private-value"
        catalog_path = Path(self.directory.name) / "fresh-catalog.json"
        catalog_path.write_bytes(json_bytes(catalog))
        result, opener = self.run_download(download_responses(), catalog_input=str(catalog_path))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(result["catalog_metadata_origin"], "same_question_input")
        self.assertTrue(result["sources"][0]["reused_for_same_question"])
        self.assertEqual(result["sources"][0]["retrieved_utc"], catalog["sources"][0]["retrieved_utc"])
        self.assertNotIn("private-value", json.dumps(result))

    def test_archive_manifest_and_unverified_catalog_input_are_rejected(self):
        valid = live_files.run_command({"command": "catalog", "division": "02"},
            network_client=live_files.FileClient(opener=FakeOpener(catalog_responses()), interval=0))
        examples = [{"results": [{"sourceItem": FILE}], "completed": 42},
                    {**valid, "complete": False}, {**valid, "mode": "archive"}]
        bad_source = deepcopy(valid)
        bad_source["sources"][0]["raw_sha256"] = "invalid"
        examples.append(bad_source)
        for index, example in enumerate(examples):
            with self.subTest(index=index):
                path = Path(self.directory.name) / "input.json"
                path.write_bytes(json_bytes(example))
                result, opener = self.run_download([], catalog_input=str(path))
                self.assertEqual(result["status"], "error")
                self.assertEqual(opener.requests, [])
                self.assertFalse(self.output.exists())

    def test_duplicate_codes_and_metadata_path_traversal_are_rejected(self):
        for rows in ([FILE, FILE], [{**FILE, "file_pth_nm": "/infofile/../private/"}],
                     [{**FILE, "file_dtl_nm": "../wrong.xlsx"}], [{**FILE, "accm_schl_div_cd": "01"}]):
            with self.subTest(rows=rows):
                result, _ = self.run_download(catalog_responses(rows))
                self.assertEqual(result["status"], "error")
                self.assertFalse(self.output.exists())

    def test_http_and_size_failure_keep_bounded_provenance_without_body(self):
        opener = FakeOpener([(live_files.CATALOG_URL, b"<html>private-value</html>", {"Content-Type": "text/html"}, 503)])
        client = live_files.FileClient(opener=opener, interval=0)
        with self.assertRaises(live_files.SourceError):
            client.request(live_files.CATALOG_URL, {"schl_div_cd": "02", "searchValue": ""})
        self.assertEqual(client.sources[0]["response_status"], 503)
        self.assertNotIn("private-value", json.dumps(client.sources))
        small = live_files.FileClient(opener=FakeOpener([(live_files.PAGE_URL, b"A" * 100, {}, 200)]),
                                      max_bytes=32, interval=0)
        with self.assertRaises(live_files.SourceError):
            small.request(live_files.PAGE_URL, method="GET")
        self.assertEqual(small.sources[0]["response_bytes"], 33)

    def test_legacy_utf8_and_rfc5987_attachment_names_are_supported(self):
        for disposition in ('attachment; filename="' + FILE["file_nm"].encode("utf-8").decode("latin1") + '"',
            "attachment; filename*=UTF-8''" + urllib.parse.quote(FILE["file_nm"])):
            with self.subTest(kind=disposition[:30]):
                live_files._xlsx(xlsx_bytes(), {"content_type": "application/x-msdownload",
                    "content_disposition": disposition}, FILE)

    def test_cli_observes_route_without_changing_query_status_on_write_failure(self):
        result = {"status": "ok", "complete": True}
        with patch.object(live_files, "run_command", return_value=result), \
             patch("route_registry.observe_result", side_effect=OSError("private-value")), \
             patch.object(sys, "stdout", io.StringIO()) as output:
            code = live_files.main(["catalog", "--division", "02"])
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["route_registry"]["status"], "unavailable")
        self.assertNotIn("private-value", output.getvalue())


if __name__ == "__main__":
    unittest.main()
