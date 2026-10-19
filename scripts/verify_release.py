"""Verify documentation, release identities and archive bytes without network I/O."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tomllib
from urllib.parse import unquote, urlsplit
import zipfile

import build_plugin

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)")


def markdown_links(root: Path) -> int:
    """Check contained relative file links; external URLs are verified separately."""
    checked = 0
    files = [*root.glob('*.md'), *root.joinpath('docs').rglob('*.md'),
             *root.joinpath('downloads').glob('*.md'),
             *root.joinpath('skills').rglob('*.md')]
    for document in files:
        for raw in LINK.findall(document.read_text(encoding='utf-8-sig')):
            target = urlsplit(raw.strip('<>'))
            if target.scheme or target.netloc or not target.path:
                continue
            resolved = (document.parent / unquote(target.path)).resolve()
            if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                raise ValueError(f'Broken or escaping local link: {document.relative_to(root)} -> {raw}')
            checked += 1
    return checked


def archive_bytes(filename: Path, expected: dict[str, bytes]) -> None:
    with zipfile.ZipFile(filename) as package:
        names = package.namelist()
        if len(names) != len(set(names)):
            raise ValueError(f'Duplicate archive members: {filename.name}')
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name:
                raise ValueError(f'Unsafe archive member: {filename.name}: {name}')
        if set(names) != set(expected):
            missing = sorted(set(expected) - set(names))
            extra = sorted(set(names) - set(expected))
            raise ValueError(f'Archive inventory differs: {filename.name}; missing={missing}; extra={extra}')
        for name, source_bytes in expected.items():
            if package.read(name) != source_bytes:
                raise ValueError(f'Archive contains stale source: {filename.name}: {name}')


def download_checksums(directory: Path) -> int:
    expected = {}
    for line in (directory / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        digest, separator, name = line.partition('  ')
        if (not separator or not re.fullmatch('[0-9a-f]{64}', digest)
                or len(PurePosixPath(name).parts) != 1 or '\\' in name or name in expected):
            raise ValueError('Invalid download checksum entry.')
        expected[name] = digest
    files = {p.name for p in directory.iterdir() if p.suffix in {'.zip', '.whl'}}
    if set(expected) != files:
        raise ValueError('Download checksum inventory differs from the release files.')
    for name, digest in expected.items():
        filename = directory / name
        if filename.is_symlink() or hashlib.sha256(filename.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Download checksum differs: {name}')
    return len(files)


def verify(root: Path, artifact_dir: Path | None = None) -> dict:
    root = root.resolve()
    previous_root = build_plugin.ROOT
    build_plugin.ROOT = root
    try:
        manifest = build_plugin._manifests()
        version = manifest['version']
        project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']
        if project['version'] != version:
            raise ValueError('CLI project and plugin versions differ.')
        cli = ast.parse((root / 'skills/academyinfo-flow/scripts/academyinfo_live.py').read_text(encoding='utf-8'))
        versions = [node.value.value for node in cli.body if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in node.targets)
                    and isinstance(node.value, ast.Constant)]
        if versions != [version]:
            raise ValueError('CLI command and plugin versions differ.')
        links = markdown_links(root)
        checksums = download_checksums(root / 'downloads')
        artifacts = []
        if artifact_dir is not None:
            skill = root / 'skills/academyinfo-flow'
            skill_files = build_plugin._skill_files()
            plugin_files = ['plugin.json', 'mcp.json', '.mcp.json', '.codex-plugin/plugin.json',
                            '.claude-plugin/plugin.json', 'LICENSE', 'pyproject.toml']
            expected_plugin = {name: (root / name).read_bytes() for name in plugin_files}
            expected_plugin.update({p.relative_to(root).as_posix(): p.read_bytes() for p in skill_files})
            plans = [('plugin', expected_plugin)]
            for target in ('codex', 'claude-web'):
                entries = {'academyinfo-flow/' + p.relative_to(skill).as_posix(): p.read_bytes()
                           for p in skill_files
                           if target != 'claude-web' or p.relative_to(skill).parts[0] != 'agents'}
                plans.append(('skill-' + target, entries))
            for target, entries in plans:
                filename = artifact_dir / f'academyinfo-flow-{target}-{version}.zip'
                archive_bytes(filename, entries)
                archive_bytes(root / 'downloads' / filename.name, entries)
                artifacts.append({'file': filename.name, 'files': len(entries),
                                  'sha256': hashlib.sha256(filename.read_bytes()).hexdigest()})
        return {'status': 'ok', 'version': version, 'checked_local_links': links,
                'checked_download_checksums': checksums,
                'archives': artifacts, 'network_used': False}
    finally:
        build_plugin.ROOT = previous_root


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    arguments = parser.parse_args(argv)
    try:
        print(json.dumps(verify(ROOT, arguments.artifacts), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, SyntaxError, zipfile.BadZipFile) as error:
        print(f'Release verification failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
