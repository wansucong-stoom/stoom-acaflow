"""Build distinct plugin, Codex folder skill, and Claude web skill archives."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def _is_link(path: Path) -> bool:
    attributes = path.lstat()
    return stat.S_ISLNK(attributes.st_mode) or bool(
        getattr(attributes, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))


def _manifests() -> dict:
    manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    overlay = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    if manifest["name"] != overlay["name"] or manifest["version"] != overlay["version"]:
        raise ValueError("Plugin identity/version differs between manifests.")
    source_interface = manifest["extensions"]["com.openai"]["interface"]
    if source_interface["defaultPrompt"] != overlay["interface"]["defaultPrompt"]:
        raise ValueError("Plugin default prompts differ between manifests.")
    claude = json.loads((ROOT / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
    marketplace = json.loads((ROOT / '.claude-plugin/marketplace.json').read_text(encoding='utf-8'))
    matches = [plugin for plugin in marketplace.get('plugins', []) if plugin.get('name') == manifest['name']]
    if (claude.get('name'), claude.get('version')) != (manifest['name'], manifest['version']) or len(matches) != 1 or matches[0].get('version') != manifest['version']:
        raise ValueError('Plugin identity/version differs in Claude manifests.')
    if overlay.get('requires_local_executor') != manifest['extensions']['com.openai'].get('requires_local_executor'):
        raise ValueError('Plugin execution declarations differ between manifests.')
    portable = json.loads((ROOT / 'mcp.json').read_text(encoding='utf-8'))
    legacy = json.loads((ROOT / '.mcp.json').read_text(encoding='utf-8'))
    portable_servers, legacy_servers = portable.get('mcpServers'), legacy.get('mcpServers')
    if (not isinstance(portable_servers, dict) or not portable_servers
            or not isinstance(legacy_servers, dict) or set(portable_servers) != set(legacy_servers)):
        raise ValueError('Portable and compatibility MCP server names must match.')
    for name, config in portable_servers.items():
        compatible = legacy_servers[name]
        if (config.get('type') != 'streamable-http' or compatible.get('type') != 'http'
                or config.get('url') != compatible.get('url')):
            raise ValueError('Portable and compatibility MCP endpoints/transports must agree.')
        url = urlsplit(config.get('url', ''))
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
            raise ValueError('Packaged remote MCP servers need an ordinary HTTPS endpoint.')
    if overlay.get('mcpServers') != './.mcp.json' or claude.get('mcpServers') != './.mcp.json':
        raise ValueError('Compatibility manifests must reference the bundled MCP file.')
    return manifest


def _skill_files() -> list[Path]:
    skill = ROOT / 'skills' / 'academyinfo-flow'
    if _is_link(skill):
        raise ValueError('Skill source may not be a link or junction.')
    files = []
    for current, folders, names in os.walk(skill, followlinks=False):
        base = Path(current)
        for name in list(folders):
            if _is_link(base / name):
                raise ValueError('Skill source may not contain links or junctions.')
            if name in {'__pycache__', '.pytest_cache', '.git', '.venv', 'node_modules'}:
                folders.remove(name)
        for name in names:
            path = base / name
            if _is_link(path) or not path.resolve().is_relative_to(ROOT):
                raise ValueError('Skill source must be a regular in-repository file.')
            if path.suffix not in {'.pyc', '.pyo'}:
                files.append(path)
    if not (skill / 'SKILL.md').is_file():
        raise ValueError('The self-contained skill needs SKILL.md.')
    return sorted(files)


def _write(output: Path, entries: list[tuple[str, Path]]) -> Path:
    output = output.resolve()
    if output.is_relative_to(ROOT / 'skills'):
        raise ValueError('Archives must be outside the skill source.')
    output.parent.mkdir(parents=True, exist_ok=True)
    for name, path in entries:
        if _is_link(path) or not path.resolve().is_relative_to(ROOT) or not path.is_file():
            raise ValueError("Plugin source must be a regular in-repository file.")
        if name.startswith('/') or '..' in Path(name).parts:
            raise ValueError('Archive members must remain relative and contained.')
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in entries:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return output


def build(output: Path | None = None) -> Path:
    manifest = _manifests()
    output = output or ROOT / 'dist' / f"academyinfo-flow-plugin-{manifest['version']}.zip"
    files = [ROOT / relative for relative in ('plugin.json', 'mcp.json', '.mcp.json',
                                             '.codex-plugin/plugin.json', '.claude-plugin/plugin.json', 'LICENSE')]
    files.extend(_skill_files())
    return _write(output, [(path.relative_to(ROOT).as_posix(), path) for path in files])


def build_skill(target: str, output: Path | None = None) -> Path:
    if target not in {'codex', 'claude-web'}:
        raise ValueError('Choose codex or claude-web skill packaging.')
    manifest = _manifests()
    output = output or ROOT / 'dist' / f"academyinfo-flow-skill-{target}-{manifest['version']}.zip"
    skill = ROOT / 'skills' / 'academyinfo-flow'
    files = _skill_files()
    if target == 'claude-web':
        files = [path for path in files if path.relative_to(skill).parts[0] != 'agents']
    return _write(output, [('academyinfo-flow/' + path.relative_to(skill).as_posix(), path) for path in files])


def build_all(output_dir: Path | None = None, *, plugin_output: Path | None = None) -> dict[str, Path]:
    manifest = _manifests()
    directory = output_dir or ROOT / 'dist'
    version = manifest['version']
    return {'plugin': build(plugin_output or directory / f'academyinfo-flow-plugin-{version}.zip'),
            'codex_skill': build_skill('codex', directory / f'academyinfo-flow-skill-codex-{version}.zip'),
            'claude_web_skill': build_skill('claude-web', directory / f'academyinfo-flow-skill-claude-web-{version}.zip')}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    print(json.dumps({key: str(path) for key, path in build_all(args.output_dir, plugin_output=args.output).items()}))
