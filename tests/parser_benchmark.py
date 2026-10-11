"""Offline differential and timing benchmark against a caller-supplied baseline.

Example from the repository root:
    python tests/parser_benchmark.py --baseline ../previous-release

The baseline may be a repository/skill directory or a report_tables.py file.
No network calls or production report data are used. Timing is descriptive,
not a flaky unit-test threshold; structural operation bounds are unit tested.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time

from parser_fixtures import rectangular_report, regression_cases, strip_raw_trees


PARSER_RELATIVE = Path('skills/academyinfo-flow/scripts/vendor/academyinfo_archive/report_tables.py')


def locate_parser(path):
    path = Path(path)
    for candidate in [path, path / PARSER_RELATIVE,
                      path / 'scripts/vendor/academyinfo_archive/report_tables.py',
                      path / 'report_tables.py']:
        if candidate.is_file() and candidate.name == 'report_tables.py':
            return candidate.resolve()
    raise ValueError('baseline must contain a report_tables.py parser')


def load_parser(path, name):
    spec = importlib.util.spec_from_file_location(name, locate_parser(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def encoded(result):
    # Preserve insertion order too: byte equality is stronger than dict equality.
    return json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def evaluate(module, raw, kwargs, *, lightweight=False):
    options = copy.deepcopy(kwargs)
    if lightweight:
        options['include_raw_tree'] = False
    try:
        return ('result', module.parse_report_xml(raw, **options))
    except module.ReportParseError as error:
        return ('error', str(error))


def differential_check(baseline, current):
    cases = regression_cases()
    # Vary rowspans, source item order and exact decimal geometry deterministically.
    for seed in range(16):
        raw, metadata = rectangular_report(rows=2 + seed % 9, columns=3 + seed % 8,
                                           rowspans=bool(seed % 2), seed=seed, decimal=bool(seed % 3))
        cases.append((f'generated-{seed}', raw, {'metadata': metadata, 'expected_pages': 1}))
    for name, raw, kwargs in cases:
        before = evaluate(baseline, raw, kwargs)
        after = evaluate(current, raw, kwargs)
        if encoded(before) != encoded(after):
            raise AssertionError('default output or validation changed for ' + name)
        lightweight = evaluate(current, raw, kwargs, lightweight=True)
        expected_lightweight = (before[0], strip_raw_trees(before[1])) if before[0] == 'result' else before
        if encoded(expected_lightweight) != encoded(lightweight):
            raise AssertionError('lightweight semantic output changed for ' + name)
    return len(cases)


def measure(module, raw, metadata, repeats, *, lightweight=False):
    durations = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = module.parse_report_xml(raw, metadata=metadata, expected_pages=1,
                                         **({'include_raw_tree': False} if lightweight else {}))
        durations.append(time.perf_counter() - started)
    if result['status'] != 'complete':
        raise AssertionError('benchmark fixture must parse completely')
    return {'median_seconds': statistics.median(durations), 'runs_seconds': durations,
            'serialized_bytes': len(encoded(result)), 'rows': len(result['rows'])}, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--rows', type=int, default=60)
    parser.add_argument('--columns', type=int, default=24)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.rows < 1 or args.columns < 3 or args.repeats < 1:
        parser.error('rows and repeats must be positive; columns must be at least 3')
    baseline = load_parser(args.baseline, 'parser_baseline')
    current = load_parser(Path(__file__).resolve().parents[1], 'parser_current')
    checked = differential_check(baseline, current)
    raw, metadata = rectangular_report(rows=args.rows, columns=args.columns)
    before, original = measure(baseline, raw, metadata, args.repeats)
    after, optimized = measure(current, raw, metadata, args.repeats)
    slim, lightweight = measure(current, raw, metadata, args.repeats, lightweight=True)
    if encoded(original) != encoded(optimized) or encoded(strip_raw_trees(original)) != encoded(lightweight):
        raise AssertionError('benchmark fixture output mismatch')
    output = {'benchmark': 'synthetic offline report parsing; excludes network and LLM time',
              'differential_cases_passed': checked,
              'default_json_byte_equal': True, 'lightweight_semantics_equal': True,
              'fixture': {'rows': args.rows, 'columns': args.columns, 'xml_bytes': len(raw)},
              'baseline': before, 'optimized_default': after, 'optimized_lightweight': slim,
              'default_speedup': before['median_seconds'] / after['median_seconds'],
              'lightweight_speedup': before['median_seconds'] / slim['median_seconds']}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
