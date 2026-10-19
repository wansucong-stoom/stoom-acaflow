"""Install a built wheel in an isolated target and exercise its offline CLI."""
from __future__ import annotations

import argparse
from email.parser import Parser
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, default=ROOT / 'dist')
    parser.add_argument('--temporary-root', type=Path)
    args = parser.parse_args(argv)
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    wheels = sorted(args.artifacts.glob(f'academyinfo_flow_cli-{project["version"]}-*.whl'))
    if len(wheels) != 1:
        parser.error('Build exactly one wheel for the current project version first.')
    wheel = wheels[0].resolve()
    with zipfile.ZipFile(wheel) as package:
        metadata_paths = [name for name in package.namelist() if name.endswith('.dist-info/METADATA')]
        if len(metadata_paths) != 1:
            raise ValueError('Wheel metadata is missing or ambiguous.')
        metadata = Parser().parsestr(package.read(metadata_paths[0]).decode('utf-8'))
        if metadata['Name'] != project['name'] or metadata['Version'] != project['version']:
            raise ValueError('Wheel identity does not match the source project.')
        source = ROOT / 'skills/academyinfo-flow/scripts'
        for filename in source.rglob('*.py'):
            relative = filename.relative_to(source).as_posix()
            if '__pycache__' not in filename.parts and package.read('academyinfo_live/' + relative) != filename.read_bytes():
                raise ValueError(f'Wheel contains stale Python source: {relative}')
        references = ROOT / 'skills/academyinfo-flow/references'
        for filename in references.iterdir():
            if filename.suffix in {'.md', '.json'}:
                if package.read('academyinfo_live/references/' + filename.name) != filename.read_bytes():
                    raise ValueError(f'Wheel contains stale reference: {filename.name}')
        entry = metadata_paths[0].removesuffix('METADATA') + 'entry_points.txt'
        if 'academyinfo-live = academyinfo_live.academyinfo_live:main' not in package.read(entry).decode('utf-8'):
            raise ValueError('Wheel console entry point is incorrect.')
    if args.temporary_root:
        args.temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.temporary_root) as temporary:
        scratch = Path(temporary)
        target = scratch / 'installed'
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                        '--no-index', '--no-deps', '--no-compile', '--target', str(target), str(wheel)],
                       check=True, capture_output=True, text=True)
        runner = 'import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("academyinfo_live",run_name="__main__")'
        prefix = [sys.executable, '-I', '-B', '-X', 'utf8', '-c', runner, str(target)]
        version = subprocess.run([*prefix, '--version'], cwd=scratch, check=True,
                                 capture_output=True, text=True).stdout.strip()
        if project['version'] not in version:
            raise ValueError('Installed CLI version differs from the wheel.')
        doctor = subprocess.run([*prefix, 'doctor'], cwd=scratch, check=True,
                                capture_output=True, text=True)
        doctor_result = json.loads(doctor.stdout)
        subprocess.run([*prefix, 'report', '--help'], cwd=scratch, check=True,
                       capture_output=True, text=True)
    print(json.dumps({'status': 'ok', 'wheel': wheel.name, 'version': project['version'],
                      'doctor_status': doctor_result.get('status'), 'installed_module_checked': True,
                      'source_and_references_match': True, 'official_source_queried': False}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
