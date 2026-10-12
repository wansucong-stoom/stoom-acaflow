"""Offline full-header regressions using only synthetic cells, values and hashes."""
import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True

from types import SimpleNamespace
SCRIPTS = Path(__file__).resolve().parents[1] / 'skills' / 'academyinfo-flow' / 'scripts'
args = SimpleNamespace(parser=SCRIPTS / 'vendor/academyinfo_archive/report_tables.py',
                       projection=SCRIPTS / 'live_report.py', selection_helper=SCRIPTS / 'select_columns.py',
                       cli=SCRIPTS / 'select_columns.py')
selection_spec = importlib.util.spec_from_file_location('reviewed_selection', args.selection_helper)
selection = importlib.util.module_from_spec(selection_spec)
selection_spec.loader.exec_module(selection)
ColumnSelectionError = selection.ColumnSelectionError
select_group = selection.select_group
select_single = selection.select_single
sum_displayed_integer_cells = selection.sum_displayed_integer_cells
spec = importlib.util.spec_from_file_location('reviewed_report_tables', args.parser)
report_tables = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report_tables)

GROUP = ['이수학생수(명)']
LEAVES = [['해당학과'], ['타학과 계열', '인문·사회'], ['타학과 계열', '자연과학'],
          ['타학과 계열', '공학'], ['타학과 계열', '의학'], ['타학과 계열', '예·체능']]


def synthetic_grid(*, support_value='99'):
    # 21 metadata columns, 6 hidden variables, 15 visible columns, 3 bands.
    # Geometry is artificial: visible widths=60; bands=20. Do not cite it.
    count, bands = 21, 3
    body = [{'col_no': str(no), 'b_col_id': f'field_{no}', 'b_col_cd': '',
             'b_col_hid_yn': 'Y' if 6 <= no <= 11 else 'N'} for no in range(count)]
    header = [{'col_no': str(no), 'h_celmrg_yn': 'N', 'h_col_hdr_krn_nm': ''}
              for no in range(count * bands)]
    cells = []

    def cell(text, x, y, width, height):
        cells.append({'item_index': len(cells), 'text': text,
                      'text_attributes': {'border': '1'},
                      'geometry': {k: str(v) for k, v in
                                   zip(('x', 'y', 'width', 'height'), (x, y, width, height))}})

    def head(row, col, row_span, col_span, label, x, y, width, height):
        header[row * count + col].update(h_celmrg_yn='Y', h_row_mrg_cnt=str(row_span),
                                          h_col_mrg_cnt=str(col_span), h_col_hdr_krn_nm=label)
        cell(label, x, y, width, height)

    for no, label in enumerate(['기준연도', '학교종류', '설립구분', '지역', '상태', '학교']):
        head(0, no, 3, 1, label, no * 60, 0, 60, 60)
    head(0, 12, 1, 6, '이수\n학생수(명)', 360, 0, 360, 20)
    head(1, 12, 2, 1, '해당학과', 360, 20, 60, 40)
    head(1, 13, 1, 5, '타학과 계열', 420, 20, 300, 20)
    for no, label in enumerate(['인문·사회', '자연과학', '공학', '의학', '예·체능'], 13):
        head(2, no, 1, 1, label, 420 + (no - 13) * 60, 40, 60, 20)
    head(0, 18, 3, 1, '지원금\n수령\n학생수(명)', 720, 0, 60, 60)
    head(0, 19, 2, 2, '지원금 수령\n총금액(원)', 780, 0, 120, 40)
    head(2, 19, 1, 1, '시제(작)품\n제작비', 780, 40, 60, 20)
    head(2, 20, 1, 1, '교육프로그램\n지원비', 840, 40, 60, 20)
    for visible_no, value in enumerate(['2025', '대학교', '사립', '검증지역', '기존', '검증대학',
                                      '10', '1', '2', '3', '0', '4', support_value, '1000', '2000']):
        cell(value, visible_no * 60, 60, 60, 20)
    for row in body + header:
        row['item_mstr_id'] = 'synthetic'
    return cells, {'master': [{'item_mstr_id': 'synthetic', 'col_num': str(count), 'row_num': '2'}],
                   'body': body, 'header': header}


class HeaderRegression(unittest.TestCase):
    def parse_fixture(self, support_value='99'):
        cells, metadata = synthetic_grid(support_value=support_value)
        columns, rows, warnings = report_tables._parse_table(cells, metadata, 0, {})
        self.assertEqual(warnings, [])
        return columns, rows[0]

    def test_multiband_group_and_support_are_distinct_by_source_column(self):
        columns, row = self.parse_fixture()
        group = select_group(columns, GROUP, expected_leaf_paths=LEAVES)
        support = select_single(columns, ['지원금 수령 학생수(명)'])
        self.assertEqual([c['source_col_no'] for c in group], list(range(12, 18)))
        self.assertEqual(support['source_col_no'], 18)
        self.assertEqual(sum_displayed_integer_cells(row, group)['value'], 20)
        self.assertEqual(row['values'][support['key']], '99')
        self.assertEqual(row['cell_sources'][group[0]['key']]['geometry']['x'], '360')
        self.assertEqual(row['cell_sources'][support['key']]['geometry']['x'], '720')

    def test_equal_values_do_not_prove_same_metric(self):
        columns, row = self.parse_fixture(support_value='20')
        group = select_group(columns, GROUP, expected_leaf_paths=LEAVES)
        support = select_single(columns, ['지원금 수령 학생수(명)'])
        self.assertEqual(sum_displayed_integer_cells(row, group)['value'], 20)
        self.assertEqual(row['values'][support['key']], '20')
        self.assertNotIn(support['key'], [c['key'] for c in group])

    def test_duplicate_leaf_labels_require_complete_parent_path(self):
        columns = [{'key': 'a', 'source_col_no': 0, 'header_path': ['이수학생수(명)', '계']},
                   {'key': 'b', 'source_col_no': 1, 'header_path': ['지원금 수령학생수(명)', '계']}]
        with self.assertRaises(ColumnSelectionError):
            select_single(columns, ['계'])
        self.assertEqual(select_single(columns, ['이수학생수(명)', '계'])['key'], 'a')
        with self.assertRaises(ColumnSelectionError):
            select_single(columns + [deepcopy(columns[0])], ['이수학생수(명)', '계'])

    def test_source_header_swap_or_geometry_drift_cannot_silently_pass(self):
        for mutation in ('label', 'geometry'):
            cells, metadata = synthetic_grid()
            support = next(c for c in cells if c['text'] == '지원금\n수령\n학생수(명)')
            if mutation == 'label':
                support['text'] = '이수\n학생수(명)'
            else:
                support['geometry']['x'] = '721'
            with self.assertRaises(report_tables.ReportParseError):
                report_tables._parse_table(cells, metadata, 0, {})

    def test_group_schema_drift_blank_and_zero_are_distinct(self):
        columns, row = self.parse_fixture()
        with self.assertRaises(ColumnSelectionError):
            select_group(columns[:-4], GROUP, expected_leaf_paths=LEAVES)
        with self.assertRaises(ColumnSelectionError):
            select_group(columns + [deepcopy(columns[6])], GROUP, expected_leaf_paths=LEAVES)
        group = select_group(columns, GROUP, expected_leaf_paths=LEAVES)
        self.assertEqual(row['values'][group[4]['key']], '0')
        row['values'][group[4]['key']] = ''
        with self.assertRaises(ColumnSelectionError):
            sum_displayed_integer_cells(row, group)

    @unittest.skipUnless(args.cli, 'No staged CLI supplied')
    def test_cli_preserves_hashes_raw_values_and_separates_derived_sums(self):
        columns, row = self.parse_fixture()
        report = {'command': 'report', 'status': 'ok', 'complete': True,
                  'columns': columns, 'rows': [row],
                  'sources': [{'raw_sha256': 'a' * 64, 'synthetic': True}],
                  'selectors': {'synthetic': True}}
        command = [sys.executable, '-X', 'utf8', str(args.cli), 'group',
                   '--header-label', GROUP[0], '--sum-integers']
        for leaf in LEAVES:
            command.extend(['--leaf-labels', *leaf])
        result = subprocess.run(command, input=json.dumps(report), capture_output=True,
                                text=True, encoding='utf-8', check=True)
        answer = json.loads(result.stdout)
        self.assertEqual(answer['source_report']['sources'], report['sources'])
        self.assertEqual(answer['source_report']['selectors'], report['selectors'])
        self.assertEqual(answer['rows'][0]['derived_integer_sum']['value'], '20')
        group = select_group(columns, GROUP, expected_leaf_paths=LEAVES)
        self.assertEqual(answer['rows'][0]['values'], {c['key']: row['values'][c['key']] for c in group})
        self.assertTrue(answer['rows'][0]['derived_integer_sum']['derived'])

    @unittest.skipUnless(args.cli, 'No staged CLI supplied')
    def test_cli_rejects_duplicate_exact_paths(self):
        columns, row = self.parse_fixture()
        support = select_single(columns, ['지원금 수령 학생수(명)'])
        columns.append(deepcopy(support))
        report = {'command': 'report', 'status': 'ok', 'complete': True,
                  'columns': columns, 'rows': [row]}
        result = subprocess.run([sys.executable, '-X', 'utf8', str(args.cli), 'column',
                                 '--header-label', '지원금 수령 학생수(명)'],
                                input=json.dumps(report), capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['status'], 'error')
        self.assertEqual(result.stderr, '')

    @unittest.skipUnless(args.projection, 'No proposed live projection supplied')
    def test_compact_projection_keeps_exact_header_geometry(self):
        # Load only local code; its missing vendor path triggers the standard
        # import fallback. These pure projection functions perform no I/O.
        spec = importlib.util.spec_from_file_location('reviewed_live_report', args.projection)
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)
        columns, row = self.parse_fixture()
        group = select_group(columns, GROUP, expected_leaf_paths=LEAVES)
        self.assertEqual(group[0]['header_cells'][0]['geometry'],
                         {'x': '360', 'y': '0', 'width': '360', 'height': '20'})
        combined = {'columns': columns, 'rows': [row], 'status': 'complete', 'warnings': []}
        request = argparse.Namespace(school_names=[], dept_names=[], offset=0, limit=50, level='school')
        result = {'command': 'report', 'catalog_item': {'mjr_use_step_cd': '0'}}
        live._numeric_result(request, result, combined, True)
        projected = live.compact_result(result)
        support = select_single(projected['columns'], ['지원금 수령 학생수(명)'])
        self.assertEqual(support['x'], '720')
        self.assertEqual(support['width'], '60')
        self.assertEqual(support['header_cells'][0]['geometry'],
                         {'x': '720', 'y': '0', 'width': '60', 'height': '60'})
        self.assertEqual(projected['rows'][0]['values'][support['key']], '99')



if __name__ == '__main__':
    unittest.main()
