"""Fresh public AcademyInfo lookups for an LLM; no archive or cache is read.

Run this file directly.  Its only dependencies are Python's standard library
and the reviewed protocol adapters shipped in scripts/vendor.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any
import urllib.error

_VENDOR = Path(__file__).resolve().parent / "vendor"
sys.path.insert(0, str(_VENDOR))

try:
    if not (_VENDOR / "academyinfo_archive" / "direct.py").is_file():
        raise ImportError("bundled adapter unavailable")
    if __package__:
        from .vendor.academyinfo_archive.catalog import CATALOG_PAGE_URL, collection_plan, published_scope
        from .vendor.academyinfo_archive.department import (
            INDICATORS, DepartmentSelection, affiliated_schools, department_info,
            department_metric, department_rows, iter_departments, iter_schools,
            metric_metadata, metric_records, school_page, school_rows,
        )
        from .vendor.academyinfo_archive.direct import DirectClient, SECRET_NAME, SourceError, rows_at
    else:
        from academyinfo_archive.catalog import CATALOG_PAGE_URL, collection_plan, published_scope
        from academyinfo_archive.department import (
            INDICATORS, DepartmentSelection, affiliated_schools, department_info,
            department_metric, department_rows, iter_departments, iter_schools,
            metric_metadata, metric_records, school_page, school_rows,
        )
        from academyinfo_archive.direct import DirectClient, SECRET_NAME, SourceError, rows_at
    _DEPENDENCIES_AVAILABLE = True
except ImportError:
    _DEPENDENCIES_AVAILABLE = False
    INDICATORS = dict.fromkeys(("v1", "v2", "v4", "v5", "v7", "v8"))
    SECRET_NAME = re.compile(r"token|password|passwd|authorization|cookie|session|secret|pkey|parg|ubikey|ubiargs", re.I)

    class SourceError(RuntimeError):
        pass


class InputError(ValueError):
    """A public selector is invalid; its untrusted value is never echoed."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError("명령과 필수 인수를 확인하세요. --help로 사용법을 볼 수 있습니다.")


def _year(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}", value):
        raise InputError("조회연도는 네 자리 문자열이어야 합니다.")
    return value


def _code(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{7}", value):
        raise InputError("학교·학과 코드는 앞자리 0을 보존한 일곱 자리 문자열이어야 합니다.")
    return value


def _positive(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise InputError("페이지·반환 제한은 1 이상의 정수여야 합니다.") from error
    if isinstance(value, bool) or number < 1 or str(number) != str(value):
        raise InputError("페이지·반환 제한은 1 이상의 정수여야 합니다.")
    return number


def _public_data(value: Any) -> Any:
    """Keep source values, dropping credential-shaped fields rather than logging them."""
    if isinstance(value, dict):
        return {key: _public_data(item) for key, item in value.items()
                if isinstance(key, str) and not SECRET_NAME.search(key)}
    if isinstance(value, list):
        return [_public_data(item) for item in value]
    if isinstance(value, str) and re.search(r"<!doctype\b|<html\b|<script\b|<body\b", value, re.I):
        raise SourceError("공개 JSON 값에서 HTML 오류 문서를 발견했습니다.")
    if isinstance(value, float) and not math.isfinite(value):
        raise SourceError("공개 JSON 값에 유한하지 않은 숫자가 있습니다.")
    return value


def _source(exchange: Any) -> dict[str, Any]:
    return {
        "source_url": exchange.url,
        "method": exchange.method,
        "public_parameters": dict(exchange.parameters),
        "retrieved_utc": exchange.fetched_at,
        "raw_sha256": hashlib.sha256(exchange.body).hexdigest(),
        "response_status": exchange.status,
        "response_content_type": exchange.content_type,
        "response_bytes": len(exchange.body),
        "final_url": exchange.final_url,
    }


class _RecordingClient:
    def __init__(self, client: Any):
        self.client = client
        self.exchanges: list[Any] = []

    def request(self, *args: Any, **kwargs: Any) -> Any:
        exchange = self.client.request(*args, **kwargs)
        self.exchanges.append(exchange)
        return exchange

    def catalog(self, *args: Any, **kwargs: Any) -> Any:
        exchange = self.client.catalog(*args, **kwargs)
        self.exchanges.append(exchange)
        return exchange


def _base(command: str, year: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source": "대학알리미",
        "mode": "live",
        "command": command,
        "status": "ok",
        "request_year": year,
        "lookup_started_utc": datetime.now(timezone.utc).isoformat(),
        "complete": False,
        "sources": [],
        "rows": [],
        "completeness": {"scope": "아직 검증되지 않은 조회", "source_complete": False,
                         "returned_complete": False},
        "value_semantics": "원천의 문자열·null·빈값·대시는 보존하며, 빈 결과를 통계값 0으로 해석하지 않습니다.",
    }


def _finish(result: dict[str, Any], client: _RecordingClient | None = None) -> dict[str, Any]:
    if client is not None:
        result["sources"] = [_source(exchange) for exchange in client.exchanges]
    result["retrieved_utc"] = result["sources"][-1]["retrieved_utc"] if result["sources"] else None
    result["returned_row_count"] = len(result.get("rows", []))
    result["data_availability"] = ("error" if result["status"] == "error" else
        "empty" if not result.get("rows") and not result.get("data") else "available")
    return result


def _complete(result: dict[str, Any], scope: str, *, source: bool = True,
              returned: bool = True, **details: Any) -> None:
    result["complete"] = source and returned
    result["completeness"] = {"scope": scope, "source_complete": source,
                              "returned_complete": returned, **details}
    if source and not returned:
        result["status"] = "partial"


def _selection(args: argparse.Namespace) -> Any:
    return DepartmentSelection(args.school_code, args.dept_code, args.major_code, args.year)


def _validate(args: argparse.Namespace) -> None:
    supported = {"scope", "schools", "affiliations", "departments", "metric", "info", "catalog"}
    if args.command not in supported:
        raise InputError("지원하는 명령은 scope, schools, affiliations, departments, metric, info, catalog입니다.")
    if args.command == "scope":
        args.year = getattr(args, "year", None) or datetime.now(timezone(timedelta(hours=9))).strftime("%Y")
        args.division = getattr(args, "division", "02")
        if args.division not in {"01", "02", "03", "04"}:
            raise InputError("학교 구분은 01, 02, 03, 04 중 하나여야 합니다.")
    _year(args.year)
    if args.command in {"affiliations", "departments", "metric", "info"}:
        _code(args.school_code)
    if args.command in {"metric", "info"}:
        _code(args.dept_code)
        _code(args.major_code)
    if args.command == "metric" and args.flag not in INDICATORS:
        raise InputError("학과 주요지표 flag는 v1, v2, v4, v5, v7, v8 중 하나여야 합니다.")
    if args.command in {"schools", "departments"}:
        args.max_pages = _positive(getattr(args, "max_pages", 1000))
        args.name = getattr(args, "name", "")
        if not isinstance(args.name, str):
            raise InputError("학교명·학과명은 문자열이어야 합니다.")
    if args.command == "catalog":
        if args.division not in {"01", "02", "03", "04"}:
            raise InputError("학교 구분은 01, 02, 03, 04 중 하나여야 합니다.")
        args.limit = _positive(getattr(args, "limit", 30))
        args.keyword = getattr(args, "keyword", "")
        if not isinstance(args.keyword, str):
            raise InputError("공시목록 검색어는 문자열이어야 합니다.")


def _scope(args: argparse.Namespace, client: _RecordingClient, result: dict[str, Any]) -> None:
    exchange = client.request(CATALOG_PAGE_URL, {"svyYr": args.year, "schlDivCd": args.division}, method="POST")
    if not 200 <= exchange.status < 300:
        raise SourceError("공개 연도 선택지 조회 HTTP 오류입니다.")
    data = published_scope(exchange.body.decode("utf-8-sig"))
    result["data"] = data
    result["latest_publication_year"] = max(data["years"])
    result["query"] = {"page_year_hint": args.year, "page_division_hint": args.division}
    result["request_year"] = args.year
    _complete(result, "공식 화면의 공개 연도·기관 구분 선택지")


def _schools(args: argparse.Namespace, client: _RecordingClient, result: dict[str, Any]) -> None:
    result["query"] = {"name": args.name, "max_pages": args.max_pages}
    result["row_fields"] = {"school_code": "schl_id", "name": "schl_nm"}
    seen: set[str] = set()
    page_count = 0
    expected = None
    expected_rows = None
    try:
        for exchange in iter_schools(client, args.year, school_name=args.name,
                                     max_pages=args.max_pages):
            rows = school_rows(exchange)
            for row in rows:
                try:
                    code = _code(row["schl_id"])
                except InputError as error:
                    raise SourceError("학교 명부의 코드 형식이 바뀌었습니다.") from error
                if code in seen:
                    raise SourceError("학교 명부에 중복 코드 또는 중복 페이지가 있습니다.")
                seen.add(code)
            payload = exchange.json()
            pagination = payload["paginationInfo"]
            total_pages = pagination["totalPageCount"]
            if isinstance(total_pages, bool) or total_pages < 0:
                raise SourceError("학교 명부의 원천 페이지 수가 잘못되었습니다.")
            if expected is not None and total_pages != expected:
                raise SourceError("학교 명부 조회 중 원천 페이지 수가 바뀌었습니다.")
            expected = total_pages
            if "totalRecordCount" in pagination:
                total_rows = pagination["totalRecordCount"]
                if isinstance(total_rows, bool) or not isinstance(total_rows, int) or total_rows < 0:
                    raise SourceError("학교 명부의 원천 행 수가 잘못되었습니다.")
                if expected_rows is not None and expected_rows != total_rows:
                    raise SourceError("학교 명부 조회 중 원천 전체 행 수가 바뀌었습니다.")
                expected_rows = total_rows
            result["rows"].extend(_public_data(rows))
            page_count += 1
    except SourceError as error:
        if str(error) != "학교 목록 페이지 제한에 도달했습니다. 전체 수집으로 표시하지 않습니다.":
            raise
        result["status"] = "partial"
        _complete(result, "지정 검색어에 대한 학교 명부", source=False, returned=False,
                  reason="max_pages", fetched_pages=page_count, source_total_pages=expected,
                  max_pages=args.max_pages)
        return
    if expected_rows is not None and len(result["rows"]) != expected_rows:
        raise SourceError("학교 명부의 실제 행 수가 원천 전체 행 수와 다릅니다.")
    _complete(result, "지정 검색어에 대한 학교 명부", fetched_pages=page_count,
              source_total_pages=expected, source_total_row_count=expected_rows)


def _departments(args: argparse.Namespace, client: _RecordingClient, result: dict[str, Any]) -> None:
    result["query"] = {"school_code": args.school_code, "name": args.name,
                       "include_closed": True, "max_pages": args.max_pages}
    result["row_fields"] = {"department_code": "schl_mjr_id", "major_code": "mjr_id", "name": "mjr_nm"}
    source_row_count = 0
    page_count = 0
    expected = None
    try:
        for exchange in iter_departments(client, args.school_code, args.year,
                                         include_closed=True, max_pages=args.max_pages):
            rows = department_rows(exchange)
            expected = exchange.json()["paginationInfo"]["totalRecordCount"]
            if isinstance(expected, bool):
                raise SourceError("학과 명부의 원천 전체 행 수가 잘못되었습니다.")
            for row in rows:
                try:
                    _code(row["schl_mjr_id"])
                    _code(row["mjr_id"])
                except InputError as error:
                    raise SourceError("학과 명부의 코드 형식이 바뀌었습니다.") from error
            source_row_count += len(rows)
            page_count += 1
            matched = [row for row in rows if args.name.casefold() in row["mjr_nm"].casefold()]
            result["rows"].extend(_public_data(matched))
    except SourceError as error:
        if str(error) != "학과 목록 페이지 제한에 도달했습니다. 전체 수집으로 표시하지 않습니다.":
            raise
        result["status"] = "partial"
        _complete(result, "지정 학교의 학과 명부에서 이름으로 필터한 후보", source=False,
                  returned=False, reason="max_pages", fetched_pages=page_count,
                  source_fetched_row_count=source_row_count, source_total_row_count=expected,
                  max_pages=args.max_pages)
        return
    _complete(result, "지정 학교의 학과 명부에서 이름으로 필터한 후보", fetched_pages=page_count,
              source_fetched_row_count=source_row_count, source_total_row_count=expected)


def _affiliations(args: argparse.Namespace, client: _RecordingClient, result: dict[str, Any]) -> None:
    result["query"] = {"school_code": args.school_code}
    exchange = school_page(client, args.school_code, year=args.year)
    result["rows"] = affiliated_schools(exchange)
    result["row_fields"] = {"school_code": "schoolCode", "division": "schoolDivision", "name": "sourceLabel"}
    _complete(result, "지정 학교의 공개 소속기관 선택 목록")


def _metric(args: argparse.Namespace, client: _RecordingClient, result: dict[str, Any]) -> None:
    selection = _selection(args)
    result["query"] = {"school_code": args.school_code, "department_code": args.dept_code,
                       "major_code": args.major_code, "flag": args.flag}
    exchange = department_metric(client, selection, args.flag)
    records = list(metric_records(exchange, selection, args.flag))
    for record in records:
        try:
            _year(record["values"]["year"])
        except InputError as error:
            raise SourceError("학과 지표의 원천 그래프 연도 형식이 바뀌었습니다.") from error
    payload = exchange.json()
    if "pramMap" in payload and not isinstance(payload["pramMap"], dict):
        raise SourceError("지표 응답의 공개 연도 메타데이터 형식이 바뀌었습니다.")
    metadata = metric_metadata(exchange, selection, args.flag)
    result["indicator"] = metadata["indicator"]
    result["unit"] = metadata["indicator"]["unit"]
    result["source_page"] = metadata["source_page"]
    result["year_semantics"] = metadata["year_semantics"]
    result["rows"] = [{"source_graph_year": record["values"]["year"],
                       "value": record["values"]["val"],
                       "source_row": _public_data(record["values"])} for record in records]
    result["coverage_note"] = metadata["coverage"]
    _complete(result, "지정 학과·지표의 공개 그래프 응답")


def _info(args: argparse.Namespace, client: _RecordingClient, result: dict[str, Any]) -> None:
    selection = _selection(args)
    result["query"] = {"school_code": args.school_code, "department_code": args.dept_code,
                       "major_code": args.major_code}
    exchange = department_info(client, selection)
    payload = exchange.json()
    if not isinstance(payload, dict):
        raise SourceError("학과 기본정보 응답이 JSON object가 아닙니다.")
    result["data"] = _public_data(payload)
    result["source_page"] = selection.source_page()
    result["schema_verified"] = False
    result["validation_status"] = "request_protocol_only"
    result["year_semantics"] = {"request_year": args.year,
        "row_year": "학과 기본정보 원문 필드를 유지하며 기준연도를 자동 추정하지 않습니다."}
    _complete(result, "학과 기본정보의 JSON 응답; 필드별 정제·완전성은 미검증",
              source=False, returned=True, reason="unverified_information_schema")


def _catalog(args: argparse.Namespace, client: _RecordingClient, result: dict[str, Any]) -> None:
    result["query"] = {"division": args.division, "keyword": args.keyword, "limit": args.limit}
    exchange = client.catalog(args.year, args.division)
    payload = exchange.json()
    plan = collection_plan(payload)
    rows = rows_at(payload, ["detailItemList"])
    matched = [row for row in rows if args.keyword.casefold() in
               json.dumps(row, ensure_ascii=False).casefold()]
    result["rows"] = [_public_data(row) | {
        "viewer_levels": ["school", "department"] if str(row["mjr_use_step_cd"]) != "0" else ["school"],
        "attachment_only": row["pdf_use_yn"] == "Y",
    } for row in matched[:args.limit]]
    result["row_fields"] = {"item_id": "item_id", "title": "pgm_estn_nm",
                            "department_available": "mjr_use_step_cd", "pdf_only": "pdf_use_yn"}
    result["catalog_note"] = plan["note"]
    _complete(result, "지정 연도·학교 구분의 공시목록에서 검색어로 필터한 행",
              returned=len(matched) <= args.limit, source_item_rows=len(rows),
              matched_row_count=len(matched), return_limit=args.limit,
              reason="return_limit" if len(matched) > args.limit else None)


def run_command(args: argparse.Namespace | dict[str, Any], *,
                network_client: Any | None = None) -> dict[str, Any]:
    """Return a JSON-safe result with fresh source requests.

    Standalone calls create a new client. An explicit batch may supply its
    anonymous client so request pacing also holds across JSON/report boundaries;
    response recording remains separate for every query.
    """
    if isinstance(args, dict):
        args = argparse.Namespace(**args)
    result = _base(getattr(args, "command", "unknown"), getattr(args, "year", None))
    client = None
    try:
        _validate(args)
        if not _DEPENDENCIES_AVAILABLE:
            result["status"] = "error"
            result["error"] = {"code": "dependency_unavailable",
                               "message": "스킬에 포함된 공개 조회 어댑터를 찾을 수 없습니다."}
            return _finish(result)
        client = _RecordingClient(network_client if network_client is not None else DirectClient())
        handler = {"schools": _schools, "departments": _departments,
                   "affiliations": _affiliations, "metric": _metric,
                   "info": _info, "catalog": _catalog, "scope": _scope}[args.command]
        handler(args, client, result)
    except (InputError, AttributeError) as error:
        result["status"] = "error"
        result["error"] = {"code": "invalid_input", "message": str(error) if isinstance(error, InputError)
                           else "명령과 필수 공개 선택조건을 확인하세요."}
    except SourceError:
        result["status"] = "partial" if result["rows"] else "error"
        result["complete"] = False
        http_error = client and client.exchanges and not 200 <= client.exchanges[-1].status < 300
        result["error"] = {"code": "source_http_error" if http_error else "source_validation_error",
            "message": "대학알리미 원천 응답을 정상 자료로 검증할 수 없습니다. 확인된 부분만 반환합니다."}
    except (urllib.error.URLError, TimeoutError, OSError):
        result["status"] = "partial" if result["rows"] else "error"
        result["complete"] = False
        result["error"] = {"code": "source_connection_error",
                           "message": "공식 대학알리미 서버 연결을 완료하지 못했습니다."}
    except Exception:
        result["status"] = "partial" if result["rows"] else "error"
        result["complete"] = False
        result["error"] = {"code": "internal_error",
                           "message": "조회 처리에 실패했습니다. 원문·세션·예외 상세는 출력하지 않습니다."}
    return _finish(result, client)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="대학알리미 공식 서버를 매번 새로 조회해 LLM용 JSON을 반환합니다.")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)
    scope = commands.add_parser("scope")
    scope.add_argument("--year", type=_year, help="공식 화면의 연도 힌트; 공개 선택지가 최신 연도를 결정합니다.")
    scope.add_argument("--division", default="02", choices=("01", "02", "03", "04"))
    for command in ("schools", "affiliations", "departments", "metric", "info", "catalog"):
        sub = commands.add_parser(command)
        sub.add_argument("--year", required=True, type=_year)
        if command in {"affiliations", "departments", "metric", "info"}:
            sub.add_argument("--school-code", required=True, type=_code)
        if command in {"schools", "departments"}:
            sub.add_argument("--name", default="")
            sub.add_argument("--max-pages", default=1000, type=_positive)
        if command in {"metric", "info"}:
            sub.add_argument("--dept-code", required=True, type=_code)
            sub.add_argument("--major-code", required=True, type=_code)
        if command == "metric":
            sub.add_argument("--flag", required=True, choices=list(INDICATORS))
        if command == "catalog":
            sub.add_argument("--division", required=True, choices=("01", "02", "03", "04"))
            sub.add_argument("--keyword", default="")
            sub.add_argument("--limit", default=30, type=_positive)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = run_command(args)
    except (InputError, ValueError):
        result = _base("invalid")
        result["status"] = "error"
        result["error"] = {"code": "invalid_input",
            "message": "명령과 필수 인수를 확인하세요. 학교·학과 코드는 일곱 자리 문자열이어야 합니다."}
        result = _finish(result)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        import route_registry
        result["route_registry"] = route_registry.observe_result(result)
    except Exception:
        result["route_registry"] = {"recorded": False, "route_count": 0,
                                    "warning": "경로 메타데이터를 기록하지 못했습니다. 원천 조회 결과는 유지합니다."}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] == "ok" and not result.get("error") else 2


if __name__ == "__main__":
    raise SystemExit(main())

