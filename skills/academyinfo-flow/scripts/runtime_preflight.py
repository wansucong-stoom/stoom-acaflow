"""Check this Python runtime; query the official public scope only on request.

No installation, credentials, client configuration, or MCP connection is
changed. Offline readiness does not establish successful source access.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable


def _scope(timeout: int) -> dict:
    command = [sys.executable, '-B', '-X', 'utf8', str(Path(__file__).with_name('live_json.py')), 'scope']
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=timeout)
        payload = json.loads(completed.stdout)
    except subprocess.TimeoutExpired:
        return {'status': 'error', 'reason': 'source_timeout'}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {'status': 'error', 'reason': 'source_response_unavailable_or_invalid'}
    success = (completed.returncode == 0 and isinstance(payload, dict)
               and payload.get('status') == 'ok' and payload.get('complete') is True)
    # live_json emits only public JSON. Preserve its values, sources, hashes and
    # failure state; never echo process stderr, bootstrap HTML or runtime tokens.
    return {'status': 'ok' if success else 'error', 'scope_response': payload,
            'process_exit_code': completed.returncode}


def inspect_runtime(*, check_source: bool = False, require_pdf: bool = False,
                    timeout: int = 45, scope_reader: Callable[[int], dict] | None = None) -> dict:
    python_ready = sys.version_info[:2] >= (3, 11)
    modules = {name: importlib.util.find_spec(name) is not None
               for name in ('ssl', 'urllib.request', 'zlib', 'xml.etree.ElementTree', 'decimal')}
    scripts_ready = all(Path(__file__).with_name(name).is_file()
                        for name in ('live_json.py', 'live_report.py', 'live_guide.py'))
    try:
        pdf_version = importlib.metadata.version('pdfplumber')
    except importlib.metadata.PackageNotFoundError:
        pdf_version = None
    match = re.match(r'^(\d+)\.(\d+)', pdf_version or '')
    pdf_module = importlib.util.find_spec('pdfplumber') is not None
    stable_version = re.fullmatch(r'\d+(?:\.\d+)*(?:\.post\d+)?', pdf_version or '') is not None
    pdf_ready = bool(pdf_module and stable_version and match and (0, 11) <= tuple(map(int, match.groups())) < (1, 0))
    runtime_ready = python_ready and all(modules.values()) and scripts_ready and (pdf_ready or not require_pdf)
    source = {'status': 'not_checked'}
    if check_source:
        source = (scope_reader or _scope)(timeout) if runtime_ready else {'status': 'not_attempted', 'reason': 'runtime_unavailable'}
    source_verified = check_source and source.get('status') == 'ok'
    ok = runtime_ready and (not check_source or source_verified)
    return {'ok': ok, 'status': 'source_verified' if source_verified else
            ('runtime_ready_source_unverified' if ok else 'blocked'),
            'runtime': {'python_version': '.'.join(map(str, sys.version_info[:3])),
                        'python_3_11_or_newer': python_ready, 'standard_modules': modules,
                        'bundled_entrypoints_present': scripts_ready},
            'pdf': {'required': require_pdf, 'available': pdf_ready, 'module_present': pdf_module, 'version': pdf_version,
                    'required_version': '>=0.11,<1'},
            'source': source, 'source_access_verified': bool(source_verified),
            'verification_scope': 'runtime and optional public scope lookup; client skill loading and other reports not verified'}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-source', action='store_true', help='Fresh official scope query; requires allowed network access.')
    parser.add_argument('--require-pdf', action='store_true', help='Also require the optional PDF parser.')
    parser.add_argument('--timeout', type=int, default=45, choices=range(1, 61), metavar='1..60')
    args = parser.parse_args(argv)
    result = inspect_runtime(check_source=args.check_source, require_pdf=args.require_pdf, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
