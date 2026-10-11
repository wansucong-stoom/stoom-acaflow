"""Offline installer tests. All user directories are isolated temporary fixtures."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("flow_installer", Path(__file__).resolve().parents[1] / "install.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repository"
        self.skill = self.repo / "skills" / installer.SKILL_ID
        self.skill.mkdir(parents=True)
        (self.repo / "plugin.json").write_text(json.dumps({"name": installer.SKILL_ID, "version": "0.1.0"}), encoding="utf-8")
        for relative in installer.REQUIRED_FILES:
            content = "---\nname: academyinfo-flow\ndescription: 대학알리미FLOW\n---\n# 대학알리미FLOW\n" if relative == "SKILL.md" else "print('fixture')\n"
            self.write(self.skill / relative, content)
        self.write(self.skill / "references" / "guide.json", '{"source":"official"}\n')
        self.write(self.skill / "scripts" / "vendor" / "runtime.py", "# bundled runtime\n")
        self.write(self.skill / "agents" / "openai.yaml", 'interface:\n  display_name: "대학알리미FLOW"\n')
        self.home = self.root / "user"
        self.home.mkdir()

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def run_install(self, *args):
        output = io.StringIO()
        with redirect_stdout(output), patch.dict(os.environ, {}, clear=True):
            code = installer.main(list(args), source_root=self.repo, home=self.home)
        return code, json.loads(output.getvalue())

    def target(self, client="codex"):
        folder = ".agents" if client == "codex" else ".claude"
        return self.home / folder / "skills" / installer.SKILL_ID

    def test_codex_copies_all_supporting_files_and_ignores_generated_cache(self):
        self.write(self.skill / "__pycache__" / "cache.pyc", "cache")
        code, result = self.run_install("--client", "codex")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["name"], "대학알리미FLOW")
        self.assertEqual(installer.inventory(self.target()), installer.inventory(self.skill))
        self.assertTrue((self.target() / "scripts" / "vendor" / "runtime.py").is_file())
        self.assertFalse((self.target() / "__pycache__").exists())
        self.assertFalse((self.home / ".codex").exists())

    def test_claude_destination_override_appends_skill_id(self):
        destination = self.root / "custom-skills"
        code, result = self.run_install("--client", "claude-code", "--dest", str(destination))
        self.assertEqual(code, 0, result)
        self.assertTrue((destination / installer.SKILL_ID / "SKILL.md").is_file())
        self.assertFalse(self.target("claude-code").exists())

    def test_both_clients_have_separate_independent_copies(self):
        code, result = self.run_install("--client", "both")
        self.assertEqual(code, 0, result)
        self.assertEqual(len(result["results"]), 2)
        self.write(self.target() / "SKILL.md", "a local Codex edit")
        self.assertEqual((self.target("claude-code") / "SKILL.md").read_bytes(), (self.skill / "SKILL.md").read_bytes())

    def test_identical_reinstall_does_not_backup_or_replace_files(self):
        self.run_install("--client", "codex")
        before = (self.target() / "SKILL.md").stat().st_mtime_ns
        code, result = self.run_install("--client", "codex")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["results"][0]["action"], "unchanged")
        self.assertEqual((self.target() / "SKILL.md").stat().st_mtime_ns, before)
        self.assertEqual(list(self.target().parent.glob("*.backup-*")), [])

    def test_differing_install_refuses_to_overwrite(self):
        self.run_install("--client", "codex")
        self.write(self.target() / "SKILL.md", "user-owned edit")
        code, result = self.run_install("--client", "codex")
        self.assertEqual(code, 1)
        self.assertIn("--update", result["error"])
        self.assertEqual((self.target() / "SKILL.md").read_text(), "user-owned edit")

    def test_explicit_update_preserves_entire_old_directory(self):
        self.run_install("--client", "codex")
        self.write(self.target() / "notes.txt", "keep this file")
        self.write(self.target() / "SKILL.md", "user-owned edit")
        code, result = self.run_install("--client", "codex", "--update")
        self.assertEqual(code, 0, result)
        entry = result["results"][0]
        self.assertEqual(entry["action"], "updated")
        backup = Path(entry["backup"])
        self.assertFalse(backup.is_relative_to(self.target().parent))
        self.assertEqual(backup.parent.resolve(), (self.home / ".agents" / "skill-backups").resolve())
        self.assertEqual((backup / "SKILL.md").read_text(), "user-owned edit")
        self.assertEqual((backup / "notes.txt").read_text(), "keep this file")
        self.assertEqual(installer.inventory(self.target()), installer.inventory(self.skill))

    def test_custom_backup_stays_outside_even_when_skills_root_is_named_skill_backups(self):
        destination = self.root / "skill-backups"
        self.run_install("--client", "claude-code", "--dest", str(destination))
        self.write(destination / installer.SKILL_ID / "SKILL.md", "local edit")
        code, result = self.run_install("--client", "claude-code", "--dest", str(destination), "--update")
        self.assertEqual(code, 0, result)
        backup = Path(result["results"][0]["backup"])
        self.assertFalse(backup.is_relative_to(destination))
        self.assertEqual((backup / "SKILL.md").read_text(), "local edit")

    def test_both_conflict_is_detected_before_any_client_changes(self):
        self.write(self.target("claude-code") / "SKILL.md", "local Claude skill")
        code, _ = self.run_install("--client", "both")
        self.assertEqual(code, 1)
        self.assertFalse(self.target().exists())
        self.assertEqual((self.target("claude-code") / "SKILL.md").read_text(), "local Claude skill")

    def test_check_missing_never_creates_destination(self):
        code, result = self.run_install("--client", "codex", "--check")
        self.assertEqual(code, 1)
        self.assertEqual(result["results"][0]["status"], "missing")
        self.assertFalse((self.home / ".agents").exists())

    def test_check_detects_changed_supporting_file_without_writing(self):
        self.run_install("--client", "claude-code")
        code, _ = self.run_install("--client", "claude-code", "--check")
        self.assertEqual(code, 0)
        self.write(self.target("claude-code") / "references" / "guide.json", "changed")
        code, result = self.run_install("--client", "claude-code", "--check")
        self.assertEqual(code, 1)
        self.assertEqual(result["results"][0]["status"], "changed")
        self.assertEqual((self.target("claude-code") / "references" / "guide.json").read_text(), "changed")

    def test_source_skill_identity_is_verified(self):
        self.write(self.skill / "SKILL.md", "---\nname: other-skill\n---\n")
        code, result = self.run_install("--client", "codex")
        self.assertEqual(code, 1)
        self.assertIn("SKILL.md", result["error"])
        self.assertFalse(self.target().exists())

    def test_incomplete_package_refuses_install(self):
        (self.skill / "scripts" / "live_json.py").unlink()
        code, result = self.run_install("--client", "codex")
        self.assertEqual(code, 1)
        self.assertIn("Incomplete", result["error"])

    def test_malformed_manifest_identity_is_rejected(self):
        (self.repo / "plugin.json").write_text("[]", encoding="utf-8")
        code, result = self.run_install("--client", "codex")
        self.assertEqual(code, 1)
        self.assertIn("identity", result["error"])

    def test_source_symlink_to_outside_is_rejected(self):
        outside = self.root / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        try:
            (self.skill / "outside-link.txt").symlink_to(outside)
        except OSError:
            self.skipTest("This host does not permit creating symlinks.")
        code, result = self.run_install("--client", "codex")
        self.assertEqual(code, 1)
        self.assertIn("Links", result["error"])
        self.assertFalse(self.target().exists())

    def test_ambiguous_detection_requires_explicit_client(self):
        self.write(self.home / ".codex" / "config.toml", "")
        self.write(self.home / ".claude" / "settings.json", "{}")
        with patch.object(installer.shutil, "which", return_value=None):
            code, result = self.run_install()
        self.assertEqual(code, 1)
        self.assertIn("--client", result["error"])
        self.assertFalse(self.target().exists())
        self.assertFalse(self.target("claude-code").exists())

    def test_single_detected_client_can_install(self):
        self.write(self.home / ".claude" / "settings.json", "{}")
        with patch.object(installer.shutil, "which", return_value=None):
            code, result = self.run_install()
        self.assertEqual(code, 0, result)
        self.assertTrue(self.target("claude-code").exists())
        self.assertFalse(self.target().exists())

    def test_legacy_codex_skill_is_preserved_without_duplicate_install(self):
        legacy = self.home / ".codex" / "skills" / installer.SKILL_ID
        self.write(legacy / "SKILL.md", "old skill")
        code, result = self.run_install("--client", "codex")
        self.assertEqual(code, 1)
        self.assertIn("older Codex", result["error"])
        self.assertFalse(self.target().exists())
        self.assertEqual((legacy / "SKILL.md").read_text(), "old skill")

    def test_same_or_nested_client_destinations_are_rejected(self):
        common = self.root / "skills"
        for claude_root in (common, common / installer.SKILL_ID):
            code, result = self.run_install("--client", "both", "--codex-dest", str(common), "--claude-dest", str(claude_root))
            self.assertEqual(code, 1)
            self.assertIn("non-nested", result["error"])
        self.assertFalse(common.exists())

    def test_existing_file_is_preserved(self):
        self.write(self.target(), "existing file")
        code, result = self.run_install("--client", "codex", "--update")
        self.assertEqual(code, 1)
        self.assertIn("is a file", result["error"])
        self.assertEqual(self.target().read_text(), "existing file")

    def test_backup_cannot_fall_inside_other_clients_scan_root(self):
        codex_root = self.root / "skills"
        claude_root = self.root / "skill-backups"
        code, result = self.run_install("--client", "both", "--codex-dest", str(codex_root), "--claude-dest", str(claude_root))
        self.assertEqual(code, 1)
        self.assertIn("backup directory", result["error"])
        self.assertFalse(codex_root.exists())
        self.assertFalse(claude_root.exists())


if __name__ == "__main__":
    unittest.main()
