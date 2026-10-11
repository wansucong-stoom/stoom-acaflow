"""Direct public HTTP requests; no browser, viewer, or LLM is needed."""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

OFFICIAL_HOSTS = frozenset({"academyinfo.go.kr", "www.academyinfo.go.kr", "m.academyinfo.go.kr"})
CATALOG_URL = "https://m.academyinfo.go.kr/main/main0780/selectItemList.do"
SECRET_NAME = re.compile(r"token|password|passwd|authorization|cookie|session|secret|pkey|parg|ubikey|ubiargs", re.I)


class SourceError(RuntimeError):
    """A response could not be validated as a successful public dataset."""


def validate_public_url(url: str) -> None:
    p = urllib.parse.urlsplit(url)
    if p.scheme != "https" or p.hostname not in OFFICIAL_HOSTS or p.port not in (None, 443):
        raise ValueError("공식 대학알리미 HTTPS 주소만 사용할 수 있습니다.")
    if p.username or p.password or p.fragment:
        raise ValueError("인증정보와 fragment가 포함된 주소는 사용할 수 없습니다.")
    for name, _ in urllib.parse.parse_qsl(p.query, keep_blank_values=True):
        if SECRET_NAME.search(name):
            raise ValueError("인증·세션 매개변수는 아카이브할 수 없습니다.")


class OfficialRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True)
class Exchange:
    url: str
    method: str
    parameters: dict[str, str]
    body: bytes
    status: int
    content_type: str
    fetched_at: str
    final_url: str

    def metadata(self) -> dict[str, Any]:
        return {"source": "대학알리미", "source_url": self.url,
                "source_language": "ko", "language": "ko", "fetched_at": self.fetched_at,
                "retrieved_utc": self.fetched_at,
                "request": {"method": self.method, "url": self.url, "parameters": self.parameters},
                "response": {"status": self.status, "content_type": self.content_type,
                             "final_url": self.final_url, "sha256": hashlib.sha256(self.body).hexdigest()}}

    def json(self) -> Any:
        if not 200 <= self.status < 300:
            raise SourceError(f"HTTP {self.status}: 정상 자료로 등록하지 않습니다.")
        try:
            value = json.loads(self.body.decode("utf-8-sig"),
                               parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
        except (UnicodeError, ValueError) as e:
            raise SourceError("응답이 UTF-8 JSON이 아닙니다. 원문만 보존해야 합니다.") from e
        if isinstance(value, dict) and "M_CODE" in value:
            try:
                if float(value["M_CODE"]) < 0:
                    raise SourceError("원천 서버가 조회 오류를 반환했습니다.")
            except (ValueError, TypeError) as e:
                raise SourceError("원천 오류 코드 형식을 확인할 수 없습니다.") from e
        return value


class DirectClient:
    """Single request at a time with bounded response sizes and rate limiting."""
    def __init__(self, *, interval: float = 1.0, timeout: float = 30.0,
                 max_bytes: int = 64 * 1024 * 1024, retries: int = 2, opener=None,
                 request_budget=None):
        if interval < 0 or timeout <= 0 or max_bytes <= 0 or not 0 <= retries <= 5:
            raise ValueError("잘못된 요청 제한입니다.")
        self.interval, self.timeout, self.max_bytes, self.retries = interval, timeout, max_bytes, retries
        self.opener = opener or urllib.request.build_opener(OfficialRedirectHandler())
        self.request_budget = request_budget
        self._last = 0.0

    def request(self, url: str, parameters: dict[str, str] | None = None, *, method="POST") -> Exchange:
        validate_public_url(url)
        parameters = dict(parameters or {})
        if any(SECRET_NAME.search(k) for k in parameters):
            raise ValueError("인증·세션 값은 조회 프로필에 넣지 않습니다.")
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in parameters.items()):
            raise ValueError("공개 조회 조건은 문자열 key/value로 지정합니다.")
        method = method.upper()
        if method not in {"POST", "GET"}:
            raise ValueError("GET/POST만 지원합니다.")
        target = url
        payload = urllib.parse.urlencode(parameters).encode("utf-8")
        if method == "GET":
            target += ("&" if "?" in target else "?") + payload.decode() if payload else ""
            payload = None
        headers = {"User-Agent": "stoom-academyinfo/0.1 (public disclosure archive)",
                   "Accept": "application/json", "Accept-Language": "ko-KR,ko;q=0.9",
                   "X-Requested-With": "XMLHttpRequest",
                   "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        for attempt in range(self.retries + 1):
            time.sleep(max(0.0, self.interval - (time.monotonic() - self._last)))
            self._last = time.monotonic()
            if self.request_budget is not None:
                self.request_budget.consume()
            try:
                response = self.opener.open(urllib.request.Request(target, payload, headers, method=method), timeout=self.timeout)
            except urllib.error.HTTPError as e:
                response = e
            with response:
                body = response.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise SourceError("응답 크기 제한을 초과했습니다.")
                status = response.code
                final_url = response.geturl()
                validate_public_url(final_url)
                exchange = Exchange(url, method, parameters, body, status,
                                    response.headers.get("Content-Type", ""),
                                    datetime.now(timezone.utc).isoformat(), final_url)
                retry_after = response.headers.get("Retry-After", "")
            if status not in {429, 502, 503, 504} or attempt == self.retries:
                return exchange
            try:
                delay = float(retry_after)
            except ValueError:
                delay = 2 ** attempt
            time.sleep(min(60.0, max(self.interval, delay)))
        raise AssertionError("unreachable")

    def catalog(self, year: str, school_division: str) -> Exchange:
        if not re.fullmatch(r"\d{4}", year) or school_division not in {"01", "02", "03", "04"}:
            raise ValueError("공시연도와 학교 구분(01~04)을 확인해주세요.")
        return self.request(CATALOG_URL, {"svyYr": year, "schlDivCd": school_division,
                            "searchGbn": "0", "category_cd": "", "category_gubun": "category", "searchVal": ""})


def rows_at(payload: Any, path: list[str]) -> list[dict]:
    current = payload
    for part in path:
        if not isinstance(current, dict) or part not in current:
            raise SourceError(f"검증된 행 경로가 없습니다: {'.'.join(path)}")
        current = current[part]
    if not isinstance(current, list) or any(not isinstance(r, dict) for r in current):
        raise SourceError("응답 행은 object 배열이어야 합니다.")
    return current


def normalized_rows(rows: list[dict], *, dimensions: dict[str, str] | None = None,
                    selectors: dict[str, str] | None = None):
    for number, row in enumerate(rows, 1):
        dims = dict(selectors or {})
        for canonical, original in (dimensions or {}).items():
            if original in row:
                dims[canonical] = row[original]
        yield {"sheet": "response", "row_number": number, "keys": list(row),
               "cells": list(row.values()), "values": row, "dimensions": dims}

