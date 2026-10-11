"""Read official disclosure reports and PDF attachments afresh, in memory.

Only reviewed public protocol adapters are imported. Nothing reads an archive,
persists a response, prints bootstrap HTML, or exposes report runtime state.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any
import urllib.error
import urllib.parse

_VENDOR = Path(__file__).resolve().parent / "vendor"
sys.path.insert(0, str(_VENDOR))
try:
    if not (_VENDOR / "academyinfo_archive" / "viewer_data.py").is_file():
        raise ImportError("bundled adapter unavailable")
    from academyinfo_archive.catalog import collection_plan
    from academyinfo_archive.direct import DirectClient, SourceError, rows_at, validate_public_url
    from academyinfo_archive.pdf_json import PDF_DOWNLOAD_URL, attachment_links, parse_pdf
    from academyinfo_archive.report_tables import (
        ReportParseError, combine_report_pages, parse_java_map_list, parse_report_xml,
    )
    from academyinfo_archive.viewer_data import ViewerDataClient
    _DEPENDENCIES_AVAILABLE = True
except ImportError:
    _DEPENDENCIES_AVAILABLE = False

    class SourceError(RuntimeError):
        pass

    class ReportParseError(ValueError):
        pass


MAX_PAGES = 10000
GENERATION_WAIT_SECONDS = 60
GENERATION_MAX_POLLS = 30
_PRIVATE_FIELD = re.compile(
    r"token|password|passwd|authorization|cookie|session|secret|pkey|parg|"
    r"ubikey|ubiargs|schema_text|source_table_metadata|xml_tree|children|"
    r"serviceid|exportseq|strquery|resultmaster|resultheader|resultbody|resultsum", re.I)


class InputError(ValueError):
    """Invalid public selectors; supplied values are never echoed in errors."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError("명령과 필수 인수를 확인하세요. --help로 사용법을 볼 수 있습니다.")


def _integer(value: Any, *, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise InputError("페이지·반환 범위는 정수로 지정해야 합니다.") from error
    if (isinstance(value, bool) or str(number) != str(value) or number < minimum
            or maximum is not None and number > maximum):
        raise InputError("페이지·반환 범위가 허용 범위를 벗어났습니다.")
    return number


def _positive(value: Any) -> int:
    return _integer(value, minimum=1)


def _offset(value: Any) -> int:
    return _integer(value)


def _year(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}", value):
        raise InputError("조회연도는 네 자리 문자열이어야 합니다.")
    return value


def _public(value: Any) -> Any:
    """Allow public display data, never transport/runtime structures."""
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items()
                if isinstance(key, str) and not _PRIVATE_FIELD.search(key)}
    if isinstance(value, list):
        return [_public(item) for item in value]
    if isinstance(value, str) and re.search(r"<!doctype\b|<html\b|<script\b|<body\b", value, re.I):
        raise SourceError("공개 표시값에서 HTML 오류 응답을 발견했습니다.")
    if isinstance(value, float) and not math.isfinite(value):
        raise SourceError("공개 표시값에 유한하지 않은 수가 있습니다.")
    return value


def _url_without_query(url: str) -> str:
    validate_public_url(url)
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _source(exchange: Any, *, page: int | None = None,
            selectors: dict[str, str] | None = None) -> dict[str, Any]:
    result = {
        "source_url": _url_without_query(exchange.url),
        "method": exchange.method,
        "public_parameters": _public(selectors if selectors is not None else exchange.parameters),
        "retrieved_utc": exchange.fetched_at,
        "raw_sha256": hashlib.sha256(exchange.body).hexdigest(),
        "response_status": exchange.status,
        "response_content_type": exchange.content_type,
        "response_bytes": len(exchange.body),
        "final_url": _url_without_query(exchange.final_url),
    }
    if page is not None:
        result["source_request_page"] = page
    return result


def _base(command: str) -> dict[str, Any]:
    return {
        "schema_version": 1, "source": "대학알리미", "mode": "live", "command": command,
        "status": "ok", "lookup_started_utc": datetime.now(timezone.utc).isoformat(),
        "complete": False, "sources": [], "rows": [],
        "completeness": {"scope": "아직 검증되지 않은 조회", "source_complete": False,
                         "returned_complete": False},
        "value_semantics": "원천 표시 문자열·null·빈값·대시를 보존하며, 빈 결과를 통계값 0으로 해석하지 않습니다.",
        "runtime_fields_omitted": True, "raw_responses_saved": False,
    }


def _finish(result: dict[str, Any]) -> dict[str, Any]:
    result["retrieved_utc"] = result["sources"][-1]["retrieved_utc"] if result["sources"] else None
    result["returned_row_count"] = len(result["rows"])
    result["data_availability"] = ("error" if result["status"] == "error" else
                                   "available" if result["rows"] else "empty")
    return _public(result)


def _validate(args: argparse.Namespace) -> None:
    if args.command not in {"report", "attachments", "pdf"}:
        raise InputError("지원하는 명령은 report, attachments, pdf입니다.")
    if args.command in {"report", "attachments"}:
        _year(args.year)
        if args.division not in {"01", "02", "03", "04"}:
            raise InputError("학교 구분은 01, 02, 03, 04 중 하나여야 합니다.")
        if not isinstance(args.item, str) or not re.fullmatch(r"[0-9]{1,6}", args.item):
            raise InputError("항목 ID는 공식 공시목록에서 확인한 숫자 문자열이어야 합니다.")
        args.item = str(int(args.item))
        if args.level not in {"school", "department"}:
            raise InputError("조회단위는 school 또는 department여야 합니다.")
        args.max_pages = _integer(getattr(args, "max_pages", 100), minimum=1, maximum=MAX_PAGES)
        args.limit = _integer(getattr(args, "limit", 50), minimum=1, maximum=100000)
        args.offset = _integer(getattr(args, "offset", 0), minimum=0)
        if args.command == "report":
            args.school_name = getattr(args, "school_name", None)
            args.dept_name = getattr(args, "dept_name", None)
            for name in (args.school_name, args.dept_name):
                if name is not None and (not isinstance(name, str) or not name or len(name) > 200):
                    raise InputError("학교·학과 이름 필터는 비어 있지 않은 문자열이어야 합니다.")
    else:
        if (not isinstance(args.file_path, str) or not re.fullmatch(
                r"/infofile/PDF_UPLOAD/PBNF_ITEM_UPLOAD/[0-9]{4}/[0-9]{2}/[0-9]+/", args.file_path)):
            raise InputError("실제 첨부 목록에 나타난 공개 PDF 경로를 지정하세요.")
        if (not isinstance(args.file_name, str) or not re.fullmatch(
                r"[A-Za-z0-9_.-]+\.pdf", args.file_name, re.I)):
            raise InputError("실제 첨부 목록에 나타난 PDF 파일명을 지정하세요.")
        if (not isinstance(args.save_name, str) or not args.save_name or len(args.save_name) > 512
                or any(ord(char) < 32 or ord(char) == 127 for char in args.save_name)):
            raise InputError("실제 첨부 목록의 공개 표시 파일명을 지정하세요.")
        args.page_start = _integer(getattr(args, "page_start", 1), minimum=1)
        end = getattr(args, "page_end", None)
        args.page_end = _integer(end, minimum=args.page_start) if end is not None else None


def _catalog(args: argparse.Namespace, client: Any, result: dict[str, Any]) -> dict[str, Any]:
    exchange = client.catalog(args.year, args.division)
    result["sources"].append(_source(exchange))
    payload = exchange.json()
    collection_plan(payload)  # Reuse the reviewed required-field/schema checks.
    items = rows_at(payload, ["detailItemList"])
    matched = []
    for row in items:
        if str(row["svy_yr"]) != args.year or str(row["schl_div_cd"]) != args.division:
            raise SourceError("공시목록의 연도·학교 구분이 요청과 다릅니다.")
        item = str(row["item_id"])
        if not re.fullmatch(r"[0-9]{1,6}", item):
            raise SourceError("공시목록의 항목 ID 형식이 변경되었습니다.")
        if str(int(item)) == args.item:
            matched.append(row)
    if len(matched) != 1:
        raise InputError("지정한 항목이 현행 공식 목록에서 유일하게 확인되지 않습니다.")
    row = matched[0]
    if row["pdf_use_yn"] not in {"Y", "N"}:
        raise SourceError("첨부 전용 여부를 확인할 수 없습니다.")
    levels = ["school", "department"] if str(row["mjr_use_step_cd"]) != "0" else ["school"]
    result["catalog_item"] = _public({key: row[key] for key in (
        "svy_yr", "schl_div_cd", "item_id", "pgm_estn_nm", "item_smry_nm",
        "mjr_use_step_cd", "pdf_use_yn", "v_pgm_nm2", "v_pgm_nm3") if key in row})
    result["catalog_item"]["supported_request_levels"] = levels
    result["catalog_item"]["pdf_only"] = row["pdf_use_yn"] == "Y"
    if args.level not in levels:
        raise InputError("이 항목의 공식 목록은 요청한 학과 조회 형식을 지원하지 않습니다.")
    if args.command == "report" and row["pdf_use_yn"] == "Y":
        raise InputError("첨부 전용 항목입니다. attachments로 실제 파일 목록을 조회한 뒤 pdf를 사용하세요.")
    return row


def _wait_for_generation(client: Any, session: Any) -> Any:
    deadline = time.monotonic() + GENERATION_WAIT_SECONDS
    for attempt in range(GENERATION_MAX_POLLS):
        status = client.report_status(session)
        if status.complete:
            if (isinstance(status.expected_pages, bool) or not isinstance(status.expected_pages, int)
                    or not 1 <= status.expected_pages <= 100000):
                raise SourceError("완료 보고서의 전체 페이지 수를 확인할 수 없습니다.")
            return status
        if attempt + 1 >= GENERATION_MAX_POLLS or time.monotonic() >= deadline:
            break
        time.sleep(1)
    raise SourceError("보고서 생성 완료를 제한 시간 내 확인하지 못했습니다.")


def _slim_page(page: dict[str, Any]) -> dict[str, Any]:
    return {"source_request_page": page["source_page_index"] + 1,
            "source_page_index": page["source_page_index"],
            "raw_sha256": page["source_sha256"],
            "response_bytes": page.get("source_byte_length")}


def _display_cells(page: dict[str, Any]) -> list[dict[str, Any]]:
    return [_public({"item_index": cell["item_index"], "text": cell["text"],
                     "geometry": cell.get("geometry")})
            for cell in page["cells"] if cell.get("text") is not None]


def _row_context(cells: list[dict[str, Any]], geometry: dict[str, Any]) -> list[dict[str, Any]]:
    """Return overlapping printed cells, without guessing their semantic roles."""
    try:
        y, height = Decimal(geometry["y"]), Decimal(geometry["height"])
        if not y.is_finite() or not height.is_finite() or height <= 0:
            return []
        context = []
        for cell in cells:
            g = cell.get("geometry") or {}
            yy, hh = Decimal(g["y"]), Decimal(g["height"])
            if yy.is_finite() and hh.is_finite() and hh > 0 and yy < y + height and y < yy + hh:
                context.append(cell)
        return context
    except (KeyError, TypeError, InvalidOperation):
        return []


def _collect(args: argparse.Namespace, client: Any, result: dict[str, Any]) -> tuple[list[dict], bool]:
    """Use one report job, completed before retrieval and checked afterwards."""
    session = client.start_report(args.year, args.division, args.item, level=args.level)
    reports: list[dict] = []
    first_status = None
    final_status = None
    failure = None
    selectors = {"pubYear": args.year, "schoolDivision": args.division,
                 "itemId": args.item, "level": args.level, "language": "ko"}
    result["selectors"] = selectors
    result["title"] = _public(session.title)
    try:
        metadata = None
        if args.command == "report":
            metadata = {key.removeprefix("result").lower(): parse_java_map_list(value)
                        for key, value in session.schema_text.items()}
        first_status = _wait_for_generation(client, session)
        for page in range(1, min(first_status.expected_pages, args.max_pages) + 1):
            # Initialization already returned page 1 of this freshly created
            # report job. Preserve its source hash, then request pages 2..N.
            exchange = session.initial if page == 1 else client.fetch_page(
                session, page, document_local_page_numbers=args.command == "attachments")
            result["sources"].append(_source(exchange, page=page, selectors=selectors))
            parsed = parse_report_xml(exchange.body, source_page_index=page - 1,
                                      metadata=metadata, selectors=selectors)
            if args.command == "attachments":
                parsed["attachment_links"] = attachment_links(exchange.body)
            # Remove runtime-bearing XML/attributes immediately; the parser has
            # already validated them. Only display cells survive for listings.
            parsed["pages"] = [dict(_slim_page(p), **{
                "source_page_index": p["source_page_index"],
                "source_sha256": p["source_sha256"],
                "display_cells": _display_cells(p) if args.command == "attachments" else [],
            }) for p in parsed["pages"]]
            parsed.pop("source_table_metadata", None)
            reports.append(parsed)
        final_status = client.report_status(session)
        if not final_status.complete or final_status.expected_pages != first_status.expected_pages:
            raise SourceError("보고서의 최종 생성 상태 또는 전체 페이지 수가 변경되었습니다.")
    except Exception as error:
        failure = error
    finally:
        session.close()
    expected = first_status.expected_pages if first_status is not None else None
    stable = bool(first_status is not None and final_status is not None and final_status.complete
                  and first_status.expected_pages == final_status.expected_pages and failure is None)
    result["generation"] = {"complete_before_fetch": first_status is not None,
                            "final_complete": bool(final_status is not None and final_status.complete),
                            "page_count_stable": stable, "source_total_pages": expected,
                            "fetched_pages": len(reports), "max_pages": args.max_pages,
                            "max_pages_allowed": MAX_PAGES}
    if reports:
        combined = combine_report_pages(reports, expected_pages=expected)
        result["page_coverage"] = combined["coverage"]
        result["pages"] = [{key: value for key, value in p.items()
                            if key not in {"display_cells", "source_sha256"}} for p in combined["pages"]]
        source_complete = stable and combined["coverage"]["complete"]
        if args.command == "report":
            _numeric_result(args, result, combined, source_complete)
        else:
            _attachment_result(args, result, reports, source_complete)
    if failure is not None:
        raise failure
    return reports, stable


def _numeric_result(args: argparse.Namespace, result: dict[str, Any], combined: dict,
                    source_complete: bool) -> None:
    rows = combined["rows"]
    filters = {key: value for key, value in (("schoolName", args.school_name),
                                            ("deptName", args.dept_name)) if value is not None}
    filter_verified = all(isinstance(row.get("dimensions", {}).get(key), str)
                          for row in rows for key in filters)
    # Empty or unparsed responses cannot prove that a dimension filter exists.
    available_dimensions = {key for row in rows for key in row.get("dimensions", {})}
    filter_verified = filter_verified and set(filters).issubset(available_dimensions)
    matched = [row for row in rows if all(row.get("dimensions", {}).get(key) == value
                                       for key, value in filters.items())]
    selected = matched[args.offset:args.offset + args.limit]
    result["rows"] = [_public(row | {"source_request_page": row["source_page_index"] + 1})
                      for row in selected]
    safe_column_keys = {"key", "source_col_no", "source_field_id", "source_semantic_code",
                        "header_path", "source_field_ids", "source_semantic_codes", "value_scope"}
    result["columns"] = [_public({key: value for key, value in col.items() if key in safe_column_keys})
                         for col in combined["columns"]]
    result["filters"] = {"match": "exact", "dimensions": filters,
                         "verified_on_all_source_rows": filter_verified}
    result["granularity"] = {"requested_level": args.level,
        "catalog_mjr_use_step_cd": result["catalog_item"]["mjr_use_step_cd"],
        "school_name_dimension_present": "schoolName" in available_dimensions,
        "department_name_dimension_present": "deptName" in available_dimensions,
        "note": "department는 공식 조회 형식입니다. 학과·계열 등 실제 통계 단위는 원천 열과 지침으로 확인해야 합니다."}
    table_verified = combined["status"] == "complete"
    returned_complete = filter_verified and args.offset == 0 and len(selected) == len(matched)
    result["complete"] = source_complete and table_verified and returned_complete
    result["status"] = "ok" if result["complete"] else "partial"
    result["completeness"] = {"scope": "지정 장표 전체에서 원천 이름 차원으로 정확히 필터한 수치 행",
        "source_complete": source_complete, "returned_complete": returned_complete,
        "table_validation_complete": table_verified, "filter_dimension_verified": filter_verified,
        "source_fetched_row_count": len(rows), "matched_row_count": len(matched),
        "return_offset": args.offset, "return_limit": args.limit,
        "reasons": (["page_limit_or_generation_unverified"] if not source_complete else [])
                   + (["table_layout_unverified"] if not table_verified else [])
                   + (["filter_dimension_unverified"] if not filter_verified else [])
                   + (["return_range"] if args.offset or len(selected) < len(matched) else [])}
    result["validation_warnings"] = _public(combined["warnings"][:30])
    result["validation_warning_count"] = len(combined["warnings"])


def _attachment_result(args: argparse.Namespace, result: dict[str, Any], reports: list[dict],
                       source_complete: bool) -> None:
    links = []
    contexts = {}
    for report in reports:
        page = report["pages"][0]
        page_number = page["source_page_index"] + 1
        cells = page["display_cells"]
        contexts[page_number] = {"source_request_page": page_number, "raw_sha256": page["source_sha256"],
                                 "cells": cells,
                                 "context_semantics": "해당 원천 페이지의 표시 텍스트와 좌표; 학교·학과 코드를 추정하지 않습니다."}
        for link in report["attachment_links"]:
            links.append(_public(link | {"source_request_page": page_number,
                "source_listing_sha256": page["source_sha256"],
                "row_context_cells": _row_context(cells, link["source_geometry"])}))
    result["rows"] = links[args.offset:args.offset + args.limit]
    returned_pages = sorted({link["source_request_page"] for link in result["rows"]})
    result["page_contexts"] = [contexts[page] for page in returned_pages]
    returned_complete = args.offset == 0 and len(result["rows"]) == len(links)
    result["complete"] = source_complete and returned_complete
    result["status"] = "ok" if result["complete"] else "partial"
    result["completeness"] = {"scope": "지정 공시항목의 공개 PDF 첨부 링크 목록",
        "source_complete": source_complete, "returned_complete": returned_complete,
        "listing_complete": source_complete, "source_fetched_attachment_count": len(links),
        "return_offset": args.offset, "return_limit": args.limit,
        "pdf_content_extracted": False, "pdf_content_validation_complete": False,
        "reasons": (["page_limit_or_generation_unverified"] if not source_complete else [])
                   + (["return_range"] if not returned_complete else [])}


def _pdf(args: argparse.Namespace, result: dict[str, Any]) -> None:
    try:
        import pdfplumber  # noqa: F401: fail before a network call if unavailable.
    except ImportError as error:
        raise InputError("PDF 조회에는 pdfplumber가 필요합니다. 스킬의 설치 안내를 확인하세요.") from error
    parameters = {"filePath": args.file_path, "fileName": args.file_name, "saveName": args.save_name}
    result["query"] = {"attachment_parameters": parameters, "page_start": args.page_start,
                       "page_end": args.page_end,
                       "selection_provenance": "caller_supplied_from_actual_attachment_listing"}
    exchange = DirectClient().request(PDF_DOWNLOAD_URL, parameters, method="POST")
    result["sources"].append(_source(exchange))
    if not 200 <= exchange.status < 300:
        raise SourceError("공식 첨부 응답의 HTTP 상태가 성공이 아닙니다.")
    records, metadata = parse_pdf(exchange.body)
    total = metadata["page_count"]
    if args.page_start > total or args.page_end is not None and args.page_end > total:
        raise InputError("반환 페이지 범위가 실제 PDF 페이지 수를 벗어났습니다.")
    end = args.page_end if args.page_end is not None else total
    result["rows"] = _public(records[args.page_start - 1:end])
    result["pdf"] = _public(metadata)
    returned_complete = args.page_start == 1 and end == total
    result["status"] = "partial"
    result["complete"] = False
    result["completeness"] = {"scope": "실제 공개 첨부 PDF의 메모리 내 텍스트·표 추출",
        "source_complete": True, "returned_complete": returned_complete,
        "extraction_complete": len(records) == total, "content_validation_complete": False,
        "source_total_pages": total, "returned_page_start": args.page_start, "returned_page_end": end,
        "reasons": ["pdf_content_requires_validation"] + ([] if returned_complete else ["return_range"])}


def run_command(args: argparse.Namespace | dict[str, Any]) -> dict[str, Any]:
    """Create a fresh client for every invocation and return one JSON-safe result."""
    if isinstance(args, dict):
        args = argparse.Namespace(**args)
    result = _base(getattr(args, "command", "unknown"))
    try:
        _validate(args)
        if not _DEPENDENCIES_AVAILABLE:
            raise InputError("스킬에 포함된 공개 조회 어댑터를 찾을 수 없습니다.")
        if args.command == "pdf":
            _pdf(args, result)
        else:
            result["query"] = {"year": args.year, "division": args.division, "item": args.item,
                               "level": args.level, "max_pages": args.max_pages,
                               "limit": args.limit, "offset": args.offset}
            client = ViewerDataClient()
            _catalog(args, client, result)
            _collect(args, client, result)
    except (InputError, AttributeError) as error:
        result["status"] = "partial" if result["rows"] else "error"
        result["complete"] = False
        result["error"] = {"code": "invalid_input", "message": str(error) if isinstance(error, InputError)
                           else "명령과 필수 공개 선택조건을 확인하세요."}
    except (SourceError, ReportParseError):
        result["status"] = "partial" if result["rows"] else "error"
        result["complete"] = False
        result["completeness"]["source_complete"] = False
        result["error"] = {"code": "source_validation_error",
            "message": "대학알리미 원천 응답·페이지 생성·표 구조를 검증하지 못했습니다. 확인된 부분만 반환합니다."}
    except (urllib.error.URLError, TimeoutError, OSError):
        result["status"] = "partial" if result["rows"] else "error"
        result["complete"] = False
        result["completeness"]["source_complete"] = False
        result["error"] = {"code": "source_connection_error",
                           "message": "공식 대학알리미 서버 연결을 완료하지 못했습니다."}
    except Exception:
        result["status"] = "partial" if result["rows"] else "error"
        result["complete"] = False
        result["error"] = {"code": "internal_error",
                           "message": "조회 처리에 실패했습니다. 원문·세션·예외 상세는 출력하지 않습니다."}
    try:
        return _finish(result)
    except Exception:
        # Untrusted source strings must not bypass the final output allowlist.
        safe = _base("invalid_source")
        safe["status"] = "error"
        safe["error"] = {"code": "source_output_validation_error",
                         "message": "공개 표시값을 안전한 JSON으로 검증하지 못했습니다."}
        return _finish(safe)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="대학알리미 공식 장표·첨부를 새로 조회해 메모리 내 JSON으로 반환합니다.")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)
    for command in ("report", "attachments"):
        sub = commands.add_parser(command)
        sub.add_argument("--year", required=True, type=_year)
        sub.add_argument("--division", required=True, choices=("01", "02", "03", "04"))
        sub.add_argument("--item", required=True)
        sub.add_argument("--level", required=True, choices=("school", "department"))
        sub.add_argument("--max-pages", default=100, type=_positive,
                         help="최대 조회 페이지; 기본 100, 허용 1~10000. 제한시 전체 완료가 아닙니다.")
        sub.add_argument("--limit", default=50, type=_positive)
        sub.add_argument("--offset", default=0, type=_offset)
        if command == "report":
            sub.add_argument("--school-name", help="원천 schoolName 차원과 정확히 일치하는 이름")
            sub.add_argument("--dept-name", help="원천 deptName 차원과 정확히 일치하는 이름")
    sub = commands.add_parser("pdf")
    sub.add_argument("--file-path", required=True)
    sub.add_argument("--file-name", required=True)
    sub.add_argument("--save-name", required=True)
    sub.add_argument("--page-start", default=1, type=_positive)
    sub.add_argument("--page-end", type=_positive)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_command(build_parser().parse_args(argv))
    except (InputError, ValueError):
        result = _base("invalid")
        result["status"] = "error"
        result["error"] = {"code": "invalid_input", "message": "명령과 필수 인수를 확인하세요. --help로 사용법을 볼 수 있습니다."}
        result = _finish(result)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())

