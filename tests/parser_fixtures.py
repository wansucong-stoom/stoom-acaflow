"""Deterministic, synthetic report layouts; no downloaded disclosure records.

The small sample/schema helpers derive from STOOM's stoom-academyinfo tests.
Copyright (c) 2026 STOOM. MIT license; the original notice is preserved in
skills/academyinfo-flow/scripts/vendor/academyinfo_archive/LICENSE.
"""
from __future__ import annotations

import copy
from decimal import Decimal
import random
from xml.sax.saxutils import escape


def item(x, y, w, h, value):
    return (f'<Item classname="UbiTextItem" x="{x}" y="{y}" width="{w}" height="{h}">'
            f'<Text border="1">{escape(value)}</Text></Item>')


def document(elements):
    return ('<?xml version="1.0" encoding="UTF-8"?><Doc pagecount="1">'
            '<Page pagenum="">' + ''.join(elements) + '</Page></Doc>').encode()


def sample(*, missing=False, overlap=False, label="학과(전공)"):
    elements = [item(0, 0, 10, 10, "기준연도"), item(10, 0, 20, 10, "학교명"),
                item(30, 0, 30, 10, label), item(0, 10, 10, 20, "2024"),
                item(10, 10, 20, 20, "한남대학교"), item(30, 10, 30, 10, "0005891"),
                item(30, 20, 30, 10, "")]
    if missing:
        elements.pop()
    if overlap:
        elements.append(item(30, 10, 30, 10, "0"))
    return document(elements)


def schema():
    names = ["기준연도", "학교명", "학과(전공)"]
    ids = ["COL_8_VAL", "SCHL_NM", "MJR_KRN_NM"]
    codes = ["APY_YR", "SCHL_NM", "MJR_KRN_NM"]
    return {"master": [{"col_num": "3", "row_num": "0"}],
            "header": [{"col_no": str(i), "h_col_hdr_krn_nm": n, "h_celmrg_yn": "Y",
                        "h_row_mrg_cnt": "1", "h_col_mrg_cnt": "1"} for i, n in enumerate(names)],
            "body": [{"col_no": str(i), "b_col_hid_yn": "N", "b_col_id": ids[i],
                      "b_col_cd": codes[i]} for i in range(3)]}


def rectangular_report(*, rows=40, columns=24, rowspans=False, seed=None, decimal=False):
    """Create a complete table with independently staggered column rowspans."""
    if rows < 1 or columns < 3:
        raise ValueError('rows >= 1 and columns >= 3 are required')
    scale = Decimal('0.1') if decimal else Decimal(10)
    names = ['기준연도', '학교명', '학과(전공)'] + [f'항목 {i}' for i in range(3, columns)]
    ids = ['APY_YR', 'SCHL_NM', 'MJR_KRN_NM'] + [f'COL_{i}' for i in range(3, columns)]
    metadata = {'master': [{'col_num': str(columns), 'row_num': '0'}],
                'header': [{'col_no': str(i), 'h_col_hdr_krn_nm': name, 'h_celmrg_yn': 'Y',
                            'h_row_mrg_cnt': '1', 'h_col_mrg_cnt': '1'} for i, name in enumerate(names)],
                'body': [{'col_no': str(i), 'b_col_hid_yn': 'N', 'b_col_id': key,
                          'b_col_cd': key if i < 3 else ''} for i, key in enumerate(ids)]}
    headers, body = [], []
    x = Decimal(0)
    for col, name in enumerate(names):
        width = scale * (1 + col % 3)
        headers.append(item(x, 0, width, scale, name))
        row = 0
        while row < rows:
            span = min(rows - row, rows if col == 0 and rowspans else
                       1 + col % 4 if rowspans and col != 2 else 1)
            value = ('2024' if col == 0 else f'시험대학 {row // 5}' if col == 1
                     else f'{row:07}' if col == 2 else ['', '0', '-', '한글 & 값', str(row * columns + col)][(row + col) % 5])
            body.append(item(x, scale * (row + 1), width, scale * span, value))
            row += span
        x += width
    if seed is not None:
        random.Random(seed).shuffle(body)
    return document(headers + body), metadata


def strip_raw_trees(result):
    """Expected slim representation, keeping every other field and order."""
    result = copy.deepcopy(result)
    for page in result['pages']:
        page.pop('xml_tree', None)
        for cell in page['cells']:
            cell.pop('children', None)
    return result


def regression_cases():
    """Return valid, partial and rejected-input cases for differential checks."""
    cases = []

    def add(name, raw, metadata=None, **kwargs):
        cases.append((name, raw, {'metadata': metadata, 'expected_pages': 1, **kwargs}))

    add('rowspans-and-original-strings', sample(), schema())
    add('missing-cell', sample(missing=True), schema())
    add('overlapping-cell', sample(overlap=True), schema())
    add('header-label-drift', sample(label='변경된 학과명'), schema())
    add('without-metadata', sample())
    add('partial-coverage', sample(), schema(), expected_pages=3, source_page_index=1)
    rich = sample().replace(b'<Page pagenum="">', b'<Page pagenum=""><!-- before --><?source test?>')
    rich = rich.replace('0005891</Text>'.encode(), '00<Span emphasis="yes">058</Span>91</Text>tail'.encode())
    rich = rich.replace(b'</Page>', b'<!-- after --><?done yes?></Page>')
    add('comments-pis-and-nested-text', rich, schema())

    metadata = schema()
    metadata['body'][1]['b_col_hid_yn'] = 'Y'
    add('hidden-column', document([item(0, 0, 10, 10, '기준연도'), item(10, 0, 30, 10, '학과(전공)'),
                                   item(0, 10, 10, 10, '2024'), item(10, 10, 30, 10, '0001')]), metadata)
    metadata = schema()
    metadata['header'][1].update(h_col_hdr_krn_nm='인원', h_col_mrg_cnt='2')
    metadata['header'][2].update(h_col_hdr_krn_nm='인원', h_celmrg_yn='N')
    add('unique-bottom-colspan-partition', document([item(0, 0, 10, 10, '기준연도'), item(10, 0, 50, 10, '인원'),
                                                    item(0, 10, 10, 10, '2024'), item(10, 10, 20, 10, '10'),
                                                    item(30, 10, 30, 10, '20')]), metadata)
    add('ambiguous-bottom-colspan-partition', document([item(0, 0, 10, 10, '기준연도'), item(10, 0, 50, 10, '인원'),
                                                       item(0, 10, 10, 10, '2024'), item(10, 10, 20, 10, '10'),
                                                       item(30, 10, 30, 10, '20'), item(10, 20, 10, 10, '10'),
                                                       item(20, 20, 40, 10, '20')]), metadata)

    metadata = schema()
    metadata['header'][2]['h_col_hdr_ofcfmla'] = 'expression'
    add('formula-label-variation', sample(label='계산 결과'), metadata)
    metadata = schema()
    metadata['master'][0]['col_num'] = '5'
    add('stale-master-count', sample(), metadata)
    metadata = schema()
    metadata['body'][0]['b_col_id'] = 'SCHL_NM'
    add('duplicate-field-id', sample(), metadata)
    metadata = schema()
    metadata['header'][2]['h_col_mrg_cnt'] = '2'
    add('out-of-bounds-header-span', sample(), metadata)
    metadata = schema()
    metadata['header'].append(copy.deepcopy(metadata['header'][0]))
    add('duplicate-header-metadata', sample(), metadata)

    for description, addition in [
        ('ignored-body-cell', item(60, 10, 10, 10, '분류 미확인')),
        ('adjacent-row', item(0, 40, 10, 10, '2025') + item(10, 40, 20, 10, '별도대학') + item(30, 40, 30, 10, '-')),
        ('line-item', '<Item classname="UbiLineItem" x="0" y="35" width="60" height="0"><Shape/></Item>'),
    ]:
        add(description, sample().replace(b'</Page>', addition.encode() + b'</Page>'), schema())

    add('rounded-zero-forward-interval', document([
        item(0, '1E+30', 10, '1E+29', '기준연도'), item(10, '1E+30', 20, '1E+29', '학교명'),
        item(30, '1E+30', 30, '1E+29', '학과(전공)'), item(0, '1.1E+30', 10, '1E+29', '2024'),
        item(10, '1.1E+30', 20, '1E+29', '시험대학'), item(30, '1.1E+30', 30, '1E-20', '축소된 셀')]), schema())

    for rows, columns, rowspans, seed, decimal in [(1, 3, False, None, False), (8, 12, True, 17, False),
                                                   (9, 7, True, 33, True), (6, 5, False, 21, True)]:
        raw, metadata = rectangular_report(rows=rows, columns=columns, rowspans=rowspans, seed=seed, decimal=decimal)
        add(f'grid-{rows}-{columns}-{rowspans}-{decimal}', raw, metadata, selectors={'pubYear': '2026'})
    for number in ['NaN', 'Infinity', '-Infinity', 'not-a-number']:
        add('invalid-coordinate-' + number, sample().replace(b'x="0"', ('x="' + number + '"').encode(), 1), schema())
    add('invalid-zero-width-text', sample().replace(b'width="10"', b'width="0"', 1), schema())
    for description, raw in [
        ('non-report-xml', b'<Error>not ready</Error>'),
        ('prohibited-dtd-entity', b'<!DOCTYPE Doc [<!ENTITY x "value">]><Doc><Page/></Doc>'),
        ('multiple-pages', b'<Doc><Page/><Page/></Doc>'),
        ('malformed-xml', b'<Doc><Page>'),
    ]:
        add(description, raw, schema())
    return cases
