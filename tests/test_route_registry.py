"""Route memory regressions with local metadata fixtures; never contact a server."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "academyinfo-flow" / "scripts" / "route_registry.py"
SPEC = importlib.util.spec_from_file_location("route_registry_under_test", SCRIPT)
registry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(registry)

CATALOG_URL = "https://m.academyinfo.go.kr/main/main0780/selectItemList.do"
REPORT_URL = "https://academyinfo.go.kr:443/NewAcInfo.do"
STAMP = "2026-10-12T00:00:00+00:00"
SHA = "a" * 64


def source(url=REPORT_URL, **overrides):
    return {"source_url": url, "method": "POST",
            "public_parameters": {"pubYear": "2026", "schoolDivision": "02", "itemId": "27",
                                  "level": "department", "language": "ko"},
            "retrieved_utc": STAMP, "raw_sha256": SHA, "response_status": 200,
            "response_content_type": "application/xml", **overrides}


def result(**overrides):
    return {"command": "report", "status": "ok", "complete": True,
            "completeness": {"source_complete": True, "returned_complete": True},
            "query": {"year": "2026", "division": "02", "item": "27", "level": "department"},
            "catalog_item": {"pgm_estn_nm": "4-다. 신입생 충원 현황"},
            "sources": [source()], "rows": [{"value": "PRIVATE_NUMERIC_ROWS_12345"}], **overrides}


def catalog(title="4-다. 신입생 충원 현황", year="2026", item="27", **overrides):
    return {"command": "catalog", "status": "ok", "complete": True,
            "completeness": {"source_complete": True},
            "sources": [source(CATALOG_URL, public_parameters={"svyYr": year, "schlDivCd": "02"})],
            "rows": [{"svy_yr": year, "schl_div_cd": "02", "item_id": item,
                      "pgm_estn_nm": title, "mjr_use_step_cd": "2", "pdf_use_yn": "N"}], **overrides}


class RouteRegistryTests(unittest.TestCase):
    def setUp(self):
        self.state = registry.empty_registry()

    def test_school_detail_bootstrap_routes_keep_distinct_school_identity(self):
        bootstrap = 'https://academyinfo.go.kr/uipnh/unt/unmcom/RdViewer.do'
        for school in ('0000001', '0000002'):
            registry.record_result(self.state, result(sources=[source(bootstrap, public_parameters={
                'paramSvyYr': '2026', 'paramSchlDivCd': '02', 'paramItemId': '27',
                'paramFormClftCd': '60', 'paramSchlCd': school, 'paramZoneCd': '99'})]))
        self.assertEqual(len(self.state['routes']), 2)
        self.assertEqual({r['scope']['school_code'] for r in self.state['routes']}, {'0000001', '0000002'})
        for route in self.state['routes']:
            self.assertEqual(route['scope']['form'], '60')
            self.assertEqual(route['scope']['level'], 'department')
            self.assertEqual(route['public_parameters']['paramZoneCd'], '99')
        # Generalization may not transfer school-specific parameters to a
        # different catalog item merely because the path and keys match.
        registry.record_result(self.state, catalog(item='99'))
        registry.learn_families(self.state)
        candidates = registry.lookup(self.state, item='99', year='2026', division='02', level='department')
        self.assertTrue(all('paramSchlCd' not in row['public_parameters'] for row in candidates['routes']))

    def test_school_detail_without_a_valid_code_is_not_remembered_as_a_global_route(self):
        bootstrap = 'https://academyinfo.go.kr/uipnh/unt/unmcom/RdViewer.do'
        for invalid in ('', 'wrong', '123', '00000001'):
            registry.record_result(self.state, result(sources=[source(bootstrap, public_parameters={
                'paramSvyYr': '2026', 'paramSchlDivCd': '02', 'paramItemId': '27',
                'paramFormClftCd': '60', 'paramSchlCd': invalid, 'paramZoneCd': '99'})]))
        self.assertEqual(self.state['routes'], [])

    def test_failure_keeps_last_success_and_duplicate_is_idempotent(self):
        self.assertEqual(registry.record_result(self.state, result()), 1)
        route = self.state["routes"][0]
        successful = copy.deepcopy(route["last_success"])
        failed = result(status="error", complete=False, sources=[source(
            retrieved_utc="2026-10-13T00:00:00Z", response_status=503, raw_sha256="b" * 64)])
        self.assertEqual(registry.record_result(self.state, failed), 1)
        self.assertEqual(registry.record_result(self.state, failed), 0)
        self.assertEqual(route["status"], "failed")
        self.assertTrue(route["support_verified"])
        self.assertEqual(route["last_success"], successful)
        self.assertEqual(len(route["observations"]), 2)

    def test_partial_http200_never_promotes_support(self):
        registry.record_result(self.state, result(status="partial", complete=False,
            completeness={"source_complete": False, "returned_complete": True}))
        route = self.state["routes"][0]
        self.assertEqual(route["status"], "partial")
        self.assertFalse(route["support_verified"])
        self.assertIsNone(route["last_success"])

    def test_unknown_command_or_status_is_not_success(self):
        for changes in ({"status": "supported"}, {"command": "unknown"}, {"complete": False},
                        {"completeness": {"source_complete": False}}):
            state = registry.empty_registry()
            registry.record_result(state, result(**changes))
            self.assertFalse(state["routes"][0]["support_verified"])

    def test_catalog_success_does_not_prove_report_support(self):
        registry.record_result(self.state, catalog())
        registry.learn_families(self.state)
        selected = registry.lookup(self.state, item="27", year="2026", division="02", level="department")
        self.assertEqual(selected["returned_count"], 1)
        candidate = selected["routes"][0]
        self.assertEqual(candidate["status"], "candidate")
        self.assertFalse(candidate["support_verified"])
        self.assertEqual(self.state["routes"][0]["status"], "catalog_confirmed")
        self.assertFalse(self.state["routes"][0]["support_verified"])

    def test_no_numeric_rows_cookies_sql_sessions_or_viewer_urls(self):
        private = "SENSITIVE_RUNTIME_MARKER"
        payload = result(sources=[source(
            source_url=REPORT_URL + "?pKey=" + private,
            public_parameters={**source()["public_parameters"], "cookie": private, "pKey": private,
                "strQuery": "select secret from users", "schema_text": private,
                "searchVal": "select password from users", "unknown": private},
            final_url="https://academyinfo.go.kr/uipnh/unt/unmcom/RdViewer.do?key=" + private),
            source("https://academyinfo.go.kr/uipnh/unt/unmcom/RdViewer.do?key=" + private)],
            session={"key": private}, data={"secret": private})
        registry.record_result(self.state, payload)
        serialized = json.dumps(self.state)
        self.assertNotIn(private, serialized)
        self.assertNotIn("PRIVATE_NUMERIC", serialized)
        self.assertNotIn("select password", serialized)
        self.assertNotIn("RdViewer", serialized)
        self.assertNotIn("schema_text", serialized)
        self.assertEqual(len(self.state["routes"]), 1)
        self.assertEqual(self.state["routes"][0]["url"], "https://academyinfo.go.kr/NewAcInfo.do")

    def test_pattern_generation_only_uses_catalog_confirmed_ids_years_levels(self):
        registry.record_result(self.state, result())
        registry.import_catalog(self.state, catalog(item="31", year="2025", title="재적 학생 현황"))
        registry.learn_families(self.state)
        candidate = registry.lookup(self.state, item="31", year="2025", level="school")["routes"][0]
        self.assertEqual(candidate["candidate_basis"], "verified_family_and_catalog")
        self.assertEqual(candidate["public_parameters"]["itemId"], "31")
        self.assertEqual(candidate["public_parameters"]["pubYear"], "2025")
        self.assertEqual(candidate["public_parameters"]["level"], "school")
        self.assertFalse(candidate["support_verified"])
        self.assertEqual(registry.lookup(self.state, item="999", year="2025")["total_matches"], 0)
        self.assertEqual(registry.lookup(self.state, item="31", year="2027")["total_matches"], 0)
        registry.import_catalog(self.state, catalog(item="40", status="partial", complete=False))
        self.assertEqual(registry.lookup(self.state, item="40")["total_matches"], 0)

    def test_no_cross_item_school_or_file_parameter_transfer(self):
        registry.record_result(self.state, result(sources=[source(public_parameters={
            **source()["public_parameters"], "schlId": "0000123"})]))
        registry.import_catalog(self.state, catalog(item="31"))
        registry.learn_families(self.state)
        self.assertEqual(registry.lookup(self.state, item="31")["total_matches"], 0)

    def test_renames_and_utc_time_filters(self):
        registry.import_catalog(self.state, catalog(title="옛 제목"))
        registry.import_catalog(self.state, catalog(title="새 제목", sources=[source(
            CATALOG_URL, retrieved_utc="2026-10-13T09:00:00+09:00",
            public_parameters={"svyYr": "2026", "schlDivCd": "02"})]))
        self.assertEqual(len(self.state["catalog"]), 1)
        self.assertEqual(self.state["catalog"][0]["titles"], ["옛 제목", "새 제목"])
        self.assertEqual(registry.lookup(self.state, keyword="옛 제목", level="school",
            since="2026-10-13T00:00:00Z")["total_matches"], 1)
        self.assertEqual(registry.lookup(self.state, keyword="새 제목", level="school",
            until="2026-10-12T23:59:59Z")["total_matches"], 0)
        with self.assertRaises(registry.RegistryError):
            registry.lookup(self.state, since="2026-10-12")

    def test_out_of_order_failures_do_not_replace_latest_success(self):
        registry.record_result(self.state, result(sources=[source(retrieved_utc="2026-10-14T00:00:00Z")]))
        registry.record_result(self.state, result(status="error", sources=[source(retrieved_utc=STAMP)]))
        self.assertEqual(self.state["routes"][0]["status"], "verified")

    def test_manifest_keeps_only_public_download_route_and_evidence(self):
        manifest = {"sourcePage": "https://www.academyinfo.go.kr/main/main0830/main0830.do",
            "results": [{"code": "017", "success": True, "retrievedAt": STAMP,
                "sourceSha256": SHA, "sourcePath": "PRIVATE_LOCAL_FILE",
                "sourceItem": {"item_id": 27, "secret": "PRIVATE_SECRET"},
                "downloadRequest": {"url": "https://www.academyinfo.go.kr/main/main0830/FileDown.do",
                    "method": "POST", "form": {"schl_div_cd": "02", "searchValue": "",
                    "file_nm": "4-다. 신입생 충원 현황.xlsx", "file_path": "/infofile/SCHEDULER/EXCEL/",
                    "file_dtl_nm": "CMN81_017.xlsx", "std_dta_div_cd": "017", "cookie": "PRIVATE_COOKIE"}},
                "steps": [{"action": "download", "status": 200, "headers": {"Set-Cookie": "PRIVATE_COOKIE"}}],
                "summary": {"rowCount": 12345, "value": "PRIVATE_NUMERIC"}}]}
        registry.import_payload(self.state, manifest)
        downloads = [r for r in self.state["routes"] if r["kind"] == "official_download"]
        self.assertEqual(len(downloads), 1)
        self.assertTrue(downloads[0]["support_verified"])
        self.assertEqual(downloads[0]["item_id"], "27")
        self.assertEqual(downloads[0]["download_code"], "017")
        self.assertEqual(len(downloads[0]["links"]["archive_route_ids"]), 6)
        self.assertNotIn("PRIVATE", json.dumps(self.state))

    def test_file_catalog_is_only_candidate_until_file_download(self):
        selected = {"std_dta_div_cd": "017", "accm_schl_div_cd": "02", "item_id": 27,
            "file_nm": "신입생 충원 현황.xlsx", "file_dtl_nm": "CMN81_017.xlsx",
            "file_pth_nm": "/infofile/SCHEDULER/EXCEL/", "file_crtn_stt_dtm": "2026-10-12"}
        listing = result(command="file_catalog", rows=[selected], sources=[source(
            "https://www.academyinfo.go.kr/main/main0830/selectGongsiDataList.do",
            public_parameters={"schl_div_cd": "02"})])
        registry.record_result(self.state, listing)
        route = next(r for r in self.state["routes"] if r["kind"] == "official_download")
        self.assertFalse(route["support_verified"])
        self.assertEqual(route["status"], "catalog_confirmed")
        download = result(command="file_download", selected_file=selected, sources=[source(
            route["url"], public_parameters=route["public_parameters"], retrieved_utc="2026-10-13T00:00:00Z")])
        registry.record_result(self.state, download)
        self.assertTrue(route["support_verified"])
        self.assertEqual(route["status"], "verified")

    def test_source_less_failure_needs_existing_route_and_preserves_success(self):
        registry.record_result(self.state, result())
        route = self.state["routes"][0]
        registry.record_result(self.state, result(status="error", sources=[], complete=False),
            route_id=route["route_id"], observed_utc="2026-10-13T00:00:00Z")
        self.assertEqual(route["status"], "failed")
        self.assertIsNotNone(route["last_success"])
        with self.assertRaises(registry.RegistryError):
            registry.record_result(self.state, result(sources=[]), route_id=route["route_id"], observed_utc=STAMP)

    def test_default_workspace_env_path_and_atomic_replace(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            destination = Path(directory) / "state" / "routes.json"
            with patch.dict(os.environ, {"ACADEMYINFO_FLOW_STATE_DIR": str(destination.parent)}):
                self.assertEqual(registry.state_path(), destination.resolve())
            registry.save_registry(self.state, destination)
            original = destination.read_bytes()
            self.state["purpose"] = "changed"
            with patch.object(registry.os, "replace", side_effect=OSError("synthetic")):
                with self.assertRaises(OSError):
                    registry.save_registry(self.state, destination)
            self.assertEqual(destination.read_bytes(), original)
            self.assertEqual(list(destination.parent.glob("*.tmp")), [])

    def test_cache_writes_blocked_and_lookup_does_not_write(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            cache = Path(directory) / ".codex" / "plugins" / "cache" / "skill" / "routes.json"
            with self.assertRaises(registry.RegistryError):
                registry.save_registry(self.state, cache)
            self.assertFalse(cache.exists())
            seed = Path(directory) / "seed.json"
            destination = Path(directory) / "new" / "routes.json"
            registry.save_registry(self.state, seed)
            with patch("builtins.print"):
                self.assertEqual(registry.main(["lookup", "--state-file", str(destination),
                    "--seed", str(seed)]), 0)
            self.assertFalse(destination.exists())

    def test_observer_is_optional_and_failure_does_not_change_query(self):
        payload = result()
        original = copy.deepcopy(payload)
        with patch.dict(os.environ, {"ACADEMYINFO_FLOW_DISABLE_ROUTE_RECORD": "1"}):
            observed = registry.observe_result(payload)
            self.assertFalse(observed["recorded"])
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            destination = Path(directory) / "routes.json"
            with patch.dict(os.environ, {"ACADEMYINFO_FLOW_DISABLE_ROUTE_RECORD": "0"}):
                with patch.object(registry, "save_registry", side_effect=OSError("PRIVATE_FAILURE")):
                    observed = registry.observe_result(payload, destination)
            self.assertFalse(observed["recorded"])
            self.assertIn("warning", observed)
            self.assertNotIn("PRIVATE_FAILURE", json.dumps(observed))
            self.assertEqual(payload, original)
            self.assertFalse(destination.exists())

    def test_observer_records_once_and_preserves_seed(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            destination = Path(directory) / "routes.json"
            with patch.dict(os.environ, {"ACADEMYINFO_FLOW_DISABLE_ROUTE_RECORD": "0"}):
                first = registry.observe_result(result(), destination)
                second = registry.observe_result(result(), destination)
            self.assertTrue(first["recorded"])
            self.assertFalse(second["recorded"])
            self.assertEqual(first["route_count"], second["route_count"])
            saved = registry.read_json(destination)
            report_routes = [r for r in saved["routes"] if r["kind"] == "live_report"]
            self.assertEqual(len(report_routes), 1)
            self.assertEqual(len(report_routes[0]["observations"]), 1)

    def test_stable_initializer_records_public_selectors_not_viewer_page_url(self):
        params = {"paramSvyYr": "2026", "paramSchlDivCd": "02", "paramItemId": "27",
                  "paramFormClftCd": "36", **registry.INIT_DEFAULTS}
        registry.record_result(self.state, result(sources=[source(
            "https://academyinfo.go.kr/uipnh/unt/unmcom/RdViewer.do", public_parameters=params)]))
        route = self.state["routes"][0]
        self.assertEqual(route["kind"], "report_bootstrap")
        self.assertTrue(route["support_verified"])
        self.assertEqual(route["scope"]["level"], "department")
        self.assertIsNone(registry.public_url(route["url"] + "?pKey=temporary"))

    def test_unknown_file_period_is_included_with_explicit_unverified_scope(self):
        selected = {"std_dta_div_cd": "158", "accm_schl_div_cd": "02", "item_id": 27,
            "file_nm": "신입생 충원 현황_대학_학과별.xlsx", "file_dtl_nm": "CMN81_158.xlsx",
            "file_pth_nm": "/infofile/SCHEDULER/EXCEL/"}
        listing = result(command="file_catalog", rows=[selected], sources=[source(
            "https://www.academyinfo.go.kr/main/main0830/selectGongsiDataList.do",
            public_parameters={"schl_div_cd": "02", "searchValue": ""})])
        registry.record_result(self.state, listing)
        found = registry.lookup(self.state, kind="official_download", year="2026", division="02", level="department")
        self.assertEqual(found["total_matches"], 1)
        self.assertEqual(found["routes"][0]["scope_matches"], "unverified")
        self.assertFalse(next(r for r in self.state["routes"] if r["kind"] == "file_catalog")["support_verified"])

    def test_file_verified_years_and_discovery_search_have_stable_identity(self):
        params = {"schl_div_cd": "02", "std_dta_div_cd": "158", "file_nm": "학과별.xlsx",
                  "file_path": "/infofile/SCHEDULER/EXCEL/", "file_dtl_nm": "CMN81_158.xlsx", "searchValue": ""}
        download = result(command="file_download", selected_file={"item_id": 27}, sources=[source(
            "https://www.academyinfo.go.kr/main/main0830/FileDown.do", public_parameters=params)],
            verified_scope={"years": ["2025", "2026"], "level": "department", "evidence": "file_contents", "complete": True})
        registry.record_result(self.state, download)
        other = copy.deepcopy(download)
        other["sources"][0]["public_parameters"]["searchValue"] = "공시 검색"
        other["sources"][0]["retrieved_utc"] = "2026-10-13T00:00:00Z"
        registry.record_result(self.state, other)
        files = [r for r in self.state["routes"] if r["kind"] == "official_download"]
        self.assertEqual(len(files), 1)
        self.assertEqual(len(files[0]["observations"]), 2)
        self.assertEqual(registry.lookup(self.state, year="2026", kind="official_download")["total_matches"], 1)
        self.assertEqual(registry.lookup(self.state, year="2024", kind="official_download")["total_matches"], 0)

    def test_source_less_catalog_failure_records_known_endpoint_attempt(self):
        payload = catalog()
        payload.update(command="file_catalog", query={"division": "02", "keyword": ""})
        payload["sources"] = [source("https://www.academyinfo.go.kr/main/main0830/selectGongsiDataList.do",
            public_parameters={"schl_div_cd": "02", "searchValue": ""})]
        registry.record_result(self.state, payload)
        failure = result(command="file_catalog", status="error", complete=False, sources=[],
            query={"division": "02", "keyword": ""}, lookup_started_utc="2026-10-13T00:00:00Z",
            error={"code": "source_connection_error", "phase": "catalog"})
        registry.record_result(self.state, failure)
        route = self.state["routes"][0]
        self.assertEqual(route["kind"], "file_catalog")
        self.assertEqual(route["status"], "failed")
        self.assertEqual(len(route["observations"]), 2)
        self.assertEqual(route["observations"][-1]["evidence_basis"], "known_command_attempt")

    def test_same_utc_correction_and_seed_upgrade_preserve_old_history(self):
        registry.record_result(self.state, result(status="error"))
        registry.record_result(self.state, result())
        self.assertEqual(self.state["routes"][0]["status"], "verified")
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            state_path, seed_path = Path(directory) / "state.json", Path(directory) / "seed.json"
            registry.save_registry(self.state, state_path)
            newer_seed = registry.empty_registry()
            registry.import_catalog(newer_seed, catalog(item="31", title="새 장표"))
            registry.save_registry(newer_seed, seed_path)
            combined = registry.load_registry(state_path, seed_path)
            self.assertEqual(len(combined["routes"][0]["observations"]), 2)
            self.assertEqual(combined["routes"][0]["status"], "verified")
            self.assertEqual(registry.lookup(combined, item="31")["total_matches"], 2)

    def test_legacy_manifest_summary_hash_without_http_is_partial_not_failure(self):
        record = {"code": "013", "success": True, "retrievedAt": STAMP,
            "summary": {"sourceSha256": SHA}, "sourceItem": {"item_id": 27}, "steps": [],
            "downloadRequest": {"url": "https://www.academyinfo.go.kr/main/main0830/FileDown.do",
                "method": "POST", "form": {"schl_div_cd": "02", "searchValue": "",
                "file_nm": "신입생 충원 현황.xlsx", "file_path": "/infofile/SCHEDULER/EXCEL/",
                "file_dtl_nm": "CMN81_013.xlsx", "std_dta_div_cd": "013"}}}
        registry.import_manifest(self.state, {"results": [record]})
        self.assertEqual(self.state["routes"][0]["status"], "partial")
        self.assertTrue(self.state["routes"][0]["preserved_file_verified"])
        self.assertNotIn("http_status", self.state["routes"][0]["latest_observation"])

    def test_archive_hosts_and_public_filters_stay_distinct_from_official_family(self):
        params = {"datasetId": "summary-013", "publicationYear": "2026", "referenceYear": "2025",
                  "referencePeriod": "2025-12-31", "surveyYear": "2026", "degree": "학사",
                  "unitStatus": "existing", "schoolType": "일반대학", "includeFilters": False}
        registry.record_result(self.state, result(command="archive_query", sources=[source(
            "https://hannam-regulations-wiki.esceeee.chatgpt.site/api/disclosures/query", public_parameters=params)]))
        route = self.state["routes"][0]
        self.assertEqual(route["kind"], "archive")
        self.assertEqual(route["public_parameters"]["includeFilters"], "false")
        self.assertTrue(route["support_verified"])
        registry.learn_families(self.state)
        self.assertEqual(self.state["families"], [])

    def test_file_rename_preserves_old_recipe_and_prefers_fresh_catalog_recipe(self):
        params = {"schl_div_cd": "02", "std_dta_div_cd": "158", "file_nm": "옛 학과별.xlsx",
                  "file_path": "/infofile/SCHEDULER/EXCEL/", "file_dtl_nm": "CMN81_158.xlsx", "searchValue": ""}
        registry.record_result(self.state, result(command="file_download", sources=[source(
            "https://www.academyinfo.go.kr/main/main0830/FileDown.do", public_parameters=params)]))
        selected = {"std_dta_div_cd": "158", "accm_schl_div_cd": "02", "item_id": 27,
            "file_nm": "새 학과별.xlsx", "file_dtl_nm": "CMN81_158.xlsx", "file_pth_nm": "/infofile/SCHEDULER/EXCEL/"}
        registry.import_file_catalog(self.state, result(command="file_catalog", rows=[selected], sources=[source(
            "https://www.academyinfo.go.kr/main/main0830/selectGongsiDataList.do",
            retrieved_utc="2026-10-13T00:00:00Z", public_parameters={"schl_div_cd": "02", "searchValue": ""})]))
        found = registry.lookup(self.state, kind="official_download", year="2026", level="department")
        self.assertEqual(found["routes"][0]["titles"], ["새 학과별.xlsx"])
        self.assertFalse(found["routes"][0]["support_verified"])
        self.assertEqual(found["routes"][1]["catalog_status"], "superseded_recipe")
        self.assertTrue(found["routes"][1]["support_verified"])
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            state_path, seed_path = Path(directory) / "state.json", Path(directory) / "seed.json"
            registry.save_registry(registry.empty_registry(), state_path)
            registry.save_registry(self.state, seed_path)
            merged = registry.load_registry(state_path, seed_path)
            found = registry.lookup(merged, kind="official_download", year="2026", level="department")
            self.assertEqual(found["routes"][0]["titles"], ["새 학과별.xlsx"])
            self.assertEqual(found["routes"][1]["catalog_status"], "superseded_recipe")


if __name__ == "__main__":
    unittest.main()
