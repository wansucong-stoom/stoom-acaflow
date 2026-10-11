"""Verified public school/department JSON routes, independent of the report viewer.

This adapter covers the department UI's six visible indicators.  It does not
represent all disclosure items, nor silently equate chart years with reference
years.  Response strings (including padding, dashes and zero) stay unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import urlencode

from .direct import DirectClient, Exchange, SourceError, normalized_rows, rows_at

BASE = "https://m.academyinfo.go.kr"
SCHOOLS_URL = BASE + "/intro/intro0350/selectSchlListAll.do"
DEPARTMENT_PAGE_URL = BASE + "/pubinfo/pubinfo0081/doInit.do"
DEPARTMENT_INFO_URL = BASE + "/pubinfo/pubinfo0081/selectList.do"
DEPARTMENT_METRIC_URL = BASE + "/pubinfo/pubinfo0081/selectFreshStudentRate.do"
DEPARTMENTS_URL = BASE + "/pubinfo/pubinfo1600/selectMjrList.do"
SCHOOL_PAGE_URL = BASE + "/pubinfo/pubinfo0020/list.do"


@dataclass(frozen=True)
class Indicator:
    flag: str
    label: str
    unit: str
    basis: str


# v3/v6 remain in legacy JavaScript but are not visible selectable tabs in the
# verified page. Do not advertise them as supported public indicators.
INDICATORS = {
    "v1": Indicator("v1", "신입생 경쟁률", "대 1", "당해연도 3월 신입생"),
    "v2": Indicator("v2", "재학생수", "명", "당해연도 4월 1일"),
    "v4": Indicator("v4", "입학정원", "명", "당해연도 신입생의 입학정원"),
    "v5": Indicator("v5", "학생 1인당 연간 장학금", "천원", "전년도 지급 장학금"),
    "v7": Indicator("v7", "취업률", "%", "전전년도 8월과 전년도 2월 졸업자, 전년도 12월 31일 조사"),
    "v8": Indicator("v8", "평균 등록금", "천원", "등록금 당해연도, 계절학기 수업료 전년도"),
}


def _year(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}", value):
        raise ValueError("조회년도는 네 자리 문자열로 지정합니다.")
    return value


def _code(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{7}", value):
        raise ValueError("학교·학과 코드는 앞자리 0을 보존한 일곱 자리 문자열이어야 합니다.")
    return value


@dataclass(frozen=True)
class DepartmentSelection:
    school_code: str
    department_code: str
    major_code: str
    year: str

    def __post_init__(self):
        _code(self.school_code)
        _code(self.department_code)
        _code(self.major_code)
        _year(self.year)

    def parameters(self, flag: str) -> dict[str, str]:
        if flag not in INDICATORS:
            raise ValueError("공개 학과 주요지표에서 검증된 flag를 지정합니다: " + ",".join(INDICATORS))
        return {"svyYr": self.year, "schlMjrId": self.department_code,
                "schlId": self.school_code, "mjrId": self.major_code, "flag": flag}

    def source_page(self) -> str:
        return DEPARTMENT_PAGE_URL + "?" + urlencode({"schlMjrId": self.department_code,
            "mjrId": self.major_code, "schlId": self.school_code})


def schools(client: DirectClient, year: str, *, school_name: str = "",
            area_code: str = "", page: int = 1) -> Exchange:
    """Public school registry page; this is not an indicator dataset."""
    _year(year)
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ValueError("page는 1 이상의 정수여야 합니다.")
    if not isinstance(school_name, str) or not isinstance(area_code, str):
        raise ValueError("학교명과 지역 코드는 문자열이어야 합니다.")
    return client.request(SCHOOLS_URL, {"svy_yr": year, "pbnf_area_cd": area_code,
        "searchVal": school_name, "pageindex": str(page)})


def school_rows(exchange: Exchange) -> list[dict[str, Any]]:
    payload = exchange.json()
    result = rows_at(payload, ["resultList"])
    for row in result:
        if not isinstance(row.get("schl_id"), str) or not isinstance(row.get("schl_nm"), str):
            raise SourceError("학교 목록에 학교 코드·한국어 학교명이 없습니다.")
    pagination = payload.get("paginationInfo")
    if not isinstance(pagination, dict) or not isinstance(pagination.get("totalPageCount"), int):
        raise SourceError("학교 목록의 페이지 수를 확인할 수 없습니다.")
    return result


def iter_schools(client: DirectClient, year: str, *, school_name: str = "",
                 area_code: str = "", max_pages: int = 1000):
    """Yield each original exchange, respecting the server's pagination metadata."""
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
        raise ValueError("max_pages는 1 이상의 정수여야 합니다.")
    for page in range(1, max_pages + 1):
        exchange = schools(client, year, school_name=school_name, area_code=area_code, page=page)
        school_rows(exchange)
        payload = exchange.json()
        pagination = payload["paginationInfo"]
        if pagination.get("currentPageNo") != page:
            raise SourceError("학교 목록 서버가 요청한 페이지와 다른 페이지를 반환했습니다.")
        yield exchange
        if page >= pagination["totalPageCount"]:
            return
    raise SourceError("학교 목록 페이지 제한에 도달했습니다. 전체 수집으로 표시하지 않습니다.")


def department_info(client: DirectClient, selection: DepartmentSelection) -> Exchange:
    # The detail form uses separate *Se selectors for its information query.
    # The indicator chart's five-parameter request is not sufficient here.
    parameters = selection.parameters("v1") | {"tabSelect": "d1",
        "schlMjrIdSe": selection.department_code, "schlIdSe": selection.school_code,
        "mjrIdSe": selection.major_code, "mjrIdDt": ""}
    return client.request(DEPARTMENT_INFO_URL, parameters)


def school_page(client: DirectClient, school_code: str, *, year: str) -> Exchange:
    """Public school form POST with an explicit year, never the Ubi viewer.

    Anonymous GET requests without svyYr can stall on this route; the public
    form's schlId/svyYr/pageIdx POST was verified for the same school codes.
    """
    _code(school_code)
    _year(year)
    return client.request(SCHOOL_PAGE_URL, {"schlId": school_code, "svyYr": year,
                                         "pageIdx": "01"}, method="POST")


class _AffiliationParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_selector = False
        self.found_selector = False
        self.value: str | None = None
        self.label: list[str] = []
        self.rows: list[dict[str, str]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "select":
            self.in_selector = attributes.get("id") == "collegeList" or attributes.get("name") == "collegeList"
            self.found_selector |= self.in_selector
        elif tag == "option" and self.in_selector:
            self.value = attributes.get("value", "")
            self.label = []

    def handle_data(self, data):
        if self.in_selector and self.value is not None:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag == "option" and self.in_selector and self.value is not None:
            value = self.value
            self.value = None
            if not value:
                return
            match = re.fullmatch(r"(\d{7}),(0[1-4])", value)
            if match is None:
                raise SourceError("대학 소속기관 선택 목록의 코드 형식이 바뀌었습니다.")
            self.rows.append({"schoolCode": match[1], "schoolDivision": match[2],
                              "sourceLabel": "".join(self.label).strip()})
        elif tag == "select":
            self.in_selector = False


def affiliated_schools(exchange: Exchange) -> list[dict[str, str]]:
    """Discover affiliated graduate schools using the public school's selector.

    These entries extend the registry; do not mistake the base school registry
    for a complete roster of graduate schools. Historical closed entries remain
    explicit in sourceLabel and are not discarded.
    """
    if not 200 <= exchange.status < 300:
        raise SourceError("학교 소속기관 조회 HTTP 오류입니다.")
    try:
        html = exchange.body.decode("utf-8-sig")
    except UnicodeError as error:
        raise SourceError("학교 소속기관 페이지가 UTF-8이 아닙니다.") from error
    parser = _AffiliationParser()
    parser.feed(html)
    parser.close()
    if not parser.found_selector or not parser.rows:
        raise SourceError("공개 학교 페이지에서 소속기관 목록을 확인할 수 없습니다.")
    if len({r["schoolCode"] for r in parser.rows}) != len(parser.rows):
        raise SourceError("소속기관 선택 목록에 중복 학교 코드가 있습니다.")
    selected_school = exchange.parameters.get("schlId")
    if selected_school and selected_school not in {r["schoolCode"] for r in parser.rows}:
        raise SourceError("공개 소속기관 목록에 요청한 학교 코드가 없습니다.")
    return parser.rows


def departments(client: DirectClient, school_code: str, year: str, *,
                include_closed: bool = True, page: int = 1) -> Exchange:
    """Public school-specific department registry, including historic units by default."""
    _code(school_code)
    _year(year)
    if not isinstance(include_closed, bool):
        raise ValueError("include_closed는 boolean이어야 합니다.")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ValueError("page는 1 이상의 정수여야 합니다.")
    return client.request(DEPARTMENTS_URL, {"svyYr": year, "schlId": school_code,
        "pulYn": "false" if include_closed else "true", "pageindex": str(page)})


def department_rows(exchange: Exchange) -> list[dict[str, Any]]:
    payload = exchange.json()
    result = rows_at(payload, ["resultList"])
    for row in result:
        try:
            _code(row.get("schl_mjr_id"))
            _code(row.get("mjr_id"))
        except ValueError as error:
            raise SourceError("학과 목록의 학교학과 코드·표준학과 코드를 확인할 수 없습니다.") from error
        if not isinstance(row.get("mjr_nm"), str):
            raise SourceError("학과 목록에 학과명이 없습니다.")
    pagination = payload.get("paginationInfo")
    if not isinstance(pagination, dict) or not isinstance(pagination.get("totalRecordCount"), int):
        raise SourceError("학과 목록의 전체 행 수를 확인할 수 없습니다.")
    return result


def selection_from_row(row: dict[str, Any], school_code: str, year: str) -> DepartmentSelection:
    return DepartmentSelection(school_code, row.get("schl_mjr_id"), row.get("mjr_id"), year)


def iter_departments(client: DirectClient, school_code: str, year: str, *,
                     include_closed: bool = True, max_pages: int = 1000):
    """Validate completeness using actual unique rows, not inconsistent page counts.

    The verified server returns all 213 HNU records on page 1, while its
    paginationInfo says 10 rows/page and 22 pages. Such a complete response is
    archived once. Duplicated incomplete pages raise rather than claim success.
    """
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
        raise ValueError("max_pages는 1 이상의 정수여야 합니다.")
    seen: set[tuple[str, str]] = set()
    expected = None
    for page in range(1, max_pages + 1):
        exchange = departments(client, school_code, year, include_closed=include_closed, page=page)
        result = department_rows(exchange)
        pagination = exchange.json()["paginationInfo"]
        total = pagination["totalRecordCount"]
        if total < 0 or (expected is not None and total != expected):
            raise SourceError("학과 목록 수집 도중 전체 행 수가 바뀌었습니다.")
        expected = total
        keys = {(r["schl_mjr_id"], r["mjr_id"]) for r in result}
        if len(keys) != len(result) or keys & seen:
            raise SourceError("학과 목록에 중복 행 또는 중복 페이지가 있습니다.")
        seen.update(keys)
        if len(seen) > total:
            raise SourceError("학과 목록의 실제 행 수가 원천 전체 행 수를 초과했습니다.")
        yield exchange
        if len(seen) == total:
            return
        if not result:
            raise SourceError("전체 행 수에 못 미친 학과 목록이 빈 페이지를 반환했습니다.")
    raise SourceError("학과 목록 페이지 제한에 도달했습니다. 전체 수집으로 표시하지 않습니다.")


def department_metric(client: DirectClient, selection: DepartmentSelection, flag: str) -> Exchange:
    return client.request(DEPARTMENT_METRIC_URL, selection.parameters(flag))


def metric_records(exchange: Exchange, selection: DepartmentSelection, flag: str):
    """Rows for archive import, with exact values and separately identified years."""
    indicator = INDICATORS[flag]
    payload = exchange.json()
    result = rows_at(payload, ["resultList"])
    for row in result:
        if not isinstance(row.get("year"), str) or not re.fullmatch(r"\d{4}", row["year"]):
            raise SourceError("학과 지표 행의 원천 연도 형식이 바뀌었습니다.")
        if "val" not in row:
            raise SourceError("학과 지표 행에 val 값이 없습니다.")
    selectors = {"schoolCode": selection.school_code, "deptCode": selection.department_code,
        "majorCode": selection.major_code, "requestYear": selection.year,
        "indicator": flag, "indicatorName": indicator.label, "unit": indicator.unit}
    # year is the chart's year. Keep it distinct from requestYear and do not
    # manufacture reference years, especially for lagging employment releases.
    yield from normalized_rows(result, dimensions={"sourceYear": "year"}, selectors=selectors)


def metric_metadata(exchange: Exchange, selection: DepartmentSelection, flag: str) -> dict[str, Any]:
    indicator = INDICATORS[flag]
    payload = exchange.json()
    rows_at(payload, ["resultList"])
    pram_map = payload.get("pramMap", {})
    return exchange.metadata() | {"dataset_kind": "department_indicator",
        "source_page": selection.source_page(), "row_path": ["resultList"],
        "coverage": "대학 학과 주요지표 공개 탭 6종(학교종류·학과상태에 따라 노출 차이 있음); 전체 공시항목 수집을 뜻하지 않음",
        "indicator": {"flag": flag, "label": indicator.label, "unit": indicator.unit,
                      "reference_basis_text": indicator.basis,
                      "source_chart_unit_text": "명" if flag in {"v1", "v2", "v4"} else indicator.unit,
                      "unit_note": ("원천 차트 JS는 명으로 표기하나 지표명은 신입생 경쟁률이며 정규화 단위는 대 1로 해석"
                                    if flag == "v1" else "원천 차트 단위를 보존")},
        "year_semantics": {"request_year": selection.year,
            "effective_source_year": pram_map.get("pbnf_bse_yr"),
            "row_year": "원천 학과 주요지표 그래프의 연도(year); 공시·기준연도 역할은 일률적으로 추정하지 않음",
            "reference_year": "지표마다 기준이 다르므로 숫자로 자동 추정하지 않음"},
        "selectors": {"schoolCode": selection.school_code,
                      "deptCode": selection.department_code, "majorCode": selection.major_code}}

