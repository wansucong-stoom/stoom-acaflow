"""Convert public UbiReport XML to Korean JSON without OCR or an LLM.

The original XML remains the authority.  By default, ``xml_tree`` preserves every
element, attribute, text and tail; its SHA-256 identifies the source bytes.
Live callers may omit duplicate raw trees without skipping table validation.
Table rows are emitted only when explicit report metadata and rectangular cells
agree.  Printed display values remain strings, including empty strings and 0.
The parser never invents identifiers absent from the report.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any


class ReportParseError(ValueError):
    """The public response is not a supported, valid report representation."""


_FIELD = re.compile(r"(?:^|, )([A-Za-z_][A-Za-z0-9_]*)=")
_RECORD = re.compile(r"\}, \{(?=item_mstr_id=)")


def parse_java_map_list(text: str) -> list[dict[str, str]]:
    """Parse the observed Java List<Map>.toString metadata, never eval it.

    This representation has no string escaping.  Consequently nested objects,
    duplicate keys, nonstandard separators or a value resembling a map key are
    unsupported; callers must retain the source response instead of guessing.
    Commas, Korean text, line breaks and formula braces in values are preserved.
    """
    if not isinstance(text, str) or len(text) > 8 * 1024 * 1024:
        raise ReportParseError("메타데이터 문자열 크기 또는 형식이 잘못되었습니다.")
    if text == "[]":
        return []
    if not text.startswith("[{") or not text.endswith("}]"):
        raise ReportParseError("확인된 Java List<Map> 메타데이터 형식이 아닙니다.")
    records = _RECORD.split(text[2:-2])
    result = []
    for record in records:
        matches = list(_FIELD.finditer(record))
        if not matches or matches[0].start() != 0:
            raise ReportParseError("메타데이터 key/value 경계를 확인할 수 없습니다.")
        keys = [m.group(1) for m in matches]
        if any(k not in {"item_mstr_id", "form_clft_cd", "row_num", "col_num", "form_ty_cd", "col_no"} and not k.startswith(("h_", "b_", "s_")) for k in keys):
            raise ReportParseError("확인되지 않은 메타데이터 key입니다. 원문을 보존해야 합니다.")
        if len(set(keys)) != len(keys):
            raise ReportParseError("중복 메타데이터 key로 원문 해석이 모호합니다.")
        if keys[0] != "item_mstr_id":
            raise ReportParseError("확인된 보고서 메타데이터 레코드가 아닙니다.")
        values = {}
        for pos, match in enumerate(matches):
            end = matches[pos + 1].start() if pos + 1 < len(matches) else len(record)
            values[match.group(1)] = record[match.end():end]
        result.append(values)
    return result


def _tree(element: ET.Element) -> dict[str, Any]:
    tag = element.tag
    name = tag if isinstance(tag, str) else ("#comment" if tag is ET.Comment else "#processing-instruction")
    return {"tag": name, "attributes": dict(element.attrib), "text": element.text,
            "tail": element.tail, "children": [_tree(child) for child in element]}


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise ReportParseError(f"{name}: 정수 값이 필요합니다.")
    try:
        number = int(value)
    except (TypeError, ValueError) as e:
        raise ReportParseError(f"{name}: 정수 값이 필요합니다.") from e
    if str(number) != str(value) or number < minimum:
        raise ReportParseError(f"{name}: 허용 범위의 정수 값이 필요합니다.")
    return number


def _number(value: str, name: str) -> Decimal:
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError) as e:
        raise ReportParseError(f"{name}: 좌표가 숫자가 아닙니다.") from e
    if not number.is_finite():
        raise ReportParseError(f"{name}: 유한한 좌표가 필요합니다.")
    return number


def _cell(element: ET.Element, item_index: int, *, include_raw_tree: bool = True) -> dict[str, Any]:
    text = element.find("Text")
    result = {"item_index": item_index, "attributes": dict(element.attrib),
              "text_attributes": dict(text.attrib) if text is not None else None,
              "text": "".join(text.itertext()) if text is not None else None,
              "source_text": text.text if text is not None else None}
    if include_raw_tree:
        result["children"] = [_tree(child) for child in element]
    if all(k in element.attrib for k in ("x", "y", "width", "height")):
        geometry = {k: element.attrib[k] for k in ("x", "y", "width", "height")}
        numbers = {k: _number(v, k) for k, v in geometry.items()}
        line = (text is None and element.get('classname') == 'UbiLineItem'
                and [child.tag for child in element] == ['Shape'])
        valid_line = (line and numbers['width'] >= 0 and numbers['height'] >= 0
                      and (numbers['width'] > 0 or numbers['height'] > 0))
        if (numbers["width"] <= 0 or numbers["height"] <= 0) and not valid_line:
            raise ReportParseError("텍스트 셀의 폭과 높이는 양수여야 합니다.")
        result["geometry"] = geometry
    return result


def _rect(cell: dict) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    g = cell["geometry"]
    return tuple(Decimal(g[k]) for k in ("x", "y", "width", "height"))


def _is_border(cell: dict) -> bool:
    return (cell.get("text_attributes") or {}).get("border") not in {None, "", "0"}


def _metadata_columns(metadata: dict) -> tuple[list[dict], dict[int, dict]]:
    masters, bodies, headers = (metadata.get(k) for k in ("master", "body", "header"))
    if not isinstance(masters, list) or len(masters) != 1 or not isinstance(bodies, list) or not isinstance(headers, list):
        raise ReportParseError("master/header/body 표 메타데이터가 필요합니다.")
    declared_count = _integer(masters[0].get("col_num"), "col_num", minimum=1)
    # Some official templates retain an obsolete master column count (observed
    # 2026 graduate-school graduation grades: master30, body28, header3x28).
    # Body's explicit consecutive col_no and the entire header grid are the
    # authoritative layout.  All physical header rectangles are validated below.
    count = len(bodies)
    header_row_count = _integer(masters[0].get("row_num"), "row_num") + 1
    if not count or count > 1000 or declared_count > 1000:
        raise ReportParseError("본문 메타데이터 컬럼 수가 허용 범위를 벗어났습니다.")
    indexed_body = {_integer(b.get("col_no"), "body.col_no"): b for b in bodies}
    indexed_header = {_integer(h.get("col_no"), "header.col_no"): h for h in headers}
    if len(indexed_body) != count or set(indexed_body) != set(range(count)):
        raise ReportParseError("본문 컬럼 번호에 누락 또는 중복이 있습니다.")
    if len(indexed_header) != len(headers) or set(indexed_header) != set(range(count * header_row_count)):
        raise ReportParseError("헤더 컬럼 번호에 누락 또는 중복이 있습니다.")
    columns, keys = [], set()
    for no in range(count):
        body = indexed_body[no]
        hidden = body.get("b_col_hid_yn")
        if hidden not in {"Y", "N"}:
            raise ReportParseError("본문 컬럼 공개 여부를 확인할 수 없습니다.")
        if hidden == "Y":
            continue
        key = body.get("b_col_id") or body.get("b_col_cd") or f"column_{no:04d}"
        if key in keys:
            raise ReportParseError("source field ID가 중복되어 컬럼 대응이 모호합니다.")
        keys.add(key)
        columns.append({"key": key, "source_col_no": no,
                        "source_body_column_count": count,
                        "source_master_column_count": declared_count,
                        "source_field_id": body.get("b_col_id", ""),
                        "source_semantic_code": body.get("b_col_cd", ""),
                        "source_body_metadata": dict(body),
                        "source_header_metadata": [dict(indexed_header[i]) for i in sorted(indexed_header) if i % count == no]})
    if not columns:
        raise ReportParseError("표에 공개 본문 컬럼이 없습니다.")
    return columns, indexed_header


def _header_label(value: str) -> str:
    # Published resultHeader metadata uses literal Java/JavaScript newline escapes.
    return value.replace("\\\\n", "\n").replace("\\n", "\n").strip()


def _header_label_matches(head, rendered, selectors=None):
    label = _header_label(head.get('h_col_hdr_krn_nm', ''))
    actual = (rendered or '').strip()
    if label == actual:
        return True
    # Source-observed 2026/02/199 school template differences. Preserve both
    # labels and keep the exact year, template, form, and column scope.
    return (selectors is not None and str(selectors.get('pubYear')) == '2026'
            and head.get('item_mstr_id') == '7656' and head.get('form_clft_cd') == '30'
            and (head.get('col_no'), label, actual) in {
                ('107', '센터장 자격\n(➀∼➃ 중 선택)', '센터장 자격\n(1∼4 중 선택)'),
                ('33', '장애학생 교육지원인력 수', '장애학생 교육지원 인력 수'),
                ('35', '수혜 장애\n학생수', '수혜장애\n학생수'),
                ('36', '개인별\n교육지원\n수립여부(O/X)', '개인별 \n교육지원계획\n수립여부(O/X)')})


def _expand_bottom_headers(leaves, columns, headers, metadata, bordered, header_end, selectors=None,
                           *, rect=_rect):
    """Split a colspan header only at a unique partition of actual body cells."""
    count = len(metadata['body'])
    rows = int(metadata['master'][0]['row_num']) + 1
    groups = []
    for no, head in headers.items():
        if head.get('h_celmrg_yn') != 'Y':
            continue
        row, col = divmod(no, count)
        span = _integer(head.get('h_row_mrg_cnt'), 'h_row_mrg_cnt', minimum=1)
        width = _integer(head.get('h_col_mrg_cnt'), 'h_col_mrg_cnt', minimum=1)
        if row + span != rows:
            continue
        covered = [c for c in columns if col <= c['source_col_no'] < col + width]
        if covered:
            groups.append((col, head, covered))
    groups.sort(key=lambda g: g[0])
    if (len(groups) != len(leaves) or
            [c['source_col_no'] for _, _, group in groups for c in group] != [c['source_col_no'] for c in columns]):
        raise ReportParseError('병합된 마지막 헤더와 본문 열을 일대일 대응할 수 없습니다.')
    expanded = []
    for leaf, (_, head, group) in zip(leaves, groups):
        if not head.get('h_col_hdr_ofcfmla') and not _header_label_matches(head, leaf['text'], selectors):
            raise ReportParseError('병합 헤더의 실제 명칭과 열 메타데이터가 다릅니다.')
        if len(group) == 1:
            expanded.append(leaf)
            continue
        if len(group) > 64:
            raise ReportParseError('병합 헤더의 본문 분할 수가 검증 한도를 초과했습니다.')
        x, _, width, _ = rect(leaf)
        end = x + width
        rectangles = {}
        for cell in bordered:
            xx, yy, ww, hh = rect(cell)
            if yy >= header_end and x <= xx and xx + ww <= end:
                rectangles.setdefault((xx, ww), cell)
        starts = {}
        for xx, ww in rectangles:
            starts.setdefault(xx, []).append(ww)
        memo = {}
        def partitions(position, remaining):
            key = (position, remaining)
            if key in memo:
                return memo[key]
            if remaining == 0:
                return [()] if position == end else []
            result = []
            for ww in starts.get(position, []):
                for tail in partitions(position + ww, remaining - 1):
                    result.append(((position, ww),) + tail)
                    if len(result) >= 2:
                        memo[key] = result
                        return result
            memo[key] = result
            return result
        choices = partitions(x, len(group))
        if len(choices) != 1:
            raise ReportParseError('병합 헤더 아래 본문 셀 경계를 유일하게 검증할 수 없습니다.')
        for pair in choices[0]:
            cell = rectangles[pair]
            expanded.append({**leaf, 'geometry': {**leaf['geometry'],
                'x': cell['geometry']['x'], 'width': cell['geometry']['width']}})
    return expanded


def _parse_table(cells: list[dict], metadata: dict, page_index: int,
                 selectors: dict[str, str] | None) -> tuple[list[dict], list[dict], list[str]]:
    # All cells (including expanded header leaves) remain alive during this
    # parse. Cache exact Decimal rectangles locally, never in emitted values or
    # across requests. Laziness preserves the existing validation order.
    rectangles = {}

    def rect(cell):
        key = id(cell)
        if key not in rectangles:
            rectangles[key] = _rect(cell)
        return rectangles[key]

    columns, header_by_no = _metadata_columns(metadata)
    # This template prints one attachment display cell for three metadata
    # variables. Preserve it as a rendered composite, without assigning the
    # filename to an unknown underlying name/path/detail field.
    attachment = [c for c in columns if c['source_col_no'] in {37, 38, 39}]
    attachment_head = header_by_no.get(37, {})
    if (str((selectors or {}).get('pubYear')) == '2026'
            and len(attachment) == 3
            and [c['source_field_id'] for c in attachment] == ['COL_36_VAL', 'COL_38_VAL', 'COL_37_VAL']
            and [c['source_semantic_code'] for c in attachment] == ['ATTCH_FILE_NM', 'ATTCH_FILE_PATH', 'ATTCH_FILE_DETAIL']
            and all(c['source_body_metadata'].get('item_mstr_id') == '7656'
                    and c['source_body_metadata'].get('form_clft_cd') == '30' for c in attachment)
            and attachment_head.get('h_celmrg_yn') == 'Y'
            and attachment_head.get('h_col_mrg_cnt') == '3'
            and _header_label(attachment_head.get('h_col_hdr_krn_nm', '')) == '장애 학생 지원 계획\n[한글/워드]'):
        composite = {**attachment[0], 'key': 'attachment_display_37_39',
                     'source_field_id': '', 'source_semantic_code': '',
                     'source_field_ids': [c['source_field_id'] for c in attachment],
                     'source_semantic_codes': [c['source_semantic_code'] for c in attachment],
                     'source_col_nos': [c['source_col_no'] for c in attachment],
                     'source_body_metadata': {'merged_group': [c['source_body_metadata'] for c in attachment]},
                     'source_header_metadata': [h for c in attachment for h in c['source_header_metadata']],
                     'value_scope': 'rendered attachment display only; underlying metadata variables not reconstructed'}
        columns = [composite if c['source_col_no'] == 37 else c for c in columns if c['source_col_no'] not in {38, 39}]
    # A visible, unmerged first metadata column anchors the repeated table header.
    first_label = _header_label(header_by_no[columns[0]["source_col_no"]].get("h_col_hdr_krn_nm", ""))
    bordered = [c for c in cells if "geometry" in c and _is_border(c)]
    anchors = [c for c in bordered if (c["text"] or '').strip() == first_label]
    if len(anchors) != 1:
        raise ReportParseError("첫 공개 컬럼 헤더를 유일하게 대응할 수 없습니다.")
    ax, ay, aw, ah = rect(anchors[0])
    header_end = ay + ah
    header_cells = [c for c in bordered if ay <= rect(c)[1] < header_end and rect(c)[1] + rect(c)[3] <= header_end]
    leaves = sorted([c for c in header_cells if rect(c)[1] + rect(c)[3] == header_end], key=lambda c: rect(c)[0])
    if len(leaves) < len(columns):
        leaves = _expand_bottom_headers(leaves, columns, header_by_no, metadata, bordered, header_end, selectors,
                                        rect=rect)
    if len(leaves) != len(columns) or rect(leaves[0])[0] != ax:
        raise ReportParseError("표 헤더 셀 수와 공개 컬럼 수가 일치하지 않습니다.")
    for left, right in zip(leaves, leaves[1:]):
        if rect(left)[0] + rect(left)[2] != rect(right)[0]:
            raise ReportParseError("표 헤더 셀 경계에 중복 또는 공백이 있습니다.")
    for col, leaf in zip(columns, leaves):
        x, y, width, height = rect(leaf)
        parents = [c for c in header_cells if rect(c)[0] <= x and rect(c)[0] + rect(c)[2] >= x + width]
        parents.sort(key=lambda c: (rect(c)[1], -rect(c)[3]))
        col.update({"x": leaf["geometry"]["x"], "width": leaf["geometry"]["width"],
                    "header_path": [c["text"] for c in parents],
                    "header_item_indices": [c["item_index"] for c in parents]})
    # Confirm every header merge against the report's explicit row/column spans.
    # Formula headers may render differently, but their exact rectangles still
    # establish column identity; original formula and rendered text are retained.
    count = len(metadata["body"])
    header_rows = int(metadata["master"][0]["row_num"]) + 1
    by_no = {no: c for c in columns for no in c.get('source_col_nos', [c['source_col_no']])}
    pending = []
    for no, head in header_by_no.items():
        if head.get("h_celmrg_yn") not in {"Y", "N"}:
            raise ReportParseError("헤더 병합 메타데이터를 확인할 수 없습니다.")
        if head["h_celmrg_yn"] == "N":
            continue
        row_no, col_no = divmod(no, count)
        row_span = _integer(head.get("h_row_mrg_cnt"), "h_row_mrg_cnt", minimum=1)
        col_span = _integer(head.get("h_col_mrg_cnt"), "h_col_mrg_cnt", minimum=1)
        if row_no + row_span > header_rows or col_no + col_span > count:
            raise ReportParseError("헤더 병합 범위가 표 크기를 벗어났습니다.")
        covered = list({by_no[i]['key']: by_no[i] for i in range(col_no, col_no + col_span) if i in by_no}.values())
        if not covered:
            continue
        pending.append((head, row_no, row_no + row_span, Decimal(covered[0]["x"]),
                        sum((Decimal(c["width"]) for c in covered), Decimal(0))))
    # Actual report headers can use unequal band heights (e.g. 22+22+24).
    # Solve logical row edges from uniquely matching source rectangles rather
    # than assuming equal heights or selecting a nearest coordinate.
    def covered_keys(head):
        start = int(head['col_no']) % count
        span = int(head['h_col_mrg_cnt'])
        return {by_no[i]['key'] for i in range(start, start + span) if i in by_no}
    row_edges = {c['key']: {0: ay, header_rows: header_end} for c in columns}
    # A logical band boundary may lie wholly inside row-spanning headers.
    # Require each actual source merge endpoint, without inventing coordinates
    # for an invisible boundary (observed university admission-result headers).
    # Different column branches may render the same logical bands at different
    # heights. Validate each visible column's source endpoints independently.
    required_edges = {c['key']: {0, header_rows} for c in columns}
    for head, start, end, _, _ in pending:
        for key in covered_keys(head):
            required_edges[key].update((start, end))
    assigned = set()
    while pending:
        progressed, remaining = False, []
        for head, row_start, row_end, x, width in pending:
            label = _header_label(head.get("h_col_hdr_krn_nm", ""))
            keys = covered_keys(head)
            candidates = []
            for actual in header_cells:
                xx, yy, ww, hh = rect(actual)
                if actual["item_index"] in assigned or (xx, ww) != (x, width):
                    continue
                if any(row_start in row_edges[key] and yy != row_edges[key][row_start] for key in keys):
                    continue
                if any(row_end in row_edges[key] and yy + hh != row_edges[key][row_end] for key in keys):
                    continue
                if not head.get("h_col_hdr_ofcfmla") and not _header_label_matches(head, actual['text'], selectors):
                    continue
                candidates.append(actual)
            if not candidates:
                raise ReportParseError("헤더 병합 좌표·명칭과 서버 컬럼 메타데이터가 일치하지 않습니다.")
            if len(candidates) != 1:
                remaining.append((head, row_start, row_end, x, width))
                continue
            actual = candidates[0]
            xx, yy, ww, hh = rect(actual)
            if not head.get('h_col_hdr_ofcfmla') and (actual['text'] or '').strip() != label:
                for col in columns:
                    if Decimal(col['x']) >= xx and Decimal(col['x']) + Decimal(col['width']) <= xx + ww:
                        col.setdefault('source_header_label_variants', []).append({
                            'metadata': head['h_col_hdr_krn_nm'], 'rendered': actual['text'],
                            'item_mstr_id': head['item_mstr_id'], 'col_no': head['col_no'],
                            'validation': 'source-observed template label difference; geometry and column identity validated'})
            for key in keys:
                row_edges[key][row_start], row_edges[key][row_end] = yy, yy + hh
            assigned.add(actual["item_index"])
            progressed = True
        if not progressed:
            raise ReportParseError("헤더 행 경계를 유일하게 대응할 수 없습니다.")
        pending = remaining
    for key, edges in row_edges.items():
        observed_edges = sorted(edges)
        if set(edges) != required_edges[key] or any(edges[a] >= edges[b] for a, b in zip(observed_edges, observed_edges[1:])):
            raise ReportParseError("헤더 행 경계에 누락 또는 역전이 있습니다.")
    if assigned != {c["item_index"] for c in header_cells}:
        raise ReportParseError("메타데이터에서 대응하지 못한 헤더 셀이 있습니다.")
    bounds = {(Decimal(c["x"]), Decimal(c["width"])): c for c in columns}
    body_cells = [c for c in bordered if rect(c)[1] >= header_end and (rect(c)[0], rect(c)[2]) in bounds]
    if not body_cells:
        raise ReportParseError("메타데이터와 대응하는 표 본문 셀이 없습니다.")
    boundaries = sorted({v for c in body_cells for v in (rect(c)[1], rect(c)[1] + rect(c)[3])})
    if boundaries[0] != header_end:
        raise ReportParseError("헤더와 본문 사이의 범위를 확인할 수 없습니다.")
    # Every cell start/end is a row boundary. Sweep those exact boundaries so
    # active cells cover the entire next band, including merged rowspans. Keep
    # separate entries by sequence position: overlapping or duplicate source
    # cells must remain ambiguous rather than overwrite each other in an index.
    starts, ends = {}, {}
    for position, cell in enumerate(body_cells):
        x, y, width, height = rect(cell)
        end = y + height
        # An extreme coordinate/height ratio can round a positive height to
        # no forward Decimal interval. It still contributes the same source
        # boundaries above, but cannot cover any band in the original overlap
        # predicate and must not enter the active index.
        if end <= y:
            continue
        entry = (position, (x, width), cell)
        starts.setdefault(y, []).append(entry)
        ends.setdefault(end, []).append(entry)
    column_bounds = [(col, (Decimal(col["x"]), Decimal(col["width"]))) for col in columns]
    active_by_bound = {bound: {} for bound in bounds}
    active_count = 0
    rows, warnings = [], []
    for y0, y1 in zip(boundaries, boundaries[1:]):
        for position, bound, _ in ends.get(y0, ()):
            del active_by_bound[bound][position]
            active_count -= 1
        for position, bound, cell in starts.get(y0, ()):
            active_by_bound[bound][position] = cell
            active_count += 1
        if not active_count:
            continue
        values, sources, missing, ambiguous = {}, {}, [], []
        for col, bound in column_bounds:
            matches = active_by_bound[bound]
            if len(matches) != 1:
                (missing if not matches else ambiguous).append(col["key"])
                values[col["key"]] = None
            else:
                cell = next(iter(matches.values()))
                values[col["key"]] = cell["text"]
                sources[col["key"]] = {"item_index": cell["item_index"],
                                       "geometry": cell["geometry"],
                                       "expanded_rowspan": rect(cell)[1] != y0 or rect(cell)[3] != y1 - y0}
        dimensions = dict(selectors or {})
        for col in columns:
            canonical = {"APY_YR": "refYear", "SCHL_NM": "schoolName", "MJR_KRN_NM": "deptName"}.get(col["source_semantic_code"]) or {"APY_YR": "refYear", "SCHL_NM": "schoolName", "MJR_KRN_NM": "deptName"}.get(col["source_field_id"])
            if canonical is not None:
                dimensions[canonical] = values[col["key"]]
        row = {"sheet": "report", "row_number": len(rows) + 1, "source_page_index": page_index,
               "y": str(y0), "height": str(y1-y0), "keys": [c["key"] for c in columns],
               "cells": [values[c["key"]] for c in columns], "values": values,
               "dimensions": dimensions, "cell_sources": sources,
               "status": "complete" if not missing and not ambiguous else "ambiguous"}
        if missing or ambiguous:
            row["missing_columns"], row["ambiguous_columns"] = missing, ambiguous
            warnings.append(f"page {page_index} row {row['row_number']}: missing={missing}, ambiguous={ambiguous}")
        rows.append(row)
    # Unclassified bordered items within the body may indicate schema drift.
    end = boundaries[-1]
    ignored = [c for c in bordered if header_end <= rect(c)[1] < end and (rect(c)[0], rect(c)[2]) not in bounds]
    if ignored:
        warnings.append(f"page {page_index}: {len(ignored)}개 본문 셀의 컬럼 경계를 대응하지 못했습니다.")
    return columns, rows, warnings


def _coverage(indices: list[int], expected_pages: int | None) -> dict[str, Any]:
    duplicates = sorted(i for i, count in Counter(indices).items() if count > 1)
    received = sorted(set(indices))
    if expected_pages is None:
        return {"expected_pages": None, "received_pages": received, "missing_pages": None,
                "duplicate_pages": duplicates, "unexpected_pages": [], "complete": False}
    expected = set(range(expected_pages))
    return {"expected_pages": expected_pages, "received_pages": received,
            "missing_pages": sorted(expected - set(received)), "duplicate_pages": duplicates,
            "unexpected_pages": sorted(set(received) - expected),
            "complete": set(received) == expected and not duplicates}


def parse_report_xml(xml_bytes: bytes, *, source_page_index: int = 0,
                     expected_pages: int | None = None, metadata: dict | None = None,
                     selectors: dict[str, str] | None = None,
                     include_raw_tree: bool = True) -> dict[str, Any]:
    """Parse one server page; a fragment's ``pagecount=1`` is never a total.

    ``source_page_index`` is the zero-based reqtype=91#n page index.  Only a
    confirmed reqtype=99 total may be passed as ``expected_pages``.  No expected
    total, missing pages or ambiguous cells prevents a complete status.

    ``include_raw_tree=False`` omits page ``xml_tree`` and cell ``children``
    copies for callers that discard them. XML parsing, item indices, geometry,
    source hashes and every table/completeness validation remain unchanged.
    """
    source_page_index = _integer(source_page_index, "source_page_index")
    if expected_pages is not None:
        expected_pages = _integer(expected_pages, "expected_pages", minimum=1)
        if expected_pages > 100000:
            raise ReportParseError("페이지 수가 파서 제한을 초과했습니다.")
    if not isinstance(xml_bytes, bytes) or not xml_bytes or len(xml_bytes) > 64 * 1024 * 1024:
        raise ReportParseError("XML 원문 크기 또는 형식이 잘못되었습니다.")
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", xml_bytes, re.I):
        raise ReportParseError("DTD/ENTITY가 포함된 응답은 해석하지 않습니다.")
    try:
        root = ET.fromstring(xml_bytes, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True)))
    except ET.ParseError as e:
        raise ReportParseError("정상 XML 응답이 아닙니다.") from e
    if root.tag != "Doc":
        raise ReportParseError("확인된 UbiReport Doc 응답이 아닙니다.")
    pages = root.findall("Page")
    if len(pages) != 1:
        raise ReportParseError("페이지 단위 XML은 Page 하나여야 합니다.")
    cells = [_cell(element, i, include_raw_tree=include_raw_tree)
             for i, element in enumerate(pages[0]) if element.tag == "Item"]
    page = {"source_page_index": source_page_index,
            "source_sha256": hashlib.sha256(xml_bytes).hexdigest(),
            "source_byte_length": len(xml_bytes), "doc_attributes": dict(root.attrib),
            "page_attributes": dict(pages[0].attrib)}
    if include_raw_tree:
        page["xml_tree"] = _tree(root)
    page["cells"] = cells
    columns, rows, warnings = [], [], []
    if metadata is not None:
        try:
            columns, rows, warnings = _parse_table(cells, metadata, source_page_index, selectors)
        except ReportParseError as e:
            warnings.append(str(e))
    else:
        warnings.append("표 메타데이터가 없어 셀 원문과 좌표만 보존했습니다.")
    coverage = _coverage([source_page_index], expected_pages)
    status = "raw_only" if not rows else ("complete" if coverage["complete"] and not warnings else "partial")
    return {"format": "academyinfo-ubireport-json-v1", "status": status,
            "coverage": coverage, "pages": [page], "columns": columns,
            "rows": rows, "warnings": warnings,
            "source_table_metadata": metadata}


def combine_report_pages(reports: list[dict], *, expected_pages: int | None = None) -> dict[str, Any]:
    """Combine validated page fragments, rejecting silent omissions and drift."""
    if not reports:
        raise ReportParseError("결합할 보고서 페이지가 없습니다.")
    if expected_pages is not None:
        expected_pages = _integer(expected_pages, "expected_pages", minimum=1)
    def signature(report):
        return [{k: c[k] for k in ("key", "source_col_no", "source_field_id", "source_semantic_code", "header_path", "x", "width")} for c in report.get("columns", [])]
    first = reports[0]
    pages, rows, warnings = [], [], []
    baseline = signature(first)
    for report in reports:
        if report.get("format") != "academyinfo-ubireport-json-v1":
            raise ReportParseError("알 수 없는 페이지 JSON 형식입니다.")
        pages.extend(report["pages"])
        warnings.extend(report["warnings"])
        if signature(report) != baseline:
            warnings.append("페이지 사이에서 표 컬럼 구조가 변경되었습니다.")
        rows.extend(report["rows"])
    pages.sort(key=lambda p: p["source_page_index"])
    rows.sort(key=lambda r: (r["source_page_index"], r["row_number"]))
    for i, row in enumerate(rows, 1):
        row = dict(row)
        row["source_page_row_number"] = row["row_number"]
        row["row_number"] = i
        rows[i - 1] = row
    coverage = _coverage([p["source_page_index"] for p in pages], expected_pages)
    status = "raw_only" if not rows else ("complete" if coverage["complete"] and not warnings and all(r["status"] == "complete" for r in rows) else "partial")
    return {"format": "academyinfo-ubireport-json-v1", "status": status,
            "coverage": coverage, "pages": pages, "columns": first["columns"],
            "rows": rows, "warnings": warnings,
            "source_table_metadata": first.get("source_table_metadata")}

