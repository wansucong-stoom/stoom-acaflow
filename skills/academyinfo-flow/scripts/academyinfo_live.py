"""One JSON CLI for the bundled fresh-source tools, without archive access.

Works both as a plugin script and as the academyinfo-live console command.
All runtime report state remains in memory in the existing protocol adapters.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

VERSION = '0.3.1'
_HERE = Path(__file__).resolve().parent
_JSON_COMMANDS = {'scope', 'catalog', 'schools', 'affiliations', 'departments', 'metric', 'info'}
_REPORT_COMMANDS = {'report', 'attachments', 'pdf'}


class CliInputError(ValueError):
    pass


class CliParser(argparse.ArgumentParser):
    def error(self, message):
        raise CliInputError('명령과 필수 인수를 확인하세요. academyinfo-live --help로 사용법을 볼 수 있습니다.')


class LookupFailure(Exception):
    def __init__(self, result):
        self.result = result


def _module(name):
    # Sibling helper imports work in both source scripts and installed wheels.
    # The console process does not import or query the archive package.
    if __package__:
        return importlib.import_module('.' + name, __package__)
    if str(_HERE) not in sys.path:
        sys.path.insert(0, str(_HERE))
    return importlib.import_module(name)


def _error(code, message):
    return {'schema_version': 1, 'mode': 'live', 'status': 'error', 'complete': False,
            'error': {'code': code, 'message': message}, 'rows': []}


def _parse(engine, argv):
    try:
        return engine.build_parser().parse_args(argv)
    except engine.InputError:
        raise CliInputError('명령과 필수 조회 인수를 확인하세요. 해당 명령의 --help로 사용법을 볼 수 있습니다.') from None


def exit_code(result):
    if result.get('status') == 'ok' and result.get('complete') is True and not result.get('error'):
        return 0
    return 3 if result.get('status') == 'partial' else 2


def _write_output(output, payload, *, force=False):
    """Commit complete JSON atomically; a failed write preserves an old file."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.parent / ('.academyinfo-output-' + uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(payload + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        if force:
            os.replace(temporary, output)
        else:
            # A hard link is an atomic exclusive commit on the same filesystem.
            # It never replaces a target created since the preflight check.
            os.link(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def _help():
    print('''academyinfo-live — 대학알리미 공식 원천 실시간 조회

사용법: academyinfo-live <명령> [조회 인수] [공통 옵션]
        python -m academyinfo_live <명령> [조회 인수]

명령:
  scope         현재 공개 연도·기관 구분
  catalog       연도·기관별 공시 항목 목록
  schools       학교 명부
  affiliations  학교의 소속기관
  departments   학교별 학과 명부
  metric        6종 학과 주요지표
  info          학과 기본정보(스키마 검증 상태 확인)
  report        수치 장표(서버 항목 ID 또는 7-가 같은 공시코드)
  attachments   공시 첨부 목록
  pdf           확인한 첨부 PDF의 지정 페이지 추출
  guide         허용된 지침 PDF의 관련 페이지 추출
  batch         조회 조건 JSON의 일괄 실행
  doctor        Python·의존성 점검, --check-source일 때만 원천 연결 점검

공통 옵션(명령 앞뒤 모두 사용 가능):
  --output PATH  결과 JSON 저장. 이미 존재하면 --force 필요
  --force        지정한 JSON 파일 덮어쓰기 허용
  --pretty       결과 JSON 들여쓰기
  --progress     공개 진행 이벤트를 stderr에 JSON Lines로 표시
  --full-output  장표의 셀 상세 포함(기본은 compact)
  --version      버전 표시

예:
  academyinfo-live scope
  academyinfo-live catalog --year 2026 --division 02 --keyword 연구
  academyinfo-live report --year 2026 --division 02 --item 7-가 --level department --dept-keyword 수학 --dept-keyword 수리 --max-pages 1000 --limit 10000 --progress --output math.json

기관구분: 01 전문대학, 02 대학, 03 소속 대학원, 04 대학원대학
종료 코드: 0 검증 완료 / 2 오류 / 3 부분 결과 / 130 사용자 중단
현재 파일 출력은 JSON입니다. 엑셀 생성이나 종료 후 세션 재개를 뜻하지 않습니다.
세부 인수: academyinfo-live <명령> --help''')


def _published_year(args, progress):
    if not hasattr(args, 'year'):
        return []
    progress({'stage': 'published_scope'})
    source = _module('live_json').run_command({'command': 'scope', 'year': args.year,
                                             'division': getattr(args, 'division', '02')})
    if source.get('status') != 'ok' or not source.get('complete'):
        raise LookupFailure(source)
    if args.year not in source.get('data', {}).get('years', []):
        raise LookupFailure(_error('year_not_published', '요청 연도가 현재 공식 공개 연도 목록에 없습니다.'))
    return source.get('sources', [])


def _resolve_item(args, progress):
    item = getattr(args, 'item', '')
    if re.fullmatch(r'[0-9]{1,6}', item):
        return [], None
    if not re.fullmatch(r'[0-9]{1,3}-[가-힣]', item):
        raise CliInputError('항목은 현재 목록의 숫자 ID 또는 7-가 같은 공시코드로 지정하세요.')
    progress({'stage': 'item_resolution'})
    result = _module('live_json').run_command({'command': 'catalog', 'year': args.year,
        'division': args.division, 'keyword': '', 'limit': 1000})
    if result.get('status') != 'ok' or not result.get('complete'):
        raise LookupFailure(result)
    pattern = re.compile(r'^\s*' + re.escape(item) + r'(?:[.．\s]|$)')
    candidates = [r for r in result['rows'] if pattern.search(r.get('pgm_estn_nm', ''))]
    if len(candidates) != 1:
        raise LookupFailure(_error('item_code_unresolved', '현재 공식 목록에서 공시코드를 유일한 항목으로 연결하지 못했습니다. catalog 결과를 확인하세요.'))
    row = candidates[0]
    args.item = str(row['item_id'])
    return result.get('sources', []), {'requested_code': item, 'resolved_item': args.item,
                                     'title': row['pgm_estn_nm'], 'source': 'fresh_catalog'}


def execute(argv, options, progress):
    command = argv[0]
    if command == 'doctor':
        p = CliParser(prog='academyinfo-live doctor')
        p.add_argument('--check-source', action='store_true')
        p.add_argument('--require-pdf', action='store_true')
        args = p.parse_args(argv[1:])
        result = _module('runtime_preflight').inspect_runtime(**vars(args))
        result['complete'] = bool(result.get('ok'))
        if result.get('ok'):
            result['status'] = 'ok'
        return result
    if command == 'batch':
        engine = _module('live_batch')
        args = _parse(engine, argv[1:])
        progress({'stage': 'batch_execution'})
        return engine.run_queries(engine.read_input(args.input), full_output=options.full_output)
    if command == 'guide':
        engine = _module('live_guide')
        args = _parse(engine, argv[1:])
        progress({'stage': 'guide_download'})
        return engine.run_command(args)
    if command in _JSON_COMMANDS:
        engine = _module('live_json')
    elif command in _REPORT_COMMANDS:
        engine = _module('live_report')
    else:
        raise CliInputError('지원하는 명령을 확인하세요. academyinfo-live --help로 사용법을 볼 수 있습니다.')
    args = _parse(engine, argv)
    if command != 'scope':
        sources = _published_year(args, progress)
    else:
        sources = []
    resolution = None
    if command in {'report', 'attachments'}:
        item_sources, resolution = _resolve_item(args, progress)
        sources.extend(item_sources)
    progress({'stage': 'lookup', 'command': command})
    if command in _REPORT_COMMANDS:
        result = engine.run_command(args, progress=progress)
        if command == 'report' and (not options.full_output or args.compact):
            result = engine.compact_result(result)
    else:
        result = engine.run_command(args)
    if sources:
        result['selection_validation_sources'] = sources
    if resolution:
        result['item_resolution'] = resolution
    return result


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv == ['--help'] or argv == ['-h']:
        _help()
        return 0
    common = CliParser(add_help=False, allow_abbrev=False)
    common.add_argument('--output')
    common.add_argument('--force', action='store_true')
    common.add_argument('--pretty', action='store_true')
    common.add_argument('--progress', action='store_true')
    common.add_argument('--full-output', action='store_true')
    common.add_argument('--version', action='store_true')
    options = None
    try:
        options, remaining = common.parse_known_args(argv)
        if options.version:
            print(VERSION)
            return 0
        if not remaining:
            raise CliInputError('조회 명령을 지정하세요.')
        output = Path(options.output) if options.output else None
        if output and output.suffix.lower() != '.json':
            raise CliInputError('--output은 JSON 파일 경로로 지정하세요. 다른 형식의 직접 출력은 지원하지 않습니다.')
        if output and output.exists() and not options.force:
            raise CliInputError('출력 파일이 이미 존재합니다. 다른 경로 또는 --force를 사용하세요.')
        def progress(event):
            if options.progress:
                print(json.dumps(event, ensure_ascii=False, allow_nan=False), file=sys.stderr, flush=True)
        try:
            result = execute(remaining, options, progress)
        except LookupFailure as failure:
            result = failure.result
        if remaining[0] != 'doctor':
            try:
                result['route_registry'] = _module('route_registry').observe_result(result)
            except Exception:
                result['route_registry'] = {'recorded': False, 'route_count': 0,
                    'warning': '경로 메타데이터를 기록하지 못했습니다. 원천 조회 결과는 유지합니다.'}
        code = exit_code(result)
        payload = json.dumps(result, ensure_ascii=False, allow_nan=False,
                             indent=2 if options.pretty else None)
        if output:
            _write_output(output, payload, force=options.force)
            print(json.dumps({'status': result.get('status'), 'complete': result.get('complete'),
                'output_file': str(output), 'returned_row_count': result.get('returned_row_count'),
                'error': result.get('error')}, ensure_ascii=False))
        else:
            print(payload)
        progress({'stage': 'finished', 'status': result.get('status'),
                  'complete': result.get('complete'), 'exit_code': code})
        return code
    except KeyboardInterrupt:
        print(json.dumps(_error('interrupted', '사용자가 중단했습니다. 미완료 결과를 완료로 저장하지 않습니다.'), ensure_ascii=False))
        return 130
    except Exception as error:
        # Do not forward argv, exception text, server bodies or session values.
        message = str(error) if isinstance(error, CliInputError) else '조회 또는 결과 저장을 완료하지 못했습니다. 필수 인수·의존성·출력 경로를 확인하세요.'
        print(json.dumps(_error('invalid_input' if isinstance(error, CliInputError) else 'cli_execution_error', message), ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
