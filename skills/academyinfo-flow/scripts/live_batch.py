"""Run a bounded set of fresh public lookups in one process.

Only this invocation may reuse a report source or an identical public JSON
query. Inputs are selector JSON, never saved statistics, and no response cache
survives the invocation. Requests remain sequential and retain each adapter's
rate limit and verification rules.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

import live_json
import live_report


MAX_INPUT_BYTES = 1024 * 1024
MAX_QUERIES = 100
MAX_NAME_FILTERS = 100

# Defaults mirror the single-query CLIs. A selector must belong to the chosen
# command; transport options, private runtime fields and arbitrary URLs are not
# accepted by this batch entry point.
_SPECS: dict[str, dict[str, Any]] = {
    "report": {
        "required": {"year", "division", "item", "level"},
        "defaults": {"max_pages": 100, "limit": 50, "offset": 0,
                     "school_name": None, "dept_name": None},
        "optional": {"school_names", "dept_names"},
    },
    "scope": {"required": set(), "defaults": {"year": None, "division": "02"}},
    "schools": {"required": {"year"}, "defaults": {"name": "", "max_pages": 1000}},
    "affiliations": {"required": {"year", "school_code"}, "defaults": {}},
    "departments": {"required": {"year", "school_code"},
                    "defaults": {"name": "", "max_pages": 1000}},
    "metric": {"required": {"year", "school_code", "dept_code", "major_code", "flag"},
               "defaults": {}},
    "info": {"required": {"year", "school_code", "dept_code", "major_code"}, "defaults": {}},
    "catalog": {"required": {"year", "division"}, "defaults": {"keyword": "", "limit": 30}},
}
_INTEGER_FIELDS = {"max_pages", "limit", "offset"}
_NAME_LIST_FIELDS = {"school_names", "dept_names"}
_INPUT_MESSAGE = "조회 목록과 각 명령의 필수 공개 선택조건을 확인하세요."


class InputError(ValueError):
    """Invalid batch input. Untrusted values are never included in errors."""

    def __init__(self, query_index: int | None = None):
        super().__init__(_INPUT_MESSAGE)
        self.query_index = query_index


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError()


def _normalise_query(query: Any, index: int) -> dict[str, Any]:
    if not isinstance(query, dict) or not isinstance(query.get("command"), str):
        raise InputError(index)
    command = query["command"]
    if command not in _SPECS:
        raise InputError(index)
    spec = _SPECS[command]
    allowed = {"command"} | spec["required"] | set(spec["defaults"]) | spec.get("optional", set())
    if set(query) - allowed or not spec["required"].issubset(query):
        raise InputError(index)
    selectors = deepcopy(spec["defaults"])
    selectors.update(deepcopy(query))
    for key, value in selectors.items():
        if key in _NAME_LIST_FIELDS:
            if (not isinstance(value, list) or len(value) > MAX_NAME_FILTERS
                    or any(not isinstance(name, str) or not 1 <= len(name) <= 200 for name in value)):
                raise InputError(index)
        elif key in _INTEGER_FIELDS:
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise InputError(index)
        elif value is None and (key in {"school_name", "dept_name"}
                                or command == "scope" and key == "year"):
            continue
        elif not isinstance(value, str):
            raise InputError(index)
    args = argparse.Namespace(**selectors)
    try:
        # Use the reviewed single-query validators so normalization (such as
        # numeric item IDs and integer limits) also determines duplicate keys.
        validator = live_report._validate if command == "report" else live_json._validate
        validator(args)
    except (live_report.InputError, live_json.InputError, AttributeError,
            TypeError, ValueError, OverflowError):
        raise InputError(index) from None
    return vars(args)


def validate_queries(payload: Any) -> list[dict[str, Any]]:
    """Validate the complete batch before opening a report or making a request."""
    if isinstance(payload, dict):
        if set(payload) != {"queries"}:
            raise InputError()
        payload = payload["queries"]
    if not isinstance(payload, list) or not 1 <= len(payload) <= MAX_QUERIES:
        raise InputError()
    return [_normalise_query(query, index) for index, query in enumerate(payload)]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise InputError()
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise InputError()


def read_input(path: str = "-") -> Any:
    """Read no more than one MiB, even when stdin or a file is oversized."""
    try:
        if path == "-":
            stream = getattr(sys.stdin, "buffer", sys.stdin)
            content = stream.read(MAX_INPUT_BYTES + 1)
        else:
            with Path(path).open("rb") as stream:
                content = stream.read(MAX_INPUT_BYTES + 1)
        if isinstance(content, str):
            content = content.encode("utf-8")
        if not content or len(content) > MAX_INPUT_BYTES:
            raise InputError()
        return json.loads(content.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise InputError() from None


def _base() -> dict[str, Any]:
    return {
        "schema_version": 1, "source": "대학알리미", "mode": "live", "command": "batch",
        "lookup_started_utc": datetime.now(timezone.utc).isoformat(),
        "status": "error", "complete": False, "results": [],
        "requested_query_count": 0, "returned_query_count": 0,
        "reuse_scope": "this_invocation_only", "raw_responses_saved": False,
        "performance": {"stages_seconds": {"validation": 0.0, "execution": 0.0,
                                            "output_projection": 0.0, "total": 0.0},
                        "repeated_queries_avoided": 0,
                        "repeated_report_sources_avoided": 0,
                        "repeated_json_queries_avoided": 0,
                        "source_report_fetches": 0, "catalog_requests_avoided": 0},
    }


def _input_failure(result: dict[str, Any], error: InputError) -> dict[str, Any]:
    result["error"] = {"code": "invalid_input", "message": _INPUT_MESSAGE,
                       "max_input_bytes": MAX_INPUT_BYTES, "max_queries": MAX_QUERIES}
    if error.query_index is not None:
        result["error"]["query_index"] = error.query_index
    return result


def _query_failure(command: str) -> dict[str, Any]:
    return {"schema_version": 1, "source": "대학알리미", "mode": "live", "command": command,
            "status": "error", "complete": False, "sources": [], "rows": [],
            "returned_row_count": 0, "data_availability": "error",
            "completeness": {"source_complete": False, "returned_complete": False},
            "error": {"code": "query_execution_error",
                      "message": "조회 처리에 실패했습니다. 원문·세션·예외 상세는 출력하지 않습니다."}}


def _count(stats: dict[str, Any], key: str) -> int:
    value = stats.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def run_queries(
    payload: Any, *, full_output: bool = False,
    report_handler: Callable[..., dict[str, Any]] | None = None,
    json_handler: Callable[..., dict[str, Any]] | None = None,
    batch_factory: Callable[..., Any] | None = None,
    compactor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute validated queries in input order, with invocation-local reuse.

    Injected handlers/context factories enable network-free verification. They
    receive only validated public selectors; report handlers also receive the
    same ``batch`` context for every report query in this invocation.
    """
    started = time.perf_counter()
    result = _base()
    stages = result["performance"]["stages_seconds"]
    try:
        if not isinstance(full_output, bool):
            raise InputError()
        queries = validate_queries(payload)
    except InputError as error:
        stages["validation"] = stages["total"] = round(time.perf_counter() - started, 6)
        return _input_failure(result, error)
    stages["validation"] = round(time.perf_counter() - started, 6)
    result["requested_query_count"] = len(queries)
    shared_json_client = json_handler is None
    report_handler = report_handler or live_report.run_command
    json_handler = json_handler or live_json.run_command
    json_results: dict[str, dict[str, Any]] = {}
    json_hits = 0
    report_stats: dict[str, Any] = {}
    projection_seconds = 0.0
    execution_started = time.perf_counter()
    stack = ExitStack()
    batch = None
    batch_unavailable = False
    try:
        if shared_json_client or any(query["command"] == "report" for query in queries):
            try:
                factory = batch_factory or live_report.ReportBatch
                batch = stack.enter_context(factory())
            except Exception:
                batch_unavailable = True
        for query in queries:
            command = query["command"]
            try:
                if command == "report":
                    item = (_query_failure(command) if batch_unavailable else
                            report_handler(deepcopy(query), batch=batch))
                else:
                    key = json.dumps(query, ensure_ascii=False, sort_keys=True, allow_nan=False,
                                     separators=(",", ":"))
                    if key in json_results:
                        json_hits += 1
                        item = deepcopy(json_results[key])
                    else:
                        try:
                            if shared_json_client:
                                # The report client also implements the public
                                # JSON adapter. Share its pacing state even for
                                # distinct JSON queries and mixed batches.
                                item = (_query_failure(command) if batch_unavailable else
                                        json_handler(deepcopy(query), network_client=batch.client()))
                            else:
                                item = json_handler(deepcopy(query))
                            if not isinstance(item, dict):
                                raise TypeError("result shape")
                        except Exception:
                            item = _query_failure(command)
                        json_results[key] = deepcopy(item)
                if not isinstance(item, dict):
                    raise TypeError("result shape")
                if command == "report" and not full_output:
                    projection_started = time.perf_counter()
                    project = compactor or live_report.compact_result
                    # The built-in projector returns an independent copy. Do
                    # not first duplicate all the cells it is about to remove.
                    item = project(deepcopy(item) if compactor is not None else item)
                    projection_seconds += time.perf_counter() - projection_started
                    if not isinstance(item, dict):
                        raise TypeError("projection shape")
                else:
                    item = deepcopy(item)
                result["results"].append(item)
            except Exception:
                result["results"].append(_query_failure(command))
        if batch is not None and isinstance(getattr(batch, "stats", None), dict):
            report_stats = dict(batch.stats)
    finally:
        try:
            stack.close()
        except Exception:
            result["error"] = {"code": "batch_cleanup_error",
                               "message": "조회 실행을 정상적으로 마무리하지 못했습니다."}
        json_results.clear()
    stages["output_projection"] = round(projection_seconds, 6)
    stages["execution"] = round(max(0.0, time.perf_counter() - execution_started - projection_seconds), 6)
    report_hits = _count(report_stats, "hits")
    result["performance"].update({
        "repeated_queries_avoided": report_hits + json_hits,
        "repeated_report_sources_avoided": report_hits,
        "repeated_json_queries_avoided": json_hits,
        "source_report_fetches": _count(report_stats, "misses"),
        "catalog_requests_avoided": _count(report_stats, "catalog_hits"),
    })
    items = result["results"]
    complete = (len(items) == len(queries) and not result.get("error") and
                all(item.get("status") == "ok" and item.get("complete") is True
                    and not item.get("error") for item in items))
    result["complete"] = complete
    result["status"] = ("ok" if complete else "error" if
                        all(item.get("status") == "error" for item in items) else "partial")
    result["returned_query_count"] = len(items)
    result["completeness"] = {
        "scope": "각 요청 결과의 원천·반환 범위를 개별 검증합니다.",
        "all_queries_complete": complete,
        "incomplete_query_count": sum(item.get("complete") is not True or
                                      item.get("status") != "ok" or bool(item.get("error"))
                                      for item in items),
        "error_query_count": sum(item.get("status") == "error" for item in items),
    }
    stages["total"] = round(time.perf_counter() - started, 6)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="공식 조회 목록을 한 번 실행하고 같은 실행의 중복 원천 요청을 줄입니다.")
    parser.add_argument("--input", default="-", help="조회 조건 JSON 파일; 기본 '-'는 표준입력입니다. 최대 1MiB·100개 조회.")
    parser.add_argument("--full-output", action="store_true", help="장표 셀 메타데이터를 포함합니다. 기본은 간결한 JSON입니다.")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = run_queries(read_input(args.input), full_output=args.full_output)
    except InputError as error:
        result = _input_failure(_base(), error)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] == "ok" and result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
