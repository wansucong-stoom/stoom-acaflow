"""Fresh official downloadable-file metadata and one explicitly selected XLSX.

Uses only the standard library. Cookies and HTML stay in memory; stdout contains
public metadata and provenance only. A catalog input is a live result obtained
for this same question, never a previous research archive or collection manifest.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import email.message
import hashlib
import http.cookiejar
import io
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

BASE_URL = "https://www.academyinfo.go.kr"
PAGE_URL = BASE_URL + "/main/main0830/main0830.do"
CATALOG_URL = BASE_URL + "/main/main0830/selectGongsiDataList.do"
PURPOSE_PAGE_URL = BASE_URL + "/popup/main2120/doInit.do"
PURPOSE_URL = BASE_URL + "/popup/main2120/doInsert.do"
DOWNLOAD_URL = BASE_URL + "/main/main0830/FileDown.do"
MAX_BYTES = 100 * 1024 * 1024
MAX_EXPANDED_BYTES = 500 * 1024 * 1024
FILE_FIELDS = ("std_dta_div_cd", "accm_schl_div_cd", "file_dtl_nm", "file_nm",
               "file_crtn_stt_dtm", "file_pth_nm", "item_id")
HTML = re.compile(r"<!doctype\b|<html\b|<script\b|<body\b", re.I)


class InputError(ValueError):
    pass


class SourceError(RuntimeError):
    pass


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError("명령과 필수 인수를 확인하세요. --help로 사용법을 볼 수 있습니다.")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _official_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "www.academyinfo.go.kr"
            or parsed.port not in (None, 443) or parsed.username or parsed.password
            or parsed.fragment or parsed.query):
        raise SourceError("검증된 공식 파일 조회 주소가 아닙니다.")


class OfficialRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class FileClient:
    """One anonymous, memory-only cookie session with bounded responses."""
    def __init__(self, *, opener=None, timeout: float = 45.0,
                 max_bytes: int = MAX_BYTES, interval: float = 1.0):
        if timeout <= 0 or not 0 < max_bytes <= MAX_BYTES or interval < 0:
            raise InputError("요청 제한을 확인하세요.")
        self.cookies = http.cookiejar.CookieJar()
        self.opener = opener if opener is not None else urllib.request.build_opener(
            OfficialRedirectHandler(), urllib.request.HTTPCookieProcessor(self.cookies))
        self.timeout, self.max_bytes, self.interval = timeout, max_bytes, interval
        self.sources: list[dict[str, Any]] = []
        self._last: float | None = None

    def request(self, url: str, parameters: dict[str, str] | None = None,
                *, method: str = "POST") -> tuple[bytes, dict[str, str]]:
        _official_url(url)
        params = dict(parameters or {})
        if method not in {"GET", "POST"} or (method == "GET" and params):
            raise InputError("검증된 GET/POST 파일 조회만 지원합니다.")
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in params.items()):
            raise InputError("공개 조회 조건은 문자열이어야 합니다.")
        if self._last is not None:
            time.sleep(max(0.0, self.interval - (time.monotonic() - self._last)))
        self._last = time.monotonic()
        payload = urllib.parse.urlencode(params).encode("utf-8") if method == "POST" else None
        request = urllib.request.Request(url, payload, {
            "User-Agent": "academyinfo-flow/1.0 (public disclosure research)",
            "Accept": "application/json, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, text/html",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest", "Referer": PAGE_URL,
        }, method=method)
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read(self.max_bytes + 1)
            headers = {"content_type": response.headers.get("Content-Type", ""),
                       "content_disposition": response.headers.get("Content-Disposition", "")}
            status, final_url = response.code, response.geturl()
        _official_url(final_url)
        self.sources.append({
            "source_url": url, "method": method, "public_parameters": params,
            "retrieved_utc": _utc(), "raw_sha256": hashlib.sha256(body).hexdigest(),
            "response_status": status, "response_content_type": headers["content_type"],
            "response_bytes": len(body), "final_url": final_url,
        })
        if len(body) > self.max_bytes:
            raise SourceError("파일 응답 크기 제한을 초과했습니다.")
        if not 200 <= status < 300:
            raise SourceError("공식 파일 서버 HTTP 오류입니다.")
        return body, headers


def _json(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8-sig"), parse_constant=lambda value:
                          (_ for _ in ()).throw(ValueError("nonfinite")))
    except (UnicodeError, ValueError) as error:
        raise SourceError("공식 응답이 정상 JSON이 아닙니다.") from error


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value or HTML.search(value) or any(
            ord(char) < 32 for char in value):
        raise SourceError("공개 파일 목록의 문자열을 검증할 수 없습니다.")
    return value


def _file_row(row: Any, division: str) -> dict[str, Any]:
    if not isinstance(row, dict) or any(key not in row for key in FILE_FIELDS):
        raise SourceError("공식 파일 목록의 필드가 바뀌었습니다.")
    clean = {key: row[key] for key in FILE_FIELDS}
    for key in FILE_FIELDS[:-1]:
        _text(clean[key])
    if (clean["accm_schl_div_cd"] != division
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", clean["std_dta_div_cd"])
            or not re.fullmatch(r"[^/\\]+\.xlsx", clean["file_dtl_nm"], re.I)
            or not clean["file_nm"].lower().endswith(".xlsx")):
        raise SourceError("파일 코드·기관 구분·XLSX 파일명을 확인할 수 없습니다.")
    source_path = clean["file_pth_nm"]
    if (not source_path.startswith("/infofile/") or ".." in source_path.split("/")
            or "\\" in source_path or "?" in source_path or "#" in source_path):
        raise SourceError("공식 파일 경로를 검증할 수 없습니다.")
    item_id = clean["item_id"]
    if isinstance(item_id, bool) or not isinstance(item_id, (int, str)) or not re.fullmatch(
            r"[1-9][0-9]*", str(item_id)):
        raise SourceError("목록의 실제 항목 ID를 확인할 수 없습니다.")
    return clean


def _base(command: str) -> dict[str, Any]:
    return {"schema_version": 1, "source": "대학알리미", "mode": "live",
            "command": command, "status": "ok", "request_year": None,
            "lookup_started_utc": _utc(), "complete": False, "sources": [], "rows": [],
            "completeness": {"scope": "아직 검증되지 않은 파일 조회",
                             "source_complete": False, "returned_complete": False},
            "value_semantics": "파일 목록의 실제 메타데이터이며, 수치·공시연도·지침 해석을 대신하지 않습니다."}


def _finish(result: dict[str, Any], client: FileClient | None) -> dict[str, Any]:
    if client is not None:
        result["sources"].extend(client.sources)
    result["lookup_completed_utc"] = _utc()
    result["retrieved_utc"] = result["sources"][-1]["retrieved_utc"] if result["sources"] else None
    result["returned_row_count"] = len(result["rows"])
    result["data_availability"] = ("error" if result["status"] == "error" else
                                   "available" if result["rows"] or result.get("data") else "empty")
    return result


def _catalog(client: FileClient, division: str, keyword: str) -> list[dict[str, Any]]:
    # The observed public endpoint works directly; do not fetch unrelated HTML
    # pages to warm a session or discover the already verified route again.
    body, _ = client.request(CATALOG_URL, {"schl_div_cd": division, "searchValue": keyword})
    payload = _json(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("resultList"), list):
        raise SourceError("공식 파일 목록의 resultList를 확인할 수 없습니다.")
    rows = [_file_row(row, division) for row in payload["resultList"]]
    codes = [row["std_dta_div_cd"] for row in rows]
    if len(codes) != len(set(codes)):
        raise SourceError("같은 기관 구분에 중복 파일 코드가 있습니다.")
    return rows


def _input_catalog(path: str, division: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        payload = _json(Path(path).read_bytes())
    except OSError as error:
        raise InputError("현재 질문에서 받은 파일 목록 JSON을 읽을 수 없습니다.") from error
    if (not isinstance(payload, dict) or payload.get("schema_version") != 1
            or payload.get("command") != "file_catalog" or payload.get("mode") != "live"
            or payload.get("source") != "대학알리미" or payload.get("status") != "ok"
            or payload.get("complete") is not True
            or payload.get("completeness", {}).get("source_complete") is not True
            or not isinstance(payload.get("rows"), list)):
        raise InputError("동일 질문에서 새로 받은 완전한 file_catalog JSON만 재사용할 수 있습니다.")
    rows = [_file_row(row, division) for row in payload["rows"]]
    if len({row["std_dta_div_cd"] for row in rows}) != len(rows):
        raise InputError("입력 목록에 중복 파일 코드가 있습니다.")
    evidence = [source for source in payload.get("sources", []) if isinstance(source, dict)
                and source.get("source_url") == CATALOG_URL and source.get("method") == "POST"
                and source.get("public_parameters", {}).get("schl_div_cd") == division]
    if len(evidence) != 1:
        raise InputError("입력 목록의 공식 조회 출처·기관 구분을 확인할 수 없습니다.")
    source = evidence[0]
    keyword = source["public_parameters"].get("searchValue", "")
    content_type = source.get("response_content_type", "")
    if (not isinstance(keyword, str) or HTML.search(keyword)
            or any(ord(char) < 32 for char in keyword)
            or not isinstance(content_type, str) or HTML.search(content_type)
            or any(ord(char) < 32 for char in content_type)):
        raise InputError("입력 목록의 공개 조회 조건·응답 형식을 확인할 수 없습니다.")
    try:
        retrieved = datetime.fromisoformat(source["retrieved_utc"])
        if retrieved.tzinfo is None or retrieved.utcoffset().total_seconds() != 0:
            raise ValueError("not UTC")
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise InputError("입력 목록의 UTC 조회 시각을 확인할 수 없습니다.") from error
    if (not isinstance(source.get("response_status"), int)
            or not 200 <= source["response_status"] < 300
            or not re.fullmatch(r"[a-f0-9]{64}", str(source.get("raw_sha256", "")))):
        raise InputError("입력 목록의 정상 응답·출처 해시를 확인할 수 없습니다.")
    # Keep selected public provenance fields, never arbitrary input fields/cookies.
    public = {key: source[key] for key in ("source_url", "method", "retrieved_utc",
              "raw_sha256", "response_status", "response_content_type") if key in source}
    public["public_parameters"] = {"schl_div_cd": division,
                                   "searchValue": keyword}
    public["reused_for_same_question"] = True
    return rows, public


def _attachment_name(disposition: str) -> set[str]:
    message = email.message.Message()
    message["Content-Disposition"] = disposition
    if message.get_content_disposition() != "attachment":
        raise SourceError("응답이 첨부파일로 확인되지 않습니다.")
    name = message.get_filename()
    if not name:
        raise SourceError("첨부 응답의 파일명을 확인할 수 없습니다.")
    names = {urllib.parse.unquote(name)}
    # The source also sends UTF-8 filename bytes in legacy Latin-1 headers.
    for _ in range(3):
        for value in tuple(names):
            try:
                names.add(value.encode("latin1").decode("utf-8"))
            except (UnicodeError, ValueError):
                pass
    return names


def _xlsx(body: bytes, headers: dict[str, str], selected: dict[str, Any]) -> None:
    if not body.startswith(b"PK\x03\x04") or "text/html" in headers["content_type"].lower():
        raise SourceError("응답이 XLSX ZIP 파일이 아닙니다.")
    if not ({selected["file_nm"], selected["file_dtl_nm"]} &
            _attachment_name(headers["content_disposition"])):
        raise SourceError("첨부파일 이름이 선택한 공식 목록과 다릅니다.")
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            entries = archive.infolist()
            names = set(archive.namelist())
            if (len(entries) > 10000 or len(names) != len(entries)
                    or sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES
                    or any(entry.flag_bits & 1 for entry in entries)
                    or not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(names)
                    or not any(name.startswith("xl/worksheets/") and name.endswith(".xml") for name in names)):
                raise SourceError("XLSX 내부 구조·압축 해제 크기를 확인할 수 없습니다.")
            if archive.testzip() is not None:
                raise SourceError("XLSX ZIP 무결성 검사에 실패했습니다.")
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            types = ET.fromstring(archive.read("[Content_Types].xml"))
            if (workbook.tag != "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook"
                    or not any(entry.get("PartName") == "/xl/workbook.xml" and entry.get("ContentType") ==
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
                               for entry in types)):
                raise SourceError("응답의 Excel 통합문서 형식을 확인할 수 없습니다.")
    except (zipfile.BadZipFile, RuntimeError, ET.ParseError, KeyError, OSError) as error:
        raise SourceError("XLSX 파일 무결성·형식 검증에 실패했습니다.") from error


def _output_path(value: Any) -> Path:
    if not isinstance(value, str) or any(ord(char) < 32 for char in value):
        raise InputError("출력 파일은 절대 .xlsx 경로여야 합니다.")
    path = Path(value)
    if not path.is_absolute() or path.suffix.lower() != ".xlsx":
        raise InputError("출력 파일은 절대 .xlsx 경로여야 합니다.")
    if path.exists() or path.is_symlink():
        raise InputError("기존 출력 파일을 덮어쓰지 않습니다. 새 파일 경로를 지정하세요.")
    if any(parent.is_symlink() for parent in path.parents):
        raise InputError("출력 경로에 심볼릭 링크가 포함되어 있습니다.")
    return path.resolve()


def run_command(args: argparse.Namespace | dict[str, Any], *,
                network_client: FileClient | None = None) -> dict[str, Any]:
    if isinstance(args, dict):
        args = argparse.Namespace(**args)
    raw_command = getattr(args, "command", "unknown")
    result = _base({"catalog": "file_catalog", "download": "file_download"}.get(raw_command, "unknown"))
    client = None
    phase = "input"
    try:
        division = args.division
        if raw_command not in {"catalog", "download"} or division not in {"01", "02", "03", "04"}:
            raise InputError("명령과 학교 구분 01, 02, 03, 04를 확인하세요.")
        output = _output_path(args.output) if raw_command == "download" else None
        keyword = getattr(args, "keyword", "")
        if not isinstance(keyword, str) or HTML.search(keyword) or any(ord(char) < 32 for char in keyword):
            raise InputError("파일 목록 검색어는 공개 문자열이어야 합니다.")
        code = getattr(args, "code", "")
        if raw_command == "download" and (not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", code)):
            raise InputError("파일 목록에서 확인한 실제 코드를 지정하세요.")
        limit = getattr(args, "limit", 1000)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise InputError("반환 제한은 1~1000의 정수여야 합니다.")
        result["query"] = {"division": division, "keyword": keyword} if raw_command == "catalog" else {
            "division": division, "code": code}
        phase = "catalog"
        catalog_input = getattr(args, "catalog_input", None)
        if catalog_input and raw_command == "download":
            rows, source = _input_catalog(catalog_input, division)
            result["sources"].append(source)
            result["catalog_metadata_origin"] = "same_question_input"
        else:
            client = network_client if network_client is not None else FileClient()
            rows = _catalog(client, division, keyword if raw_command == "catalog" else "")
            result["catalog_metadata_origin"] = "fresh_lookup"
        if raw_command == "catalog":
            result["rows"] = rows[:limit]
            complete = len(rows) <= limit
            result["status"] = "ok" if complete else "partial"
            result["complete"] = complete
            result["completeness"] = {"scope": "지정한 기관·검색어의 공식 다운로드 파일 목록",
                "source_complete": True, "returned_complete": complete,
                "source_item_rows": len(rows), "return_limit": limit}
            return _finish(result, client)
        matching = [row for row in rows if row["std_dta_div_cd"] == code]
        if len(matching) != 1:
            raise SourceError("선택한 실제 파일 코드가 현재 목록에 유일하게 존재하지 않습니다.")
        selected = matching[0]
        result["selected_file"] = selected
        result["title"] = selected["file_nm"]
        if client is None:
            client = network_client if network_client is not None else FileClient()
        phase = "purpose"
        purpose = {"schlDivCd": division, "itemId": str(selected["item_id"]),
                   "dwldUsrDivCd": "008", "dwldEtcUsrNm": "대학 공시자료 연구",
                   "dwldPrpsCd": "003", "dwldEtcPrpsCtnt": "",
                   "dwldDtlCtnt": "전국 대학 학과 및 입학정원 변화 비교 분석"}
        body, _ = client.request(PURPOSE_URL, purpose)
        payload = _json(body)
        if not isinstance(payload, dict) or payload.get("result") != "success":
            raise SourceError("공식 다운로드 목적 등록이 성공하지 않았습니다.")
        phase = "download"
        parameters = {"schl_div_cd": division, "searchValue": "",
                      "file_nm": selected["file_nm"], "file_path": selected["file_pth_nm"],
                      "file_dtl_nm": selected["file_dtl_nm"], "std_dta_div_cd": selected["std_dta_div_cd"]}
        body, headers = client.request(DOWNLOAD_URL, parameters)
        phase = "validation"
        _xlsx(body, headers, selected)
        phase = "output"
        output.parent.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            with output.open("xb") as destination:
                created = True
                destination.write(body)
        except OSError:
            if created:
                output.unlink(missing_ok=True)
            raise
        result["data"] = {"output_path": str(output), "title": selected["file_nm"],
                          "source_code": selected["std_dta_div_cd"], "bytes": len(body),
                          "sha256": hashlib.sha256(body).hexdigest(),
                          "validation": "xlsx_attachment_name_and_ooxml_zip_integrity"}
        result["complete"] = True
        result["completeness"] = {"scope": "현재 목록에서 명시적으로 선택한 XLSX 파일 한 개",
                                  "source_complete": True, "returned_complete": True}
    except (InputError, AttributeError):
        result["status"] = "error"
        result["error"] = {"code": "invalid_input", "phase": phase,
                           "message": "필수 공개 조건·현재 질문의 목록 입력·새 절대 XLSX 경로를 확인하세요."}
    except SourceError:
        result["status"] = "error"
        result["error"] = {"code": "source_validation_error", "phase": phase,
                           "message": "공식 파일 응답을 정상 자료로 검증하지 못했습니다. 파일을 저장하지 않습니다."}
    except (urllib.error.URLError, TimeoutError, OSError):
        result["status"] = "error"
        result["error"] = {"code": "output_error" if phase == "output" else "source_connection_error",
                           "phase": phase, "message": "공식 연결 또는 새 파일 저장을 완료하지 못했습니다."}
    except Exception:
        result["status"] = "error"
        result["error"] = {"code": "internal_error", "phase": phase,
                           "message": "파일 조회에 실패했습니다. 원문·세션·예외 상세는 출력하지 않습니다."}
    return _finish(result, client)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="공식 다운로드 목록을 새로 조회하고 선택한 XLSX 한 개만 검증·저장합니다.")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)
    catalog = commands.add_parser("catalog")
    catalog.add_argument("--division", required=True, choices=("01", "02", "03", "04"))
    catalog.add_argument("--keyword", default="")
    catalog.add_argument("--limit", type=int, default=1000)
    download = commands.add_parser("download")
    download.add_argument("--division", required=True, choices=("01", "02", "03", "04"))
    download.add_argument("--code", required=True, help="같은 질문의 공식 파일 목록에서 확인한 코드")
    download.add_argument("--catalog-input", help="같은 질문에서 새로 받은 완전한 file_catalog JSON")
    download.add_argument("--output", required=True, help="새 절대 .xlsx 경로; 기존 파일 덮어쓰기 없음")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_command(build_parser().parse_args(argv))
    except (InputError, ValueError):
        result = _base("invalid")
        result["status"] = "error"
        result["error"] = {"code": "invalid_input", "message": "명령과 필수 공개 인수를 확인하세요."}
        result = _finish(result, None)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        import route_registry
        result["route_registry"] = route_registry.observe_result(result)
    except Exception:
        # Learning a route must never turn an otherwise valid source result into
        # a failure or expose state-file paths, cookies, or exception details.
        result["route_registry"] = {"status": "unavailable",
                                    "message": "조회 경로 메타데이터 기록을 완료하지 못했습니다."}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] == "ok" and result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
