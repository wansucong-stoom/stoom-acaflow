"""Build the installable plugin from versioned source; exclude test/runtime files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def build(output: Path | None = None) -> Path:
    manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    overlay = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    if manifest["name"] != overlay["name"] or manifest["version"] != overlay["version"]:
        raise ValueError("Plugin identity/version differs between manifests.")
    source_interface = manifest["extensions"]["com.openai"]["interface"]
    if source_interface["defaultPrompt"] != overlay["interface"]["defaultPrompt"]:
        raise ValueError("Plugin default prompts differ between manifests.")
    output = output or ROOT / "dist" / f"academyinfo-flow-{manifest['version']}.zip"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = [ROOT / "plugin.json", ROOT / ".codex-plugin/plugin.json"]
    files.extend(path for path in sorted((ROOT / "skills").rglob("*"))
                 if path.is_file() and "__pycache__" not in path.parts
                 and path.suffix not in {".pyc", ".pyo"})
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("Plugin source must be a regular in-repository file.")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(build(args.output))
