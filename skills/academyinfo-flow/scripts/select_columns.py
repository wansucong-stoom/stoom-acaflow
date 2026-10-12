"""Select source columns by their complete header paths without fetching data.

Import the pure functions, or use the CLI with the current request's public
report JSON. Raw display values and source metadata remain separate from any
explicitly requested, per-row derived integer sum. No metric is inferred.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import sys
from typing import Any


class ColumnSelectionError(ValueError):
    """A source header or cell cannot be selected unambiguously."""


def _labels(labels: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(labels, (list, tuple)) or not labels:
        raise ColumnSelectionError('A complete nonempty header path is required.')
    if any(not isinstance(label, str) or not label.strip() for label in labels):
        raise ColumnSelectionError('Header labels must be nonempty source strings.')
    # Normalize presentation whitespace only; keep semantic words and units.
    return tuple(re.sub(r'\s+', '', label) for label in labels)


def _path(column: dict[str, Any]) -> tuple[str, ...]:
    if not isinstance(column, dict):
        raise ColumnSelectionError('Source column definitions are required.')
    return _labels(column.get('header_path'))


def _validate_identities(columns: list[dict[str, Any]]) -> None:
    keys = [column.get('key') for column in columns]
    positions = [column.get('source_col_no') for column in columns]
    if (any(not isinstance(key, str) or not key for key in keys)
            or len(set(keys)) != len(keys)
            or any(type(position) is not int or position < 0 for position in positions)
            or len(set(positions)) != len(positions)):
        raise ColumnSelectionError('Source column identities must be unambiguous.')


def select_single(columns: list[dict[str, Any]], header_path: list[str]) -> dict[str, Any]:
    """Return one exact complete path, including every parent header."""
    target = _labels(header_path)
    matches = [column for column in columns if _path(column) == target]
    if len(matches) != 1:
        raise ColumnSelectionError('The complete header path does not identify one column.')
    _validate_identities(matches)
    return matches[0]


def select_group(columns: list[dict[str, Any]], header_prefix: list[str], *,
                 expected_leaf_paths: list[list[str]]) -> list[dict[str, Any]]:
    """Return explicitly named leaves of a full parent path, failing on drift.

    Expected leaf paths are relative to the parent prefix. They must come from
    the current source form/guide, rather than a fixed ID or metric mapping.
    """
    prefix = _labels(header_prefix)
    if not isinstance(expected_leaf_paths, list) or not expected_leaf_paths:
        raise ColumnSelectionError('Expected leaf paths must be explicit and unique.')
    expected = [_labels(leaf) for leaf in expected_leaf_paths]
    if len(set(expected)) != len(expected):
        raise ColumnSelectionError('Expected leaf paths must be explicit and unique.')
    matches = [column for column in columns if _path(column)[:len(prefix)] == prefix]
    observed = [_path(column)[len(prefix):] for column in matches]
    if len(set(observed)) != len(observed) or set(observed) != set(expected):
        raise ColumnSelectionError('Missing, extra, or duplicate leaves in the requested group.')
    _validate_identities(matches)
    return sorted(matches, key=lambda column: column['source_col_no'])


def sum_displayed_integer_cells(row: dict[str, Any], selected_columns: list[dict[str, Any]]) -> dict[str, Any]:
    """Create an explicit per-row derived sum and retain all selected inputs.

    Does not establish a unit, aggregate period, or number of unique people.
    Missing, blank, suppressed, fractional, and ambiguous values fail closed.
    """
    if not isinstance(row, dict) or row.get('status') != 'complete':
        raise ColumnSelectionError('An incomplete row cannot produce a verified sum.')
    if not selected_columns:
        raise ColumnSelectionError('No source cells were selected.')
    _validate_identities(selected_columns)
    values = row.get('values')
    if not isinstance(values, dict):
        raise ColumnSelectionError('Source display values are required.')
    inputs = []
    for column in selected_columns:
        key = column['key']
        raw = values.get(key)
        if not isinstance(raw, str) or not re.fullmatch(r'(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)', raw.strip()):
            raise ColumnSelectionError('A missing or noninteger display value cannot be summed.')
        inputs.append({'key': key, 'source_col_no': column['source_col_no'],
                       'header_path': list(column['header_path']), 'source_value': raw,
                       'number': Decimal(raw.replace(',', '').strip()),
                       'cell_source': row.get('cell_sources', {}).get(key)})
    # Integer addition is exact even beyond Decimal's arithmetic context.
    return {'value': Decimal(sum(int(item['number']) for item in inputs)),
            'derived': True, 'operation': 'sum_displayed_integer_cells', 'inputs': inputs,
            'source_page_index': row.get('source_page_index'),
            'source_page_row_number': row.get('source_page_row_number', row.get('row_number'))}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ColumnSelectionError('Check the command and required header labels with --help.')


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = _Parser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for mode in ('column', 'group'):
        command = commands.add_parser(mode)
        command.add_argument('--input', type=Path, help='Current-request report JSON; omit to read stdin.')
        command.add_argument('--header-label', action='append', required=True,
                             help='One complete path component; repeat in parent-to-leaf order.')
        if mode == 'group':
            command.add_argument('--leaf-labels', action='append', nargs='+', required=True,
                                 help='One relative leaf path; repeat for every expected leaf.')
            command.add_argument('--sum-integers', action='store_true',
                                 help='Explicit per-row derived sum, separate from raw values.')
    return parser.parse_args(argv)


def _read_report(path: Path | None) -> dict[str, Any]:
    try:
        if path is not None and path.stat().st_size > 64 * 1024 * 1024:
            raise ColumnSelectionError('Input report exceeds the supported size.')
        text = path.read_text(encoding='utf-8') if path is not None else sys.stdin.read(64 * 1024 * 1024 + 1)
        if len(text.encode('utf-8')) > 64 * 1024 * 1024:
            raise ColumnSelectionError('Input report exceeds the supported size.')
        report = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ColumnSelectionError('A readable UTF-8 public report JSON is required.') from error
    if (not isinstance(report, dict) or report.get('command') != 'report'
            or not isinstance(report.get('columns'), list) or not isinstance(report.get('rows'), list)):
        raise ColumnSelectionError('Expected live_report report JSON with columns and rows.')
    if any(not isinstance(row, dict) or not isinstance(row.get('values'), dict) for row in report['rows']):
        raise ColumnSelectionError('Report rows must retain their source display values.')
    return report


def _decimal_json(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError('Unsupported JSON value')


def main(argv: list[str] | None = None) -> int:
    try:
        args = _arguments(argv)
        report = _read_report(args.input)
        if args.command == 'column':
            selected = [select_single(report['columns'], args.header_label)]
        else:
            selected = select_group(report['columns'], args.header_label,
                                    expected_leaf_paths=args.leaf_labels)
        keys = [column['key'] for column in selected]
        projected = []
        for row in report['rows']:
            item = {key: row[key] for key in ('dimensions', 'status', 'source_page_index',
                                             'source_page_row_number', 'row_number', 'source_request_page') if key in row}
            item['values'] = {key: row['values'].get(key) for key in keys}
            if getattr(args, 'sum_integers', False):
                item['derived_integer_sum'] = sum_displayed_integer_cells(row, selected)
            projected.append(item)
        complete = report.get('complete') is True
        result = {'status': 'ok' if complete else 'partial', 'complete': complete,
                  'selection': {'mode': args.command, 'header_path': args.header_label,
                                'expected_leaf_paths': getattr(args, 'leaf_labels', None)},
                  'columns': selected, 'rows': projected,
                  'source_report': {key: report[key] for key in ('sources', 'selectors', 'lookup_started_utc',
                                   'complete', 'status', 'completeness', 'title') if key in report}}
        print(json.dumps(result, ensure_ascii=False, default=_decimal_json))
        return 0
    except ColumnSelectionError as error:
        print(json.dumps({'status': 'error', 'complete': False, 'error': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
