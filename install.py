#!/usr/bin/env python3
"""Install the 대학알리미FLOW skill without network calls or dependencies."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

SKILL_ID = "academyinfo-flow"
DISPLAY_NAME = "대학알리미FLOW"
REPOSITORY = "https://github.com/wansucong-stoom/stoom-acaflow"
REQUIRED_FILES = ("SKILL.md", "scripts/live_json.py", "scripts/live_report.py", "scripts/live_guide.py")
IGNORED_DIRS = {"__pycache__", ".git", ".pytest_cache"}


class InstallError(Exception):
    """A validation or installation failure that leaves existing content intact."""


def is_link(path: Path) -> bool:
    """Also reject Windows junctions/reparse points on Python 3.11."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def inventory(directory: Path) -> dict[str, str]:
    """Hash ordinary contained files; never follow links out of a skill tree."""
    if is_link(directory) or not directory.is_dir():
        raise InstallError(f"Ordinary skill directory required: {directory}")
    root = directory.resolve()
    files: dict[str, str] = {}
    for current, folders, names in os.walk(directory, followlinks=False):
        base = Path(current)
        for name in list(folders):
            entry = base / name
            if is_link(entry):
                raise InstallError(f"Links and junctions are not installed: {entry}")
            if name in IGNORED_DIRS:
                folders.remove(name)
        for name in names:
            entry = base / name
            if is_link(entry):
                raise InstallError(f"Links and junctions are not installed: {entry}")
            resolved = entry.resolve()
            if not resolved.is_relative_to(root) or not stat.S_ISREG(entry.stat().st_mode):
                raise InstallError(f"Ordinary contained file required: {entry}")
            if name.endswith((".pyc", ".pyo")):
                continue
            files[entry.relative_to(directory).as_posix()] = hashlib.sha256(entry.read_bytes()).hexdigest()
    return dict(sorted(files.items()))


def validate_source(root: Path) -> tuple[Path, dict[str, str], str]:
    root = root.resolve()
    manifest_path = root / "plugin.json"
    if is_link(manifest_path) or not manifest_path.is_file():
        raise InstallError("Run install.py from the complete repository checkout; plugin.json is missing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict) or manifest.get("name") != SKILL_ID:
        raise InstallError(f"Unexpected plugin identity; expected {SKILL_ID}.")
    skill = root / "skills" / SKILL_ID
    if is_link(root / "skills") or is_link(skill) or not skill.resolve().is_relative_to(root):
        raise InstallError("The skill source must stay inside the repository.")
    files = inventory(skill)
    missing = [name for name in REQUIRED_FILES if name not in files]
    if missing:
        raise InstallError(f"Incomplete skill package: {', '.join(missing)}")
    text = (skill / "SKILL.md").read_text(encoding="utf-8-sig")
    frontmatter = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", text, re.DOTALL)
    if not frontmatter or not re.search(r"(?m)^name:\s*['\"]?academyinfo-flow['\"]?\s*$", frontmatter[1]):
        raise InstallError(f"SKILL.md must declare name: {SKILL_ID}.")
    return skill, files, str(manifest.get("version", "unknown"))


def detect_client(home: Path) -> str:
    candidates = []
    if shutil.which("codex") or (home / ".codex" / "config.toml").is_file() or os.environ.get("CODEX_THREAD_ID"):
        candidates.append("codex")
    if shutil.which("claude") or (home / ".claude" / "settings.json").is_file() or os.environ.get("CLAUDECODE"):
        candidates.append("claude-code")
    if len(candidates) != 1:
        found = ", ".join(candidates) if candidates else "none"
        raise InstallError(f"Client detection found {found}. Choose --client codex, --client claude-code, or --client both.")
    return candidates[0]


def backup_directory(target: Path) -> Path:
    skills_root = target.parent
    label = "skill-backups" if skills_root.name == "skills" else f"{skills_root.name}.backups"
    return skills_root.parent / label


def destinations(args: argparse.Namespace, home: Path, source: Path) -> dict[str, Path]:
    choice = args.client or detect_client(home)
    clients = ("codex", "claude-code") if choice == "both" else (choice,)
    if args.dest and choice == "both":
        raise InstallError("--dest accepts one client. For both use --codex-dest and --claude-dest.")
    if args.codex_dest and "codex" not in clients or args.claude_dest and "claude-code" not in clients:
        raise InstallError("A destination override must match a selected client.")
    roots = {
        "codex": Path(args.codex_dest).expanduser() if args.codex_dest else home / ".agents" / "skills",
        "claude-code": Path(args.claude_dest).expanduser() if args.claude_dest else home / ".claude" / "skills",
    }
    if args.dest:
        roots[clients[0]] = Path(args.dest).expanduser()
    targets: dict[str, Path] = {}
    for client in clients:
        root = roots[client].absolute()
        if is_link(root) or is_link(root / SKILL_ID):
            raise InstallError(f"The install destination may not be a link or junction: {root / SKILL_ID}")
        target = root.resolve() / SKILL_ID
        if target.is_relative_to(source.resolve()) or source.resolve().is_relative_to(target):
            raise InstallError("The install destination and source skill must be separate.")
        if client == "codex" and not (args.dest or args.codex_dest):
            legacy_root = Path(os.environ.get("CODEX_HOME", str(home / ".codex"))) / "skills"
            legacy = legacy_root / SKILL_ID
            if legacy.exists() or is_link(legacy):
                raise InstallError(
                    f"An older Codex skill already exists at {legacy}. To preserve it and avoid duplicate skills, "
                    f"inspect it and explicitly choose --dest \"{legacy_root}\" or move it yourself."
                )
        if any(target.parent.is_relative_to(other.parent) or other.parent.is_relative_to(target.parent) for other in targets.values()):
            raise InstallError("Each selected client needs a separate, non-nested skills directory.")
        targets[client] = target
    for target in targets.values():
        backup_root = backup_directory(target).resolve()
        if any(backup_root.is_relative_to(other.parent) for other in targets.values()):
            raise InstallError("A backup directory would fall inside another selected client's skills directory. Choose separate destinations.")
    return targets


def inspect_target(target: Path, files: dict[str, str]) -> str:
    if is_link(target):
        raise InstallError(f"The destination may not be a link or junction: {target}")
    if not target.exists():
        return "missing"
    if not target.is_dir():
        raise InstallError(f"The destination is a file: {target}")
    return "installed" if inventory(target) == files else "changed"


def install_target(source: Path, target: Path, files: dict[str, str], update: bool) -> dict:
    status = inspect_target(target, files)
    result = {"path": str(target), "status": status}
    if status == "installed":
        return {**result, "action": "unchanged"}
    if status == "changed" and not update:
        raise InstallError(f"Existing skill differs: {target}. Review the changes, then use --update to back it up and replace it.")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{SKILL_ID}-stage-", dir=target.parent))
    backup = None
    try:
        for relative in files:
            origin = source / relative
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Recheck before copying in case the checkout was edited after preflight.
            if is_link(origin) or not origin.resolve().is_relative_to(source.resolve()):
                raise InstallError(f"The source changed during installation: {origin}")
            shutil.copy2(origin, destination)
        if inventory(stage) != files:
            raise InstallError("The source changed during installation. No installed files were replaced.")
        # A newly created destination must not be overwritten between preflight and commit.
        if inspect_target(target, files) != status:
            raise InstallError("The destination changed during installation. Retry after inspecting it.")
        if status == "changed":
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            # Skill scanners read every child of a skills root. Preserve backups
            # outside that root so the previous SKILL.md cannot load twice.
            backup_root = backup_directory(target)
            if is_link(backup_root) or backup_root.resolve().is_relative_to(target.parent.resolve()):
                raise InstallError(f"A separate ordinary backup directory is required: {backup_root}")
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root / f"{SKILL_ID}.backup-{timestamp}-{uuid4().hex[:8]}"
            target.rename(backup)
        try:
            stage.rename(target)
        except Exception:
            if backup is not None:
                backup.rename(target)
            raise
        return {"path": str(target), "status": "installed", "action": "updated" if backup else "installed", "backup": str(backup) if backup else None}
    finally:
        # This is only the fresh staging directory created above, never the user's skill.
        if stage.exists() and stage.parent.resolve() == target.parent.resolve() and not is_link(stage):
            shutil.rmtree(stage)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Install {DISPLAY_NAME} as a personal local skill. No packages, MCP settings, or hooks are installed.")
    parser.add_argument("--client", choices=("codex", "claude-code", "both"), help="Choose a client; omitted only when one client can be detected.")
    parser.add_argument("--dest", help="Override the selected client's skills parent directory (academyinfo-flow is appended).")
    parser.add_argument("--codex-dest", help="Override Codex's skills parent directory, including when --client both is used.")
    parser.add_argument("--claude-dest", help="Override Claude Code's skills parent directory, including when --client both is used.")
    parser.add_argument("--check", action="store_true", help="Compare all installed files with this checkout without writing files.")
    parser.add_argument("--update", action="store_true", help="Replace a differing skill after moving the complete previous directory to a backup.")
    return parser


def main(argv: list[str] | None = None, *, source_root: Path | None = None, home: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = {"name": DISPLAY_NAME, "skill_id": SKILL_ID, "repository": REPOSITORY, "mode": "check" if args.check else "install", "results": []}
    try:
        if sys.version_info < (3, 11):
            raise InstallError("Python 3.11 or newer is required.")
        source, files, version = validate_source(source_root or Path(__file__).resolve().parent)
        result["version"] = version
        result["source_sha256"] = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        targets = destinations(args, home or Path.home(), source)
        # Validate every client before making the first change.
        statuses = {client: inspect_target(target, files) for client, target in targets.items()}
        if not args.check and not args.update:
            conflicts = [str(targets[client]) for client, status in statuses.items() if status == "changed"]
            if conflicts:
                raise InstallError(f"Existing skill differs: {', '.join(conflicts)}. Review the changes, then use --update to preserve a backup and replace it.")
        for client, target in targets.items():
            if args.check:
                entry = {"path": str(target), "status": statuses[client]}
            else:
                entry = install_target(source, target, files, args.update)
            result["results"].append({"client": client, **entry})
        result["ok"] = all(entry["status"] == "installed" for entry in result["results"])
    except (InstallError, OSError, ValueError) as error:
        result["ok"] = False
        result["error"] = str(error)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
