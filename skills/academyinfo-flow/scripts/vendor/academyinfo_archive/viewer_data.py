"""Replay the official public report protocol without running a viewer.

The HTML bootstrap is transport metadata, never an archived artifact. Its
generated SQL and ephemeral report key are used verbatim in memory, then
discarded. This module does not accept arbitrary SQL or report-server URLs.
"""
from __future__ import annotations

import re
import http.cookiejar
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .direct import DirectClient, Exchange, OfficialRedirectHandler, SourceError, validate_public_url

BOOTSTRAP_URL = "https://academyinfo.go.kr/uipnh/unt/unmcom/RdViewer.do"
DATA_URL = "https://academyinfo.go.kr:443/NewAcInfo.do"
PUBLIC_DATA_PATHS = frozenset({"/NewAcInfo.do", "/NewAcInfo2.do", "/UbiServer.do"})
_LITERAL = r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')'''
_EXTRA_FIELDS = frozenset({
    "resultMaster", "resultHeader", "resultBody", "resultSum", "strQuery",
    "url", "strSvyYr", "strSchlNm", "strPgmNm", "strUnt", "strRmk",
    "strNowDate", "strWrtrNm", "strFormClftCd", "isMerge", "columLaung",
    "strItemId", "strItemId2", "strSchlDivCd", "strMasterId",
})


def _js_string(literal: str) -> str:
    """Decode one static JavaScript string literal without evaluating code."""
    if len(literal) < 2 or literal[0] != literal[-1] or literal[0] not in "'\"":
        raise SourceError("원천 초기화 문자열 형식이 변경되었습니다.")
    chars = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
             "v": "\v", "0": "\0", "\\": "\\", "'": "'", '"': '"'}
    return re.sub(r"\\(?:u([0-9A-Fa-f]{4})|x([0-9A-Fa-f]{2})|(.))",
                  lambda m: chr(int(m[1] or m[2], 16)) if m[1] or m[2]
                  else chars.get(m[3], m[3]), literal[1:-1])


def decode_metadata(value: str, *, max_bytes: int = 16 * 1024 * 1024) -> str:
    """Decode the public report schema, not the generated query or a token.

    Academyinfo's Java escape convention uses ``\\e`` for a zero byte.
    The zlib checksum is required; unsupported encodings fail closed.
    """
    chars = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
             "e": "\0", " ": " ", "\\": "\\", "'": "'", '"': '"'}

    def replace(m):
        if m[1]:
            return chr(int(m[1], 16))
        if m[2] not in chars:
            raise SourceError("표 메타데이터 escape 형식을 확인할 수 없습니다.")
        return chars[m[2]]

    try:
        raw = re.sub(r"\\(?:u([0-9A-Fa-f]{4})|(.))", replace, value).encode("latin1")
        dec = zlib.decompressobj()
        data = dec.decompress(raw, max_bytes + 1)
        if len(data) > max_bytes or dec.unconsumed_tail:
            raise SourceError("표 메타데이터 크기 제한을 초과했습니다.")
        data += dec.flush()
        if len(data) > max_bytes or not dec.eof or dec.unused_data:
            raise SourceError("표 메타데이터 압축을 검증할 수 없습니다.")
        return data.decode("utf-8")
    except (UnicodeError, zlib.error) as e:
        raise SourceError("표 메타데이터 압축·문자셋 검증에 실패했습니다.") from e


@dataclass(repr=False)
class ReportSession:
    initial: Exchange
    selectors: dict[str, str]
    schema_text: dict[str, str]
    title: str
    _runtime: dict[str, str] = field(repr=False)
    _server_url: str = field(repr=False)
    _service_id: str = field(repr=False)
    schema_identity: dict[str, str] = field(default_factory=dict)

    def __repr__(self):
        return f"ReportSession(selectors={self.selectors!r}, title={self.title!r})"

    def public_metadata(self) -> dict[str, Any]:
        return {"protocol": "academyinfo-public-report", "source_language": "ko",
                "selectors": dict(self.selectors), "title": self.title,
                "runtime_fields_omitted": True,
                "schema_text": dict(self.schema_text)}

    def close(self) -> None:
        self._runtime.clear()
        self._service_id = ""


@dataclass(frozen=True)
class ReportStatus:
    expected_pages: int
    complete: bool
    multiple_paper: bool


def parse_status(body: bytes) -> ReportStatus:
    """The public client consumes the last count#state#paper status chunk."""
    try:
        text = body.decode("utf-8").strip()
    except UnicodeError as e:
        raise SourceError("공시 페이지 상태 응답의 문자셋을 확인할 수 없습니다.") from e
    if text.startswith("ER0"):
        raise SourceError("원천 서버가 공시 페이지 생성 오류를 반환했습니다.")
    # A bounded read may stop in the next chunk. Use the last *complete*
    # status, rather than claiming that the entire HTTP stream was consumed.
    chunks = list(re.finditer(r"(?:^|\^)\s*(\d+)#([01])#([01])(?=\^|\s*$)", text))
    if not chunks or re.search(r"[^0-9#^\s]", text):
        raise SourceError("전체 페이지 상태 응답 형식이 변경되었습니다.")
    m = chunks[-1]
    return ReportStatus(int(m[1]), m[2] == "0", m[3] == "1")


class ViewerDataClient(DirectClient):
    """Public HTTP only: bootstrap -> report XML -> JSON in the archive layer."""

    def __init__(self, *, opener=None, **kwargs):
        # Fresh anonymous cookie state may be required by the report bootstrap;
        # never import a signed-in browser session or serialize these cookies.
        opener = opener or urllib.request.build_opener(
            OfficialRedirectHandler(),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        super().__init__(opener=opener, **kwargs)

    def _runtime_post(self, url: str, runtime: dict[str, str],
                      public_parameters: dict[str, str], *,
                      read_prefix_bytes: int | None = None) -> tuple[Exchange, str]:
        validate_public_url(url)
        if urllib.parse.urlsplit(url).path not in PUBLIC_DATA_PATHS:
            raise SourceError("공개 공시 데이터 경로가 변경되었습니다.")
        self._last_response_diagnostic = {}
        # Match _ubi_ajax.serialize(), which encodes each value twice.
        payload = "&".join(k + "=" + urllib.parse.quote(
            urllib.parse.quote(str(v), safe=""), safe="") for k, v in runtime.items()).encode("utf-8")
        time.sleep(max(0.0, self.interval - (time.monotonic() - self._last)))
        self._last = time.monotonic()
        request = urllib.request.Request(url, data=payload, method="POST", headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "User-Agent": "stoom-academyinfo/0.1 (public disclosure archive)",
        })
        budget = getattr(self, "request_budget", None)
        for attempt in range(self.retries + 1):
            if budget is not None:
                budget.consume()
            self._last = time.monotonic()
            try:
                response = self.opener.open(request, timeout=self.timeout)
                break
            except urllib.error.HTTPError as e:
                response = e
                break  # HTTP access refusals never retry or use another route.
            except (urllib.error.URLError, TimeoutError) as e:
                reason = str(getattr(e, 'reason', e)).casefold()
                denied = any(word in reason for word in ('blocked by policy', 'access denied', 'permission denied', 'forbidden'))
                if denied or attempt >= self.retries:
                    raise SourceError("공시 원천 서버 요청에 실패했습니다.") from e
                time.sleep(max(self.interval, min(2 ** attempt, 4)))
        with response:
            body = response.read(read_prefix_bytes or (self.max_bytes + 1))
            if read_prefix_bytes is None and len(body) > self.max_bytes:
                raise SourceError("공시 원문 응답 크기 제한을 초과했습니다.")
            final_url = response.geturl()
            validate_public_url(final_url)
            exchange = Exchange(url, "POST", dict(public_parameters), body, response.code,
                                response.headers.get("Content-Type", ""),
                                datetime.now(timezone.utc).isoformat(), final_url)
            length = response.headers.get('Content-Length', '')
            age = response.headers.get('Age', '')
            encoding = response.headers.get('Content-Encoding', 'identity').lower()
            mime = exchange.content_type.split(';', 1)[0].strip().lower()
            self._last_response_diagnostic = {
                'http_status': exchange.status, 'body_bytes': len(body),
                'declared_content_length': int(length) if length.isdigit() else None,
                'age_seconds': int(age) if age.isdigit() else None,
                'chunked': 'chunked' in [v.strip().lower() for v in response.headers.get('Transfer-Encoding', '').split(',')],
                'content_encoding': encoding if encoding in ('identity','gzip','deflate','br') else 'unknown',
                'mime': mime if re.fullmatch(r'[a-z0-9.+-]+/[a-z0-9.+-]+', mime) else 'unknown',
                'cache_header_present': bool(response.headers.get('Cache-Control')),
                'via_header_present': bool(response.headers.get('Via')),
                'final_path_known': urllib.parse.urlsplit(final_url).path in PUBLIC_DATA_PATHS,
            }
            exportseq = response.headers.get("exportseq", "")
        if not 200 <= exchange.status < 300:
            error = SourceError(f"공시 원천 서버 HTTP {exchange.status} 오류입니다.")
            error.transport_diagnostic = dict(self._last_response_diagnostic)
            error.policy_refusal = exchange.status in {401, 403} or bool(
                re.search(rb'blocked by policy|access denied|permission denied|forbidden', body, re.I))
            raise error
        if body.startswith(b"ER0"):
            error = SourceError("공시 원천 서버가 조회 오류를 반환했습니다.")
            error.transport_diagnostic = dict(self._last_response_diagnostic)
            raise error
        return exchange, exportseq

    @staticmethod
    def _xml(body: bytes):
        try:
            root = ET.fromstring(body)
        except ET.ParseError as e:
            error = SourceError("공시 원문 XML 형식을 확인할 수 없습니다.")
            error.policy_refusal = bool(re.search(rb'blocked by policy|access denied|forbidden', body, re.I))
            # A bounded fresh report may recover a truncated public Doc.
            # HTML, unknown responses, and access refusals do not qualify.
            error.retryable_public_xml = bool(
                re.match(rb'\s*(?:<\?xml[^>]*>\s*)?<Doc(?:\s|>)', body[:512])
                and not error.policy_refusal)
            raise error from e
        if root.tag != "Doc" or not root.findall("Page"):
            error = SourceError("공시 원문이 정상 report Doc/Page가 아닙니다.")
            error.policy_refusal = bool(re.search(rb'blocked by policy|access denied|forbidden', body, re.I))
            raise error
        return root

    def start_report(self, year: str, school_division: str, item_id: str,
                     *, level: str = "department", school_code: str | None = None) -> ReportSession:
        if (not re.fullmatch(r"\d{4}", year) or school_division not in {"01", "02", "03", "04"}
                or not re.fullmatch(r"\d{1,6}", item_id) or level not in {"department", "school"}):
            raise ValueError("공시연도·학교구분·항목 ID·조회단위를 확인해주세요.")
        if school_code is not None and (not re.fullmatch(r"[0-9]{7}", school_code) or level != "department"):
            raise ValueError("학교 범위 기본양식은 실제 7자리 학교코드와 학과 조회가 필요합니다.")
        self.page_recovery_events = []
        form = "60" if school_code else "36" if level == "department" else "30"
        selectors = {"pubYear": year, "schoolDivision": school_division,
                     "itemId": str(int(item_id)), "level": level, "language": "ko"}
        if school_code:
            selectors.update(schoolCode=school_code, formClassification="60")
        bootstrap = self.request(BOOTSTRAP_URL, {
            "paramSvyYr": year, "paramSchlDivCd": school_division,
            "paramItemId": str(int(item_id)), "paramFormClftCd": form,
            "paramMjrItem1": "00", "paramMjrItem2": "00", "paramMjrItem3": "00",
            "paramSchlKindCd": "99", "paramSchlEstabCd": "99", "paramDomainDiv": "MOB",
            **({"paramSchlCd": school_code, "paramZoneCd": "99"} if school_code else {}),
        })
        if bootstrap.status != 200:
            raise SourceError(f"공시 초기화 HTTP {bootstrap.status} 오류입니다.")
        try:
            source = bootstrap.body.decode("utf-8")
        except UnicodeError as e:
            raise SourceError("공시 초기화 응답이 UTF-8이 아닙니다.") from e
        # Never return or persist this HTML: it contains generated SQL/tokens.
        source = re.sub(r"(?m)^\s*//.*$", "", source)
        variables = {m[1]: _js_string(m[2]) for m in re.finditer(
            r"\bvar\s+(pKey|pArg|pServerUrl|pResId|pJrf)\s*=\s*(" + _LITERAL + r")", source)}
        required = {"pKey", "pArg", "pServerUrl", "pResId", "pJrf"}
        if set(variables) != required:
            raise SourceError("공개 공시 초기화 프로토콜이 변경되었습니다.")
        server = variables["pServerUrl"]
        validate_public_url(server)
        extra = {m[1]: _js_string(m[2]) for m in re.finditer(
            r"htmlViewer\.params\.(\w+)\s*=\s*(" + _LITERAL + r")", source)
            if m[1] in _EXTRA_FIELDS}
        if (extra.get("strSvyYr") != year or extra.get("strItemId") != str(int(item_id))
                or extra.get("strFormClftCd") != form or extra.get("strSchlDivCd") != school_division
                or extra.get("columLaung") != "KOR"):
            raise SourceError("요청 범위 또는 한국어 공시 응답을 검증할 수 없습니다.")
        schema = {name: decode_metadata(extra[name]) for name in
                  ("resultMaster", "resultHeader", "resultBody", "resultSum") if name in extra}
        if not {"resultMaster", "resultHeader", "resultBody"}.issubset(schema):
            raise SourceError("공시 표 스키마가 없습니다.")
        runtime = {"reqtype": "0", "cHJvY2lk": "GATEWAY", "key": variables["pKey"],
                   "ubiserverurl": server, "jrffile": variables["pJrf"],
                   "resid": variables["pResId"], "arg": variables["pArg"],
                   "exportseq": str(int(time.time() * 1000)), "isStreaming": "true",
                   "issvg": "false", "isencrypt": "true", "isencrypt64": "false",
                   "language": "ko", "isredbc": "false", **extra}
        initial, sequence = self._runtime_post(server, runtime, {**selectors, "reqtype": "0"})
        root = self._xml(initial.body)
        runtime["exportseq"] = sequence or runtime["exportseq"]
        service = root.get("serviceid", "")
        # Public UbiDoc.getData() permits a missing serviceid (empty string).
        if not sequence:
            raise SourceError("공시 페이지 세션을 검증할 수 없습니다.")
        identity = {'form_clft_cd': form}
        if 'strMasterId' in extra:
            identity['item_mstr_id'] = extra['strMasterId']
        return ReportSession(initial, selectors, schema, extra.get("strPgmNm", ""), runtime, server, service,
                             schema_identity=identity)

    def report_status(self, session: ReportSession) -> ReportStatus:
        if not session._runtime:
            raise SourceError("공시 요청 세션이 종료되었습니다.")
        params = {**session._runtime, "reqtype": "99"}
        # NewAcInfo's status stream repeats the current status rapidly until
        # generation finishes. Read a small prefix and close the connection;
        # callers can poll later. It is a control response, not an archived page.
        for attempt in range(5):
            exchange, _ = self._runtime_post(session._server_url, params,
                                            {**session.selectors, "reqtype": "99"},
                                            read_prefix_bytes=4096)
            if exchange.body or attempt == 4:
                break
            time.sleep(max(self.interval, min(2 ** attempt, 8)))
        body = exchange.body
        # Source-observed UbiServer framing (2026/02/163): exactly one
        # leading NUL before the usual caret-delimited status stream.
        if urllib.parse.urlsplit(session._server_url).path == '/UbiServer.do' and body.startswith(b'\x00^'):
            body = body[1:]
        try:
            status = parse_status(body)
        except SourceError as error:
            error.policy_refusal = bool(re.search(rb'blocked by policy|access denied|forbidden', body, re.I))
            error.transport_diagnostic = dict(getattr(self, '_last_response_diagnostic', {}))
            error.source_stage = 'generation_status'
            raise
        session._last_generation_status = status
        return status

    def fetch_page(self, session: ReportSession, page: int, *, document_local_page_numbers: bool = False) -> Exchange:
        if not session._runtime or not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise ValueError("유효한 공시 세션과 양의 페이지 번호가 필요합니다.")
        # This is the public _requestReportPage() field subset, unmodified.
        runtime = {k: session._runtime[k] for k in
                   ("cHJvY2lk", "key", "ubiserverurl", "jrffile", "resid", "exportseq", "issvg")}
        runtime.update({"reqtype": f"91#{page}", "timeout": str(int(self.timeout * 1000)),
                        "userHeader": "", "serviceid": session._service_id})
        malformed_doc_retries = 0
        for attempt in range(5):
            try:
                exchange, _ = self._runtime_post(session._server_url, runtime,
                                                {**session.selectors, "reqtype": f"91#{page}"})
            except SourceError as error:
                diagnostic = getattr(error, 'transport_diagnostic', {})
                error.requested_page = page
                error.source_stage = 'report_page_transport'
                # Retry only transient server failures, on the identical page
                # and report job. Never retry access refusals or change routes.
                if (diagnostic.get('http_status') in {500, 502, 503, 504}
                        and not getattr(error, 'policy_refusal', False) and attempt < 2):
                    events = getattr(self, 'page_recovery_events', None)
                    if events is None:
                        self.page_recovery_events = events = []
                    events.append({'source_request_page': page, 'http_status': diagnostic['http_status'],
                                   'retry_attempt': attempt + 1, 'reason': 'transient_server_error'})
                    time.sleep(max(self.interval, 2 ** attempt))
                    continue
                raise
            try:
                root = self._xml(exchange.body)
            except SourceError as error:
                if not exchange.body and attempt < 4:
                    previous = getattr(session, '_last_generation_status', None)
                    if attempt == 0 and previous is not None and previous.complete:
                        # Audit the existing job through its public control
                        # route. This never starts or substitutes another job.
                        try:
                            checked = self.report_status(session)
                        except SourceError as check_error:
                            check_error.requested_page = page
                            check_error.source_stage = 'generation_recheck'
                            check_error.transport_diagnostic = dict(getattr(self, '_last_response_diagnostic', {}))
                            raise
                        if not checked.complete or checked.expected_pages != previous.expected_pages:
                            changed = SourceError('빈 페이지 재시도 중 보고서 생성 상태 또는 전체 페이지 수가 변경되었습니다.')
                            changed.requested_page = page
                            changed.source_stage = 'generation_recheck'
                            raise changed
                    # Observed HTTP-success responses can contain no XML.
                    # Wait before retrying the identical page in this session.
                    # HTTP/policy refusals are raised outside this catch.
                    time.sleep(max(self.interval, min(2 ** attempt, 8)))
                    continue
                if getattr(error,'retryable_public_xml',False) and malformed_doc_retries == 0 and attempt < 4:
                    malformed_doc_retries += 1
                    time.sleep(self.interval)
                    continue  # Same report key and page; never mix sessions.
                error.response_bytes = len(exchange.body)
                error.requested_page = page
                error.xml_error_position = getattr(error.__cause__,'position',None)
                error.transport_diagnostic = dict(getattr(self, '_last_response_diagnostic', {}))
                raise
            break
        page_attrs = {p.get("pagenum") for p in root.findall("Page") if p.get("pagenum")}
        local_pdf_page = (document_local_page_numbers
                          and urllib.parse.urlsplit(session._server_url).path == '/NewAcInfo2.do'
                          and root.get('enableNoPage') == 'true'
                          and root.get('pagecount') == '1'
                          and len(root.findall('Page')) == 1 and page_attrs == {'1'})
        if page_attrs and page_attrs != {str(page)} and not local_pdf_page:
            raise SourceError("응답 페이지 번호가 요청과 일치하지 않습니다.")
        return exchange

