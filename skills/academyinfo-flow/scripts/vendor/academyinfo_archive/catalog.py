"""A coverage plan derived from an official item-list response, not filenames."""
from __future__ import annotations
from html.parser import HTMLParser
import re
from .direct import rows_at, SourceError

CATALOG_PAGE_URL = "https://m.academyinfo.go.kr/main/main0780/selectListLink.do"


def published_scope(html: str) -> dict:
    class Selects(HTMLParser):
        def __init__(self):
            super().__init__(); self.current = None; self.values = {}
        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag == 'select':
                self.current = values.get('id')
            elif tag == 'option' and self.current in {'vn_svy_yr', 'vn_schl_div_cd'}:
                self.values.setdefault(self.current, []).append(values.get('value', ''))
        def handle_endtag(self, tag):
            if tag == 'select': self.current = None
    parser = Selects(); parser.feed(html)
    years = parser.values.get('vn_svy_yr', [])
    divisions = parser.values.get('vn_schl_div_cd', [])
    if not years or any(not re.fullmatch(r'\d{4}', y) for y in years) or set(divisions) != {'01','02','03','04'}:
        raise SourceError('공식 공개 연도·학교구분 선택지 형식이 변경되었습니다.')
    return {'years': list(dict.fromkeys(years)), 'school_divisions': list(dict.fromkeys(divisions))}


def collection_plan(payload: dict) -> dict:
    items = rows_at(payload, ["detailItemList"])
    targets = {}
    for item in items:
        required = ("svy_yr", "schl_div_cd", "item_id", "mjr_use_step_cd", "pdf_use_yn")
        if any(key not in item for key in required):
            raise SourceError("공식 공시목록 스키마가 변경되었습니다.")
        year, division, item_id = str(item['svy_yr']), str(item['schl_div_cd']), str(item['item_id'])
        levels = ["school"]
        if str(item['mjr_use_step_cd']) != "0":
            levels.append("department")
        for level in levels:
            key = f"report/{year}/{division}/{item_id}/{level}"
            targets[key] = {"dataset_id": key, "year": year, "school_division": division,
                            "item_id": item_id, "level": level,
                            "title": item.get('pgm_estn_nm', item.get('item_smry_nm', '')),
                            "pdf_only": item['pdf_use_yn'] == 'Y', "status": "pending"}
    return {"schema_version": 1, "scope": "공식 공시목록에 나타난 조회 조건",
            "source_item_rows": len(items), "target_count": len(targets),
            "targets": sorted(targets.values(), key=lambda t: t['dataset_id']),
            "note": "목록 발견은 본문 데이터 수집 완료를 뜻하지 않습니다. PDF 공시는 표 JSON과 별도로 수집해야 합니다."}

